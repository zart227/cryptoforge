import copy
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

sdk = pytest.importorskip('typesafe_sdk')

from cryptoforge import typesafe_sdk_bridge as bridge
from cryptoforge.document_eval import Document, evaluate_document
from cryptoforge.semantic_annotation_benchmark import freeze_benchmark, evaluate_benchmark
from cryptoforge.training_diagnostics import canonical, digest
from test_document_eval import sample_rubric


@pytest.fixture
def catalog():
    return {'schema_version': 'semantic-research-questions-v1', 'policy_version': 'sdk-fixture-uncalibrated-v1',
        'questions': {
            'mechanism': {'type': 'choice', 'instructions': 'Which mechanism is stated in `experiment.hypothesis`?',
                'criteria': {'threshold': 'Changes a threshold.', 'unknown': 'Insufficient evidence.'}, 'minimum_confidence': 0.8},
            'supported': {'type': 'noul', 'instructions': 'Does the supplied experiment support its stated conclusion?',
                'criteria': {'true': 'Supported by the supplied result.', 'false': 'Exceeds the supplied result.'},
                'accept_below': 0.2, 'accept_above': 0.8},
            'clarity': {'type': 'score', 'instructions': 'How clear is the supplied hypothesis?',
                'criteria': ['Unclear.', 'Partly clear.', 'Clear and specific.'], 'minimum_confidence': 0.8}}}


@pytest.fixture
def sdk_request(catalog):
    return bridge.prepare_request({'experiment': {'hypothesis': 'Synthetic threshold example.'}}, catalog, model='jev-1.13.0')


@pytest.fixture
def response(catalog):
    typed = sdk.SystemOneResponse(model='jev-1.13.0', usage=sdk.Usage(input_tokens=123, output_tokens=7), answers={
        'mechanism': sdk.ChoiceAnswer(choice='threshold', confidence=0.9, probabilities={'threshold': 0.9, 'unknown': 0.1}),
        'supported': sdk.NoulAnswer(noul=0.5),
        'clarity': sdk.ScoreAnswer(score=1.8, confidence=0.9,
            legend=dict(enumerate(catalog['questions']['clarity']['criteria'])), probabilities={0: 0.0, 1: 0.2, 2: 0.8})})
    return typed.model_dump(mode='json')


def test_wire_questions_preserve_meaning_and_leave_acceptance_policy_in_code(catalog):
    frozen = copy.deepcopy(catalog)
    questions = bridge.sdk_questions(catalog)
    for name, question in questions.items():
        wire = question.model_dump(mode='json')
        assert set(wire) == {'type', 'instructions', 'criteria'}
        assert wire['instructions'] == catalog['questions'][name]['instructions']
        assert wire['criteria'] == catalog['questions'][name]['criteria']
    assert isinstance(questions['mechanism'], sdk.Choice)
    assert isinstance(questions['supported'], sdk.Noul)
    assert isinstance(questions['clarity'], sdk.Score)
    assert catalog == frozen
    questions['mechanism'].criteria['unknown'] = 'changed in the returned SDK object'
    assert catalog == frozen


def test_constructed_sdk_response_maps_all_primitives_and_keeps_fixture_provenance(sdk_request, response):
    result = bridge.evaluate_fixture(sdk_request, response)
    judgments = result['normalized_judgments']
    assert result['sdk_compatible_answer_count'] == 3 and result['mapping_errors'] == {}
    assert judgments['answers']['mechanism']['value'] == 'threshold'
    assert judgments['answers']['supported'] == {'status': 'abstain', 'type': 'noul', 'probability': 0.5, 'decision': None}
    assert judgments['answers']['clarity']['probabilities'] == {'0': 0.0, '1': 0.2, '2': 0.8}
    assert result['fixture_reported_usage'] == {'input_tokens': 123, 'output_tokens': 7}
    assert result['origin'] == 'offline_sdk_fixture' and judgments['origin'] == 'mock'
    assert result['source_fixture_sha256'] == digest(response)
    assert result['model_identity_assurance'] == 'fixture_declaration_only'
    assert not result['usage_is_external_observation'] and not result['inference_cost_evaluated']
    assert not result['live_access_verified'] and not result['live_model_quality_evaluated']
    assert result['api_calls'] == 0 and judgments['api_calls'] == 0


