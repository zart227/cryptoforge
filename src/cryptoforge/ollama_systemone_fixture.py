"""Offline Ollama System One wire fixtures; no live inference entry point."""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path

from cryptoforge import llm_research_contracts, ollama_decision_readiness, training_diagnostics, typesafe_judgment_contracts
from cryptoforge.ollama_decision_readiness import local_model, model_digest, server_version
from cryptoforge.semantic_annotation_benchmark import write_new
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields
from cryptoforge.training_experiment_planner import read_json
from cryptoforge.typesafe_judgment_contracts import evaluate_mock, normalize_answer, validate_catalog


MAX_WIRE_BYTES = 48_000


def implementation_sources():
    return {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in {
        'bridge': __file__, 'metadata': ollama_decision_readiness.__file__,
        'normalizer': typesafe_judgment_contracts.__file__,
        'canonical': training_diagnostics.__file__, 'json_boundary': llm_research_contracts.__file__}.items()}


def prepare_request(state, catalog, *, model, digest_pin, version):
    validate_catalog(catalog)
    if not isinstance(state, dict) or not state or len(canonical(state).encode()) > 32_000:
        raise ValueError('nonempty bounded approved research state object required')
    pin = {'model': local_model(model), 'model_digest': model_digest(digest_pin),
           'server_version': server_version(version)}
    questions = {name: {key: deepcopy(q[key]) for key in ('type', 'instructions', 'criteria')}
                 for name, q in catalog['questions'].items()}
    wire = {'model': pin['model'], 'state': deepcopy(state), 'questions': questions, 'keep_alive': 0}
    wire_bytes = len(canonical(wire).encode())
    if wire_bytes > MAX_WIRE_BYTES:
        raise ValueError('bounded System One wire payload required; no truncation')
    core = {'schema_version': 'ollama-systemone-fixture-request-v1', 'origin': 'offline_ollama_systemone_fixture',
        'state': deepcopy(state), 'catalog': deepcopy(catalog), 'declared_model_pin': pin,
        'wire_request': wire, 'wire_bytes': wire_bytes, 'max_wire_bytes': MAX_WIRE_BYTES,
        'implementation_sources': implementation_sources(), 'live_access_verified': False,
        'hard_input_token_limit_verified': False, 'byte_limit_is_token_limit': False}
    return {**core, 'request_sha256': digest(core)}


def token_count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise ValueError('bounded integer fixture token count required')
    return value


def evaluate_fixture(request, fixture):
    exact_fields(request, {'schema_version', 'origin', 'state', 'catalog', 'declared_model_pin',
        'wire_request', 'wire_bytes', 'max_wire_bytes', 'implementation_sources',
        'live_access_verified', 'hard_input_token_limit_verified', 'byte_limit_is_token_limit', 'request_sha256'})
    pin = request['declared_model_pin']
    exact_fields(pin, {'model', 'model_digest', 'server_version'})
    rebuilt = prepare_request(request['state'], request['catalog'], model=pin['model'],
        digest_pin=pin['model_digest'], version=pin['server_version'])
    if canonical(rebuilt) != canonical(request):
        raise ValueError('fixture request or implementation changed')
    if len(canonical(fixture).encode()) > 64_000:
        raise ValueError('System One fixture response too large')
    optional = {'prompt_eval_cached_count'} if isinstance(fixture, dict) and 'prompt_eval_cached_count' in fixture else set()
    exact_fields(fixture, {'model', 'answers', 'usage'} | optional)
    if fixture['model'] != pin['model']:
        raise ValueError('fixture model differs from declared pin')
    exact_fields(fixture['usage'], {'input_tokens', 'output_tokens'})
    usage = {key: token_count(value) for key, value in fixture['usage'].items()}
    cached = token_count(fixture['prompt_eval_cached_count']) if optional else None
    questions, answers = request['catalog']['questions'], fixture['answers']
    if not isinstance(answers, dict) or set(answers) - set(questions):
        raise ValueError('unknown fixture question')
    mapped, errors = {}, {}
    for name, question in questions.items():
        try:
            raw = answers[name]
            if question['type'] == 'score':
                exact_fields(raw, {'type', 'score', 'probabilities', 'confidence', 'legend'})
                if raw['legend'] != {str(i): text for i, text in enumerate(question['criteria'])}:
                    raise ValueError('Score legend differs from requested rubric')
                raw = {key: value for key, value in raw.items() if key != 'legend'}
            normalize_answer(question, raw)
            mapped[name] = deepcopy(raw)
        except (ValueError, KeyError, TypeError):
            errors[name] = 'invalid_or_missing_ollama_fixture_answer'
    return {'schema_version': 'ollama-systemone-fixture-result-v1', 'origin': 'offline_ollama_systemone_fixture',
        'request_sha256': request['request_sha256'], 'source_fixture_sha256': digest(fixture),
        'declared_model_pin': deepcopy(pin), 'model_identity_assurance': 'fixture_declaration_only',
        'compatible_answer_count': len(mapped), 'mapping_errors': errors,
        'fixture_reported_usage': usage, 'fixture_reported_cached_input_tokens': cached,
        'usage_is_external_observation': False, 'cached_usage_accounting_verified': False, 'api_calls': 0,
        'normalized_judgments': evaluate_mock(request['state'], request['catalog'], {'answers': mapped}),
        'live_access_verified': False, 'live_model_quality_evaluated': False,
        'independent_trading_evidence': False, 'hard_input_token_limit_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--state', type=Path, required=True)
    prepare.add_argument('--questions', type=Path, required=True)
    prepare.add_argument('--model', required=True)
    prepare.add_argument('--model-digest', required=True)
    prepare.add_argument('--server-version', required=True)
    fixture = sub.add_parser('fixture')
    fixture.add_argument('--request', type=Path, required=True)
    fixture.add_argument('--response', type=Path, required=True)
    for command in (prepare, fixture):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        result = prepare_request(read_json(args.state, 32_000), read_json(args.questions, 64_000),
            model=args.model, digest_pin=args.model_digest, version=args.server_version)
    else:
        result = evaluate_fixture(read_json(args.request), read_json(args.response, 64_000))
    write_new(args.output, result)
    print('Offline Ollama wire fixture saved; zero API calls, no live provenance')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
