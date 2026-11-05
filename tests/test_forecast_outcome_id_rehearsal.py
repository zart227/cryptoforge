from datetime import UTC, datetime, timedelta
import multiprocessing
import os
import sqlite3
import json

import pytest

from cryptoforge.forecast_outcome_id_rehearsal import append_synthetic_outcome, create_sandbox
from test_forecast_retention_rehearsal import setup, run, sha


def prepare(data):
    run(data);root=data[-1];receipt=root/'output/receipt.json';sandbox=root/'sandbox'
    create_sandbox(receipt,sha(receipt),sandbox,minimum_free_bytes=0)
    reg=sandbox/'registration.json'
    return reg,sha(reg),sandbox


def event(fid='a',value=1):return {'scope':'synthetic_rehearsal_only','forecast_id':fid,'event_id':f'event-{value}','value':value}


def append(reg,pin,payload,when=None,**kwargs):
    now=datetime.now(UTC)+timedelta(minutes=2)
    return append_synthetic_outcome(reg,pin,payload['forecast_id'],payload,(when or now).isoformat(),
                                    now=now,minimum_free_bytes=0,**kwargs)


def _writer(reg,pin,value,when,queue):
    try:queue.put(('ok',append_synthetic_outcome(reg,pin,'b',event('b',value),when.isoformat(),now=when,minimum_free_bytes=0,busy_timeout_seconds=20)))
    except Exception as exc:queue.put(('error',str(exc)))


def _crash_writer(reg,pin,after_commit,when):
    import cryptoforge.forecast_outcome_id_rehearsal as module
    def crash(db):
        if after_commit:db.commit()
        os._exit(43 if after_commit else 42)
    module._commit=crash
    append(reg,pin,event('b',987),when=when)


def test_first_ids_use_both_parts_and_retry_is_idempotent(setup):
    reg,pin,root=prepare(setup);archive_before=sha(root/'archive.sqlite')
    when=datetime.now(UTC)+timedelta(minutes=1)
    r1=append(reg,pin,event('a',1),when=when);r2=append(reg,pin,event('b',2),when=when);r3=append(reg,pin,event('b',2),when=when)
    assert r1['id']==5 and r2['id']==6 and r3=={'status':'already_recorded','id':6,'synthetic_only':True}
    assert sha(root/'archive.sqlite')==archive_before
    with sqlite3.connect(root/'active.sqlite') as db:
        assert db.execute('select id from primary_forecast_outcomes order by id').fetchall()==[(3,),(4,),(5,),(6,)]


def test_concurrent_processes_have_unique_increasing_ids(setup):
    reg,pin,root=prepare(setup);ctx=multiprocessing.get_context('fork');q=ctx.Queue()
    when=datetime.now(UTC)+timedelta(minutes=2)
    workers=[ctx.Process(target=_writer,args=(reg,pin,i,when,q)) for i in range(4)]
    for p in workers:p.start()
    for p in workers:p.join(30);assert p.exitcode==0
    results=[q.get(timeout=2) for _ in workers]
    assert all(k=='ok' for k,v in results),results
    assert sorted(v['id'] for k,v in results)==[5,6,7,8]
    with sqlite3.connect(root/'active.sqlite') as db:
        assert db.execute("select count(distinct id) from primary_forecast_outcomes where forecast='b'").fetchone()[0]==4


def test_concurrent_redelivery_records_same_event_once(setup):
    reg,pin,root=prepare(setup);ctx=multiprocessing.get_context('fork');q=ctx.Queue()
    when=datetime.now(UTC)+timedelta(minutes=2)
    workers=[ctx.Process(target=_writer,args=(reg,pin,42,when,q)) for _ in range(4)]
    for p in workers:p.start()
    for p in workers:p.join(30);assert p.exitcode==0
    results=[q.get(timeout=2) for _ in workers]
    assert all(k=='ok' and v['id']==5 for k,v in results),results
    assert sorted(v['status'] for k,v in results)==['already_recorded']*3+['recorded']
    with sqlite3.connect(root/'active.sqlite') as db:
        assert db.execute("select count(*) from primary_forecast_outcomes where forecast='b'").fetchone()[0]==1


@pytest.mark.parametrize('after_commit',[False,True])
def test_process_death_before_or_after_commit_and_retry(setup,after_commit):
    reg,pin,root=prepare(setup);ctx=multiprocessing.get_context('fork')
    when=datetime.now(UTC)+timedelta(minutes=1)
    worker=ctx.Process(target=_crash_writer,args=(reg,pin,after_commit,when));worker.start();worker.join(30)
    assert worker.exitcode==(43 if after_commit else 42)
    with sqlite3.connect(root/'active.sqlite') as db:
        present=db.execute("select count(*) from primary_forecast_outcomes where forecast='b'").fetchone()[0]
    assert present==int(after_commit)
    result=append(reg,pin,event('b',987),when=when)
    assert result['id']==5 and result['status']==('already_recorded' if after_commit else 'recorded')


