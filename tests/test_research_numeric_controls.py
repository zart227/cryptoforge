from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading

import pytest

from cryptoforge import research_numeric_controls as numeric, research_numeric_worker as worker
from cryptoforge import research_code_budget as code, research_code_preview as preview
from cryptoforge import research_run_budget as common, research_feature_windows as windows
from cryptoforge.research_training_diagnostics import canonical, digest
from test_research_code_static import registered, source, bundle
from test_research_feature_windows import capture, request


def setup(tmp_path, *, expression='1.0', **kwargs):
    legacy,directory = registered(tmp_path,candidate=source(expression),**kwargs)
    selected = tmp_path/'window'; windows.stage_window(selected,capture(),request(),windows.POLICY)
    budget = numeric.NumericControlBudget(legacy,numeric.POLICY)
    return budget,directory,selected


def migrated(tmp_path, **kwargs):
    result = setup(tmp_path,**kwargs); result[0].migrate(); return result


def fake_worker(packet):
    # Independent test oracle. No candidate source or Python code is executed.
    def read(node, data):
        op = node[0]
        if op == 'const': return float(node[1])
        if op == 'read': return data[node[1]][node[2]]
        args = [read(item,data) for item in node[1:]]
        if op == 'pos': return +args[0]
        if op == 'neg': return -args[0]
        if op == 'abs': return abs(args[0])
        if op == 'min': return min(args)
        if op == 'max': return max(args)
        if op == 'add': return args[0]+args[1]
        if op == 'sub': return args[0]-args[1]
        if op == 'mul': return args[0]*args[1]
        return args[0]/args[1]
    def lookback(node):
        if node[0] == 'read': return node[1]+1 if node[1]>=0 else -node[1]
        if node[0] == 'const': return 0
        return max(map(lookback,node[1:]))
    required = lookback(packet['program']); results=[]
    for case in packet['cases']:
        if not case['valid']: status,value,n,repeated = 'input_rejected',None,0,None
        elif len(case['window']) < required: status,value,n,repeated = 'insufficient_window',None,0,None
        else:
            try: value = windows.validate_output({'value':read(packet['program'],case['window'])})['value']; status='valid_output'
            except (ValueError,ArithmeticError): value=None;status='numeric_invalid'
            n,repeated=2,True
        results.append({'id':case['id'],'status':status,'value':value,'evaluations':n,'repeat_equal':repeated})
    return {'child':{'required_window_size':required,'results':results,
        'output_checks':[{'id':case['id'],'accepted':case['valid']} for case in packet['outputs']]},
        'runtime':{},'unit_removed':True,'cgroup_removed':True}


def run(budget,directory,selected, **kwargs): return budget.check(directory,selected,capture(),**kwargs)


def test_explicit_additive_seal_preserves_history_and_does_not_reset_shared_budget(tmp_path):
    budget,directory,selected = setup(tmp_path)
    with sqlite3.connect(budget.legacy.path) as db: before=numeric._history(db)
    old=budget.legacy.snapshot(); report=budget.migrate()
    assert report['new_actions']==0 and report['legacy_writers_sealed']
    with sqlite3.connect(budget.legacy.path) as db: assert numeric._history(db)==before
    snapshot=budget.snapshot()
    assert snapshot['total_reserved']==2 and snapshot['numeric_control_reserved']==0
    assert snapshot['reserved_allocations']==old['resources']['reserved_allocations']
    raw=budget.legacy.path.read_bytes(); assert budget.migrate()['already_migrated']
    assert budget.legacy.path.read_bytes()==raw
    with pytest.raises(ValueError): budget.legacy.snapshot()
    with pytest.raises(ValueError): budget.legacy.run('fit',{},lambda:pytest.fail('sealed writer'))
    assert budget.legacy.path.read_bytes()==raw


def test_control_is_distinct_common_action_and_cache_has_zero_new_evaluations(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path); calls=[]
    monkeypatch.setattr(worker,'run',lambda packet:(calls.append(packet) or fake_worker(packet)))
    first=run(budget,directory,selected); second=run(budget,directory,selected)
    assert len(calls)==1 and not first['cached'] and second['cached']
    assert second['new_actions']==0 and second['invocation_arithmetic_evaluations']==0
    assert first['result']==second['result'] and first['result']['summary']['arithmetic_evaluations']==16
    status=budget.snapshot()
    assert status['reserved_by_kind']=={'fit':1,'code_check':1,'numeric_control':1}
    assert status['reserved_allocations']=={'input_tokens':0,'output_tokens':0,'wall_ms':50000}
    assert status['total_reserved']==3 and status['semantic_questions_reserved']==0
    assert not first['result']['candidate_python_executed'] and not first['result']['feature_utility_verified']


