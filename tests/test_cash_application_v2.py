from datetime import timedelta
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from cryptoforge.cash_application_v2 import SegmentedCashApplicationV2,CashApplicationPolicyV2,SQL,_decode
from cryptoforge.cash_worker_application import CashWorkerApplication
from cryptoforge.cash_entry_contract import freeze_cash_contract,load_cash_contract
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy
from cryptoforge.reference_delivery import ReferenceDelivery,DeliveryPolicy
from cryptoforge.paper_producer_v2 import register_kernel
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from cryptoforge.local_source_provenance import canonical,digest,stamp,parse
from test_cash_worker_application import rules,PositiveClient
from test_reference_source_ledger import Clock,Client
from test_paper_capture_v3 import lifecycle,storage
from test_native_paper_archive_v2 import policy as native_policy,WORKER_POLICY
from test_paper_worker_capture_v2 import budgets
from test_paper_wallet import config
from test_paper_valuation_capture import raw_market


def setup(tmp_path,*,role='candidate',duration=20,policy=None):
    clock=Clock();start=clock()+timedelta(seconds=60);end=start+timedelta(seconds=duration)
    source=ReferenceLedger.create(tmp_path/'source',clock=clock,start=start,end=end,
        policy=ReferencePolicy(maximum_events=200,maximum_versions=2000,maximum_forecasts=10,maximum_database_bytes=8*1024**2))
    queue=ReferenceDelivery.create(tmp_path/'queue',source.receipt()['reference'],clock=clock,
        policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_source_events_per_batch=4))
    ref=freeze_cash_contract(tmp_path/'cash-contract',queue,rules=rules(),closeout_seconds=5,clock=clock);contract=load_cash_contract(ref)
    kernel=register_kernel(tmp_path/'kernel',candidate_sha=contract['strategies'][role],study_protocol_sha256=ref['contract_sha256'],
        role=role,config=config(),worker_policy=WORKER_POLICY,backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY':'synthetic'},
        start=start,end=end,closeout_seconds=5,clock=clock)
    worker=CapturedPaperWorkerV2.create(tmp_path/'worker',kernel_root=kernel['root'],expected_kernel_contract_sha256=kernel['contract_sha256'],
        expected_kernel_registration_sha256=kernel['registration_sha256'],lifecycle=lifecycle(maximum_operations_per_poll=1),
        storage_policy=storage(maximum_events=16384,maximum_segments=512,maximum_segment_events=128,maximum_record_bytes=32768,maximum_total_bytes=32*1024**2),
        native_policy=native_policy(maximum_total_bytes=32*1024**2),capture_policy=budgets(),market=lambda pair:raw_market(clock,pair),clock=clock)
    app=SegmentedCashApplicationV2.create(tmp_path/'application-v2',ref,queue,worker,clock=clock,policy=policy)
    clock.advance(60)
    return clock,source,queue,worker,app


def poll(source,queue,clock,positive=False):
    source.poll(PositiveClient(clock) if positive else Client(clock));queue.ingest(source.receipt()['reference'])


def test_original_receipt_bytes_and_worker_sha_survive_compressed_archival(tmp_path):
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock,True)
    first=app.apply(queue,worker);assert first['opportunity_count']==2
    assert not list((app.root/'groups').iterdir())
    clock.advance(5);second=app.apply(queue,worker)
    assert second['worker_result']['fills_processed']==['filled','filled']
    assert not list((app.root/'groups').iterdir())
    assert app.audit()['performance_hidden'] is True
    clock.now=stamp(app.manifest['end']);audit=app.audit()
    assert audit['full_history_integrity_pass'] and audit['completed_applications']==2
    raw=app.read_group(1);assert digest(raw['worker-result.json'])==first['worker_receipt_sha256']
    assert parse(raw['ack.json'])['acknowledgement']['worker_receipt_sha256']==first['worker_receipt_sha256']
    assert raw['complete.json']==canonical(parse(raw['complete.json']))
    with app._db() as db:
        compressed,original=db.execute('SELECT sum(length(payload)),sum(raw_bytes) FROM groups').fetchone()
    assert compressed<original
    assert SegmentedCashApplicationV2.open(second['reference'],clock=clock).audit()['full_history_integrity_pass']
    with pytest.raises(ValueError):CashWorkerApplication.open(second['reference'],clock=clock)


