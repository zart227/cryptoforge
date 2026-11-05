"""Versioned v3 candidate offline cleaned exchange records. No transport, credentials, quotas or model actions.

The complete JSON body after bounded redaction is retained, with exact Decimal
values represented as strings. Raw response bytes and HTTP headers are never
saved. This is a tested record contract, not a live provider capture or general
PII attestation; an operational transport must bind it to its existing journal.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re

from cryptoforge import llm_research_advisor as advisor
from cryptoforge.llm_candidate_adapter_v3 import CandidateAdvisor
from cryptoforge.llm_research_contracts import strict_json, validate_proposal
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp
from cryptoforge import research_local_export as private
from cryptoforge import semantic_source_collector as files

CANDIDATE_MODEL = 'nvidia/nemotron-3.5-super-vl:free'

POLICY = {'schema_version': 'cleaned-advisor-exchange-candidate-policy-v3', 'candidate_model': CANDIDATE_MODEL, 'maximum_raw_response_bytes': 1000000,
    'maximum_cleaned_response_bytes': 1000000, 'maximum_record_bytes': 1200000, 'maximum_depth': 12,
    'maximum_container_items': 128, 'maximum_known_secrets': 16, 'maximum_usage_tokens': 10000000,
    'maximum_credit_amount': '1000000000000', 'response_decimal_values': 'exact_strings',
    'non_JSON_response': 'metadata_only_no_raw_text', 'unknown_privacy_claims': 'not_attested',
    'network_or_key_reads_enabled': False, 'operational_capture_integrated': False, 'new_allowance_created': False}
SENSITIVE = {'authorization', 'apikey', 'password', 'passwd', 'secret', 'token', 'accesstoken', 'refreshtoken',
    'credentials', 'headers', 'cookie', 'setcookie', 'email', 'userid', 'organizationid'}
OPAQUE = {'id', 'requestid', 'generationid'}
PATTERNS = (
    ('credential_pattern', re.compile(r'\bsk-(?:or-v1-)?[A-Za-z0-9_-]{16,}')),
    ('credential_pattern', re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]{8,}')),
    ('credential_pattern', re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}')),
    ('credential_pattern', re.compile(r'(?i)\b(?:https?|postgres(?:ql)?)://[^/\s@]+@')),
    ('email_pattern', re.compile(r'\b[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b')),
    ('credential_pattern', re.compile(r'(?i)\b(?:[A-Z_]*API_KEY|PASSWORD|SECRET|ACCESS_TOKEN)["\x27]?\s*[:=]\s*(?:"[^"\n]*"|\x27[^\x27\n]*\x27|[^\s,;]+)')),
)


def implementation():
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {
        'audit': Path(__file__), 'advisor': Path(advisor.__file__),
        'contracts': Path(__file__).with_name('llm_research_contracts.py'),
        'preflight': Path(__file__).with_name('llm_prompt_preflight.py'),
        'candidate_adapter': Path(__file__).with_name('llm_candidate_adapter_v3.py'),
        'candidate_payload': Path(__file__).with_name('llm_candidate_payload_v3.py'),
        'diagnostics': Path(__file__).with_name('training_diagnostics.py')}.items()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY or CANDIDATE_MODEL != POLICY['candidate_model']: raise ValueError('fixed_cleaned_exchange_policy_required')


def _parse(raw):
    def fields(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate_outer_response_key')
            result[key] = value
        return result
    def constant(value): raise ValueError('finite_outer_response_required')
    try: result = json.loads(raw, parse_float=Decimal, object_pairs_hook=fields, parse_constant=constant)
    except (ValueError, TypeError, OverflowError, RecursionError): raise ValueError('strict_outer_response_required') from None
    if type(result) is not dict: raise ValueError('outer_response_object_required')
    return result


def scrub(value, secrets=()):
    if type(secrets) is not tuple or len(secrets) > 16 or any(type(s) is not str or not 8 <= len(s) <= 8192 for s in secrets):
        raise ValueError('bounded_ephemeral_secret_tuple_required')
    secrets = sorted(set(secrets), key=len, reverse=True)
    counts = {k: 0 for k in ('known_secret', 'credential_pattern', 'email_pattern', 'sensitive_field', 'opaque_identifier', 'unsafe_key')}
    def text(value):
        original = value
        value = re.sub(r'\\u00([0-9a-fA-F]{2})', lambda match: chr(int(match[1], 16)) if 32 <= int(match[1], 16) <= 126 else match[0], value)
        before = sum(counts.values())
        for secret in secrets:
            counts['known_secret'] += value.count(secret); value = value.replace(secret, '[REDACTED]')
        for kind, pattern in PATTERNS:
            value, count = pattern.subn('[REDACTED]', value); counts[kind] += count
        return value if sum(counts.values()) != before else original
    def clean(value, depth):
        if depth > 12: raise ValueError('response_depth_exceeded')
        if value is None or type(value) is bool: return value
        if type(value) is int:
            if len(str(value)) > 32: raise ValueError('bounded_response_integer_required')
            return value
        if type(value) is Decimal:
            if not value.is_finite() or value.copy_abs() > Decimal('1e100') or value.as_tuple().exponent < -100:
                raise ValueError('bounded_response_decimal_required')
            return str(value)
        if type(value) is float:
            if not math.isfinite(value) or abs(value) > 1e100: raise ValueError('bounded_response_float_required')
            return value
        if type(value) is str:
            if value.lstrip().startswith(('{', '[')):
                try: nested = strict_json(value, max_bytes=1000000)
                except ValueError: nested = None
                if type(nested) in (dict, list): return canonical(clean(nested, depth+1))
            return text(value)
        if type(value) is list:
            if len(value) > 128: raise ValueError('response_list_limit')
            return [clean(item, depth+1) for item in value]
        if type(value) is dict:
            if len(value) > 128: raise ValueError('response_object_limit')
            result = {}
            for key, child in value.items():
                if type(key) is not str: raise ValueError('string_response_keys_required')
                normalized = re.sub('[^a-z0-9]', '', key.lower())
                safe = text(key)
                if safe != key or re.fullmatch(r'[A-Za-z0-9_./:-]{1,100}', key) is None:
                    counts['unsafe_key'] += 1; safe = 'redacted_field_'+str(len(result))
                if safe in result: raise ValueError('cleaned_response_key_collision')
                if normalized in SENSITIVE: counts['sensitive_field'] += 1; result[safe] = '[REDACTED]'
                elif normalized in OPAQUE:
                    clean(child, depth+1)
                    counts['opaque_identifier'] += 1; result[safe] = '[REDACTED:identifier]'
                else: result[safe] = clean(child, depth+1)
            return result
        raise ValueError('supported_bounded_response_values_required')
    return clean(value, 0), counts


def _counter(usage, key):
    value = usage.get(key)
    if value is None: return None
    if type(value) is not int or not 0 <= value <= 10000000: raise ValueError('bounded_native_usage_required')
    return value


def _cost(usage):
    value = usage.get('cost')
    if value is None: return None
    if type(value) not in (int, str, Decimal) or len(str(value)) > 80: raise ValueError('bounded_native_cost_required')
    try: number = Decimal(str(value))
    except InvalidOperation: raise ValueError('bounded_native_cost_required') from None
    if not number.is_finite() or not 0 <= number <= Decimal('1e12') or number.as_tuple().exponent < -24: raise ValueError('bounded_native_cost_required')
    return str(number)


def _usage(response, provider):
    usage = response.get('usage') if provider == 'openrouter' else response
    if usage is None: usage = {}
    keys = {'prompt_tokens': 'prompt_tokens', 'completion_tokens': 'completion_tokens', 'total_tokens': 'total_tokens'} if provider == 'openrouter' else {'prompt_tokens': 'prompt_eval_count', 'completion_tokens': 'eval_count'}
    tokens = {key: None for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}; errors = []
    if type(usage) is not dict: return tokens, None, ['usage_not_an_object']
    for target, native in keys.items():
        try: tokens[target] = _counter(usage, native)
        except ValueError: errors.append('invalid_'+target)
    cost = None
    if provider == 'openrouter':
        try: cost = _cost(usage)
        except ValueError: errors.append('invalid_native_cost')
        if all(value is not None for value in tokens.values()) and tokens['total_tokens'] != tokens['prompt_tokens']+tokens['completion_tokens']: errors.append('inconsistent_token_total')
        if cost is not None and Decimal(cost) != 0: errors.append('nonzero_reported_cost_on_free_route')
    elif tokens['prompt_tokens'] is not None and tokens['completion_tokens'] is not None:
        total = tokens['prompt_tokens']+tokens['completion_tokens']
        if total > 10000000: errors.append('derived_total_out_of_bounds')
        else: tokens['total_tokens'] = total
    return tokens, cost, errors


def _validate(response, report, provider, model, parameters):
    if response.get('error') is not None: raise ValueError('provider_error_response')
    if provider == 'openrouter':
        choices = response.get('choices')
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict: raise ValueError('single_complete_choice_required')
        choice = choices[0]; message = choice.get('message')
        if choice.get('finish_reason') != 'stop' or response.get('model') not in (model, model.removesuffix(':free')): raise ValueError('model_or_finish_reason_changed')
    else:
        if response.get('done') is not True or response.get('done_reason') != 'stop' or response.get('model') != model: raise ValueError('model_or_finish_reason_changed')
        message = response.get('message')
    if type(message) is not dict or message.get('role') != 'assistant' or message.get('tool_calls') or message.get('function_call') or message.get('refusal'):
        raise ValueError('assistant_text_without_tools_or_refusal_required')
    proposal = validate_proposal(strict_json(message.get('content')), report)
    if proposal['parameter'] not in parameters: raise ValueError('unsupported_worker_parameter')
    return proposal


def build(report, response_bytes, *, provider='openrouter', model=CANDIDATE_MODEL, parameters=('l2', 'threshold'), observed_at, known_secrets=()):
    _guard()
    try: when = timestamp(observed_at)
    except (ValueError, TypeError): raise ValueError('bounded_exchange_timestamp_required') from None
    if not 2020 <= when.year <= 2100: raise ValueError('bounded_exchange_timestamp_required')
    if type(response_bytes) is not bytes or len(response_bytes) > 1000000: raise ValueError('bounded_response_bytes_required')
    if provider == 'openrouter' and (model != CANDIDATE_MODEL or not model.endswith(':free')): raise ValueError('fixed_free_exchange_model_required')
    prepared = CandidateAdvisor(provider=provider, model=model, parameters=parameters).preflight(report)
    cleaned_request, request_redactions = scrub(prepared['payload'], known_secrets)
    response = None; cleaned_response = None; redactions = None; status = 'rejected_outer_response'; reason = 'outer_response_invalid_or_outside_cleaning_bounds'
    try:
        response = _parse(response_bytes); cleaned_response, redactions = scrub(response, known_secrets)
        if len(canonical(cleaned_response).encode()) > 1000000: raise ValueError('cleaned_response_byte_limit')
    except (ValueError, TypeError, RecursionError): cleaned_response = None
    proposal = None; tokens = {key: None for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}; cost = None; usage_errors = []
    if response is not None: tokens, cost, usage_errors = _usage(response, provider)
    sensitive = lambda counts: counts and any(counts[key] for key in counts if key != 'opaque_identifier')
    if sensitive(request_redactions): status = 'rejected_request_privacy'; reason = 'request_required_redaction'
    elif cleaned_response is not None:
        if sensitive(redactions): status = 'rejected_response_privacy'; reason = 'response_required_sensitive_redaction'
        else:
            try:
                if usage_errors: raise ValueError('native_usage_contract_failed')
                proposal = _validate(response, report, provider, model, parameters)
                status = 'proposal_schema_valid_only'; reason = None
            except (ValueError, TypeError, KeyError, IndexError): status = 'rejected_response_contract'; reason = 'provider_identity_usage_or_proposal_contract_failed'
    record = {'request': cleaned_request, 'response': {'cleaned_body': cleaned_response,
            'full_cleaned_JSON_body_available': cleaned_response is not None, 'raw_body_saved': False},
        'validation': {'schema_version': 'cleaned-exchange-validation-v1', 'status': status, 'reason': reason,
            'proposal': proposal, 'usage': tokens, 'provider_reported_cost_usd': cost, 'usage_errors': usage_errors,
            'usage_unavailable_means_zero': False, 'semantic_truth_or_usefulness_verified': False,
            'training_or_provider_action_authorized': False},
        'provenance': {'schema_version': 'cleaned-exchange-provenance-v1', 'observed_at': when.isoformat(),
            'scope': 'offline_validation_record_not_live_capture', 'provider': provider, 'requested_model': model,
            'report_sha256': digest(report), 'original_request_factory_payload_sha256': digest(prepared['payload']),
            'original_response_body_sha256': hashlib.sha256(response_bytes).hexdigest(), 'original_response_bytes': len(response_bytes),
            'request_redactions': request_redactions, 'response_redactions': redactions, 'known_secret_count': len(known_secrets),
            'HTTP_headers_or_credentials_saved': False, 'new_network_key_reads_or_journal_reservations': 0,
            'provider_generation_performed_by_this_module': False, 'account_billing_or_global_PII_attested': False}}
    if len(canonical(record).encode()) > 1200000: raise ValueError('cleaned_exchange_total_byte_limit')
    return record


def save(directory, record, *, known_secrets=()):
    _guard(); directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_cleaned_exchange_directory_required')
    exact_fields(record, {'request', 'response', 'validation', 'provenance'})
    if record['provenance']['scope'] != 'offline_validation_record_not_live_capture': raise ValueError('offline_record_scope_required')
    if record['provenance']['known_secret_count'] != len(known_secrets): raise ValueError('same_ephemeral_redaction_scope_required')
    for name in ('request', 'response', 'validation', 'provenance'):
        cleaned, _ = scrub(record[name], known_secrets)
        if cleaned != record[name]: raise ValueError('uncleaned_exchange_record_refused')
    if len(canonical(record).encode()) > 1200000: raise ValueError('cleaned_exchange_total_byte_limit')
    directory.mkdir(mode=0o700)
    for name, value in [('policy.json', POLICY)]+[(name+'.json', value) for name, value in record.items()]: files._write(directory, name, value)
    manifest = {'schema_version': 'cleaned-exchange-pack-v1', 'implementation': _LOADED,
        'files': {name: hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('policy.json', 'request.json', 'response.json', 'validation.json', 'provenance.json')}}
    files._write(directory, 'manifest.json', manifest); return manifest


def verify(directory):
    _guard(); directory = private._safe_directory(directory, private=True)
    from cryptoforge import research_data_protocol as temporal
    read = lambda name: temporal._read(directory, name, 1200000)
    manifest = read('manifest.json'); exact_fields(manifest, {'schema_version', 'implementation', 'files'})
    names = {'policy.json', 'request.json', 'response.json', 'validation.json', 'provenance.json'}
    if manifest['schema_version'] != 'cleaned-exchange-pack-v1' or manifest['implementation'] != _LOADED or set(manifest['files']) != names or read('policy.json') != POLICY:
        raise ValueError('original_cleaned_exchange_manifest_required')
    for name, value in manifest['files'].items():
        if hashlib.sha256(private._private_read(directory, name, 1200000)).hexdigest() != value: raise ValueError('original_cleaned_exchange_file_changed')
    return read('validation.json')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv)
    try: result = verify(args.directory)
    except Exception:
        print('Cleaned exchange verification refused; no provider or training authorization'); return 2
    print('Cleaned exchange: '+result['status']+'; no provider or training authorization'); return 0


if __name__ == '__main__': raise SystemExit(main())
