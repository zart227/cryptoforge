from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
import threading

import pytest

from cryptoforge.research_run_budget import ResearchRunBudget, DEFAULT_POLICY, ZERO_USAGE, BudgetCancelled, BudgetTimedOut


def bindings(tmp_path):
    return {kind: tmp_path/(kind+'.sqlite') for kind in ('proposal','semantic_fixture','fit')}


def policy(**changes):
    return {**DEFAULT_POLICY, **changes}


def envelope(kind, *, actual=False):
    observed = dict(ZERO_USAGE)
    if actual: observed[{'proposal':'remote_completions','semantic_fixture':'fixture_workers','fit':'numeric_fits'}[kind]] = 1
    return {'result': {'example_origin':'synthetic_fixture'}, 'observed':observed}


def test_all_three_kinds_consume_one_common_limit(tmp_path):
    budget = ResearchRunBudget(tmp_path/'common.sqlite', bindings(tmp_path), policy=policy(total_actions=3))
    for kind in ('proposal','fit','semantic_fixture'):
        budget.run(kind, {'id':kind}, lambda: envelope(kind), questions=2 if kind=='semantic_fixture' else 0)
    called=[]
    with pytest.raises(ValueError,match='common research action budget'):
        budget.run('fit', {'id':'fourth'}, lambda: called.append(True))
    snapshot=budget.snapshot()
    assert snapshot['total_reserved_actions']==3 and snapshot['reserved_semantic_questions']==2
    assert snapshot['reserved_by_kind']=={'proposal':1,'fit':1,'semantic_fixture':1}
    assert snapshot['observed_completed_work']==ZERO_USAGE and called==[]
    assert all(not path.exists() for path in bindings(tmp_path).values())


def test_cached_result_keeps_original_usage_but_invocation_does_no_work(tmp_path):
    path=tmp_path/'common.sqlite'; limits=policy(total_actions=1)
    calls=[]
    def operation(): calls.append(1); return envelope('fit',actual=True)
    first=ResearchRunBudget(path,bindings(tmp_path),policy=limits).run('fit',{'config':'one'},operation)
    repeat=ResearchRunBudget(path,bindings(tmp_path),policy=limits).run('fit',{'config':'one'},operation)
    assert not first['coordinator_cached'] and repeat['coordinator_cached']
    assert repeat['original_observed']['numeric_fits']==1 and repeat['invocation_observed']==ZERO_USAGE
    assert repeat['operation_key']==first['operation_key'] and len(calls)==1
    assert path.stat().st_mode & 0o777==0o600


def test_daily_reset_does_not_reset_lifetime_cap(tmp_path):
    path=tmp_path/'common.sqlite'; limits=policy(daily_actions=1,total_actions=2)
    day=datetime(2025,1,1,23,tzinfo=timezone(timedelta(hours=-3)))
    first=ResearchRunBudget(path,bindings(tmp_path),policy=limits,clock=lambda:day)
    first.run('proposal',{'id':0},lambda:envelope('proposal'))
    assert first.snapshot()['utc_day']=='2025-01-02'
    with pytest.raises(ValueError): first.run('fit',{'id':1},lambda:envelope('fit'))
    second=ResearchRunBudget(path,bindings(tmp_path),policy=limits,clock=lambda:day+timedelta(days=1))
    second.run('fit',{'id':1},lambda:envelope('fit'))
    later=ResearchRunBudget(path,bindings(tmp_path),policy=limits,clock=lambda:day+timedelta(days=2))
    with pytest.raises(ValueError): later.run('proposal',{'id':2},lambda:envelope('proposal'))
    assert later.snapshot()['total_reserved_actions']==2


def test_per_kind_and_semantic_question_caps_are_independent(tmp_path):
    limits=policy(maximum_by_kind={'proposal':0,'fit':2,'semantic_fixture':2},semantic_questions=3)
    budget=ResearchRunBudget(tmp_path/'common.sqlite',bindings(tmp_path),policy=limits)
    with pytest.raises(ValueError,match='kind or question'): budget.run('proposal',{},lambda:envelope('proposal'))
    budget.run('semantic_fixture',{'id':1},lambda:envelope('semantic_fixture'),questions=2)
    with pytest.raises(ValueError,match='kind or question'):
        budget.run('semantic_fixture',{'id':2},lambda:envelope('semantic_fixture'),questions=2)
    budget.run('fit',{},lambda:envelope('fit'))
    assert budget.snapshot()['total_reserved_actions']==2


def test_denied_first_admission_still_freezes_policy_and_bindings(tmp_path):
    path=tmp_path/'common.sqlite'
    limits=policy(maximum_by_kind={'proposal':0,'fit':1,'semantic_fixture':1})
    with pytest.raises(ValueError,match='kind or question'):
        ResearchRunBudget(path,bindings(tmp_path),policy=limits).run('proposal',{},lambda:envelope('proposal'))
    with pytest.raises(ValueError,match='policy or journal bindings changed'):
        ResearchRunBudget(path,bindings(tmp_path)).run('proposal',{},lambda:envelope('proposal'))
    changed={**bindings(tmp_path),'fit':tmp_path/'new-fit.sqlite'}
    with pytest.raises(ValueError,match='policy or journal bindings changed'):
        ResearchRunBudget(path,changed,policy=limits).run('fit',{},lambda:envelope('fit'))