def test_calendar_first_metadata_audit_never_decodes_unfinished_groups(tmp_path,monkeypatch):
    import cryptoforge.cash_application_v2 as module
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock)
    app.apply(queue,worker)
    def forbidden(*args):pytest.fail('unfinished payload decoded during metadata audit')
    monkeypatch.setattr(module,'_decode',forbidden)
    result=SegmentedCashApplicationV2.audit_reference(app.reference,clock=clock)
    assert result['performance_hidden'] and result['full_history_integrity_pass'] is False
    with pytest.raises(ValueError,match='sealed'):app.read_group(1)


def test_normal_ticks_touch_only_latest_commit_not_the_whole_old_archive(tmp_path,monkeypatch):
    clock,source,queue,worker,app=setup(tmp_path,role='control',duration=220);poll(source,queue,clock)
    for _ in range(36):app.apply(queue,worker);clock.advance(5)
    touched=[];original=app._row
    def observed(row):touched.append(row[0]);return original(row)
    monkeypatch.setattr(app,'_row',observed)
    app.apply(queue,worker)
    assert set(touched)<={36,37} and touched
    assert app.reference['sequence']==37 and not list((app.root/'groups').iterdir())
    assert app.policy.maximum_groups>1024


def test_cold_corruption_is_detected_by_full_history_audit(tmp_path):
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock)
    app.apply(queue,worker);clock.advance(5);app.apply(queue,worker)
    db=sqlite3.connect(app.root/'archive.sqlite')
    try:
        db.execute('DROP TRIGGER groups_no_update')
        with db:db.execute('UPDATE groups SET payload=zeroblob(length(payload)) WHERE seq=1')
        db.execute(SQL['groups_no_update']);db.commit()
    finally:db.close()
    clock.now=stamp(app.manifest['end'])
    with pytest.raises(ValueError,match='commitment'):app.audit()


def test_immutable_schema_and_blob_decompression_limits(tmp_path):
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock);app.apply(queue,worker)
    with app._db(write=True) as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM groups')
        with pytest.raises(sqlite3.IntegrityError):db.execute('UPDATE groups SET raw_bytes=0')
    with pytest.raises(ValueError):_decode(b'x'*(app.policy.maximum_group_bytes+65537),1,app.policy)
    with pytest.raises(ValueError):_decode(b'not-gzip',app.policy.maximum_group_bytes+1,app.policy)


@pytest.mark.parametrize('fault',['clock','runtime_policy','archive_head','alias'])
def test_v2_identity_guards_block_before_next_worker_effect(tmp_path,fault):
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock);app.apply(queue,worker)
    before=list(worker._head())
    if fault=='clock':clock.advance(-1)
    if fault=='runtime_policy':app.policy=replace(app.policy,maximum_groups=1)
    if fault=='archive_head':app.reference['archive_head_sha256']='f'*64
    if fault=='alias':
        alias=tmp_path/'alias';alias.symlink_to(app.root);app.root=alias
    with pytest.raises((ValueError,FileNotFoundError)):app.apply(queue,worker)
    assert list(worker._head())==before


def test_archive_budget_stops_before_queue_offer_or_tick(tmp_path):
    clock,source,queue,worker,app=setup(tmp_path,policy=CashApplicationPolicyV2(maximum_groups=1));poll(source,queue,clock)
    app.apply(queue,worker);clock.advance(5);before=list(worker._head());ref=queue.receipt()['reference']
    with pytest.raises(ValueError,match='budget'):app.apply(queue,worker)
    assert list(worker._head())==before and queue.receipt()['reference']==ref


@pytest.mark.parametrize('point',['before_archive','after_archive_before_delete'])
def test_explicit_completed_archive_recovery_never_repeats_worker(tmp_path,monkeypatch,point):
    import cryptoforge.cash_application_v2 as module
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock,True);known=dict(app.reference)
    if point=='before_archive':
        original=app._archive_tail
        def fail():raise OSError('lost before archive')
        monkeypatch.setattr(app,'_archive_tail',fail)
    else:
        original=module.shutil.rmtree
        def fail(*a,**k):raise OSError('lost after durable archive commit')
        monkeypatch.setattr(module.shutil,'rmtree',fail)
    with pytest.raises(OSError):app.apply(queue,worker)
    if point=='before_archive':monkeypatch.setattr(app,'_archive_tail',original)
    else:monkeypatch.setattr(module.shutil,'rmtree',original)
    before=list(worker._head());result=SegmentedCashApplicationV2.recover(known,clock=clock)
    assert result['worker_execution_repeated'] is False and result['provider_calls']==0 and list(worker._head())==before
    restored=SegmentedCashApplicationV2.open(result['reference'],clock=clock)
    assert not list((restored.root/'groups').iterdir())
    clock.advance(5);q=ReferenceDelivery.open(result['queue_reference'],clock=clock)
    tick=restored.apply(q,worker)
    assert tick['worker_result']['new_intents']==0 and tick['worker_result']['fills_processed']==['filled','filled']


