from decimal import Decimal

from cryptoforge.live_pilot import (
    OperatorAttestation,
    evaluate_live_pilot_readiness,
    read_switch,
    render_readiness,
    validate_live_freqtrade_config,
    write_switch,
)


def test_live_readiness_blocks_without_operator_attestation() -> None:
    readiness = evaluate_live_pilot_readiness(
        attestation=OperatorAttestation(),
        kill_switch_enabled=False,
        no_new_entry_enabled=False,
        monitoring_healthy=True,
        backup_verified=True,
        current_vps_sufficient=False,
    )

    assert not readiness.ready
    assert "explicit operator approval is required" in readiness.blockers
    assert "dedicated limited Bybit sub-account is required" in readiness.blockers
    assert "capital allocation must be explicitly chosen" in readiness.blockers
    assert "live kill switch must be enabled and tested" in readiness.blockers
    assert "current VPS is insufficient; migrate or reduce scope first" in readiness.blockers


def test_live_readiness_can_pass_only_with_all_gates() -> None:
    readiness = evaluate_live_pilot_readiness(
        attestation=OperatorAttestation(
            dedicated_subaccount=True,
            withdrawals_disabled=True,
            ip_whitelisted=True,
            capital_allocation_usdt=Decimal("25"),
            explicit_operator_approval=True,
        ),
        kill_switch_enabled=True,
        no_new_entry_enabled=True,
        monitoring_healthy=True,
        backup_verified=True,
        current_vps_sufficient=True,
    )

    assert readiness.ready
    assert readiness.blockers == ()
    assert render_readiness(readiness)["ready"] is True


def test_live_readiness_rejects_capital_above_pilot_cap() -> None:
    readiness = evaluate_live_pilot_readiness(
        attestation=OperatorAttestation(
            dedicated_subaccount=True,
            withdrawals_disabled=True,
            ip_whitelisted=True,
            capital_allocation_usdt=Decimal("1000"),
            explicit_operator_approval=True,
        ),
        kill_switch_enabled=True,
        no_new_entry_enabled=True,
        monitoring_healthy=True,
        backup_verified=True,
        current_vps_sufficient=True,
    )

    assert not readiness.ready
    assert "capital allocation exceeds pilot cap" in readiness.blockers


def test_live_config_validator_rejects_unsafe_or_incomplete_config(tmp_path) -> None:
    config = tmp_path / "live.json"
    config.write_text(
        """
        {
          "dry_run": false,
          "trading_mode": "futures",
          "margin_mode": "isolated",
          "max_open_trades": 10,
          "stake_amount": "unlimited",
          "leverage": 3,
          "exchange": {"name": "bybit", "key": "", "secret": ""},
          "telegram": {"enabled": true}
        }
        """,
        encoding="utf-8",
    )

    blockers = validate_live_freqtrade_config(config)

    assert "live config must be Spot only" in blockers
    assert "margin must be disabled" in blockers
    assert "leverage settings are forbidden" in blockers
    assert "stake_amount must be explicit and bounded" in blockers
    assert "max_open_trades exceeds pilot policy" in blockers
    assert "live config must use operator-supplied API key at runtime" in blockers
    assert "live config must use operator-supplied API secret at runtime" in blockers


def test_switch_files_are_explicit(tmp_path) -> None:
    switch = tmp_path / "kill-switch"

    assert not read_switch(switch)
    write_switch(switch, True)
    assert read_switch(switch)
    write_switch(switch, False)
    assert not read_switch(switch)
