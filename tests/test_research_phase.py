from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import sqlite3
import threading

import pytest

from cryptoforge import research_phase as phase,research_numeric_controls as numeric,research_run_budget as common
from cryptoforge import research_numeric_worker as worker,research_code_budget as code,research_feature_windows as windows
from cryptoforge import llm_research_coordinator as coordinator
from cryptoforge.research_semantic_budget import DEFAULT_SEMANTIC_POLICY
from cryptoforge.research_resource_budget import DEFAULT_RESOURCES
from cryptoforge.research_training_diagnostics import canonical,digest
from test_research_numeric_controls import migrated as numeric_migrated,fake_worker
from test_research_numeric_controls import setup as numeric_setup
from test_research_run_budget import envelope,bindings
from test_research_feature_windows import capture,request
from test_llm_training_study import inputs
from cryptoforge.training_experiment_planner import freeze_protocol


def prepared(tmp_path,**kwargs):
    previous,preview,selected=numeric_migrated(tmp_path,**kwargs)
    return phase.ResearchPhaseBudget(previous,phase.POLICY),preview,selected


def migrated(tmp_path,**kwargs):
    result=prepared(tmp_path,**kwargs);result[0].migrate();return result


def test_phase_migration_preserves_all_prior_tables_and_quotas_atomically(tmp_path):
    budget,preview,selected=prepared(tmp_path)
    before=budget.previous.snapshot()
    with sqlite3.connect(budget.path) as db:history=phase._history(db)
    result=budget.migrate()
    assert not result['already_migrated'] and result['new_actions']==0
    assert result['numeric_control_cache_only'] and not result['journal_relocated_or_reset']
    with sqlite3.connect(budget.path) as db:assert phase._history(db)==history
    after=budget.snapshot()
    assert after['total_reserved_actions']==before['total_reserved']
    assert after['reserved_by_kind']==before['reserved_by_kind']
    assert after['resources']['reserved_allocations']==before['reserved_allocations']
    raw=budget.path.read_bytes();assert budget.migrate()['already_migrated']
    assert budget.path.read_bytes()==raw
    with pytest.raises(ValueError):budget.previous.snapshot()
    with pytest.raises(ValueError):budget.legacy.snapshot()
    assert not any(path.exists() for path in bindings(tmp_path).values())


def test_effect_keys_and_original_v3_cache_survive_phase_transition(tmp_path):
    budget,preview,selected=migrated(tmp_path)
    result=budget.run('fit',{'initial':True},lambda:pytest.fail('old cached fit cannot execute'))
    assert result['coordinator_cached'] and result['cache_origin']=='v3'
    assert result['invocation_observed']==common.ZERO_USAGE
    assert budget.snapshot()['total_reserved_actions']==2
    old_preview=code.check_preview(budget,preview)
    assert old_preview['coordinator_cached'] and old_preview['cache_origin']=='v3'
    assert old_preview['result']['candidate_execution_enabled'] is False


def test_old_failed_effect_cannot_retry_by_changing_phase_or_day(tmp_path):
    previous,preview,selected=numeric_setup(tmp_path)
    def fail():raise ValueError('private error')
    with pytest.raises(RuntimeError):previous.legacy.run('fit',{'failed':True},fail)
    previous.migrate()
    budget=phase.ResearchPhaseBudget(previous,phase.POLICY);budget.migrate()
    with pytest.raises(ValueError,match='no automatic retry'):budget.run('fit',{'failed':True},lambda:pytest.fail('no retry'))
    assert budget.snapshot()['total_reserved_actions']==3


