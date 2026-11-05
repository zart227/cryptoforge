"""Closed validation-record inputs and typed local System One results."""
from copy import deepcopy
import hashlib
from pathlib import Path

from cryptoforge import llm_research_contracts, semantic_research_catalog, training_diagnostics, typesafe_judgment_contracts, ollama_decision_readiness
from cryptoforge.ollama_decision_readiness import local_endpoint, model_digest
from cryptoforge.semantic_research_catalog import validate_record
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp
from cryptoforge.typesafe_judgment_contracts import validate_catalog, normalize_answer


SUPPORTED_SERVER_VERSION = '0.40.5'
MAX_WIRE_BYTES = 48000


def implementation():
    return {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in {
        'contracts': __file__, 'json': llm_research_contracts.__file__,
        'record': semantic_research_catalog.__file__, 'canonical': training_diagnostics.__file__,
        'normalizer': typesafe_judgment_contracts.__file__, 'endpoint': ollama_decision_readiness.__file__}.items()}


def prepare_request(record, catalog, *, endpoint, digest_pin, version=SUPPORTED_SERVER_VERSION):
    record, catalog = deepcopy(validate_record(record)), deepcopy(validate_catalog(catalog))
    if version != SUPPORTED_SERVER_VERSION:
        raise ValueError('checked Ollama 0.40.5 digest-reference profile required')
    pin = model_digest(digest_pin)
    reference = 'sha256-' + pin.removeprefix('sha256:') + ':local'
    state = {'experiment': record}
    if len(canonical(state).encode()) > 32000:
        raise ValueError('bounded closed validation state required')
    wire = {'model': reference, 'state': state, 'keep_alive': 0,
        'questions': {name: {key: deepcopy(q[key]) for key in ('type', 'instructions', 'criteria')}
                      for name, q in catalog['questions'].items()}}
    size = len(canonical(wire).encode())
    if size > MAX_WIRE_BYTES:
        raise ValueError('bounded semantic payload required; no truncation')
    core = {'schema_version': 'local-semantic-request-v1', 'origin': 'closed_validation_research_record',
        'endpoint': local_endpoint(endpoint), 'record': record, 'catalog': catalog,
        'model_digest': pin, 'model_reference': reference, 'server_version': version,
        'wire_request': wire, 'wire_bytes': size, 'implementation': implementation(),
        'hard_input_token_limit_verified': False, 'byte_limit_is_token_limit': False}
    return {**core, 'request_sha256': digest(core)}


def validate_request(request):
    if isinstance(request, dict) and request.get('schema_version') == 'local-semantic-source-request-v2':
        from cryptoforge.source_semantic_contracts import validate_request as validate_source
        return validate_source(request)
    exact_fields(request, {'schema_version', 'origin', 'endpoint', 'record', 'catalog',
        'model_digest', 'model_reference', 'server_version', 'wire_request', 'wire_bytes', 'implementation',
        'hard_input_token_limit_verified', 'byte_limit_is_token_limit', 'request_sha256'})
    rebuilt = prepare_request(request['record'], request['catalog'], endpoint=request['endpoint'],
        digest_pin=request['model_digest'], version=request['server_version'])
    if canonical(rebuilt) != canonical(request):
        raise ValueError('semantic request or implementation changed')
    return request


def inference_identity(request):
    """Stable provider work identity; code-side thresholds need no new inference."""
    return digest({'schema_version': 'local-semantic-inference-identity-v1',
        'endpoint': request['endpoint'], 'server_version': request['server_version'],
        'model_digest': request['model_digest'], 'wire_sha256': digest(request['wire_request'])})


def check_show_metadata(show, request):
    if not isinstance(show, dict) or any(key in show and show[key] != '' for key in ('remote_host', 'remote_model')):
        raise ValueError('remote or invalid model metadata refused')
    capabilities = show.get('capabilities')
    if (not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 16
            or any(not isinstance(c, str) or not 1 <= len(c) <= 64 for c in capabilities)
            or len(set(capabilities)) != len(capabilities) or 'decision' not in capabilities):
        raise ValueError('decision capability required')
    manifests = show.get('manifests', [])
    if not isinstance(manifests, list) or len(manifests) > 1:
        raise ValueError('single pinned leaf manifest required')
    if manifests:
        item = manifests[0]
        if (not isinstance(item, dict) or item.get('selected') is not True
                or model_digest(item.get('digest')) != request['model_digest']):
            raise ValueError('manifest selection differs from pinned leaf')
    return sorted(capabilities)


