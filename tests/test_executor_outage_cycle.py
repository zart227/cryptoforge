from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import sqlite3
from types import SimpleNamespace

import pytest
from scripts import run_supabase_live_executor as launcher
from cryptoforge.decision_outbox import DecisionOutbox
from cryptoforge.order_submission_journal import OrderSubmissionJournal
from test_supabase_executor import support_bounce_candles


def offline(*args, **kwargs):
    raise OSError('simulated remote outage')


def harness(tmp_path, monkeypatch, *, holding=True, kill=False):
    monkeypatch.chdir(tmp_path)
    now = datetime.now(UTC)
    closed = now.replace(minute=now.minute//5*5, second=0, microsecond=0)-timedelta(minutes=5)
    original = support_bounce_candles(); shift = closed-original[-1].open_time
    candles = [replace(row, open_time=row.open_time+shift) for row in original]
    sent = []
    bybit = SimpleNamespace(synchronize_time=lambda: 0,
        get_unified_usdt_balance=lambda: SimpleNamespace(total_equity_usd=Decimal('200'), usdt_wallet_balance=Decimal('100')),
        get_unified_wallet_coins=lambda: [dict(coin='USDT', usdValue='100')]+([dict(coin='HYPE', usdValue='97')] if holding else []),
        get_unified_coin_wallet_balance=lambda coin: Decimal('1' if holding and coin=='HYPE' else '0'),
        get_open_orders=lambda **kw: [],
        get_spot_instrument=lambda symbol: SimpleNamespace(quantity_step=Decimal('.0001'),
            minimum_quantity=Decimal('.0001'), minimum_order_amount=Decimal('5')),
        get_order_history=lambda **kw: [dict(side='Buy', orderStatus='Filled', avgPrice='110')],
        create_spot_market_order=lambda **intent: sent.append(intent) or dict(retCode=0, result=dict(orderId='fake-order')))
    remote = SimpleNamespace(upsert=offline)
    monkeypatch.setattr(launcher.SupabaseRestClient, 'from_env', lambda **kw: remote)
    monkeypatch.setattr(launcher, 'sync_live_journal', offline)
    monkeypatch.setattr(launcher, 'BybitOrderObserver', lambda **kw: SimpleNamespace(observe_filled_buys=offline))
    monkeypatch.setattr(launcher, 'NightResearchSelector', lambda *a: SimpleNamespace(select_pairs=offline))
    monkeypatch.setattr(launcher, 'SupabaseMarketReader', lambda *a: SimpleNamespace(read_candles=offline))
    writer = SimpleNamespace(write_bot_health=offline, write_tickers=offline, write_candles=offline)
    monkeypatch.setattr(launcher, 'SupabaseMarketWriter', lambda *a: writer)
    public = SimpleNamespace(get_tickers=lambda *a: [], get_klines=lambda *a, **kw: [SimpleNamespace(
        symbol=row.symbol, start_ms=int(row.open_time.timestamp()*1000), open=row.open, high=row.high,
        low=row.low, close=row.close, volume=row.volume) for row in candles])
    monkeypatch.setattr(launcher, 'BybitPublicClient', lambda **kw: public)
    state = tmp_path/'.local/state/live-equity-risk.json'; state.parent.mkdir(parents=True)
    state.write_text(json.dumps(dict(date=now.date().isoformat(), start_equity='200')))
    controls = tmp_path/'controls.json'
    controls.write_text(json.dumps(dict(schema_version='executor-controls-v1', kill_switch=kill, no_new_entry=True)))
    args = SimpleNamespace(fractional_risk_policy=None, timeout=1, pair=['HYPE/USDT'], use_night_research=True,
        night_research_limit=2, append_fallback_pairs=True, stake_amount='6', max_open_positions=6,
        max_daily_loss='2', drawdown_state=None, max_portfolio_drawdown=None, stop_loss_percent='.04',
        live=True, decision_outbox=tmp_path/'decisions.sqlite', execution_controls=controls,
        order_submission_journal=tmp_path/'orders.sqlite', settle_closed_reservations=False,
        submission_risk_guard=True, spot_reservation_guard=False, local_order_reservations=True,
        allow_intraday_reversion=True, allow_emerging_momentum=False, ml_mode='off',
        ml_threshold=.5, ml_max_age_hours=36, max_dust_fraction='.01', exit_data_fallback=True)
    return args, bybit, sent


def test_entire_cycle_keeps_exit_after_research_and_supabase_outage(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    assert launcher.run_cycle(args, bybit) == 1  # Remote journal still unhealthy.
    assert len(sent) == 1 and sent[0]['side'] == 'Sell'
    assert DecisionOutbox(args.decision_outbox).pending() == 1
    with sqlite3.connect(args.order_submission_journal) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'acknowledged'
    risk = json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert 'research pair selection unavailable; new entries paused' in risk['entry_blockers']
    assert 'operator no-new-entry active; buys paused' in risk['entry_blockers']
    assert risk['configured_protections']['order_submission_journal'] is True
    assert risk['configured_protections']['fractional_risk'] is False
    # A repeated cycle cannot resend the same original market order.
    assert launcher.run_cycle(args, bybit) == 1 and len(sent) == 1
    repeated = json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert 'decision outbox pending; new entries paused' in repeated['entry_blockers']


def test_entire_outage_cycle_cannot_submit_buy(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch, holding=False)
    assert launcher.run_cycle(args, bybit) == 1 and sent == []


def test_operator_kill_is_respected_on_emergency_exit_path(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch, kill=True)
    assert launcher.run_cycle(args, bybit) == 1 and sent == []
    with sqlite3.connect(args.order_submission_journal) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'blocked'


def test_diagnostic_write_failure_still_allows_exit(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    monkeypatch.setattr(launcher, 'write_json_report', offline)
    assert launcher.run_cycle(args, bybit) == 1
    assert len(sent) == 1 and sent[0]['side'] == 'Sell'


@pytest.mark.parametrize('failure', ['balance', 'inventory', 'none_inventory', 'nan_value', 'nan_equity', 'duplicate_coin'])
def test_account_wide_failure_preserves_per_symbol_exit_without_resetting_risk_state(tmp_path, monkeypatch, failure):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    state = tmp_path/'.local/state/live-equity-risk.json'; original = state.read_bytes()
    if failure == 'balance': bybit.get_unified_usdt_balance = offline
    if failure == 'inventory': bybit.get_unified_wallet_coins = offline
    if failure == 'none_inventory': bybit.get_unified_wallet_coins = lambda: None
    if failure == 'nan_value': bybit.get_unified_wallet_coins = lambda: [dict(coin='USDT',usdValue='100'),dict(coin='HYPE',usdValue='NaN')]
    if failure == 'nan_equity': bybit.get_unified_usdt_balance = lambda: SimpleNamespace(total_equity_usd=Decimal('NaN'), usdt_wallet_balance=Decimal('100'))
    if failure == 'duplicate_coin': bybit.get_unified_wallet_coins = lambda: [dict(coin='USDT',usdValue='100'),dict(coin='USDT',usdValue='100')]
    assert launcher.run_cycle(args, bybit) == 1
    assert len(sent) == 1 and sent[0]['side'] == 'Sell'
    assert state.read_bytes() == original
    risk = json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert risk['account_risk_data_status'] == 'unknown'
    assert risk['open_positions'] is None and risk['total_equity'] is None
    assert risk['available_entry_slots'] == 0


def test_account_failure_blocks_buy_without_claiming_success(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch, holding=False)
    bybit.get_unified_usdt_balance = offline
    monkeypatch.setattr(launcher, 'reconcile_journal', lambda *a: True)
    assert launcher.run_cycle(args, bybit) == 1 and sent == []


def test_fully_unavailable_private_position_data_never_submits_blind_sell(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    bybit.get_unified_usdt_balance = offline
    bybit.get_unified_coin_wallet_balance = offline
    assert launcher.run_cycle(args, bybit) == 1 and sent == []


def test_recovered_snapshot_adds_outside_fallback_holding_in_same_cycle(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    args.pair = ['ETH/USDT']
    healthy = bybit.get_unified_wallet_coins
    calls = []
    def recovering_inventory():
        calls.append('wallet')
        if len(calls) == 1: raise OSError('first inventory unavailable')
        return healthy()
    bybit.get_unified_wallet_coins = recovering_inventory
    assert launcher.run_cycle(args, bybit) == 1
    assert len(calls) == 2  # Reuse sizing snapshot, not another wallet query.
    assert len(sent) == 1 and sent[0]['symbol'] == 'HYPEUSDT' and sent[0]['side'] == 'Sell'
    risk = json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert risk['evaluation_pairs'] == ['ETH/USDT','HYPE/USDT']
    assert risk['open_positions'] == 1 and risk['account_risk_data_status'] == 'checked'


def test_consistent_held_snapshots_do_not_duplicate_exit_attempts(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    args.pair = ['HYPE/USDT', 'HYPE/USDT']
    assert launcher.run_cycle(args, bybit) == 1
    assert len(sent) == 1
    risk = json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert risk['evaluation_pairs'] == ['HYPE/USDT']


def test_total_exit_price_outage_is_unhealthy_even_with_healthy_reconciliation(tmp_path, monkeypatch):
    args, bybit, sent = harness(tmp_path, monkeypatch)
    monkeypatch.setattr(launcher, 'BybitPublicClient', lambda **kw: SimpleNamespace(
        get_tickers=lambda *a: [], get_klines=offline))
    monkeypatch.setattr(launcher, 'reconcile_journal', lambda *a: True)
    assert launcher.run_cycle(args, bybit) == 1
    assert sent == []
