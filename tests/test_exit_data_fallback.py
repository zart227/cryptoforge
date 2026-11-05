from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
from cryptoforge.supabase_executor import ExecutorDecision, SupabaseLiveExecutor
from test_supabase_executor import support_bounce_candles


def setup_case(primary='error', holding=True):
    candles = support_bounce_candles()
    now = candles[-1].open_time + timedelta(minutes=5)
    def read(*args, **kwargs):
        if primary == 'error':
            raise OSError('primary unavailable')
        if primary == 'missing':
            return []
        if primary == 'stale':
            return candles[:-4]
        return candles
    orders = []
    bybit = SimpleNamespace(get_open_orders=lambda **kw: [],
        get_unified_coin_wallet_balance=lambda coin: Decimal('1' if holding else '0'),
        get_spot_instrument=lambda symbol: SimpleNamespace(quantity_step=Decimal('.001'),
            minimum_quantity=Decimal('.001'), minimum_order_amount=Decimal('5')),
        get_order_history=lambda **kw: [dict(side='Buy', orderStatus='Filled', avgPrice='110')],
        create_spot_market_order=lambda **kw: orders.append(kw) or {'orderId': 'test'})
    executor = SupabaseLiveExecutor(reader=SimpleNamespace(read_candles=read),
        bybit=bybit, supabase=SimpleNamespace(), allow_intraday_reversion=True,
        entry_blockers=('existing risk blocker',))
    executor._record = lambda pair, decision, reasons, candles, live, order=None: ExecutorDecision(
        decision, pair, tuple(reasons), order)
    public = SimpleNamespace(get_klines=lambda *a, **kw: [SimpleNamespace(
        symbol=c.symbol, start_ms=int(c.open_time.timestamp()*1000), open=c.open, high=c.high,
        low=c.low, close=c.close, volume=c.volume) for c in candles])
    return executor, public, now, orders


@pytest.mark.parametrize('failure', ['error', 'missing', 'stale'])
def test_primary_failure_still_checks_and_submits_existing_stop(failure):
    executor, public, now, orders = setup_case(failure)
    reader, blockers = executor.reader, executor.entry_blockers
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'approve_exit'
    assert len(orders) == 1 and orders[0]['side'] == 'Sell'
    assert executor.reader is reader and executor.entry_blockers == blockers
    assert any('entry_disabled' in reason for reason in result.reasons)


def test_fallback_cannot_enable_new_buy_even_without_other_risk_blockers():
    executor, public, now, orders = setup_case(holding=False)
    executor.entry_blockers = ()
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'reject_entry' and orders == []
    assert 'exit_only_public_fallback; new entries paused' in result.reasons


@pytest.mark.parametrize('kind', ['outage', 'wrong_market', 'gap', 'nan', 'stale'])
def test_bad_fallback_does_not_submit_or_claim_exit(kind):
    executor, public, now, orders = setup_case()
    rows = public.get_klines()
    if kind == 'outage':
        def read(*a, **kw):
            raise OSError('public unavailable')
        public.get_klines = read
    else:
        if kind == 'wrong_market': rows[-1].symbol = 'BTCUSDT'
        if kind == 'gap': rows.pop(-2)
        if kind == 'nan': rows[-1].close = Decimal('NaN')
        if kind == 'stale': rows = rows[:-4]
        public.get_klines = lambda *a, **kw: rows
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'recovery_required' and orders == []
    assert 'exit_data_unavailable' in result.reasons[0]


def test_order_capable_call_is_never_retried_on_exception():
    executor, public, now, orders = setup_case()
    reader = executor.reader
    def submit_then_fail(*a, **kw):
        orders.append('attempted')
        raise OSError('unknown submission outcome')
    executor.run_once = submit_then_fail
    with pytest.raises(OSError, match='submission'):
        run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert orders == ['attempted'] and executor.reader is reader


def test_healthy_primary_never_requests_public_data():
    executor, public, now, orders = setup_case('healthy')
    public.get_klines = lambda *a, **kw: pytest.fail('unnecessary public request')
    assert run_with_exit_data_fallback(executor, public, 'HYPE/USDT', now=now).decision == 'approve_exit'
    assert orders == []


def test_missing_exit_data_blocks_later_entry_but_fresh_cycle_can_recover():
    executor, public, now, orders = setup_case(holding=False)
    executor.entry_blockers = ()
    healthy_public = public.get_klines
    public.get_klines = lambda *a, **kw: []
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'recovery_required'
    blocker = executor.entry_blockers[0]
    # Primary data becomes healthy for the next pair; prior outage still pauses buys.
    rows = healthy_public()
    from cryptoforge.supabase_executor import CandleRow
    from datetime import UTC, datetime
    candles = [CandleRow(pair='HYPE/USDT', symbol=r.symbol,
        open_time=datetime.fromtimestamp(r.start_ms/1000, UTC), open=r.open,
        high=r.high, low=r.low, close=r.close, volume=r.volume) for r in rows]
    executor.reader = SimpleNamespace(read_candles=lambda *a, **kw: candles)
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'reject_entry' and blocker in result.reasons
    assert orders == []
    fresh, public, now, orders = setup_case('healthy', holding=False)
    fresh.entry_blockers = ()
    fresh.bybit.get_unified_usdt_balance = lambda: SimpleNamespace(usdt_wallet_balance=Decimal('100'))
    result = run_with_exit_data_fallback(fresh, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'approve_entry' and len(orders) == 1


@pytest.mark.parametrize('primary', ['healthy', 'error'])
def test_existing_stop_does_not_depend_on_model_registry(primary):
    executor, public, now, orders = setup_case(primary)
    executor.ml_mode = 'gate'
    executor.active_model_registry = SimpleNamespace(latest=lambda **kw: pytest.fail('exit queried ML registry'))
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'approve_exit'
    assert len(orders) == 1 and orders[0]['side'] == 'Sell'


def test_price_outage_blocker_does_not_stop_later_held_position_exit():
    executor, public, now, orders = setup_case()
    healthy_public = public.get_klines
    public.get_klines = lambda *a, **kw: []
    assert run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now).decision == 'recovery_required'
    public.get_klines = healthy_public
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'approve_exit'
    assert len(orders) == 1 and orders[0]['side'] == 'Sell'
    assert any('exit_data_unavailable' in blocker for blocker in executor.entry_blockers)
