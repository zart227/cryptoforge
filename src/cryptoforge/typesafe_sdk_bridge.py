"""Offline SDK compatibility bridge for research fixtures, never a live client.

No credentials, endpoint discovery, client construction or inference. SDK-shaped
fixtures remain mock predictions and cannot establish provider provenance.
"""
import argparse
from copy import deepcopy
import hashlib
from importlib import metadata
import inspect
from pathlib import Path
import re

from cryptoforge import typesafe_judgment_contracts
from cryptoforge.semantic_annotation_benchmark import write_new
from cryptoforge.training_diagnostics import canonical, digest, exact_fields
from cryptoforge.training_experiment_planner import read_json
from cryptoforge.typesafe_judgment_contracts import evaluate_mock, normalize_answer, validate_catalog


TESTED_SDK_VERSION = '0.7.1'


def load_sdk():
    try:
        version = metadata.version('typesafe-sdk')
    except metadata.PackageNotFoundError:
        raise ValueError('optional typesafe-sdk is unavailable; no automatic installation') from None
    if version != TESTED_SDK_VERSION:
        raise ValueError('SDK version has not been checked by this offline bridge')
    import typesafe_sdk
    return typesafe_sdk


def sdk_questions(catalog):
    validate_catalog(catalog)
    sdk = load_sdk()
    classes = {'choice': sdk.Choice, 'noul': sdk.Noul, 'score': sdk.Score}
    return {name: classes[q['type']](instructions=q['instructions'], criteria=deepcopy(q['criteria']))
            for name, q in catalog['questions'].items()}


def prepare_request(state, catalog, *, model):
    validate_catalog(catalog)
    if not isinstance(state, dict) or len(canonical(state).encode()) > 32000:
        raise ValueError('bounded approved research state object required')
    if not isinstance(model, str) or not re.fullmatch(r'jev-[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', model):
        raise ValueError('explicit Jev revision required for a fixture; no latest alias')
    questions = sdk_questions(catalog)
    sdk = load_sdk()
    core = {'schema_version': 'semantic-sdk-fixture-request-v1', 'origin': 'offline_sdk_fixture',
        'state': deepcopy(state), 'catalog': deepcopy(catalog), 'requested_model': model,
        'wire_questions': {name: q.model_dump(mode='json') for name, q in questions.items()},
        'sdk_version': TESTED_SDK_VERSION,
        'sdk_sources': {name: hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest()
                        for name, cls in (('questions', sdk.Choice), ('responses', sdk.SystemOneResponse))},
        'bridge_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'normalizer_sha256': hashlib.sha256(Path(typesafe_judgment_contracts.__file__).read_bytes()).hexdigest(),
        'live_access_verified': False}
    return {**core, 'request_sha256': digest(core)}


def usage_from_fixture(raw):
    if not isinstance(raw, dict) or set(raw)-{'input_tokens', 'output_tokens'}:
        raise ValueError('closed fixture usage object required')
    usage = {key: raw.get(key) for key in ('input_tokens', 'output_tokens')}
    for value in usage.values():
        if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000_000):
            raise ValueError('nonnegative fixture token counts or null required')
    return usage


def parse_answer(question, raw, sdk):
    """Validate the raw boundary before the SDK can ignore unknown fields."""
    kind = question['type']
    fields = {'type', 'noul'} if kind == 'noul' else {'type', kind, 'confidence', 'probabilities'}
    exact_fields(raw, fields | ({'legend'} if kind == 'score' else set()))
    if kind == 'score':
        expected_legend = {str(i): value for i, value in enumerate(question['criteria'])}
        if raw['legend'] != expected_legend:
            raise ValueError('fixture Score legend differs from requested criteria')
    normalized_raw = {key: value for key, value in raw.items() if key != 'legend'}
    normalize_answer(question, normalized_raw)
    cls = {'noul': sdk.NoulAnswer, 'choice': sdk.ChoiceAnswer, 'score': sdk.ScoreAnswer}[kind]
    # The SDK decodes JSON Score keys to integer levels. model_validate on a
    # Python dict has different coercion rules, so exercise the JSON boundary.
    return cls.model_validate_json(canonical(raw))


