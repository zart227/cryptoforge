from datetime import timedelta

import pytest

from cryptoforge.paired_cached_coordinator import PairedCachedCoordinator,PairedCoordinatorPolicy
from cryptoforge.local_source_provenance import canonical,parse,stamp
from cryptoforge.reference_delivery import ROLES
from test_reference_source_ledger import Clock,Client
from test_cash_worker_application import PositiveClient,rules
from test_paper_wallet import config
from test_native_paper_archive_v2 import WORKER_POLICY
from test_paper_valuation_capture import raw_market

ENV=dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='synthetic-not-saved')


def setup(tmp_path,**changes):
    clock=Clock();values=dict(start=clock()+timedelta(seconds=1),end=clock()+timedelta(seconds=21),rules=rules(),
        configs={r:config() for r in ROLES},worker_policy=WORKER_POLICY,closeout_seconds=5,backend_env=ENV,
        clock=clock,market=lambda pair:raw_market(clock,pair))
    values.update(changes);return PairedCachedCoordinator.create(tmp_path/'runner',**values),clock


@pytest.mark.parametrize('positive',[False,True])
def test_complete_coordinator_uses_cached_apps_and_seals_independent_proofs(tmp_path,positive):
    runner,clock=setup(tmp_path)
    result=runner.run(client=PositiveClient(clock) if positive else Client(clock),market=lambda pair:raw_market(clock,pair),sleeper=clock.advance)
    assert result['status']=='completed' and result['ticks_by_role']==dict.fromkeys(ROLES,4)
    assert result['missed_slots_by_role']==dict.fromkeys(ROLES,0)
    assert runner.reference['sequence']==44 and runner.progress['done']
    assert runner.audit()['full_journal_integrity_pass']
    for role in ROLES:
        replay=parse((runner.root/'results'/result['results'][role]['name']).read_bytes())
        assert replay['full_worker_decision_replay_pass'] and replay['full_fifo_replay_pass']
        assert replay['fills_checked']==(2 if positive and role!='control' else 0)
    proof=parse((runner.root/'results'/'final-proof.json').read_bytes())
    assert all(proof['applications'][r]['reader_proof_full_audit_pass'] for r in ROLES)
    assert all(result[k] is False for k in ('full_worker_or_host_qualified','paper_evidence_pass','economic_profitability_established','live_admission_granted'))


def test_each_completed_operation_can_be_reopened_before_original_end(tmp_path):
    runner,clock=setup(tmp_path);clock.advance(1);client=Client(clock)
    for _ in range(6):
        result=runner.step(client=client,market=lambda pair:raw_market(clock,pair))
        runner=PairedCachedCoordinator.open(result['reference'],clock=clock)
    assert runner.progress['ticks']==dict.fromkeys(ROLES,1) and runner.reference['sequence']==12
    assert len(client.calls)==2
    state=runner.inspect();assert state['performance_hidden'] and not state['results']
    assert runner.audit()['full_journal_integrity_pass'] is False
    completed=runner.run(client=client,market=lambda pair:raw_market(clock,pair),sleeper=clock.advance)
    assert completed['ticks_by_role']==dict.fromkeys(ROLES,4)


def test_pending_source_effect_is_visible_and_never_automatically_retried(tmp_path,monkeypatch):
    runner,clock=setup(tmp_path);known=dict(runner.reference);clock.advance(1)
    from cryptoforge.reference_source_ledger import ReferenceLedger
    def fail(*a,**k):raise OSError('unknown source commit')
    monkeypatch.setattr(ReferenceLedger,'poll',fail)
    with pytest.raises(OSError):runner.step(client=Client(clock))
    assert runner.inspect()['pending_operation']=='source_poll'
    observed=PairedCachedCoordinator.inspect_reference(known,clock=clock)
    assert observed['read_only'] and observed['pending_operation']=='source_poll' and not observed['checkpoint_adopted']
    with pytest.raises(ValueError,match='pending'):runner.step(client=Client(clock))
    with pytest.raises(ValueError,match='remains blocked'):PairedCachedCoordinator.recover(known,clock=clock)


