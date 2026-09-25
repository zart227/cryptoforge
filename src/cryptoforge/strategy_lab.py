from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import Any

from cryptoforge.outbox import EventEnvelope, SQLiteOutbox


class ExperimentKind(StrEnum):
    PARAMETER_OPTIMIZATION = "parameter_optimization"
    MACHINE_LEARNING = "machine_learning"
    STRATEGY_DISCOVERY = "strategy_discovery"


class ExperimentStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ResourceSnapshot:
    available_ram_mb: int
    load_1m: float
    free_disk_gb: float
    trading_runtime_active: bool


@dataclass(frozen=True)
class ResearchPolicy:
    min_available_ram_mb: int = 350
    max_load_1m: float = 0.75
    min_free_disk_gb: float = 5.0
    max_parallel_backtests: int = 1
    heavy_search_active: bool = False
    trading_hours_start: time = time(8, 0)
    trading_hours_end: time = time(22, 0)


@dataclass(frozen=True)
class ExperimentPlan:
    experiment_id: str
    kind: ExperimentKind
    status: ExperimentStatus
    objective: str
    strategy_version: str
    dataset_id: str
    parameters: dict[str, Any]
    reproducibility: dict[str, Any]
    candidate_for_paper: bool
    live_risk_changes_allowed: bool = False

    def as_payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "objective": self.objective,
            "strategy_version": self.strategy_version,
            "dataset_id": self.dataset_id,
            "parameters": self.parameters,
            "reproducibility": self.reproducibility,
            "candidate_for_paper": self.candidate_for_paper,
            "live_risk_changes_allowed": self.live_risk_changes_allowed,
        }


@dataclass(frozen=True)
class LabDecision:
    allowed: bool
    reasons: tuple[str, ...]


class StrategyLab:
    def __init__(
        self,
        outbox: SQLiteOutbox,
        policy: ResearchPolicy | None = None,
    ) -> None:
        self.outbox = outbox
        self.policy = policy or ResearchPolicy()

    def create_experiment(
        self,
        *,
        kind: ExperimentKind,
        objective: str,
        strategy_version: str,
        dataset_id: str,
        parameters: dict[str, Any],
        reproducibility: dict[str, Any],
    ) -> ExperimentPlan:
        if kind == ExperimentKind.MACHINE_LEARNING and self.policy.heavy_search_active:
            raise ValueError("heavy continuous training is not allowed on current VPS")
        return ExperimentPlan(
            experiment_id=str(uuid.uuid4()),
            kind=kind,
            status=ExperimentStatus.PLANNED,
            objective=objective,
            strategy_version=strategy_version,
            dataset_id=dataset_id,
            parameters=parameters,
            reproducibility=reproducibility,
            candidate_for_paper=True,
            live_risk_changes_allowed=False,
        )

    def can_run(
        self,
        snapshot: ResourceSnapshot,
        *,
        current_time: time,
    ) -> LabDecision:
        reasons: list[str] = []
        if self.policy.heavy_search_active:
            reasons.append("heavy search is marked NOT ACTIVE on current VPS")
        if snapshot.trading_runtime_active and self.is_trading_hours(current_time):
            reasons.append("research deferred while trading runtime is active during trading hours")
        if snapshot.available_ram_mb < self.policy.min_available_ram_mb:
            reasons.append("insufficient available RAM")
        if snapshot.load_1m > self.policy.max_load_1m:
            reasons.append("load average too high")
        if snapshot.free_disk_gb < self.policy.min_free_disk_gb:
            reasons.append("insufficient free disk")
        return LabDecision(allowed=not reasons, reasons=tuple(reasons))

    def persist_experiment(self, plan: ExperimentPlan) -> None:
        self.outbox.enqueue(
            EventEnvelope(
                event_type="experiment.planned",
                source="cryptoforge.strategy_lab",
                severity="info",
                idempotency_key=f"experiment:{plan.experiment_id}:planned",
                payload=plan.as_payload(),
            )
        )

    def is_trading_hours(self, current_time: time) -> bool:
        start = self.policy.trading_hours_start
        end = self.policy.trading_hours_end
        if start <= end:
            return start <= current_time < end
        return current_time >= start or current_time < end


def low_priority_research_prefix() -> str:
    return "nice -n 10 ionice -c2 -n7"
