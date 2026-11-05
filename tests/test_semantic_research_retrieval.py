import copy
import json
import sqlite3

import pytest

from test_llm_training_experiments import setup
from cryptoforge.semantic_research_catalog import SemanticResearchCatalog
from cryptoforge.semantic_research_retrieval import main, prepare_request, rerank_mock
from cryptoforge.research_training_diagnostics import canonical, digest


@pytest.fixture(scope='module')
def receipt(tmp_path_factory):
    *_, result, _ = setup(tmp_path_factory.mktemp('retrieval-fit'))
    return {'status': 'completed', 'command': 'run', 'result': result}


@pytest.fixture
def catalog(tmp_path, receipt):
    store = SemanticResearchCatalog(tmp_path/'research catalog?#.sqlite')
    ids = []
    for hypothesis, conclusion in [
        ('Change threshold; inspect threshold selection.', 'No validation improvement from threshold.'),
        ('Change threshold with regularization.', 'Threshold leaves predictions unchanged.'),
        ('Проверить калибровку сигнала.', 'Калибровка требует отдельной оценки.')]:
        item = copy.deepcopy(receipt)
        item['result']['study_id'] = digest(hypothesis)
        ids.append(store.register(item, hypothesis=hypothesis, conclusion=conclusion)['experiment_id'])
    return store, ids


def response(request, values):
    return {'answers': {name: {'type': 'noul', 'noul': value}
                        for name, value in zip(request['question_catalog']['questions'], values)}}


def test_deterministic_lexical_shortlist_preserves_negative_evidence_and_unicode(catalog):
    store, ids = catalog
    before = store.path.read_bytes()
    request = prepare_request(store.path, 'THRESHOLD', limit=2)
    assert request == prepare_request(store.path, 'THRESHOLD', limit=2)
    assert {r['experiment']['experiment_id'] for r in request['state']['candidates']} == set(ids[:2])
    assert all(r['matched_terms'] == ['threshold'] and r['lexical_score'] > 0 for r in request['state']['candidates'])
    assert request['state']['candidates'][0]['experiment']['conclusion'].startswith('No validation')
    russian = prepare_request(store.path, 'КАЛИБРОВКА')
    assert [r['experiment']['experiment_id'] for r in russian['state']['candidates']] == [ids[2]]
    assert store.path.read_bytes() == before


def test_explicit_exclusion_prevents_self_retrieval(catalog):
    store, ids = catalog
    request = prepare_request(store.path, 'threshold', excluded_ids=[ids[0]])
    assert [r['experiment']['experiment_id'] for r in request['state']['candidates']] == [ids[1]]
    with pytest.raises(ValueError, match='not registered'):
        prepare_request(store.path, 'threshold', excluded_ids=['f'*64])


def test_mock_can_change_ranking_but_cannot_change_numerical_evidence(catalog):
    store, _ = catalog
    before = store.path.read_bytes()
    request = prepare_request(store.path, 'threshold')
    frozen = copy.deepcopy(request)
    result = rerank_mock(store.path, request, response(request, [0.81, 0.99]))
    assert result['selected_experiment_ids'] == [r['experiment']['experiment_id'] for r in reversed(request['state']['candidates'])]
    assert result['origin'] == 'mock' and result['api_calls'] == 0
    assert not result['calibrated_policy'] and not result['live_semantic_quality_evaluated']
    assert not result['point_in_time_qualified'] and not result['independent_trading_evidence']
    assert request == frozen and store.path.read_bytes() == before


def test_low_relevance_abstention_and_error_are_separate(catalog):
    store, _ = catalog
    request = prepare_request(store.path, 'threshold')
    raw = response(request, [0.1, 0.5])
    result = rerank_mock(store.path, request, raw)
    assert result['selected_experiment_ids'] == []
    assert result['candidates'][0]['judgment']['decision'] == 'no'
    assert result['candidates'][1]['judgment']['status'] == 'abstain'
    raw['answers'].pop('candidate_01')
    result = rerank_mock(store.path, request, raw)
    assert result['candidates'][1]['judgment']['status'] == 'error'
    assert 'decision' not in result['candidates'][1]['judgment']
    raw['answers']['candidate_00']['confidence'] = 0.99
    assert rerank_mock(store.path, request, raw)['candidates'][0]['judgment']['status'] == 'error'


def test_no_vocabulary_match_is_empty_not_arbitrary_fallback(catalog):
    store, _ = catalog
    request = prepare_request(store.path, 'unrelatedword')
    assert request['state']['candidates'] == [] and request['question_catalog'] is None
    result = rerank_mock(store.path, request, {'answers': {}})
    assert result['status'] == 'no_lexical_candidates' and result['judgments'] is None
    assert result['selected_experiment_ids'] == []
    with pytest.raises(ValueError, match='empty shortlist'):
        rerank_mock(store.path, request, {'answers': {'candidate_00': {'type': 'noul', 'noul': 0.9}}})