def test_known_completed_tick_is_reconciled_without_rerunning_worker(tmp_path,monkeypatch):
    runner,clock=setup(tmp_path);clock.advance(1);client=PositiveClient(clock);market=lambda pair:raw_market(clock,pair)
    for _ in range(3):runner.step(client=client,market=market)
    known=parse(canonical(runner.reference));append=runner._append
    def fail(phase,op,*a,**k):
        if phase=='completed' and op=='tick':raise OSError('lost outer completion after actual worker')
        return append(phase,op,*a,**k)
    monkeypatch.setattr(runner,'_append',fail)
    with pytest.raises(OSError):runner.step(client=client,market=market)
    monkeypatch.setattr(runner,'_append',append)
    assert runner.inspect()['pending_operation']=='tick'
    result=PairedCachedCoordinator.recover(known,clock=clock)
    assert not result['worker_execution_repeated'] and result['provider_calls']==0
    recovered=PairedCachedCoordinator.open(result['reference'],clock=clock)
    assert recovered.progress['ticks']==dict(candidate=1,control=0,stress=0)
    assert stamp(recovered.progress['market_pause_until'])>=clock()+timedelta(seconds=599)
    final=recovered.run(client=client,market=market,sleeper=clock.advance)
    assert final['ticks_by_role']==dict.fromkeys(ROLES,4) and recovered.audit()['full_journal_integrity_pass']


def prepare_tick(runner,clock):
    clock.advance(1);client=PositiveClient(clock);market=lambda pair:raw_market(clock,pair)
    for _ in range(3):runner.step(client=client,market=market)
    return client,market


def test_completed_checkpoint_recovery_never_calls_worker_or_provider(tmp_path,monkeypatch):
    runner,clock=setup(tmp_path);known=parse(canonical(runner.reference));client,market=prepare_tick(runner,clock)
    runner.step(client=client,market=market);current=parse(canonical(runner.reference))
    from cryptoforge.cached_cash_application_v3 import CachedCashApplicationV3
    def forbidden(*a,**k):pytest.fail('completed checkpoint recovery repeated execution')
    monkeypatch.setattr(CachedCashApplicationV3,'apply',forbidden)
    with pytest.raises(ValueError,match='stale'):PairedCachedCoordinator.open(known,clock=clock)
    before=(runner.root/'journal.sqlite').read_bytes()
    result=PairedCachedCoordinator.recover(known,clock=clock)
    assert result['reference']==current and not result['worker_execution_repeated'] and result['provider_calls']==0
    assert (runner.root/'journal.sqlite').read_bytes()==before and len(client.calls)==2


def test_real_process_exit_after_tick_commit_can_be_explicitly_reconciled(tmp_path,monkeypatch):
    import os
    runner,clock=setup(tmp_path);client,market=prepare_tick(runner,clock);known=parse(canonical(runner.reference))
    pid=os.fork()
    if pid==0:
        append=runner._append
        def die(phase,op,*a,**k):
            if phase=='completed' and op=='tick':os._exit(42)
            return append(phase,op,*a,**k)
        runner._append=die
        runner.step(client=client,market=market)
        os._exit(99)
    _,status=os.waitpid(pid,0);assert os.waitstatus_to_exitcode(status)==42
    from cryptoforge.cached_cash_application_v3 import CachedCashApplicationV3
    def forbidden(*a,**k):pytest.fail('dead process tick was repeated')
    with monkeypatch.context() as patch:
        patch.setattr(CachedCashApplicationV3,'apply',forbidden)
        result=PairedCachedCoordinator.recover(known,clock=clock)
    restored=PairedCachedCoordinator.open(result['reference'],clock=clock)
    assert restored.progress['ticks']==dict(candidate=1,control=0,stress=0)
    assert restored.components['applications']['candidate']['application_reference']['sequence']==1
    restored.step(client=client,market=market,maximum_operations=2)
    assert restored.progress['ticks']==dict.fromkeys(ROLES,1)