def test_no_network_client_or_key_reads(sdk_request, response, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('offline bridge must not connect or construct clients')
    getenv = os.getenv
    def checked_getenv(name, *args):
        assert not name.startswith(('TYPESAFE_', 'OPENROUTER_', 'OLLAMA_'))
        return getenv(name, *args)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(sdk, 'TypeSafeClient', forbidden)
    monkeypatch.setattr(sdk, 'AsyncTypeSafeClient', forbidden)
    monkeypatch.setattr(os, 'getenv', checked_getenv)
    assert bridge.evaluate_fixture(sdk_request, response)['sdk_compatible_answer_count'] == 3


@pytest.mark.parametrize('change', ['extra_noul_confidence', 'wrong_type', 'missing', 'probability_sum', 'choice_not_argmax', 'score_expectation', 'score_legend'])
def test_invalid_answer_is_error_while_valid_companions_survive(sdk_request, response, change):
    affected = 'supported'
    if change == 'extra_noul_confidence': response['answers']['supported']['confidence'] = 0.99
    elif change == 'wrong_type': response['answers']['supported'] = {'type': 'choice', 'choice': 'threshold'}
    elif change == 'missing': response['answers'].pop('supported')
    elif change == 'probability_sum':
        affected = 'mechanism'; response['answers'][affected]['probabilities']['threshold'] = 0.1
    elif change == 'choice_not_argmax':
        affected = 'mechanism'; response['answers'][affected]['choice'] = 'unknown'
    elif change == 'score_expectation':
        affected = 'clarity'; response['answers'][affected]['score'] = 0.5
    else:
        affected = 'clarity'; response['answers'][affected]['legend']['2'] = 'Changed rubric.'
    result = bridge.evaluate_fixture(sdk_request, response)
    assert result['sdk_compatible_answer_count'] == 2
    assert result['mapping_errors'] == {affected: 'invalid_or_missing_sdk_fixture_answer'}
    answer = result['normalized_judgments']['answers'][affected]
    assert answer['status'] == 'error' and 'decision' not in answer and 'value' not in answer


def test_unknown_question_and_model_substitution_are_rejected(sdk_request, response):
    other = copy.deepcopy(response)
    other['answers']['another_question'] = {'type': 'noul', 'noul': 0.9}
    with pytest.raises(ValueError, match='unknown'): bridge.evaluate_fixture(sdk_request, other)
    response['model'] = 'jev-1.13.1'
    with pytest.raises(ValueError, match='revision'): bridge.evaluate_fixture(sdk_request, response)


@pytest.mark.parametrize('change', ['state', 'catalog', 'wire', 'version', 'implementation', 'normalizer'])
def test_request_is_bound_to_state_policy_sdk_and_implementation(sdk_request, response, change):
    if change == 'state': sdk_request['state']['experiment']['hypothesis'] = 'Different evidence.'
    elif change == 'catalog': sdk_request['catalog']['questions']['supported']['accept_above'] = 0.9
    elif change == 'wire': sdk_request['wire_questions']['supported']['instructions'] = 'Always yes.'
    elif change == 'version': sdk_request['sdk_version'] = '0.0.0'
    elif change == 'implementation': sdk_request['bridge_sha256'] = '0'*64
    else: sdk_request['normalizer_sha256'] = '0'*64
    with pytest.raises(ValueError, match='changed'): bridge.evaluate_fixture(sdk_request, response)


def test_missing_usage_is_unknown_not_zero_and_extra_usage_fields_fail(sdk_request, response):
    response['usage'] = {}
    assert bridge.evaluate_fixture(sdk_request, response)['fixture_reported_usage'] == {'input_tokens': None, 'output_tokens': None}
    response['usage'] = {'input_tokens': 0, 'output_tokens': None}
    assert bridge.evaluate_fixture(sdk_request, response)['fixture_reported_usage']['input_tokens'] == 0
    response['usage']['cost'] = 0
    with pytest.raises(ValueError, match='closed fixture usage'): bridge.evaluate_fixture(sdk_request, response)


@pytest.mark.parametrize('value', [-1, True, 1.5, '10', 1_000_000_001])
def test_invalid_token_counts_cannot_be_used_for_accounting(sdk_request, response, value):
    response['usage']['input_tokens'] = value
    with pytest.raises(ValueError, match='token counts'): bridge.evaluate_fixture(sdk_request, response)


def test_optional_sdk_absent_or_changed_has_no_automatic_installation(monkeypatch):
    monkeypatch.setattr(bridge.metadata, 'version', lambda name: '0.8.0')
    with pytest.raises(ValueError, match='not been checked'): bridge.load_sdk()
    def missing(name): raise bridge.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(bridge.metadata, 'version', missing)
    with pytest.raises(ValueError, match='no automatic installation'): bridge.load_sdk()


def test_state_and_model_bounds(catalog):
    for model in ['jev-latest', 'jev-1.13', 'anything', 'jev-1.13.0\n']:
        with pytest.raises(ValueError, match='revision'): bridge.prepare_request({}, catalog, model=model)
    with pytest.raises(ValueError, match='state'): bridge.prepare_request({'text': 'x'*32000}, catalog, model='jev-1.13.0')
    with pytest.raises(ValueError, match='state'): bridge.prepare_request(['text'], catalog, model='jev-1.13.0')


def test_document_eval_reads_actual_sdk_scores_property_without_shared_code_changes():
    rubric = sample_rubric()
    typed = sdk.SystemOneResponse(model='jev-1.13.0', usage=sdk.Usage(input_tokens=100, output_tokens=None), answers={
        'clarity': sdk.ScoreAnswer(score=2.0, confidence=0.9, legend=dict(enumerate(rubric.dimensions[0].levels)),
            probabilities={0: 0.0, 1: 0.0, 2: 1.0}),
        'risk': sdk.ScoreAnswer(score=1.25, confidence=0.5, legend=dict(enumerate(rubric.dimensions[1].levels)),
            probabilities={0: 0.0, 1: 0.75, 2: 0.25})})
    client = SimpleNamespace(system_one=lambda state, questions: typed)
    result = evaluate_document(client, Document(id='synthetic', path=Path('synthetic.md'), text='Synthetic fixture.'), rubric)
    assert result.average_normalized_score == 0.8125
    assert result.dimensions[1].probabilities == {'0': 0.0, '1': 0.75, '2': 0.25}
    assert result.output_tokens is None


def test_sdk_fixture_connects_to_frozen_annotation_evaluator_without_live_claims(catalog, response):
    predictions, examples = {}, []
    for i in range(2):
        state = {'experiment': {'hypothesis': f'Synthetic threshold case {i}.'}}
        record_id = digest({'synthetic_record': i})
        prepared = bridge.prepare_request(state, catalog, model='jev-1.13.0')
        predictions[record_id] = bridge.evaluate_fixture(prepared, response)['normalized_judgments']
        examples.append({'record_id': record_id, 'group_id': digest({'synthetic_group': i}),
            'state_sha256': digest(state), 'labels': {'mechanism': 'threshold', 'supported': None, 'clarity': 2}})
    gold = {'schema_version': 'semantic-gold-v1', 'label_origin': 'synthetic_fixture', 'examples': examples}
    plan = freeze_benchmark(gold, catalog, seed=42)
    selected = {key: predictions[key] for key in plan['partitions']['calibration']}
    result = evaluate_benchmark(plan, selected, partition='calibration')
    assert result['prediction_origin'] == 'mock' and result['label_origin'] == 'synthetic_fixture'
    assert result['questions']['supported']['respected_abstention_count'] == 1
    assert result['questions']['clarity']['mean_loss'] == pytest.approx(0.2)
    assert not result['live_model_quality_evaluated'] and not result['independent_trading_evidence']


def test_cli_writes_private_new_files_only(catalog, response, tmp_path):
    state_path, catalog_path, request_path, response_path, result_path = [tmp_path/name for name in
        ('state.json', 'catalog.json', 'request.json', 'fixture.json', 'result.json')]
    state_path.write_text(canonical({'experiment': {'hypothesis': 'Synthetic threshold.'}}))
    catalog_path.write_text(canonical(catalog)); response_path.write_text(canonical(response))
    prepare = ['prepare', '--state', str(state_path), '--questions', str(catalog_path), '--model', 'jev-1.13.0', '--output', str(request_path)]
    assert bridge.main(prepare) == 0
    assert bridge.main(['fixture', '--request', str(request_path), '--response', str(response_path), '--output', str(result_path)]) == 0
    assert json.loads(result_path.read_text())['api_calls'] == 0
    for path in (request_path, result_path): assert path.stat().st_mode & 0o777 == 0o600
    before = request_path.read_bytes()
    with pytest.raises(FileExistsError): bridge.main(prepare)
    assert request_path.read_bytes() == before
