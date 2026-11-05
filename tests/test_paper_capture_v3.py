from dataclasses import replace
from datetime import timedelta
from decimal import localcontext
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import cryptoforge.paper_capture_v3 as capture
from cryptoforge.evidence_segments import SegmentPolicy
from cryptoforge.paper_capture_v3 import (
    SegmentedCapturedPaperWallet, SegmentedLifecycle, audit_segmented_capture, capacity_plan,
)
from test_paper_wallet import Clock, START, config
from test_paper_valuation_capture import raw_market


def lifecycle(**changes):
    base = SegmentedLifecycle(poll_seconds=5, maximum_operations_per_poll=8,
        estimated_bytes_per_operation=8192, maximum_mark_gap_seconds=10,
        maximum_endpoint_gap_seconds=10, minimum_known_time_fraction='.9', closeout_seconds=5,
        finalization_grace_seconds=10, maximum_operation_wall_seconds=5,
        maximum_storage_bytes=128*1024*1024, minimum_free_disk_bytes=128*1024*1024,
        minimum_available_memory_bytes=1)
    return replace(base, **changes)


def storage(**changes):
    return replace(SegmentPolicy(maximum_events=512, maximum_segments=128, maximum_segment_events=4,
        maximum_segment_bytes=1024*1024, maximum_record_bytes=256*1024,
        maximum_total_bytes=8*1024*1024), **changes)


def setup(tmp_path, **changes):
    clock = Clock()
    clock.now = START-timedelta(seconds=10)
    fields = dict(candidate_sha='a'*64, study_protocol_sha256='b'*64, role='candidate', config=config(),
        lifecycle=lifecycle(), storage_policy=storage(), start=START, end=START+timedelta(seconds=20), clock=clock)
    fields.update(changes)
    wallet = SegmentedCapturedPaperWallet.create(tmp_path/'v3-study', **fields)
    clock.now = START
    return wallet, clock


def mark(wallet, clock, **changes):
    quote, rule = raw_market(clock, **changes)
    return wallet.mark({quote['pair']: quote}, {rule['pair']: rule})


def fill(wallet, clock, identity, side, **changes):
    wallet.enqueue(identity, changes.get('pair', 'AAA/USDT'), side, created_at=clock.now)
    clock.advance()
    return wallet.execute(identity, *raw_market(clock, **changes))


def finish(wallet, clock):
    clock.now = START+timedelta(seconds=20)
    wallet.terminate('completed')
    return wallet.finalize()


def audit(wallet, receipt, clock=None):
    return audit_segmented_capture(wallet.root, expected_registration_sha256=wallet.registration_sha256,
        expected_seal_sha256=receipt['seal_sha256'], clock=clock or (lambda: START+timedelta(seconds=20)))


