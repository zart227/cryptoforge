from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from cryptoforge.bybit_private import BybitSpotInstrument
from cryptoforge.supabase_executor import SupabaseLiveExecutor
from test_supabase_executor import support_bounce_candles


def make_executor(stake="5", holding="0", minimum="5", step="0.0001"):
    candles = support_bounce_candles()
    bybit = Mock()
    bybit.get_open_orders.return_value = []
    bybit.get_unified_coin_wallet_balance.return_value = Decimal(holding)
    bybit.get_spot_instrument.return_value = BybitSpotInstrument(
        "HYPEUSDT", Decimal(step), Decimal("0.001"), Decimal(minimum)
    )
    bybit.get_unified_usdt_balance.return_value = SimpleNamespace(
        usdt_wallet_balance=Decimal("100")
    )
    bybit.get_order_history.return_value = [
        {"side": "Buy", "orderStatus": "Filled", "avgPrice": "110"}
    ]
    bybit.create_spot_market_order.return_value = {"retCode": 0}
    executor = SupabaseLiveExecutor(
        reader=SimpleNamespace(read_candles=lambda *a, **kw: candles),
        supabase=Mock(), bybit=bybit, stake_amount=Decimal(stake),
        allow_intraday_reversion=True,
    )
    return executor, bybit, candles[-1].open_time


def test_minimum_sized_buy_is_blocked_before_live_order():
    executor, bybit, now = make_executor()
    decision = executor.run_once("HYPE/USDT", live=True, now=now)
    assert decision.decision == "reject_entry"
    assert any("exit would be below exchange minimum" in r for r in decision.reasons)
    bybit.create_spot_market_order.assert_not_called()


def test_sufficient_stake_can_enter_without_increasing_operator_cap():
    executor, bybit, now = make_executor(stake="6")
    assert executor.run_once("HYPE/USDT", live=True, now=now).decision == "approve_entry"
    assert bybit.create_spot_market_order.call_args.kwargs["qty"] == Decimal("6")


def test_rounding_can_make_stop_exit_unsellable():
    executor, bybit, now = make_executor(stake="6", step="0.04")
    executor.max_dust_fraction = Decimal("1")
    decision = executor.run_once("HYPE/USDT", live=True, now=now)
    assert decision.decision == "reject_entry"
    assert any("exit would be below exchange minimum" in r for r in decision.reasons)
    bybit.create_spot_market_order.assert_not_called()


def test_blocked_existing_stop_preserves_position_without_top_up():
    executor, bybit, now = make_executor(holding="0.05")
    decision = executor.run_once("HYPE/USDT", live=True, now=now)
    assert decision.decision == "hold"
    assert any("exit_blocked_by_exchange_minimum" in r for r in decision.reasons)
    assert "stop_loss=True" in decision.reasons
    bybit.create_spot_market_order.assert_not_called()


def test_sellable_stop_still_exits():
    executor, bybit, now = make_executor(holding="0.06")
    decision = executor.run_once("HYPE/USDT", live=True, now=now)
    assert decision.decision == "approve_exit"
    assert bybit.create_spot_market_order.call_args.kwargs["side"] == "Sell"
