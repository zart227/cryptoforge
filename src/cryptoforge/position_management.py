from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from cryptoforge.risk import (
    PortfolioState,
    RiskEngine,
    RiskResult,
    TradeRiskRequest,
)


class StopMethod(StrEnum):
    ATR = "ATR"
    FIXED_PCT = "FIXED_PCT"


class TakeProfitMethod(StrEnum):
    RISK_REWARD = "RISK_REWARD"
    ATR = "ATR"


@dataclass(frozen=True)
class PositionProtectionConfig:
    version: str = "sl-tp-v0.1.0"
    stop_method: StopMethod = StopMethod.ATR
    take_profit_method: TakeProfitMethod = TakeProfitMethod.RISK_REWARD
    atr_multiple_stop: Decimal = Decimal("2.0")
    atr_multiple_take_profit: Decimal = Decimal("3.0")
    fixed_stop_pct: Decimal = Decimal("0.02")
    min_stop_pct: Decimal = Decimal("0.005")
    max_stop_pct: Decimal = Decimal("0.04")
    risk_reward: Decimal = Decimal("1.5")
    break_even_trigger_r: Decimal = Decimal("1.0")
    trailing_trigger_r: Decimal = Decimal("2.0")
    trailing_distance_r: Decimal = Decimal("1.0")

    def __post_init__(self) -> None:
        if self.atr_multiple_stop <= 0 or self.atr_multiple_take_profit <= 0:
            raise ValueError("ATR multiples must be positive")
        if not Decimal("0") < self.fixed_stop_pct <= self.max_stop_pct:
            raise ValueError("fixed_stop_pct must be positive and <= max_stop_pct")
        if not Decimal("0") < self.min_stop_pct <= self.max_stop_pct:
            raise ValueError("min_stop_pct must be positive and <= max_stop_pct")
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be positive")
        if self.break_even_trigger_r <= 0:
            raise ValueError("break_even_trigger_r must be positive")
        if self.trailing_trigger_r <= 0 or self.trailing_distance_r <= 0:
            raise ValueError("trailing trigger/distance must be positive")


@dataclass(frozen=True)
class ProtectionPlan:
    pair: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    stop_distance: Decimal
    stop_distance_pct: Decimal
    take_profit_distance: Decimal
    risk_reward: Decimal
    version: str
    stop_method: StopMethod
    take_profit_method: TakeProfitMethod

    def journal_context(self) -> dict[str, str]:
        return {
            "protection_version": self.version,
            "stop_method": self.stop_method.value,
            "take_profit_method": self.take_profit_method.value,
            "entry_price": str(self.entry_price),
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "stop_distance_pct": str(self.stop_distance_pct),
            "risk_reward": str(self.risk_reward),
        }


@dataclass(frozen=True)
class ProtectedEntry:
    plan: ProtectionPlan
    risk_result: RiskResult

    @property
    def approved(self) -> bool:
        return self.risk_result.approved


@dataclass(frozen=True)
class PositionState:
    entry_price: Decimal
    initial_stop_loss: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    highest_price: Decimal
    break_even_applied: bool = False
    trailing_active: bool = False


@dataclass(frozen=True)
class PositionUpdate:
    state: PositionState
    exit_reason: str | None = None


class PositionProtectionPlanner:
    def __init__(
        self,
        risk_engine: RiskEngine,
        config: PositionProtectionConfig | None = None,
    ) -> None:
        self.risk_engine = risk_engine
        self.config = config or PositionProtectionConfig()

    def plan(
        self,
        *,
        pair: str,
        entry_price: Decimal,
        atr: Decimal | None,
    ) -> ProtectionPlan:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")

        stop_distance = self._stop_distance(entry_price, atr)
        stop_loss = entry_price - stop_distance
        if stop_loss <= 0:
            raise ValueError("computed stop_loss must be positive")

        take_profit_distance = self._take_profit_distance(stop_distance, atr)
        take_profit = entry_price + take_profit_distance
        risk_reward = take_profit_distance / stop_distance

        return ProtectionPlan(
            pair=pair,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance / entry_price,
            take_profit_distance=take_profit_distance,
            risk_reward=risk_reward,
            version=self.config.version,
            stop_method=self.config.stop_method,
            take_profit_method=self.config.take_profit_method,
        )

    def evaluate_entry(
        self,
        *,
        pair: str,
        entry_price: Decimal,
        atr: Decimal | None,
        portfolio: PortfolioState,
        requested_notional: Decimal | None = None,
    ) -> ProtectedEntry:
        plan = self.plan(pair=pair, entry_price=entry_price, atr=atr)
        risk_result = self.risk_engine.evaluate(
            TradeRiskRequest(
                pair=pair,
                entry_price=entry_price,
                stop_price=plan.stop_loss,
                requested_notional=requested_notional,
            ),
            portfolio,
        )
        return ProtectedEntry(plan=plan, risk_result=risk_result)

    def update_position(
        self,
        state: PositionState,
        *,
        current_price: Decimal,
    ) -> PositionUpdate:
        if current_price <= 0:
            raise ValueError("current_price must be positive")

        if current_price <= state.stop_loss:
            return PositionUpdate(state=state, exit_reason="stop_loss")
        if current_price >= state.take_profit:
            return PositionUpdate(state=state, exit_reason="take_profit")

        risk_unit = state.entry_price - state.initial_stop_loss
        if risk_unit <= 0:
            raise ValueError("state initial_stop_loss must be below entry_price")

        highest = max(state.highest_price, current_price)
        stop_loss = state.stop_loss
        break_even_applied = state.break_even_applied
        trailing_active = state.trailing_active
        profit_r = (highest - state.entry_price) / risk_unit

        if not break_even_applied and profit_r >= self.config.break_even_trigger_r:
            stop_loss = max(stop_loss, state.entry_price)
            break_even_applied = True

        if profit_r >= self.config.trailing_trigger_r:
            trailing_active = True
            trailing_stop = highest - (risk_unit * self.config.trailing_distance_r)
            stop_loss = max(stop_loss, trailing_stop)

        return PositionUpdate(
            state=PositionState(
                entry_price=state.entry_price,
                initial_stop_loss=state.initial_stop_loss,
                stop_loss=stop_loss,
                take_profit=state.take_profit,
                highest_price=highest,
                break_even_applied=break_even_applied,
                trailing_active=trailing_active,
            )
        )

    def _stop_distance(self, entry_price: Decimal, atr: Decimal | None) -> Decimal:
        if self.config.stop_method == StopMethod.FIXED_PCT:
            raw_pct = self.config.fixed_stop_pct
        else:
            if atr is None or atr <= 0:
                raise ValueError("positive ATR is required for ATR stop method")
            raw_pct = (atr * self.config.atr_multiple_stop) / entry_price

        clamped_pct = min(max(raw_pct, self.config.min_stop_pct), self.config.max_stop_pct)
        return entry_price * clamped_pct

    def _take_profit_distance(self, stop_distance: Decimal, atr: Decimal | None) -> Decimal:
        if self.config.take_profit_method == TakeProfitMethod.ATR:
            if atr is None or atr <= 0:
                raise ValueError("positive ATR is required for ATR take-profit method")
            return atr * self.config.atr_multiple_take_profit
        return stop_distance * self.config.risk_reward