@pytest.mark.parametrize('kind',['proposal','fit','semantic_fixture','semantic_live','code_check'])
def test_supported_kinds_resume_under_same_shared_limits_and_cache(tmp_path,kind):
    budget,preview,selected=migrated(tmp_path);calls=[]
    def operation():calls.append(1);return {'result':{'origin':'synthetic_accounting'},'observed':dict(common.ZERO_USAGE)}
    questions=2 if kind in ('semantic_fixture','semantic_live') else 0
    first=budget.run(kind,{'new':kind},operation,questions=questions)
    repeat=budget.run(kind,{'new':kind},operation,questions=questions)
    assert not first['coordinator_cached'] and repeat['coordinator_cached'] and repeat['cache_origin']=='v5'
    assert first['operation_key']==repeat['operation_key'] and len(calls)==1
    status=budget.snapshot()
    assert status['total_reserved_actions']==3 and status['phase_actions']==1
    assert status['reserved_semantic_questions']==questions


def test_numeric_cache_preserves_original_evidence_and_blocks_every_fresh_launch(tmp_path,monkeypatch):
    previous,preview,selected=numeric_migrated(tmp_path)
    monkeypatch.setattr(worker,'run',fake_worker)
    original=previous.check(preview,selected,capture())
    budget=phase.ResearchPhaseBudget(previous,phase.POLICY);budget.migrate()
    raw=budget.path.read_bytes()
    monkeypatch.setattr(worker,'run',lambda packet:pytest.fail('new numeric execution prohibited'))
    result=budget.numeric_cache(preview,selected,capture())
    assert result['result']==original['result'] and result['operation_key']==original['operation_key']
    assert result['new_actions']==0 and result['database_read_only'] and result['new_worker_launches']==0
    different=tmp_path/'different';windows.stage_window(different,capture(),request(bars=2),windows.POLICY)
    with pytest.raises(ValueError,match='completed-cache only'):budget.numeric_cache(preview,different,capture())
    with pytest.raises(ValueError,match='cache-only'):budget.run('numeric_control',{},lambda:pytest.fail('unsupported numeric handler'))
    assert budget.path.read_bytes()==raw


@pytest.mark.parametrize('error,status',[(ValueError,'failed'),(common.BudgetCancelled,'cancelled'),
    (common.BudgetTimedOut,'timed_out'),(KeyboardInterrupt,'cancelled'),(SystemExit,'reserved')])
def test_failure_timeout_cancel_and_process_exit_remain_charged_without_retry(tmp_path,error,status):
    budget,_,_=migrated(tmp_path)
    def fail():raise error('private error content')
    with pytest.raises((RuntimeError,SystemExit)):budget.run('proposal',{'attempt':1},fail)
    snapshot=budget.snapshot()
    assert snapshot['statuses'][status]==1 and snapshot['total_reserved_actions']==3
    assert snapshot['resources']['reserved_allocations']['input_tokens']==32000
    with pytest.raises(ValueError,match='no automatic retry'):budget.run('proposal',{'attempt':1},lambda:pytest.fail('retry'))
    assert b'private error content' not in budget.path.read_bytes()


@pytest.mark.parametrize('limit',['total','daily','kind','questions','wall','input_tokens','output_tokens'])
def test_prior_usage_and_allocations_count_toward_all_limits(tmp_path,limit):
    policy=deepcopy(common.DEFAULT_POLICY);resources=deepcopy(DEFAULT_RESOURCES);kind='proposal';questions=0
    if limit=='total':policy['total_actions']=2
    elif limit=='daily':policy['daily_actions']=2
    elif limit=='kind':policy['maximum_by_kind']['fit']=1;kind='fit'
    elif limit=='questions':policy['semantic_questions']=1;kind='semantic_fixture';questions=2
    elif limit=='wall':resources['total_wall_ms']=94999
    elif limit=='input_tokens':resources['total_input_tokens']=31999
    else:resources['total_output_tokens']=2047
    budget,_,_=migrated(tmp_path,policy=policy,resource_policy=resources)
    with pytest.raises(ValueError,match='budget exhausted'):budget.run(kind,{'new':True},lambda:pytest.fail('no resource room'),questions=questions)
    assert budget.snapshot()['total_reserved_actions']==2


