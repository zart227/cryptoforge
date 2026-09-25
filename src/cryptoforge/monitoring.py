from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cryptoforge.market_data import Freshness
from cryptoforge.outbox import OutboxStats


class HealthStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    blocks_new_entries: bool = False


@dataclass(frozen=True)
class ResourceSnapshot:
    load_1m: float
    cpu_count: int
    available_ram_mb: float
    swap_used_mb: float
    disk_free_gb: float


@dataclass(frozen=True)
class ResourceThresholds:
    max_load_per_cpu_warning: float = 1.5
    max_load_per_cpu_critical: float = 3.0
    min_available_ram_mb_warning: float = 256.0
    min_available_ram_mb_critical: float = 128.0
    max_swap_used_mb_warning: float = 256.0
    max_swap_used_mb_critical: float = 768.0
    min_disk_free_gb_warning: float = 5.0
    min_disk_free_gb_critical: float = 1.0


@dataclass(frozen=True)
class OutboxThresholds:
    max_pending_warning: int = 100
    max_pending_critical: int = 500
    max_oldest_age_warning_seconds: float = 900.0
    max_oldest_age_critical_seconds: float = 3600.0


@dataclass(frozen=True)
class RiskLimitSnapshot:
    daily_loss_limit_reached: bool = False
    drawdown_limit_reached: bool = False
    max_positions_reached: bool = False


@dataclass(frozen=True)
class MonitoringSummary:
    checks: tuple[HealthCheck, ...]

    @property
    def status(self) -> HealthStatus:
        statuses = {check.status for check in self.checks}
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK

    @property
    def allow_new_entries(self) -> bool:
        return not any(check.blocks_new_entries for check in self.checks)

    @property
    def no_new_entry_reasons(self) -> tuple[str, ...]:
        return tuple(check.message for check in self.checks if check.blocks_new_entries)

    @property
    def visible_messages(self) -> tuple[str, ...]:
        return tuple(
            f"{check.name}: {check.status.value}: {check.message}"
            for check in self.checks
            if check.status != HealthStatus.OK
        )


def check_trader_process(is_running: bool) -> HealthCheck:
    if is_running:
        return HealthCheck("trader_process", HealthStatus.OK, "trader process is running")
    return HealthCheck(
        "trader_process",
        HealthStatus.CRITICAL,
        "trader process is not running",
        blocks_new_entries=True,
    )


def check_bybit_connectivity(is_connected: bool) -> HealthCheck:
    if is_connected:
        return HealthCheck("bybit_connectivity", HealthStatus.OK, "Bybit connectivity is healthy")
    return HealthCheck(
        "bybit_connectivity",
        HealthStatus.CRITICAL,
        "Bybit connectivity failed",
        blocks_new_entries=True,
    )


def check_market_freshness(freshness: Freshness) -> HealthCheck:
    if freshness.is_fresh:
        return HealthCheck("market_freshness", HealthStatus.OK, freshness.reason)
    return HealthCheck(
        "market_freshness",
        HealthStatus.CRITICAL,
        f"stale market data: {freshness.reason}",
        blocks_new_entries=True,
    )


def check_resources(
    snapshot: ResourceSnapshot,
    thresholds: ResourceThresholds | None = None,
) -> tuple[HealthCheck, ...]:
    limits = thresholds or ResourceThresholds()
    cpu_count = max(snapshot.cpu_count, 1)
    load_per_cpu = snapshot.load_1m / cpu_count
    checks: list[HealthCheck] = []

    checks.append(
        _threshold_check(
            name="cpu_load",
            value=load_per_cpu,
            warning=limits.max_load_per_cpu_warning,
            critical=limits.max_load_per_cpu_critical,
            higher_is_worse=True,
            unit="load/cpu",
            critical_blocks=True,
        )
    )
    checks.append(
        _threshold_check(
            name="ram_available",
            value=snapshot.available_ram_mb,
            warning=limits.min_available_ram_mb_warning,
            critical=limits.min_available_ram_mb_critical,
            higher_is_worse=False,
            unit="MiB",
            critical_blocks=True,
        )
    )
    checks.append(
        _threshold_check(
            name="swap_used",
            value=snapshot.swap_used_mb,
            warning=limits.max_swap_used_mb_warning,
            critical=limits.max_swap_used_mb_critical,
            higher_is_worse=True,
            unit="MiB",
            critical_blocks=True,
        )
    )
    checks.append(
        _threshold_check(
            name="disk_free",
            value=snapshot.disk_free_gb,
            warning=limits.min_disk_free_gb_warning,
            critical=limits.min_disk_free_gb_critical,
            higher_is_worse=False,
            unit="GiB",
            critical_blocks=True,
        )
    )
    return tuple(checks)


def check_outbox(
    stats: OutboxStats,
    thresholds: OutboxThresholds | None = None,
) -> tuple[HealthCheck, ...]:
    limits = thresholds or OutboxThresholds()
    checks: list[HealthCheck] = []

    checks.append(
        _threshold_check(
            name="outbox_depth",
            value=float(stats.pending_count),
            warning=float(limits.max_pending_warning),
            critical=float(limits.max_pending_critical),
            higher_is_worse=True,
            unit="pending",
            critical_blocks=True,
        )
    )

    oldest_age = stats.oldest_pending_age_seconds or 0.0
    checks.append(
        _threshold_check(
            name="outbox_age",
            value=oldest_age,
            warning=limits.max_oldest_age_warning_seconds,
            critical=limits.max_oldest_age_critical_seconds,
            higher_is_worse=True,
            unit="seconds",
            critical_blocks=True,
        )
    )

    if stats.dead_count > 0:
        checks.append(
            HealthCheck(
                "outbox_dead_letters",
                HealthStatus.WARNING,
                f"{stats.dead_count} outbox events are dead-lettered",
            )
        )
    else:
        checks.append(HealthCheck("outbox_dead_letters", HealthStatus.OK, "no dead-lettered outbox events"))

    return tuple(checks)


