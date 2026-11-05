from dataclasses import replace
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

import cryptoforge.paper_capture_v4 as capture
from cryptoforge.paper_capture_v4 import ArchivedCapturedPaperWallet, audit_archived_capture, capacity_plan
from test_paper_capture_v3 import lifecycle, storage
from test_native_paper_archive import policy, WORKER_POLICY
from test_paper_wallet import START, Clock, config
from test_paper_valuation_capture import raw_market


def setup(tmp_path, **changes):
    clock = Clock();clock.now = START-timedelta(seconds=10)
    fields = dict(candidate_sha='a'*64, study_protocol_sha256='b'*64, role='candidate', config=config(),
        worker_policy=WORKER_POLICY, lifecycle=lifecycle(), storage_policy=storage(), native_policy=policy(),
        start=START, end=START+timedelta(seconds=20), clock=clock)
    fields.update(changes)
    wallet = ArchivedCapturedPaperWallet.create(tmp_path/'v4-study', **fields)
    clock.now = START
    return wallet, clock


def mark(wallet, clock, **changes):
    quote, rule = raw_market(clock, **changes)
    return wallet.mark({quote['pair']:quote}, {rule['pair']:rule})


def fill(wallet, clock, identity, side, **changes):
    wallet.enqueue(identity, changes.get('pair', 'AAA/USDT'), side, created_at=clock.now)
    clock.advance()
    return wallet.execute(identity, *raw_market(clock, **changes))


def finish(wallet, clock):
    clock.now = START+timedelta(seconds=20)
    wallet.terminate('completed')
    return wallet.finalize()


def audit(wallet, receipt, **changes):
    fields = dict(expected_registration_sha256=wallet.registration_sha256,
        expected_seal_sha256=receipt['seal_sha256'], clock=lambda:START+timedelta(seconds=20))
    fields.update(changes)
    return audit_archived_capture(wallet.root, **fields)


def test_wallet_delta_archive_checkpoint_and_read_only_audit(tmp_path):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    assert fill(wallet, clock, 'buy', 'Buy')['status'] == 'filled'
    wallet.compact()
    mark(wallet, clock)
    assert fill(wallet, clock, 'sell', 'Sell', price='98')['status'] == 'filled'
    wallet.compact()
    clock.advance(2)
    mark(wallet, clock, price='98')
    receipt = finish(wallet, clock)
    before = {str(p.relative_to(wallet.root)):p.read_bytes() for p in wallet.root.rglob('*') if p.is_file()}
    result = audit(wallet, receipt)
    assert result['source_checkpoint_trace_pass']
    assert result['events_checked'] == 20
    assert result['source_counts']['wallet.marks'] == 3
    assert result['source_counts']['wallet.fills'] == 2
    assert result['source_counts']['wallet.closed_segments'] == 1
    for flag in ('paper_evidence_pass','economic_profitability_established','live_admission_granted',
                 'full_fifo_replay_pass','coverage_evidence_pass','full_worker_or_host_qualified'):
        assert result[flag] is False
    assert before == {str(p.relative_to(wallet.root)):p.read_bytes() for p in wallet.root.rglob('*') if p.is_file()}


def test_empty_completed_capture_is_source_only(tmp_path):
    wallet, clock = setup(tmp_path)
    result = audit(wallet, finish(wallet, clock))
    assert result['operations_checked'] == 0
    assert result['source_counts']['wallet.marks'] == 0
    assert result['source_checkpoint_trace_pass'] and not result['paper_evidence_pass']


def test_native_compaction_does_not_change_logical_commitments(tmp_path):
    wallet, clock = setup(tmp_path)
    for _ in range(5):mark(wallet, clock)
    before = json.loads(wallet._head()[2])['after']
    clock.advance(5);wallet.compact()
    after = json.loads(wallet._head()[2])['after']
    assert before['sources'] == after['sources']
    assert after['checkpoint']['generation'] == before['checkpoint']['generation']+1
    assert len(list(wallet._source.iter_rows('wallet.marks'))) == 5
    with wallet._source.wallet._db() as db:
        assert db.execute('SELECT count(*) FROM marks').fetchone()[0] == 1
    assert audit(wallet, finish(wallet, clock))['source_checkpoint_trace_pass']


