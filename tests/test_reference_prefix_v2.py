from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3

import pytest

from cryptoforge.reference_prefix_v2 import ReferencePrefixV2,PrefixPolicyV2,SourceReplay,SQL
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy,file_sha
from cryptoforge.reference_source_ledger import _database as source_db
from cryptoforge.local_source_provenance import digest,parse,stamp
from test_reference_source_ledger import Clock,Client


def setup(tmp_path,*,policy=None):
    clock=Clock();start=clock()+timedelta(seconds=60);end=start+timedelta(minutes=30)
    source=ReferenceLedger.create(tmp_path/'source',clock=clock,start=start,end=end,
        policy=ReferencePolicy(maximum_events=400,maximum_versions=10000,maximum_forecasts=1,maximum_database_bytes=16*1024**2))
    prefix=ReferencePrefixV2.create(tmp_path/'prefix-v2',source.receipt()['reference'],clock=clock,
        policy=policy or PrefixPolicyV2(maximum_database_bytes=32*1024**2))
    clock.advance(60);return clock,source,prefix


def expected(source,tmp_path):
    db=source_db(source.path,source.policy,readonly=True)
    try:
        with SourceReplay(source.manifest,None,parent=tmp_path,maximum_database_bytes=32*1024**2) as replay:
            for row in db.execute('SELECT * FROM events ORDER BY seq'):replay.feed(row)
            return replay.view()
    finally:db.close()


def test_incremental_updates_feed_only_new_events_and_preserve_original_first_seen(tmp_path,monkeypatch):
    clock,source,prefix=setup(tmp_path);seen=[];feed=SourceReplay.feed
    def observed(self,row):seen.append(row[0]);return feed(self,row)
    monkeypatch.setattr(SourceReplay,'feed',observed)
    for poll in range(3):
        if poll:clock.advance(300)
        source.poll(Client(clock));seen.clear();result=prefix.ingest(source.receipt()['reference'])
        assert result['new_source_events']==4 and seen==list(range(4*poll+1,4*poll+5))
        assert not result['semantic_prefix_reprocessed'] and result['physical_sha_still_reads_whole_database']
        view=prefix.view();assert seen==list(range(4*poll+1,4*poll+5))
        assert view['source_view']==expected(source,tmp_path)
    assert prefix.audit(scratch_parent=tmp_path)['prefix_semantic_integrity_pass']
    assert prefix.view()['source_view']['source_sequence']==12


def test_reopen_exact_checkpoint_and_idempotent_same_source_are_byte_stable(tmp_path):
    clock,source,prefix=setup(tmp_path);source.poll(Client(clock));ref=source.receipt()['reference'];prefix.ingest(ref)
    saved=dict(prefix.reference);before=prefix.path.read_bytes()
    reopened=ReferencePrefixV2.open(saved,clock=clock)
    result=reopened.ingest(ref)
    assert result['new_source_events']==0 and reopened.reference==saved and prefix.path.read_bytes()==before
    assert reopened.audit(scratch_parent=tmp_path)['prefix_semantic_integrity_pass']


def test_failed_source_observation_is_retained_and_matches_full_replay(tmp_path):
    clock,source,prefix=setup(tmp_path);source.poll(Client(clock,failed='BTC/USDT'));prefix.ingest(source.receipt()['reference'])
    assert prefix.view()['source_view']==expected(source,tmp_path)
    assert prefix.view()['source_view']['windows']['BTC/USDT']['derived']['status']!='ready'
    assert prefix.audit(scratch_parent=tmp_path)['prefix_semantic_integrity_pass']


def test_interrupted_index_transaction_rolls_back_before_old_checkpoint_is_reused(tmp_path,monkeypatch):
    clock,source,prefix=setup(tmp_path);source.poll(Client(clock));saved=dict(prefix.reference);before=prefix.path.read_bytes()
    feed=SourceReplay.feed
    def broken(self,row):
        if row[0]==3:raise RuntimeError('synthetic mid-transaction failure')
        return feed(self,row)
    monkeypatch.setattr(SourceReplay,'feed',broken)
    with pytest.raises(RuntimeError):prefix.ingest(source.receipt()['reference'])
    assert prefix.path.read_bytes()==before and prefix.reference==saved
    assert prefix.view()['source_view']['source_sequence']==0
    monkeypatch.setattr(SourceReplay,'feed',feed)
    assert prefix.ingest(source.receipt()['reference'])['new_source_events']==4


@pytest.mark.parametrize('fault',['stale_checkpoint','changed_projection','policy','alias','clock'])
def test_unknown_or_changed_index_cannot_be_adopted(tmp_path,fault):
    clock,source,prefix=setup(tmp_path);old=dict(prefix.reference);source.poll(Client(clock));prefix.ingest(source.receipt()['reference'])
    if fault=='stale_checkpoint':
        with pytest.raises(ValueError,match='stale or changed'):ReferencePrefixV2.open(old,clock=clock)
        return
    if fault=='changed_projection':
        with sqlite3.connect(prefix.path) as db:
            db.execute('DROP TRIGGER versions_no_update');db.execute("UPDATE versions SET known_at='2000-01-01T00:00:00+00:00'")
            db.execute(SQL['versions_no_update'])
    if fault=='policy':prefix.policy=replace(prefix.policy,maximum_new_events=8)
    if fault=='alias':
        alias=tmp_path/'alias';alias.symlink_to(prefix.root);prefix.root=alias
    if fault=='clock':clock.advance(-1)
    with pytest.raises((ValueError,FileNotFoundError)):prefix.view()


