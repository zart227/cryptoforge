from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cryptoforge.market_data import Candle
from cryptoforge.outbox import SQLiteOutbox
from cryptoforge.trade_journal import (
    CanonicalTradeRecord,
    TradeFeatureSnapshot,
    TradeJournal,
    compute_mfe_mae_pct,
    validate_against_local_trade_state,
    validate_trade_record,
)


def feature_snapshot() -> TradeFeatureSnapshot:
    return TradeFeatureSnapshot(
        captured_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
        features={"rsi": "58", "ema_fast": "101", "ema_slow": "100"},
        market_snapshot={"spread_pct": "0.001", "volume_ratio": "1.2"},
    )


def record(**overrides) -> CanonicalTradeRecord:  # type: ignore[no-untyped-def]
    opened = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    values = {
        "trade_id": "dry-run-1",
        "external_trade_id": "freqtrade-1",
        "strategy_name": "CryptoForgeBaselineStrategy",
        "strategy_version": "cryptoforge-baseline-v0.1.0",
        "exchange": "bybit",
        "market_type": "spot",
        "mode": "dry_run",
        "pair": "BTC/USDT",
        "timeframe": "5m",
        "side": "long",
        "status": "closed",
        "opened_at": opened,
        "closed_at": opened + timedelta(minutes=30),
        "entry_price": Decimal("100"),
        "exit_price": Decimal("103"),
        "amount": Decimal("0.5"),
        "stake_amount": Decimal("50"),
        "fee_amount": Decimal("0.1"),
        "realized_pnl": Decimal("1.4"),
        "realized_pnl_pct": Decimal("0.028"),
        "stop_loss": Decimal("98"),
        "take_profit": Decimal("103"),
        "regime": "TREND_UP",
        "entry_reason": "ema_rsi_volume_atr_baseline",
        "exit_reason": "take_profit",
        "protection_context": {"protection_version": "sl-tp-v0.1.0"},
        "feature_snapshot": feature_snapshot(),
        "mfe_pct": Decimal("0.04"),
        "mae_pct": Decimal("-0.01"),
    }
    values.update(overrides)
    return CanonicalTradeRecord(**values)


def test_canonical_trade_payload_can_reconstruct_completed_trade() -> None:
    payload = record().as_payload()

    assert payload["trade_id"] == "dry-run-1"
    assert payload["strategy_version"] == "cryptoforge-baseline-v0.1.0"
    assert payload["pair"] == "BTC/USDT"
    assert payload["stop_loss"] == "98"
    assert payload["take_profit"] == "103"
    assert payload["feature_snapshot"]["features"]["rsi"] == "58"
    assert payload["mfe_pct"] == "0.04"
    assert payload["mae_pct"] == "-0.01"


def test_trade_journal_sends_durable_event_through_outbox(tmp_path) -> None:
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    journal = TradeJournal(outbox)

    journal.record_trade(record())

    due = outbox.due_events()
    assert len(due) == 1
    assert due[0].event_type == "trade.closed"
    assert due[0].idempotency_key == "trade-journal:dry_run:dry-run-1:closed"
    assert due[0].payload["pair"] == "BTC/USDT"
    assert outbox.stats().pending_count == 1


def test_trade_context_survives_outbox_reopen(tmp_path) -> None:
    db_path = tmp_path / "outbox.sqlite3"
    TradeJournal(SQLiteOutbox(db_path)).record_trade(record())

    reopened = SQLiteOutbox(db_path)
    due = reopened.due_events()

    assert len(due) == 1
    assert due[0].payload["entry_reason"] == "ema_rsi_volume_atr_baseline"
    assert due[0].payload["protection_context"]["protection_version"] == "sl-tp-v0.1.0"


def test_validate_trade_record_rejects_incomplete_closed_trade() -> None:
    with pytest.raises(ValueError, match="closed trades require exit_price"):
        validate_trade_record(record(exit_price=None))
    with pytest.raises(ValueError, match="stop_loss must be below entry_price"):
        validate_trade_record(record(stop_loss=Decimal("101")))


def test_compute_mfe_mae_pct_from_overlapping_candles() -> None:
    candles = [
        Candle(
            symbol="BTCUSDT",
            interval="5",
            start_ms=idx * 300_000,
            open=Decimal("100"),
            high=Decimal("100") + Decimal(idx),
            low=Decimal("100") - Decimal(idx) / Decimal("2"),
            close=Decimal("100"),
            volume=Decimal("1"),
            turnover=Decimal("100"),
        )
        for idx in range(1, 5)
    ]

    mfe, mae = compute_mfe_mae_pct(
        entry_price=Decimal("100"),
        opened_at_ms=300_000,
        closed_at_ms=1_500_000,
        candles=candles,
    )

    assert mfe == Decimal("0.04")
    assert mae == Decimal("-0.02")


def test_validate_against_local_trade_state() -> None:
    validate_against_local_trade_state(
        record(),
        {
            "pair": "BTC/USDT",
            "amount": "0.5",
            "entry_price": "100",
            "status": "closed",
        },
    )

    with pytest.raises(ValueError, match="local trade state mismatch"):
        validate_against_local_trade_state(record(), {"pair": "ETH/USDT"})
