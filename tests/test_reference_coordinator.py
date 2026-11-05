from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_reference_source_ledger import Clock, Client, artifact
from cryptoforge.local_source_provenance import canonical, digest, parse
from cryptoforge.reference_source_ledger import ReferencePolicy
from cryptoforge.reference_delivery import DeliveryPolicy, ROLES
from cryptoforge.reference_coordinator import ReferenceCoordinator, CoordinatorPolicy, GATES


@pytest.fixture(autouse=True)
def disk(monkeypatch):
    monkeypatch.setattr('cryptoforge.reference_coordinator.shutil.disk_usage', lambda _: SimpleNamespace(free=20*1024**3))


def make(tmp_path, *, consumers=True, prospective=False, model=True, policy=None, delivery_policy=None, source_policy=None):
    clock = Clock()
    obj = ReferenceCoordinator.create(tmp_path/'coordinator', clock=clock,
        diagnostic_consumers=consumers, artifact_raw=artifact() if model else None,
        start=clock()+timedelta(seconds=60) if prospective else None,
        end=clock()+timedelta(hours=1), policy=policy,
        source_policy=source_policy or ReferencePolicy(maximum_database_bytes=8*1024**2, maximum_versions=2000),
        delivery_policy=delivery_policy or DeliveryPolicy(maximum_database_bytes=16*1024**2))
    return clock, obj


def ref(obj):
    return obj.receipt()['reference']


def test_end_to_end_all_roles_and_offline_receipt_replay(tmp_path):
    clock, obj = make(tmp_path)
    client = Client(clock)
    result = obj.step(client=client)
    assert client.calls == ['BTC/USDT', 'ETH/USDT']
    assert result['poll_performed'] is True and result['ingests_performed'] == 1
    assert result['diagnostic_packets'] == 3
    audited = ReferenceCoordinator.open(result['reference'], clock=clock).audit()
    assert audited['journal_integrity_pass'] and audited['diagnostic_input_receipt_integrity_pass']
    assert audited['source_audit']['events_checked'] == 6
    assert audited['delivery_audit']['acknowledged_by_role'] == dict.fromkeys(ROLES, 1)
    assert audited['health']['source_head_caught_up'] is True
    packets = [parse(p.read_bytes()) for p in (obj.root/'packets').iterdir()]
    assert len({p['delivery']['batch_sha256'] for p in packets}) == 1
    assert len({p['delivery']['delivery_id'] for p in packets}) == 3
    assert all(p['source_events'] == packets[0]['source_events'] for p in packets)
    assert all(audited[k] is False for k in GATES)
    assert not any('would_enter' in str(p) for p in packets)


def test_same_bar_resume_does_no_network_and_does_not_refresh_observations(tmp_path):
    clock, obj = make(tmp_path)
    first = obj.step(client=Client(clock))
    clock.advance(10)
    resumed = ReferenceCoordinator.open(first['reference'], clock=clock)
    client = Client(clock)
    second = resumed.step(client=client)
    assert client.calls == [] and second['reference'] == first['reference']
    assert second['source_reference'] == first['source_reference']
    assert second['diagnostic_packets'] == 3
    assert second['health']['poll_age_seconds'] > first['health']['poll_age_seconds']


def test_next_bar_appends_forecasts_and_keeps_old_inputs(tmp_path):
    clock, obj = make(tmp_path)
    obj.step(client=Client(clock))
    original = {p.name: p.read_bytes() for p in (obj.root/'packets').iterdir()}
    clock.advance(300)
    second = obj.step(client=Client(clock, revision=True))
    assert second['diagnostic_packets'] == 6
    assert all((obj.root/'packets'/n).read_bytes() == raw for n, raw in original.items())
    audit = obj.audit()
    assert audit['source_audit']['forecasts_checked'] == 4
    assert audit['delivery_audit']['acknowledged_by_role'] == dict.fromkeys(ROLES, 2)
    assert audit['delivery_audit']['missing_source_poll_slots'] == 0