def count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise ValueError('explicit nonnegative semantic token count required')
    return value


def normalize_transport(request, transport):
    validate_request(request)
    exact_fields(transport, {'request_sha256', 'inference_identity_sha256', 'response', 'metadata'})
    model_digest(transport['request_sha256'])
    if transport['inference_identity_sha256'] != inference_identity(request):
        raise ValueError('semantic transport inference identity mismatch')
    source_request = request['schema_version'] == 'local-semantic-source-request-v2'
    metadata = transport['metadata']
    exact_fields(metadata, {'server_version', 'model_reference', 'version_before_sha256', 'version_after_sha256',
        'show_sha256', 'capabilities', 'checked_at'} | ({'response_received_at'} if source_request else set()))
    if metadata['server_version'] != request['server_version'] or metadata['model_reference'] != request['model_reference']:
        raise ValueError('semantic metadata identity mismatch')
    timestamp(metadata['checked_at'])
    if source_request and timestamp(metadata['response_received_at']) > timestamp(metadata['checked_at']):
        raise ValueError('semantic receipt clock order changed')
    if source_request and timestamp(metadata['response_received_at']) < timestamp(request['packet']['parameters']['decision_time']):
        raise ValueError('semantic response precedes source decision time')
    for key in ('version_before_sha256', 'version_after_sha256', 'show_sha256'):
        model_digest(metadata[key])
    expected_version_sha = digest({'version': request['server_version']})
    if metadata['version_before_sha256'] != expected_version_sha or metadata['version_after_sha256'] != expected_version_sha:
        raise ValueError('semantic version observation mismatch')
    check_show_metadata({'capabilities': metadata['capabilities']}, request)
    response = transport['response']
    if len(canonical(response).encode()) > 64000:
        raise ValueError('semantic response too large')
    optional = {'prompt_eval_cached_count'} if isinstance(response, dict) and 'prompt_eval_cached_count' in response else set()
    exact_fields(response, {'model', 'answers', 'usage'} | optional)
    if response['model'] != request['model_reference']:
        raise ValueError('semantic response model substitution refused')
    exact_fields(response['usage'], {'input_tokens', 'output_tokens'})
    usage = {key: count(value) for key, value in response['usage'].items()}
    cached_count = count(response['prompt_eval_cached_count']) if optional else None
    questions, raw_answers = request['catalog']['questions'], response['answers']
    if not isinstance(raw_answers, dict) or set(raw_answers)-set(questions):
        raise ValueError('unknown semantic question')
    answers = {}
    for name, question in questions.items():
        try:
            raw = raw_answers[name]
            if question['type'] == 'score':
                exact_fields(raw, {'type', 'score', 'legend', 'probabilities', 'confidence'})
                if raw['legend'] != {str(i): value for i, value in enumerate(question['criteria'])}:
                    raise ValueError('Score legend differs from requested rubric')
                raw = {key: value for key, value in raw.items() if key != 'legend'}
            answers[name] = normalize_answer(question, raw)
        except (ValueError, KeyError, TypeError):
            answers[name] = {'status': 'error', 'type': question['type'], 'error': 'invalid_or_missing_answer'}
    state = request['wire_request']['state']
    return {'schema_version': 'local-semantic-source-result-v2' if source_request else 'local-semantic-result-v1',
        'origin': 'ollama_local_systemone',
        'request_sha256': request['request_sha256'], 'source_request_sha256': transport['request_sha256'],
        'inference_identity_sha256': transport['inference_identity_sha256'],
        **({'source_packet_sha256': request['packet']['packet_sha256']} if source_request
           else {'record_sha256': digest(request['record'])}),
        'model_digest': request['model_digest'], 'model_reference': request['model_reference'],
        'model_identity_assurance': 'trusted_server_digest_reference_not_runtime_attestation',
        'state_sha256': digest(state), 'question_catalog_sha256': digest(request['catalog']),
        'question_snapshot': deepcopy(request['catalog']), 'answers': answers,
        'provider_reported_usage': usage, 'provider_reported_cached_input_tokens': cached_count,
        'metadata': deepcopy(metadata), 'response_sha256': digest(response), 'evaluated_at': metadata['checked_at'],
        'calibrated_policy': False, 'transport_round_trip_observed': True, 'api_calls': 1,
        'metadata_http_requests': 3, 'cached_usage_accounting_verified': False,
        'hard_input_token_limit_verified': False, 'live_model_quality_evaluated': False,
        'independent_trading_evidence': False}
