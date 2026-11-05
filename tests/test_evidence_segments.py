from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import tracemalloc

import pytest

from cryptoforge.evidence_segments import SegmentPolicy, SegmentedEventLog


def policy(**changes):
    base = SegmentPolicy(maximum_events=100, maximum_segments=32, maximum_segment_events=4,
        maximum_segment_bytes=4096, maximum_record_bytes=512, maximum_total_bytes=2*1024*1024)
    return replace(base, **changes)


def create(tmp_path, **changes):
    return SegmentedEventLog.create(tmp_path/'segments-study', source_protocol_sha256='a'*64,
        policy=policy(**changes))


def append(log, count):
    for seq in range(1, count+1):
        log.append('complete', {'n': seq}, expected_sequence=seq)


def audit(log, receipt=None):
    receipt = receipt or log.seal()
    return log.audit(expected_head_sha256=receipt['head_sha256'], expected_catalog_sha256=receipt['catalog_sha256'])


def test_rotation_preserves_one_global_chain_and_policy(tmp_path):
    log = create(tmp_path)
    append(log, 13)
    receipt = log.seal()
    assert len(list((log.root/'segments').iterdir())) == 4
    reopened = SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    result = audit(reopened, receipt)
    assert result['events_checked'] == 13 and result['storage_integrity_pass']
    assert not result['paper_evidence_pass']
    assert not result['economic_profitability_established']
    assert not result['live_admission_granted']
    rows = list(log.iter_events(expected_head_sha256=receipt['head_sha256'],
        expected_catalog_sha256=receipt['catalog_sha256']))
    assert [row['sequence'] for row in rows] == list(range(1, 14))


def test_byte_limit_rotates_before_a_segment_overflows(tmp_path):
    log = create(tmp_path, maximum_events=12, maximum_segment_events=20,
        maximum_segment_bytes=1024, maximum_record_bytes=512)
    append(log, 12)
    assert all(path.stat().st_size <= 1024 for path in (log.root/'segments').iterdir())
    assert audit(log)['events_checked'] == 12


def test_retry_is_exactly_once_after_rotation_and_restart(tmp_path):
    log = create(tmp_path)
    append(log, 5)
    resumed = SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    before = (log.root/'catalog.sqlite').read_bytes()
    assert resumed.append('complete', {'n': 1}, expected_sequence=1)['duplicate']
    assert (log.root/'catalog.sqlite').read_bytes() == before
    with pytest.raises(ValueError, match='retry cannot change'):
        resumed.append('complete', {'n': 'different'}, expected_sequence=1)
    with pytest.raises(ValueError, match='sequence gap'):
        resumed.append('complete', {'n': 7}, expected_sequence=7)
    assert audit(resumed)['events_checked'] == 5


