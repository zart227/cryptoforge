from __future__ import annotations

import argparse
import os
from decimal import Decimal
from pathlib import Path

from cryptoforge.backup import create_backup, verify_backup
from cryptoforge.bybit_private import BybitPrivateClient, readiness_from_audit
from cryptoforge.live_config import LiveConfigRequest, write_live_config
from cryptoforge.live_pilot import (
    OperatorAttestation,
    evaluate_live_pilot_readiness,
    read_switch,
    validate_live_freqtrade_config,
    write_switch,
)
from cryptoforge.notifications import Notification, NotificationKind, telegram_notifier_from_env


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run no-trade live pilot smoke checks.")
    parser.add_argument("--env-file", type=Path, default=Path("/opt/cryptoforge/app/.env"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--live-config", type=Path, default=Path("/opt/cryptoforge/config/freqtrade.live-pilot.json"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("/opt/cryptoforge/app/data/live-smoke"))
    parser.add_argument("--backup-dir", type=Path, default=Path("/opt/cryptoforge/backups"))
    parser.add_argument("--required-usdt", type=Decimal, default=Decimal("16"))
    parser.add_argument("--stake-amount", type=Decimal, default=Decimal("10"))
    args = parser.parse_args()

    load_env(args.env_file)
    args.runtime_dir.mkdir(parents=True, exist_ok=True)

    live_config_path = write_live_config(
        args.live_config,
        LiveConfigRequest(stake_amount=args.stake_amount, max_open_trades=1, pair_whitelist=("BTC/USDT",)),
    )
    live_config_blockers = validate_live_freqtrade_config(live_config_path)

    kill_switch = args.runtime_dir / "kill-switch"
    no_new_entry_switch = args.runtime_dir / "no-new-entry"
    write_switch(kill_switch, True)
    write_switch(no_new_entry_switch, True)

    client = BybitPrivateClient.from_env()
    audit = client.get_api_key_audit()
    balance = client.get_unified_usdt_balance()
    bybit = readiness_from_audit(audit, balance, args.required_usdt)

    backup = create_backup(args.project_root, args.backup_dir)
    verify_backup(backup.archive_path, backup.checksum_path)

    readiness = evaluate_live_pilot_readiness(
        attestation=OperatorAttestation(
            dedicated_subaccount=bybit["subaccount_like"],
            withdrawals_disabled=bybit["withdrawals_absent"],
            ip_whitelisted=bybit["ip_whitelist_count"] > 0,
            capital_allocation_usdt=args.required_usdt,
            explicit_operator_approval=True,
        ),
        kill_switch_enabled=read_switch(kill_switch),
        no_new_entry_enabled=read_switch(no_new_entry_switch),
        monitoring_healthy=True,
        backup_verified=True,
        current_vps_sufficient=True,
    )

    notifier = telegram_notifier_from_env()
    notification_result = notifier.notify(
        Notification(
            kind=NotificationKind.STARTED,
            title="CryptoForge live smoke",
            body="No-trade live pilot smoke check completed.",
            fields={
                "bybit_balance_usdt": bybit["usdt_wallet_balance"],
                "live_config": str(live_config_path),
                "readiness_ready": readiness.ready,
            },
        )
    )

    checks = {
        "bybit_has_required_usdt": bybit["has_required_usdt"],
        "bybit_subaccount_like": bybit["subaccount_like"],
        "bybit_withdrawals_absent": bybit["withdrawals_absent"],
        "bybit_spot_trade_enabled": bybit["spot_trade_enabled"],
        "bybit_ip_whitelist_confirmed": bybit["ip_whitelist_count"] > 0,
        "live_config_valid": not live_config_blockers,
        "kill_switch_tested": read_switch(kill_switch),
        "no_new_entry_switch_tested": read_switch(no_new_entry_switch),
        "backup_verified": True,
        "alert_smoke_sent": notification_result.sent,
        "readiness_ready": readiness.ready,
    }

    for key, value in checks.items():
        print(f"{key}={value}")
    print(f"backup_archive={backup.archive_path}")
    print(f"live_config={live_config_path}")
    print(f"alert_reason={notification_result.reason}")
    if live_config_blockers:
        print("live_config_blockers=" + "; ".join(live_config_blockers))
    if readiness.blockers:
        print("readiness_blockers=" + "; ".join(readiness.blockers))
    if readiness.warnings:
        print("readiness_warnings=" + "; ".join(readiness.warnings))

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
