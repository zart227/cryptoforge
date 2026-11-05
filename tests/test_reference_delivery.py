from datetime import UTC,datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import sqlite3
import subprocess
import sys

import pytest

from test_reference_source_ledger import Clock,Client,artifact
from cryptoforge.local_source_provenance import canonical,digest,parse
from cryptoforge.reference_source_ledger import FLAGS,ReferenceLedger,ReferencePolicy,file_sha
from cryptoforge.reference_delivery import DeliveryPolicy,ReferenceDelivery,DeliveredReferenceReader,ROLES,SQL


@pytest.fixture(autouse=True)
def disk(monkeypatch):
    monkeypatch.setattr('cryptoforge.reference_delivery.shutil.disk_usage',lambda _:SimpleNamespace(free=20*1024**3))


def ref(obj):return obj.receipt()['reference']


def make(tmp_path,*,prospective=False,policy=None,poll=True,forecast=True,clock=None):
    clock=clock or Clock()
    source=ReferenceLedger.create(tmp_path/'source',clock=clock,artifact_raw=artifact(),
        start=clock()+timedelta(seconds=60) if prospective else None,end=clock()+timedelta(hours=1),
        policy=ReferencePolicy(maximum_events=200,maximum_versions=2000,maximum_forecasts=100,maximum_database_bytes=8*1024**2))
    queue=ReferenceDelivery.create(tmp_path/'queue',ref(source),clock=clock,diagnostic=not prospective,
        policy=policy or DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_events=200,maximum_source_events=200,maximum_batches=50))
    if poll:
        if prospective:clock.advance(60)
        source.poll(Client(clock))
        if forecast:source.forecast('BTC/USDT');source.forecast('ETH/USDT')
    return clock,source,queue


def test_all_three_roles_get_same_source_events_and_independent_pending_cursors(tmp_path):
    clock,source,queue=make(tmp_path);receipt=queue.ingest(ref(source))
    assert receipt['source_events']==6 and receipt['batches']==1
    snapshots=[];delivery_ids=[]
    for role in ROLES:
        delivered=queue.next(role);d=delivered['delivery'];delivery_ids.append(d['delivery_id'])
        reader=DeliveredReferenceReader.open(queue,role,d['delivery_id'],clock=clock)
        assert reader.status()['closed_candles_ready'] is True
        rows=reader.read_candles('ETH/USDT');features=reader.features('ETH/USDT')
        forecasts=reader.original_forecasts()
        assert len(rows)==120 and len(forecasts)==2
        assert all(f['original']['payload']['long_probability']<.5 for f in forecasts)
        assert all(f['entry_decision_available'] is False for f in forecasts)
        expected=next(f['original']['payload']['features'] for f in forecasts if f['original']['payload']['pair']=='ETH/USDT')
        assert list(features)==expected
        assert all(reader.status()[k] is False for k in FLAGS)
        snapshots.append((reader.status()['batch_sha256'],reader.source_events(),rows,features))
    assert len(set(delivery_ids))==3 and snapshots[0]==snapshots[1]==snapshots[2]
    assert all(row['pending_sequence']==1 and row['cursor']==0 for row in queue.receipt()['role_cursors'].values())


def test_restart_redelivers_original_id_and_time_until_acknowledged(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));first=queue.next('candidate')
    clock.advance(10);resumed=ReferenceDelivery.open(first['reference'],clock=clock)
    second=resumed.next('candidate')
    assert second['delivery']==first['delivery'] and second['redelivered'] is True
    assert second['reference']==first['reference']
    ack=resumed.acknowledge('candidate',first['delivery']['delivery_id'],worker_receipt_sha256='a'*64)
    assert ack['role_cursors']['candidate']['cursor']==1 and ack['role_cursors']['control']['cursor']==0
    assert resumed.next('candidate')['status']=='empty'
    assert resumed.audit()['acknowledged_by_role']==dict(candidate=1,control=0,stress=0)


def test_acknowledgements_are_idempotent_and_conflicts_do_not_mutate_state(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));d=queue.next('control')['delivery']
    queue.acknowledge('control',d['delivery_id'],worker_receipt_sha256='a'*64);before=ref(queue)
    assert queue.acknowledge('control',d['delivery_id'],worker_receipt_sha256='a'*64)['stored'] is False
    with pytest.raises(ValueError,match='conflicting'):queue.acknowledge('control',d['delivery_id'],worker_receipt_sha256='b'*64)
    assert ref(queue)==before