def test_reworded_preview_and_future_tail_share_effect_cache_but_retain_original_provenance(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path)
    monkeypatch.setattr(worker,'run',fake_worker)
    first=run(budget,directory,selected)
    changed=bundle(tmp_path,'reworded',wording='Different text with the same source effect')
    tail=tmp_path/'future'; windows.stage_window(tail,capture(20),request(),windows.POLICY)
    second=budget.check(changed,tail,capture(20))
    assert second['cached'] and second['result']==first['result']
    assert second['current_preview_sha256'] != first['current_preview_sha256']
    assert second['current_window_pack_sha256'] != first['current_window_pack_sha256']
    assert budget.snapshot()['total_reserved']==3


@pytest.mark.parametrize('kind', ['failed','cancelled','timed_out','reserved'])
def test_failed_cancelled_timeout_or_exit_attempt_keeps_reservation_and_has_no_retry(tmp_path,monkeypatch,kind):
    budget,directory,selected=migrated(tmp_path)
    def fail(packet):
        if kind=='failed': raise ValueError('private text not logged')
        if kind=='cancelled': raise KeyboardInterrupt()
        if kind=='timed_out': raise subprocess.TimeoutExpired(['fixed'],8)
        raise SystemExit(3)
    monkeypatch.setattr(worker,'run',fail)
    with pytest.raises((RuntimeError,common.BudgetCancelled,common.BudgetTimedOut,SystemExit)): run(budget,directory,selected)
    snapshot=budget.snapshot()
    assert snapshot['numeric_statuses']=={kind:1} and snapshot['numeric_control_reserved']==1
    assert snapshot['reserved_allocations']['wall_ms']==50000
    monkeypatch.setattr(worker,'run',lambda packet:pytest.fail('no retry'))
    with pytest.raises(ValueError,match='no automatic retry'): run(budget,directory,selected)
    assert b'private text' not in budget.legacy.path.read_bytes()


def test_cancel_before_reservation_spends_nothing(tmp_path):
    budget,directory,selected=migrated(tmp_path); event=threading.Event();event.set()
    raw=budget.legacy.path.read_bytes()
    with pytest.raises(common.BudgetCancelled): run(budget,directory,selected,cancel_event=event)
    assert budget.legacy.path.read_bytes()==raw


@pytest.mark.parametrize('limit', ['total','daily','wall'])
def test_existing_shared_quota_is_consumed_without_new_kind_reset(tmp_path,monkeypatch,limit):
    policy=deepcopy(common.DEFAULT_POLICY);resources=None
    if limit=='total': policy['total_actions']=2
    elif limit=='daily': policy['daily_actions']=2
    else:
        from cryptoforge.research_resource_budget import DEFAULT_RESOURCES
        resources=deepcopy(DEFAULT_RESOURCES);resources['total_wall_ms']=49999
    budget,directory,selected=migrated(tmp_path,policy=policy,resource_policy=resources)
    monkeypatch.setattr(worker,'run',lambda packet:pytest.fail('no worker at exhausted shared quota'))
    with pytest.raises(ValueError,match='budget exhausted'): run(budget,directory,selected)
    assert budget.snapshot()['total_reserved']==2


def test_race_for_last_shared_action_is_atomic(tmp_path,monkeypatch):
    policy=deepcopy(common.DEFAULT_POLICY);policy['total_actions']=3
    budget,directory,selected=migrated(tmp_path,policy=policy)
    second=tmp_path/'second'; windows.stage_window(second,capture(),request(bars=2),windows.POLICY)
    monkeypatch.setattr(worker,'run',fake_worker)
    def attempt(path):
        try: return run(budget,directory,path)
        except ValueError: return None
    with ThreadPoolExecutor(2) as pool: result=list(pool.map(attempt,[selected,second]))
    assert sum(item is not None for item in result)==1 and budget.snapshot()['total_reserved']==3


def test_cache_survives_exhausted_total_and_new_utc_day_does_not_duplicate(tmp_path,monkeypatch):
    now=[datetime(2026,10,20,tzinfo=timezone.utc)]
    policy=deepcopy(common.DEFAULT_POLICY);policy['total_actions']=3
    budget,directory,selected=migrated(tmp_path,policy=policy,clock=lambda:now[0])
    monkeypatch.setattr(worker,'run',fake_worker)
    first=run(budget,directory,selected); now[0]+=timedelta(days=1)
    assert run(budget,directory,selected)['result']==first['result']
    assert budget.snapshot()['today_reserved']==0 and budget.snapshot()['total_reserved']==3


