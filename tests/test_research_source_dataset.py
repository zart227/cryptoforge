"""Exploratory source-to-dataset replay uses no fitting or network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from cryptoforge import research_source_dataset as m


def rows():
    start=datetime(2026,10,26,0,0,tzinfo=timezone.utc)
    result=[]
    for i in range(118):
        opened=start+timedelta(minutes=5*i); end=opened+timedelta(minutes=20)
        result.append({'pair':'BTC/USDT','input_end_time':opened.isoformat(),'label_end_time':end.isoformat(),
            'feature_hex':[float(i/100+j/1000).hex() for j in range(7)],'future_return_hex':float(.01).hex(),
            'long_label':i%2,'short_label':0})
    return result


def case():
    values=rows(); as_of='2026-10-26T10:08:39+00:00'
    packet={'schema_version':'source-dataset-replay-request-v1','worker_sha256':m._LOADED['worker'],
        'module_hashes':{'fake':'a'*64},'pairs':['BTC/USDT'],'as_of':as_of,'rows':{}}
    admission={'accepted_pairs':['BTC/USDT']}
    result={'schema_version':'source-dataset-replay-result-v1','request_sha256':m.digest(packet),
        'examples':values,'examples_sha256':m.digest(values),'source_admission':admission,
        'main_runtime_hashes':packet['module_hashes'],'query_pairs':packet['pairs'],
        'network_fit_prediction_publication_performed':False}
    native={'native':{'all_examples_sha256':m.digest(values),'all_examples':len(values),'source_admission':admission},
        'exact_parser':{'all_examples_sha256':m.digest(values)},'loaded_value_runtime':packet['module_hashes']}
    diagnostics={'report_sha256':'c'*64,'proposal_route':'review_source_data',
        'source_blocking_reasons':['minimum_pair_coverage_not_met'],
        'coverage':{'accepted_pairs':13,'requested_pairs':20,'minimum_satisfied':False}}
    binding={'diagnostics_directory':'fixture','source_pack':'fixture'}
    return binding,diagnostics,{},native,packet,result


def test_split_purges_crossing_label_boundaries_and_never_claims_independence():
    binding,diagnostics,audit,native,packet,replay=case()
    report=m._assemble(binding,diagnostics,audit,native,packet,replay)
    data=report['candidate_dataset']; split=report['split']
    assert split['validation_start']=='2026-10-26T04:05:00+00:00'
    assert split['train_label_end_before']=='2026-10-26T03:50:00+00:00'
    assert split['train_examples']+split['validation_examples']+split['purged_examples']==118
    assert split['purged_examples']>0
    assert all(m.timestamp(r['label_end_time']) < m.timestamp(split['train_label_end_before']) for r in data['train'])
    assert all(m.timestamp(r['open_time']) >= m.timestamp(split['validation_start']) for r in data['validation'])
    assert report['source_proposal_route']=='review_source_data' and report['source_blocking_reasons']
    assert report['training_admitted'] is False and report['independent_holdout_or_prospective_study'] is False
    with pytest.raises(ValueError):m.planner.parse_development(report)
    assert m.planner.parse_development(data)[0]==data  # schema compatibility, not approval


@pytest.mark.parametrize('change',['digest','native_digest','request','admission','runtime','queries','forged_work'])
def test_replay_must_match_the_full_original_native_and_exact_parser_evidence(change):
    _,_,_,native,packet,replay=case();native=deepcopy(native);replay=deepcopy(replay)
    if change=='digest':replay['examples'][0]['long_label']=1
    elif change=='native_digest':native['exact_parser']['all_examples_sha256']='f'*64
    elif change=='request':replay['request_sha256']='f'*64
    elif change=='admission':replay['source_admission']['accepted_pairs']=[]
    elif change=='runtime':replay['main_runtime_hashes']={'fake':'b'*64}
    elif change=='queries':replay['query_pairs']=[]
    else:replay['network_fit_prediction_publication_performed']=True
    with pytest.raises(ValueError):m._checked_replay(replay,native,packet)


@pytest.mark.parametrize('change',['future','nonfinite','duplicate','wrong_shape','boolean_label'])
def test_invalid_candidate_examples_are_rejected(change):
    values=rows()
    if change=='future':values[0]['label_end_time']='2026-10-27T00:00:00+00:00'
    elif change=='nonfinite':values[0]['feature_hex'][0]='nan'
    elif change=='duplicate':values[1]['input_end_time']=values[0]['input_end_time']
    elif change=='wrong_shape':values[0]['feature_hex'].pop()
    else:values[0]['long_label']=True
    with pytest.raises(ValueError):m._split(values,'2026-10-26T10:08:39+00:00')


def test_review_pack_reverifies_original_binding_and_stored_results_without_worker(tmp_path, monkeypatch):
    bound=case();binding, diagnostics, audit, native, packet, replay=bound
    monkeypatch.setattr(m,'_inputs',lambda directory:(deepcopy(binding),deepcopy(diagnostics),deepcopy(audit),deepcopy(native),deepcopy(packet)))
    launched=[];monkeypatch.setattr(m,'_replay',lambda *args:(launched.append(1) or deepcopy(replay)))
    binding['main_project']='fixture';out=tmp_path/'review';original=m.prepare(out,tmp_path)
    assert len(launched)==1
    monkeypatch.setattr(m,'_replay',lambda *args:pytest.fail('verification cannot launch worker'))
    assert m.verify(out)==original
    p=out/'review.json';stored=m._read(out,'review.json');stored['training_admitted']=True
    p.write_text(m.canonical(stored));p.chmod(0o600)
    with pytest.raises(ValueError,match='review_dataset_changed'):m.verify(out)


def test_replay_source_guard_and_existing_destination_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(m,'_inputs',lambda *a:pytest.fail('destination must be new'))
    monkeypatch.setattr(m,'_replay',lambda *a:pytest.fail('source changed'))
    with pytest.raises(ValueError,match='new_review_directory'):m.prepare(tmp_path,tmp_path)
    monkeypatch.setattr(m,'implementation',lambda:{})
    with pytest.raises(ValueError,match='implementation_changed'):m.verify(tmp_path)
