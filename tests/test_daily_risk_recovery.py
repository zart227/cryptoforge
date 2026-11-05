from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
import fcntl
import json

import pytest

from cryptoforge.daily_risk_recovery import create_daily_backup, digest, restore_daily_backup
from cryptoforge.live_risk import daily_equity_blockers
from scripts.recover_daily_equity_state import main


NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
SCOPE = 'a' * 64


def backup(tmp_path, raw=b'{"date":"2026-10-16", "start_equity":"100.0000"}\n'):
    source = tmp_path/'source'/'risk.json'
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    output = tmp_path/'backup.json'
    receipt = create_daily_backup(state_path=source, backup_path=output, account_scope=SCOPE,
        reviewed_state_sha256=digest(raw), now=NOW)
    return source, output, receipt


def restore(output, destination, receipt, **changes):
    values = dict(backup_path=output, state_path=destination, account_scope=SCOPE,
        expected_backup_sha256=receipt['backup_sha256'], now=NOW+timedelta(minutes=1))
    values.update(changes)
    return restore_daily_backup(**values)


@pytest.mark.parametrize('raw', [
    b'{"date":"2026-10-16", "start_equity":"100.0000"}\n',
    b'{"date":"2026-10-16","start_equity":"100","timezone":"UTC"}',
])
def test_transfer_preserves_original_bytes_and_accumulated_daily_loss(tmp_path, raw):
    source, output, receipt = backup(tmp_path, raw)
    destination = tmp_path/'other-host'/'risk.json'
    restored = restore(output, destination, receipt)
    assert destination.read_bytes() == source.read_bytes() == raw
    assert restored['restored_state_sha256'] == digest(raw)
    assert restored['live_admission_granted'] is False
    assert output.stat().st_mode & 0o777 == destination.stat().st_mode & 0o777 == 0o600
    blockers = daily_equity_blockers(current_equity=Decimal('97'), maximum_loss=Decimal('2'),
        state_path=destination, now=NOW+timedelta(minutes=2))
    assert 'daily equity loss limit reached' in blockers[0]
    assert destination.read_bytes() == raw  # No new current-equity baseline.


@pytest.mark.parametrize('raw', [b'{', b'null', b'[]',
    b'{"date":"2026-10-15","start_equity":"100"}',
    b'{"date":"2026-10-17","start_equity":"100"}',
    b'{"date":"2026-10-16","start_equity":"NaN"}',
    b'{"date":"2026-10-16","start_equity":"Infinity"}',
    b'{"date":"2026-10-16","start_equity":"-1"}',
    b'{"date":"2026-10-16","start_equity":100}',
    b'{"date":"2026-10-16","start_equity":"100","timezone":"Europe/Moscow"}',
    b'{"date":"2026-10-16","start_equity":"100","start_equity":"90"}',
    b'{"date":"2026-10-16","start_equity":"100","unexpected":true}',
])
def test_backup_does_not_certify_invalid_or_other_day_state(tmp_path, raw):
    with pytest.raises((ValueError, ArithmeticError)):
        backup(tmp_path, raw)
    assert not (tmp_path/'backup.json').exists()
    assert (tmp_path/'source/risk.json').read_bytes() == raw


def test_backup_requires_exact_reviewed_bytes_without_overwriting_earlier_backup(tmp_path):
    source, output, receipt = backup(tmp_path)
    original = output.read_bytes()
    source.write_bytes(source.read_bytes()+b' ')
    with pytest.raises(ValueError, match='reviewed state'):
        create_daily_backup(state_path=source, backup_path=tmp_path/'other.json', account_scope=SCOPE,
            reviewed_state_sha256=receipt['state_sha256'], now=NOW)
    assert not (tmp_path/'other.json').exists()
    with pytest.raises(FileExistsError):
        create_daily_backup(state_path=source, backup_path=output, account_scope=SCOPE,
            reviewed_state_sha256=digest(source.read_bytes()), now=NOW)
    assert output.read_bytes() == original


@pytest.mark.parametrize('changes', [dict(account_scope='b'*64),
    dict(expected_backup_sha256='b'*64), dict(account_scope='unknown'),
    dict(now=NOW-timedelta(seconds=1)), dict(now=NOW+timedelta(days=1)),
    dict(now=NOW.replace(tzinfo=None))])
def test_restore_refuses_mismatch_unreviewed_scope_and_wrong_clock(tmp_path, changes):
    _, output, receipt = backup(tmp_path)
    destination = tmp_path/'restore/risk.json'
    with pytest.raises(ValueError): restore(output, destination, receipt, **changes)
    assert not destination.exists()


@pytest.mark.parametrize('changes', [dict(state_json='{}'), dict(state_sha256='b'*64),
    dict(schema_version='other'), dict(captured_at='2026-10-16T12:00:00'),
    dict(unexpected=True), dict(identity_assurance='verified')])
def test_matching_bundle_hash_does_not_bypass_inner_validation(tmp_path, changes):
    _, output, receipt = backup(tmp_path)
    bundle = json.loads(output.read_bytes()); bundle.update(changes)
    output.write_text(json.dumps(bundle))
    receipt['backup_sha256'] = digest(output.read_bytes())
    destination = tmp_path/'restored.json'
    with pytest.raises(ValueError): restore(output, destination, receipt)
    assert not destination.exists()


@pytest.mark.parametrize('raw', [b'{', b'{"date":"2026-10-16","start_equity":"110"}', b''])
def test_restore_never_replaces_existing_state_even_if_corrupt(tmp_path, raw):
    _, output, receipt = backup(tmp_path)
    destination = tmp_path/'existing.json'; destination.write_bytes(raw)
    with pytest.raises(FileExistsError): restore(output, destination, receipt)
    assert destination.read_bytes() == raw


def test_transfer_uses_same_lock_as_running_daily_gate(tmp_path):
    source, output, receipt = backup(tmp_path)
    with source.with_name('risk.json.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            create_daily_backup(state_path=source, backup_path=tmp_path/'new.json', account_scope=SCOPE,
                reviewed_state_sha256=receipt['state_sha256'], now=NOW)
    destination = tmp_path/'destination.json'
    with destination.with_name('destination.json.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): restore(output, destination, receipt)
    assert not destination.exists()


def test_failure_before_atomic_publication_leaves_no_partial_state(tmp_path, monkeypatch):
    _, output, receipt = backup(tmp_path)
    destination = tmp_path/'other-host/risk.json'
    def fail(*a, **kw): raise OSError('simulated failure before publish')
    monkeypatch.setattr('cryptoforge.daily_risk_recovery.os.link', fail)
    with pytest.raises(OSError): restore(output, destination, receipt)
    assert not destination.exists()
    assert [path.name for path in destination.parent.iterdir()] == ['risk.json.lock']


def test_local_midnight_does_not_change_utc_transfer_day(tmp_path):
    _, output, receipt = backup(tmp_path)
    local = datetime(2026, 10, 17, 1, tzinfo=timezone(timedelta(hours=3)))
    restore(output, tmp_path/'destination.json', receipt, now=local)


def test_cli_failure_returns_blocked_without_creating_destination(tmp_path, capsys):
    assert main(['restore', '--backup', str(tmp_path/'missing.json'), '--state', str(tmp_path/'risk.json'),
        '--account-scope', SCOPE, '--expected-backup-sha256', 'b'*64]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked'
    assert not (tmp_path/'risk.json').exists()
