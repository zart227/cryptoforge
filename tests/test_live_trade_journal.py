from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
import sqlite3

import pytest

from cryptoforge.live_trade_journal import reconstruct_trades, sync_live_journal


def fill(identity, side, qty, price, *, fee='0', currency='USDT', link='cf-test', time=1000, symbol='ETHUSDT'):
    return {'execId': identity, 'orderId': 'order-' + identity, 'orderLinkId': link,
            'execTime': str(time), 'execType': 'Trade', 'side': side, 'symbol': symbol,
            'execQty': qty, 'execPrice': price, 'execValue': str(Decimal(qty) * Decimal(price)),
            'execFee': fee, 'feeCurrency': currency}


def closed(rows):
    return [r for r in rows if r['status'] == 'closed']


def test_base_buy_fee_and_quote_sell_fee_are_not_double_counted():
    rows, result = reconstruct_trades([
        fill('b', 'Buy', '10', '2', fee='0.1', currency='ETH'),
        fill('s', 'Sell', '9.9', '3', fee='0.3', time=2000),
    ])
    trade = closed(rows)[0]
    assert Decimal(trade['realized_pnl']) == Decimal('9.4')  # 29.7 - .3 - 20
    assert Decimal(trade['fee_amount']) == Decimal('.5')
    assert Decimal(trade['stake_amount']) == Decimal('20')
    assert result.open_lots == 0
    assert next(r for r in rows if r['closed_at'] is None)['status'] == 'cancelled'


def test_partial_sell_allocates_cost_and_fees_and_keeps_remainder():
    rows, _ = reconstruct_trades([
        fill('b', 'Buy', '10', '2', fee='1'),
        fill('s', 'Sell', '4', '3', fee='.2', time=2000),
    ])
    trade = closed(rows)[0]
    assert Decimal(trade['realized_pnl']) == Decimal('3.4')
    assert Decimal(trade['fee_amount']) == Decimal('.6')
    remainder = next(r for r in rows if r['status'] == 'open')
    assert Decimal(remainder['amount']) == 6
    assert Decimal(remainder['stake_amount']) == Decimal('12.6')


def test_fifo_spans_buys_and_multiple_partial_fills_of_same_order():
    rows, result = reconstruct_trades([
        fill('b1', 'Buy', '2', '10'), fill('b2', 'Buy', '3', '20', time=1100),
        fill('s1', 'Sell', '4', '30', time=2000), fill('s2', 'Sell', '1', '30', time=2100),
    ])
    assert result.closed_segments == 3
    assert sum(Decimal(r['realized_pnl']) for r in closed(rows)) == 70
    assert result.open_lots == 0
    assert len({r['idempotency_key'] for r in rows}) == len(rows)


def test_external_inventory_is_consumed_without_becoming_bot_profit():
    rows, _ = reconstruct_trades([
        fill('external', 'Buy', '1', '1', link=''),
        fill('bot', 'Buy', '1', '2', time=1500),
        fill('manual-sell', 'Sell', '1', '3', link='', time=2000),
    ])
    assert not closed(rows)
    assert len(rows) == 1
    assert rows[0]['status'] == 'open'


def test_bot_exit_of_known_external_inventory_records_cost_and_origin():
    rows, _ = reconstruct_trades([fill('b', 'Buy', '1', '2', link=''), fill('s', 'Sell', '1', '3', time=2000)])
    assert Decimal(closed(rows)[0]['realized_pnl']) == 1
    assert 'origin=external' in closed(rows)[0]['entry_reason']


def test_unmatched_sells_and_unknown_fee_currency_do_not_invent_pnl():
    rows, result = reconstruct_trades([
        fill('unmatched', 'Sell', '5', '3'),
        fill('b', 'Buy', '1', '2', fee='.1', currency='MNT', time=2000),
        fill('s', 'Sell', '1', '3', time=3000),
    ])
    assert result.unmatched_sells == 1
    assert result.incomplete_fees == 1
    assert closed(rows)[0]['realized_pnl'] is None
    assert closed(rows)[0]['fee_amount'] is None


