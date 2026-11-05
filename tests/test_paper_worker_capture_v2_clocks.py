"""Actual leaf clocks, causal counters and failure atomicity for capture v2."""
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from cryptoforge.evidence_segments import canonical,digest
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from cryptoforge.paper_worker_capture import CapturedPaperWorker as FrozenCapture
from cryptoforge.paper_capture_state_v2 import GROUPS,_empty,_apply,_valid_row
from test_paper_worker_capture_v2 import setup,prediction,tick,finish,audit,records
from test_paper_capture_v4 import rehash
from test_paper_wallet import START
from test_paper_valuation_capture import raw_market
from test_paper_capture_v3 import storage


def arm_lock_observation(worker,clock,monkeypatch,at):
    """Move UTC only after the actual execute transaction obtained its lock."""
    original_db=worker._source.wallet._db
    original_execute=worker._source.wallet.execute
    gate={'active':False,'lock':False}
    class Connection:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        def execute(self,sql,*args):
            result=self.db.execute(sql,*args)
            if gate['active'] and sql=='BEGIN IMMEDIATE':
                gate['lock']=True;clock.now=at
            return result
    def execute(*args,**kwargs):
        gate['active']=True
        try:return original_execute(*args,**kwargs)
        finally:gate['active']=False
    monkeypatch.setattr(worker._source.wallet,'_db',lambda:Connection(original_db()))
    monkeypatch.setattr(worker._source.wallet,'execute',execute)
    return gate


@pytest.mark.parametrize('case',['cutoff','expiry','fill'])
def test_execution_uses_durable_post_lock_clock_not_preparation(tmp_path,monkeypatch,case):
    end=START+timedelta(seconds=60 if case=='expiry' else 20)
    worker,clock=setup(tmp_path,end=end,storage_policy=storage(maximum_events=2048,
        maximum_segment_events=64,maximum_record_bytes=32768,maximum_total_bytes=16*1024*1024))
    tick(worker,clock,[prediction(clock)])
    clock.now=START+timedelta(seconds=29 if case=='expiry' else 10)
    at=START+timedelta(seconds={'cutoff':15,'expiry':31,'fill':11}[case])
    gate=arm_lock_observation(worker,clock,monkeypatch,at)
    report=tick(worker,clock)
    assert gate['lock']
    assert report['fills_processed']==['filled' if case=='fill' else 'rejected']
    # Restore instrumentation before the endpoint uses connection contexts.
    monkeypatch.undo()
    with worker._source.wallet._db() as db:
        intent=db.execute('SELECT observed_at,status,reason FROM intents').fetchone()
        assert intent[0]==at.isoformat()
        if case!='fill':
            assert db.execute('SELECT count(*) FROM fills').fetchone()[0]==0
            assert db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0]=='100'
            assert intent[2]==('paper_entry_window_finished' if case=='cutoff' else 'expired_signal')
    clock.now=end
    worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    trace=records(worker,seal)
    actions={r['sequence']:r['payload'] for r in trace if r['kind']=='prepared' and r['payload'].get('operation')=='execute'}
    matched=[]
    for r in trace:
        e=r['payload']
        if r['kind']=='complete' and e.get('phase')=='action' and e['prepared_seq'] in actions and e['native_clocks']:
            p=actions[e['prepared_seq']]
            if e['native_clocks'][0]==at.isoformat():
                assert p['at'] < e['native_clocks'][0]
                matched.append(e)
                clocks=[x for x in trace if x['payload'].get('action_prepared_seq')==e['prepared_seq']]
                assert [x['payload']['at'] for x in clocks]==e['native_clocks']
                assert all(x['sequence']<r['sequence'] for x in clocks)
    assert len(matched)==1
    assert audit(worker,seal,clock=clock)['worker_source_trace_pass']


def test_clock_must_be_committed_before_native_fill_can_use_it(tmp_path,monkeypatch):
    worker,clock=setup(tmp_path)
    tick(worker,clock,[prediction(clock)]);clock.advance(5)
    original=worker._record
    def stop(kind,event):
        if event.get('phase')=='clock' and worker._action_seq is not None:
            head=json.loads(worker._head()[2])
            if head.get('operation')=='execute':raise OSError('synthetic clock journal failure')
        return original(kind,event)
    monkeypatch.setattr(worker,'_record',stop)
    with pytest.raises(ValueError,match='fault|unfinished'):tick(worker,clock)
    with worker._source.wallet._db() as db:
        assert db.execute('SELECT count(*) FROM fills').fetchone()[0]==0
        assert db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0]=='100'
        assert db.execute('SELECT seq FROM sqlite_sequence').fetchall()==[]
    with pytest.raises(ValueError,match='unfinished'):
        CapturedPaperWorkerV2.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)


