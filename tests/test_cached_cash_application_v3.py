from datetime import timedelta

import pytest

from cryptoforge.cached_cash_application_v3 import CachedCashApplicationV3
from cryptoforge.cash_application_v2 import CashApplicationPolicyV2
from cryptoforge.cached_reference_reader_v2 import CachedReferenceReaderV2
from cryptoforge.reference_prefix_v2 import ReferencePrefixV2,PrefixPolicyV2
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy
from cryptoforge.reference_delivery import ReferenceDelivery,DeliveryPolicy,ROLES
from cryptoforge.cash_entry_contract import freeze_cash_contract,load_cash_contract
from cryptoforge.paper_producer_v2 import register_kernel
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from cryptoforge.paper_worker_replay_v2 import register_worker_replay,audit_worker_replay
from cryptoforge.local_source_provenance import canonical,digest,parse,stamp
from test_reference_source_ledger import Clock,Client
from test_cash_worker_application import PositiveClient,rules
from test_paper_capture_v3 import lifecycle,storage
from test_native_paper_archive_v2 import policy as native_policy,WORKER_POLICY
from test_paper_worker_capture_v2 import budgets
from test_paper_wallet import config
from test_paper_valuation_capture import raw_market
from test_paper_worker_replay_v2 import policy as replay_policy