def test_base_sell_fee_consumes_inventory_and_rebate_is_supported():
    rows, _ = reconstruct_trades([
        fill('b', 'Buy', '10', '2', fee='-.1', currency='ETH'),
        fill('s', 'Sell', '10', '3', fee='.1', currency='ETH', time=2000),
    ])
    assert Decimal(closed(rows)[0]['realized_pnl']) == 10
    assert not any(r['status'] == 'open' for r in rows)


def test_duplicate_and_out_of_order_fills_are_deterministic():
    b = fill('b', 'Buy', '1', '2')
    s = fill('s', 'Sell', '1', '3', time=2000)
    assert reconstruct_trades([s, b, b])[0] == reconstruct_trades([b, s])[0]


class Store:
    def __init__(self):
        self.rows = {}
        self.fail = False

    def upsert(self, table, records, **kwargs):
        if self.fail:
            raise RuntimeError('offline')
        key = kwargs['on_conflict']
        for row in records:
            self.rows[(table, row[key])] = row


def test_sync_backfills_windows_retries_failed_publish_and_survives_restart(tmp_path):
    requests = []
    fills = [fill('b', 'Buy', '1', '2'), fill('s', 'Sell', '1', '3', time=2000)]
    def fetch(**kwargs):
        requests.append(kwargs)
        return [r for r in fills if kwargs['start_ms'] <= int(r['execTime']) <= kwargs['end_ms']]
    bybit = SimpleNamespace(get_spot_executions=fetch)
    store = Store()
    path = tmp_path / 'journal.sqlite'
    now = datetime(1970, 1, 16, tzinfo=UTC)
    since = datetime(1970, 1, 1, tzinfo=UTC)
    result = sync_live_journal(bybit=bybit, supabase=store, cache_path=path, now=now, since=since)
    assert len(requests) == 3
    assert all(r['end_ms'] - r['start_ms'] < 7 * 86400000 for r in requests)
    assert result.closed_segments == 1
    original = dict(store.rows)
    requests.clear()
    store.fail = True
    with pytest.raises(RuntimeError):
        sync_live_journal(bybit=bybit, supabase=store, cache_path=path, now=datetime(1970, 1, 17, tzinfo=UTC))
    with sqlite3.connect(path) as db:
        assert db.execute('select cursor_ms from journal_state').fetchone()[0] == int(now.timestamp() * 1000)
    store.fail = False
    sync_live_journal(bybit=bybit, supabase=store, cache_path=path, now=datetime(1970, 1, 17, tzinfo=UTC))
    assert {k: v for k, v in store.rows.items() if k[0] == 'trades'} == {k: v for k, v in original.items() if k[0] == 'trades'}


def test_history_boundary_cannot_change_on_existing_cache(tmp_path):
    path = tmp_path / 'journal.sqlite'
    bybit = SimpleNamespace(get_spot_executions=lambda **kw: [])
    now = datetime(2026, 10, 7, tzinfo=UTC)
    sync_live_journal(bybit=bybit, supabase=Store(), cache_path=path, now=now)
    with pytest.raises(ValueError, match='cannot be changed'):
        sync_live_journal(bybit=bybit, supabase=Store(), cache_path=path, now=now, since=now)


def test_extra_fees_and_missing_fee_amount_remain_unknown():
    buy = fill('b', 'Buy', '1', '2')
    buy['extraFees'] = '[{"feeCoin":"MNT","fee":"1"}]'
    sale = fill('s', 'Sell', '1', '3', time=2000)
    del sale['execFee']
    rows, result = reconstruct_trades([buy, sale])
    assert closed(rows)[0]['realized_pnl'] is None
    assert result.incomplete_fees == 1


def test_reconciliation_failure_records_health_without_logging_credentials(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('journal_executor_test', Path(__file__).parents[1] / 'scripts/run_supabase_live_executor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'sync_live_journal', lambda **kw: (_ for _ in ()).throw(RuntimeError('secret-token')))
    store = Store()
    assert module.reconcile_journal(SimpleNamespace(), store) is False
    health = store.rows[('bot_health', 'live_trade_journal')]
    assert health['status'] == 'error'
    assert 'secret-token' not in str(health)
    assert 'secret-token' not in capsys.readouterr().out
