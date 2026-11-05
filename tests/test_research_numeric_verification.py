from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3

import pytest

from cryptoforge import research_numeric_verification as verification, research_numeric_worker as worker
from cryptoforge import research_feature_windows as windows, research_code_resources as resources
from cryptoforge.training_diagnostics import canonical, digest
from test_research_numeric_controls import migrated, fake_worker
from test_research_code_static import source
from test_research_feature_windows import capture, request


def mock_runtime(monkeypatch):
    calls=[]
    def execute(packet):
        calls.append(packet)
        result=fake_worker(packet)
        result['runtime']=resources._runtime()
        unit='cryptoforge-research-resource-'+format(len(calls),'016x')+'.scope'
        result['child'].update(unit=unit,cgroup_path='/user.slice/'+unit,
            schema_version='research-numeric-child-v1',packet_sha256=digest(packet),
            python_version='3.12.3',checks={name:True for name in ('configured_limits','network_namespace_differs',
                'only_loopback','private_paths_hidden','environment_cleared','no_capabilities','no_new_privileges')})
        return result
    monkeypatch.setattr(worker,'run',execute)
    return calls


def prepared(tmp_path,**kwargs):
    budget,preview,seed=migrated(tmp_path,**kwargs)
    directory=tmp_path/'verification'
    plan=verification.prepare(directory,budget,preview,seed,capture(),verification.POLICY)
    return directory,budget,preview,seed,plan


def test_prepare_freezes_two_real_window_choices_without_new_journal_or_attempt(tmp_path):
    directory,budget,preview,seed,plan=prepared(tmp_path)
    assert plan['policy']==verification.POLICY
    assert [case['request']['bars'] for case in plan['cases']]==[1,2]
    assert len({case['identity']['window_identity_sha256'] for case in plan['cases']})==2
    assert len({case['operation_key'] for case in plan['cases']})==2
    assert budget.snapshot()['numeric_control_reserved']==0
    assert plan['metamorphic']['scope']=='input_selection_only'
    assert all(case['future_value_invariant'] for case in plan['metamorphic']['results'])
    assert len(list(directory.rglob('*.json')))==7
    assert all(path.stat().st_mode & 0o777==0o600 for path in directory.rglob('*.json'))
    assert all(path.stat().st_mode & 0o777==0o700 for path in (directory,*[p for p in directory.rglob('*') if p.is_dir()]))


def test_budgeted_two_process_evidence_matches_reference_and_readback_is_read_only(tmp_path,monkeypatch):
    calls=mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    with sqlite3.connect(budget.legacy.path) as db:before=budget._check(db)[0]
    receipt=verification.execute(directory,budget,preview,seed,capture())
    assert receipt['status']=='completed' and receipt['new_v4_actions']==2
    assert receipt['invocation_worker_evaluations']==32 and len(calls)==2
    assert receipt['summary']['shared_13_fixture_reproducibility']
    assert receipt['summary']['reference_agreement'] and receipt['summary']['selected_windows_valid']
    assert not receipt['summary']['whole_packet_reexecution_proven']
    assert sum(case['reference_evaluations'] for case in receipt['cases'])==16
    assert not receipt['summary']['trusted_reference_cost_in_v4_handler_measurement']
    assert budget.snapshot()['numeric_control_reserved']==2 and budget.snapshot()['total_reserved']==4
    raw=budget.legacy.path.read_bytes()
    result=verification.verify(directory,budget,preview,seed,capture())
    assert result['verification_passed'] and result['new_v4_actions']==0
    assert result['database_read_only'] and len(calls)==2 and raw==budget.legacy.path.read_bytes()
    with sqlite3.connect(budget.legacy.path) as db:assert before==budget._check(db)[0]
    with pytest.raises(FileExistsError):verification.execute(directory,budget,preview,seed,capture())