def setup(tmp_path,*,policy=None,replays=False):
    clock=Clock();start=clock()+timedelta(seconds=60);end=start+timedelta(seconds=20)
    source=ReferenceLedger.create(tmp_path/'source',clock=clock,start=start,end=end,
        policy=ReferencePolicy(maximum_events=100,maximum_versions=1000,maximum_forecasts=1,maximum_database_bytes=4*1024**2))
    queue=ReferenceDelivery.create(tmp_path/'queue',source.receipt()['reference'],clock=clock,
        policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_source_events_per_batch=4))
    prefix=ReferencePrefixV2.create(tmp_path/'prefix',source.receipt()['reference'],clock=clock,
        policy=PrefixPolicyV2(maximum_database_bytes=32*1024**2))
    reader=CachedReferenceReaderV2.create(tmp_path/'reader',queue,prefix,clock=clock)
    cash=freeze_cash_contract(tmp_path/'cash',queue,rules=rules(),closeout_seconds=5,clock=clock);contract=load_cash_contract(cash)
    workers={};apps={};registered={}
    for role in ROLES:
        kernel=register_kernel(tmp_path/('kernel-'+role),candidate_sha=contract['strategies'][role],study_protocol_sha256=cash['contract_sha256'],role=role,
            config=config(),worker_policy=WORKER_POLICY,backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY':'synthetic'},
            start=start,end=end,closeout_seconds=5,clock=clock)
        worker=CapturedPaperWorkerV2.create(tmp_path/('worker-'+role),kernel_root=kernel['root'],expected_kernel_contract_sha256=kernel['contract_sha256'],
            expected_kernel_registration_sha256=kernel['registration_sha256'],lifecycle=lifecycle(maximum_operations_per_poll=1),
            storage_policy=storage(maximum_events=2048,maximum_segment_events=128,maximum_record_bytes=32768,maximum_total_bytes=16*1024**2),
            native_policy=native_policy(),capture_policy=budgets(),market=lambda pair:raw_market(clock,pair),clock=clock)
        workers[role]=worker;apps[role]=CachedCashApplicationV3.create(tmp_path/('application-v3-'+role),cash,queue,worker,reader,policy=policy,clock=clock)
        if replays:
            registered[role]=register_worker_replay(tmp_path/('replay-'+role),capture_root=worker.root,expected_registration_sha256=worker.registration_sha256,
                policy=replay_policy(),backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY':'synthetic'},clock=clock)
    clock.advance(60);return clock,source,queue,prefix,workers,apps,registered


def poll(clock,source,queue,prefix,*,positive=True):
    source.poll(PositiveClient(clock) if positive else Client(clock));ref=source.receipt()['reference']
    prefix.ingest(ref);queue.ingest(ref)


@pytest.mark.parametrize('role',ROLES)
def test_cached_packet_proof_is_bound_into_actual_worker_result_and_ack(tmp_path,monkeypatch,role):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    def forbidden(*a,**k):pytest.fail('legacy queue.read was used')
    monkeypatch.setattr(queue,'read',forbidden)
    app=apps[role];result=app.apply(queue,workers[role],prefix.reference)
    assert result['opportunity_count']==2 and result['positive_decisions']==(0 if role=='control' else 2)
    db=app.application._db()
    try:raw=app.application._row(app.application._read_row(db,1))
    finally:db.close()
    original=parse(raw['input.json']);proof=original['cached_reader_proof']
    assert proof['application_manifest_sha256']==app.reference['manifest_sha256']
    assert proof['packet_sha256']==digest(canonical(original['packet']))
    assert digest(raw['worker-result.json'])==result['worker_receipt_sha256']==parse(raw['ack.json'])['acknowledgement']['worker_receipt_sha256']
    assert parse(raw['worker-result.json'])['input_sha256']==digest(raw['input.json'])
    assert not list((app.application.root/'groups').iterdir())
    assert all(result[k] is False for k in ('full_worker_or_host_qualified','paper_evidence_pass','economic_profitability_established','live_admission_granted'))


def test_empty_tick_executes_pending_fills_without_new_opportunities_or_source_ack(tmp_path):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    app=apps['candidate'];app.apply(queue,workers['candidate'],prefix.reference);clock.advance(5)
    result=app.apply(queue,workers['candidate'],prefix.reference)
    assert result['worker_result']['fills_processed']==['filled','filled'] and result['worker_result']['new_intents']==0
    assert result['opportunity_count']==0 and queue.receipt()['role_cursors']['candidate']['cursor']==1


def test_v3_independent_controller_fifo_and_full_source_reader_proof_replay(tmp_path):
    clock,source,queue,prefix,workers,apps,replays=setup(tmp_path,replays=True);poll(clock,source,queue,prefix)
    for tick in range(4):
        if tick:
            clock.advance(5)
            if tick==2:
                for worker in workers.values():worker._market=lambda pair:raw_market(clock,pair,price='95')
        for role in ROLES:apps[role].apply(queue,workers[role],prefix.reference)
    clock.now=stamp(apps['candidate'].manifest['end'])
    for role in ROLES:
        worker=workers[role];quotes={};filters={}
        if role!='control':
            for pair in source.manifest['pairs']:quotes[pair],filters[pair]=raw_market(clock,pair,price='95')
        worker.mark_endpoint(quotes,filters);worker.terminate('completed');seal=worker.finalize()
        replay=audit_worker_replay(worker.root,expected_registration_sha256=worker.registration_sha256,expected_seal_sha256=seal['seal_sha256'],
            replay_root=replays[role]['root'],expected_replay_registration_sha256=replays[role]['replay_registration_sha256'],scratch_parent=tmp_path,clock=clock)
        assert replay['full_worker_decision_replay_pass'] and replay['full_fifo_replay_pass'] and replay['fills_checked']==(0 if role=='control' else 4)
        audit=apps[role].audit(queue)
        assert audit['reader_proof_full_audit_pass'] and audit['groups_checked']==4


def test_before_end_audit_keeps_results_hidden_and_never_replays_queue(tmp_path,monkeypatch):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    app=apps['candidate'];app.apply(queue,workers['candidate'],prefix.reference)
    def forbidden(*a,**k):pytest.fail('unfinished-window audit accessed payload or full queue')
    import cryptoforge.cash_application_v2 as archive
    monkeypatch.setattr(queue,'audit',forbidden);monkeypatch.setattr(archive,'_decode',forbidden)
    assert app.audit(queue)['performance_hidden'] is True


def test_unknown_worker_result_is_retained_and_cannot_be_retried(tmp_path,monkeypatch):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    app=apps['candidate'];known=dict(app.reference)
    def fail(*a,**k):raise RuntimeError('synthetic unknown worker effect')
    monkeypatch.setattr(workers['candidate'],'tick',fail)
    with pytest.raises(RuntimeError):app.apply(queue,workers['candidate'],prefix.reference)
    assert (app.application.root/'groups/00000001/worker-error.json').exists()
    before=queue.path.read_bytes()
    with pytest.raises(ValueError):CachedCashApplicationV3.open(known,clock=clock)
    with pytest.raises(ValueError):app.apply(queue,workers['candidate'],prefix.reference)
    assert queue.path.read_bytes()==before and queue.receipt()['role_cursors']['candidate']['cursor']==0


def test_stale_parent_checkpoint_cannot_adopt_committed_child(tmp_path):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    app=apps['candidate'];known=parse(canonical(app.reference));result=app.apply(queue,workers['candidate'],prefix.reference)
    with pytest.raises(ValueError):CachedCashApplicationV3.open(known,clock=clock)
    assert CachedCashApplicationV3.open(result['reference'],clock=clock).reference==result['reference']


@pytest.mark.parametrize('fault',['wrong_worker','parent_metadata','reader_metadata','alias','clock'])
def test_original_binding_guards_stop_before_next_queue_or_worker_effect(tmp_path,fault):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    app=apps['candidate'];worker=workers['candidate']
    if fault=='wrong_worker':worker=workers['stress']
    if fault=='parent_metadata':app.manifest['role']='stress'
    if fault=='reader_metadata':app.reader.manifest['maximum_read_seconds']=30
    if fault=='alias':
        alias=tmp_path/'alias';alias.symlink_to(app.root);app.root=alias
    if fault=='clock':clock.now=stamp(app.manifest['registered_at'])-timedelta(seconds=1)
    before=queue.path.read_bytes();head=list(worker._head())
    with pytest.raises(ValueError):app.apply(queue,worker,prefix.reference)
    assert queue.path.read_bytes()==before and list(worker._head())==head


def test_v3_archive_group_quota_blocks_before_offer_or_tick(tmp_path):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path,policy=CashApplicationPolicyV2(maximum_groups=1));poll(clock,source,queue,prefix)
    app=apps['candidate'];app.apply(queue,workers['candidate'],prefix.reference);clock.advance(5)
    head=list(workers['candidate']._head());before=queue.path.read_bytes()
    with pytest.raises(ValueError,match='budget'):app.apply(queue,workers['candidate'],prefix.reference)
    assert queue.path.read_bytes()==before and list(workers['candidate']._head())==head


