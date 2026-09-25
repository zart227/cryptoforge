from cryptoforge.daily_summary import DailySummary, empty_daily_metrics
from cryptoforge.market_data import Freshness
from cryptoforge.monitoring import (
    ResourceSnapshot,
    RiskLimitSnapshot,
    evaluate_monitoring,
)
from cryptoforge.outbox import OutboxStats


def test_daily_summary_renders_user_visible_status() -> None:
    monitoring = evaluate_monitoring(
        trader_process_running=True,
        bybit_connected=True,
        market_freshness=Freshness(True, 10_000, 600_000, "fresh"),
        resources=ResourceSnapshot(
            load_1m=0.2,
            cpu_count=1,
            available_ram_mb=512,
            swap_used_mb=0,
            disk_free_gb=10,
        ),
        outbox=OutboxStats(0, 3, 0, None),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )

    summary = DailySummary(
        date="2026-09-25",
        mode="dry-run",
        metrics=empty_daily_metrics(),
        monitoring=monitoring,
        open_positions=0,
        notes=("real trading disabled",),
    ).render_text()

    assert "CryptoForge daily summary - 2026-09-25" in summary
    assert "mode: dry-run" in summary
    assert "monitoring: ok" in summary
    assert "allow_new_entries: True" in summary
    assert "real trading disabled" in summary


def test_daily_summary_shows_no_new_entry_reasons() -> None:
    monitoring = evaluate_monitoring(
        trader_process_running=False,
        bybit_connected=True,
        market_freshness=Freshness(True, 10_000, 600_000, "fresh"),
        resources=ResourceSnapshot(
            load_1m=0.2,
            cpu_count=1,
            available_ram_mb=512,
            swap_used_mb=0,
            disk_free_gb=10,
        ),
        outbox=OutboxStats(0, 3, 0, None),
        supabase_available=True,
        risk_limits=RiskLimitSnapshot(),
    )

    summary = DailySummary(
        date="2026-09-25",
        mode="dry-run",
        metrics=empty_daily_metrics(),
        monitoring=monitoring,
        open_positions=0,
    ).render_text()

    assert "allow_new_entries: False" in summary
    assert "trader process is not running" in summary