def test_wrong_role_and_unknown_ack_cannot_advance_a_cursor(tmp_path):
    _,source,queue=make(tmp_path);queue.ingest(ref(source));d=queue.next('candidate')['delivery'];before=ref(queue)
    with pytest.raises(ValueError,match='wrong-role'):queue.acknowledge('stress',d['delivery_id'],worker_receipt_sha256='a'*64)
    with pytest.raises(ValueError,match='wrong-role'):queue.acknowledge('candidate','f'*64,worker_receipt_sha256='a'*64)
    with pytest.raises(ValueError,match='pending role'):queue.read('control',d['delivery_id'])
    assert ref(queue)==before


def test_history_survives_source_append_and_original_database_removal(tmp_path):
    clock,source,queue=make(tmp_path);original_ref=ref(source);queue.ingest(original_ref)
    d=queue.next('candidate')['delivery'];old=queue.read('candidate',d['delivery_id'])
    clock.advance(300);source.poll(Client(clock,revision=True))
    assert ref(source)['database_sha256']!=original_ref['database_sha256']
    assert queue.read('candidate',d['delivery_id'])['source_view']==old['source_view']
    queue.ingest(ref(source));last_ref=ref(queue);shutil.rmtree(source.root)
    resumed=ReferenceDelivery.open(last_ref,clock=clock)
    assert resumed.read('candidate',d['delivery_id'])['source_events']==old['source_events']
    assert resumed.audit()['source_events_checked']==10
    assert resumed.audit()['retained_source_integrity_pass'] is True


def test_bounded_partial_ingest_never_offers_an_unanchored_source_prefix(tmp_path):
    policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_source_events_per_batch=4)
    _,source,queue=make(tmp_path,policy=policy)
    first=queue.ingest(ref(source))
    assert first['source_events']==4 and queue.audit()['unresolved_source_attestations']==1
    for role in ROLES:assert queue.next(role)['status']=='source_attestation_incomplete'
    second=queue.ingest(ref(source));assert second['source_events']==6
    assert queue.audit()['unresolved_source_attestations']==0
    for role in ROLES:
        d=queue.next(role)['delivery'];assert d['batch_sequence']==1
        assert len(queue.read(role,d['delivery_id'])['source_events'])==4
        queue.acknowledge(role,d['delivery_id'],worker_receipt_sha256='a'*64)
        d=queue.next(role)['delivery'];assert d['batch_sequence']==2
        events=queue.read(role,d['delivery_id'])['source_events']
        assert [e['kind'] for e in events]==['forecast','forecast']


def test_batch_boundaries_never_split_a_poll_or_skip_forecasts(tmp_path):
    policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_source_events_per_batch=4)
    clock,source,queue=make(tmp_path,policy=policy);clock.advance(300);source.poll(Client(clock))
    assert [queue.ingest(ref(source))['source_events'] for _ in range(3)]==[4,6,10]
    assert queue.audit()['source_events_checked']==10
    assert queue.audit()['batches_checked']==3


def test_duplicate_source_checkpoint_is_noop_and_old_descriptor_is_rejected(tmp_path):
    clock,source,queue=make(tmp_path);initial=ref(source);first=queue.ingest(initial)
    assert queue.ingest(initial)['reference']==first['reference']
    clock.advance(300);source.poll(Client(clock));queue.ingest(ref(source));before=ref(queue)
    with pytest.raises(ValueError,match='database pin'):queue.ingest(initial)
    assert ref(queue)==before


def test_global_first_seen_and_revisions_remain_original_after_delivery(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));clock.advance(300)
    source.poll(Client(clock,revision=True));queue.ingest(ref(source))
    d=queue.next('candidate')['delivery'];queue.acknowledge('candidate',d['delivery_id'],worker_receipt_sha256='a'*64)
    d=queue.next('candidate')['delivery'];view=queue.read('candidate',d['delivery_id'])['source_view']
    rows=view['windows']['ETH/USDT']['derived']['rows']
    assert any(r['first_seen_at']<r['known_at'] for r in rows)
    assert all(r['first_seen_event_sequence']<=view['windows']['ETH/USDT']['event_seq'] for r in rows)


def test_missing_poll_slots_are_reported_and_do_not_become_verified_coverage(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));clock.advance(900);source.poll(Client(clock));queue.ingest(ref(source))
    audit=queue.audit()
    assert audit['missing_source_poll_slots']==2 and audit['source_poll_completeness_verified'] is False