def test_missing_worker_completion_cannot_be_adopted_by_archive_recovery(tmp_path,monkeypatch):
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock);known=dict(app.reference)
    def crash(*a,**k):raise RuntimeError('unknown worker result')
    monkeypatch.setattr(worker,'tick',crash)
    with pytest.raises(RuntimeError):app.apply(queue,worker)
    before=queue.receipt()['reference']
    with pytest.raises(ValueError,match='incomplete'):SegmentedCashApplicationV2.recover(known,clock=clock)
    assert queue.receipt()['reference']==before


@pytest.mark.parametrize('point',['committed_before_delete','deleted_before_external_checkpoint'])
def test_real_process_death_recovers_one_committed_group_without_worker_rerun(tmp_path,point):
    import json,subprocess,sys
    code='''
import json,os,sys
from pathlib import Path
sys.path[:0]=['src','tests']
import cryptoforge.cash_application_v2 as module
from test_cash_application_v2 import setup,poll
root=Path(sys.argv[1]);clock,source,queue,worker,app=setup(root)
poll(source,queue,clock,True)
(root/'external.json').write_text(json.dumps(dict(reference=app.reference,at=clock().isoformat())))
original=module.shutil.rmtree
def die(*a,**k):
    if sys.argv[2]=='deleted_before_external_checkpoint':original(*a,**k)
    os._exit(42)
module.shutil.rmtree=die
app.apply(queue,worker)
'''
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path),point],capture_output=True,text=True,timeout=60)
    assert child.returncode==42,child.stderr
    saved=json.loads((tmp_path/'external.json').read_text());clock=lambda:stamp(saved['at']);root=Path(saved['reference']['root'])
    with sqlite3.connect(root/'archive.sqlite') as db:
        assert db.execute('SELECT seq FROM state').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM groups').fetchone()==(1,)
    assert bool(list((root/'groups').iterdir()))==(point=='committed_before_delete')
    with pytest.raises(ValueError):SegmentedCashApplicationV2.open(saved['reference'],clock=clock)
    result=SegmentedCashApplicationV2.recover(saved['reference'],clock=clock)
    assert result['reference']['sequence']==1 and not result['worker_execution_repeated'] and result['provider_calls']==0
    assert not list((root/'groups').iterdir())
    recovered=SegmentedCashApplicationV2.open(result['reference'],clock=clock)
    assert recovered.audit()['performance_hidden'] and recovered.worker_head[1]=='complete'


def test_oversize_stored_blob_is_rejected_before_blob_read_or_worker(tmp_path,monkeypatch):
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock);app.apply(queue,worker)
    with sqlite3.connect(app.root/'archive.sqlite') as db:
        db.execute('DROP TRIGGER groups_no_update')
        db.execute('UPDATE groups SET payload=zeroblob(?)',(app.policy.maximum_group_bytes+65537,))
        db.execute(SQL['groups_no_update'])
    before=list(worker._head())
    monkeypatch.setattr(app,'_row',lambda *a:pytest.fail('unbounded payload fetched'))
    with pytest.raises(ValueError,match='bounded stored'):app.apply(queue,worker)
    assert list(worker._head())==before


@pytest.mark.parametrize('effect',['offer','ack'])
def test_recovery_rejects_foreign_role_queue_advance_after_known_group(tmp_path,effect):
    clock,source,queue,worker,app=setup(tmp_path,duration=340);poll(source,queue,clock);app.apply(queue,worker)
    known=dict(app.reference);clock.advance(300);poll(source,queue,clock)
    delivery=queue.next('candidate')['delivery']
    if effect=='ack':queue.acknowledge('candidate',delivery['delivery_id'],worker_receipt_sha256='f'*64)
    before=queue.receipt()['reference'];head=list(worker._head())
    with pytest.raises(ValueError,match='queue advanced'):SegmentedCashApplicationV2.recover(known,clock=clock)
    assert list(worker._head())==head and queue.receipt()['reference']==before


def test_dispatch_lease_prevents_second_writer_before_queue_or_worker_effect(tmp_path):
    import fcntl
    clock,source,queue,worker,app=setup(tmp_path);poll(source,queue,clock)
    before=list(worker._head());ref=queue.receipt()['reference']
    with (app.root/'dispatch.lock').open('rb') as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):app.apply(queue,worker)
    assert list(worker._head())==before and queue.receipt()['reference']==ref
