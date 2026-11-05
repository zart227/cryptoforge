"""Ported durable archive contracts for the separately registered v2 producer."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import tracemalloc

import pytest

from cryptoforge.native_paper_archive_v2 import NativeArchivePolicy, NativePaperArchiveV2 as NativePaperArchive
from cryptoforge.paper_producer_v2 import register_kernel
from test_paper_wallet import START,Clock,config,market


WORKER_POLICY=dict(enabled=True,status='frozen',runtime=dict(maximum_new_signals_per_tick=2,wall_budget_seconds=10),
    exits=dict(stop_fraction='.04',maximum_hold_seconds=3600,shared_exit_signal=False))


def policy(**changes):
    return replace(NativeArchivePolicy(shards=4,maximum_shard_bytes=1024*1024,
        maximum_active_bytes=1024*1024,maximum_active_rows=32,maximum_records=10000,
        maximum_row_bytes=16384,maximum_batch_bytes=65536,maximum_total_bytes=32*1024*1024,
        minimum_free_disk_bytes=32*1024*1024,minimum_available_memory_bytes=1),**changes)


def setup(tmp_path,*,paper_config=None,**changes):
    clock=Clock();clock.now=START-timedelta(seconds=10)
    kernel=register_kernel(tmp_path/'kernel',candidate_sha='b'*64,study_protocol_sha256='a'*64,
        role='candidate',config=paper_config or config(),worker_policy=WORKER_POLICY,
        backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY':'synthetic-key'},
        start=START,end=START+timedelta(hours=1),closeout_seconds=30,clock=clock)
    state=NativePaperArchive.create(tmp_path/'owned',source_protocol_sha256='a'*64,
        kernel_root=kernel['root'],expected_kernel_contract_sha256=kernel['contract_sha256'],
        expected_kernel_registration_sha256=kernel['registration_sha256'],policy=policy(**changes),
        market=lambda pair:market(clock,pair),clock=clock)
    clock.now=START
    return state,clock


def fill(state,clock,identity,side,price='100'):
    state.wallet.enqueue(identity,'AAA/USDT',side,created_at=clock.now);clock.advance()
    return state.wallet.execute(identity,*market(clock,price=price))


def read(state,seal):
    return NativePaperArchive.reader(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,
        expected_seal_sha256=seal['seal_sha256'])


def test_compaction_preserves_all_rows_and_monotonic_native_ids(tmp_path):
    state,clock=setup(tmp_path)
    for _ in range(10):state.wallet.mark({},{});state.worker._event({'n':_});clock.advance()
    state.compact()
    with state.wallet._db() as db:assert db.execute('SELECT id FROM marks').fetchall()==[(10,)]
    assert [r[0] for r in state.iter_rows('wallet.marks')]==list(range(1,11))
    state.wallet.mark({},{});state.worker._event({'n':10})
    state.compact()
    with state.wallet._db() as db:assert db.execute('SELECT id FROM marks').fetchall()==[(11,)]
    assert [r[0] for r in state.iter_rows('worker.worker_events')]==list(range(1,12))
    sealed=state.seal();reader=read(state,sealed)
    result=reader.audit()
    assert result['source_counts']['wallet.marks']==11
    assert result['native_source_integrity_pass'] and not result['paper_evidence_pass']
    assert not result['economic_profitability_established'] and not result['live_admission_granted']


def test_fifo_cash_open_fills_and_day_anchors_survive_cleanup(tmp_path):
    state,clock=setup(tmp_path)
    fill(state,clock,'buy','Buy')
    fill(state,clock,'sell','Sell',price='98')
    q,r=market(clock,price='98');state.wallet.mark({q['pair']:q},{r['pair']:r})
    before=state.wallet.snapshot()
    state.compact();after=state.wallet.snapshot()
    assert after['cash']==before['cash'] and after['open_lots']==before['open_lots']
    assert after['history_scope']=='bounded_active_projection_not_full_history'
    assert [r[0] for r in state.iter_rows('wallet.fills')]==['buy','sell']
    segments=list(state.iter_rows('wallet.closed_segments'))
    assert len(segments)==1 and Decimal(json.loads(segments[0][1])['net_pnl'])<0
    assert list(state.iter_rows('wallet.day_anchors'))


def test_terminal_intent_is_not_reexecuted_after_it_leaves_active_store(tmp_path):
    state,clock=setup(tmp_path)
    state.wallet.enqueue('expired','AAA/USDT','Buy',created_at=clock.now)
    clock.advance(31)
    assert state.wallet.execute('expired',*market(clock))['status']=='rejected'
    state.compact()
    with state.wallet._db() as db:assert db.execute('SELECT count(*) FROM intents').fetchone()[0]==0
    assert state.wallet.execute('expired',*market(clock))==dict(status='rejected',duplicate=True)
    assert not state.wallet.enqueue('expired','AAA/USDT','Buy',created_at=START)
    with pytest.raises(ValueError,match='cannot change'):
        state.wallet.enqueue('expired','BBB/USDT','Buy',created_at=START)


def test_pending_native_intent_and_original_link_remain_available(tmp_path):
    state,clock=setup(tmp_path)
    assert state.worker._enqueue('pending','AAA/USDT','Buy',clock.now,{'source_deadline':(clock.now+timedelta(seconds=30)).isoformat()},source_key='prediction')
    state.compact()
    assert state.wallet.pending_intents()[0]['id']=='pending'
    assert state.lookup('worker.intent_links','pending')
    assert state.lookup('worker.seen_predictions','prediction')
    assert list(state.iter_rows('wallet.intents'))[0][5]=='pending'
    with state.worker._db() as db:assert db.execute('SELECT count(*) FROM seen_predictions').fetchone()[0]==0
    clock.advance()
    assert state.wallet.execute('pending',*market(clock))['status']=='filled'


def test_worker_seen_history_prevents_repeated_predictions_after_restart(tmp_path):
    state,clock=setup(tmp_path)
    prediction=dict(candidate_sha256='b'*64,opportunity='rejected',predicted_at=clock.now.isoformat(),
        observed_at=clock.now.isoformat(),would_enter=False,pair='AAA/USDT')
    state.worker.tick([prediction],window_start=START,window_end=START+timedelta(hours=1),entry_cutoff=START+timedelta(hours=1)-timedelta(seconds=30))
    state.compact()
    resumed=NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,
        market=lambda pair:market(clock,pair),clock=clock)
    prediction['would_enter']=True
    result=resumed.worker.tick([prediction],window_start=START,window_end=START+timedelta(hours=1),entry_cutoff=START+timedelta(hours=1)-timedelta(seconds=30))
    assert result['new_intents']==0 and resumed.wallet.pending_intents()==[]
    identity=hashlib.sha256(('b'*64+'|rejected').encode()).hexdigest()
    assert resumed.lookup('worker.seen_predictions',identity)[1]=='candidate_rejected'


@pytest.mark.parametrize('stage',['after_archive_commit','before_projection_commit','after_projection_commit'])
def test_actual_process_death_at_compaction_boundaries_never_loses_native_rows(tmp_path,stage):
    state,clock=setup(tmp_path)
    for i in range(6):state.wallet.mark({},{});state.worker._event({'n':i});clock.advance()
    code='''
import os,sys
from cryptoforge.native_paper_archive_v2 import NativePaperArchiveV2 as NativePaperArchive
state=NativePaperArchive.resume(sys.argv[1],expected_manifest_sha256=sys.argv[2],expected_ready_sha256=sys.argv[4],market=lambda pair:None)
def killed(stage):
    if stage==sys.argv[3]:os._exit(81)
state._stage=killed
state.compact()
'''
    result=subprocess.run([sys.executable,'-c',code,str(state.root),state.manifest_sha256,stage,state.ready_sha256],timeout=30)
    assert result.returncode==81
    resumed=NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,
        market=lambda pair:market(clock,pair),clock=clock)
    resumed.compact()
    assert [r[0] for r in resumed.iter_rows('wallet.marks')]==list(range(1,7))
    assert [r[0] for r in resumed.iter_rows('worker.worker_events')]==list(range(1,7))
    resumed.wallet.mark({},{});resumed.compact()
    assert [r[0] for r in resumed.iter_rows('wallet.marks')]==list(range(1,8))


def test_archive_write_failure_does_not_remove_active_rows(tmp_path,monkeypatch):
    state,clock=setup(tmp_path)
    for _ in range(4):state.wallet.mark({},{})
    before=(state.root/'wallet.sqlite').read_bytes()
    def failed(*_):raise OSError('archive unavailable')
    monkeypatch.setattr(state,'_append_batch',failed)
    with pytest.raises(OSError):state.compact()
    assert (state.root/'wallet.sqlite').read_bytes()==before


def test_native_changed_after_archive_commit_cannot_be_silently_pruned(tmp_path,monkeypatch):
    state,clock=setup(tmp_path);state.wallet.mark({},{})
    def change(stage):
        if stage=='after_archive_commit':
            with state.wallet._db() as db:db.execute('UPDATE marks SET payload=payload||?',(' ',))
    monkeypatch.setattr(state,'_stage',change)
    with pytest.raises(ValueError,match='changed during archival'):state.compact()
    with state.wallet._db() as db:assert db.execute('SELECT count(*) FROM marks').fetchone()[0]==1


def test_global_record_budget_survives_shards_and_resume(tmp_path):
    state,clock=setup(tmp_path,maximum_records=3)
    for i in range(5):state.worker._seen(str(i),'candidate_rejected')
    with pytest.raises(ValueError,match='record budget'):state.compact()
    with state.worker._db() as db:assert db.execute('SELECT count(*) FROM seen_predictions').fetchone()[0]==5
    resumed=NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,market=lambda p:None)
    with pytest.raises(ValueError,match='record budget'):resumed.compact()


@pytest.mark.parametrize('mutation',['missing','changed','extra','hardlink','symlink','schema','manifest'])
def test_archive_source_tampering_never_returns_integrity_pass(tmp_path,mutation):
    state,clock=setup(tmp_path);state.wallet.mark({},{})
    seal=state.seal();path=state._path(0)
    if mutation=='missing':path.unlink()
    if mutation=='changed':
        with sqlite3.connect(path) as db:db.execute('UPDATE head SET sha=?',('f'*64,))
    if mutation=='extra':(state.root/'archive'/'extra.sqlite').write_bytes(b'')
    if mutation=='hardlink':os.link(path,tmp_path/'alias')
    if mutation=='symlink':
        target=tmp_path/'saved';path.replace(target);path.symlink_to(target)
    if mutation=='schema':
        with sqlite3.connect(path) as db:db.execute('CREATE VIEW forged AS SELECT 1')
    if mutation=='manifest':(state.root/'manifest.json').write_text('{}')
    with pytest.raises((ValueError,OSError)):read(state,seal).audit()


def test_deleted_archive_index_row_is_not_interpreted_as_unseen_prediction(tmp_path):
    state,clock=setup(tmp_path);state.worker._seen('old','candidate_rejected');state.compact()
    key='old';bucket=state._bucket('worker.seen_predictions',key)
    with sqlite3.connect(state._path(bucket)) as db:db.execute('DELETE FROM records')
    with pytest.raises(ValueError,match='counter/head'):state.lookup('worker.seen_predictions','old')


def test_lost_high_water_anchor_blocks_restart_without_repair(tmp_path):
    state,clock=setup(tmp_path);state.wallet.mark({},{});state.compact()
    with state.wallet._db() as db:db.execute('DELETE FROM marks')
    with pytest.raises(ValueError,match='high-water'):
        NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,market=lambda p:None)


def test_reset_checkpoint_cannot_hide_lost_original_id_anchor(tmp_path):
    state,clock=setup(tmp_path);state.wallet.mark({},{});state.compact()
    with state.wallet._db() as db:db.execute('DELETE FROM marks')
    with sqlite3.connect(state.root/'checkpoint.sqlite') as db:db.execute('UPDATE checkpoint SET watermarks=?',('{}',))
    with pytest.raises(ValueError,match='high-water'):
        NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,market=lambda p:None)


def test_reader_is_read_only_and_sealed_writers_stay_closed(tmp_path):
    state,clock=setup(tmp_path);state.wallet.mark({},{})
    seal=state.seal()
    before={str(p.relative_to(state.root)):p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
    assert read(state,seal).audit()['source_counts']['wallet.marks']==1
    assert before=={str(p.relative_to(state.root)):p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='sealed'):state.wallet.mark({},{})
    with pytest.raises(ValueError,match='sealed'):
        NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,market=lambda p:None)


def test_changed_manifest_during_stream_blocks_final_verification(tmp_path):
    state,clock=setup(tmp_path)
    for _ in range(3):state.wallet.mark({},{})
    reader=read(state,state.seal());stream=reader.iter_rows('wallet.marks')
    assert next(stream)[0]==1
    (state.root/'manifest.json').write_text('{}')
    with pytest.raises(ValueError):list(stream)


def test_schema_missing_table_cannot_be_adopted_as_new_native_state(tmp_path):
    state,clock=setup(tmp_path)
    with state.wallet._db() as db:db.execute('DROP TABLE intents')
    before=(state.root/'wallet.sqlite').read_bytes()
    with pytest.raises(ValueError,match='schema'):
        NativePaperArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,expected_ready_sha256=state.ready_sha256,market=lambda p:None)
    assert (state.root/'wallet.sqlite').read_bytes()==before


@pytest.mark.parametrize('changes',[dict(shards=3),dict(maximum_active_rows=2),dict(maximum_shard_bytes=65537),
    dict(maximum_row_bytes=300000),dict(minimum_free_disk_bytes=1),dict(maximum_records=True)])
def test_impossible_or_ambiguous_native_budgets_are_rejected(changes):
    with pytest.raises(ValueError):policy(**changes)


def test_many_compactions_keep_native_projection_bounded(tmp_path):
    state,clock=setup(tmp_path)
    for i in range(100):
        state.wallet.mark({},{});state.worker._seen(str(i),'candidate_rejected');clock.advance()
    state.compact()
    assert sum(1 for _ in state.iter_rows('wallet.marks'))==100
    assert sum(1 for _ in state.iter_rows('worker.seen_predictions'))==100
    with state.wallet._db() as db:assert db.execute('SELECT count(*) FROM marks').fetchone()[0]==1
    with state.worker._db() as db:assert db.execute('SELECT count(*) FROM seen_predictions').fetchone()[0]==0
    assert all(p.stat().st_size<=state.policy.maximum_active_bytes for p in [state.wallet.path,state.worker.path])


def test_seen_intent_link_failure_rolls_back_both_native_databases(tmp_path):
    state,clock=setup(tmp_path)
    state.worker._seen('already-seen','candidate_rejected')
    with pytest.raises(sqlite3.IntegrityError):
        state.worker._enqueue('must-not-exist','AAA/USDT','Buy',clock.now,{},source_key='already-seen')
    assert state.wallet.pending_intents()==[]
    with state.worker._db() as db:assert db.execute('SELECT count(*) FROM intent_links').fetchone()[0]==0
    state.compact()
    assert not state.worker._enqueue('still-absent','AAA/USDT','Buy',clock.now,{},source_key='already-seen')


def test_shard_page_limit_keeps_active_sources_when_archive_is_full(tmp_path):
    state,clock=setup(tmp_path,shards=1,maximum_shard_bytes=65536)
    for i in range(20):state.worker._event({'n':i,'padding':'x'*3000})
    before=(state.root/'worker.sqlite').read_bytes()
    with pytest.raises(sqlite3.OperationalError,match='full'):state.compact()
    assert (state.root/'worker.sqlite').read_bytes()==before
    assert state._path(0).stat().st_size<=65536


def test_pending_capacity_reserves_slots_for_exits_before_rejecting_more_buys(tmp_path):
    state,clock=setup(tmp_path,maximum_active_rows=16)
    for i in range(8):assert state.wallet.enqueue(f'buy-{i}','AAA/USDT','Buy',created_at=clock.now)
    with pytest.raises(ValueError,match='reserve'):state.wallet.enqueue('too-many','AAA/USDT','Buy',created_at=clock.now)
    assert state.wallet.enqueue('known-exit','AAA/USDT','Sell',created_at=clock.now)
    assert len(state.wallet.pending_intents())==9


def test_latest_unknown_and_latest_known_marks_both_survive_projection(tmp_path):
    state,clock=setup(tmp_path)
    fill(state,clock,'buy','Buy')
    q,r=market(clock);state.wallet.mark({q['pair']:q},{r['pair']:r})
    clock.advance(11);state.wallet.mark({},{});state.compact()
    with state.wallet._db() as db:
        rows=db.execute('SELECT id,payload FROM marks ORDER BY id').fetchall()
    assert len(rows)==2 and json.loads(rows[0][1])['equity'] is not None and json.loads(rows[1][1])['equity'] is None


def test_archived_input_batch_limit_counts_filtered_predictions_too(tmp_path):
    state,clock=setup(tmp_path,maximum_active_rows=16)
    prediction=dict(candidate_sha256='b'*64,opportunity='seen',predicted_at=clock.now.isoformat(),would_enter=False,pair='AAA/USDT')
    identity=hashlib.sha256(('b'*64+'|seen').encode()).hexdigest()
    state.worker._seen(identity,'candidate_rejected');state.compact()
    with pytest.raises(ValueError,match='prediction batch'):
        state.worker.tick([prediction]*17,window_start=START,window_end=START+timedelta(hours=1),entry_cutoff=START+timedelta(hours=1)-timedelta(seconds=30))


def test_native_archive_exceeds_old_event_cap_with_bounded_active_rows_and_stream(tmp_path):
    count=10005
    state,clock=setup(tmp_path,maximum_active_rows=256,maximum_records=20000,maximum_shard_bytes=2*1024*1024)
    started=time.monotonic()
    for first in range(1,count+1,200):
        with state.worker._db() as db:
            db.executemany('INSERT INTO worker_events VALUES (?,?,?)',
                [(i,clock.now.isoformat(),json.dumps({'n':i})) for i in range(first,min(first+200,count+1))])
        state.compact()
        with state.worker._db() as db:assert db.execute('SELECT count(*) FROM worker_events').fetchone()[0]==1
    seal=state.seal();write_seconds=time.monotonic()-started
    tracemalloc.start()
    try:
        started=time.monotonic();reader=read(state,seal);result=reader.audit()
        audit_seconds=time.monotonic()-started;_,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert result['source_counts']['worker.worker_events']==count and peak<8*1024*1024
    assert [r[0] for r in reader.iter_rows('worker.worker_events')]==list(range(1,count+1))
    (tmp_path/'measurement.json').write_text(json.dumps(dict(rows=count,shards=state.policy.shards,
        write_seconds=write_seconds,audit_seconds=audit_seconds,python_peak_bytes=peak,
        active_worker_bytes=state.worker.path.stat().st_size,
        scope='synthetic_worker_rows_not_full_capture_or_market_RSS_or_host_qualification')))