def test_rate_limit_skips_and_cooldown_pauses_survive_retention(tmp_path):
    clock,source,queue=make(tmp_path,poll=False)
    client=Client(clock,failed='BTC/USDT');source.poll(client);queue.ingest(ref(source))
    assert client.calls==['BTC/USDT']
    d=queue.next('stress')['delivery'];packet=queue.read('stress',d['delivery_id'])
    response=[e['payload'] for e in packet['source_events'] if e['kind']=='source_response']
    assert [r['request_performed'] for r in response]==[True,False]
    clock.advance(900);source.poll(Client(clock));queue.ingest(ref(source))
    audit=queue.audit();assert audit['explicit_rate_pause_slots']==2 and audit['missing_source_poll_slots']==0


def test_stale_recovered_inputs_cannot_become_a_fresh_entry(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));clock.advance(610)
    d=queue.next('candidate')['delivery'];reader=DeliveredReferenceReader.open(queue,'candidate',d['delivery_id'],clock=clock)
    assert reader.status()['closed_candles_ready'] is False
    with pytest.raises(ValueError,match='stale'):reader.read_candles('ETH/USDT')
    assert len(reader.original_forecasts())==2 and all(f['usable_price_input_now'] is False for f in reader.original_forecasts())
    assert all(f['original']['payload']['predicted_at']<d['offered_at'] for f in reader.original_forecasts())


def test_no_network_request_is_made_by_ingest_delivery_or_replay(tmp_path,monkeypatch):
    clock,source,queue=make(tmp_path)
    def forbidden(*args):raise AssertionError('network request from delivery')
    monkeypatch.setattr('cryptoforge.reference_sources.PublicReferenceClient.fetch',forbidden)
    queue.ingest(ref(source));d=queue.next('control')['delivery']
    reader=DeliveredReferenceReader.open(queue,'control',d['delivery_id'],clock=clock)
    assert len(reader.read_candles('BTC/USDT'))==120
    queue.acknowledge('control',d['delivery_id'],worker_receipt_sha256='a'*64);queue.audit()


@pytest.mark.parametrize('kwargs',[{'maximum_source_events':4},{'maximum_source_bytes_per_batch':4096}])
def test_ingest_limits_preserve_atomic_empty_state(tmp_path,kwargs):
    policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,**kwargs)
    _,source,queue=make(tmp_path,policy=policy);before=ref(queue)
    with pytest.raises(ValueError,match='budget'):queue.ingest(ref(source))
    assert ref(queue)==before and queue.audit()['source_events_checked']==0


def test_delivery_byte_limit_cannot_be_bypassed_by_a_successful_offer(tmp_path):
    _,source,queue=make(tmp_path,policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_delivery_bytes=4096))
    queue.ingest(ref(source));d=queue.next('candidate')['delivery']
    with pytest.raises(ValueError,match='payload budget'):queue.read('candidate',d['delivery_id'])
    assert queue.receipt()['role_cursors']['candidate']['cursor']==0


def test_disk_floor_blocks_before_any_new_mutation(tmp_path,monkeypatch):
    _,source,queue=make(tmp_path);reference=ref(source)
    monkeypatch.setattr('cryptoforge.reference_delivery.shutil.disk_usage',lambda _:SimpleNamespace(free=2048*1024**2))
    with pytest.raises(ValueError,match='reserve'):queue.ingest(reference)


def test_prospective_registration_and_original_window_are_enforced(tmp_path):
    clock,source,queue=make(tmp_path,prospective=True,poll=False)
    with pytest.raises(ValueError,match='window'):queue.next('candidate')
    with pytest.raises(ValueError,match='window'):queue.ingest(ref(source))
    clock.advance(60);source.poll(Client(clock));queue.ingest(ref(source))
    assert queue.audit()['scope']=='prospective'
    with pytest.raises(ValueError,match='empty prospective'):ReferenceDelivery.create(tmp_path/'late',ref(source),clock=clock)
    assert not (tmp_path/'late').exists()


@pytest.mark.parametrize('late_step',['manifest.json','registered.json'])
def test_late_durable_registration_has_no_valid_ready_pin(tmp_path,monkeypatch,late_step):
    import cryptoforge.reference_delivery as module
    clock=Clock();source=ReferenceLedger.create(tmp_path/'source',clock=clock,start=clock()+timedelta(seconds=60))
    original=module._write_new
    def late(path,value):
        pin=original(path,value)
        if path.name==late_step:clock.advance(61)
        return pin
    monkeypatch.setattr(module,'_write_new',late)
    with pytest.raises(ValueError,match='missed original start'):ReferenceDelivery.create(tmp_path/'queue',ref(source),clock=clock)
    assert not (tmp_path/'queue/registered.json').exists()