@pytest.mark.parametrize('stage',['after_clock','during_clock_frame','after_fill_commit'])
def test_process_death_at_post_lock_clock_never_adopts_or_repeats_tick(tmp_path,stage):
    worker,clock=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.advance(5)
    code='''
from pathlib import Path
from datetime import datetime
import json,os,sys
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from cryptoforge.evidence_segments import canonical,digest
root,pin,at,stage=sys.argv[1:];now=datetime.fromisoformat(at)
# Use the exact same raw normalized fixture supplied by the parent process.
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_paper_valuation_capture import raw_market
from test_paper_wallet import Clock
clock=Clock();clock.now=now
w=CapturedPaperWorkerV2.resume(Path(root),expected_registration_sha256=pin,market=lambda pair:raw_market(clock,pair),clock=lambda:now)
original=w._record
if stage=='after_clock':
 def record(kind,event):
  result=original(kind,event)
  if event.get('phase')=='clock' and w._action_seq is not None:
   # A clock append changes the log head, so locate preparation by sequence.
   if getattr(w,'executing',False):os._exit(85)
  return result
 w._record=record
elif stage=='during_clock_frame':
 original_frame=w.log._write_frame
 def frame(path,offset,raw):
  r=json.loads(raw)
  if r['payload'].get('phase')=='clock' and getattr(w,'executing',False):
   with path.open('ab') as f:f.write(raw[:len(raw)//2]);f.flush();os.fsync(f.fileno())
   os._exit(86)
  return original_frame(path,offset,raw)
 w.log._write_frame=frame
original_execute=w._source.wallet.execute
def execute(*args,**kwargs):
 w.executing=True
 result=original_execute(*args,**kwargs)
 if stage=='after_fill_commit':os._exit(87)
 return result
w._source.wallet.execute=execute
w.tick([],source_id='empty',source_observed_at=now,expected_source_sha256=digest(canonical([])))
'''
    process=subprocess.run([sys.executable,'-c',code,str(worker.root),worker.registration_sha256,clock.now.isoformat(),stage],
        capture_output=True,text=True,timeout=40)
    assert process.returncode==({'after_clock':85,'during_clock_frame':86,'after_fill_commit':87}[stage]),process.stderr
    # Recovering a durable log frame cannot prove completion of the enclosing tick.
    with pytest.raises(ValueError,match='unfinished'):
        CapturedPaperWorkerV2.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)
    with sqlite3.connect(worker.root/'native'/'wallet.sqlite') as db:
        assert db.execute('SELECT count(*) FROM fills').fetchone()[0]==(1 if stage=='after_fill_commit' else 0)
        cash=db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0]
        assert (cash!='100') if stage=='after_fill_commit' else (cash=='100')


@pytest.mark.parametrize('mutation',['orphan','wrong_parent','missing_list','extra_list','wrong_counter','wrong_order','missing_group','late_fill'])
def test_rehashed_clock_and_fourteen_group_forgery_is_rejected(tmp_path,mutation):
    worker,clock=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    seal=finish(worker,clock)
    def mutate(record):
        e=record['payload']
        if e.get('phase')=='clock' and e.get('action_prepared_seq') is not None:
            if mutation=='orphan':e['action_prepared_seq']=None
            if mutation=='wrong_parent':e['action_prepared_seq']+=1
        if record['kind']=='complete' and e.get('phase')=='action':
            if mutation=='missing_list':e['native_clocks']=[]
            if mutation=='extra_list':e['native_clocks'].append(e['at'])
            for c in e['changes']:
                if mutation=='wrong_counter' and c['source']=='wallet.fill_counter':c['after'][1]+=1
                if mutation=='wrong_order' and c['source']=='wallet.fill_order':c['after'][0]+=1
                if mutation=='late_fill' and c['source']=='wallet.fills':
                    fill=json.loads(c['after'][1]);fill['filled_at']=(START+timedelta(seconds=16)).isoformat();c['after'][1]=json.dumps(fill)
        if record['kind']=='genesis' and mutation=='missing_group':del e['after']['sources']['wallet.fill_counter']
    with pytest.raises((ValueError,KeyError)):audit(worker,rehash(worker,seal,mutate))


