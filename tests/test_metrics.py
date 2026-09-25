from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptoforge.metrics import (
    MetricsPublisher,
    compute_max_drawdown,
    compute_metrics,
    daily_metrics,
    regime_metrics,
    strategy_version_metrics,
)
from cryptoforge.outbox import SQLiteOutbox
from tests.test_trade_journal import record


def closed_trade(
    trade_id: str,
    pnl: str,
    pnl_pct: str,
    *,
    day_offset: int = 0,
    strategy_version: str = "v1",
    regime: str = "TREND_UP",
):
    opened = datetime(2026, 9, 25, 12, 0, tzinfo=UTC) + timedelta(days=day_offset)
    return record(
        trade_id=trade_id,
        strategy_version=strategy_version,
        regime=regime,
        opened_at=opened,
        closed_at=opened + timedelta(minutes=5),
        realized_pnl=Decimal(pnl),
        realized_pnl_pct=Decimal(pnl_pct),
        fee_amount=Decimal("0.10"),
    )


def test_compute_metrics_matches_controlled_sample() -> None:
    trades = [
        closed_trade("t1", "10", "0.10"),
        closed_trade("t2", "-4", "-0.04"),
        closed_trade("t3", "0", "0"),
        closed_trade("t4", "6", "0.06"),
    ]

    metrics = compute_metrics(trades)

    assert metrics.trade_count == 4
    assert metrics.net_pnl == Decimal("12")
    assert metrics.gross_profit == Decimal("16")
    assert metrics.gross_loss == Decimal("-4")
    assert metrics.fees == Decimal("0.40")
    assert metrics.win_rate == Decimal("0.5")
    assert metrics.profit_factor == Decimal("4")
    assert metrics.expectancy == Decimal("3")
    assert metrics.average_win == Decimal("8")
    assert metrics.average_loss == Decimal("-4")
    assert metrics.max_drawdown == Decimal("4")
    assert metrics.sharpe is not None


def test_metrics_do_not_treat_win_rate_as_primary_payload() -> None:
    metrics = compute_metrics([closed_trade("t1", "-1", "-0.01")])
    payload = metrics.as_payload()

    assert payload["net_pnl"] == "-1"
    assert payload["expectancy"] == "-1"
    assert payload["win_rate"] == "0"


def test_grouped_metrics_by_day_strategy_and_regime() -> None:
    trades = [
        closed_trade("t1", "1", "0.01", day_offset=0, strategy_version="v1", regime="RANGE"),
        closed_trade("t2", "2", "0.02", day_offset=1, strategy_version="v2", regime="RANGE"),
        closed_trade("t3", "-1", "-0.01", day_offset=1, strategy_version="v2", regime="TREND_DOWN"),
    ]

    by_day = daily_metrics(trades)
    by_strategy = strategy_version_metrics(trades)
    by_regime = regime_metrics(trades)

    assert len(by_day) == 2
    assert by_strategy["v2"].net_pnl == Decimal("1")
    assert by_regime["RANGE"].net_pnl == Decimal("3")
    assert by_regime["TREND_DOWN"].net_pnl == Decimal("-1")


def test_compute_max_drawdown_from_trade_pnl_curve() -> None:
    assert compute_max_drawdown(
        [Decimal("5"), Decimal("-2"), Decimal("-4"), Decimal("3")]
    ) == Decimal("6")


def test_metrics_publisher_persists_summary_through_outbox(tmp_path) -> None:
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    publisher = MetricsPublisher(outbox)
    metrics = compute_metrics([closed_trade("t1", "1", "0.01")], scope="daily:2026-09-25")

    publisher.publish(metrics, idempotency_key="metrics:daily:2026-09-25")

    due = outbox.due_events()
    assert len(due) == 1
    assert due[0].event_type == "metrics.summary"
    assert due[0].payload["scope"] == "daily:2026-09-25"
    assert due[0].payload["net_pnl"] == "1"
