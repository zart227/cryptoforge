from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cryptoforge.outbox import OutboxStats


class RecoveryAction(StrEnum):
    VERIFY_CONFIG = "verify_config"
    START_TRADER = "start_trader"
    FLUSH_OUTBOX = "flush_outbox"
    START_RESEARCH = "start_research"
    VERIFY_HEALTH = "verify_health"


@dataclass(frozen=True)
class RecoveryPolicy:
    maintenance_window_open: bool = False
    vps_services_verified: bool = False
    resources_constrained: bool = True
    heavy_research_auto_start: bool = False


@dataclass(frozen=True)
class RecoveryState:
    config_valid: bool
    trader_running: bool
    outbox: OutboxStats
    local_state_ok: bool
    duplicate_trade_events_detected: bool = False


@dataclass(frozen=True)
class RecoveryPlan:
    actions: tuple[RecoveryAction, ...]
    allow_research_start: bool
    allow_reboot_test: bool
    reasons: tuple[str, ...]


def build_recovery_plan(state: RecoveryState, policy: RecoveryPolicy | None = None) -> RecoveryPlan:
    active_policy = policy or RecoveryPolicy()
    actions: list[RecoveryAction] = []
    reasons: list[str] = []

    if not state.config_valid:
        actions.append(RecoveryAction.VERIFY_CONFIG)
        reasons.append("configuration must be verified before runtime start")

    if not state.trader_running and state.config_valid and state.local_state_ok:
        actions.append(RecoveryAction.START_TRADER)
        reasons.append("trader starts before research")

    if state.outbox.has_pending or state.outbox.dead_count > 0:
        actions.append(RecoveryAction.FLUSH_OUTBOX)
        reasons.append("outbox must recover without manual database repair")

    if state.duplicate_trade_events_detected:
        reasons.append("duplicate trade events detected; research remains disabled")

    allow_research_start = (
        active_policy.heavy_research_auto_start
        and state.trader_running
        and state.local_state_ok
        and not active_policy.resources_constrained
        and not state.duplicate_trade_events_detected
    )
    if allow_research_start:
        actions.append(RecoveryAction.START_RESEARCH)
    else:
        reasons.append("heavy research does not auto-start during constrained recovery")

    actions.append(RecoveryAction.VERIFY_HEALTH)
    allow_reboot_test = active_policy.maintenance_window_open and active_policy.vps_services_verified
    if not allow_reboot_test:
        reasons.append("server reboot test requires maintenance window and verified existing VPS services")

    return RecoveryPlan(
        actions=tuple(dict.fromkeys(actions)),
        allow_research_start=allow_research_start,
        allow_reboot_test=allow_reboot_test,
        reasons=tuple(reasons),
    )


def detect_duplicate_ids(ids: list[str] | tuple[str, ...]) -> bool:
    return len(set(ids)) != len(ids)