def test_new_source_groups_have_a_distinct_commitment_domain():
    assert len(GROUPS)==14 and {'wallet.fill_counter','wallet.fill_order'} <= set(GROUPS)
    assert _valid_row('wallet.fill_counter',['fill_order',1])==['fill_order',1]
    result=_apply(_empty(),[dict(source='wallet.fill_counter',key='fill_order',before=None,after=['fill_order',1])],maximum_bytes=8192)
    assert result['wallet.fill_counter']['count']==1
    with pytest.raises(ValueError):_valid_row('wallet.fill_order',['1','intent'])


def test_frozen_capture_does_not_adopt_new_schema(tmp_path):
    worker,clock=setup(tmp_path)
    before={str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):FrozenCapture.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
        market=lambda pair:raw_market(clock,pair),clock=clock)
    assert before=={str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('file',['kernel-contract.json','registered.json','ready.json'])
def test_original_kernel_and_native_ready_are_rechecked_before_tick(tmp_path,file):
    worker,clock=setup(tmp_path)
    path=(tmp_path/'kernel'/file) if file!='ready.json' else worker.root/'native'/file
    path.write_text('{}')
    with pytest.raises(ValueError):tick(worker,clock)
    assert worker._head()[0]==1


def test_pair_named_token_is_a_market_identity_not_a_secret(tmp_path):
    worker,clock=setup(tmp_path)
    tick(worker,clock,[prediction(clock,pair='TOKEN/USDT')]);clock.advance(5);tick(worker,clock)
    assert audit(worker,finish(worker,clock))['worker_source_trace_pass']


@pytest.mark.parametrize('stage',['after_native_ready','after_registration_fsync'])
def test_late_setup_cannot_reuse_partial_capture_root(tmp_path,monkeypatch,stage):
    import cryptoforge.paper_worker_capture_v2 as capture
    original_create=capture.NativePaperArchive.create
    original_write=capture._write_new
    clocks={}
    def create(*args,**kwargs):
        clocks['clock']=kwargs['clock']
        result=original_create(*args,**kwargs)
        if stage=='after_native_ready':clocks['clock'].now=START
        return result
    def write(path,payload):
        result=original_write(path,payload)
        if Path(path).name=='registration.json' and stage=='after_registration_fsync':clocks['clock'].now=START
        return result
    monkeypatch.setattr(capture.NativePaperArchive,'create',create)
    monkeypatch.setattr(capture,'_write_new',write)
    with pytest.raises(ValueError,match='registration|start'):setup(tmp_path)
    root=tmp_path/'worker-study'
    assert root.exists() and not (root/'registration.json').exists()
    with pytest.raises((ValueError,OSError)):
        CapturedPaperWorkerV2.resume(root,expected_registration_sha256='a'*64,market=lambda pair:None)


def test_capture_preserves_kernel_tick_identity_checks(tmp_path):
    worker,clock=setup(tmp_path)
    with worker._worker._db() as db:
        db.execute("UPDATE worker_state SET value='{}' WHERE key='identity'")
    with pytest.raises(ValueError):tick(worker,clock)
    assert worker._head()[0]==1


@pytest.mark.parametrize('value',['secret','too_many'])
def test_endpoint_maps_are_bounded_before_any_source_mutation(tmp_path,value):
    worker,clock=setup(tmp_path)
    clock.now=START+timedelta(seconds=20)
    if value=='secret':
        q,r=raw_market(clock,'TOKEN/USDT');q['api_key']='synthetic-secret';quotes={q['pair']:q};filters={r['pair']:r}
    else:quotes={f'P{i}/USDT':{} for i in range(3000)};filters={}
    with pytest.raises(ValueError):worker.mark_endpoint(quotes,filters)
    assert worker._head()[0]==1


def test_real_write_lock_wait_crosses_cutoff_without_spending(tmp_path,monkeypatch):
    import threading
    import time
    worker,clock=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.now=START+timedelta(seconds=10)
    original_db=worker._source.wallet._db;original_execute=worker._source.wallet.execute
    held=threading.Event();requested=threading.Event();finished=threading.Event();errors=[]
    gate={'active':False,'waited':0.0}
    def holder():
        try:
            with sqlite3.connect(worker._source.wallet.path,timeout=1) as db:
                db.execute('BEGIN IMMEDIATE');held.set()
                assert requested.wait(2)
                time.sleep(.05);clock.now=START+timedelta(seconds=15);db.rollback()
        except BaseException as exc:errors.append(type(exc).__name__)
        finally:finished.set()
    class Connection:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        def execute(self,sql,*args):
            if gate['active'] and sql=='BEGIN IMMEDIATE':
                requested.set();started=time.monotonic();result=self.db.execute(sql,*args)
                gate['waited']=time.monotonic()-started;return result
            return self.db.execute(sql,*args)
    def execute(*args,**kwargs):
        gate['active']=True;thread=threading.Thread(target=holder);thread.start()
        assert held.wait(2)
        try:return original_execute(*args,**kwargs)
        finally:
            gate['active']=False;thread.join(3)
            assert finished.is_set() and not errors
    monkeypatch.setattr(worker._source.wallet,'_db',lambda:Connection(original_db()))
    monkeypatch.setattr(worker._source.wallet,'execute',execute)
    assert tick(worker,clock)['fills_processed']==['rejected']
    assert gate['waited']>=.04
    monkeypatch.undo()
    with worker._source.wallet._db() as db:
        assert db.execute('SELECT count(*) FROM fills').fetchone()[0]==0
        assert db.execute('SELECT status,reason FROM intents').fetchone()==('rejected','paper_entry_window_finished')
    assert audit(worker,finish(worker,clock))['worker_source_trace_pass']


@pytest.mark.parametrize('path',[('inputs','quotes'),('inputs','filters'),('result','errors'),('inputs','payload','errors')])
def test_scoped_pair_key_policy_preserves_credential_guard(path):
    from cryptoforge.paper_worker_events_v2 import _check_public_payload
    def nested(value):
        for key in reversed(path):value={key:value}
        return value
    _check_public_payload(nested({'TOKEN/USDT':{}}))
    with pytest.raises(ValueError):_check_public_payload(nested({'api_key':'synthetic'}))
    with pytest.raises(ValueError):_check_public_payload(nested({'TOKEN/USDT':{'api_key':'synthetic'}}))
    with pytest.raises(ValueError):_check_public_payload({'other':{'TOKEN/USDT':{}}})


def test_rejection_observed_at_uses_second_native_clock(tmp_path,monkeypatch):
    worker,clock=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.now=START+timedelta(seconds=10)
    gate=arm_lock_observation(worker,clock,monkeypatch,START+timedelta(seconds=15))
    def actual():
        if gate['lock']:clock.now+=timedelta(milliseconds=1)
        return clock.now
    worker.clock=actual
    assert tick(worker,clock)['fills_processed']==['rejected']
    monkeypatch.undo();worker.clock=clock
    with worker._source.wallet._db() as db:observed=db.execute('SELECT observed_at FROM intents').fetchone()[0]
    seal=finish(worker,clock)
    actions=[r['payload'] for r in records(worker,seal) if r['kind']=='complete' and r['payload'].get('phase')=='action'
        and r['payload'].get('result',{} ) and type(r['payload']['result']) is dict and r['payload']['result'].get('reason')=='paper_entry_window_finished']
    assert len(actions)==1 and len(actions[0]['native_clocks'])==2
    assert actions[0]['native_clocks'][0]<actions[0]['native_clocks'][1]==observed
    assert audit(worker,seal)['worker_source_trace_pass']


def test_endpoint_preserves_advancing_actual_times_without_backfill(tmp_path):
    worker,clock=setup(tmp_path);tick(worker,clock)
    end=START+timedelta(seconds=20);clock.now=end
    def advancing():
        clock.now+=timedelta(milliseconds=1)
        return clock.now
    worker.clock=advancing
    worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,clock=clock)
    assert result['worker_source_trace_pass']
    assert result['endpoint_observations_backfill_window'] is False
    assert result['endpoint_mark_observed_at']>end.isoformat()
    trace=records(worker,seal)
    preparations=[r['payload'] for r in trace if r['kind']=='prepared' and r['payload'].get('phase')=='tick'
        and r['payload']['mode']=='endpoint']
    assert len(preparations)==1 and preparations[0]['at']>end.isoformat()
    assert worker.protocol['plan']['endpoint_observation_deadline']==(end+timedelta(seconds=10)).isoformat()
    assert result['paper_evidence_pass'] is False