def test_failed_cached_read_retains_same_offer_and_retry_does_not_repeat_worker(tmp_path):
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);old=dict(prefix.reference);poll(clock,source,queue,prefix)
    app=apps['candidate'];before=list(workers['candidate']._head())
    with pytest.raises(ValueError):app.apply(queue,workers['candidate'],old)
    cursor=queue.receipt()['role_cursors']['candidate'];assert cursor['cursor']==0 and cursor['delivery_id']
    assert list(workers['candidate']._head())==before and not list((app.application.root/'groups').iterdir())
    result=app.apply(queue,workers['candidate'],prefix.reference)
    assert result['worker_result']['new_intents']==2 and result['opportunity_count']==2
    assert queue.receipt()['role_cursors']['candidate']['cursor']==1


def test_busy_parent_lease_stops_before_offer_and_worker(tmp_path):
    import fcntl
    clock,source,queue,prefix,workers,apps,_=setup(tmp_path);poll(clock,source,queue,prefix)
    app=apps['candidate'];before=queue.path.read_bytes();head=list(workers['candidate']._head())
    with (app.root/'writer.lock').open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):app.apply(queue,workers['candidate'],prefix.reference)
    assert queue.path.read_bytes()==before and list(workers['candidate']._head())==head


def test_real_process_death_after_child_archive_commit_blocks_stale_parent_without_rerun(tmp_path):
    import json,subprocess,sys,sqlite3
    from pathlib import Path
    code='''
import json,os,sys
from pathlib import Path
sys.path[:0]=['src','tests']
from test_cached_cash_application_v3 import setup,poll
root=Path(sys.argv[1]);clock,source,queue,prefix,workers,apps,_=setup(root);poll(clock,source,queue,prefix)
app=apps['candidate'];(root/'external.json').write_text(json.dumps(dict(reference=app.reference,at=clock().isoformat())))
original=app.application._archive_tail
def die():
    original()
    os._exit(42)
app.application._archive_tail=die
app.apply(queue,workers['candidate'],prefix.reference)
'''
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True,timeout=60)
    assert child.returncode==42,child.stderr
    saved=json.loads((tmp_path/'external.json').read_text());app_root=Path(saved['reference']['application_reference']['root'])
    with sqlite3.connect(app_root/'archive.sqlite') as db:assert db.execute('SELECT seq FROM state').fetchone()==(1,)
    assert not list((app_root/'groups').iterdir())
    before=(app_root/'archive.sqlite').read_bytes()
    with pytest.raises(ValueError):CachedCashApplicationV3.open(saved['reference'],clock=lambda:stamp(saved['at']))
    assert (app_root/'archive.sqlite').read_bytes()==before