@pytest.mark.parametrize('change', ['cap','enabled','extra','bool'])
def test_closed_policy_cannot_expand_quota_or_enable_python(tmp_path,change):
    budget,_,_=setup(tmp_path);policy=deepcopy(numeric.POLICY)
    if change=='cap':policy['maximum_actions']=4
    elif change=='enabled':policy['generic_python_execution_enabled']=True
    elif change=='extra':policy['unknown']=1
    else:policy['input_tokens']=False
    with pytest.raises(ValueError):numeric.NumericControlBudget(budget.legacy,policy)


@pytest.mark.parametrize('change', ['reserved','checksum','extra_table','missing_resource','wrong_binding'])
def test_migration_refuses_unresolved_corrupt_incomplete_history_without_writing(tmp_path,change):
    budget,_,_=setup(tmp_path)
    with sqlite3.connect(budget.legacy.path) as db:
        if change=='reserved':db.execute("UPDATE coordinated_actions SET status='reserved' WHERE kind='fit'")
        elif change=='checksum':db.execute("UPDATE coordinated_actions SET payload_sha='bad' WHERE kind='fit'")
        elif change=='extra_table':db.execute('CREATE TABLE unwanted (x INTEGER)')
        elif change=='missing_resource':db.execute("DELETE FROM coordinated_resources WHERE key IN (SELECT key FROM coordinated_actions WHERE kind='fit')")
    if change=='wrong_binding': budget.legacy.manifest['journal_path_hashes']['fit']='0'*64
    raw=budget.legacy.path.read_bytes()
    with pytest.raises(ValueError):budget.migrate()
    assert budget.legacy.path.read_bytes()==raw


@pytest.mark.parametrize('change', ['history','receipt','config','table','result','measurement'])
def test_sealed_state_tampering_refused_without_repair(tmp_path,monkeypatch,change):
    budget,directory,selected=migrated(tmp_path);monkeypatch.setattr(worker,'run',fake_worker)
    run(budget,directory,selected)
    with sqlite3.connect(budget.legacy.path) as db:
        if change=='history':db.execute("UPDATE coordinated_actions SET input_sha='bad' WHERE kind='fit'")
        elif change in ('receipt','config'):
            raw,sha=db.execute('SELECT payload,sha FROM coordinated_numeric_extension').fetchone();data=json.loads(raw)
            if change=='receipt':data['migration']['prior_action_count']=0
            else:data['configuration']['policy']['maximum_actions']=4
            db.execute('UPDATE coordinated_numeric_extension SET payload=?,sha=?',(canonical(data),digest(data)))
        elif change=='table':db.execute('CREATE VIEW unwanted AS SELECT 1')
        elif change=='result':db.execute("UPDATE coordinated_numeric_actions SET payload_sha='bad'")
        else:db.execute('UPDATE coordinated_numeric_actions SET measured_wall_ms=-1')
    raw=budget.legacy.path.read_bytes()
    with pytest.raises(ValueError):budget.snapshot()
    assert budget.legacy.path.read_bytes()==raw


def test_runtime_failure_is_completed_evidence_without_numeric_validity_claim(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path,expression='1 / (1 - 1)')
    monkeypatch.setattr(worker,'run',fake_worker)
    result=run(budget,directory,selected)
    assert not result['result']['summary']['all_applicable_outputs_valid']
    assert all(row['status']=='numeric_invalid' for row in result['result']['observation']['child']['results'] if row['evaluations'])
    assert budget.snapshot()['numeric_statuses']=={'completed':1}
    assert run(budget,directory,selected)['cached']


def test_unavailable_window_and_unregistered_preview_do_not_reserve_controls(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path); raw=budget.legacy.path.read_bytes()
    bad=bundle(tmp_path,'unregistered',candidate=source('2'))
    monkeypatch.setattr(worker,'run',lambda packet:pytest.fail('invalid preflight'))
    with pytest.raises(ValueError):run(budget,bad,selected)
    unavailable=tmp_path/'unavailable';windows.stage_window(unavailable,capture(2),request(),windows.POLICY)
    with pytest.raises(ValueError):budget.check(directory,unavailable,capture(2))
    assert budget.legacy.path.read_bytes()==raw


