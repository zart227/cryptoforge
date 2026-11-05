import copy
import json
from pathlib import Path

import pytest

from cryptoforge.semantic_review_package import make_package, blank_response, complete_review, main, validate_package
from cryptoforge.semantic_annotation_benchmark import freeze_benchmark
from cryptoforge.research_training_diagnostics import build_diagnostics, digest
from cryptoforge.training_experiment_planner import read_json


def catalog():
    return read_json(Path(__file__).parents[1]/'config/semantic-research-questions-v1.json')


def entry(index,dataset='a'*64):
    artifact={'production_compatible':False, 'config':{'l2':0.01,'threshold':0.6},'fixture':index}
    report=build_diagnostics({'partition':'validation','dataset_sha256':dataset,'source_sha256':'b'*64,
        'development_end':'2025-01-02T00:00:00Z','rows':[
        {'pair':'BTC/USDT','open_time':'2025-01-01T00:00:00Z','label_end_time':'2025-01-01T00:01:00Z','label':1,'probability':0.9},
        {'pair':'BTC/USDT','open_time':'2025-01-01T00:05:00Z','label_end_time':'2025-01-01T00:06:00Z','label':0,'probability':0.2}]}, threshold=0.6)
    return {'receipt':{'status':'completed','command':'run','result':{
        'artifact':artifact,'artifact_sha256':digest(artifact),'dataset_sha256':dataset,
        'study_id':digest({'fixture_study':index}),'reports':{'validation':{'diagnostics':report}}}},
        'hypothesis':'Synthetic threshold experiment.', 'conclusion':'Development observations only.'}


def filled(package):
    result=blank_response(package)
    result.update(reviewer_id='unit-fixture',review_kind='synthetic_fixture',reviewed_at='2026-10-16T12:00:00Z')
    for review in result['reviews']:
        for name,decision in review['decisions'].items():
            decision.update(status='answered',value='threshold' if name=='mechanism' else 'yes',reason='Synthetic test rationale.')
    return result


def test_blank_packet_preserves_states_and_does_not_supply_answers():
    entries=[entry(0),entry(1)]
    package=make_package(entries,catalog())
    template=blank_response(package)
    assert package['group_count']==1 and not package['minimum_group_count_met']
    assert not package['contains_model_answers']
    assert all(d['status']=='pending' and d['value'] is None for r in template['reviews'] for d in r['decisions'].values())
    assert template['reviewer_id'] is None and template['reviewed_at'] is None
    with pytest.raises(ValueError):complete_review(package,template)
    before=copy.deepcopy(entries)
    validate_package(package)
    assert entries==before


def test_explicit_insufficient_is_distinct_from_pending_and_not_false():
    package=make_package([entry(0),entry(1)],catalog())
    response=filled(package)
    response['reviews'][0]['decisions']['conclusion_supported'].update(status='insufficient',value=None)
    gold,audit=complete_review(package,response)
    assert gold['label_origin']=='synthetic_fixture'
    assert any(e['labels']['conclusion_supported'] is None for e in gold['examples'])
    assert not audit['independent_label_audit_performed']
    assert audit['attestation_assurance']=='reviewer_declaration_only'
    with pytest.raises(ValueError,match='two independent groups'):
        freeze_benchmark(gold,package['catalog'])


@pytest.mark.parametrize('mutation',['pending','missing','duplicate','wrong_state','package','bad_label','missing_reason','human'])
def test_unfinished_forged_or_inconsistent_review_refused(mutation):
    package=make_package([entry(0),entry(1)],catalog())
    response=filled(package)
    if mutation=='pending':response['reviews'][0]['decisions']['mechanism']['status']='pending'
    elif mutation=='missing':response['reviews'].pop()
    elif mutation=='duplicate':response['reviews'][1]=copy.deepcopy(response['reviews'][0])
    elif mutation=='wrong_state':response['reviews'][0]['state_sha256']='0'*64
    elif mutation=='package':response['package_sha256']='0'*64
    elif mutation=='bad_label':response['reviews'][0]['decisions']['mechanism']['value']='unlisted'
    elif mutation=='missing_reason':response['reviews'][0]['decisions']['mechanism']['reason']=None
    else:response['review_kind']='human_review'
    with pytest.raises(ValueError):complete_review(package,response)


def test_group_splitting_and_prediction_injection_into_packet_rejected():
    package=make_package([entry(0),entry(1)],catalog())
    package['records'][0]['group_id']='c'*64
    with pytest.raises(ValueError,match='separate groups'):validate_package(package)
    package=make_package([entry(0),entry(1)],catalog())
    package['records'][0]['model_prediction']='threshold'
    with pytest.raises(ValueError):validate_package(package)


def test_distinct_datasets_still_need_independent_group_audit():
    package=make_package([entry(0),entry(1,'c'*64)],catalog())
    assert package['minimum_group_count_met'] and package['group_count']==2
    assert not package['independent_groups_audited']
    gold,audit=complete_review(package,filled(package))
    assert not audit['independent_groups_audited']
    assert freeze_benchmark(gold,package['catalog'])['grouping_basis']=='caller_supplied_clusters_not_independently_audited'


def test_duplicate_receipts_rejected_before_review():
    with pytest.raises(ValueError,match='duplicate experiment'):make_package([entry(0),entry(0)],catalog())


def test_cli_prepare_and_complete_private_never_overwrite(tmp_path):
    entries=[entry(0),entry(1)]
    manifest=[]
    for i,e in enumerate(entries):
        p=tmp_path/f'receipt-{i}.json';p.write_text(json.dumps(e['receipt']))
        manifest.append({'receipt_path':p.name,'hypothesis':e['hypothesis'],'conclusion':e['conclusion']})
    (tmp_path/'sources.json').write_text(json.dumps(manifest))
    tasks=tmp_path/'tasks'
    args=['prepare','--manifest',str(tmp_path/'sources.json'),'--questions',str(Path(__file__).parents[1]/'config/semantic-research-questions-v1.json'),'--directory',str(tasks)]
    assert main(args)==0
    assert (tasks/'response-template.json').stat().st_mode & 0o777==0o600
    with pytest.raises(FileExistsError):main(args)
    package=read_json(tasks/'package.json')
    (tmp_path/'fixture-response.json').write_text(json.dumps(filled(package)))
    gold=tmp_path/'completed'
    assert main(['complete','--package',str(tasks/'package.json'),'--response',str(tmp_path/'fixture-response.json'),'--directory',str(gold)])==0
    assert read_json(gold/'gold.json')['label_origin']=='synthetic_fixture'
    assert (gold/'review-audit.json').stat().st_mode & 0o777==0o600


def test_oversized_manifest_refused_before_opening_receipts(tmp_path):
    manifest=tmp_path/'sources.json'
    manifest.write_text(json.dumps([{'receipt_path':'missing.json','hypothesis':'x','conclusion':'x'}]*1001))
    with pytest.raises(ValueError,match='manifest records'):
        main(['prepare','--manifest',str(manifest),'--questions','unused.json','--directory',str(tmp_path/'out')])
    assert not (tmp_path/'out').exists()
