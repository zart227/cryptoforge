from pathlib import Path
import json
import pytest

from cryptoforge.cash_ack_recovery import recover_cash_ack
from cryptoforge.cash_worker_application import CashWorkerApplication
from cryptoforge.local_source_provenance import canonical,digest
from cryptoforge.reference_delivery import ReferenceDelivery
from test_cash_worker_application import setup,poll


def inventory(root):return {str(p.relative_to(root)):digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}


def interrupted(tmp_path,monkeypatch,mode='before_ack'):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    app=apps['candidate'];worker=workers['candidate'];known=dict(app.reference)
    original=queue.acknowledge
    def fail(*args,**kwargs):
        if mode=='after_ack':original(*args,**kwargs)
        raise OSError('simulated lost ack')
    if mode=='before_complete':
        import cryptoforge.cash_worker_application as module
        write=module._write_new
        def missing(path,value):
            if path.name=='complete.json' and path.parent.parent==app.root/'groups':raise SystemExit(42)
            return write(path,value)
        monkeypatch.setattr(module,'_write_new',missing)
        with pytest.raises(SystemExit):app.apply(queue,worker)
        monkeypatch.setattr(module,'_write_new',write)
    else:
        monkeypatch.setattr(queue,'acknowledge',fail)
        with pytest.raises(OSError):app.apply(queue,worker)
        monkeypatch.setattr(queue,'acknowledge',original)
    return clock,queue,worker,app,known


@pytest.mark.parametrize('mode',['before_ack','after_ack','before_complete'])
def test_explicit_recovery_completes_only_ack_and_never_repeats_actual_worker(tmp_path,monkeypatch,mode):
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch,mode)
    head=list(worker._head());folder=app.root/'groups/00000001';result_pin=digest((folder/'worker-result.json').read_bytes())
    existing_ack=(folder/'ack.json').read_bytes() if (folder/'ack.json').exists() else None
    old_queue_pin=digest(queue.path.read_bytes())
    recovered=recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    assert recovered['status']=='known_worker_result_acknowledgement_recovered'
    assert recovered['worker_execution_repeated'] is False and recovered['provider_calls']==0
    assert recovered['original_worker_result_sha256']==result_pin and list(worker._head())==head
    if existing_ack is not None:assert (folder/'ack.json').read_bytes()==existing_ack
    if mode!='before_ack':assert digest(queue.path.read_bytes())==old_queue_pin
    resumed=CashWorkerApplication.open(recovered['application_reference'],clock=clock)
    assert resumed.audit()['completed_applications']==1
    queue=ReferenceDelivery.open(recovered['current_queue_reference'],clock=clock)
    assert queue.receipt()['role_cursors']['candidate']['cursor']==1
    clock.advance(5);heartbeat=resumed.apply(queue,worker)
    assert heartbeat['status']=='actual_worker_heartbeat_completed'
    assert heartbeat['worker_result']['new_intents']==0 and heartbeat['worker_result']['fills_processed']==['filled','filled']
    assert all(recovered[k] is False for k in ('paper_evidence_pass','economic_profitability_established','live_admission_granted'))


def test_default_plan_is_read_only_for_original_application_worker_and_queue(tmp_path,monkeypatch):
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch)
    roots=[app.root,worker.root,queue.root];before=[inventory(p) for p in roots]
    value=recover_cash_ack(known,tmp_path/'proposal',clock=clock)
    assert value['status']=='read_only_recovery_plan' and value['application_or_queue_changed'] is False
    assert [inventory(p) for p in roots]==before
    assert not (app.root/'groups/00000001/ack.json').exists()


@pytest.mark.parametrize('fault',['missing_result','changed_input','wrong_ancestor','advanced_worker','conflicting_ack'])
def test_unknown_or_conflicting_effects_stay_blocked_without_recovery_namespace(tmp_path,monkeypatch,fault):
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch)
    folder=app.root/'groups/00000001'
    if fault=='missing_result':(folder/'worker-result.json').unlink()
    if fault=='changed_input':
        p=folder/'input.json';p.write_bytes(p.read_bytes().replace(b'momentum',b'xxxxxxxx',1))
    if fault=='wrong_ancestor':known['head_sha256']='f'*64
    if fault=='advanced_worker':
        clock.advance(5);worker.tick([],source_id='foreign-tick',source_observed_at=clock(),expected_source_sha256=digest(canonical([])))
    if fault=='conflicting_ack':
        delivery=json.loads((folder/'input.json').read_text())['packet']['delivery']
        queue.acknowledge('candidate',delivery['delivery_id'],worker_receipt_sha256='f'*64)
    queue_before=digest(queue.path.read_bytes());worker_before=list(worker._head())
    with pytest.raises((ValueError,KeyError)):recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    assert digest(queue.path.read_bytes())==queue_before and list(worker._head())==worker_before
    # Conflicting ack is detected at the idempotent ack boundary, with a durable
    # recovery proposal, but no original receipt is overwritten.
    assert not (folder/'complete.json').exists()