def test_mutation_during_worker_is_failed_and_reserved(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path)
    def mutate(packet):
        (directory/'candidate/research/feature_candidate.py').write_text(source('999'))
        return fake_worker(packet)
    monkeypatch.setattr(worker,'run',mutate)
    with pytest.raises(RuntimeError):run(budget,directory,selected)
    assert budget.snapshot()['numeric_statuses']=={'failed':1}


@pytest.mark.parametrize('expression', ["__import__('os')",'2**100',"window[-1]['target']",'float(1)',"window[0].get('close')"])
def test_program_compiler_has_no_open_python_constructs(expression):
    with pytest.raises(ValueError):worker.program(source(expression))


@pytest.mark.parametrize('expression,expected', [('1',['const',1]),('-1',['neg',['const',1]]),
    ("window[-1]['close']",['read',-1,'close']),('max(1,abs(-2))',['max',['const',1],['abs',['neg',['const',2]]]])])
def test_closed_program_is_data_with_fixed_operators(expression,expected):
    assert worker.program(source(expression))[0]==expected


@pytest.mark.parametrize('change', ['count','order','invalid_evaluated','repeat','output','lookback'])
def test_parent_rejects_missing_or_false_control_observations(change):
    packet,analysis,_=worker.packet(source('1'),[{'open':1,'high':1,'low':1,'close':1,'volume':1}])
    result=fake_worker(packet)
    if change=='count':result['child']['results'].pop()
    elif change=='order':result['child']['results'].reverse()
    elif change=='invalid_evaluated':result['child']['results'][7]['evaluations']=1
    elif change=='repeat':result['child']['results'][0]['repeat_equal']=False
    elif change=='output':result['child']['output_checks'][0]['accepted']=False
    else:result['child']['required_window_size']=1
    with pytest.raises(ValueError):worker.validate_result(result,packet,analysis['required_window_size'])


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS')!='1',reason='explicit actual namespace/cgroup test')
@pytest.mark.parametrize('expression,expected', [('1.0',1.0),("window[-1]['close']",4.0),
    ("window[-1]['close'] / window[-2]['close'] - 1",4/3-1),
    ('max(0,min(1,abs(-2)))',1.0),('1/(1-1)',None),('1000000*1000000*1000000',None)])
def test_actual_fixed_interpreter_isolated_and_arithmetic_checked(expression,expected):
    packet,analysis,_=worker.packet(source(expression),windows.prepare(capture(),request(),windows.POLICY)['payload']['window'])
    observed=worker.run(packet);summary=worker.validate_result(observed,packet,analysis['required_window_size'])
    selected=observed['child']['results'][-1]
    assert selected['value']==expected
    assert selected['status']==('numeric_invalid' if expected is None else 'valid_output')
    assert observed['unit_removed'] and observed['cgroup_removed'] and all(observed['child']['checks'].values())
    assert summary['arithmetic_evaluations']>0 and selected['repeat_equal']


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS')!='1',reason='explicit actual namespace/cgroup test')
def test_actual_budgeted_worker_and_cached_replay_preserve_legacy_rows(tmp_path):
    budget,directory,selected=migrated(tmp_path,expression="window[-1]['close']")
    with sqlite3.connect(budget.legacy.path) as db: before=numeric._history(db)
    first=run(budget,directory,selected);second=run(budget,directory,selected)
    assert first['result']['summary']['all_applicable_outputs_valid'] and second['cached']
    assert first['result']['observation']['child']['results'][-1]['value']==4.0
    with sqlite3.connect(budget.legacy.path) as db: assert before==numeric._history(db)
    assert budget.snapshot()['total_reserved']==3


def test_kind_limit_includes_all_prior_numeric_windows(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path);monkeypatch.setattr(worker,'run',fake_worker)
    for bars in (1,2,3):
        path=tmp_path/('bars'+str(bars));windows.stage_window(path,capture(),request(bars=bars),windows.POLICY)
        run(budget,directory,path)
    path=tmp_path/'bars4';windows.stage_window(path,capture(),request(bars=4),windows.POLICY)
    with pytest.raises(ValueError,match='action budget exhausted'):run(budget,directory,path)
    assert budget.snapshot()['numeric_control_reserved']==3 and budget.snapshot()['total_reserved']==5


def test_prior_observed_overrun_blocks_fresh_work_and_keeps_completed_cache(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path);monkeypatch.setattr(worker,'run',fake_worker)
    first=run(budget,directory,selected)
    with sqlite3.connect(budget.legacy.path) as db:db.execute('UPDATE coordinated_numeric_actions SET measured_wall_ms=20001')
    assert budget.snapshot()['overrun_actions']==1 and run(budget,directory,selected)['cached']
    path=tmp_path/'different';windows.stage_window(path,capture(),request(bars=2),windows.POLICY)
    with pytest.raises(ValueError,match='overrun'):run(budget,directory,path)
    assert budget.snapshot()['total_reserved']==3