def test_source_only_prospective_mode_never_offers_or_acknowledges_workers(tmp_path):
    clock, obj = make(tmp_path, consumers=False, prospective=True)
    with pytest.raises(ValueError, match='window'):
        obj.step(client=Client(clock))
    clock.advance(60)
    obj.step(client=Client(clock))
    audit = obj.audit()
    assert audit['diagnostic_packets'] == 0
    assert audit['delivery_audit']['acknowledged_by_role'] == dict.fromkeys(ROLES, 0)
    assert audit['delivery_audit']['batches_checked'] == 1
    with pytest.raises(ValueError, match='diagnostic'):
        make(tmp_path/'bad', consumers=True, prospective=True)


def test_no_model_source_collection_works_without_inventing_forecasts(tmp_path):
    clock, obj = make(tmp_path, model=False)
    obj.step(client=Client(clock))
    audit = obj.audit()
    assert audit['source_audit']['forecasts_checked'] == 0
    assert audit['diagnostic_packets'] == 3


def test_rate_limit_keeps_failures_skips_other_gets_and_honours_cooldown(tmp_path):
    clock, obj = make(tmp_path)
    client = Client(clock, failed='BTC/USDT')
    first = obj.step(client=client)
    assert client.calls == ['BTC/USDT']
    assert first['health']['venue_cooldown_active'] is True
    assert first['health']['closed_candles_ready'] is False
    assert obj.audit()['source_audit']['forecasts_checked'] == 0
    results = [p['result'] for prepared, p in obj.completed if prepared['operation'] == 'forecast']
    assert len(results) == 2 and all(r['status'] == 'skipped_missing_stale_or_failed_inputs' for r in results)
    clock.advance(300)
    client = Client(clock)
    before = ref(obj)
    second = obj.step(client=client)
    assert client.calls == [] and ref(obj) == before
    assert second['health']['missing_completed_tail_slots'] == 1
    clock.advance(301)
    assert obj.step(client=client)['poll_performed'] is True
    assert client.calls == ['BTC/USDT', 'ETH/USDT']


def test_tail_and_internal_gaps_stay_visible_and_never_grant_completeness(tmp_path):
    clock, obj = make(tmp_path)
    obj.step(client=Client(clock))
    clock.advance(900)
    stale = obj.audit()
    assert stale['health']['missing_completed_tail_slots'] == 3
    assert stale['health']['closed_candles_ready'] is False
    obj.step(client=Client(clock))
    audit = obj.audit()
    assert audit['delivery_audit']['missing_source_poll_slots'] == 2
    assert audit['health']['missing_completed_tail_slots'] == 0
    assert audit['source_poll_completeness_verified'] is False


def test_partial_ingest_backlog_blocks_deliveries_until_anchor_is_retained(tmp_path):
    policy = CoordinatorPolicy(maximum_ingests_per_step=1)
    clock, obj = make(tmp_path, policy=policy, delivery_policy=DeliveryPolicy(maximum_source_events_per_batch=4))
    first = obj.step(client=Client(clock))
    assert first['diagnostic_packets'] == 0
    assert first['health']['source_head_caught_up'] is False
    second = obj.step(client=Client(clock))
    assert second['health']['source_head_caught_up'] is True
    assert second['diagnostic_packets'] == 3
    obj.step(client=Client(clock))
    assert obj.audit()['delivery_audit']['acknowledged_by_role'] == dict.fromkeys(ROLES, 2)


def test_stale_external_checkpoint_requires_explicit_known_ancestor_recovery(tmp_path):
    clock, obj = make(tmp_path)
    known = ref(obj)
    current = obj.step(client=Client(clock))
    with pytest.raises(ValueError, match='stale coordinator checkpoint'):
        ReferenceCoordinator.open(known, clock=clock)
    recovered = ReferenceCoordinator.recover(known, clock=clock)
    assert recovered['reference'] == current['reference']
    assert recovered['recovery']['new_checkpoint_required'] is True
    assert ReferenceCoordinator.open(recovered['reference'], clock=clock).audit()['journal_integrity_pass']
    with pytest.raises(ValueError, match='unknown coordinator ancestor'):
        ReferenceCoordinator.recover(dict(known, head_sha256='f'*64), clock=clock)