def research_answer(answer):
    if answer.type == 'noul':
        return {'type': 'noul', 'noul': answer.noul}
    result = {'type': answer.type, answer.type: getattr(answer, answer.type),
              'confidence': answer.confidence, 'probabilities': dict(answer.probabilities)}
    if answer.type == 'score':
        result['probabilities'] = {str(key): value for key, value in answer.probabilities.items()}
    return result


def evaluate_fixture(request, fixture):
    exact_fields(request, {'schema_version', 'origin', 'state', 'catalog', 'requested_model',
        'wire_questions', 'sdk_version', 'sdk_sources', 'bridge_sha256', 'normalizer_sha256',
        'live_access_verified', 'request_sha256'})
    rebuilt = prepare_request(request['state'], request['catalog'], model=request['requested_model'])
    if canonical(rebuilt) != canonical(request):
        raise ValueError('fixture request, SDK or implementation changed')
    if len(canonical(fixture).encode()) > 64000:
        raise ValueError('SDK fixture response too large')
    exact_fields(fixture, {'model', 'usage', 'answers'})
    if fixture['model'] != request['requested_model']:
        raise ValueError('fixture model differs from requested revision')
    usage = usage_from_fixture(fixture['usage'])
    answers = fixture['answers']
    questions = request['catalog']['questions']
    if not isinstance(answers, dict) or set(answers)-set(questions):
        raise ValueError('unknown fixture question')
    sdk = load_sdk()
    parsed, errors = {}, {}
    for name, question in questions.items():
        try:
            parsed[name] = parse_answer(question, answers[name], sdk)
        except (ValueError, KeyError, TypeError):
            errors[name] = 'invalid_or_missing_sdk_fixture_answer'
    typed = sdk.SystemOneResponse(model=fixture['model'], usage=sdk.Usage(**usage), answers=parsed)
    mock = {'answers': {name: research_answer(answer) for name, answer in typed.answers.items()}}
    judgments = evaluate_mock(request['state'], request['catalog'], mock)
    return {'schema_version': 'semantic-sdk-fixture-result-v1', 'origin': 'offline_sdk_fixture',
        'request_sha256': request['request_sha256'], 'source_fixture_sha256': digest(fixture),
        'typed_response_sha256': digest(typed.model_dump(mode='json')),
        'reported_model': typed.model, 'model_identity_assurance': 'fixture_declaration_only',
        'sdk_version': TESTED_SDK_VERSION, 'sdk_compatible_answer_count': len(parsed), 'mapping_errors': errors,
        'fixture_reported_usage': {'input_tokens': typed.usage.input_tokens, 'output_tokens': typed.usage.output_tokens},
        'usage_is_external_observation': False, 'inference_cost_evaluated': False,
        'normalized_judgments': judgments, 'api_calls': 0, 'live_access_verified': False,
        'live_model_quality_evaluated': False, 'independent_trading_evidence': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--state', type=Path, required=True, help='explicitly approved research state only')
    prepare.add_argument('--questions', type=Path, required=True)
    prepare.add_argument('--model', required=True, help='fixture declaration, never model discovery')
    evaluate = sub.add_parser('fixture')
    evaluate.add_argument('--request', type=Path, required=True)
    evaluate.add_argument('--response', type=Path, required=True)
    for command in (prepare, evaluate):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        result = prepare_request(read_json(args.state, 32000), read_json(args.questions, 64000), model=args.model)
    else:
        result = evaluate_fixture(read_json(args.request), read_json(args.response, 64000))
    write_new(args.output, result)
    print('Offline SDK fixture artifact saved; zero API calls, no live provenance')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