def test_capture_rotates_and_replays_mark_fill_sources_read_only(tmp_path):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    fill(wallet, clock, 'z-buy', 'Buy')
    mark(wallet, clock)
    fill(wallet, clock, 'a-sell', 'Sell', price='98')
    mark(wallet, clock, price='98')
    receipt = finish(wallet, clock)
    before = {str(p.relative_to(wallet.root)): p.read_bytes() for p in wallet.root.rglob('*') if p.is_file()}
    result = audit(wallet, receipt)
    assert result['events_checked'] == 12
    assert result['marks_checked'] == result['raw_source_marks'] == 3
    assert result['fills_checked'] == result['raw_source_fills'] == 2
    assert result['operation_trace_pass']
    assert not result['paper_evidence_pass'] and not result['coverage_evidence_pass']
    assert not result['full_fifo_replay_pass']
    assert not result['live_admission_granted'] and not result['economic_profitability_established']
    assert len(list((wallet.root/'storage'/'segments').iterdir())) == 3
    assert before == {str(p.relative_to(wallet.root)): p.read_bytes() for p in wallet.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('role', ['candidate', 'control', 'stress'])
def test_original_role_and_parent_study_are_bound(tmp_path, role):
    wallet, clock = setup(tmp_path, role=role)
    assert wallet.protocol['study_protocol_sha256'] == 'b'*64
    receipt = finish(wallet, clock)
    assert audit(wallet, receipt)['role'] == role
    wallet.protocol['role'] = 'other'
    with pytest.raises(ValueError, match='in-memory'):
        wallet.finalize()


@pytest.mark.parametrize('mutation', ['root_alias', 'registration_pin', 'protocol', 'storage_manifest'])
def test_v3_original_registration_and_paths_cannot_be_adopted(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    root, pin = wallet.root, wallet.registration_sha256
    if mutation == 'root_alias':
        root = tmp_path/'alias';root.symlink_to(wallet.root, target_is_directory=True)
    if mutation == 'registration_pin': pin = 'f'*64
    if mutation == 'protocol': (root/'protocol.json').write_text('{}')
    if mutation == 'storage_manifest': (root/'storage'/'manifest.json').write_text('{}')
    with pytest.raises((ValueError, OSError)):
        SegmentedCapturedPaperWallet.resume(root, expected_registration_sha256=pin, clock=clock)


def test_long_capacity_exceeds_old_event_and_total_caps_without_claiming_host_qualification():
    limits = lifecycle(maximum_storage_bytes=8*1024**3, minimum_free_disk_bytes=8*1024**3,
        maximum_operations_per_poll=1)
    segments = storage(maximum_events=1100000, maximum_segments=128,
        maximum_segment_events=10000, maximum_segment_bytes=64*1024*1024,
        maximum_record_bytes=4096, maximum_total_bytes=6*1024**3)
    plan = capacity_plan(limits, segments, START, START+timedelta(days=30))
    assert plan['required_events'] == 1036804
    assert not plan['full_worker_or_host_qualified'] and not plan['native_source_archive_qualified']
    from cryptoforge.paper_lifecycle import PaperLifecycle
    with pytest.raises(ValueError):
        PaperLifecycle(**{key:value for key,value in limits.payload().items() if key != 'schema_version'})


@pytest.mark.parametrize('problem', ['unknown_role', 'past_window', 'untyped_lifecycle', 'insufficient_storage', 'disk_floor'])
def test_invalid_v3_preregistration_creates_no_namespace(tmp_path, problem):
    fields = {}
    if problem == 'unknown_role': fields['role'] = 'live'
    if problem == 'past_window': fields['start'] = START-timedelta(seconds=20)
    if problem == 'untyped_lifecycle': fields['lifecycle'] = object()
    if problem == 'insufficient_storage': fields['lifecycle'] = lifecycle(maximum_storage_bytes=64*1024*1024)
    if problem == 'disk_floor':
        with pytest.raises(ValueError): lifecycle(minimum_free_disk_bytes=1)
        return
    with pytest.raises(ValueError): setup(tmp_path, **fields)
    assert not (tmp_path/'v3-study').exists()


def test_restart_preserves_completed_head_and_never_duplicates_a_native_fill(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    head = wallet._head()[0]
    resumed = SegmentedCapturedPaperWallet.resume(wallet.root,
        expected_registration_sha256=wallet.registration_sha256, clock=clock)
    assert resumed._head()[0] == head
    assert len(resumed.snapshot()['fills']) == 1
    assert audit(resumed, finish(resumed, clock))['fills_checked'] == 1


@pytest.mark.parametrize('stage', ['native_error', 'completion_missing', 'prepared_partial', 'complete_partial'])
def test_pending_storage_recovery_never_resubmits_unknown_native_operation(tmp_path, monkeypatch, stage):
    wallet, clock = setup(tmp_path)
    original_append = wallet.log.append
    if stage == 'native_error':
        def native_fail(*_): raise OSError('native operation failed')
        monkeypatch.setattr(wallet._wallet, 'mark', native_fail)
    if stage == 'completion_missing':
        def append(kind, payload, **kw):
            if kind == 'complete': raise OSError('completion unavailable')
            return original_append(kind, payload, **kw)
        monkeypatch.setattr(wallet.log, 'append', append)
    if stage in {'prepared_partial', 'complete_partial'}:
        original_write = wallet.log._write_frame
        def interrupted(path, offset, frame):
            if (b'"kind":"prepared"' if stage == 'prepared_partial' else b'"kind":"complete"') in frame:
                with path.open('ab') as output: output.write(frame[:80])
                raise OSError('interrupted frame write')
            original_write(path, offset, frame)
        monkeypatch.setattr(wallet.log, '_write_frame', interrupted)
    with pytest.raises(OSError): mark(wallet, clock)
    if stage == 'complete_partial':
        resumed = SegmentedCapturedPaperWallet.resume(wallet.root,
            expected_registration_sha256=wallet.registration_sha256, clock=clock)
        assert resumed._head()[1] == 'complete'
        assert resumed.snapshot()['fills'] == []
        with resumed._db() as db: assert db.execute('SELECT count(*) FROM marks').fetchone()[0] == 1
    else:
        with pytest.raises(ValueError, match='unfinished native'):
            SegmentedCapturedPaperWallet.resume(wallet.root,
                expected_registration_sha256=wallet.registration_sha256, clock=clock)
        with pytest.raises(ValueError): wallet.enqueue('after-failure', 'AAA/USDT', 'Buy', created_at=clock.now)


def test_buy_cutoff_blocks_enqueued_and_direct_pending_buy_but_allows_sell(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    wallet.enqueue('pending-buy', 'BBB/USDT', 'Buy', created_at=clock.now)
    clock.now = START+timedelta(seconds=15)
    with pytest.raises(ValueError, match='entry window'): wallet.enqueue('late', 'AAA/USDT', 'Buy', created_at=clock.now)
    with pytest.raises(ValueError, match='cutoff'): wallet.execute('pending-buy', *raw_market(clock, 'BBB/USDT'))
    assert fill(wallet, clock, 'sell', 'Sell', price='98')['status'] == 'filled'
    assert audit(wallet, finish(wallet, clock))['fills_checked'] == 2


def test_auditor_reads_only_registration_and_protocol_until_future_end(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    for path in (wallet.root/'storage', wallet.path):
        path.rename(path.with_name(path.name+'.hidden'))
    def no_rewards(*_): raise AssertionError('rewards opened before end')
    monkeypatch.setattr(capture, '_read_db', no_rewards)
    result = audit_segmented_capture(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
    assert result['status'] == 'sealed_until_capture_end' and result['performance_hidden']


def test_early_abort_cannot_reveal_sealed_outcomes_or_forge_completed_terminal(tmp_path):
    wallet, clock = setup(tmp_path)
    with pytest.raises(ValueError, match='termination'): wallet.terminate('completed')
    wallet.terminate('operator_abort')
    receipt = wallet.finalize()
    assert audit(wallet, receipt, clock=clock)['performance_hidden']
    assert audit(wallet, receipt)['terminal_reason'] == 'operator_abort'


def test_seal_requires_original_terminal_and_external_seal_pin(tmp_path):
    wallet, clock = setup(tmp_path)
    with pytest.raises(ValueError, match='terminal'): wallet.finalize()
    receipt = finish(wallet, clock)
    with pytest.raises(ValueError):
        audit_segmented_capture(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
    receipt['seal_sha256'] = 'f'*64
    with pytest.raises(ValueError, match='metadata pin'): audit(wallet, receipt)


@pytest.mark.parametrize('table', ['marks', 'fills', 'closed_segments'])
def test_native_row_rewrite_never_borrows_the_original_segmented_trace(tmp_path, table):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    fill(wallet, clock, 'sell', 'Sell', price='98')
    mark(wallet, clock, price='98')
    receipt = finish(wallet, clock)
    with wallet._db() as db:
        row_id, raw = db.execute(f'SELECT rowid,payload FROM {table} LIMIT 1').fetchone() if table != 'fills' else (None, None)
        if table == 'fills':
            identity, raw = db.execute('SELECT intent_id,payload FROM fills LIMIT 1').fetchone()
            db.execute('UPDATE fills SET payload=? WHERE intent_id=?', (raw+' ', identity))
        else: db.execute(f'UPDATE {table} SET payload=? WHERE id=?', (raw+' ', row_id))
    with pytest.raises(ValueError, match='source row/hash'): audit(wallet, receipt)


def test_native_row_deletion_blocks_restart_before_any_new_operation(tmp_path):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    with wallet._db() as db: db.execute('DELETE FROM marks')
    with pytest.raises(ValueError):
        SegmentedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


def test_nested_storage_bytes_and_unknown_files_are_in_the_capture_budget(tmp_path):
    wallet, clock = setup(tmp_path)
    measured = wallet._resources()
    assert measured['storage_bytes'] == sum(p.stat().st_size for p in wallet.root.rglob('*') if p.is_file())
    (wallet.root/'unregistered.sqlite').write_bytes(b'extra')
    with pytest.raises(ValueError, match='unregistered'): mark(wallet, clock)


def test_resource_abort_happens_before_native_mark(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    measured = wallet._resources()
    monkeypatch.setattr(wallet, '_resources', lambda: {**measured, 'available_memory_bytes': 0})
    with pytest.raises(ValueError, match='budget terminated'): mark(wallet, clock)
    assert wallet._head()[1] == 'terminated'
    assert audit(wallet, wallet.finalize())['marks_checked'] == 0


def test_changed_decimal_context_blocks_before_native_write(tmp_path):
    wallet, clock = setup(tmp_path)
    with localcontext() as context:
        context.prec += 1
        with pytest.raises(ValueError, match='identity/runtime'): mark(wallet, clock)


def test_existing_worker_uses_segmented_adapter_without_modifying_worker_source(tmp_path):
    from cryptoforge.paper_worker import PaperWorker
    wallet, clock = setup(tmp_path)
    worker = PaperWorker(wallet, tmp_path/'worker.sqlite', policy=dict(enabled=True, status='frozen',
        runtime=dict(maximum_new_signals_per_tick=2, wall_budget_seconds=10),
        exits=dict(stop_fraction='.04', maximum_hold_seconds=3600)),
        market=lambda pair: raw_market(clock, pair), clock=clock)
    prediction = dict(candidate_sha256='a'*64, opportunity='new', predicted_at=clock.now.isoformat(),
        observed_at=clock.now.isoformat(), would_enter=True, pair='AAA/USDT')
    worker.tick([prediction], window_start=START, window_end=START+timedelta(seconds=20))
    clock.advance()
    worker.tick([], window_start=START, window_end=START+timedelta(seconds=20))
    assert audit(wallet, finish(wallet, clock))['fills_checked'] == 1


def test_cli_has_no_clock_override_and_no_source_output(tmp_path):
    spec = importlib.util.spec_from_file_location('v3_cli', Path(__file__).resolve().parents[1]/'scripts/audit_paper_capture_v3.py')
    cli = importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    wallet, clock = setup(tmp_path)
    args = ['--root', str(wallet.root), '--expected-registration-sha256', wallet.registration_sha256]
    with pytest.raises(SystemExit): cli.main(args+['--as-of', START.isoformat()])
    assert cli.main(args+['--output', str(wallet.path)]) == 1


@pytest.mark.parametrize('stage', ['after_native_commit', 'during_complete_frame'])
def test_actual_process_death_keeps_native_operation_exactly_once(tmp_path, stage):
    wallet, clock = setup(tmp_path)
    code = '''
import os,sys
from datetime import datetime
from cryptoforge.paper_capture_v3 import SegmentedCapturedPaperWallet
clock=lambda:datetime.fromisoformat(sys.argv[3])
wallet=SegmentedCapturedPaperWallet.resume(sys.argv[1],expected_registration_sha256=sys.argv[2],clock=clock)
if sys.argv[4]=='after_native_commit':
    original=wallet._wallet.mark
    def killed(*args):
        original(*args)
        os._exit(81)
    wallet._wallet.mark=killed
else:
    original=wallet.log._write_frame
    def killed(path,offset,frame):
        if b'"kind":"complete"' in frame:
            with path.open('ab') as output:
                output.write(frame[:80]);output.flush();os.fsync(output.fileno())
            os._exit(82)
        original(path,offset,frame)
    wallet.log._write_frame=killed
wallet.mark({},{})
'''
    result = subprocess.run([sys.executable, '-c', code, str(wallet.root), wallet.registration_sha256,
        clock.now.isoformat(), stage], timeout=20)
    assert result.returncode == (81 if stage == 'after_native_commit' else 82)
    with wallet._db() as db: assert db.execute('SELECT count(*) FROM marks').fetchone()[0] == 1
    if stage == 'after_native_commit':
        with pytest.raises(ValueError, match='unfinished native'):
            SegmentedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
    else:
        resumed = SegmentedCapturedPaperWallet.resume(wallet.root,
            expected_registration_sha256=wallet.registration_sha256, clock=clock)
        assert audit(resumed, finish(resumed, clock))['marks_checked'] == 1


def test_global_event_budget_preserves_one_terminal_after_last_endpoint(tmp_path):
    wallet, clock = setup(tmp_path, storage_policy=storage(maximum_events=68, maximum_segments=17))
    for second in (0, 5, 10, 15):
        clock.now = START+timedelta(seconds=second)
        for _ in range(8): mark(wallet, clock)
    clock.now = START+timedelta(seconds=20)
    mark(wallet, clock)
    with pytest.raises(ValueError, match='global event budget'): mark(wallet, clock)
    assert audit(wallet, finish(wallet, clock))['marks_checked'] == 33


def test_native_file_budget_stops_before_producer_write(tmp_path):
    wallet, clock = setup(tmp_path)
    reserve = 8*wallet.log.policy.maximum_record_bytes+capture.METADATA_BYTES
    with wallet.path.open('ab') as output: output.truncate(capture.MAX_BYTES-reserve+1)
    with pytest.raises(ValueError, match='budget terminated'): mark(wallet, clock)
    with wallet._db() as db: assert db.execute('SELECT count(*) FROM marks').fetchone()[0] == 0


def test_wall_budget_violation_is_durable_and_reported_without_admission(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    ticks = iter((0, 6*10**9))
    monkeypatch.setattr(capture, 'monotonic_ns', lambda: next(ticks))
    with pytest.raises(ValueError, match='wall budget'): mark(wallet, clock)
    result = audit(wallet, wallet.finalize())
    assert result['terminal_reason'] == 'operation_wall_budget'
    assert not result['operation_wall_budget_pass'] and not result['paper_evidence_pass']


def test_daily_anchor_carries_the_latest_pre_midnight_mark(tmp_path):
    start = START.replace(hour=23, minute=59, second=55)
    wallet, clock = setup(tmp_path, start=start, end=start+timedelta(seconds=20))
    clock.now = start
    mark(wallet, clock)
    clock.now = start+timedelta(seconds=6)
    fill(wallet, clock, 'overnight-buy', 'Buy')
    clock.now = start+timedelta(seconds=20)
    wallet.terminate('completed')
    receipt = wallet.finalize()
    result = audit(wallet, receipt, clock=clock)
    assert result['fills_checked'] == 1
    with wallet._db() as db:
        anchors = db.execute("SELECT value FROM state WHERE key LIKE 'day_anchor:%'").fetchall()
    assert anchors == [('100',), ('100',)]


@pytest.mark.parametrize('mutation', ['missing_intents', 'extra_table', 'extra_column'])
def test_native_schema_drift_cannot_trigger_automatic_repair_on_resume(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    with wallet._db() as db:
        if mutation == 'missing_intents': db.execute('DROP TABLE intents')
        if mutation == 'extra_table': db.execute('CREATE TABLE unrelated (value TEXT)')
        if mutation == 'extra_column': db.execute('ALTER TABLE lots ADD COLUMN hidden TEXT')
    before = wallet.path.read_bytes()
    with pytest.raises(ValueError, match='native schema'):
        SegmentedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
    assert wallet.path.read_bytes() == before


@pytest.mark.parametrize('field', ['path', 'protocol_sha256'])
def test_mutated_in_memory_source_identity_blocks_before_preparation(tmp_path, field):
    wallet, clock = setup(tmp_path)
    setattr(wallet, field, tmp_path/'other.sqlite' if field == 'path' else 'f'*64)
    with pytest.raises(ValueError, match='in-memory'): mark(wallet, clock)
    assert wallet._head()[0] == 1


def test_oversized_native_completion_stays_prepared_without_truncation_or_retry(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    original = wallet._wallet.mark
    def oversized(*args):
        return {**original(*args), 'unbounded_native_result': 'x'*(300*1024)}
    monkeypatch.setattr(wallet._wallet, 'mark', oversized)
    with pytest.raises(ValueError, match='record budget'): mark(wallet, clock)
    with wallet._db() as db: assert db.execute('SELECT count(*) FROM marks').fetchone()[0] == 1
    assert wallet._head()[1] == 'prepared'
    with pytest.raises(ValueError, match='unfinished native'):
        SegmentedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


def test_rehashed_false_intent_side_cannot_borrow_original_buy_fill(tmp_path):
    from cryptoforge.evidence_segments import _frame, _record
    from cryptoforge.paper_valuation_capture import canonical, digest
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    fill(wallet, clock, 'buy', 'Buy')
    receipt = finish(wallet, clock)
    previous = wallet.log.manifest_sha256
    catalog = wallet.root/'storage'/'catalog.sqlite'
    with sqlite3.connect(catalog) as db:
        for ordinal, in db.execute('SELECT ordinal FROM segments ORDER BY ordinal').fetchall():
            path = wallet.log._path(ordinal)
            frames = []
            for raw in path.read_bytes().splitlines():
                record = json.loads(raw)
                if record['kind'] == 'prepared' and record['payload']['operation'] == 'execute':
                    record['payload']['intent_before']['side'] = 'Sell'
                record = _record(record['sequence'], record['kind'], record['payload'], previous)
                frames.append(_frame(record));previous = record['sha256']
            raw = b''.join(frames)
            path.write_bytes(raw)
            db.execute('UPDATE segments SET previous=?,bytes=?,sealed_sha=? WHERE ordinal=?',
                (json.loads(frames[0])['previous_sha256'], len(raw), digest(raw), ordinal))
        db.execute('UPDATE head SET sha=?', (previous,))
    seal = json.loads((wallet.root/'sealed.json').read_bytes())
    seal['head_sha256'], seal['catalog_sha256'] = previous, digest(catalog.read_bytes())
    raw = canonical(seal)
    (wallet.root/'sealed.json').write_bytes(raw)
    receipt['seal_sha256'] = digest(raw)
    with pytest.raises(ValueError, match='fill source/clock/cutoff'):
        audit(wallet, receipt)