def test_recovery_cannot_reapply_a_completed_group_or_change_original_runtime(tmp_path,monkeypatch):
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch)
    recovered=recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    before=inventory(app.root)
    with pytest.raises(ValueError,match='already completed'):
        recover_cash_ack(known,tmp_path/'again',apply=True,clock=clock)
    assert inventory(app.root)==before


def test_busy_application_lock_prevents_recovery_before_any_queue_change(tmp_path,monkeypatch):
    import fcntl
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch);before=digest(queue.path.read_bytes())
    with (app.root/'writer.lock').open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    assert digest(queue.path.read_bytes())==before


def test_recovery_output_cannot_pollute_original_source_or_owner_namespace(tmp_path,monkeypatch):
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch)
    before=digest(queue.path.read_bytes())
    with pytest.raises(ValueError):recover_cash_ack(known,tmp_path/'source'/'recovery',apply=True,clock=clock)
    assert digest(queue.path.read_bytes())==before and not (tmp_path/'source/recovery').exists()


def test_untracked_native_change_is_not_acknowledged(tmp_path,monkeypatch):
    clock,queue,worker,app,known=interrupted(tmp_path,monkeypatch)
    with worker._source.wallet._db() as db:db.execute("UPDATE state SET value='99' WHERE key='cash'")
    before=digest(queue.path.read_bytes())
    with pytest.raises(ValueError):recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    assert digest(queue.path.read_bytes())==before


def test_recovery_honors_nonzero_completed_application_prefix(tmp_path,monkeypatch):
    clock,source,queue,_,workers,apps=setup(tmp_path);app=apps['candidate'];worker=workers['candidate']
    first=app.apply(queue,worker);assert first['status']=='actual_worker_heartbeat_completed'
    clock.advance(5);poll(source,queue,clock);known=dict(app.reference);assert known['sequence']==1
    original=queue.acknowledge
    def fail(*a,**k):raise OSError('lost ack after second application')
    monkeypatch.setattr(queue,'acknowledge',fail)
    with pytest.raises(OSError):app.apply(queue,worker)
    monkeypatch.setattr(queue,'acknowledge',original)
    result=recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    assert result['application_reference']['sequence']==2
    assert CashWorkerApplication.open(result['application_reference'],clock=clock).audit()['completed_applications']==2


@pytest.mark.parametrize('role',['control','stress'])
def test_recovery_acknowledges_only_the_original_role(tmp_path,monkeypatch,role):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    app=apps[role];known=dict(app.reference);original=queue.acknowledge
    def fail(*a,**k):raise OSError('lost original role ack')
    monkeypatch.setattr(queue,'acknowledge',fail)
    with pytest.raises(OSError):app.apply(queue,workers[role])
    monkeypatch.setattr(queue,'acknowledge',original)
    result=recover_cash_ack(known,tmp_path/'recovery',apply=True,clock=clock)
    queue=ReferenceDelivery.open(result['current_queue_reference'],clock=clock)
    assert {r:v['cursor'] for r,v in queue.receipt()['role_cursors'].items()}=={r:int(r==role) for r in apps}


def test_true_process_exit_after_queue_commit_recovers_without_reexecuting_worker(tmp_path):
    import subprocess,sys
    from cryptoforge.local_source_provenance import stamp
    code='''
from pathlib import Path
import json,os,sys
sys.path[:0]=['src','tests']
from test_cash_worker_application import setup,poll
root=Path(sys.argv[1]);clock,source,queue,_,workers,apps=setup(root);poll(source,queue,clock)
app=apps['candidate'];(root/'outside.json').write_text(json.dumps(dict(reference=app.reference,at=clock().isoformat())))
original=queue.acknowledge
def die(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(42)
queue.acknowledge=die
app.apply(queue,workers['candidate'])
'''
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True)
    assert child.returncode==42,child.stderr
    outside=json.loads((tmp_path/'outside.json').read_text());clock=lambda:stamp(outside['at'])
    root=Path(outside['reference']['root']);pending=root/'groups/00000001'
    result_pin=digest((pending/'worker-result.json').read_bytes())
    assert not (pending/'ack.json').exists() and not (pending/'complete.json').exists()
    recovered=recover_cash_ack(outside['reference'],tmp_path/'recovery',apply=True,clock=clock)
    assert recovered['original_worker_result_sha256']==result_pin and recovered['worker_execution_repeated'] is False
    assert CashWorkerApplication.open(recovered['application_reference'],clock=clock).audit()['completed_applications']==1
