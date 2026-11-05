"""Exact synthetic equivalence and physical work reduction, no operational fits."""
from copy import deepcopy

import pytest
from test_llm_training_experiments import dataset
from cryptoforge import training_fit_reuse as m


EVIDENCE={'schema_version':'fit-reuse-evidence-context-v1','raw_source_manifest_sha256':'a'*64,
    'source_revision_manifest_sha256':'b'*64,'exposure_inventory_sha256':'c'*64,'execution_protocol_sha256':'d'*64}


def inputs(tmp_path,epochs=5):
    path,data=dataset(tmp_path);protocol=m.planner.freeze_protocol(path,version='synthetic-fit-reuse-v1',epochs=epochs)
    configs=[dict(m.planner.BASELINE)]
    for name in ('l2','threshold'):
        configs.extend({**m.planner.BASELINE,name:float(v)} for v in m.CATALOG[name] if v!=m.planner.BASELINE[name])
    return data,protocol,configs


def test_every_artifact_and_report_bitwise_matches_seven_independent_original_evaluations(tmp_path):
    data,protocol,configs=inputs(tmp_path);_,splits=m.planner.parse_development(data)
    originals=[m.planner.evaluate(splits,c,protocol) for c in configs]
    admitted=[]
    result=m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,
        admit=lambda e,context:admitted.append((e,context)))
    assert len(admitted)==7 and len({x[0]['logical_evaluation_key'] for x in admitted})==7
    for expected,actual in zip(originals,result['results'],strict=True):
        assert m.canonical(actual)==m.canonical({k:expected[k] for k in ('artifact','artifact_sha256','reports')})
    assert result['actual_counts']=={'logical_evaluations':7,'standardizer_fits':1,'long_head_fits':4,
        'probability_evaluations':160,'optimizer_training_row_presentations':400,'optimizer_feature_operations':2800,'diagnostic_reports':14}
    assert not result['logical_evaluation_charges_reduced'] and not result['production_compatible']
    pack={'schema_version':'synthetic-fit-reuse-equivalence-v1','only_synthetic_unit_data':True,
        'data':data,'protocol':protocol,'configurations':configs,'evidence_context':EVIDENCE,'optimized':result,
        'independent_original_core_results':[{k:r[k] for k in ('artifact','artifact_sha256','reports')} for r in originals],
        'logical_admissions':len(admitted),'operational_model_actions':0,'real_lineage_or_budget_approved':False}
    path=tmp_path/'exact-comparison.json';path.write_text(m.canonical(pack));path.chmod(0o600)


def test_no_fit_before_every_logical_admission_and_counts_match_actual_calls(tmp_path,monkeypatch):
    data,protocol,configs=inputs(tmp_path);events=[];actual={'fit_standardizer':0,'fit_logistic_head':0,'predict_probability':0}
    for name in actual:
        original=getattr(m.planner.model_training,name)
        def wrapped(*a,_name=name,_original=original,**k):
            assert events==list(range(7));actual[_name]+=1;return _original(*a,**k)
        monkeypatch.setattr(m.planner.model_training,name,wrapped)
    result=m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=lambda e,context:events.append(e['index']))
    assert actual=={'fit_standardizer':1,'fit_logistic_head':4,'predict_probability':160}
    assert result['actual_counts']['long_head_fits']==actual['fit_logistic_head']


def test_admission_refusal_leaves_prior_logical_charges_and_performs_no_model_work(tmp_path,monkeypatch):
    data,protocol,configs=inputs(tmp_path);charges=[]
    def refuse(e,context):
        if e['index']==3:raise ValueError('synthetic common budget exhausted')
        charges.append(e['logical_evaluation_key'])
    for name in ('fit_standardizer','fit_logistic_head','predict_probability'):
        monkeypatch.setattr(m.planner.model_training,name,lambda *a,**k:pytest.fail('no numeric action before admissions'))
    with pytest.raises(ValueError,match='budget exhausted'):
        m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=refuse)
    assert len(charges)==3


def test_fit_failure_does_not_refund_any_previously_admitted_logical_evaluation(tmp_path,monkeypatch):
    data,protocol,configs=inputs(tmp_path);charges=[]
    def fail(*a,**k):raise RuntimeError('synthetic optimizer failure')
    monkeypatch.setattr(m.planner.model_training,'fit_logistic_head',fail)
    with pytest.raises(RuntimeError):
        m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=lambda e,c:charges.append(e['logical_evaluation_key']))
    assert len(charges)==7


@pytest.mark.parametrize('field',['raw_source_manifest_sha256','source_revision_manifest_sha256','exposure_inventory_sha256','execution_protocol_sha256'])
def test_each_lineage_exposure_and_execution_identity_invalidates_all_reuse_keys(tmp_path,field):
    data,protocol,configs=inputs(tmp_path);original=m.plan(data,protocol,configs,evidence_context=EVIDENCE)
    changed={**EVIDENCE,field:'f'*64};current=m.plan(data,protocol,configs,evidence_context=changed)
    assert {e['fit_key'] for e in original['evaluations']}.isdisjoint({e['fit_key'] for e in current['evaluations']})
    assert not current['evidence_digests_verified_against_original_sources']