def test_new_protocol_directory_uses_same_completed_effects_without_new_attempts(tmp_path,monkeypatch):
    calls=mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    verification.execute(directory,budget,preview,seed,capture())
    second=tmp_path/'second'
    verification.prepare(second,budget,preview,seed,capture(),verification.POLICY)
    receipt=verification.execute(second,budget,preview,seed,capture())
    assert receipt['status']=='completed' and receipt['new_v4_actions']==0
    assert receipt['invocation_worker_evaluations']==0 and len(calls)==2
    assert budget.snapshot()['numeric_control_reserved']==2


@pytest.mark.parametrize('expression,expected', [
    ('0',0.0),('-0.0',0.0),('+(1)',1.0),('1/3',1/3),('(0.1+0.2)-0.3',(0.1+0.2)-0.3),
    ('1/1000000',1/1000000),('abs(-2)',2.0),('min(3,2,1)',1.0),('max(-1,-2,-3)',-1.0),
    ("window[-1]['close']/window[-2]['close']-1",4/3-1),
    ("(window[0]['high']-window[0]['low'])/window[0]['close']",0.0),
    ('0.0000000000000000000001*0.0000000000000000000001',1e-22*1e-22),
    ('1/(1-1)',None),('1000000*1000000*1000000',None),('1/1e-300',None),
])
def test_reference_uses_independent_ast_fraction_math_and_normalized_binary64(expression,expected):
    packet,_,_=worker.packet(source(expression),windows.prepare(capture(),request(),windows.POLICY)['payload']['window'])
    result=verification.reference(source(expression),packet['cases'])
    row=result['results'][-1]
    assert row['status']==('numeric_invalid' if expected is None else 'valid_output')
    assert row['value']==expected
    if expected is not None:assert row['value'].hex()==(expected if expected else 0.0).hex()
    assert result['reference_evaluations']>0


def test_reference_refuses_missing_history_instead_of_returning_zero():
    candidate=source("window[-64]['close']")
    packet,_,_=worker.packet(candidate,windows.prepare(capture(),request(),windows.POLICY)['payload']['window'])
    result=verification.reference(candidate,packet['cases'])
    assert result['reference_evaluations']==1
    assert result['results'][-1]=={'id':'selected_window','status':'insufficient_window','value':None}
    assert result['results'][4]['status']=='valid_output'


@pytest.mark.parametrize('expression',["__import__('os')",'2**100',"window[-1]['future']",'open("key")'])
def test_reference_cannot_evaluate_open_python(expression):
    with pytest.raises(ValueError):verification.reference(source(expression),[])


def test_reference_catches_a_worker_arithmetic_error_and_stops_before_second_attempt(tmp_path,monkeypatch):
    calls=mock_runtime(monkeypatch);original=worker.run
    def faulty(packet):
        result=original(packet)
        result['child']['results'][0]['value']=999.0
        return result
    monkeypatch.setattr(worker,'run',faulty)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    receipt=verification.execute(directory,budget,preview,seed,capture())
    assert receipt['status']=='verification_failed' and not receipt['cases'][0]['reference_matches']
    assert receipt['new_v4_actions']==1 and len(calls)==1
    assert budget.snapshot()['numeric_statuses']=={'completed':1}
    assert not verification.verify(directory,budget,preview,seed,capture())['verification_passed']


def test_reused_scope_cannot_claim_cross_process_independence(tmp_path,monkeypatch):
    mock_runtime(monkeypatch);original=worker.run
    def same(packet):
        result=original(packet);unit='cryptoforge-research-resource-'+'0'*16+'.scope';result['child'].update(unit=unit,cgroup_path='/user.slice/'+unit);return result
    monkeypatch.setattr(worker,'run',same)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    receipt=verification.execute(directory,budget,preview,seed,capture())
    assert receipt['status']=='verification_failed'
    assert receipt['summary']['reference_agreement'] and not receipt['summary']['shared_13_fixture_reproducibility']