@pytest.mark.parametrize('exception,status',[(RuntimeError,'failed'),(BudgetCancelled,'cancelled'),(BudgetTimedOut,'timed_out'),(SystemExit,'reserved')])
def test_failed_cancelled_timed_out_or_crashed_actions_remain_charged(tmp_path,exception,status):
    path=tmp_path/'common.sqlite'
    budget=ResearchRunBudget(path,bindings(tmp_path))
    def fail(): raise exception('private error content')
    with pytest.raises((RuntimeError,SystemExit)): budget.run('proposal',{},fail)
    assert budget.snapshot()['statuses']=={status:1}
    assert budget.snapshot()['unknown_work_attempts']==1
    assert budget.snapshot()['observed_completed_work']==ZERO_USAGE
    with pytest.raises(ValueError,match='no automatic retry'):
        ResearchRunBudget(path,bindings(tmp_path)).run('proposal',{},lambda:envelope('proposal'))
    with sqlite3.connect(path) as db: saved=repr(db.execute('SELECT * FROM coordinated_actions').fetchall())
    assert 'private error content' not in saved


def test_mixed_concurrent_kinds_cannot_both_take_last_common_slot(tmp_path):
    path=tmp_path/'common.sqlite'; limits=policy(total_actions=1)
    barrier=threading.Barrier(2); executed=[]
    def attempt(kind):
        barrier.wait(timeout=5)
        def operation(): executed.append(kind); return envelope(kind)
        try:
            ResearchRunBudget(path,bindings(tmp_path),policy=limits).run(kind,{'kind':kind},operation)
            return 'completed'
        except ValueError as error:
            assert 'common research action budget' in str(error)
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks=[pool.submit(attempt,kind) for kind in ('proposal','fit')]
        assert sorted(t.result(timeout=5) for t in tasks)==['completed','rejected']
    assert len(executed)==1


def test_cache_and_observed_summary_corruption_are_detected(tmp_path):
    path=tmp_path/'common.sqlite'; budget=ResearchRunBudget(path,bindings(tmp_path))
    budget.run('fit',{},lambda:envelope('fit',actual=True))
    with sqlite3.connect(path) as db: db.execute("UPDATE coordinated_actions SET payload='{}'")
    with pytest.raises(ValueError,match='checksum'): budget.run('fit',{},lambda:envelope('fit'))
    with sqlite3.connect(path) as db: db.execute("UPDATE coordinated_actions SET observed='{}'")
    with pytest.raises(ValueError): budget.snapshot()


def test_read_only_snapshot_and_foreign_ledger_permissions(tmp_path):
    path=tmp_path/'common.sqlite'; budget=ResearchRunBudget(path,bindings(tmp_path))
    with pytest.raises(ValueError,match='existing'): budget.snapshot()
    assert not path.exists()
    budget.run('fit',{},lambda:envelope('fit'))
    before=path.read_bytes(); budget.snapshot(); assert path.read_bytes()==before
    other=tmp_path/'foreign.sqlite'
    with sqlite3.connect(other) as db: db.execute('CREATE TABLE studies (id TEXT)')
    other.chmod(0o640); before=other.read_bytes()
    with pytest.raises(ValueError,match='separate database'):
        ResearchRunBudget(other,bindings(tmp_path)).run('fit',{},lambda:envelope('fit'))
    assert other.read_bytes()==before and other.stat().st_mode & 0o777==0o640


def test_pre_cancellation_creates_no_journal_and_unknown_usage_is_not_accepted(tmp_path):
    path=tmp_path/'common.sqlite'; budget=ResearchRunBudget(path,bindings(tmp_path))
    cancel=threading.Event(); cancel.set()
    with pytest.raises(BudgetCancelled): budget.run('fit',{},lambda:envelope('fit'),cancel_event=cancel)
    assert not path.exists()
    with pytest.raises(RuntimeError): budget.run('fit',{},lambda:envelope('proposal',actual=True))
    assert budget.snapshot()['statuses']=={'failed':1}


@pytest.mark.parametrize('changes',[{'free_only':False},{'daily_actions':True},{'semantic_questions':-1}])
def test_invalid_policies_and_overlapping_journals_are_refused(tmp_path,changes):
    with pytest.raises(ValueError): ResearchRunBudget(tmp_path/'common.sqlite',bindings(tmp_path),policy=policy(**changes))
    with pytest.raises(ValueError): ResearchRunBudget(tmp_path/'common.sqlite',{**bindings(tmp_path),'fit':tmp_path/'common.sqlite'})
    assert not (tmp_path/'common.sqlite').exists()