def check_supabase_sync(is_available: bool, stats: OutboxStats | None = None) -> HealthCheck:
    if is_available:
        return HealthCheck("supabase_sync", HealthStatus.OK, "Supabase sync is available")

    pending = 0 if stats is None else stats.pending_count
    return HealthCheck(
        "supabase_sync",
        HealthStatus.WARNING,
        f"Supabase sync is offline; local outbox is retaining {pending} pending events",
    )


def check_strategy_errors(recent_error_count: int) -> HealthCheck:
    if recent_error_count <= 0:
        return HealthCheck("strategy_errors", HealthStatus.OK, "no recent strategy errors")
    return HealthCheck(
        "strategy_errors",
        HealthStatus.CRITICAL,
        f"{recent_error_count} recent strategy errors",
        blocks_new_entries=True,
    )


def check_database_errors(recent_error_count: int) -> HealthCheck:
    if recent_error_count <= 0:
        return HealthCheck("database_errors", HealthStatus.OK, "no recent database errors")
    return HealthCheck(
        "database_errors",
        HealthStatus.WARNING,
        f"{recent_error_count} recent database errors",
    )


def check_risk_limits(snapshot: RiskLimitSnapshot) -> tuple[HealthCheck, ...]:
    checks: list[HealthCheck] = []
    if snapshot.daily_loss_limit_reached:
        checks.append(
            HealthCheck(
                "risk_daily_loss",
                HealthStatus.CRITICAL,
                "daily loss limit reached",
                blocks_new_entries=True,
            )
        )
    else:
        checks.append(HealthCheck("risk_daily_loss", HealthStatus.OK, "daily loss limit is clear"))

    if snapshot.drawdown_limit_reached:
        checks.append(
            HealthCheck(
                "risk_drawdown",
                HealthStatus.CRITICAL,
                "portfolio drawdown limit reached",
                blocks_new_entries=True,
            )
        )
    else:
        checks.append(HealthCheck("risk_drawdown", HealthStatus.OK, "portfolio drawdown limit is clear"))

    if snapshot.max_positions_reached:
        checks.append(
            HealthCheck(
                "risk_max_positions",
                HealthStatus.WARNING,
                "max simultaneous positions reached",
                blocks_new_entries=True,
            )
        )
    else:
        checks.append(HealthCheck("risk_max_positions", HealthStatus.OK, "position count is below limit"))

    return tuple(checks)


def summarize_checks(checks: tuple[HealthCheck, ...] | list[HealthCheck]) -> MonitoringSummary:
    return MonitoringSummary(tuple(checks))


def evaluate_monitoring(
    *,
    trader_process_running: bool,
    bybit_connected: bool,
    market_freshness: Freshness,
    resources: ResourceSnapshot,
    outbox: OutboxStats,
    supabase_available: bool,
    risk_limits: RiskLimitSnapshot,
    recent_database_errors: int = 0,
    recent_strategy_errors: int = 0,
    resource_thresholds: ResourceThresholds | None = None,
    outbox_thresholds: OutboxThresholds | None = None,
) -> MonitoringSummary:
    checks: list[HealthCheck] = [
        check_trader_process(trader_process_running),
        check_bybit_connectivity(bybit_connected),
        check_market_freshness(market_freshness),
        check_supabase_sync(supabase_available, outbox),
        check_database_errors(recent_database_errors),
        check_strategy_errors(recent_strategy_errors),
    ]
    checks.extend(check_resources(resources, resource_thresholds))
    checks.extend(check_outbox(outbox, outbox_thresholds))
    checks.extend(check_risk_limits(risk_limits))
    return summarize_checks(checks)


def _threshold_check(
    *,
    name: str,
    value: float,
    warning: float,
    critical: float,
    higher_is_worse: bool,
    unit: str,
    critical_blocks: bool,
) -> HealthCheck:
    if higher_is_worse:
        if value >= critical:
            return HealthCheck(
                name,
                HealthStatus.CRITICAL,
                f"{name} is {value:g} {unit}; critical threshold is {critical:g}",
                blocks_new_entries=critical_blocks,
            )
        if value >= warning:
            return HealthCheck(
                name,
                HealthStatus.WARNING,
                f"{name} is {value:g} {unit}; warning threshold is {warning:g}",
            )
    else:
        if value <= critical:
            return HealthCheck(
                name,
                HealthStatus.CRITICAL,
                f"{name} is {value:g} {unit}; critical threshold is {critical:g}",
                blocks_new_entries=critical_blocks,
            )
        if value <= warning:
            return HealthCheck(
                name,
                HealthStatus.WARNING,
                f"{name} is {value:g} {unit}; warning threshold is {warning:g}",
            )

    return HealthCheck(name, HealthStatus.OK, f"{name} is {value:g} {unit}")