def test_forecast_steps_are_not_repeated_after_restart_before_ingest(tmp_path, monkeypatch):
    clock, obj = make(tmp_path)
    original = obj._operation
    def operation(name, args, invoke):
        if name == 'ingest':
            raise RuntimeError('stop before preparing ingest')
        return original(name, args, invoke)
    monkeypatch.setattr(obj, '_operation', operation)
    with pytest.raises(RuntimeError):
        obj.step(client=Client(clock))
    resumed = ReferenceCoordinator.open(ref(obj), clock=clock)
    resumed.step(client=Client(clock))
    assert resumed.audit()['source_audit']['forecasts_checked'] == 2
    assert len([p for p, _ in resumed.completed if p['operation'] == 'forecast']) == 2


def test_uncertain_prepared_operation_blocks_retry_and_does_not_refetch(tmp_path, monkeypatch):
    clock, obj = make(tmp_path)
    def fail(client=None):
        raise RuntimeError('before source mutation')
    monkeypatch.setattr(obj.source, 'poll', fail)
    with pytest.raises(RuntimeError):
        obj.step(client=Client(clock))
    checkpoint = ref(obj)
    resumed = ReferenceCoordinator.open(checkpoint, clock=clock)
    assert resumed.receipt()['pending_operation'] == 'poll'
    client = Client(clock)
    with pytest.raises(ValueError, match='incomplete'):
        resumed.step(client=client)
    assert client.calls == []
    with pytest.raises(ValueError, match='incomplete'):
        resumed.audit()


def test_crash_after_source_commit_without_coordinator_completion_is_not_adopted(tmp_path, monkeypatch):
    clock, obj = make(tmp_path)
    original = obj._append
    def append(kind, payload):
        if kind == 'completed':
            raise RuntimeError('receipt lost after source commit')
        return original(kind, payload)
    monkeypatch.setattr(obj, '_append', append)
    known = ref(obj)
    with pytest.raises(RuntimeError):
        obj.step(client=Client(clock))
    with pytest.raises(ValueError, match='database pin'):
        ReferenceCoordinator.recover(known, clock=clock)


def test_packet_tampering_and_orphans_block_restart(tmp_path):
    clock, obj = make(tmp_path)
    obj.step(client=Client(clock))
    checkpoint = ref(obj)
    path = next((obj.root/'packets').iterdir())
    old = path.read_bytes()
    value = parse(old)
    value['source_events'][0]['sha256'] = 'a'*64
    path.write_bytes(canonical(value))
    with pytest.raises(ValueError, match='receipt differs'):
        ReferenceCoordinator.open(checkpoint, clock=clock)
    path.write_bytes(old)
    (obj.root/'packets'/('f'*64+'.json')).write_bytes(b'{}')
    with pytest.raises(ValueError, match='inventory'):
        ReferenceCoordinator.open(checkpoint, clock=clock)


def test_truncated_journal_or_temporary_write_is_not_silently_cleaned(tmp_path):
    clock, obj = make(tmp_path)
    obj.step(client=Client(clock))
    checkpoint = ref(obj)
    path = obj.root/'journal'/'.interrupted.tmp'
    path.write_bytes(b'{')
    with pytest.raises(ValueError, match='inventory'):
        ReferenceCoordinator.open(checkpoint, clock=clock)
    assert path.read_bytes() == b'{'


def test_packet_budget_does_not_ack_an_unpersisted_consumer_result(tmp_path):
    policy = CoordinatorPolicy(maximum_packet_bytes=4096, maximum_total_packet_bytes=4096)
    clock, obj = make(tmp_path, policy=policy)
    with pytest.raises(ValueError, match='packet byte budget'):
        obj.step(client=Client(clock))
    assert obj.queue.audit()['acknowledged_by_role'] == dict.fromkeys(ROLES, 0)
    assert obj.receipt()['pending_operation'] == 'read'


def test_journal_reserve_failure_precedes_all_network_and_component_mutation(tmp_path):
    clock, obj = make(tmp_path, policy=CoordinatorPolicy(maximum_journal_bytes=4096))
    before = obj.receipt()
    client = Client(clock)
    with pytest.raises(ValueError, match='journal reserve'):
        obj.step(client=client)
    assert client.calls == [] and obj.receipt() == before


