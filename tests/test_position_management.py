from decimal import Decimal

import pytest

from cryptoforge.position_management import (
    PositionProtectionConfig,
    PositionProtectionPlanner,
    PositionState,
    StopMethod,
    TakeProfitMethod,
)
from cryptoforge.risk import PortfolioState, RiskDecision, RiskEngine


def portfolio() -> PortfolioState:
    return PortfolioState(
        equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        daily_realized_pnl=Decimal("0"),
        open_positions=0,
    )


def test_protection_plan_defines_stop_take_profit_and_journal_context() -> None:
    planner = PositionProtectionPlanner(RiskEngine())

    plan = planner.plan(pair="BTC/USDT", entry_price=Decimal("100"), atr=Decimal("1"))

    assert plan.stop_loss == Decimal("98.00")
    assert plan.take_profit == Decimal("103.000")
    assert plan.stop_distance_pct == Decimal("0.02")
    assert plan.risk_reward == Decimal("1.5")
    assert plan.journal_context()["protection_version"] == "sl-tp-v0.1.0"
    assert plan.journal_context()["stop_loss"] == "98.00"


def test_stop_distance_feeds_risk_engine_position_sizing() -> None:
    planner = PositionProtectionPlanner(RiskEngine())

    entry = planner.evaluate_entry(
        pair="BTC/USDT",
        entry_price=Decimal("100"),
        atr=Decimal("1"),
        portfolio=portfolio(),
    )

    assert entry.approved
    assert entry.risk_result.position_size is not None
    assert entry.risk_result.position_size.stop_distance_pct == entry.plan.stop_distance_pct
    assert entry.risk_result.position_size.notional == Decimal("50.00000000")


def test_trade_cannot_open_without_valid_risk_definition() -> None:
    planner = PositionProtectionPlanner(RiskEngine())

    with pytest.raises(ValueError):
        planner.evaluate_entry(
            pair="BTC/USDT",
            entry_price=Decimal("100"),
            atr=None,
            portfolio=portfolio(),
        )


def test_fixed_pct_stop_and_atr_take_profit_are_supported() -> None:
    planner = PositionProtectionPlanner(
        RiskEngine(),
        PositionProtectionConfig(
            stop_method=StopMethod.FIXED_PCT,
            take_profit_method=TakeProfitMethod.ATR,
            fixed_stop_pct=Decimal("0.01"),
            atr_multiple_take_profit=Decimal("4"),
        ),
    )

    plan = planner.plan(pair="BTC/USDT", entry_price=Decimal("100"), atr=Decimal("1"))

    assert plan.stop_loss == Decimal("99.00")
    assert plan.take_profit == Decimal("104")
    assert plan.stop_method == StopMethod.FIXED_PCT
    assert plan.take_profit_method == TakeProfitMethod.ATR


def test_gap_through_stop_exits_at_stop_loss_reason() -> None:
    planner = PositionProtectionPlanner(RiskEngine())
    state = PositionState(
        entry_price=Decimal("100"),
        initial_stop_loss=Decimal("98"),
        stop_loss=Decimal("98"),
        take_profit=Decimal("103"),
        highest_price=Decimal("100"),
    )

    update = planner.update_position(state, current_price=Decimal("95"))

    assert update.exit_reason == "stop_loss"
    assert update.state == state


def test_fast_move_through_take_profit_exits_at_take_profit_reason() -> None:
    planner = PositionProtectionPlanner(RiskEngine())
    state = PositionState(
        entry_price=Decimal("100"),
        initial_stop_loss=Decimal("98"),
        stop_loss=Decimal("98"),
        take_profit=Decimal("103"),
        highest_price=Decimal("100"),
    )

    update = planner.update_position(state, current_price=Decimal("110"))

    assert update.exit_reason == "take_profit"


def test_break_even_and_trailing_state_machine_only_raises_stop() -> None:
    planner = PositionProtectionPlanner(RiskEngine())
    state = PositionState(
        entry_price=Decimal("100"),
        initial_stop_loss=Decimal("98"),
        stop_loss=Decimal("98"),
        take_profit=Decimal("110"),
        highest_price=Decimal("100"),
    )

    break_even = planner.update_position(state, current_price=Decimal("102"))
    assert break_even.exit_reason is None
    assert break_even.state.stop_loss == Decimal("100")
    assert break_even.state.break_even_applied
    assert not break_even.state.trailing_active

    trailing = planner.update_position(break_even.state, current_price=Decimal("104"))
    assert trailing.state.trailing_active
    assert trailing.state.stop_loss == Decimal("102")

    pullback = planner.update_position(trailing.state, current_price=Decimal("103"))
    assert pullback.state.stop_loss == Decimal("102")
    assert pullback.state.highest_price == Decimal("104")


def test_no_new_trade_guard_flows_through_protected_entry() -> None:
    planner = PositionProtectionPlanner(RiskEngine())

    entry = planner.evaluate_entry(
        pair="BTC/USDT",
        entry_price=Decimal("100"),
        atr=Decimal("1"),
        portfolio=PortfolioState(
            equity=Decimal("1000"),
            peak_equity=Decimal("1000"),
            daily_realized_pnl=Decimal("-20"),
            open_positions=0,
        ),
    )

    assert entry.risk_result.decision == RiskDecision.NO_NEW_TRADES
    assert entry.plan.stop_loss == Decimal("98.00")
