from cryptoforge.market_data import Freshness
from cryptoforge.monitoring import (
    HealthStatus,
    OutboxThresholds,
    ResourceSnapshot,
    RiskLimitSnapshot,
    check_supabase_sync,
    evaluate_monitoring,
)
from cryptoforge.outbox import OutboxStats


def fresh_market() -> Freshness:
    return Freshness(
        is_fresh=True,
        age_ms=60_000,
        max_age_ms=600_000,
        reason="latest candle is fresh",
    )


def stale_market() -> Freshness:
    return Freshness(
        is_fresh=False,
        age_ms=900_000,
        max_age_ms=600_000,
        reason="latest candle is older than max age",
    )


def healthy_resources() -> ResourceSnapshot:
    return ResourceSnapshot(
        load_1m=0.4,
        cpu_count=1,
        available_ram_mb=512,
        swap_used_mb=32,
        disk_free_gb=10,
    )


def empty_outbox() -> OutboxStats:
    return OutboxStats(
        pending_count=0,
        delivered_count=12,
        dead_count=0,
        oldest_pending_age_seconds=None,
    )


def test_healthy_monitoring_allows_new_entries() -> None:
    summary = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=healthy_resources(),
        outbox=empty_outbox(),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )

    assert summary.status == HealthStatus.OK
    assert summary.allow_new_entries
    assert summary.no_new_entry_reasons == ()


def test_stale_market_data_blocks_new_entries() -> None:
    summary = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=stale_market(),
        resources=healthy_resources(),
        outbox=empty_outbox(),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )

    assert summary.status == HealthStatus.CRITICAL
    assert not summary.allow_new_entries
    assert any("stale market data" in reason for reason in summary.no_new_entry_reasons)


def test_bybit_connectivity_failure_blocks_new_entries() -> None:
    summary = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=False,
        market_freshness=fresh_market(),
        resources=healthy_resources(),
        outbox=empty_outbox(),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )

    assert not summary.allow_new_entries
    assert "Bybit connectivity failed" in summary.no_new_entry_reasons


def test_supabase_offline_is_visible_without_blocking_position_management() -> None:
    check = check_supabase_sync(
        False,
        OutboxStats(
            pending_count=3,
            delivered_count=10,
            dead_count=0,
            oldest_pending_age_seconds=120,
        ),
    )

    assert check.status == HealthStatus.WARNING
    assert not check.blocks_new_entries
    assert "local outbox" in check.message


def test_outbox_growth_warns_then_blocks_when_critical() -> None:
    warning = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=healthy_resources(),
        outbox=OutboxStats(101, 0, 0, 60),
        supabase_available=False,
        risk_limits=RiskLimitSnapshot(),
    )
    critical = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=healthy_resources(),
        outbox=OutboxStats(10, 0, 0, 3_600),
        supabase_available=False,
        risk_limits=RiskLimitSnapshot(),
    )

    assert warning.status == HealthStatus.WARNING
    assert warning.allow_new_entries
    assert critical.status == HealthStatus.CRITICAL
    assert not critical.allow_new_entries
    assert any("outbox_age" in reason for reason in critical.no_new_entry_reasons)


def test_disk_warning_and_critical_resource_fail_safe() -> None:
    warning = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=ResourceSnapshot(
            load_1m=0.5,
            cpu_count=1,
            available_ram_mb=512,
            swap_used_mb=64,
            disk_free_gb=4,
        ),
        outbox=empty_outbox(),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )
    critical = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=ResourceSnapshot(
            load_1m=4.0,
            cpu_count=1,
            available_ram_mb=64,
            swap_used_mb=900,
            disk_free_gb=0.5,
        ),
        outbox=empty_outbox(),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )

    assert warning.status == HealthStatus.WARNING
    assert warning.allow_new_entries
    assert critical.status == HealthStatus.CRITICAL
    assert not critical.allow_new_entries
    assert len(critical.no_new_entry_reasons) >= 4


def test_risk_limit_alerts_block_new_entries() -> None:
    summary = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=healthy_resources(),
        outbox=empty_outbox(),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(
            daily_loss_limit_reached=True,
            drawdown_limit_reached=True,
            max_positions_reached=True,
        ),
    )

    assert summary.status == HealthStatus.CRITICAL
    assert not summary.allow_new_entries
    assert "daily loss limit reached" in summary.no_new_entry_reasons
    assert "portfolio drawdown limit reached" in summary.no_new_entry_reasons
    assert "max simultaneous positions reached" in summary.no_new_entry_reasons


def test_custom_outbox_thresholds_can_match_risk_policy() -> None:
    summary = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=fresh_market(),
        resources=healthy_resources(),
        outbox=OutboxStats(1, 0, 0, 1_800),
        supabase_available=False,
        risk_limits=RiskLimitSnapshot(),
        outbox_thresholds=OutboxThresholds(
            max_pending_warning=10,
            max_pending_critical=100,
            max_oldest_age_warning_seconds=300,
            max_oldest_age_critical_seconds=1_800,
        ),
    )

    assert summary.status == HealthStatus.CRITICAL
    assert not summary.allow_new_entries