def test_cancel_after_atomic_reservation_is_charged(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path)
    class Event:
        count=0
        def is_set(self):self.count+=1;return self.count>=3
    monkeypatch.setattr(worker,'run',lambda packet:pytest.fail('cancelled before worker'))
    with pytest.raises(common.BudgetCancelled):run(budget,directory,selected,cancel_event=Event())
    assert budget.snapshot()['numeric_statuses']=={'cancelled':1}


def test_structurally_rejected_registered_source_never_reserves_runtime(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path,expression="__import__('os')")
    raw=budget.legacy.path.read_bytes()
    monkeypatch.setattr(worker,'run',lambda packet:pytest.fail('invalid source'))
    with pytest.raises(ValueError):run(budget,directory,selected)
    assert budget.legacy.path.read_bytes()==raw


def test_insufficient_history_is_explicit_even_when_full64_control_is_valid(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path,expression="window[-64]['close']")
    monkeypatch.setattr(worker,'run',fake_worker)
    result=run(budget,directory,selected)['result']
    assert result['summary']['selected_window_status']=='insufficient_window'
    assert result['summary']['arithmetic_evaluations']==2
    assert not result['summary']['all_valid_windows_have_sufficient_history']
    assert result['observation']['child']['results'][-1]['value'] is None


def test_cache_rechecks_controls_even_if_outer_result_hash_was_recomputed(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path);monkeypatch.setattr(worker,'run',fake_worker)
    run(budget,directory,selected)
    with sqlite3.connect(budget.legacy.path) as db:
        data=json.loads(db.execute('SELECT payload FROM coordinated_numeric_actions').fetchone()[0])
        data['summary']['arithmetic_evaluations']=999
        db.execute('UPDATE coordinated_numeric_actions SET payload=?,payload_sha=?',(canonical(data),digest(data)))
    with pytest.raises(ValueError,match='controls mismatch'):run(budget,directory,selected)


def test_configuration_and_loaded_source_cannot_change_existing_phase(tmp_path,monkeypatch):
    budget,directory,selected=migrated(tmp_path)
    monkeypatch.setattr(numeric,'implementation',lambda:{'changed':True})
    with pytest.raises(ValueError,match='source changed'):budget.snapshot()


def test_cli_exclusive_private_receipts_and_output_collision(tmp_path):
    budget,directory,selected=setup(tmp_path)
    semantic=tmp_path/'semantic-policy.json';semantic.write_text(canonical(budget.legacy.semantic_policy))
    code_policy=tmp_path/'code-policy.json';code_policy.write_text(canonical(code.POLICY))
    policy=tmp_path/'numeric-policy.json';policy.write_text(canonical(numeric.POLICY))
    args=['--database',str(budget.legacy.path),'--proposal-ledger',str(tmp_path/'proposal.sqlite'),
        '--semantic-ledger',str(tmp_path/'semantic.sqlite'),'--fit-ledger',str(tmp_path/'fit.sqlite'),
        '--semantic-live-ledger',str(tmp_path/'live.sqlite'),'--semantic-live-policy',str(semantic),
        '--code-policy',str(code_policy),'--numeric-policy',str(policy)]
    # Match the legacy test helper's actual binding names.
    from test_research_run_budget import bindings
    bound=bindings(tmp_path)
    for flag,kind in (('--proposal-ledger','proposal'),('--semantic-ledger','semantic_fixture'),('--fit-ledger','fit')):
        args[args.index(flag)+1]=str(bound[kind])
    output=tmp_path/'migration.json'
    assert numeric.main([*args,'--output',str(output),'migrate'])==0
    assert output.stat().st_mode & 0o777==0o600
    assert json.loads(output.read_text())['status']=='completed'
    with pytest.raises(FileExistsError):numeric.main([*args,'--output',str(output),'status'])
    with pytest.raises(SystemExit):numeric.main([*args,'--output',str(policy),'status'])


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS')!='1',reason='explicit actual namespace/cgroup test')
def test_actual_worker_refuses_arbitrary_operator_and_cleans_scope():
    packet,_,_=worker.packet(source('1'),[{'open':1,'high':1,'low':1,'close':1,'volume':1}])
    packet['program']=['__import__','os']
    with pytest.raises(ValueError,match='worker or cleanup failed'):worker.run(packet)
