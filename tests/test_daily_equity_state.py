from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
import fcntl
import json

import pytest
from cryptoforge.live_risk import daily_equity_blockers


NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def check(path, **kwargs):
    values = dict(current_equity=Decimal('8'), maximum_loss=Decimal('2'), state_path=path, now=NOW)
    values.update(kwargs)
    return daily_equity_blockers(**values)


@pytest.mark.parametrize('raw', ['{', 'null', '[]', '{}',
    '{"date":"2026-10-15","start_equity":"NaN"}',
    '{"date":"2026-10-15","start_equity":"Infinity"}',
    '{"date":"2026-10-15","start_equity":"-1"}',
    '{"date":"2026-10-15","start_equity":true}',
    '{"date":"2026-10-16","start_equity":"10"}',
    '{"date":"2026-10-14","start_equity":"bad"}',
    '{"date":"2026-10-15","start_equity":"10","timezone":"Europe/Moscow"}'])
def test_invalid_state_blocks_without_resetting_loss(tmp_path, raw):
    path = tmp_path/'risk.json'; path.write_text(raw)
    assert 'recovery' in check(path)[0]
    assert path.read_text() == raw


def test_missing_state_cannot_silently_initialize(tmp_path):
    path = tmp_path/'risk.json'
    assert 'recovery' in check(path)[0]
    assert not path.exists()


def test_existing_legacy_baseline_is_preserved(tmp_path):
    path = tmp_path/'risk.json'; raw = '{"date":"2026-10-15","start_equity":"10"}'
    path.write_text(raw)
    assert 'loss limit reached' in check(path)[0]
    assert path.read_text() == raw


def test_utc_rollover_is_atomic_and_retains_timezone_policy(tmp_path):
    path = tmp_path/'risk.json'
    path.write_text('{"date":"2026-10-14","start_equity":"10"}')
    assert check(path) == ()
    assert json.loads(path.read_bytes()) == dict(date='2026-10-15', start_equity='8', timezone='UTC')
    assert path.stat().st_mode & 0o777 == 0o600
    # Local midnight does not reset a still-current UTC day.
    path.write_text('{"date":"2026-10-15","start_equity":"10"}')
    local = datetime(2026, 10, 16, 1, tzinfo=timezone(timedelta(hours=3)))
    assert 'loss limit reached' in daily_equity_blockers(current_equity=Decimal('8'),
        maximum_loss=Decimal('2'), state_path=path, now=local)[0]


def test_atomic_replace_failure_preserves_old_baseline(tmp_path, monkeypatch):
    path = tmp_path/'risk.json'; raw = '{"date":"2026-10-14","start_equity":"10"}'
    path.write_text(raw)
    def fail(*args):
        raise OSError('simulated crash before replace')
    monkeypatch.setattr('cryptoforge.atomic_reports.os.replace', fail)
    assert check(path)
    assert path.read_text() == raw
    assert set(item.name for item in tmp_path.iterdir()) == {'risk.json', 'risk.json.lock'}


def test_lock_contention_returns_blocker_without_waiting(tmp_path):
    path = tmp_path/'risk.json'; path.write_text('{"date":"2026-10-15","start_equity":"10"}')
    with (tmp_path/'risk.json.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert 'recovery' in check(path)[0]


@pytest.mark.parametrize('equity,limit', [('NaN','2'), ('Infinity','2'), ('-1','2'), ('8','0'), ('8','NaN')])
def test_nonfinite_or_invalid_inputs_block_before_state_access(tmp_path, equity, limit):
    path = tmp_path/'risk.json'
    assert 'input invalid' in daily_equity_blockers(current_equity=Decimal(equity),
        maximum_loss=Decimal(limit), state_path=path, now=NOW)[0]
    assert not path.exists()


def test_naive_clock_is_rejected(tmp_path):
    assert 'input invalid' in check(tmp_path/'risk.json', now=NOW.replace(tzinfo=None))[0]