def test_threshold_artifacts_are_separate_and_mutation_cannot_change_shared_results(tmp_path):
    data,protocol,configs=inputs(tmp_path);configs=[c for c in configs if c['l2']==.01]
    result=m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=lambda *a:None)
    assert result['actual_counts']['long_head_fits']==1 and len(result['results'])==4
    assert len({r['artifact_sha256'] for r in result['results']})==4
    protected=m.canonical(result['results'][1]);result['results'][0]['artifact']['weights'][0]=999.
    assert m.canonical(result['results'][1])==protected
    assert len({r['reports']['validation']['diagnostics']['evidence']['overall']['brier_score'] for r in result['results']})==1


def test_no_persistent_cross_call_cache_and_no_implicit_admission(tmp_path,monkeypatch):
    data,protocol,configs=inputs(tmp_path);calls=[];original=m.planner.model_training.fit_logistic_head
    def fit(*a,**k):calls.append(1);return original(*a,**k)
    monkeypatch.setattr(m.planner.model_training,'fit_logistic_head',fit)
    for _ in (1,2):m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=lambda *a:None)
    assert len(calls)==8
    with pytest.raises(ValueError,match='admission_callback'):
        m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=None)


@pytest.mark.parametrize('configurations',[[],[{'l2':.01,'threshold':.6}]*2,[{'l2':.1,'threshold':.7}],
    [{'l2':.2,'threshold':.6}],[{'l2':True,'threshold':.6}],[{'l2':.01,'threshold':.6,'epochs':5}]])
def test_invalid_or_cross_parameter_search_never_reaches_admission(tmp_path,configurations):
    data,protocol,_=inputs(tmp_path)
    with pytest.raises(ValueError):m.evaluate_admitted_batch(data,protocol,configurations,evidence_context=EVIDENCE,
        admit=lambda *a:pytest.fail('validate all first'))


@pytest.mark.parametrize('change',['data','protocol','evidence','source'])
def test_modified_inputs_or_sources_are_refused_before_admission(tmp_path,monkeypatch,change):
    data,protocol,configs=inputs(tmp_path);evidence=deepcopy(EVIDENCE)
    if change=='data':data['validation'][0]['label']=1-data['validation'][0]['label']
    elif change=='protocol':protocol['epochs']=0
    elif change=='evidence':evidence['exposure_inventory_sha256']=True
    else:monkeypatch.setattr(m.graph,'source_profile',lambda:{})
    with pytest.raises(ValueError):m.evaluate_admitted_batch(data,protocol,configs,evidence_context=evidence,
        admit=lambda *a:pytest.fail('invalid inputs cannot be admitted'))


def test_readonly_plan_does_not_fit_predict_launch_or_write_journal(tmp_path,monkeypatch):
    data,protocol,configs=inputs(tmp_path)
    for name in ('fit_standardizer','fit_logistic_head','predict_probability'):
        monkeypatch.setattr(m.planner.model_training,name,lambda *a,**k:pytest.fail('plan only'))
    monkeypatch.setattr(m.planner,'ResearchAttempts',lambda *a,**k:pytest.fail('no journals'))
    monkeypatch.setattr(m.planner.subprocess,'Popen',lambda *a,**k:pytest.fail('no processes'))
    result=m.plan(data,protocol,configs,evidence_context=EVIDENCE)
    assert result['counts']['long_head_fits']==4 and not result['study_or_budget_approved']


def test_outer_bindings_keep_exact_source_context_even_when_legacy_artifact_is_identical(tmp_path):
    data,protocol,configs=inputs(tmp_path);configs=configs[:1]
    a=m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=lambda *a:None)
    b=m.evaluate_admitted_batch(data,protocol,configs,evidence_context={**EVIDENCE,'raw_source_manifest_sha256':'f'*64},admit=lambda *a:None)
    assert a['results'][0]['artifact_sha256']==b['results'][0]['artifact_sha256']
    assert a['result_bindings']!=b['result_bindings'] and a['batch_sha256']!=b['batch_sha256']
    assert a['batch_sha256']==m.digest({k:v for k,v in a.items() if k!='batch_sha256'})


def test_returned_plan_cannot_mutate_loaded_source_identity(tmp_path):
    data,protocol,configs=inputs(tmp_path);p=m.plan(data,protocol,configs,evidence_context=EVIDENCE)
    p['context']['implementation']['primitive']='f'*64
    assert m.plan(data,protocol,configs,evidence_context=EVIDENCE)['context']['implementation']==m.implementation()


def test_callback_cannot_silently_return_false_instead_of_refusing(tmp_path,monkeypatch):
    data,protocol,configs=inputs(tmp_path)
    monkeypatch.setattr(m.planner.model_training,'fit_standardizer',lambda *a,**k:pytest.fail('no fit'))
    with pytest.raises(ValueError,match='return_none_or_raise'):
        m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=lambda *a:False)


def test_mutable_caller_data_and_config_cannot_change_internal_inputs_during_admission(tmp_path):
    data,protocol,configs=inputs(tmp_path);original=m.plan(data,protocol,configs,evidence_context=EVIDENCE)
    def admit(e,context):
        data['train'][0]['features'][0]=999.;protocol['epochs']=100;configs[0]['l2']=1.
        e['configuration']['l2']=99.
    result=m.evaluate_admitted_batch(data,protocol,configs,evidence_context=EVIDENCE,admit=admit)
    assert result['plan']==original and result['actual_counts']['optimizer_training_row_presentations']==400