def test_reject_non_synthetic_future_backdate_and_unknown(setup):
    reg,pin,root=prepare(setup);now=datetime.now(UTC)+timedelta(minutes=2)
    with pytest.raises(ValueError,match='synthetic rehearsal payload'):
        append_synthetic_outcome(reg,pin,'a',{'forecast_id':'a'},now.isoformat(),now=now,minimum_free_bytes=0)
    with pytest.raises(ValueError,match='future observation'):
        append_synthetic_outcome(reg,pin,'a',event('a'),(now+timedelta(seconds=1)).isoformat(),now=now,minimum_free_bytes=0)
    with pytest.raises(ValueError,match='exactly one forecast'):append(reg,pin,event('missing'))
    with pytest.raises(ValueError,match='before forecast target'):
        append(reg,pin,event('a'),when=now-timedelta(days=30))
    append(reg,pin,event('a',1),when=now-timedelta(minutes=1))
    with pytest.raises(ValueError,match='backdated'):append(reg,pin,event('a',2),when=now-timedelta(minutes=2))


def test_existing_collisions_archive_modifications_and_storage_limit_reject(setup):
    reg,pin,root=prepare(setup)
    with sqlite3.connect(root/'active.sqlite') as db:
        db.execute("insert into primary_forecast_outcomes values (1,'b','bad','2026-01-01T00:00:00+00:00','{}')")
    with pytest.raises(ValueError,match='overlapping outcome ids'):append(reg,pin,event('b'))
    with pytest.raises(ValueError,match='storage budget'):append(reg,pin,event('b'),maximum_active_bytes=1)
    with (root/'archive.sqlite').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='archive pin mismatch'):append(reg,pin,event('b'))


def test_failed_copy_does_not_replace_previous_sandbox(setup):
    reg,pin,root=prepare(setup);receipt=setup[-1]/'output/receipt.json'
    with pytest.raises(ValueError,match='new separate'):create_sandbox(receipt,sha(receipt),root,minimum_free_bytes=0)
    assert sha(reg)==pin
    with pytest.raises(ValueError,match='disk reserve'):
        create_sandbox(receipt,sha(receipt),setup[-1]/'no-space',minimum_free_bytes=10**18)
    assert not (setup[-1]/'no-space').exists()


def test_retry_after_another_correction_uses_original_event_id(setup):
    reg,pin,_=prepare(setup);now=datetime.now(UTC)+timedelta(minutes=2)
    first=append(reg,pin,event('b',1),when=now)
    second=append(reg,pin,event('b',2),when=now)
    replay=append(reg,pin,event('b',1),when=now)
    assert [first['id'],second['id'],replay['id']]==[5,6,5]
    assert replay['status']=='already_recorded'


def test_changed_event_with_same_identity_is_rejected(setup):
    reg,pin,_=prepare(setup);now=datetime.now(UTC)+timedelta(minutes=1)
    append(reg,pin,event('b',1),when=now)
    changed={**event('b',1),'value':'different'}
    with pytest.raises(ValueError,match='identity conflict'):append(reg,pin,changed,when=now)
    with pytest.raises(ValueError,match='identity conflict'):append(reg,pin,event('b',1),when=now+timedelta(seconds=1))


def test_duplicate_retry_rechecks_archive_before_return(setup,monkeypatch):
    import cryptoforge.forecast_outcome_id_rehearsal as module
    reg,pin,root=prepare(setup);now=datetime.now(UTC)+timedelta(minutes=1)
    append(reg,pin,event('b',1),when=now)
    original=module._file_sha; calls=0
    def changed_archive(path):
        nonlocal calls
        if path==root/'archive.sqlite':
            calls+=1
            if calls==2:return '0'*64
        return original(path)
    monkeypatch.setattr(module,'_file_sha',changed_archive)
    with pytest.raises(ValueError,match='inputs or reserve changed'):append(reg,pin,event('b',1),when=now)


def test_outcome_id_exhaustion_is_rejected(setup):
    reg,_,root=prepare(setup)
    with sqlite3.connect(root/'archive.sqlite') as db:
        db.execute('insert into primary_forecast_outcomes values (?,?,?,?,?)',
                   (2**63-1,'a','x','2026-01-01T00:00:00+00:00','{}'))
    registration=json.loads(reg.read_text());registration['archive_sha256']=sha(root/'archive.sqlite')
    reg.write_text(json.dumps(registration));pin=sha(reg)
    with pytest.raises(ValueError,match='id space exhausted'):append(reg,pin,event('b'))
    with sqlite3.connect(root/'active.sqlite') as db:
        assert db.execute("select count(*) from primary_forecast_outcomes where forecast='b'").fetchone()[0]==0


def test_busy_writer_times_out_without_partial_outcome(setup):
    reg,pin,root=prepare(setup)
    with sqlite3.connect(root/'active.sqlite',isolation_level=None) as locked:
        locked.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError,match='locked'):
            append(reg,pin,event('b'),busy_timeout_seconds=1)
        locked.rollback()
    with sqlite3.connect(root/'active.sqlite') as db:
        assert db.execute("select count(*) from primary_forecast_outcomes where forecast='b'").fetchone()[0]==0
