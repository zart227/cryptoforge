from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from cryptoforge.metrics import PerformanceMetrics


class CandidateRole(StrEnum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    CONTROL = "CONTROL"


@dataclass(frozen=True)
class StrategyCandidate:
    strategy_name: str
    strategy_version: str
    role: CandidateRole
    dataset_id: str
    timerange: str
    status: str
    metadata: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "role": self.role.value,
            "dataset_id": self.dataset_id,
            "timerange": self.timerange,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ComparisonEvidence:
    champion: PerformanceMetrics
    challenger: PerformanceMetrics
    out_of_sample: PerformanceMetrics | None
    walk_forward: PerformanceMetrics | None
    regime_metrics: dict[str, PerformanceMetrics]

    def as_payload(self) -> dict[str, Any]:
        return {
            "champion": self.champion.as_payload(),
            "challenger": self.challenger.as_payload(),
            "out_of_sample": None
            if self.out_of_sample is None
            else self.out_of_sample.as_payload(),
            "walk_forward": None
            if self.walk_forward is None
            else self.walk_forward.as_payload(),
            "regime_metrics": {
                key: metrics.as_payload() for key, metrics in self.regime_metrics.items()
            },
        }


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reason: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class PromotionCriteria:
    min_expectancy_delta: Decimal = Decimal("0")
    min_profit_factor_delta: Decimal = Decimal("0.05")
    max_drawdown_multiplier: Decimal = Decimal("1.10")
    require_out_of_sample: bool = True
    require_walk_forward: bool = True
    require_regime_evidence: bool = True


def baseline_champion_candidate() -> StrategyCandidate:
    return StrategyCandidate(
        strategy_name="CryptoForgeBaselineStrategy",
        strategy_version="cryptoforge-baseline-v0.1.0",
        role=CandidateRole.CHAMPION,
        dataset_id="bybit_spot_btcusdt_5m_20260923_20260925",
        timerange="20260923-20260925",
        status="BACKTESTED",
        metadata={
            "purpose": "initial transparent control/champion candidate",
            "live_enabled": False,
        },
    )


def compare_champion_challenger(
    champion: StrategyCandidate,
    challenger: StrategyCandidate,
    evidence: ComparisonEvidence,
    *,
    criteria: PromotionCriteria | None = None,
) -> PromotionDecision:
    criteria = criteria or PromotionCriteria()
    reasons: list[str] = []

    if champion.dataset_id != challenger.dataset_id or champion.timerange != challenger.timerange:
        reasons.append("champion and challenger were not evaluated on equivalent data")
    if criteria.require_out_of_sample and evidence.out_of_sample is None:
        reasons.append("missing out-of-sample evidence")
    if criteria.require_walk_forward and evidence.walk_forward is None:
        reasons.append("missing walk-forward evidence")
    if criteria.require_regime_evidence and not evidence.regime_metrics:
        reasons.append("missing regime-specific evidence")

    champion_pf = evidence.champion.profit_factor or Decimal("0")
    challenger_pf = evidence.challenger.profit_factor or Decimal("0")
    if challenger_pf - champion_pf < criteria.min_profit_factor_delta:
        reasons.append("profit factor improvement is insufficient")
    if (
        evidence.challenger.expectancy - evidence.champion.expectancy
        <= criteria.min_expectancy_delta
    ):
        reasons.append("expectancy improvement is insufficient")
    if evidence.challenger.max_drawdown > (
        evidence.champion.max_drawdown * criteria.max_drawdown_multiplier
    ):
        reasons.append("challenger drawdown is too high")

    profit_only = (
        evidence.challenger.net_pnl > evidence.champion.net_pnl
        and len(reasons) > 0
    )
    if profit_only:
        reasons.append("absolute profit alone is not enough for promotion")

    if reasons:
        return PromotionDecision(
            promote=False,
            reason="; ".join(reasons),
            evidence=evidence.as_payload(),
        )
    return PromotionDecision(
        promote=True,
        reason="challenger passed equivalent-data, OOS, walk-forward and risk-adjusted checks",
        evidence=evidence.as_payload(),
    )