def test_diagnostic_source_never_becomes_a_prospective_delivery(tmp_path):
    clock,source,_=make(tmp_path)
    with pytest.raises(ValueError,match='empty prospective'):ReferenceDelivery.create(tmp_path/'bad',ref(source),clock=clock)


def test_source_substitution_is_rejected_before_any_archive_mutation(tmp_path):
    clock,_,queue=make(tmp_path);other=ReferenceLedger.create(tmp_path/'other',clock=clock)
    before=ref(queue)
    with pytest.raises(ValueError,match='substitute'):queue.ingest(ref(other))
    assert ref(queue)==before


def test_rehashed_cursor_and_ack_projections_are_not_trusted(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));reference=ref(queue)
    db=sqlite3.connect(queue.path);db.execute("UPDATE cursors SET cursor=1 WHERE role='candidate'");db.commit();db.close()
    reference['database_sha256']=file_sha(queue.path,queue.policy.maximum_database_bytes)
    with pytest.raises(ValueError,match='cursor projection'):ReferenceDelivery.open(reference,clock=clock)


def test_rehashed_false_original_forecast_is_detected_without_source_database(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));reference=ref(queue);shutil.rmtree(source.root)
    db=sqlite3.connect(queue.path)
    for table in ('source_events','events','batches'):db.execute('DROP TRIGGER '+table+'_no_update')
    seq,raw,previous=db.execute("SELECT seq,payload,previous FROM source_events ORDER BY seq DESC LIMIT 1").fetchone()
    p=parse(raw);p['payload']['long_probability']=.99
    source_head=digest(canonical(dict(sequence=seq,kind='forecast',payload=p,previous_sha256=previous)))
    db.execute('UPDATE source_events SET payload=?,sha=? WHERE seq=?',(canonical(p),source_head,seq))
    seq,raw,previous=db.execute('SELECT seq,payload,previous FROM events').fetchone();event=parse(raw)
    event['batch']['source_end_head']=source_head;event['batch']['source_reference']['head_sha256']=source_head
    batch_sha=digest(canonical(event['batch']));event['batch_sha256']=batch_sha
    head=digest(canonical(dict(sequence=seq,kind='ingest',payload=event,previous_sha256=previous)))
    db.execute('UPDATE batches SET payload=?,sha=?',(canonical(event['batch']),batch_sha))
    db.execute('UPDATE events SET payload=?,sha=?',(canonical(event),head))
    db.execute('UPDATE state SET head=?,source_head=?',(head,source_head))
    for table in ('source_events','events','batches'):db.execute(SQL[table+'_no_update'])
    db.commit();db.close();reference.update(database_sha256=file_sha(queue.path,queue.policy.maximum_database_bytes),head_sha256=head)
    with pytest.raises(ValueError,match='forecast/source linkage'):ReferenceDelivery.open(reference,clock=clock)


def test_append_only_tables_reject_sql_updates_and_deletes(tmp_path):
    _,source,queue=make(tmp_path);queue.ingest(ref(source))
    d=queue.next('candidate')['delivery'];queue.acknowledge('candidate',d['delivery_id'],worker_receipt_sha256='a'*64)
    db=sqlite3.connect(queue.path)
    for table in ('events','source_events','batches','acks'):
        for verb in ('UPDATE','DELETE'):
            sql=f'UPDATE {table} SET rowid=rowid' if verb=='UPDATE' and table!='acks' else f'DELETE FROM {table}'
            if verb=='UPDATE' and table=='acks':sql='UPDATE acks SET role=role'
            with pytest.raises(sqlite3.IntegrityError):db.execute(sql)
            db.rollback()
    db.close()


def test_queue_and_delivered_reader_reject_backwards_clocks(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));d=queue.next('candidate')['delivery']
    reader=DeliveredReferenceReader.open(queue,'candidate',d['delivery_id'],clock=clock)
    clock.advance(10);reader.status();queue.receipt();clock.advance(-1)
    with pytest.raises(ValueError,match='backwards'):reader.status()
    with pytest.raises(ValueError,match='backwards'):queue.next('candidate')


