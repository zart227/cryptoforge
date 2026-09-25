from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LivePilotPolicy:
    exchange_name: str = "bybit"
    trading_mode: str = "spot"
    margin_mode: str = ""
    require_dedicated_subaccount: bool = True
    require_withdrawals_disabled: bool = True
    require_ip_whitelist: bool = True
    require_explicit_capital: bool = True
    max_capital_allocation_usdt: Decimal = Decimal("100")
    max_position_notional_pct: Decimal = Decimal("0.05")
    max_simultaneous_positions: int = 2
    daily_loss_limit_pct: Decimal = Decimal("0.02")
    max_drawdown_pct: Decimal = Decimal("0.10")


@dataclass(frozen=True)
class OperatorAttestation:
    dedicated_subaccount: bool = False
    withdrawals_disabled: bool = False
    ip_whitelisted: bool = False
    capital_allocation_usdt: Decimal | None = None
    explicit_operator_approval: bool = False


@dataclass(frozen=True)
class LivePilotReadiness:
    ready: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_live_freqtrade_config(
    config_path: str | Path,
    *,
    policy: LivePilotPolicy | None = None,
) -> tuple[str, ...]:
    active_policy = policy or LivePilotPolicy()
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    blockers: list[str] = []

    if config.get("dry_run") is not False:
        blockers.append("live config must explicitly set dry_run=false")
    if config.get("trading_mode") != active_policy.trading_mode:
        blockers.append("live config must be Spot only")
    if config.get("margin_mode") not in ("", None):
        blockers.append("margin must be disabled")
    if config.get("exchange", {}).get("name") != active_policy.exchange_name:
        blockers.append("exchange must be Bybit")
    if "leverage" in json.dumps(config).lower():
        blockers.append("leverage settings are forbidden")
    if config.get("stake_amount") in (None, "unlimited"):
        blockers.append("stake_amount must be explicit and bounded")
    if int(config.get("max_open_trades", 9999)) > active_policy.max_simultaneous_positions:
        blockers.append("max_open_trades exceeds pilot policy")
    if not config.get("exchange", {}).get("key"):
        blockers.append("live config must use operator-supplied API key at runtime")
    if not config.get("exchange", {}).get("secret"):
        blockers.append("live config must use operator-supplied API secret at runtime")
    if config.get("telegram", {}).get("enabled") is True:
        blockers.append("Freqtrade built-in Telegram should stay disabled; use CryptoForge notifications")

    return tuple(blockers)


def evaluate_live_pilot_readiness(
    *,
    attestation: OperatorAttestation,
    kill_switch_enabled: bool,
    no_new_entry_enabled: bool,
    monitoring_healthy: bool,
    backup_verified: bool,
    current_vps_sufficient: bool,
    policy: LivePilotPolicy | None = None,
) -> LivePilotReadiness:
    active_policy = policy or LivePilotPolicy()
    blockers: list[str] = []
    warnings: list[str] = []

    if not attestation.explicit_operator_approval:
        blockers.append("explicit operator approval is required")
    if active_policy.require_dedicated_subaccount and not attestation.dedicated_subaccount:
        blockers.append("dedicated limited Bybit sub-account is required")
    if active_policy.require_withdrawals_disabled and not attestation.withdrawals_disabled:
        blockers.append("withdrawal permission must be absent")
    if active_policy.require_ip_whitelist and not attestation.ip_whitelisted:
        warnings.append("IP whitelist is not confirmed")
    if active_policy.require_explicit_capital and attestation.capital_allocation_usdt is None:
        blockers.append("capital allocation must be explicitly chosen")
    if (
        attestation.capital_allocation_usdt is not None
        and attestation.capital_allocation_usdt > active_policy.max_capital_allocation_usdt
    ):
        blockers.append("capital allocation exceeds pilot cap")
    if not kill_switch_enabled:
        blockers.append("live kill switch must be enabled and tested")
    if not no_new_entry_enabled:
        blockers.append("no-new-entry switch must be enabled and tested")
    if not monitoring_healthy:
        blockers.append("monitoring must be healthy")
    if not backup_verified:
        blockers.append("backup/restore must be verified immediately before live start")
    if not current_vps_sufficient:
        blockers.append("current VPS is insufficient; migrate or reduce scope first")

    return LivePilotReadiness(
        ready=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def read_switch(path: str | Path) -> bool:
    switch_path = Path(path)
    if not switch_path.exists():
        return False
    value = switch_path.read_text(encoding="utf-8").strip().lower()
    return value in {"1", "true", "enabled", "on"}


def write_switch(path: str | Path, enabled: bool) -> None:
    switch_path = Path(path)
    switch_path.parent.mkdir(parents=True, exist_ok=True)
    switch_path.write_text("enabled\n" if enabled else "disabled\n", encoding="utf-8")


def render_readiness(readiness: LivePilotReadiness) -> dict[str, Any]:
    return {
        "ready": readiness.ready,
        "blockers": list(readiness.blockers),
        "warnings": list(readiness.warnings),
    }