def test_disk_floor_and_clock_reversal_block_before_network(tmp_path, monkeypatch):
    clock, obj = make(tmp_path)
    client = Client(clock)
    monkeypatch.setattr('cryptoforge.reference_coordinator.shutil.disk_usage', lambda _: SimpleNamespace(free=2048*1024**2))
    with pytest.raises(ValueError, match='disk reserve'):
        obj.step(client=client)
    assert client.calls == []
    monkeypatch.setattr('cryptoforge.reference_coordinator.shutil.disk_usage', lambda _: SimpleNamespace(free=20*1024**3))
    clock.advance(-1)
    with pytest.raises(ValueError, match='clock'):
        obj.step(client=client)
    assert client.calls == []


@pytest.mark.parametrize('field,value', [('maximum_steps', True), ('minimum_step_seconds', 1),
    ('minimum_free_disk_mb', 2047), ('maximum_ingests_per_step', 9), ('maximum_run_seconds', 1801)])
def test_frozen_policy_caps_cannot_be_weakened(field, value):
    with pytest.raises(ValueError):
        CoordinatorPolicy(**{field: value})


def test_single_writer_lock_and_stale_in_memory_writer(tmp_path):
    import fcntl
    clock, obj = make(tmp_path)
    stale = ReferenceCoordinator.open(ref(obj), clock=clock)
    with (obj.root/'writer.lock').open('rb') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            obj.step(client=Client(clock))
    obj.step(client=Client(clock))
    with pytest.raises(ValueError, match='stale coordinator writer'):
        stale.step(client=Client(clock))


