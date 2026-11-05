from types import SimpleNamespace
import sqlite3

import pytest
from cryptoforge.decision_outbox import DecisionOutbox, DurableDecisionClient
from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
from test_exit_data_fallback import setup_case


OPTIONS = dict(on_conflict='idempotency_key', resolution='ignore-duplicates')
ROWS = [dict(idempotency_key='executor:order:original', features={'order': {'result': {'orderId': 'original'}}})]


def offline(*args, **kwargs):
    raise OSError('test remote outage')


def test_restart_delivers_original_payload_once_without_exchange_calls(tmp_path):
    path = tmp_path/'outbox.sqlite'; box = DecisionOutbox(path)
    proxy = DurableDecisionClient(SimpleNamespace(upsert=offline), box)
    proxy.upsert('trade_decisions', ROWS, **OPTIONS)
    proxy.upsert('trade_decisions', ROWS, **OPTIONS)
    assert box.pending() == 1
    calls = []
    recovered = DecisionOutbox(path)
    client = SimpleNamespace(upsert=lambda *args, **kwargs: calls.append((args, kwargs)))
    assert recovered.flush(client) == 1
    assert recovered.flush(client) == 0 and recovered.pending() == 0
    assert calls == [(('trade_decisions', ROWS), OPTIONS)]
    assert path.stat().st_mode & 0o777 == 0o600


def test_local_failure_prevents_remote_delivery(tmp_path, monkeypatch):
    box = DecisionOutbox(tmp_path/'outbox.sqlite'); calls = []
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(box, 'enqueue', fail)
    with pytest.raises(OSError, match='disk full'):
        DurableDecisionClient(SimpleNamespace(upsert=lambda *a, **kw: calls.append(a)), box).upsert(
            'trade_decisions', ROWS, **OPTIONS)
    assert calls == []


def test_cannot_queue_exchange_or_nonidempotent_actions(tmp_path):
    box = DecisionOutbox(tmp_path/'outbox.sqlite')
    for table, rows, options in [('orders', ROWS, OPTIONS), ('trade_decisions', [{}], OPTIONS),
                                  ('trade_decisions', ROWS, {})]:
        with pytest.raises(ValueError):
            box.enqueue(table, rows, options)
    assert box.pending() == 0


def test_corrupt_payload_is_not_delivered(tmp_path):
    box = DecisionOutbox(tmp_path/'outbox.sqlite'); key = box.enqueue('trade_decisions', ROWS, OPTIONS)
    with sqlite3.connect(box.path) as db:
        db.execute("UPDATE decision_outbox SET payload='{}'")
    with pytest.raises(ValueError, match='corrupt'):
        box.deliver(SimpleNamespace(upsert=lambda *a, **kw: pytest.fail('corrupt delivery')), key)


def test_delivery_keeps_insertion_order_and_stops_at_first_failure(tmp_path):
    box = DecisionOutbox(tmp_path/'outbox.sqlite')
    rows = [[dict(idempotency_key='same-key', sequence=i)] for i in range(3)]
    for batch in rows:
        box.enqueue('trade_decisions', batch, OPTIONS)
    assert box.flush(SimpleNamespace(upsert=offline)) == 0 and box.pending() == 3
    seen = []
    assert box.flush(SimpleNamespace(upsert=lambda table, records, **kw: seen.append(records)), limit=2) == 2
    assert seen == rows[:2] and box.pending() == 1


def test_unrelated_database_is_rejected(tmp_path):
    path = tmp_path/'other.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE user_data(id INTEGER)')
    with pytest.raises(ValueError, match='isolated'):
        DecisionOutbox(path)


def test_actual_exit_is_returned_despite_decision_remote_outage(tmp_path):
    executor, public, now, orders = setup_case()
    box = DecisionOutbox(tmp_path/'outbox.sqlite')
    executor.supabase = DurableDecisionClient(SimpleNamespace(upsert=offline), box)
    # Restore production record builder, including exact exchange response.
    del executor._record
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'approve_exit' and len(orders) == 1
    assert box.pending() == 1
    calls = []
    box.flush(SimpleNamespace(upsert=lambda *a, **kw: calls.append(a)))
    assert len(orders) == 1 and calls[0][1][0]['decision'] == 'approve_exit'
    assert calls[0][1][0]['features']['order'] == result.order