def test_offline_cli_after_source_removal_never_accepts_as_of_override(tmp_path):
    clock=Clock();clock.now=datetime.now(UTC)-timedelta(minutes=1)
    _,source,queue=make(tmp_path,clock=clock);queue.ingest(ref(source));reference=ref(queue);shutil.rmtree(source.root)
    path=tmp_path/'reference.json';path.write_bytes(canonical(reference))
    command=[sys.executable,'scripts/deliver_reference_sources.py','audit','--reference-file',str(path)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['retained_source_integrity_pass'] is True
    rejected=subprocess.run(command+['--as-of',clock().isoformat()],capture_output=True,text=True,timeout=15)
    assert rejected.returncode!=0 and 'unrecognized arguments' in rejected.stderr


def test_transaction_fault_rolls_back_source_batch_event_and_cursor_together(tmp_path,monkeypatch):
    clock,source,queue=make(tmp_path);before=ref(queue);original=queue._commit
    def faulty(kind,payload,apply):
        def fail(db,event_seq):apply(db,event_seq);raise RuntimeError('injected pre-commit crash')
        return original(kind,payload,fail)
    monkeypatch.setattr(queue,'_commit',faulty)
    with pytest.raises(RuntimeError):queue.ingest(ref(source))
    restored=ReferenceDelivery.open(before,clock=clock)
    assert restored.audit()['source_events_checked']==0 and restored.audit()['queue_events_checked']==0


def test_hard_sqlite_cap_never_advances_the_archive_on_storage_failure(tmp_path):
    clock,source,queue=make(tmp_path,policy=DeliveryPolicy(maximum_database_bytes=65536))
    queue.ingest(ref(source));before=ref(queue)
    clock.advance(300);source.poll(Client(clock))
    with pytest.raises(sqlite3.DatabaseError):queue.ingest(ref(source))
    restored=ReferenceDelivery.open(before,clock=clock)
    assert restored.audit()['source_events_checked']==6
    assert restored.path.stat().st_size<=65536


def test_full_replay_detects_a_rehashed_ack_projection(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));d=queue.next('candidate')['delivery']
    queue.acknowledge('candidate',d['delivery_id'],worker_receipt_sha256='a'*64);reference=ref(queue)
    db=sqlite3.connect(queue.path);db.execute('DROP TRIGGER acks_no_update')
    raw,=db.execute('SELECT payload FROM acks').fetchone();value=parse(raw);value['worker_receipt_sha256']='b'*64
    db.execute('UPDATE acks SET payload=?',(canonical(value),));db.execute(SQL['acks_no_update']);db.commit();db.close()
    reference['database_sha256']=file_sha(queue.path,queue.policy.maximum_database_bytes)
    with pytest.raises(ValueError,match='acknowledgement projection'):ReferenceDelivery.open(reference,clock=clock)


def test_known_ancestor_recovery_after_lost_offer_receipt_is_explicit_and_idempotent(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));known=ref(queue)
    offered=queue.next('candidate');new=offered['reference']
    with pytest.raises(ValueError,match='database pin'):ReferenceDelivery.open(known,clock=clock)
    recovered=ReferenceDelivery.recover(known,clock=clock)
    assert recovered['reference']==new and recovered['recovery']['prior_database_bytes_reproduced'] is False
    resumed=ReferenceDelivery.open(recovered['reference'],clock=clock)
    assert resumed.next('candidate')['delivery']==offered['delivery']
    assert ReferenceDelivery.recover(known,clock=clock)['reference']==new


def test_recovery_refuses_unknown_ancestor_without_mutating_history(tmp_path):
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));before=ref(queue)
    fake=dict(before,head_sha256='f'*64)
    with pytest.raises(ValueError,match='ancestor'):ReferenceDelivery.recover(fake,clock=clock)
    assert ref(queue)==before


def test_real_process_death_after_commit_before_receipt_is_recoverable(tmp_path):
    clock=Clock();clock.now=datetime.now(UTC)-timedelta(seconds=30)
    _,source,queue=make(tmp_path,clock=clock);queue.ingest(ref(source));known=ref(queue)
    path=tmp_path/'known.json';path.write_bytes(canonical(known))
    code='''import json,os,sys
from pathlib import Path
from cryptoforge.reference_delivery import ReferenceDelivery
q=ReferenceDelivery.open(json.loads(Path(sys.argv[1]).read_bytes()))
q._receipt=lambda:os._exit(42)
q.next('candidate')
'''
    result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode==42,result.stderr
    clock.now=datetime.now(UTC)
    recovered=ReferenceDelivery.recover(known,clock=clock)
    resumed=ReferenceDelivery.open(recovered['reference'],clock=clock)
    result=resumed.next('candidate');assert result['redelivered'] is True
    assert result['events']==2 and result['role_cursors']['candidate']['cursor']==0
    assert len(resumed.read('candidate',result['delivery']['delivery_id'])['source_events'])==6