@pytest.mark.parametrize('change',['policy','source_hash','capture','window','plan_hash','runtime'])
def test_frozen_plan_changes_fail_before_worker_admission(tmp_path,monkeypatch,change):
    calls=mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    supplied=capture()
    if change=='capture':supplied['source_export_sha256']='b'*64
    elif change=='window':(directory/'bars_1/window.json').write_text('{}')
    else:
        if change=='policy':plan['policy']['selected_window_bars']=[1,3]
        elif change=='source_hash':plan['implementation']['verification']='0'*64
        elif change=='runtime':plan['runtime']['python']='0'*64
        else:plan['plan_sha256']='0'*64
        (directory/'plan.json').write_text(canonical(plan))
    with pytest.raises(ValueError):verification.execute(directory,budget,preview,seed,supplied)
    assert not calls and budget.snapshot()['numeric_control_reserved']==0


@pytest.mark.parametrize('change',['summary','case','checksum','status','plan_binding'])
def test_readback_refuses_recomputed_but_false_receipts(tmp_path,monkeypatch,change):
    mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    receipt=verification.execute(directory,budget,preview,seed,capture())
    if change=='summary':receipt['summary']['whole_packet_reexecution_proven']=True
    elif change=='case':receipt['cases'][0]['reference_matches']=False
    elif change=='status':receipt['status']='verification_failed'
    elif change=='plan_binding':receipt['plan_sha256']='0'*64
    if change!='checksum':receipt['receipt_sha256']=digest({key:value for key,value in receipt.items() if key!='receipt_sha256'})
    else:receipt['receipt_sha256']='0'*64
    (directory/'receipt.json').write_text(canonical(receipt))
    raw=budget.legacy.path.read_bytes()
    with pytest.raises(ValueError):verification.verify(directory,budget,preview,seed,capture())
    assert raw==budget.legacy.path.read_bytes()


def test_future_transform_does_not_claim_pass_without_development_time_to_add_a_row():
    supplied=capture();supplied['development_end']=request()['decision_time']
    result=verification.metamorphic(supplied,[request(bars=1),request(bars=2)])
    assert all(row['future_value_invariant'] is None for row in result['results'])
    assert result['candidate_reexecutions']==0 and not result['upstream_or_financial_causality_proven']


def test_existing_future_values_and_late_observations_are_excluded_from_both_selected_windows():
    supplied=capture(8)
    result=verification.metamorphic(supplied,[request(bars=1),request(bars=2)])
    assert all(row['future_rows_changed_or_added']==4 and row['future_value_invariant'] for row in result['results'])
    assert supplied==capture(8)


def test_started_worker_failure_is_safe_and_does_not_refund_or_run_second_case(tmp_path,monkeypatch):
    directory,budget,preview,seed,plan=prepared(tmp_path)
    monkeypatch.setattr(worker,'run',lambda packet:(_ for _ in ()).throw(ValueError('private text')))
    receipt=verification.execute(directory,budget,preview,seed,capture())
    assert receipt['status']=='failed' and receipt['safe_error']=='verification_inputs_budget_or_worker_rejected'
    assert budget.snapshot()['numeric_statuses']=={'failed':1}
    assert 'private text' not in (directory/'receipt.json').read_text()
    with pytest.raises(ValueError):verification.verify(directory,budget,preview,seed,capture())
    with pytest.raises(FileExistsError):verification.execute(directory,budget,preview,seed,capture())


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS')!='1',reason='actual namespace/cgroup worker test')
@pytest.mark.parametrize('expression',["window[-1]['close']",'1/3',"window[-1]['close']/window[-2]['close']-1"])
def test_actual_scopes_and_independent_reference_agree_on_shared_fixtures(tmp_path,expression):
    directory,budget,preview,seed,plan=prepared(tmp_path,expression=expression)
    receipt=verification.execute(directory,budget,preview,seed,capture())
    assert receipt['summary']['distinct_worker_scopes']
    assert receipt['summary']['shared_13_fixture_reproducibility'] and receipt['summary']['reference_agreement']
    assert receipt['status']==('verification_failed' if '-2' in expression else 'completed')
    assert len({row['unit'] for row in receipt['cases']})==2
    assert verification.verify(directory,budget,preview,seed,capture())['database_read_only']


