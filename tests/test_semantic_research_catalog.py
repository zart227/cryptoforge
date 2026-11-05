import copy
import json
from pathlib import Path
import sqlite3

import pytest

from test_llm_training_experiments import setup
from cryptoforge.semantic_research_catalog import SemanticResearchCatalog, record_from_receipt
from cryptoforge.typesafe_judgment_contracts import evaluate_mock, validate_catalog
from cryptoforge.training_experiment_planner import read_json


@pytest.fixture
def catalog():
    return read_json(Path(__file__).parents[1]/'config/semantic-research-questions-v1.json')


def response():
    return {'answers': {
        'mechanism': {'type': 'choice', 'choice': 'threshold', 'confidence': 0.9,
                      'probabilities': {'regularization':0.02,'threshold':0.9,'features':0.02,'data':0.02,'unknown':0.04}},
        'conclusion_supported': {'type':'noul','noul':0.9},
        'context_sufficient': {'type':'noul','noul':0.5}}}


@pytest.fixture
def receipt(tmp_path):
    _, _, _, _, result, _ = setup(tmp_path)
    return {'status':'completed','command':'run','result':result}


def test_typed_mock_has_explicit_uncertainty_and_no_noul_confidence(catalog):
    result=evaluate_mock({'experiment':{}},catalog,response())
    assert result['origin']=='mock' and result['api_calls']==0
    assert not result['calibrated_policy']
    assert result['answers']['mechanism']['status']=='available'
    assert result['answers']['context_sufficient']['status']=='abstain'
    assert result['answers']['context_sufficient']['decision'] is None
    assert 'confidence' not in result['answers']['conclusion_supported']


@pytest.mark.parametrize('change', ['missing','nan','wrong_type','noul_confidence','probabilities'])
def test_invalid_answers_are_errors_not_false_labels(catalog,change):
    raw=response()
    if change=='missing': del raw['answers']['conclusion_supported']
    elif change=='nan': raw['answers']['conclusion_supported']['noul']=float('inf')
    elif change=='wrong_type': raw['answers']['conclusion_supported']['type']='choice'
    elif change=='noul_confidence': raw['answers']['conclusion_supported']['confidence']=0.99
    else: raw['answers']['mechanism']['probabilities']['threshold']=0.1
    if change=='nan':
        with pytest.raises(ValueError): evaluate_mock({},catalog,raw)
    else:
        result=evaluate_mock({},catalog,raw)
        key='mechanism' if change=='probabilities' else 'conclusion_supported'
        assert result['answers'][key]['status']=='error'
        assert 'decision' not in result['answers'][key]


def test_choice_unknown_abstains_and_score_checks_expectation(catalog):
    raw=response()
    raw['answers']['mechanism'].update(choice='unknown',probabilities={
        'regularization':0,'threshold':0,'features':0,'data':0,'unknown':1})
    assert evaluate_mock({},catalog,raw)['answers']['mechanism']['status']=='abstain'
    catalog['questions']={'clarity': {'type':'score','instructions':'How complete is the description?',
        'criteria':['Incomplete','Complete'],'minimum_confidence':0.8}}
    result=evaluate_mock({},catalog,{'answers':{'clarity':{'type':'score','score':0.8,
        'confidence':0.9,'probabilities':{'0':0.2,'1':0.8}}}})
    assert result['answers']['clarity']['value']==0.8


def test_unknown_questions_and_missing_unknown_option_fail(catalog):
    raw=response();raw['answers']['unexpected']={}
    with pytest.raises(ValueError): evaluate_mock({},catalog,raw)
    del catalog['questions']['mechanism']['criteria']['unknown']
    with pytest.raises(ValueError): validate_catalog(catalog)


def test_numerical_record_immutable_and_annotation_cache_invalidates(tmp_path,receipt,catalog):
    store=SemanticResearchCatalog(tmp_path/'semantic.sqlite')
    record=store.register(receipt,hypothesis='Change decision threshold.',conclusion='No independent efficacy established.')
    first=store.annotate_mock(record['experiment_id'],catalog,response())
    assert not first['cached']
    assert store.annotate_mock(record['experiment_id'],catalog,response())['cached']
    snapshot=copy.deepcopy(first['question_snapshot'])
    catalog['questions']['mechanism']['instructions']+=' Only use supplied facts.'
    assert first['question_snapshot']==snapshot
    assert not store.annotate_mock(record['experiment_id'],catalog,response())['cached']
    with pytest.raises(ValueError,match='immutable'):
        store.register(receipt,hypothesis='Rewrite previous hypothesis.',conclusion='Different claim.')
    with sqlite3.connect(store.path) as db:
        saved=json.loads(db.execute('SELECT payload FROM semantic_records').fetchone()[0])
    assert saved==record and saved['metrics']==receipt['result']['reports']['validation']['diagnostics']['evidence']['overall']
    assert store.path.stat().st_mode & 0o777==0o600


def test_record_tampering_detected_before_annotation(tmp_path,receipt,catalog):
    store=SemanticResearchCatalog(tmp_path/'semantic.sqlite')
    record=store.register(receipt,hypothesis='Baseline.',conclusion='Development evidence only.')
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE semantic_records SET payload='{}'")
    with pytest.raises(ValueError,match='checksum mismatch'):
        store.annotate_mock(record['experiment_id'],catalog,response())


def test_bad_experiment_and_existing_fit_database_refused(tmp_path,receipt):
    broken=copy.deepcopy(receipt)
    broken['result']['artifact']['bias']=123
    with pytest.raises(ValueError,match='artifact'):
        record_from_receipt(broken,hypothesis='Baseline.',conclusion='Unknown.')
    with pytest.raises(ValueError,match='separate database'):
        SemanticResearchCatalog(tmp_path/'attempts.sqlite').register(receipt,hypothesis='Baseline.',conclusion='Unknown.')