def test_pending_tick_without_durable_worker_result_stays_blocked(tmp_path,monkeypatch):
    from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
    runner,clock=setup(tmp_path);client,market=prepare_tick(runner,clock);known=parse(canonical(runner.reference))
    def fail(*a,**k):raise RuntimeError('worker effect not known')
    monkeypatch.setattr(CapturedPaperWorkerV2,'tick',fail)
    with pytest.raises(RuntimeError):runner.step(client=client,market=market)
    before=(runner.root/'journal.sqlite').read_bytes()
    with pytest.raises(ValueError):PairedCachedCoordinator.recover(known,clock=clock)
    assert (runner.root/'journal.sqlite').read_bytes()==before and runner.inspect()['pending_operation']=='tick'


def test_recovery_rejects_foreign_worker_advance_without_repeating_it(tmp_path):
    runner,clock=setup(tmp_path);client,market=prepare_tick(runner,clock);known=parse(canonical(runner.reference))
    runner.step(client=client,market=market);context=runner._context(market)
    context['applications']['stress'].apply(context['queue'],context['workers']['stress'],runner.components['prefix'])
    before=(runner.root/'journal.sqlite').read_bytes()
    with pytest.raises(ValueError):PairedCachedCoordinator.recover(known,clock=clock)
    assert (runner.root/'journal.sqlite').read_bytes()==before


@pytest.mark.parametrize('fault',['past','long','far','cloud','shared_exit','records','bytes'])
def test_invalid_registration_is_rejected_before_creating_root(tmp_path,fault):
    clock=Clock();changes={}
    if fault=='past':changes['start']=clock()-timedelta(seconds=1)
    if fault=='long':changes['end']=clock()+timedelta(seconds=302)
    if fault=='far':changes.update(start=clock()+timedelta(seconds=61),end=clock()+timedelta(seconds=81))
    if fault=='cloud':changes['backend_env']=dict(CRYPTOFORGE_BACKEND='supabase')
    if fault=='shared_exit':changes['worker_policy']=dict(WORKER_POLICY,exits=dict(WORKER_POLICY['exits'],shared_exit_signal=True))
    if fault=='records':changes['policy']=PairedCoordinatorPolicy(maximum_journal_records=32)
    if fault=='bytes':changes['policy']=PairedCoordinatorPolicy(maximum_journal_bytes=1024**2)
    with pytest.raises(ValueError):setup(tmp_path,**changes)
    assert not (tmp_path/'runner').exists()


def test_journal_reserve_and_busy_lease_stop_before_source_effect(tmp_path,monkeypatch):
    import fcntl,sqlite3
    runner,clock=setup(tmp_path);clock.advance(1)
    def forbidden(*a,**k):pytest.fail('source effect ran without journal capacity or exclusive lease')
    from cryptoforge.reference_source_ledger import ReferenceLedger
    monkeypatch.setattr(ReferenceLedger,'poll',forbidden)
    with (runner.root/'writer.lock').open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):runner.step(client=Client(clock))
    with sqlite3.connect(runner.root/'journal.sqlite') as db:
        db.execute('PRAGMA page_size=4096');db.execute('VACUUM')
        db.execute('CREATE TABLE reserve(blob)');db.execute('INSERT INTO reserve VALUES (zeroblob(?))',(runner.policy.maximum_journal_bytes-256*1024,));db.commit()
        db.execute('DROP TABLE reserve');db.commit()
    with pytest.raises(ValueError,match='reserve'):runner.step(client=Client(clock))
    assert runner.reference['sequence']==0


