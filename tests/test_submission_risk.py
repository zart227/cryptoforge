from datetime import UTC, datetime
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.submission_risk import SubmissionRiskClient


NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)
BUY = dict(symbol='BTCUSDT', side='Buy', qty=Decimal('6'), order_link_id='test')


def setup(tmp_path):
    state = tmp_path/'risk.json'
    state.write_text(json.dumps(dict(date='2026-10-15', start_equity='20')))
    sent = []
    account = SimpleNamespace(total_equity_usd=Decimal('20'), usdt_wallet_balance=Decimal('20'))
    coins = [dict(coin='USDT', usdValue='20')]
    client = SimpleNamespace(get_unified_usdt_balance=lambda: account,
        get_unified_wallet_coins=lambda: coins,
        create_spot_market_order=lambda **kw: sent.append(kw) or {'retCode': 0, 'result': {'orderId': 'id'}})
    guard = SubmissionRiskClient(client, maximum_stake=Decimal('6'), position_cap=2,
        maximum_daily_loss=Decimal('2'), state_path=state, clock=lambda: NOW)
    return guard, account, coins, sent


def test_balances_and_positions_are_rechecked_for_each_buy(tmp_path):
    guard, account, coins, sent = setup(tmp_path)
    guard.create_spot_market_order(**BUY)
    coins.extend([dict(coin='BTC', usdValue='6'), dict(coin='ETH', usdValue='6')])
    with pytest.raises(OrderControlBlocked, match='capacity'):
        guard.create_spot_market_order(**dict(BUY, order_link_id='second'))
    assert len(sent) == 1


@pytest.mark.parametrize('qty', ['7', '0', '-1', 'NaN', 'Infinity'])
def test_invalid_or_oversize_quote_amount_never_submitted(tmp_path, qty):
    guard, _, _, sent = setup(tmp_path)
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**dict(BUY, qty=Decimal(qty)))
    assert sent == []


def test_daily_loss_rechecked_and_baseline_never_reset(tmp_path):
    guard, account, _, sent = setup(tmp_path)
    account.total_equity_usd = Decimal('18')
    with pytest.raises(OrderControlBlocked, match='daily equity loss'):
        guard.create_spot_market_order(**BUY)
    assert json.loads((tmp_path/'risk.json').read_bytes())['start_equity'] == '20'
    assert sent == []


@pytest.mark.parametrize('problem', ['outage', 'nan', 'missing_usdt', 'duplicate', 'missing_value', 'low_wallet', 'state_missing'])
def test_unknown_risk_inputs_block_buy(tmp_path, problem):
    guard, account, coins, sent = setup(tmp_path)
    if problem == 'outage':
        def fail(): raise OSError('unavailable')
        guard.client.get_unified_usdt_balance = fail
    if problem == 'nan': account.total_equity_usd = Decimal('NaN')
    if problem == 'missing_usdt': coins.clear()
    if problem == 'duplicate': coins.append(dict(coins[0]))
    if problem == 'missing_value': coins.append(dict(coin='BTC'))
    if problem == 'low_wallet': account.usdt_wallet_balance = Decimal('5')
    if problem == 'state_missing': (tmp_path/'risk.json').unlink()
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**BUY)
    assert sent == []


def test_risk_data_outage_does_not_block_sell(tmp_path):
    guard, _, _, sent = setup(tmp_path)
    guard.client.get_unified_usdt_balance = lambda: pytest.fail('exit depends on entry risk data')
    guard.create_spot_market_order(**dict(BUY, side='Sell', qty=Decimal('.01')))
    assert sent[0]['side'] == 'Sell'


def test_journal_marks_risk_rejection_as_known_blocked(tmp_path):
    from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient
    import sqlite3
    guard, account, _, sent = setup(tmp_path)
    account.total_equity_usd = Decimal('17')
    path = tmp_path/'orders.sqlite'
    journaled = JournaledOrderClient(guard, OrderSubmissionJournal(path))
    with pytest.raises(OrderControlBlocked): journaled.create_spot_market_order(**BUY)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'blocked'
    assert sent == []


def test_limit_order_cannot_bypass_market_risk_contract(tmp_path):
    guard, _, _, sent = setup(tmp_path)
    with pytest.raises(OrderControlBlocked, match='outside'):
        guard.create_spot_limit_order(**BUY, price=Decimal('100'))
    assert sent == []


def test_actual_executor_buy_reaches_submission_guard(tmp_path):
    from test_exit_data_fallback import setup_case
    from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
    executor, public, now, sent = setup_case('healthy', holding=False)
    executor.entry_blockers = ()
    executor.stake_amount = Decimal('6')
    instrument = executor.bybit.get_spot_instrument('HYPEUSDT')
    instrument.quantity_step = Decimal('.0001')
    executor.bybit.get_spot_instrument = lambda symbol: instrument
    executor.bybit.get_unified_usdt_balance = lambda: SimpleNamespace(
        total_equity_usd=Decimal('20'), usdt_wallet_balance=Decimal('20'))
    executor.bybit.get_unified_wallet_coins = lambda: [dict(coin='USDT', usdValue='8'),
        dict(coin='BTC', usdValue='6'), dict(coin='ETH', usdValue='6')]
    state = tmp_path/'risk.json'
    state.write_text(json.dumps(dict(date=now.date().isoformat(), start_equity='20')))
    executor.bybit = SubmissionRiskClient(executor.bybit, maximum_stake=Decimal('6'), position_cap=2,
        maximum_daily_loss=Decimal('2'), state_path=state, clock=lambda: now)
    executor.shadow_observer = SimpleNamespace(before_buy=lambda **kw: None, after_buy=lambda *a: None)
    with pytest.raises(OrderControlBlocked, match='capacity'):
        run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert sent == []