@pytest.mark.parametrize('stage', ['before_file', 'partial_line', 'after_full_line'])
def test_pending_append_recovery_finishes_only_known_prefix(tmp_path, monkeypatch, stage):
    log = create(tmp_path, maximum_segment_events=1, maximum_events=20)
    log.append('prepared', {'n': 1}, expected_sequence=1)
    original = log._write_frame
    def interrupted(path, offset, frame):
        if stage == 'partial_line':
            with path.open('xb') as output:
                output.write(frame[:len(frame)//2])
                output.flush()
                os.fsync(output.fileno())
        if stage == 'after_full_line': original(path, offset, frame)
        raise OSError('simulated append interruption')
    monkeypatch.setattr(log, '_write_frame', interrupted)
    with pytest.raises(OSError): log.append('complete', {'n': 2}, expected_sequence=2)
    target = log.root/'segments'/'000002.jsonl'
    retained_prefix = target.read_bytes() if target.exists() else b''
    resumed = SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    assert target.read_bytes().startswith(retained_prefix)
    assert resumed.append('complete', {'n': 2}, expected_sequence=2)['duplicate']
    assert audit(resumed)['events_checked'] == 2


def test_different_partial_tail_is_never_truncated_or_rewritten(tmp_path, monkeypatch):
    log = create(tmp_path)
    def interrupted(path, offset, frame):
        with path.open('ab') as output: output.write(b'CORRUPTED')
        raise OSError('interrupted')
    monkeypatch.setattr(log, '_write_frame', interrupted)
    with pytest.raises(OSError): log.append('prepared', {'n': 1}, expected_sequence=1)
    source = log.root/'segments'/'000001.jsonl'
    before = source.read_bytes()
    with pytest.raises(ValueError, match='partial frame differs'):
        SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    assert source.read_bytes() == before


def test_actual_process_death_during_segment_write_recovers_exactly_once(tmp_path):
    log = create(tmp_path)
    code = '''
import os,sys
from cryptoforge.evidence_segments import SegmentedEventLog
log=SegmentedEventLog.open(sys.argv[1],expected_manifest_sha256=sys.argv[2])
def kill(path,offset,frame):
    with path.open('ab') as output:
        output.write(frame[:50]);output.flush();os.fsync(output.fileno())
    os._exit(73)
log._write_frame=kill
log.append('prepared',{'n':1},expected_sequence=1)
'''
    result = subprocess.run([sys.executable, '-c', code, str(log.root), log.manifest_sha256], timeout=15)
    assert result.returncode == 73
    resumed = SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    assert resumed.append('prepared', {'n': 1}, expected_sequence=1)['duplicate']
    assert audit(resumed)['events_checked'] == 1


def test_process_death_during_catalog_commit_recovers_sqlite_journal(tmp_path):
    log = create(tmp_path)
    code = '''
import os,sys,json
from cryptoforge.evidence_segments import SegmentedEventLog
log=SegmentedEventLog.open(sys.argv[1],expected_manifest_sha256=sys.argv[2])
original=log._recover
def kill(db):
    head=log._head(db)
    if head[4] is None:return original(db)
    pending=json.loads(head[4]);record=pending['record']
    from cryptoforge.evidence_segments import _frame
    frame=_frame(record)
    log._write_frame(log._path(pending['ordinal']),pending['offset'],frame)
    db.execute('BEGIN IMMEDIATE')
    db.execute('UPDATE segments SET count=count+1,last_seq=?,bytes=? WHERE ordinal=?',
        (record['sequence'],pending['offset']+len(frame),pending['ordinal']))
    db.execute('UPDATE head SET seq=?,sha=?,pending=NULL WHERE id=1',(record['sequence'],record['sha256']))
    os._exit(74)
log._recover=kill
log.append('prepared',{'n':1},expected_sequence=1)
'''
    result = subprocess.run([sys.executable, '-c', code, str(log.root), log.manifest_sha256], timeout=15)
    assert result.returncode == 74
    assert Path(str(log.root/'catalog.sqlite')+'-journal').exists()
    resumed = SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    assert not Path(str(log.root/'catalog.sqlite')+'-journal').exists()
    assert resumed.append('prepared', {'n': 1}, expected_sequence=1)['duplicate']
    assert audit(resumed)['events_checked'] == 1


def test_storage_reader_will_not_recover_or_rewrite_pending_source(tmp_path, monkeypatch):
    log = create(tmp_path)
    def fail(*_): raise OSError('storage unavailable')
    monkeypatch.setattr(log, '_write_frame', fail)
    with pytest.raises(OSError): log.append('prepared', {'n': 1}, expected_sequence=1)
    before = {str(path.relative_to(log.root)): path.read_bytes() for path in log.root.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='sealed original'):
        log.audit(expected_head_sha256='b'*64, expected_catalog_sha256='c'*64)
    assert before == {str(path.relative_to(log.root)): path.read_bytes() for path in log.root.rglob('*') if path.is_file()}


def test_global_event_budget_does_not_reset_at_rotation_or_restart(tmp_path):
    log = create(tmp_path, maximum_events=5, maximum_segment_events=2)
    append(log, 5)
    resumed = SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    with pytest.raises(ValueError, match='global event budget'):
        resumed.append('complete', {'n': 6}, expected_sequence=6)
    assert audit(resumed)['events_checked'] == 5


def test_total_storage_budget_fails_before_new_frame(tmp_path):
    log = create(tmp_path, maximum_events=300, maximum_segments=300, maximum_segment_events=1,
        maximum_segment_bytes=1024, maximum_total_bytes=128*1024)
    reached = 0
    for seq in range(1, 301):
        try: log.append('complete', {'n': seq, 'padding': 'a'*200}, expected_sequence=seq)
        except ValueError as error:
            assert 'storage budget' in str(error)
            break
        reached = seq
    assert 0 < reached < 300
    assert audit(log)['events_checked'] == reached
    assert sum(path.stat().st_size for path in log.root.rglob('*') if path.is_file()) <= 128*1024


def test_file_and_protocol_aliases_cannot_be_adopted(tmp_path):
    log = create(tmp_path)
    with pytest.raises(FileExistsError):
        SegmentedEventLog.create(log.root, source_protocol_sha256='a'*64, policy=policy())
    with pytest.raises(ValueError, match='pin'):
        SegmentedEventLog.open(log.root, expected_manifest_sha256='b'*64)
    with pytest.raises(ValueError, match='evidence SHA'):
        SegmentedEventLog.create(tmp_path/'bad', source_protocol_sha256='legacy', policy=policy())
    linked = tmp_path/'alias'
    linked.symlink_to(log.root, target_is_directory=True)
    with pytest.raises(ValueError): SegmentedEventLog.open(linked, expected_manifest_sha256=log.manifest_sha256)


@pytest.mark.parametrize('mutation', ['deleted', 'extra', 'changed', 'hardlink', 'symlink', 'oversized', 'catalog', 'manifest'])
def test_source_tampering_is_rejected_before_structural_pass(tmp_path, mutation):
    log = create(tmp_path)
    append(log, 6)
    receipt = log.seal()
    path = log.root/'segments'/'000001.jsonl'
    if mutation == 'deleted': path.unlink()
    if mutation == 'extra': (log.root/'segments'/'000003.jsonl').write_bytes(b'')
    if mutation == 'changed': path.write_bytes(path.read_bytes().replace(b'"n":1', b'"n":9'))
    if mutation == 'hardlink': os.link(path, tmp_path/'hardlink.jsonl')
    if mutation == 'symlink':
        saved = tmp_path/'saved.jsonl';path.replace(saved);path.symlink_to(saved)
    if mutation == 'oversized': path.write_bytes(b'x'*4097)
    if mutation == 'catalog':
        with sqlite3.connect(log.root/'catalog.sqlite') as db: db.execute('UPDATE head SET seq=0')
    if mutation == 'manifest':
        p=log.root/'manifest.json';data=json.loads(p.read_text());data['policy']['maximum_events']=200;p.write_text(json.dumps(data))
    with pytest.raises((OSError, ValueError)): audit(log, receipt)


def test_sealed_state_and_external_head_catalog_pins_cannot_be_bypassed(tmp_path):
    log = create(tmp_path)
    append(log, 1)
    with pytest.raises(ValueError, match='sealed original'):
        log.audit(expected_head_sha256='a'*64, expected_catalog_sha256='a'*64)
    receipt = log.seal()
    with pytest.raises(ValueError, match='closed ledger'): log.append('complete', {'n': 2}, expected_sequence=2)
    with pytest.raises(ValueError, match='sealed original'):
        log.audit(expected_head_sha256='b'*64, expected_catalog_sha256=receipt['catalog_sha256'])
    with pytest.raises(ValueError, match='catalogue pin'):
        log.audit(expected_head_sha256=receipt['head_sha256'], expected_catalog_sha256='b'*64)


def test_read_only_stream_does_not_modify_sources_and_has_local_lease(tmp_path):
    log = create(tmp_path)
    append(log, 6)
    receipt = log.seal()
    before = {str(p.relative_to(log.root)): p.read_bytes() for p in log.root.rglob('*') if p.is_file()}
    assert audit(log, receipt)['events_checked'] == 6
    assert before == {str(p.relative_to(log.root)): p.read_bytes() for p in log.root.rglob('*') if p.is_file()}
    with log._lease(writer=True):
        with pytest.raises(BlockingIOError): audit(log, receipt)


def test_source_mutation_while_generator_is_open_prevents_final_pass(tmp_path):
    log = create(tmp_path)
    append(log, 6)
    receipt = log.seal()
    stream = log.iter_events(expected_head_sha256=receipt['head_sha256'], expected_catalog_sha256=receipt['catalog_sha256'])
    assert next(stream)['sequence'] == 1
    (log.root/'manifest.json').write_bytes(b'{}')
    with pytest.raises(ValueError): list(stream)


@pytest.mark.parametrize('mutation', ['identity_view', 'extra_column', 'extra_table'])
def test_catalogue_schema_is_validated_before_application_queries(tmp_path, mutation):
    log = create(tmp_path)
    with sqlite3.connect(log.root/'catalog.sqlite') as db:
        if mutation == 'identity_view':
            db.execute('ALTER TABLE identity RENAME TO previous_identity')
            db.execute('CREATE VIEW identity AS SELECT function_that_must_never_execute() AS pin')
        if mutation == 'extra_column': db.execute('ALTER TABLE head ADD COLUMN bypass TEXT')
        if mutation == 'extra_table': db.execute('CREATE TABLE unrelated (payload TEXT)')
    with pytest.raises(ValueError, match='catalogue schema'):
        SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)


def test_resume_checks_the_entire_committed_active_prefix(tmp_path):
    log = create(tmp_path)
    append(log, 3)
    source = log.root/'segments'/'000001.jsonl'
    changed = source.read_bytes().replace(b'"n":1', b'"n":9')
    source.write_bytes(changed)
    with pytest.raises(ValueError, match='hash chain'):
        SegmentedEventLog.open(log.root, expected_manifest_sha256=log.manifest_sha256)
    assert source.read_bytes() == changed


def test_retry_checks_the_original_frame_digest(tmp_path):
    log = create(tmp_path)
    append(log, 2)
    source = log.root/'segments'/'000001.jsonl'
    frames = source.read_bytes().splitlines(keepends=True)
    first = json.loads(frames[0])
    frames[0] = frames[0].replace(first['sha256'].encode(), b'0'*64)
    source.write_bytes(b''.join(frames))
    with pytest.raises(ValueError, match='hash chain'):
        log.append('complete', {'n': 1}, expected_sequence=1)


def test_extra_segment_after_open_is_rejected_before_append(tmp_path):
    log = create(tmp_path)
    append(log, 1)
    catalog = (log.root/'catalog.sqlite').read_bytes()
    source = log.root/'segments'/'000001.jsonl'
    before = source.read_bytes()
    (log.root/'segments'/'unregistered.jsonl').write_bytes(b'extra')
    with pytest.raises(ValueError, match='segment inventory'):
        log.append('complete', {'n': 2}, expected_sequence=2)
    assert source.read_bytes() == before
    assert (log.root/'catalog.sqlite').read_bytes() == catalog


@pytest.mark.parametrize('changes', [dict(maximum_events=True), dict(maximum_segments=4097),
    dict(maximum_record_bytes=255), dict(maximum_segment_bytes=65*1024*1024),
    dict(maximum_total_bytes=1), dict(maximum_segment_events=1, maximum_segments=2)])
def test_impossible_or_ambiguous_policies_are_rejected(changes):
    with pytest.raises(ValueError): policy(**changes)


def test_credentials_nonfinite_and_oversized_payload_are_not_written(tmp_path):
    log = create(tmp_path)
    for payload in [{'api_key': 'never-copy'}, {'n': float('nan')}, {'n': 'x'*600}]:
        with pytest.raises(ValueError): log.append('prepared', payload, expected_sequence=1)
    assert audit(log)['events_checked'] == 0
    assert b'never-copy' not in (log.root/'catalog.sqlite').read_bytes()


def test_exceeds_old_event_limit_with_bounded_streaming_memory(tmp_path):
    count = 10005
    log = create(tmp_path, maximum_events=count, maximum_segments=32, maximum_segment_events=500,
        maximum_segment_bytes=1024*1024, maximum_total_bytes=8*1024*1024)
    started = time.monotonic()
    append(log, count)
    receipt = log.seal()
    write_seconds = time.monotonic()-started
    tracemalloc.start()
    try:
        started = time.monotonic()
        result = audit(log, receipt)
        audit_seconds = time.monotonic()-started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result['events_checked'] == count
    assert peak < 2*1024*1024
    assert len(list((log.root/'segments').iterdir())) == 21
    assert all(path.stat().st_size <= 1024*1024 for path in (log.root/'segments').iterdir())
    with pytest.raises(ValueError, match='global event budget'):
        log.append('complete', {'n': count+1}, expected_sequence=count+1)
    (tmp_path/'measurement.json').write_text(json.dumps(dict(events=count, segments=21,
        write_seconds=write_seconds, audit_seconds=audit_seconds, audit_python_peak_bytes=peak,
        scope='synthetic_small_records_not_actual_market_capture_or_process_RSS')))