def test_offline_cli_audit_and_recovery_reject_as_of_and_run_overrides(tmp_path):
    clock, obj = make(tmp_path)
    obj.step(client=Client(clock))
    path = tmp_path/'ref.json'
    path.write_bytes(canonical(obj.receipt()))
    script = str(Path('scripts/coordinate_reference_sources.py').resolve())
    result = subprocess.run([sys.executable, script, 'audit', '--reference-file', str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['journal_integrity_pass'] is True
    bad = subprocess.run([sys.executable, script, 'run', '--reference-file', str(path), '--steps', '361', '--seconds', '1'], capture_output=True, text=True)
    assert bad.returncode == 1 and 'ValueError' in bad.stderr
    bad = subprocess.run([sys.executable, script, 'step', '--reference-file', str(path), '--as-of', clock().isoformat()], capture_output=True, text=True)
    assert bad.returncode == 2


def test_original_runtime_change_is_rejected_without_network(tmp_path, monkeypatch):
    import cryptoforge.reference_coordinator as module
    clock, obj = make(tmp_path)
    before = ref(obj)
    monkeypatch.setattr(module, '_LOADED_RUNTIME', {})
    with pytest.raises(ValueError, match='runtime changed'):
        ReferenceCoordinator.open(before, clock=clock)


def test_true_process_death_after_completed_pass_recovers_new_checkpoint(tmp_path):
    code = '''
from pathlib import Path
import os,sys
sys.path.insert(0,'tests')
from test_reference_source_ledger import Clock,Client,artifact
from cryptoforge.local_source_provenance import canonical
from cryptoforge.reference_coordinator import ReferenceCoordinator
clock=Clock()
obj=ReferenceCoordinator.create(Path(sys.argv[1])/'coordinator',clock=clock,artifact_raw=artifact(),diagnostic_consumers=True)
(Path(sys.argv[1])/'known.json').write_bytes(canonical(obj.receipt()))
obj.step(client=Client(clock))
os._exit(42)
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 42, result.stderr
    known = parse((tmp_path/'known.json').read_bytes())['reference']
    with pytest.raises(ValueError, match='stale coordinator checkpoint'):
        ReferenceCoordinator.open(known)
    recovered = ReferenceCoordinator.recover(known)
    assert recovered['diagnostic_packets'] == 3
    obj = ReferenceCoordinator.open(recovered['reference'])
    assert obj.audit()['diagnostic_input_receipt_integrity_pass']


def test_true_process_death_mid_poll_never_refetches_or_cleans_up(tmp_path):
    code = '''
from pathlib import Path
import os,sys
sys.path.insert(0,'tests')
from test_reference_source_ledger import Clock
from cryptoforge.local_source_provenance import canonical
from cryptoforge.reference_coordinator import ReferenceCoordinator
clock=Clock()
obj=ReferenceCoordinator.create(Path(sys.argv[1])/'coordinator',clock=clock)
(Path(sys.argv[1])/'known.json').write_bytes(canonical(obj.receipt()))
class Die:
 def fetch(self,pair,anchor):os._exit(43)
obj.step(client=Die())
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 43, result.stderr
    known = parse((tmp_path/'known.json').read_bytes())['reference']
    with pytest.raises(ValueError, match='database pin'):
        ReferenceCoordinator.recover(known)
    with sqlite3.connect(tmp_path/'coordinator'/'source'/'source.sqlite') as db:
        assert db.execute('SELECT count(*) FROM events').fetchone()[0] == 1
        assert db.execute('SELECT pending FROM state').fetchone()[0] is not None


def test_real_foreground_cli_run_is_bounded_and_reuses_one_original_poll(tmp_path):
    # Run the unmodified CLI control loop with a deterministic offline transport;
    # neither the CLI nor the production coordinator exposes this override.
    code = '''
from pathlib import Path
from datetime import datetime,UTC
import sys,importlib.util
sys.path.insert(0,'tests')
from test_reference_source_ledger import observation
from cryptoforge.reference_coordinator import ReferenceCoordinator,CoordinatorPolicy
from cryptoforge.local_source_provenance import canonical
from cryptoforge.reference_sources import PublicReferenceClient
def fetch(self,pair,anchor):
 now=datetime.now(UTC)
 return observation(pair,anchor,now,datetime.now(UTC))
PublicReferenceClient.fetch=fetch
obj=ReferenceCoordinator.create(Path(sys.argv[1])/'coordinator',policy=CoordinatorPolicy(minimum_step_seconds=5),diagnostic_consumers=True)
ref=Path(sys.argv[1])/'known.json'
ref.write_bytes(canonical(obj.receipt()))
spec=importlib.util.spec_from_file_location('coordinator_cli','scripts/coordinate_reference_sources.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
raise SystemExit(module.main(['run','--reference-file',str(ref),'--steps','2','--seconds','15']))
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 2 and rows[0]['poll_performed'] and not rows[1]['poll_performed']
    assert rows[0]['reference'] == rows[1]['reference']
    assert ReferenceCoordinator.open(rows[-1]['reference']).audit()['diagnostic_packets'] == 3


@pytest.mark.parametrize('change', ['source', 'offer', 'freshness'])
def test_rehashed_future_diagnostic_receipt_still_requires_original_source_and_offer(tmp_path, change):
    from cryptoforge.reference_coordinator import _input_receipt
    clock, obj = make(tmp_path)
    known = ref(obj)
    obj.step(client=Client(clock))
    path = next((obj.root/'packets').iterdir())
    packet = parse(path.read_bytes())
    if change == 'source':
        packet['source_view']['windows']['ETH/USDT']['derived']['rows'][-1]['raw_row'][4] = '999'
    elif change == 'offer':
        packet['delivery']['offered_at'] = (clock()-timedelta(seconds=1)).isoformat()
    else:
        packet['closed_candles_ready'] = False
    path.write_bytes(canonical(packet))
    previous = known['head_sha256']
    for log in sorted((obj.root/'journal').iterdir()):
        event = parse(log.read_bytes())
        if event['kind'] == 'completed' and event['payload']['result'].get('receipt', {}).get('delivery', {}).get('delivery_id') == path.stem:
            receipt = event['payload']['result']['receipt']
            new = _input_receipt(packet, canonical(packet), receipt['read_at'])
            event['payload']['result'] = dict(receipt=new, receipt_sha256=digest(canonical(new)))
        if event['kind'] == 'completed':
            event['payload']['prepared_sha256'] = previous
        event['previous_sha256'] = previous
        event['sha256'] = digest(canonical({k: v for k, v in event.items() if k != 'sha256'}))
        log.write_bytes(canonical(event))
        previous = event['sha256']
    match = {'source': 'source replay differs', 'offer': 'role offer differs', 'freshness': 'cannot grant worker'}[change]
    with pytest.raises(ValueError, match=match):
        ReferenceCoordinator.recover(known, clock=clock)