@pytest.mark.parametrize('offset',[-1,11])
def test_endpoint_start_outside_registered_tolerance_has_no_effect(tmp_path,offset):
    worker,clock=setup(tmp_path);tick(worker,clock)
    old=worker._head()[0];clock.now=START+timedelta(seconds=20+offset)
    with pytest.raises(ValueError):worker.mark_endpoint({},{})
    assert worker._head()[0]==old


def test_endpoint_overrun_has_no_successful_receipt_or_retry(tmp_path):
    worker,clock=setup(tmp_path);tick(worker,clock);clock.now=START+timedelta(seconds=29)
    def advancing():
        value=clock.now;clock.now+=timedelta(milliseconds=400)
        return value
    worker.clock=advancing
    with pytest.raises(ValueError):worker.mark_endpoint({},{})
    with pytest.raises(ValueError):worker.mark_endpoint({},{})
    with pytest.raises(ValueError,match='unfinished'):
        CapturedPaperWorkerV2.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)


def test_endpoint_observation_tolerance_is_stricter_than_completion_grace(tmp_path):
    from test_paper_capture_v3 import lifecycle
    worker,clock=setup(tmp_path,lifecycle=lifecycle(maximum_operations_per_poll=1,maximum_endpoint_gap_seconds=2))
    tick(worker,clock);clock.now=START+timedelta(seconds=21)
    def advancing():
        value=clock.now;clock.now+=timedelta(milliseconds=500)
        return value
    worker.clock=advancing
    with pytest.raises(ValueError,match='endpoint observation'):worker.mark_endpoint({},{})
    assert worker._fault and worker._head()[1]=='prepared'


