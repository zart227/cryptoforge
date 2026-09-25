from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from cryptoforge.metrics import PerformanceMetrics


class StrategyStatus(StrEnum):
    DRAFT = "DRAFT"
    BACKTESTED = "BACKTESTED"
    OUT_OF_SAMPLE_TESTED = "OUT_OF_SAMPLE_TESTED"
    WALK_FORWARD_TESTED = "WALK_FORWARD_TESTED"
    PAPER_TRADING = "PAPER_TRADING"
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


ALLOWED_TRANSITIONS: dict[StrategyStatus, set[StrategyStatus]] = {
    StrategyStatus.DRAFT: {StrategyStatus.BACKTESTED, StrategyStatus.REJECTED},
    StrategyStatus.BACKTESTED: {
        StrategyStatus.OUT_OF_SAMPLE_TESTED,
        StrategyStatus.REJECTED,
        StrategyStatus.RETIRED,
    },
    StrategyStatus.OUT_OF_SAMPLE_TESTED: {
        StrategyStatus.WALK_FORWARD_TESTED,
        StrategyStatus.REJECTED,
        StrategyStatus.RETIRED,
    },
    StrategyStatus.WALK_FORWARD_TESTED: {
        StrategyStatus.PAPER_TRADING,
        StrategyStatus.REJECTED,
        StrategyStatus.RETIRED,
    },
    StrategyStatus.PAPER_TRADING: {
        StrategyStatus.CANDIDATE,
        StrategyStatus.REJECTED,
        StrategyStatus.RETIRED,
    },
    StrategyStatus.CANDIDATE: {
        StrategyStatus.APPROVED,
        StrategyStatus.REJECTED,
        StrategyStatus.RETIRED,
    },
    StrategyStatus.APPROVED: {StrategyStatus.RETIRED},
    StrategyStatus.REJECTED: {StrategyStatus.DRAFT},
    StrategyStatus.RETIRED: set(),
}


@dataclass(frozen=True)
class StrategyLifecycleMetadata:
    strategy_name: str
    strategy_version: str
    status: StrategyStatus
    evidence: dict[str, Any]
    human_live_approval_required: bool = True

    def as_payload(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "status": self.status.value,
            "evidence": self.evidence,
            "human_live_approval_required": self.human_live_approval_required,
        }


@dataclass(frozen=True)
class EvaluationCriteria:
    min_trade_count: int = 30
    min_profit_factor: Decimal = Decimal("1.10")
    min_expectancy: Decimal = Decimal("0")
    min_sharpe: Decimal = Decimal("0")
    min_sortino: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("50")
    max_loss_streak: int = 5


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    reasons: tuple[str, ...]
    evidence: dict[str, Any]


def transition_status(
    current: StrategyStatus,
    target: StrategyStatus,
) -> StrategyStatus:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid lifecycle transition {current.value} -> {target.value}")
    return target


def evaluate_strategy(
    metrics: PerformanceMetrics,
    *,
    criteria: EvaluationCriteria | None = None,
    loss_streak: int = 0,
) -> EvaluationResult:
    criteria = criteria or EvaluationCriteria()
    reasons: list[str] = []

    if metrics.trade_count < criteria.min_trade_count:
        reasons.append("insufficient trade count")
    if metrics.profit_factor is None or metrics.profit_factor < criteria.min_profit_factor:
        reasons.append("profit factor below threshold")
    if metrics.expectancy <= criteria.min_expectancy:
        reasons.append("expectancy below threshold")
    if metrics.sharpe is None or metrics.sharpe < criteria.min_sharpe:
        reasons.append("Sharpe below threshold")
    if metrics.sortino is None or metrics.sortino < criteria.min_sortino:
        reasons.append("Sortino below threshold")
    if metrics.max_drawdown > criteria.max_drawdown:
        reasons.append("drawdown above threshold")
    if loss_streak > criteria.max_loss_streak:
        reasons.append("loss streak above threshold")

    return EvaluationResult(
        passed=not reasons,
        reasons=tuple(reasons),
        evidence={
            "metrics": metrics.as_payload(),
            "criteria": {
                "min_trade_count": criteria.min_trade_count,
                "min_profit_factor": str(criteria.min_profit_factor),
                "min_expectancy": str(criteria.min_expectancy),
                "min_sharpe": str(criteria.min_sharpe),
                "min_sortino": str(criteria.min_sortino),
                "max_drawdown": str(criteria.max_drawdown),
                "max_loss_streak": criteria.max_loss_streak,
            },
            "loss_streak": loss_streak,
        },
    )


def recommend_next_status(
    current: StrategyStatus,
    evaluation: EvaluationResult,
) -> StrategyStatus:
    if not evaluation.passed:
        return StrategyStatus.REJECTED
    ordered = [
        StrategyStatus.DRAFT,
        StrategyStatus.BACKTESTED,
        StrategyStatus.OUT_OF_SAMPLE_TESTED,
        StrategyStatus.WALK_FORWARD_TESTED,
        StrategyStatus.PAPER_TRADING,
        StrategyStatus.CANDIDATE,
        StrategyStatus.APPROVED,
    ]
    if current not in ordered:
        return current
    next_status = ordered[min(ordered.index(current) + 1, len(ordered) - 1)]
    return transition_status(current, next_status)