@pytest.mark.parametrize('change', ['metric', 'question', 'hash', 'snapshot'])
def test_request_and_question_tampering_rejected(catalog, change):
    store, _ = catalog
    request = prepare_request(store.path, 'threshold')
    raw = response(request, [0.9, 0.9])
    if change == 'metric': request['state']['candidates'][0]['experiment']['metrics']['brier_score'] = 0
    elif change == 'question': request['question_catalog']['questions']['candidate_00']['criteria']['true'] = 'Always select.'
    elif change == 'hash': request['retriever_sha256'] = '0'*64
    else: request['catalog_snapshot_sha256'] = '0'*64
    with pytest.raises(ValueError, match='changed'):
        rerank_mock(store.path, request, raw)


def test_catalog_addition_requires_new_frozen_request(catalog, receipt):
    store, _ = catalog
    request = prepare_request(store.path, 'threshold')
    item = copy.deepcopy(receipt); item['result']['study_id'] = digest('another')
    store.register(item, hypothesis='Another threshold.', conclusion='No effect measured.')
    with pytest.raises(ValueError, match='changed'):
        rerank_mock(store.path, request, response(request, [0.9, 0.9]))


@pytest.mark.parametrize('change', ['payload', 'rehashed_test', 'identity'])
def test_invalid_stored_evidence_rejected_even_with_recomputed_checksum(catalog, change):
    store, ids = catalog
    with sqlite3.connect(store.path) as db:
        record = json.loads(db.execute('SELECT payload FROM semantic_records WHERE id=?', (ids[0],)).fetchone()[0])
        if change == 'rehashed_test': record['partition'] = 'test'
        else: record['experiment_id'] = '0'*64
        checksum = '0'*64 if change == 'payload' else digest(record)
        db.execute('UPDATE semantic_records SET sha=?,payload=? WHERE id=?', (checksum, canonical(record), ids[0]))
    with pytest.raises(ValueError, match='development|checksum'):
        prepare_request(store.path, 'threshold')


def test_reader_does_not_create_missing_catalog_or_use_fit_database(tmp_path):
    missing = tmp_path/'missing'/'catalog.sqlite'
    with pytest.raises(ValueError, match='existing'):
        prepare_request(missing, 'threshold')
    assert not missing.parent.exists()
    other = tmp_path/'attempts.sqlite'
    with sqlite3.connect(other) as db: db.execute('CREATE TABLE attempts (id TEXT)')
    before = other.read_bytes()
    with pytest.raises(ValueError, match='separate'):
        prepare_request(other, 'threshold')
    assert other.read_bytes() == before


def test_catalog_and_state_size_limits_fail_without_silent_truncation(catalog):
    store, ids = catalog
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE semantic_records SET payload=? WHERE id=?', ('x'*64001, ids[0]))
    with pytest.raises(ValueError, match='bounded'):
        prepare_request(store.path, 'threshold')


def test_large_shortlist_requires_explicit_smaller_limit(catalog):
    store, ids = catalog
    with sqlite3.connect(store.path) as db:
        for record_id in ids:
            record = json.loads(db.execute('SELECT payload FROM semantic_records WHERE id=?', (record_id,)).fetchone()[0])
            record['hypothesis'] = 'threshold '+('я'*3900)
            db.execute('UPDATE semantic_records SET payload=?,sha=? WHERE id=?', (canonical(record), digest(record), record_id))
    with pytest.raises(ValueError, match='smaller shortlist'):
        prepare_request(store.path, 'threshold', limit=3)
    assert len(prepare_request(store.path, 'threshold', limit=1)['state']['candidates']) == 1


def test_bounded_query_and_shortlist_inputs(catalog):
    store, _ = catalog
    for query, limit in [(' ', 8), ('---', 8), ('x'*4001, 8), ('threshold', True), ('threshold', 17)]:
        with pytest.raises(ValueError): prepare_request(store.path, query, limit=limit)


def test_cli_private_new_artifacts_and_no_overwrite(catalog, tmp_path):
    store, _ = catalog
    request_path, result_path, response_path = [tmp_path/n for n in ('request.json', 'result.json', 'mock.json')]
    args = ['prepare', '--database', str(store.path), '--query', 'threshold', '--output', str(request_path)]
    assert main(args) == 0
    request = json.loads(request_path.read_text())
    response_path.write_text(json.dumps(response(request, [0.9, 0.5])))
    assert main(['mock', '--database', str(store.path), '--request', str(request_path),
        '--mock-response', str(response_path), '--output', str(result_path)]) == 0
    for path in (request_path, result_path): assert path.stat().st_mode & 0o777 == 0o600
    before = request_path.read_bytes()
    with pytest.raises(FileExistsError): main(args)
    assert request_path.read_bytes() == before