def test_concurrent_kinds_share_last_action_slot(tmp_path):
    policy=deepcopy(common.DEFAULT_POLICY);policy['total_actions']=3
    budget,_,_=migrated(tmp_path,policy=policy);barrier=threading.Barrier(2);executed=[]
    def attempt(kind):
        barrier.wait(timeout=5)
        try:
            budget.run(kind,{'new':kind},lambda:(executed.append(kind) or envelope(kind)))
            return 'completed'
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(attempt,['proposal','fit']))==['completed','rejected']
    assert len(executed)==1 and budget.snapshot()['total_reserved_actions']==3


def test_daily_change_does_not_reset_lifetime_cache_or_numeric_cap(tmp_path):
    now=[datetime(2026,10,20,tzinfo=timezone.utc)]
    policy=deepcopy(common.DEFAULT_POLICY);policy['total_actions']=3
    budget,_,_=migrated(tmp_path,policy=policy,clock=lambda:now[0])
    result=budget.run('proposal',{'new':True},lambda:envelope('proposal'));now[0]+=timedelta(days=1)
    assert budget.run('proposal',{'new':True},lambda:pytest.fail('cache'))['result']==result['result']
    with pytest.raises(ValueError,match='budget exhausted'):budget.run('fit',{'next':True},lambda:pytest.fail('lifetime exhausted'))
    assert budget.snapshot()['daily_reserved_actions']==0


