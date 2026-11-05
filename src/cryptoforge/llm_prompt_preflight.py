"""Exact outbound byte admission, explicitly distinct from unknown native tokens.

No tokenizer estimate or caller-supplied count can authorize a verified token
bound. Current native provider contracts do not establish such a bound.
"""
import hashlib
from pathlib import Path

from cryptoforge.llm_research_contracts import CATALOG, PROPOSAL_VERSION
from cryptoforge.research_training_diagnostics import canonical, digest, validate_diagnostics

MAX_MESSAGE_BYTES = 24000
MAX_REQUEST_BYTES = 32000
UNVERIFIED_LIMIT = 'verified_input_token_limit_unavailable'
_LOADED_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def prepare_prompt(report, parameters, *, system, prompt_version):
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _LOADED_SHA:
        raise ValueError('prompt preflight source changed; restart required')
    validate_diagnostics(report)
    if (not isinstance(parameters, tuple) or not parameters or any(not isinstance(name, str) or name not in CATALOG for name in parameters)
            or len(parameters) != len(set(parameters))):
        raise ValueError('fixed catalog parameters required')
    user = canonical({'diagnostics': report, 'catalog': {p: CATALOG[p] for p in parameters}, 'schema_version': PROPOSAL_VERSION})
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
    size = len(canonical(messages).encode('utf-8'))
    if size > MAX_MESSAGE_BYTES:
        raise ValueError('serialized prompt byte limit exceeded; no truncation allowed')
    return messages, {'schema_version': 'advisor-input-preflight-v1', 'report_sha256': digest(report),
        'messages_sha256': digest(messages), 'system_sha256': digest(system), 'prompt_version': prompt_version,
        'message_bytes': size, 'maximum_message_bytes': MAX_MESSAGE_BYTES,
        'input_tokens_upper_bound': None, 'hard_input_token_limit_verified': False,
        'byte_limit_is_token_limit': False,
        'implementation_sha256': _LOADED_SHA}


def provider_payload(messages, provider, model):
    if not isinstance(model, str) or not 1 <= len(model) <= 200:
        raise ValueError('bounded model identity required')
    if provider == 'openrouter':
        payload = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': 2048, 'stream': False,
                   'provider': {'max_price': {'prompt': 0, 'completion': 0}}}
    elif provider == 'ollama':
        payload = {'model': model, 'messages': messages, 'stream': False, 'format': 'json',
                   'options': {'temperature': 0, 'num_predict': 2048}}
    else:
        raise ValueError('supported provider required')
    size = len(canonical(payload).encode('utf-8'))
    if size > MAX_REQUEST_BYTES:
        raise ValueError('serialized provider payload byte limit exceeded')
    return payload, size


def require_verified_limit(required):
    if type(required) is not bool:
        raise ValueError('boolean input-limit requirement required')
    if required:
        raise ValueError(UNVERIFIED_LIMIT)


def main(argv=None):
    import argparse
    import os
    from cryptoforge.llm_research_advisor import FreeAdvisor, DEFAULT_MODEL
    from cryptoforge.training_experiment_planner import read_json
    parser = argparse.ArgumentParser(description='Offline prompt admission audit; no credentials or provider requests.')
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--provider', choices=('openrouter', 'ollama'), required=True)
    parser.add_argument('--model')
    parser.add_argument('--require-verified-input-limit', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        receipt = {'schema_version': 'advisor-input-audit-receipt-v1', 'status': 'started', 'api_calls': 0,
                   'credentials_read': False, 'journal_mutations': 0}
        stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            model = args.model or (DEFAULT_MODEL if args.provider == 'openrouter' else 'nemotron-3-nano:30b')
            prepared = FreeAdvisor(provider=args.provider, model=model, parameters=('l2', 'threshold')).preflight(read_json(args.diagnostics))
            receipt['input_preflight'] = prepared['audit']
            require_verified_limit(args.require_verified_input_limit)
            receipt['status'] = 'completed'; code = 0
        except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
            receipt.update(status='rejected', error=UNVERIFIED_LIMIT if str(error) == UNVERIFIED_LIMIT else 'prompt_input_rejected')
            code = 1
        stream.seek(0); stream.truncate(); stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
    print('Offline input audit saved; no provider call or model change')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