def test_locks_and_stale_writers_do_not_merge_unreviewed_state(tmp_path):
    import fcntl,os
    clock,source,queue=make(tmp_path);known=ref(queue);stale=ReferenceDelivery.open(known,clock=clock)
    fd=os.open(queue.root/'writer.lock',os.O_RDONLY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):queue.ingest(ref(source))
    finally:os.close(fd)
    queue.ingest(ref(source))
    with pytest.raises(ValueError,match='outside this writer'):stale.next('candidate')


def test_source_rewind_and_other_pair_windows_cannot_be_adopted(tmp_path):
    clock,source,queue=make(tmp_path,poll=False)
    source.poll(Client(clock));old=ref(source);old_bytes=source.path.read_bytes()
    source.forecast('ETH/USDT');queue.ingest(ref(source))
    source.path.write_bytes(old_bytes)
    with pytest.raises(ValueError,match='rewound'):queue.ingest(old)


def test_delivered_reader_keeps_precision_and_model_scope(tmp_path):
    from decimal import localcontext
    clock,source,queue=make(tmp_path);queue.ingest(ref(source));d=queue.next('stress')['delivery']
    reader=DeliveredReferenceReader.open(queue,'stress',d['delivery_id'],clock=clock)
    p=next(v['original']['payload'] for v in reader.original_forecasts() if v['original']['payload']['pair']=='ETH/USDT')
    with localcontext() as context:
        context.prec=6
        assert list(reader.features('ETH/USDT'))==p['features'] and context.prec==6
    for kwargs in ({'limit':119},{'limit':True},{'timeframe':'1m'}):
        with pytest.raises(ValueError,match='bounded120'):reader.read_candles('ETH/USDT',**kwargs)
    with pytest.raises(ValueError,match='bounded120'):reader.read_candles('SOL/USDT')


def test_runtime_drift_is_rejected_before_queue_mutation(tmp_path,monkeypatch):
    import cryptoforge.reference_delivery as module
    _,source,queue=make(tmp_path);source_ref=ref(source)
    paths=module._paths();copied=tmp_path/'backend.py';copied.write_bytes(paths['backend.py'].read_bytes());paths['backend.py']=copied
    monkeypatch.setattr(module,'_paths',lambda:paths);copied.write_bytes(copied.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='runtime'):queue.ingest(source_ref)


def test_scratch_limit_is_checked_before_committing_an_unreplayable_batch(tmp_path):
    clock,source,queue=make(tmp_path,policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_scratch_database_bytes=65536))
    before=ref(queue)
    with pytest.raises(sqlite3.DatabaseError):queue.ingest(ref(source))
    assert ReferenceDelivery.open(before,clock=clock).audit()['source_events_checked']==0


def test_hot_journal_after_real_process_death_requires_explicit_host_recovery(tmp_path):
    clock=Clock();clock.now=datetime.now(UTC)-timedelta(seconds=30)
    _,source,queue=make(tmp_path,clock=clock);known=ref(queue)
    payload=tmp_path/'args.json';payload.write_bytes(canonical(dict(queue=known,source=ref(source))))
    code='''import json,os,sys
from pathlib import Path
from cryptoforge.reference_delivery import ReferenceDelivery
a=json.loads(Path(sys.argv[1]).read_bytes());q=ReferenceDelivery.open(a['queue'])
original=q._commit
def fault(kind,payload,apply):
 def kill(db,seq):apply(db,seq);os._exit(42)
 return original(kind,payload,kill)
q._commit=fault;q.ingest(a['source'])
'''
    result=subprocess.run([sys.executable,'-c',code,str(payload)],capture_output=True,text=True,timeout=15)
    assert result.returncode==42,result.stderr
    assert Path(str(queue.path)+'-journal').exists()
    clock.now=datetime.now(UTC)
    with pytest.raises(ValueError,match='unfinished'):ReferenceDelivery.recover(known,clock=clock)
