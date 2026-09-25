from cryptoforge.outbox import EventEnvelope, OutboxStats, SQLiteOutbox
from cryptoforge.recovery import (
    RecoveryAction,
    RecoveryPolicy,
    RecoveryState,
    build_recovery_plan,
    detect_duplicate_ids,
)
from tests.test_outbox import ManualClock, RecordingSink


def state(**overrides) -> RecoveryState:  # type: ignore[no-untyped-def]
    values = {
        "config_valid": True,
        "trader_running": False,
        "outbox": OutboxStats(
            pending_count=0,
            delivered_count=0,
            dead_count=0,
            oldest_pending_age_seconds=None,
        ),
        "local_state_ok": True,
        "duplicate_trade_events_detected": False,
    }
    values.update(overrides)
    return RecoveryState(**values)


def test_recovery_startup_order_starts_trader_before_research() -> None:
    plan = build_recovery_plan(state())

    assert plan.actions[0] == RecoveryAction.START_TRADER
    assert RecoveryAction.START_RESEARCH not in plan.actions
    assert RecoveryAction.VERIFY_HEALTH in plan.actions
    assert not plan.allow_research_start
    assert "trader starts before research" in plan.reasons


def test_heavy_research_can_start_only_after_healthy_unconstrained_runtime() -> None:
    plan = build_recovery_plan(
        state(trader_running=True),
        RecoveryPolicy(
            resources_constrained=False,
            heavy_research_auto_start=True,
            maintenance_window_open=True,
            vps_services_verified=True,
        ),
    )

    assert plan.allow_research_start
    assert RecoveryAction.START_RESEARCH in plan.actions
    assert plan.allow_reboot_test


def test_reboot_test_is_blocked_without_safe_window() -> None:
    plan = build_recovery_plan(
        state(trader_running=True),
        RecoveryPolicy(
            maintenance_window_open=False,
            vps_services_verified=False,
        ),
    )

    assert not plan.allow_reboot_test
    assert any("server reboot test requires maintenance window" in reason for reason in plan.reasons)


def test_outbox_recovery_survives_process_restart(tmp_path) -> None:
    clock = ManualClock()
    db_path = tmp_path / "outbox.sqlite3"
    outbox = SQLiteOutbox(db_path, clock=clock)
    outbox.enqueue(
        EventEnvelope(
            event_type="trade.closed",
            source="test",
            payload={"trade_id": "t1"},
            idempotency_key="trade-closed-t1",
        )
    )

    restarted = SQLiteOutbox(db_path, clock=clock)
    plan = build_recovery_plan(
        state(
            trader_running=True,
            outbox=restarted.stats(),
        )
    )

    assert RecoveryAction.FLUSH_OUTBOX in plan.actions
    result = restarted.flush_due(RecordingSink())
    assert result.delivered == 1
    assert restarted.stats().pending_count == 0


def test_duplicate_ids_keep_research_disabled() -> None:
    duplicate = detect_duplicate_ids(["trade-1", "trade-2", "trade-1"])
    plan = build_recovery_plan(
        state(
            trader_running=True,
            duplicate_trade_events_detected=duplicate,
        ),
        RecoveryPolicy(
            resources_constrained=False,
            heavy_research_auto_start=True,
        ),
    )

    assert duplicate
    assert not plan.allow_research_start
    assert RecoveryAction.START_RESEARCH not in plan.actions
    assert any("duplicate trade events detected" in reason for reason in plan.reasons)


def test_invalid_local_state_prevents_runtime_start() -> None:
    plan = build_recovery_plan(state(local_state_ok=False))

    assert RecoveryAction.START_TRADER not in plan.actions
    assert RecoveryAction.VERIFY_HEALTH in plan.actions