def test_rehashed_endpoint_clock_cannot_borrow_longer_completion_grace(tmp_path):
    from test_paper_capture_v3 import lifecycle
    worker,clock=setup(tmp_path,lifecycle=lifecycle(maximum_operations_per_poll=1,maximum_endpoint_gap_seconds=2))
    tick(worker,clock);seal=finish(worker,clock)
    endpoint={'active':False}
    def mutate(record):
        event=record['payload']
        if record['kind']=='prepared' and event.get('mode')=='endpoint':endpoint['active']=True;return
        if endpoint['active']:event['at']=(START+timedelta(seconds=23)).isoformat()
    with pytest.raises(ValueError,match='endpoint observation tolerance'):
        audit(worker,rehash(worker,seal,mutate))


def test_capture_fill_order_counter_survive_full_closeout_compaction_and_resume(tmp_path):
    from test_native_paper_archive_v2 import policy
    worker,clock=setup(tmp_path,end=START+timedelta(seconds=65),native_policy=policy(maximum_active_rows=16),
        storage_policy=storage(maximum_events=2048,maximum_segment_events=64,maximum_record_bytes=32768,
            maximum_total_bytes=16*1024*1024))
    for cycle in range(3):
        clock.now=START+timedelta(seconds=cycle*20)
        worker._market=lambda pair:raw_market(clock,pair,price='100')
        tick(worker,clock,[prediction(clock,opportunity=str(cycle))])
        clock.advance(5);assert tick(worker,clock)['fills_processed']==['filled']
        worker._market=lambda pair:raw_market(clock,pair,price='95')
        clock.advance(5);tick(worker,clock)
        clock.advance(5);assert tick(worker,clock)['fills_processed']==['filled']
        worker=CapturedPaperWorkerV2.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)
        state=json.loads(worker._head()[2])['after']['sources']
        assert state['wallet.fill_order']['count']==2*(cycle+1)
        assert state['wallet.fill_counter']['count']==1
    clock.now=START+timedelta(seconds=65)
    worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    assert audit(worker,seal,clock=clock)['worker_source_trace_pass']
    assert [r[0] for r in worker._source.iter_rows('wallet.fill_order')]==list(range(1,7))
    assert list(worker._source.iter_auxiliary_rows('wallet.fill_counter'))==[('fill_order',6)]