@pytest.mark.parametrize('role', ['candidate','control','stress'])
def test_original_role_parent_and_source_manifests_are_bound(tmp_path, role):
    wallet, clock = setup(tmp_path, role=role)
    assert wallet.protocol['study_protocol_sha256'] == 'b'*64
    assert wallet._source.manifest['source_protocol_sha256'] == wallet.protocol_sha256
    assert wallet.log.manifest['source_protocol_sha256'] == wallet.protocol_sha256
    assert audit(wallet, finish(wallet, clock))['role'] == role


@pytest.mark.parametrize('mutation', ['root_alias','registration','protocol','native_manifest','storage_manifest'])
def test_existing_namespace_or_changed_identity_is_never_adopted(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    with pytest.raises(FileExistsError):setup(tmp_path)
    root, pin = wallet.root, wallet.registration_sha256
    if mutation == 'root_alias':
        root = tmp_path/'alias';root.symlink_to(wallet.root, target_is_directory=True)
    elif mutation == 'registration':pin = 'f'*64
    else:
        path = {'protocol':root/'protocol.json','native_manifest':root/'native'/'manifest.json',
                'storage_manifest':root/'storage'/'manifest.json'}[mutation]
        path.write_text('{}')
    with pytest.raises((OSError, ValueError, KeyError)):
        ArchivedCapturedPaperWallet.resume(root, expected_registration_sha256=pin, clock=clock)


@pytest.mark.parametrize('mutation', ['cash','worker','compact'])
def test_uncaptured_native_or_worker_mutation_blocks_before_new_preparation(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    if mutation == 'cash':
        with wallet._source.wallet._db() as db:db.execute("UPDATE state SET value='101' WHERE key='cash'")
    elif mutation == 'worker':wallet._source.worker._event({'unrecorded':True})
    else:wallet._source.compact()
    with pytest.raises(ValueError, match='uncaptured'):mark(wallet, clock)
    assert wallet._head()[0] == 1
    with pytest.raises(ValueError, match='uncaptured'):
        ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


def test_original_seal_and_terminal_required_and_writers_stop_after_seal(tmp_path):
    wallet, clock = setup(tmp_path)
    with pytest.raises(ValueError, match='terminal'):wallet.finalize()
    receipt = finish(wallet, clock)
    with pytest.raises(ValueError, match='SHA256'):audit(wallet, receipt, expected_seal_sha256=None)
    with pytest.raises(ValueError, match='metadata pin'):audit(wallet, receipt, expected_seal_sha256='f'*64)
    with pytest.raises(ValueError, match='sealed'):mark(wallet, clock)
    with pytest.raises(ValueError, match='sealed'):
        ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


def test_end_gate_does_not_open_logs_sources_or_seal(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    for name in ('native','storage','capture.lock'):
        (wallet.root/name).rename(wallet.root/(name+'.hidden'))
    monkeypatch.setattr(capture.NativePaperArchive, 'reader', lambda *a,**k:pytest.fail('native source opened early'))
    monkeypatch.setattr(capture.SegmentedEventLog, '_load', lambda *a,**k:pytest.fail('event outcomes opened early'))
    result = audit_archived_capture(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
    assert result['performance_hidden'] and result['status'] == 'sealed_until_capture_end'


def test_early_abort_stays_hidden_and_cannot_forge_completion(tmp_path):
    wallet, clock = setup(tmp_path)
    with pytest.raises(ValueError, match='terminal'):wallet.terminate('completed')
    wallet.terminate('operator_abort')
    with pytest.raises(ValueError, match='end window'):wallet.finalize()
    assert audit_archived_capture(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)['performance_hidden']
    clock.now = START+timedelta(seconds=20)
    receipt = wallet.finalize()
    assert audit(wallet, receipt)['terminal_reason'] == 'operator_abort'


def test_captured_cancellation_and_archived_duplicate_remain_exact(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.enqueue('cancelled','AAA/USDT','Buy', created_at=clock.now)
    wallet.cancel_pending('cancelled','operator_cancel')
    wallet.compact()
    assert wallet.execute('cancelled',*raw_market(clock)) == dict(status='rejected',duplicate=True)
    assert not wallet.enqueue('cancelled','AAA/USDT','Buy', created_at=clock.now)
    result = audit(wallet, finish(wallet, clock))
    assert result['source_counts']['wallet.intents'] == 1
    assert result['source_counts']['wallet.fills'] == 0


def test_entry_cutoff_for_pending_and_new_buys_allows_sell(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy','Buy')
    wallet.enqueue('pending','BBB/USDT','Buy',created_at=clock.now)
    clock.now = START+timedelta(seconds=15)
    with pytest.raises(ValueError, match='cutoff'):
        wallet.enqueue('late','AAA/USDT','Buy',created_at=clock.now)
    with pytest.raises(ValueError, match='cutoff'):wallet.execute('pending',*raw_market(clock,'BBB/USDT'))
    assert fill(wallet, clock, 'sell','Sell',price='98')['status'] == 'filled'
    assert audit(wallet, finish(wallet, clock))['source_counts']['wallet.fills'] == 2


def test_auto_compaction_and_restart_keep_all_original_marks(tmp_path):
    wallet, clock = setup(tmp_path, native_policy=policy(maximum_active_rows=16),
        lifecycle=lifecycle(maximum_operations_per_poll=1), end=START+timedelta(seconds=210))
    for n in range(42):
        clock.now = START+timedelta(seconds=n*5)
        mark(wallet, clock)
        if n == 20:
            wallet = ArchivedCapturedPaperWallet.resume(wallet.root,
                expected_registration_sha256=wallet.registration_sha256, clock=clock)
    with wallet._source.wallet._db() as db:
        assert db.execute('SELECT count(*) FROM marks').fetchone()[0] < 16
        assert db.execute('SELECT max(id) FROM marks').fetchone()[0] == 42
    assert json.loads(wallet._head()[2])['after']['sources']['wallet.marks']['count'] == 42
    clock.now = START+timedelta(seconds=210)
    wallet.terminate('completed');receipt = wallet.finalize()
    assert audit(wallet, receipt, clock=clock)['source_counts']['wallet.marks'] == 42


@pytest.mark.parametrize('stage', ['after_native_commit','during_complete_frame','after_archive_commit','before_projection_commit','after_projection_commit'])
def test_actual_process_death_never_repeats_unknown_native_operation(tmp_path, stage):
    wallet, clock = setup(tmp_path)
    if stage in {'after_archive_commit','before_projection_commit','after_projection_commit'}:
        mark(wallet, clock)
    code = '''
import os,sys
from datetime import datetime
from cryptoforge.paper_capture_v4 import ArchivedCapturedPaperWallet
clock=lambda:datetime.fromisoformat(sys.argv[3])
wallet=ArchivedCapturedPaperWallet.resume(sys.argv[1],expected_registration_sha256=sys.argv[2],clock=clock)
stage=sys.argv[4]
if stage=='after_native_commit':
    original=wallet._source.wallet.mark
    def killed(*args):
        original(*args);os._exit(81)
    wallet._source.wallet.mark=killed
elif stage=='during_complete_frame':
    original=wallet.log._write_frame
    def killed(path,offset,frame):
        if b'"kind":"complete"' in frame:
            with path.open('ab') as output:
                output.write(frame[:80]);output.flush();os.fsync(output.fileno())
            os._exit(82)
        original(path,offset,frame)
    wallet.log._write_frame=killed
else:
    def killed(name):
        if name==stage:os._exit(83)
    wallet._source._stage=killed
if stage in {'after_native_commit','during_complete_frame'}:wallet.mark({},{})
else:wallet.compact()
'''
    process = subprocess.run([sys.executable,'-c',code,str(wallet.root),wallet.registration_sha256,
        clock.now.isoformat(),stage], timeout=20)
    assert process.returncode == (81 if stage == 'after_native_commit' else 82 if stage == 'during_complete_frame' else 83)
    if stage == 'during_complete_frame':
        restored = ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
        assert json.loads(restored._head()[2])['after']['sources']['wallet.marks']['count'] == 1
        assert audit(restored, finish(restored, clock))['source_counts']['wallet.marks'] == 1
    else:
        with pytest.raises(ValueError, match='unfinished native'):
            ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
        assert wallet._head()[1] == 'prepared'


def test_source_seal_without_final_capture_receipt_is_not_automatically_adopted(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    clock.now = START+timedelta(seconds=20);wallet.terminate('completed')
    def stopped():raise OSError('capture receipt not published')
    monkeypatch.setattr(wallet.log, 'seal', stopped)
    with pytest.raises(OSError):wallet.finalize()
    assert (wallet.root/'native'/'sealed.json').exists()
    assert not (wallet.root/'sealed.json').exists()
    with pytest.raises(ValueError, match='sealed source'):
        ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


@pytest.mark.parametrize('source', ['shard','wallet','worker','checkpoint','extra'])
def test_sealed_sources_missing_modified_or_extra_do_not_borrow_original_trace(tmp_path, source):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock);receipt = finish(wallet, clock)
    root = wallet.root/'native'
    if source == 'shard':(root/'archive'/'00.sqlite').unlink()
    elif source == 'extra':(root/'unregistered').write_text('x')
    else:
        path = root/(source+'.sqlite')
        raw = path.read_bytes();path.write_bytes(raw+b'changed')
    with pytest.raises((ValueError,OSError)):audit(wallet, receipt)


def test_global_event_limit_reserves_endpoint_and_original_terminal(tmp_path):
    wallet, clock = setup(tmp_path, storage_policy=storage(maximum_events=68, maximum_segments=17))
    for second in (0,5,10,15):
        clock.now = START+timedelta(seconds=second)
        for _ in range(8):mark(wallet, clock)
    clock.now = START+timedelta(seconds=20);mark(wallet, clock)
    with pytest.raises(ValueError, match='global event budget'):mark(wallet, clock)
    assert audit(wallet, finish(wallet, clock))['source_counts']['wallet.marks'] == 33


@pytest.mark.parametrize('kind', ['rate','memory','wall'])
def test_original_resource_rate_and_wall_budgets_remain_enforced(tmp_path, monkeypatch, kind):
    wallet, clock = setup(tmp_path)
    if kind == 'rate':
        for _ in range(8):mark(wallet, clock)
    elif kind == 'memory':
        original = wallet._resources
        monkeypatch.setattr(wallet, '_resources', lambda:{**original(),'available_memory_bytes':0})
    else:
        ticks = iter((0,6*10**9));monkeypatch.setattr(capture,'monotonic_ns',lambda:next(ticks))
    with pytest.raises(ValueError, match='budget'):mark(wallet, clock)
    assert wallet._head()[1] == 'terminated'
    clock.now = START+timedelta(seconds=20)
    result = audit(wallet, wallet.finalize())
    assert result['terminal_reason'] == dict(rate='operation_rate_budget',memory='resource_budget',wall='operation_wall_budget')[kind]
    if kind == 'wall':assert not result['operation_wall_budget_pass']


def test_overlarge_completion_cannot_retry_native_call(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    original = wallet._source.wallet.mark
    def overlarge(*args):return {**original(*args),'too_large':'x'*(300*1024)}
    monkeypatch.setattr(wallet._source.wallet,'mark',overlarge)
    with pytest.raises(ValueError, match='record budget'):mark(wallet, clock)
    assert wallet._head()[1] == 'prepared'
    with wallet._source.wallet._db() as db:assert db.execute('SELECT count(*) FROM marks').fetchone()[0] == 1
    with pytest.raises(ValueError, match='unfinished native'):
        ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


@pytest.mark.parametrize('field', ['protocol_sha256','candidate_sha','config','log_policy'])
def test_mutated_in_memory_pins_cannot_weaken_frozen_contract(tmp_path, field):
    wallet, clock = setup(tmp_path)
    if field == 'log_policy':wallet.log.policy = replace(wallet.log.policy, maximum_total_bytes=16*1024*1024)
    elif field == 'config':wallet.config = config(max_positions=1)
    else:setattr(wallet,field,'f'*64)
    with pytest.raises(ValueError, match='in-memory'):mark(wallet, clock)


def test_combined_capacity_and_native_record_floor_checked_before_new_root(tmp_path):
    with pytest.raises(ValueError, match='capacity'):
        setup(tmp_path, lifecycle=lifecycle(maximum_storage_bytes=32*1024*1024))
    assert not (tmp_path/'v4-study').exists()
    with pytest.raises(ValueError, match='capacity'):
        setup(tmp_path, native_policy=policy(maximum_records=4))
    assert not (tmp_path/'v4-study').exists()


def test_cli_real_clock_no_asof_and_new_output_outside_sources(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location('v4_cli',Path(__file__).resolve().parents[1]/'scripts/audit_paper_capture_v4.py')
    cli = importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    wallet, clock = setup(tmp_path)
    args = ['--root',str(wallet.root),'--expected-registration-sha256',wallet.registration_sha256]
    with pytest.raises(SystemExit):cli.main(args+['--as-of',START.isoformat()])
    assert cli.main(args+['--output',str(wallet.root/'invalid')]) == 1
    receipt = finish(wallet, clock);args += ['--expected-seal-sha256',receipt['seal_sha256']]
    output = tmp_path/'audit.json'
    assert cli.main(args+['--output',str(output)]) == 0
    assert json.loads(output.read_bytes())['source_checkpoint_trace_pass']
    before = output.read_bytes()
    assert cli.main(args+['--output',str(output)]) == 1
    assert output.read_bytes() == before


def rehash(wallet, receipt, mutation):
    """Adversarially issue new structural pins; semantic checks must still fail."""
    import sqlite3
    from cryptoforge.evidence_segments import _frame, _record, canonical, digest
    previous = wallet.log.manifest_sha256
    catalog = wallet.root/'storage'/'catalog.sqlite'
    with sqlite3.connect(catalog) as db:
        for ordinal, in db.execute('SELECT ordinal FROM segments ORDER BY ordinal').fetchall():
            path, frames = wallet.log._path(ordinal), []
            for raw in path.read_bytes().splitlines():
                record = json.loads(raw);mutation(record)
                record = _record(record['sequence'],record['kind'],record['payload'],previous)
                frames.append(_frame(record));previous = record['sha256']
            raw = b''.join(frames);path.write_bytes(raw)
            db.execute('UPDATE segments SET previous=?,bytes=?,sealed_sha=? WHERE ordinal=?',
                (json.loads(frames[0])['previous_sha256'],len(raw),digest(raw),ordinal))
        db.execute('UPDATE head SET sha=?',(previous,))
    seal = json.loads((wallet.root/'sealed.json').read_bytes())
    seal['head_sha256'],seal['catalog_sha256'] = previous,digest(catalog.read_bytes())
    raw = canonical(seal);(wallet.root/'sealed.json').write_bytes(raw)
    return {**receipt,'seal_sha256':digest(raw)}


@pytest.mark.parametrize('mutation', ['genesis','operation_scope','delta_key','mark_clock','fill_quote'])
def test_rehashed_structural_trace_does_not_override_original_row_semantics(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock);fill(wallet, clock,'buy','Buy')
    receipt = finish(wallet, clock)
    def change(record):
        kind,event = record['kind'],record['payload']
        if mutation == 'genesis' and kind == 'genesis':event['after']['sources']['wallet.marks']['count'] = 1
        elif mutation == 'operation_scope' and kind == 'prepared' and event['operation'] == 'mark':event['operation'] = 'compact'
        elif mutation == 'delta_key' and kind == 'complete' and event['changes']:event['changes'][0]['key'] = 'forged'
        elif mutation == 'mark_clock' and kind == 'complete':
            for row in event['changes']:
                if row['source'] == 'wallet.marks':row['after'][1] = (START-timedelta(seconds=1)).isoformat()
        elif mutation == 'fill_quote' and kind == 'prepared' and event['operation'] == 'execute':event['inputs']['quote']['bid'] = '99'
    with pytest.raises(ValueError):audit(wallet, rehash(wallet,receipt,change))


@pytest.mark.parametrize('mutation', ['missing_table','extra_column'])
def test_native_schema_is_never_repaired_by_capture_resume(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    with wallet._source.wallet._db() as db:
        db.execute('DROP TABLE intents' if mutation == 'missing_table' else 'ALTER TABLE lots ADD COLUMN hidden TEXT')
    before = (wallet.root/'native'/'wallet.sqlite').read_bytes()
    with pytest.raises(ValueError, match='schema'):
        ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)
    assert (wallet.root/'native'/'wallet.sqlite').read_bytes() == before


def test_completion_clock_leaving_original_window_blocks_resume(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    original = wallet._source.wallet.mark
    def late(*args):
        result = original(*args);clock.now = START+timedelta(seconds=21);return result
    monkeypatch.setattr(wallet._source.wallet,'mark',late)
    with pytest.raises(ValueError, match='completion outside'):mark(wallet, clock)
    assert wallet._head()[1] == 'prepared'
    with pytest.raises(ValueError, match='unfinished native'):
        ArchivedCapturedPaperWallet.resume(wallet.root, expected_registration_sha256=wallet.registration_sha256, clock=clock)


@pytest.mark.parametrize('mutation', ['prefix_hash','compaction_watermark'])
def test_rehashed_intermediate_checkpoint_must_reference_original_archive_prefix(tmp_path, mutation):
    wallet, clock = setup(tmp_path, native_policy=policy(shards=1))
    mark(wallet, clock);wallet.compact();mark(wallet, clock)
    receipt = finish(wallet, clock)
    # Final seal adds mark2 to exactly one shard. Changing that shard's earlier
    # tip still looks monotonic, so a mere sequence/head-order check is insufficient.
    final = json.loads((wallet.root/'sealed.json').read_bytes())['native_after']['checkpoint']
    states = [json.loads(raw)['payload']['after']['checkpoint']
        for path in (wallet.root/'storage'/'segments').iterdir() for raw in path.read_bytes().splitlines()
        if json.loads(raw)['kind'] == 'complete']
    earlier = next(state for state in states if state['generation'] == 1)
    bucket = next(b for b,(old,new) in enumerate(zip(earlier['archive_heads'],final['archive_heads'])) if new[0] > old[0])
    assert earlier['archive_heads'][bucket][0] > 0
    def change(record):
        event = record['payload']
        for field in ('before','after'):
            point = event.get(field,{}).get('checkpoint')
            if point and point['generation'] == 1:
                if mutation == 'prefix_hash':point['archive_heads'][bucket][1] = 'f'*64
                else:point['watermarks']['wallet.marks'] = 0
    with pytest.raises(ValueError, match='prefix|watermark'):
        audit(wallet, rehash(wallet, receipt, change))