def test_independent_audit_detects_projection_even_with_forged_physical_pin_in_fault_fixture(tmp_path):
    clock,source,prefix=setup(tmp_path);source.poll(Client(clock));prefix.ingest(source.receipt()['reference'])
    with sqlite3.connect(prefix.path) as db:
        db.execute('DROP TRIGGER versions_no_update');db.execute("UPDATE versions SET known_at='2000-01-01T00:00:00+00:00'")
        db.execute(SQL['versions_no_update'])
    # Fault injection only: a supplied new file SHA must not masquerade as a
    # semantic replay proof. Original saved external reference remains unchanged.
    forged=dict(prefix.reference,database_sha256=file_sha(prefix.path,prefix.policy.maximum_database_bytes))
    obj=ReferencePrefixV2.open(forged,clock=clock)
    with pytest.raises(ValueError,match='projection|index'):obj.audit(scratch_parent=tmp_path)


def test_more_than_registered_increment_is_blocked_before_any_index_write(tmp_path):
    clock,source,prefix=setup(tmp_path,policy=PrefixPolicyV2(maximum_database_bytes=32*1024**2,maximum_new_events=4))
    before=prefix.path.read_bytes();source.poll(Client(clock));clock.advance(300);source.poll(Client(clock))
    with pytest.raises(ValueError,match='bounded original'):prefix.ingest(source.receipt()['reference'])
    assert prefix.path.read_bytes()==before


def test_busy_lock_blocks_ingestion_and_no_index_scratch_pollutes_owner_root(tmp_path):
    import fcntl
    clock,source,prefix=setup(tmp_path);source.poll(Client(clock));before=prefix.path.read_bytes()
    with (prefix.root/'writer.lock').open('rb') as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):prefix.ingest(source.receipt()['reference'])
    assert prefix.path.read_bytes()==before
    with pytest.raises(ValueError,match='scratch'):prefix.audit(scratch_parent=prefix.root)
    assert {p.name for p in prefix.root.iterdir()}=={'manifest.json','registered.json','writer.lock','index.sqlite'}


def test_original_window_is_not_extended_and_all_admission_flags_stay_false(tmp_path):
    clock,source,prefix=setup(tmp_path);source.poll(Client(clock));prefix.ingest(source.receipt()['reference'])
    clock.now=stamp(prefix.manifest['end'])+timedelta(seconds=1)
    with pytest.raises(ValueError,match='outside'):prefix.ingest(source.receipt()['reference'])
    audit=prefix.audit(scratch_parent=tmp_path)
    assert audit['prefix_semantic_integrity_pass']
    assert all(audit[k] is False for k in ('full_worker_or_host_qualified','paper_evidence_pass','economic_profitability_established','live_admission_granted'))


def test_real_process_death_after_index_commit_leaves_old_external_pin_blocked(tmp_path):
    import json,subprocess,sys
    code='''
import json,os,sys
from pathlib import Path
sys.path[:0]=['src','tests']
import cryptoforge.reference_prefix_v2 as module
from test_reference_prefix_v2 import setup,Client
root=Path(sys.argv[1]);clock,source,prefix=setup(root);source.poll(Client(clock))
saved=dict(prefix.reference);(root/'external.json').write_text(json.dumps(dict(reference=saved,at=clock().isoformat())))
original=module.file_sha
def die(path,maximum):
    value=original(path,maximum)
    if path==prefix.path and value!=saved['database_sha256']:os._exit(42)
    return value
module.file_sha=die
prefix.ingest(source.receipt()['reference'])
'''
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True,timeout=60)
    assert child.returncode==42,child.stderr
    saved=json.loads((tmp_path/'external.json').read_text());ref=saved['reference'];path=Path(ref['root'])/'index.sqlite'
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM events').fetchone()==(4,)
    before=path.read_bytes()
    with pytest.raises(ValueError,match='stale or changed'):ReferencePrefixV2.open(ref,clock=lambda:stamp(saved['at']))
    assert path.read_bytes()==before


@pytest.mark.parametrize('limit',['state','database'])
def test_byte_caps_block_without_changing_previous_index(tmp_path,limit):
    policy=(PrefixPolicyV2(maximum_database_bytes=32*1024**2,maximum_state_bytes=65536) if limit=='state'
        else PrefixPolicyV2(maximum_database_bytes=1024**2))
    clock,source,prefix=setup(tmp_path,policy=policy);source.poll(Client(clock));before=prefix.path.read_bytes()
    with pytest.raises(ValueError,match='byte|reserve'):prefix.ingest(source.receipt()['reference'])
    assert prefix.path.read_bytes()==before and prefix.view()['source_view']['source_sequence']==0


def test_incomplete_source_poll_is_not_copied_or_silently_finished(tmp_path,monkeypatch):
    clock,source,prefix=setup(tmp_path);append=source._append;before=prefix.path.read_bytes()
    def broken(kind,*args,**kwargs):
        if kind=='source_response':raise OSError('source process interrupted')
        return append(kind,*args,**kwargs)
    monkeypatch.setattr(source,'_append',broken)
    with pytest.raises(OSError):source.poll(Client(clock))
    ref=source.receipt()['reference']
    with pytest.raises(ValueError,match='complete bounded'):prefix.ingest(ref)
    assert prefix.path.read_bytes()==before


def test_foreign_source_namespace_is_rejected_before_index_effect(tmp_path):
    clock,source,prefix=setup(tmp_path/'one');_,foreign,_=setup(tmp_path/'two')
    before=prefix.path.read_bytes()
    with pytest.raises(ValueError,match='identity'):prefix.ingest(foreign.receipt()['reference'])
    assert prefix.path.read_bytes()==before
