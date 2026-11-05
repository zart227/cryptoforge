from datetime import UTC, datetime, timedelta
from decimal import Decimal
import fcntl
import json
import sqlite3

import pytest
from cryptoforge.portfolio_drawdown import drawdown_blockers
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient
from test_submission_risk import setup, BUY


NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
OWNER = 'a'*64


def seed(path):
    state = dict(schema_version='observed-portfolio-drawdown-v1', owner_id=OWNER,
        maximum_drawdown='0.10', peak_equity='100', last_equity='100',
        observed_at=(NOW-timedelta(seconds=1)).isoformat(), breach_latched=False)
    path.write_text(json.dumps(state)); return state


def check(path, value, **changes):
    args = dict(current_equity=Decimal(value), maximum_drawdown=Decimal('.10'),
        state_path=path, owner_id=OWNER, now=NOW)
    args.update(changes); return drawdown_blockers(**args)


def test_peak_grows_and_persists_over_restart_and_day_boundary(tmp_path):
    path = tmp_path/'peak.json'; seed(path)
    assert check(path, '110') == ()
    assert check(path, '105', now=NOW+timedelta(days=1)) == ()
    state = json.loads(path.read_bytes())
    assert state['peak_equity'] == '110' and state['last_equity'] == '105'
    assert path.stat().st_mode & 0o777 == 0o600
    assert 'latched' in check(path, '99', now=NOW+timedelta(days=1))[0]


def test_breach_latches_at_exact_boundary_and_equity_recovery_cannot_clear_it(tmp_path):
    path = tmp_path/'peak.json'; seed(path)
    assert 'latched' in check(path, '90')[0]
    assert 'latched' in check(path, '120', now=NOW+timedelta(seconds=1))[0]
    assert json.loads(path.read_bytes())['breach_latched'] is True


@pytest.mark.parametrize('field,value', [('peak_equity','NaN'), ('last_equity','Infinity'),
    ('peak_equity','0'), ('last_equity','101'), ('owner_id','b'*64), ('maximum_drawdown','.05'),
    ('observed_at',(NOW+timedelta(seconds=1)).isoformat()), ('breach_latched','false'),
    ('peak_equity',True), ('last_equity','80')])
def test_corrupt_incompatible_or_unlatched_breach_never_resets_peak(tmp_path, field, value):
    path = tmp_path/'peak.json'; state = seed(path); state[field] = value
    raw = json.dumps(state); path.write_text(raw)
    assert check(path, '100')
    assert path.read_text() == raw


def test_missing_state_is_unknown_not_new_peak(tmp_path):
    path = tmp_path/'missing.json'
    assert check(path, '100') and not path.exists()


def test_clock_rollback_and_atomic_write_failure_keep_prior_state(tmp_path, monkeypatch):
    path = tmp_path/'peak.json'; seed(path); raw = path.read_bytes()
    assert check(path, '110', now=NOW-timedelta(hours=1))
    assert path.read_bytes() == raw
    def fail(*args): raise OSError('simulated write failure')
    monkeypatch.setattr('cryptoforge.atomic_reports.os.replace', fail)
    assert check(path, '110') and path.read_bytes() == raw


def test_lock_contention_blocks_without_waiting(tmp_path):
    path = tmp_path/'peak.json'; seed(path)
    with (tmp_path/'peak.json.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert check(path, '100')


def test_submission_guard_checks_drawdown_and_journal_marks_known_local_block(tmp_path):
    guard, account, _, sent = setup(tmp_path)
    path = tmp_path/'peak.json'; seed(path)
    guard.drawdown_policy = dict(state_path=path, maximum_drawdown=Decimal('.10'), owner_id=OWNER)
    guard.clock = lambda: NOW
    account.total_equity_usd = Decimal('89')
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    with pytest.raises(OrderControlBlocked, match='latched'):
        JournaledOrderClient(guard, journal).create_spot_market_order(**BUY)
    assert sent == []
    with sqlite3.connect(journal.path) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'blocked'
    path.unlink()
    guard.create_spot_market_order(**dict(BUY, side='Sell', qty=Decimal('.01')))
    assert sent[0]['side'] == 'Sell'