@pytest.mark.parametrize('change',['unfinished','history','resource','foreign','extension'])
def test_migration_refuses_unfinished_or_corrupt_history_without_writing(tmp_path,change):
    budget,_,_=prepared(tmp_path)
    with sqlite3.connect(budget.path) as db:
        if change=='unfinished':
            db.execute("INSERT INTO coordinated_numeric_actions VALUES (?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                ('a'*64,'b'*64,'2026-10-21','reserved','2026-10-21T00:00:00+00:00'))
        elif change=='history':db.execute("UPDATE coordinated_actions SET payload_sha='bad' WHERE kind='fit'")
        elif change=='resource':db.execute('DELETE FROM coordinated_resources')
        elif change=='foreign':db.execute('CREATE TABLE foreign_data(x INTEGER)')
        else:db.execute("UPDATE coordinated_numeric_extension SET sha='bad'")
    raw=budget.path.read_bytes()
    with pytest.raises(ValueError):budget.migrate()
    assert budget.path.read_bytes()==raw


@pytest.mark.parametrize('change',['prior_row','prior_policy','phase_policy','phase_hash','phase_allocation','phase_result','phase_observed','phase_measurement','orphan_resource','view'])
def test_immutable_old_history_and_new_accounting_corruption_are_detected(tmp_path,change):
    budget,_,_=migrated(tmp_path);budget.run('proposal',{'new':True},lambda:envelope('proposal'))
    with sqlite3.connect(budget.path) as db:
        if change=='prior_row':db.execute("UPDATE coordinated_actions SET input_sha='bad' WHERE kind='fit'")
        elif change=='prior_policy':db.execute("UPDATE coordinated_resource_policy SET payload='{}'")
        elif change=='phase_policy':
            payload=json.loads(db.execute('SELECT payload FROM coordinated_phase_extension').fetchone()[0]);payload['configuration']['policy']['new_limits_or_refunds']=True
            db.execute('UPDATE coordinated_phase_extension SET payload=?,sha=?',(canonical(payload),digest(payload)))
        elif change=='phase_hash':db.execute("UPDATE coordinated_phase_extension SET sha='bad'")
        elif change=='phase_allocation':db.execute("UPDATE coordinated_phase_resources SET allocation='{}'")
        elif change=='phase_result':db.execute("UPDATE coordinated_phase_actions SET payload='{}'")
        elif change=='phase_observed':db.execute("UPDATE coordinated_phase_actions SET observed='{}'")
        elif change=='phase_measurement':db.execute("UPDATE coordinated_phase_resources SET measurement='{}'")
        elif change=='orphan_resource':db.execute("INSERT INTO coordinated_phase_resources VALUES ('foreign','{}','bad',NULL,NULL)")
        else:db.execute('CREATE VIEW extra AS SELECT 1')
    raw=budget.path.read_bytes()
    with pytest.raises(ValueError):budget.snapshot()
    assert raw==budget.path.read_bytes()


def test_phase_does_not_create_missing_database_or_implicitly_migrate(tmp_path):
    previous,preview,selected=numeric_setup(tmp_path)
    budget=phase.ResearchPhaseBudget(previous,phase.POLICY)
    with pytest.raises(ValueError,match='migration'):budget.snapshot()
    with pytest.raises(ValueError):budget.run('fit',{},lambda:pytest.fail('not migrated'))


def test_full_coordinator_reuses_pre_phase_fit_cache_and_resumes_fixed_handlers(tmp_path):
    dataset,proposal=inputs(tmp_path)
    protocol=freeze_protocol(dataset,version='phase-synthetic-v1',epochs=3)
    bound=bindings(tmp_path)
    kwargs={'proposal_ledger':bound['proposal'],'semantic_ledger':bound['semantic_fixture'],'fit_ledger':bound['fit']}
    old=coordinator.ResearchCoordinator(tmp_path/'common.sqlite',**kwargs)
    original=old.fit(dataset,protocol)
    semantic={'semantic_live_ledger':tmp_path/'live.sqlite','semantic_live_policy':DEFAULT_SEMANTIC_POLICY}
    v2=common.ResearchRunBudget(old.budget.path,bound,**semantic);v2.migrate_semantic_budget()
    v3=common.ResearchRunBudget(v2.path,bound,**semantic,code_check_policy=code.POLICY);code.migrate(v3)
    v4=numeric.NumericControlBudget(v3,numeric.POLICY);v4.migrate()
    research=phase.PhaseResearchCoordinator(v3.path,**kwargs,**semantic,code_check_policy=code.POLICY,phase_policy=phase.POLICY)
    research.budget.migrate()
    cached=research.fit(dataset,protocol)
    assert cached['coordinator_cached'] and cached['cache_origin']=='v3' and cached['result']==original['result']
    report=original['result']['reports']['validation']['diagnostics']
    advice=research.propose(report,mock=proposal)
    candidate=research.fit(dataset,protocol,proposal=advice['result']['advice']['proposal'],report=report)
    assert candidate['result']['artifact']['production_compatible'] is False
    assert not advice['coordinator_cached']
    status=research.budget.snapshot()
    assert status['reserved_by_kind']=={'fit':2,'proposal':1} and status['total_reserved_actions']==3
    assert status['observed_completed_work']['numeric_fits']==2
    assert not bound['proposal'].exists()


def test_cli_migration_status_and_completed_code_cache_are_private_and_exclusive(tmp_path):
    budget,preview,selected=prepared(tmp_path)
    paths={}
    for name,value in [('semantic',budget.semantic_policy),('code',code.POLICY),('numeric',numeric.POLICY),('phase',phase.POLICY)]:
        path=tmp_path/(name+'.json');path.write_text(canonical(value));paths[name]=path
    bound=bindings(tmp_path)
    args=['--database',str(budget.path),'--proposal-ledger',str(bound['proposal']),
        '--semantic-ledger',str(bound['semantic_fixture']),'--fit-ledger',str(bound['fit']),
        '--semantic-live-ledger',str(tmp_path/'live.sqlite'),'--semantic-live-policy',str(paths['semantic']),
        '--code-policy',str(paths['code']),'--numeric-policy',str(paths['numeric']),'--phase-policy',str(paths['phase'])]
    output=tmp_path/'migration.json'
    assert phase.main([*args,'--output',str(output),'migrate'])==0
    assert output.stat().st_mode&0o777==0o600
    assert json.loads(output.read_text())['status']=='completed'
    cached=tmp_path/'cached.json'
    assert phase.main([*args,'--output',str(cached),'code-check','--preview',str(preview)])==0
    assert json.loads(cached.read_text())['call']['coordinator_cached']
    with pytest.raises(FileExistsError):phase.main([*args,'--output',str(output),'status'])
    with pytest.raises(SystemExit):phase.main([*args,'--output',str(paths['phase']),'status'])


def test_phase_migration_rolls_back_ddl_when_final_validation_fails(tmp_path,monkeypatch):
    budget,_,_=prepared(tmp_path);raw=budget.path.read_bytes()
    monkeypatch.setattr(budget,'_check',lambda db:(_ for _ in ()).throw(ValueError('injected final check failure')))
    with pytest.raises(ValueError):budget.migrate()
    assert budget.path.read_bytes()==raw
    with sqlite3.connect(budget.path) as db:assert numeric._objects(db)=={('table',name) for name in numeric.TABLES}


@pytest.mark.parametrize('name',['policy','resource_policy','semantic_policy','code_policy'])
def test_inherited_limits_cannot_be_mutated_in_memory_after_migration(tmp_path,name):
    budget,_,_=migrated(tmp_path)
    replacement=deepcopy(getattr(budget,name))
    if name=='policy':replacement['total_actions']+=1
    elif name=='resource_policy':replacement['total_wall_ms']+=1
    else:replacement['maximum_actions']+=1
    setattr(budget,name,replacement)
    with pytest.raises(ValueError,match='inherited'):budget.snapshot()


def test_phase_source_change_is_rejected_before_handler_or_new_row(tmp_path,monkeypatch):
    budget,_,_=migrated(tmp_path);raw=budget.path.read_bytes()
    monkeypatch.setattr(phase,'implementation',lambda:{'changed':True})
    with pytest.raises(ValueError,match='source'):budget.run('proposal',{},lambda:pytest.fail('source changed'))
    assert raw==budget.path.read_bytes()


def test_post_migration_database_copy_cannot_be_used_at_a_new_common_path(tmp_path):
    budget,_,_=migrated(tmp_path)
    copied=tmp_path/'copied.sqlite';copied.write_bytes(budget.path.read_bytes())
    original=budget.legacy
    base=common.ResearchRunBudget(copied,bindings(tmp_path),semantic_live_ledger=tmp_path/'live.sqlite',
        semantic_live_policy=original.semantic_policy,code_check_policy=code.POLICY)
    other=phase.ResearchPhaseBudget(numeric.NumericControlBudget(base,numeric.POLICY),phase.POLICY)
    with pytest.raises(ValueError,match='configuration'):other.snapshot()


def test_prior_semantic_questions_and_kind_count_are_not_reset(tmp_path):
    from test_research_numeric_controls import setup
    policy=deepcopy(common.DEFAULT_POLICY);policy['semantic_questions']=4
    previous,_,_=setup(tmp_path,policy=policy)
    previous.legacy.run('semantic_live',{'old':True},lambda:{'result':{},'observed':dict(common.ZERO_USAGE)},questions=3)
    previous.migrate();budget=phase.ResearchPhaseBudget(previous,phase.POLICY);budget.migrate()
    with pytest.raises(ValueError,match='question budget'):budget.run('semantic_live',{'next':True},lambda:pytest.fail('questions exhausted'),questions=2)
    assert budget.snapshot()['reserved_semantic_questions']==3


def test_all_three_old_numeric_actions_count_in_shared_cap_and_remain_immutable(tmp_path,monkeypatch):
    policy=deepcopy(common.DEFAULT_POLICY);policy['total_actions']=6
    previous,preview,selected=numeric_migrated(tmp_path,policy=policy)
    monkeypatch.setattr(worker,'run',fake_worker)
    for bars in (1,2,3):
        directory=tmp_path/('numeric'+str(bars));windows.stage_window(directory,capture(),request(bars=bars),windows.POLICY)
        previous.check(preview,directory,capture())
    with sqlite3.connect(previous.legacy.path) as db:old=phase._history(db)
    budget=phase.ResearchPhaseBudget(previous,phase.POLICY);budget.migrate()
    assert budget.snapshot()['total_reserved_actions']==5 and budget.snapshot()['numeric_control_lifetime_used']==3
    budget.run('proposal',{'new':True},lambda:envelope('proposal'))
    with pytest.raises(ValueError,match='action budget'):budget.run('fit',{'new':True},lambda:pytest.fail('all six spent'))
    with sqlite3.connect(budget.path) as db:assert phase._history(db)==old


def test_cancellation_before_and_after_reservation_has_correct_charging(tmp_path):
    budget,_,_=migrated(tmp_path);event=threading.Event();event.set()
    with pytest.raises(common.BudgetCancelled):budget.run('fit',{},lambda:pytest.fail('pre-cancelled'),cancel_event=event)
    assert budget.snapshot()['total_reserved_actions']==2
    class Event:
        calls=0
        def is_set(self):self.calls+=1;return self.calls>=3
    with pytest.raises(common.BudgetCancelled):budget.run('fit',{},lambda:pytest.fail('post-cancelled'),cancel_event=Event())
    assert budget.snapshot()['statuses']['cancelled']==1


def test_prior_measurement_overrun_blocks_fresh_work_but_preserves_cache(tmp_path):
    budget,_,_=migrated(tmp_path)
    clock=iter([0,66_000_000_000]);budget.timer=lambda:next(clock)
    first=budget.run('proposal',{'slow':True},lambda:envelope('proposal'))
    assert first['original_resources']['handler_wall_ms']==66000
    assert budget.snapshot()['resources']['overrun_actions']==1
    with pytest.raises(ValueError,match='overrun'):budget.run('fit',{'fresh':True},lambda:pytest.fail('prior overrun'))
    assert budget.run('proposal',{'slow':True},lambda:pytest.fail('cache after overrun'))['coordinator_cached']


def test_static_review_reads_both_old_and_new_completed_preview_registrations(tmp_path):
    from test_research_code_static import bundle,source
    from cryptoforge import research_code_static as static
    budget,preview,selected=migrated(tmp_path)
    old=budget.static_review(preview,static.POLICY)
    assert old['cache_origin']=='v3' and old['analysis']['verdict']=='passed_static_contract'
    fresh=bundle(tmp_path,'new_preview',candidate=source('2.0'))
    with pytest.raises(ValueError,match='registration'):budget.static_review(fresh,static.POLICY)
    code.check_preview(budget,fresh);raw=budget.path.read_bytes()
    new=budget.static_review(fresh,static.POLICY)
    assert new['cache_origin']=='v5' and new['analysis']['verdict']=='passed_static_contract'
    assert new['new_actions']==0 and new['candidate_execution_enabled'] is False
    assert budget.path.read_bytes()==raw


def test_phase_policy_snapshot_cannot_add_caps_or_enable_runtime(tmp_path):
    budget,_,_=prepared(tmp_path);policy=deepcopy(phase.POLICY)
    policy['new_limits_or_refunds']=True
    with pytest.raises(ValueError):phase.ResearchPhaseBudget(budget.previous,policy)
    policy=deepcopy(phase.POLICY);policy['maximum_actions']=100
    with pytest.raises(ValueError):phase.ResearchPhaseBudget(budget.previous,policy)


@pytest.mark.parametrize('name',['manifest','semantic_configuration','code_configuration'])
def test_identity_configuration_cannot_be_rebound_to_retry_an_old_effect(tmp_path,name):
    budget,_,_=migrated(tmp_path);replacement=deepcopy(getattr(budget,name));replacement['changed']=True
    setattr(budget,name,replacement)
    with pytest.raises(ValueError,match='identity configuration'):budget.run('fit',{'initial':True},lambda:pytest.fail('rebound identity'))