def test_worker_start_time_assigns_actual_slot_and_records_missed_intervals(tmp_path,monkeypatch):
    from cryptoforge.cached_reference_reader_v2 import CachedReferenceReaderV2
    runner,clock=setup(tmp_path);client,market=prepare_tick(runner,clock);read=CachedReferenceReaderV2.read
    def slow(self,*a,**k):
        value=read(self,*a,**k);clock.advance(6);return value
    with monkeypatch.context() as patch:
        patch.setattr(CachedReferenceReaderV2,'read',slow)
        runner.step(client=client,market=market)
    assert runner.progress['role_slots']['candidate']==1 and runner.progress['missed_slots']['candidate']==1
    runner.step(client=client,market=market,maximum_operations=2)
    assert runner.progress['ticks']==dict.fromkeys(ROLES,1)
    runner.step(client=client,market=market)
    assert runner.progress['ticks']==dict.fromkeys(ROLES,1)


def test_market_cooldown_survives_exact_checkpoint_reopen(tmp_path,monkeypatch):
    import time
    from cryptoforge.paired_cash_rehearsal import BoundedPaperPublicClient
    runner,clock=setup(tmp_path);client,market=prepare_tick(runner,clock)
    runner.public=BoundedPaperPublicClient();runner.public.paused_until=time.monotonic()+500
    runner.step(client=client,market=market);pause=runner.progress['market_pause_until']
    reopened=PairedCachedCoordinator.open(runner.reference,clock=clock)
    import cryptoforge.paired_cached_coordinator as module
    calls=[]
    def observed(public,pair):
        calls.append(pair);assert public.paused_until>time.monotonic()+490
        return raw_market(clock,pair)
    monkeypatch.setattr(module,'observe_valuation_market',observed)
    reopened.step(client=client,maximum_operations=2)
    assert reopened.public.paused_until>time.monotonic()+490 and reopened.progress['market_pause_until']>=pause


def test_calendar_first_metadata_does_not_open_worker_or_replay_outcomes(tmp_path,monkeypatch):
    runner,clock=setup(tmp_path);prepare_tick(runner,clock)
    def forbidden(*a,**k):pytest.fail('unfinished inspection accessed worker outcomes')
    monkeypatch.setattr(runner,'_validate_components',forbidden);monkeypatch.setattr(runner,'_full',forbidden)
    assert runner.inspect()['performance_hidden'] and runner.audit()['performance_hidden']
    assert runner.audit()['full_journal_integrity_pass'] is False


def test_source_phase_resumes_exactly_and_incomplete_pipeline_cannot_finalize(tmp_path):
    runner,clock=setup(tmp_path);clock.advance(1);client=Client(clock)
    runner.step(client=client);assert runner.progress['source_work']=='prefix'
    runner=PairedCachedCoordinator.open(runner.reference,clock=clock);runner.step(client=client)
    assert runner.progress['source_work']=='queue' and len(client.calls)==2
    clock.now=stamp(runner.manifest['end']);before=(runner.root/'journal.sqlite').read_bytes()
    with pytest.raises(ValueError,match='incomplete'):runner.step(client=client)
    assert (runner.root/'journal.sqlite').read_bytes()==before


def test_full_audit_detects_cold_corruption_and_bounded_projection(tmp_path):
    import sqlite3
    from cryptoforge.paired_cached_coordinator import SQL
    runner,clock=setup(tmp_path);prepare_tick(runner,clock)
    with sqlite3.connect(runner.root/'journal.sqlite') as db:
        db.execute('DROP TRIGGER no_update');db.execute('UPDATE events SET payload=zeroblob(length(payload)) WHERE seq=1')
        db.execute(SQL['no_update']);db.commit()
    assert runner.inspect()['status']=='ready'
    clock.now=stamp(runner.manifest['end'])
    with pytest.raises((ValueError,UnicodeDecodeError)):runner.audit()
    with sqlite3.connect(runner.root/'journal.sqlite') as db:
        db.execute('UPDATE state SET progress=zeroblob(?)',(runner.policy.maximum_record_bytes+1,));db.commit()
    with pytest.raises(ValueError,match='bounded'):runner.inspect()
