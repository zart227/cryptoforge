from decimal import Decimal
import json
import sqlite3
from types import SimpleNamespace

import pytest
from cryptoforge.execution_controls import ControlledOrderClient, OrderControlBlocked, control_blockers
from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient


def write(path, *, kill=False, pause=False):
    path.write_text(json.dumps(dict(schema_version='executor-controls-v1', kill_switch=kill, no_new_entry=pause)))


def test_no_entry_keeps_sells_available_and_toggle_is_read_before_submit(tmp_path):
    path = tmp_path/'controls.json'; write(path)
    sent = []
    client = ControlledOrderClient(SimpleNamespace(create_spot_market_order=lambda **kw: sent.append(kw)), path)
    client.create_spot_market_order(side='Buy')
    write(path, pause=True)
    with pytest.raises(OrderControlBlocked, match='no-new-entry'):
        client.create_spot_market_order(side='Buy')
    client.create_spot_market_order(side='Sell')
    write(path, kill=True)
    for side in ('Buy', 'Sell'):
        with pytest.raises(OrderControlBlocked, match='kill switch'):
            client.create_spot_market_order(side=side)
    assert [row['side'] for row in sent] == ['Buy', 'Sell']


@pytest.mark.parametrize('raw', [None, '{', 'null', '[]', '{}',
    '{"schema_version":"executor-controls-v1","kill_switch":"false","no_new_entry":false}',
    '{"schema_version":"executor-controls-v1","kill_switch":true,"kill_switch":false,"no_new_entry":false}',
    '{"schema_version":"executor-controls-v1","kill_switch":false,"no_new_entry":0}'])
def test_missing_or_invalid_controls_do_not_fail_open(tmp_path, raw):
    path = tmp_path/'controls.json'
    if raw is not None: path.write_text(raw)
    assert control_blockers(path, 'Buy') and control_blockers(path, 'Sell')


def test_switch_checked_after_intent_commit_and_local_block_is_not_unknown(tmp_path, monkeypatch):
    path = tmp_path/'controls.json'; write(path)
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    prepare = journal.prepare
    def changed_during_prepare(**intent):
        result = prepare(**intent)
        write(path, pause=True)
        return result
    monkeypatch.setattr(journal, 'prepare', changed_during_prepare)
    sent = []
    client = JournaledOrderClient(ControlledOrderClient(SimpleNamespace(
        create_spot_market_order=lambda **kw: sent.append(kw)), path), journal)
    with pytest.raises(OrderControlBlocked):
        client.create_spot_market_order(symbol='BTCUSDT', side='Buy', qty=Decimal('6'), order_link_id='attempt')
    assert sent == []
    with sqlite3.connect(journal.path) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'blocked'


def test_actual_executor_stop_survives_entry_pause_but_respects_kill(tmp_path):
    from test_exit_data_fallback import setup_case
    from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
    path = tmp_path/'controls.json'; write(path, pause=True)
    executor, public, now, sent = setup_case()
    executor.bybit = ControlledOrderClient(executor.bybit, path)
    assert run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now).decision == 'approve_exit'
    assert len(sent) == 1
    write(path, kill=True)
    with pytest.raises(OrderControlBlocked):
        run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert len(sent) == 1


def test_limit_orders_also_respect_guard(tmp_path):
    path = tmp_path/'controls.json'; write(path, pause=True)
    client = ControlledOrderClient(SimpleNamespace(
        create_spot_limit_order=lambda **kw: pytest.fail('buy sent')), path)
    with pytest.raises(OrderControlBlocked): client.create_spot_limit_order(side='Buy')
