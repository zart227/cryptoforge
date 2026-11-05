"""Reviewed adoption must preserve uncertain orders and fail without changing ownership."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import sqlite3
import traceback
from types import SimpleNamespace

import pytest

from cryptoforge import account_migration as migration
from cryptoforge.account_ownership import account_execution_lease, account_lock_key, digest
from cryptoforge.execution_ownership import execution_lease, credential_lock_key, credential_scope
from cryptoforge.order_submission_journal import OrderSubmissionJournal
from test_account_verification import key_response, write_policy


def setup_case(root):
    root.mkdir(parents=True, exist_ok=True)
    policy = root / 'policy.json'
    write_policy(policy)
    calls = []
    client = SimpleNamespace(api_key='migration-fake-key', base_url='https://api.bybit.com')
    client._private_get = lambda path, params: calls.append((path, params)) or key_response(
        api_key=client.api_key, now=clock[0])
    client.create_spot_market_order = lambda **kw: pytest.fail('migration submitted an order')
    journal_path = root / 'orders.sqlite'
    locks = root / 'locks'
    statuses = ['prepared', 'unknown', 'acknowledged', 'observed', 'blocked', 'released_unfilled']
    with execution_lease(journal_path, client, lock_directory=locks, machine_id='migration-host'):
        journal = OrderSubmissionJournal(journal_path)
        for i, status in enumerate(statuses):
            link = 'original-' + status
            journal.prepare(symbol='PAIR' + str(i) + 'USDT', side='Buy', qty=Decimal(i + 2), order_link_id=link)
            journal.finish(link, 'blocked')  # Seed independent historical intents, then restore their actual state.
        for i, status in enumerate(statuses):
            journal.finish('original-' + status, status,
                dict(retCode=0, result=dict(orderId='order-' + status)) if status == 'acknowledged' else None,
                'OSError' if status == 'unknown' else None)
    clock = [datetime.now(UTC) + timedelta(seconds=1)]
    scope = credential_scope(client, machine_id='migration-host')
    binding = journal_path.with_name(journal_path.name + '.owner.json')
    registry = locks / (credential_lock_key(scope) + '.owner.json')
    account_registry = locks / 'accounts' / (account_lock_key(digest('101'), client.base_url) + '.owner.json')
    return SimpleNamespace(root=root, policy=policy, client=client, calls=calls, journal=journal,
        journal_path=journal_path, locks=locks, clock=clock, binding=binding, registry=registry,
        account_binding=journal_path.with_name(journal_path.name + '.account-owner.json'),
        account_registry=account_registry,
        intent=journal_path.with_name(journal_path.name + '.uid-migration-intent.json'),
        backup=root / 'reviewed-backup.sqlite', plan=root / 'reviewed-plan.json')


@pytest.fixture
def case(tmp_path):
    return setup_case(tmp_path)


def prepare(case):
    return migration.prepare_migration(journal_path=case.journal_path, client=case.client,
        policy_path=case.policy, lock_directory=case.locks, backup_path=case.backup,
        plan_path=case.plan, review_reference='operator-reviewed-local-migration',
        machine_id='migration-host', clock=lambda: case.clock[0])


def apply(case, result=None):
    result = result or dict(plan_sha256=migration.sha(case.plan.read_bytes()))
    return migration.apply_migration(plan_path=case.plan, reviewed_plan_sha256=result['plan_sha256'],
        client=case.client, machine_id='migration-host', clock=lambda: case.clock[0])


def original_files(case):
    return {path: path.read_bytes() for path in (case.journal_path, case.binding, case.registry, case.policy)}


def assert_originals(original):
    assert all(path.read_bytes() == raw for path, raw in original.items())


def assert_unbound(case):
    assert not case.account_binding.exists()
    assert not case.account_registry.exists()
    assert not case.intent.exists()


def test_prepare_reviewed_apply_and_uid_restart_preserve_original_bytes_and_reservations(case):
    original = original_files(case)
    before_inode = case.journal_path.stat().st_ino
    reservations = case.journal.buy_reservations()
    assert reservations == {'PAIR0USDT': Decimal('2'), 'PAIR1USDT': Decimal('3'),
        'PAIR2USDT': Decimal('4'), 'PAIR3USDT': Decimal('5')}
    result = prepare(case)
    assert result['status'] == 'prepared_for_review' and result['row_count'] == 6
    assert result['status_counts'] == {status: 1 for status in
        ('prepared', 'unknown', 'acknowledged', 'observed', 'blocked', 'released_unfilled')}
    assert not case.backup.exists()
    assert_unbound(case)
    assert_originals(original)
    result = apply(case, result)
    assert result['status'] == 'uid_binding_migrated'
    assert result['live_admission_granted'] is False and result['orders_submitted'] is False
    assert result['journal_sha256'] == result['backup_sha256'] == migration.sha(original[case.journal_path])
    assert case.backup.read_bytes() == original[case.journal_path]
    assert case.journal_path.stat().st_ino == before_inode
    assert_originals(original)
    assert case.journal.buy_reservations() == reservations
    assert case.calls == [('/v5/user/query-api', {}), ('/v5/user/query-api', {})]
    case.client._private_get = lambda *a: pytest.fail('UID-bound restart performed a key query')
    with account_execution_lease(case.journal_path, case.client, policy_path=case.policy,
            lock_directory=case.locks, machine_id='migration-host', clock=lambda: case.clock[0]) as lease:
        lease.assert_held()
    assert_originals(original)
    for path in (case.plan, case.backup, case.intent, case.account_binding, case.account_registry):
        assert path.stat().st_mode & 0o777 == 0o600
        assert b'migration-fake-key' not in path.read_bytes()
        assert b'private-note-must-not-be-persisted' not in path.read_bytes()


def test_apply_can_resume_exact_completed_plan_without_replacing_owners(case):
    result = prepare(case)
    first = apply(case, result)
    outputs = {path: path.read_bytes() for path in
        (case.backup, case.intent, case.account_binding, case.account_registry)}
    case.clock[0] += timedelta(seconds=2)
    assert apply(case, result) == first
    assert_originals(outputs)


def test_wrong_review_sha_never_publishes_backup_or_uid_owners(case):
    prepare(case)
    with pytest.raises(ValueError, match='SHA256'):
        apply(case, dict(plan_sha256='0' * 64))
    assert not case.backup.exists()
    assert_unbound(case)


@pytest.mark.parametrize('input_name', ['journal', 'binding', 'registry', 'policy', 'inode'])
def test_drift_after_review_refuses_migration_and_keeps_changed_source(case, input_name):
    result = prepare(case)
    if input_name == 'journal':
        case.journal.finish('original-unknown', 'observed', {'exchange_observations': []})
    elif input_name == 'inode':
        replacement = case.root / 'copy.sqlite'
        replacement.write_bytes(case.journal_path.read_bytes())
        replacement.replace(case.journal_path)
    else:
        path = getattr(case, input_name)
        path.write_bytes(path.read_bytes() + b'\n')
    changed = original_files(case)
    with pytest.raises((ValueError, OSError)):
        apply(case, result)
    assert_originals(changed)
    assert not case.backup.exists()
    assert_unbound(case)


def test_changed_implementation_cannot_use_old_review(case, monkeypatch):
    result = prepare(case)
    original = migration.implementation_hashes
    monkeypatch.setattr(migration, 'implementation_hashes', lambda: dict(original(), account_ownership='0' * 64))
    with pytest.raises(ValueError, match='implementation'):
        apply(case, result)
    assert not case.backup.exists()
    assert_unbound(case)


@pytest.mark.parametrize('kind', ['unbound', 'missing_registry', 'foreign_key', 'foreign_host', 'foreign_endpoint'])
def test_prepare_does_not_adopt_unbound_or_foreign_credential_history(case, kind):
    if kind == 'unbound':
        case.binding.unlink()
        case.registry.unlink()
    elif kind == 'missing_registry':
        case.registry.unlink()
    elif kind == 'foreign_key':
        case.client.api_key = 'other-fake-key'
    elif kind == 'foreign_endpoint':
        case.client.base_url = 'https://other.invalid'
    else:
        record = json.loads(case.binding.read_bytes())
        record['host_sha256'] = 'f' * 64
        case.binding.write_text(json.dumps(record))
        case.registry.write_text(json.dumps(record))
    raw = case.journal_path.read_bytes()
    with pytest.raises((ValueError, OSError)):
        prepare(case)
    assert case.journal_path.read_bytes() == raw
    assert not case.plan.exists() and not case.backup.exists() and not case.calls
    assert_unbound(case)


def test_existing_uid_binding_is_never_reprepared_or_overwritten(case):
    result = prepare(case)
    apply(case, result)
    original = {path: path.read_bytes() for path in (case.intent, case.account_binding, case.account_registry)}
    case.plan = case.root / 'new-plan.json'
    case.backup = case.root / 'new-backup.sqlite'
    with pytest.raises(ValueError, match='existing account binding'):
        prepare(case)
    assert_originals(original)
    assert not case.plan.exists() and not case.backup.exists()


@pytest.mark.parametrize('publication', ['backup', 'intent', 'registry', 'binding'])
def test_partial_publication_resumes_only_same_plan_preserving_original_journal(case, monkeypatch, publication):
    result = prepare(case)
    original = original_files(case)
    target = {'backup': case.backup, 'intent': case.intent,
        'registry': case.account_registry, 'binding': case.account_binding}[publication]
    original_publish = migration.publish_matching
    def interrupted(path, raw):
        if path == target:
            raise OSError('injected process interruption')
        return original_publish(path, raw)
    monkeypatch.setattr(migration, 'publish_matching', interrupted)
    with pytest.raises(OSError, match='interruption'):
        apply(case, result)
    assert_originals(original)
    monkeypatch.setattr(migration, 'publish_matching', original_publish)
    assert apply(case, result)['status'] == 'uid_binding_migrated'
    assert_originals(original)
    assert case.backup.read_bytes() == original[case.journal_path]
    with account_execution_lease(case.journal_path, case.client, policy_path=case.policy,
            lock_directory=case.locks, machine_id='migration-host', clock=lambda: case.clock[0]) as active:
        active.assert_held()


@pytest.mark.parametrize('conflict_name', ['backup', 'intent', 'account_binding', 'account_registry'])
def test_conflicting_existing_output_is_never_replaced(case, conflict_name):
    result = prepare(case)
    conflict = getattr(case, conflict_name)
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.write_bytes(b'{"foreign_owner":true}')
    original = original_files(case)
    with pytest.raises((ValueError, KeyError)):
        apply(case, result)
    assert conflict.read_bytes() == b'{"foreign_owner":true}'
    assert_originals(original)
    other = case.account_registry if conflict_name == 'account_binding' else case.account_binding
    assert not other.exists()


@pytest.mark.parametrize('phase', ['prepare', 'apply'])
def test_active_credential_lease_blocks_migration_before_authentication(case, phase):
    result = prepare(case) if phase == 'apply' else None
    case.calls.clear()
    with execution_lease(case.journal_path, case.client, lock_directory=case.locks, machine_id='migration-host'):
        with pytest.raises((ValueError, BlockingIOError)):
            apply(case, result) if phase == 'apply' else prepare(case)
    assert not case.calls and not case.backup.exists()
    assert_unbound(case)


def test_held_uid_lock_blocks_migration_even_for_credential_only_journal(case):
    key = account_lock_key(digest('101'), case.client.base_url)
    path = case.locks / 'accounts' / (key + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises((ValueError, BlockingIOError)):
            prepare(case)
    assert not case.calls and not case.plan.exists()
    assert_unbound(case)


@pytest.mark.parametrize('phase', ['prepare', 'apply'])
@pytest.mark.parametrize('failure', ['outage', 'wrong_uid', 'withdraw_permission', 'stale'])
def test_unqualified_fresh_key_observation_never_publishes_ownership(case, phase, failure):
    result = prepare(case) if phase == 'apply' else None
    original = original_files(case)
    def bad_query(*args):
        if failure == 'outage':
            raise OSError('sensitive-upstream migration-fake-key')
        response = key_response(api_key=case.client.api_key, now=case.clock[0])
        if failure == 'wrong_uid':
            response['result']['userID'] = 102
        elif failure == 'withdraw_permission':
            response['result']['permissions']['Wallet'] = ['Withdraw']
        else:
            response['time'] -= 11000
        return response
    case.client._private_get = bad_query
    with pytest.raises(ValueError) as error:
        apply(case, result) if phase == 'apply' else prepare(case)
    rendered = ''.join(traceback.format_exception(error.value))
    assert 'sensitive-upstream' not in rendered and 'migration-fake-key' not in rendered
    assert_originals(original)
    assert_unbound(case)
    assert not case.backup.exists()
    if phase == 'prepare':
        assert not case.plan.exists()


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_sqlite_sidecars_require_quiescent_review_and_are_preserved(case, suffix):
    sidecar = Path(str(case.journal_path) + suffix)
    sidecar.write_bytes(b'possible-active-state')
    with pytest.raises(ValueError, match='quiescent'):
        prepare(case)
    assert sidecar.read_bytes() == b'possible-active-state'
    assert not case.plan.exists() and not case.calls
    assert_unbound(case)


def test_corrupt_intent_sha_is_not_migrated(case):
    with sqlite3.connect(case.journal_path) as db:
        db.execute("UPDATE order_submissions SET sha=? WHERE link=?", ('0' * 64, 'original-prepared'))
    original = original_files(case)
    with pytest.raises(ValueError, match='original order intent'):
        prepare(case)
    assert_originals(original)
    assert not case.plan.exists() and not case.calls
    assert_unbound(case)


@pytest.mark.parametrize('output', ['plan', 'backup'])
@pytest.mark.parametrize('target', ['account_binding', 'account_registry', 'intent', 'sqlite_wal',
    'sqlite_shm', 'sqlite_journal', 'lock_directory_child'])
def test_review_outputs_cannot_occupy_live_owner_sqlite_or_lock_namespace(case, output, target):
    if target.startswith('sqlite_'):
        destination = Path(str(case.journal_path) + '-' + target.removeprefix('sqlite_'))
    elif target == 'lock_directory_child':
        destination = case.locks / 'review-output.json'
    else:
        destination = getattr(case, target)
    setattr(case, output, destination)
    original = original_files(case)
    with pytest.raises(ValueError):
        prepare(case)
    assert_originals(original)
    assert not destination.exists()
    assert_unbound(case)


def test_opened_journal_inode_cannot_be_replaced_before_initial_snapshot(case, monkeypatch):
    original = case.journal_path.read_bytes()
    original_connect = migration.sqlite3.connect
    def replaced_after_open(path, *args, **kwargs):
        connection = original_connect(path, *args, **kwargs)
        replacement = case.root / 'replaced-after-open.sqlite'
        replacement.write_bytes(original)
        replacement.replace(case.journal_path)
        return connection
    monkeypatch.setattr(migration.sqlite3, 'connect', replaced_after_open)
    with pytest.raises(ValueError):
        prepare(case)
    assert case.journal_path.read_bytes() == original
    assert not case.plan.exists() and not case.backup.exists()
    assert_unbound(case)


@pytest.mark.parametrize('tamper', ['admission', 'extra_field', 'future_clock', 'schema'])
def test_partial_publication_requires_strict_original_migration_intent(case, monkeypatch, tamper):
    result = prepare(case)
    original_publish = migration.publish_matching
    def stop_after_intent(path, raw):
        if path == case.account_registry:
            raise OSError('interrupted before account registry')
        return original_publish(path, raw)
    monkeypatch.setattr(migration, 'publish_matching', stop_after_intent)
    with pytest.raises(OSError):
        apply(case, result)
    monkeypatch.setattr(migration, 'publish_matching', original_publish)
    intent = json.loads(case.intent.read_bytes())
    if tamper == 'admission':
        intent['live_admission_granted'] = True
    elif tamper == 'extra_field':
        intent['arbitrary_adoption'] = True
    elif tamper == 'future_clock':
        intent['observed_at'] = (case.clock[0] + timedelta(days=1)).isoformat()
    else:
        intent['schema_version'] = 'foreign-migration-v0'
    raw = migration.json_bytes(intent)
    case.intent.write_bytes(raw)
    original = original_files(case)
    with pytest.raises(ValueError):
        apply(case, result)
    assert case.intent.read_bytes() == raw
    assert_originals(original)
    assert not case.account_binding.exists() and not case.account_registry.exists()


def test_backup_hardlink_to_live_journal_cannot_replace_an_independent_copy(case):
    result = prepare(case)
    original = original_files(case)
    case.backup.hardlink_to(case.journal_path)
    with pytest.raises(ValueError):
        apply(case, result)
    assert_originals(original)
    assert case.backup.read_bytes() == original[case.journal_path]
    assert_unbound(case)


@pytest.mark.parametrize('output', ['backup', 'plan'])
@pytest.mark.parametrize('dangling', [False, True])
def test_symlinked_review_output_is_rejected_without_following_or_replacing_link(case, output, dangling):
    destination = getattr(case, output)
    target = case.root / ('dangling-target' if dangling else 'existing-target')
    if not dangling:
        target.write_bytes(b'external-reviewed-evidence')
    destination.symlink_to(target)
    original = original_files(case)
    with pytest.raises(ValueError):
        prepare(case)
    assert destination.is_symlink() and destination.readlink() == target
    if dangling:
        assert not target.exists()
    else:
        assert target.read_bytes() == b'external-reviewed-evidence'
    assert_originals(original)
    assert_unbound(case)


def test_backup_replaced_by_symlink_after_review_cannot_migrate(case):
    result = prepare(case)
    independent = case.root / 'byte-identical-unreviewed.sqlite'
    independent.write_bytes(case.journal_path.read_bytes())
    case.backup.symlink_to(independent)
    with pytest.raises(ValueError):
        apply(case, result)
    assert case.backup.is_symlink()
    assert independent.read_bytes() == case.journal_path.read_bytes()
    assert_unbound(case)


@pytest.mark.parametrize('ancestor', ['backup', 'plan'])
def test_backup_and_plan_cannot_be_ancestor_and_descendant_paths(case, ancestor):
    root = case.root / 'nested-output'
    setattr(case, ancestor, root)
    setattr(case, 'plan' if ancestor == 'backup' else 'backup', root / 'review.json')
    original = original_files(case)
    with pytest.raises(ValueError):
        prepare(case)
    assert not root.exists()
    assert_originals(original)
    assert_unbound(case)