def test_prepared_manifest_and_returned_receipt_do_not_alias_loaded_implementation(tmp_path,monkeypatch):
    mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    plan['implementation']['verification']='changed'
    verification._guard()
    result=verification.execute(directory,budget,preview,seed,capture())
    result['implementation']['verification']='changed'
    verification._guard()
    assert verification.verify(directory,budget,preview,seed,capture())['verification_passed']


@pytest.mark.parametrize('change',['empty_checks','packet_hash','cleanup','cgroup_path'])
def test_missing_runtime_proof_cannot_count_as_reproducibility(tmp_path,monkeypatch,change):
    mock_runtime(monkeypatch);original=worker.run
    def bad(packet):
        result=original(packet)
        if change=='empty_checks':result['child']['checks']={}
        elif change=='packet_hash':result['child']['packet_sha256']='0'*64
        elif change=='cleanup':result['unit_removed']=False
        else:result['child']['cgroup_path']='/../../etc'
        return result
    monkeypatch.setattr(worker,'run',bad)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    result=verification.execute(directory,budget,preview,seed,capture())
    assert result['status']=='failed' and budget.snapshot()['numeric_control_reserved']==1
    with pytest.raises(ValueError):verification.verify(directory,budget,preview,seed,capture())


def test_loaded_verifier_change_stops_before_admission(tmp_path,monkeypatch):
    calls=mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    monkeypatch.setattr(verification,'implementation',lambda:{'changed':True})
    with pytest.raises(ValueError):verification.execute(directory,budget,preview,seed,capture())
    assert not calls and budget.snapshot()['numeric_control_reserved']==0


def test_existing_last_slot_cannot_be_used_twice_by_protocol(tmp_path,monkeypatch):
    calls=mock_runtime(monkeypatch)
    directory,budget,preview,seed,plan=prepared(tmp_path)
    from test_research_numeric_controls import run
    run(budget,preview,seed)
    extra=tmp_path/'different';windows.stage_window(extra,capture(),request(bars=4),windows.POLICY)
    run(budget,preview,extra)
    assert budget.snapshot()['numeric_control_reserved']==2
    result=verification.execute(directory,budget,preview,seed,capture())
    assert result['status']=='failed' and len(result['cases'])==1
    assert budget.snapshot()['numeric_control_reserved']==3 and len(calls)==3


def test_cli_prepare_execute_and_verify_use_explicit_fixed_policy(tmp_path,monkeypatch):
    mock_runtime(monkeypatch)
    budget,preview,seed=migrated(tmp_path)
    paths={}
    for name,value in [('semantic',budget.legacy.semantic_policy),('code',budget.legacy.code_policy),
        ('numeric',budget.configuration['policy']),('verification',verification.POLICY),('capture',capture())]:
        path=tmp_path/(name+'.json');path.write_text(canonical(value));paths[name]=path
    from test_research_run_budget import bindings
    bound=bindings(tmp_path)
    args=['--database',str(budget.legacy.path),'--proposal-ledger',str(bound['proposal']),
        '--semantic-ledger',str(bound['semantic_fixture']),'--fit-ledger',str(bound['fit']),
        '--semantic-live-ledger',str(tmp_path/'live.sqlite'),'--semantic-live-policy',str(paths['semantic']),
        '--code-policy',str(paths['code']),'--numeric-policy',str(paths['numeric']),
        '--verification-policy',str(paths['verification']),'--preview',str(preview),'--seed-window',str(seed),
        '--capture',str(paths['capture']),'--directory',str(tmp_path/'protocol')]
    assert verification.main([*args,'prepare'])==0
    assert verification.main([*args,'execute'])==0
    raw=budget.legacy.path.read_bytes()
    assert verification.main([*args,'verify'])==0 and raw==budget.legacy.path.read_bytes()
    with pytest.raises(FileExistsError):verification.main([*args,'execute'])
