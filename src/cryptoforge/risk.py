from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum


class RiskDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NO_NEW_TRADES = "NO_NEW_TRADES"


@dataclass(frozen=True)
class HardRiskConfig:
    virtual_capital: Decimal = Decimal("1000")
    risk_per_trade_pct: Decimal = Decimal("0.005")
    max_simultaneous_positions: int = 2
    daily_loss_limit_pct: Decimal = Decimal("0.02")
    max_portfolio_drawdown_pct: Decimal = Decimal("0.10")
    taker_fee_pct: Decimal = Decimal("0.001")
    min_order_notional: Decimal = Decimal("5")
    min_order_qty: Decimal = Decimal("0.000001")
    qty_step: Decimal = Decimal("0.000001")
    max_position_notional_pct: Decimal = Decimal("0.05")
    fail_safe_max_outbox_age_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.virtual_capital <= 0:
            raise ValueError("virtual_capital must be positive")
        if not Decimal("0") < self.risk_per_trade_pct <= Decimal("0.005"):
            raise ValueError("risk_per_trade_pct must be > 0 and <= 0.5%")
        if self.max_simultaneous_positions < 1:
            raise ValueError("max_simultaneous_positions must be >= 1")
        if not Decimal("0") < self.daily_loss_limit_pct <= Decimal("0.02"):
            raise ValueError("daily_loss_limit_pct must be > 0 and <= 2%")
        if not Decimal("0") < self.max_portfolio_drawdown_pct <= Decimal("0.10"):
            raise ValueError("max_portfolio_drawdown_pct must be > 0 and <= 10%")
        if self.taker_fee_pct < 0:
            raise ValueError("taker_fee_pct cannot be negative")
        if self.min_order_notional <= 0:
            raise ValueError("min_order_notional must be positive")
        if self.min_order_qty <= 0 or self.qty_step <= 0:
            raise ValueError("min_order_qty and qty_step must be positive")
        if not Decimal("0") < self.max_position_notional_pct <= Decimal("0.05"):
            raise ValueError("max_position_notional_pct must be > 0 and <= 5%")


@dataclass(frozen=True)
class PortfolioState:
    equity: Decimal
    peak_equity: Decimal
    daily_realized_pnl: Decimal
    open_positions: int
    oldest_pending_outbox_age_seconds: int | None = None


@dataclass(frozen=True)
class TradeRiskRequest:
    pair: str
    entry_price: Decimal
    stop_price: Decimal
    requested_notional: Decimal | None = None

    @property
    def stop_distance_pct(self) -> Decimal:
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.stop_price <= 0:
            raise ValueError("stop_price must be positive")
        if self.stop_price >= self.entry_price:
            raise ValueError("spot long stop_price must be below entry_price")
        return (self.entry_price - self.stop_price) / self.entry_price


@dataclass(frozen=True)
class PositionSize:
    qty: Decimal
    notional: Decimal
    risk_amount: Decimal
    estimated_fee_amount: Decimal
    stop_distance_pct: Decimal


@dataclass(frozen=True)
class RiskResult:
    decision: RiskDecision
    reasons: tuple[str, ...]
    position_size: PositionSize | None = None

    @property
    def approved(self) -> bool:
        return self.decision == RiskDecision.APPROVED


class RiskEngine:
    def __init__(self, config: HardRiskConfig | None = None) -> None:
        self.config = config or HardRiskConfig()

    def evaluate(self, request: TradeRiskRequest, state: PortfolioState) -> RiskResult:
        guard_reasons = self.no_new_trade_reasons(state)
        if guard_reasons:
            return RiskResult(RiskDecision.NO_NEW_TRADES, tuple(guard_reasons))

        try:
            position_size = self.calculate_position_size(request, state)
        except ValueError as exc:
            return RiskResult(RiskDecision.REJECTED, (str(exc),))

        reasons: list[str] = []
        if position_size.notional < self.config.min_order_notional:
            reasons.append("position notional below minimum order notional")
        if position_size.qty < self.config.min_order_qty:
            reasons.append("position quantity below minimum order quantity")
        if request.requested_notional is not None and request.requested_notional > position_size.notional:
            reasons.append("requested notional exceeds hard risk limit")

        if reasons:
            return RiskResult(RiskDecision.REJECTED, tuple(reasons), position_size)

        return RiskResult(
            RiskDecision.APPROVED,
            ("approved by independent hard-risk engine",),
            position_size,
        )

    def calculate_position_size(
        self,
        request: TradeRiskRequest,
        state: PortfolioState,
    ) -> PositionSize:
        if state.equity <= 0:
            raise ValueError("equity must be positive")

        stop_distance = request.stop_distance_pct
        round_trip_fee_pct = self.config.taker_fee_pct * Decimal("2")
        effective_risk_pct = stop_distance + round_trip_fee_pct
        if effective_risk_pct <= 0:
            raise ValueError("effective risk must be positive")

        risk_budget = state.equity * self.config.risk_per_trade_pct
        risk_based_notional = risk_budget / effective_risk_pct
        max_position_notional = state.equity * self.config.max_position_notional_pct
        notional = min(risk_based_notional, max_position_notional)
        if request.requested_notional is not None:
            notional = min(notional, request.requested_notional)

        qty = quantize_down(notional / request.entry_price, self.config.qty_step)
        notional = quantize_down(qty * request.entry_price, Decimal("0.00000001"))
        fee_amount = notional * round_trip_fee_pct

        return PositionSize(
            qty=qty,
            notional=notional,
            risk_amount=notional * stop_distance + fee_amount,
            estimated_fee_amount=fee_amount,
            stop_distance_pct=stop_distance,
        )

    def no_new_trade_reasons(self, state: PortfolioState) -> list[str]:
        reasons: list[str] = []
        if state.open_positions >= self.config.max_simultaneous_positions:
            reasons.append("max simultaneous positions reached")

        daily_loss_limit = self.config.virtual_capital * self.config.daily_loss_limit_pct
        if state.daily_realized_pnl <= -daily_loss_limit:
            reasons.append("daily loss limit reached")

        if state.peak_equity <= 0:
            reasons.append("peak equity must be positive")
        else:
            drawdown = (state.peak_equity - state.equity) / state.peak_equity
            if drawdown >= self.config.max_portfolio_drawdown_pct:
                reasons.append("max portfolio drawdown reached")

        if (
            state.oldest_pending_outbox_age_seconds is not None
            and state.oldest_pending_outbox_age_seconds
            >= self.config.fail_safe_max_outbox_age_seconds
        ):
            reasons.append("persistence outbox fail-safe exceeded")

        return reasons


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("step must be positive")
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step
