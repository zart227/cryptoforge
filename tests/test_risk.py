from decimal import Decimal

import pytest

from cryptoforge.risk import (
    HardRiskConfig,
    PortfolioState,
    RiskDecision,
    RiskEngine,
    TradeRiskRequest,
    quantize_down,
)


def state(**overrides) -> PortfolioState:  # type: ignore[no-untyped-def]
    values = {
        "equity": Decimal("1000"),
        "peak_equity": Decimal("1000"),
        "daily_realized_pnl": Decimal("0"),
        "open_positions": 0,
        "oldest_pending_outbox_age_seconds": None,
    }
    values.update(overrides)
    return PortfolioState(**values)


def request(**overrides) -> TradeRiskRequest:  # type: ignore[no-untyped-def]
    values = {
        "pair": "BTC/USDT",
        "entry_price": Decimal("100"),
        "stop_price": Decimal("98"),
        "requested_notional": None,
    }
    values.update(overrides)
    return TradeRiskRequest(**values)


def test_hard_config_rejects_limits_above_policy() -> None:
    with pytest.raises(ValueError):
        HardRiskConfig(risk_per_trade_pct=Decimal("0.006"))
    with pytest.raises(ValueError):
        HardRiskConfig(daily_loss_limit_pct=Decimal("0.021"))
    with pytest.raises(ValueError):
        HardRiskConfig(max_portfolio_drawdown_pct=Decimal("0.11"))
    with pytest.raises(ValueError):
        HardRiskConfig(max_position_notional_pct=Decimal("0.10"))


def test_position_size_accounts_for_stop_distance_fees_and_max_notional() -> None:
    engine = RiskEngine()
    result = engine.evaluate(request(), state())

    assert result.approved
    assert result.position_size is not None
    assert result.position_size.notional == Decimal("50.00000000")
    assert result.position_size.qty == Decimal("0.500000")
    assert result.position_size.stop_distance_pct == Decimal("0.02")
    assert result.position_size.estimated_fee_amount == Decimal("0.10000000000")
    assert result.position_size.risk_amount == Decimal("1.10000000000")


def test_requested_oversized_trade_is_rejected_even_if_clamped_size_exists() -> None:
    engine = RiskEngine()
    result = engine.evaluate(
        request(requested_notional=Decimal("500")),
        state(),
    )

    assert result.decision == RiskDecision.REJECTED
    assert "requested notional exceeds hard risk limit" in result.reasons
    assert result.position_size is not None
    assert result.position_size.notional == Decimal("50.00000000")


def test_requested_smaller_trade_can_be_approved() -> None:
    engine = RiskEngine()
    result = engine.evaluate(
        request(requested_notional=Decimal("20")),
        state(),
    )

    assert result.approved
    assert result.position_size is not None
    assert result.position_size.notional == Decimal("20.00000000")


def test_minimum_order_constraints_reject_too_small_size() -> None:
    engine = RiskEngine(
        HardRiskConfig(
            min_order_notional=Decimal("5"),
            min_order_qty=Decimal("0.001"),
            qty_step=Decimal("0.001"),
        )
    )

    result = engine.evaluate(
        request(entry_price=Decimal("100000"), stop_price=Decimal("99000")),
        state(equity=Decimal("100"), peak_equity=Decimal("100")),
    )

    assert result.decision == RiskDecision.REJECTED
    assert "position notional below minimum order notional" in result.reasons
    assert "position quantity below minimum order quantity" in result.reasons


def test_no_new_trade_guards_stop_entries() -> None:
    engine = RiskEngine()

    max_positions = engine.evaluate(request(), state(open_positions=2))
    daily_loss = engine.evaluate(
        request(),
        state(daily_realized_pnl=Decimal("-20")),
    )
    drawdown = engine.evaluate(
        request(),
        state(equity=Decimal("900"), peak_equity=Decimal("1000")),
    )
    outbox = engine.evaluate(
        request(),
        state(oldest_pending_outbox_age_seconds=3600),
    )

    assert max_positions.decision == RiskDecision.NO_NEW_TRADES
    assert daily_loss.decision == RiskDecision.NO_NEW_TRADES
    assert drawdown.decision == RiskDecision.NO_NEW_TRADES
    assert outbox.decision == RiskDecision.NO_NEW_TRADES
    assert "max simultaneous positions reached" in max_positions.reasons
    assert "daily loss limit reached" in daily_loss.reasons
    assert "max portfolio drawdown reached" in drawdown.reasons
    assert "persistence outbox fail-safe exceeded" in outbox.reasons


def test_invalid_stop_is_rejected() -> None:
    engine = RiskEngine()

    result = engine.evaluate(
        request(entry_price=Decimal("100"), stop_price=Decimal("101")),
        state(),
    )

    assert result.decision == RiskDecision.REJECTED
    assert result.reasons == ("spot long stop_price must be below entry_price",)


def test_quantize_down_respects_precision_step() -> None:
    assert quantize_down(Decimal("1.23456789"), Decimal("0.001")) == Decimal("1.234")
