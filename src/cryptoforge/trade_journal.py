from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cryptoforge.market_data import Candle
from cryptoforge.outbox import EventEnvelope, SQLiteOutbox


@dataclass(frozen=True)
class TradeFeatureSnapshot:
    captured_at: datetime
    features: dict[str, str]
    market_snapshot: dict[str, str]

    def as_payload(self) -> dict[str, Any]:
        return {
            "captured_at": isoformat_utc(self.captured_at),
            "features": self.features,
            "market_snapshot": self.market_snapshot,
        }


@dataclass(frozen=True)
class CanonicalTradeRecord:
    trade_id: str
    external_trade_id: str | None
    strategy_name: str
    strategy_version: str
    exchange: str
    market_type: str
    mode: str
    pair: str
    timeframe: str
    side: str
    status: str
    opened_at: datetime
    closed_at: datetime | None
    entry_price: Decimal
    exit_price: Decimal | None
    amount: Decimal
    stake_amount: Decimal
    fee_amount: Decimal
    realized_pnl: Decimal | None
    realized_pnl_pct: Decimal | None
    stop_loss: Decimal
    take_profit: Decimal
    regime: str
    entry_reason: str
    exit_reason: str | None
    protection_context: dict[str, str]
    feature_snapshot: TradeFeatureSnapshot
    mfe_pct: Decimal | None = None
    mae_pct: Decimal | None = None

    @property
    def idempotency_key(self) -> str:
        return f"trade-journal:{self.mode}:{self.trade_id}:{self.status}"

    def as_payload(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "external_trade_id": self.external_trade_id,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "mode": self.mode,
            "pair": self.pair,
            "timeframe": self.timeframe,
            "side": self.side,
            "status": self.status,
            "opened_at": isoformat_utc(self.opened_at),
            "closed_at": None if self.closed_at is None else isoformat_utc(self.closed_at),
            "entry_price": str(self.entry_price),
            "exit_price": None if self.exit_price is None else str(self.exit_price),
            "amount": str(self.amount),
            "stake_amount": str(self.stake_amount),
            "fee_amount": str(self.fee_amount),
            "realized_pnl": None if self.realized_pnl is None else str(self.realized_pnl),
            "realized_pnl_pct": None
            if self.realized_pnl_pct is None
            else str(self.realized_pnl_pct),
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "regime": self.regime,
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
            "protection_context": self.protection_context,
            "feature_snapshot": self.feature_snapshot.as_payload(),
            "mfe_pct": None if self.mfe_pct is None else str(self.mfe_pct),
            "mae_pct": None if self.mae_pct is None else str(self.mae_pct),
        }


class TradeJournal:
    def __init__(self, outbox: SQLiteOutbox) -> None:
        self.outbox = outbox

    def record_trade(self, record: CanonicalTradeRecord) -> None:
        validate_trade_record(record)
        self.outbox.enqueue(
            EventEnvelope(
                event_type=f"trade.{record.status}",
                source="cryptoforge.trade_journal",
                severity="info",
                occurred_at=record.closed_at or record.opened_at,
                idempotency_key=record.idempotency_key,
                payload=record.as_payload(),
            )
        )


def validate_trade_record(record: CanonicalTradeRecord) -> None:
    if not record.trade_id:
        raise ValueError("trade_id is required")
    if record.exchange != "bybit":
        raise ValueError("exchange must be bybit")
    if record.market_type != "spot":
        raise ValueError("market_type must be spot")
    if record.mode not in {"dry_run", "live"}:
        raise ValueError("mode must be dry_run or live")
    if record.side != "long":
        raise ValueError("only spot long trades are supported")
    if record.status not in {"open", "closed", "cancelled", "error"}:
        raise ValueError("invalid trade status")
    if record.entry_price <= 0 or record.amount <= 0 or record.stake_amount <= 0:
        raise ValueError("entry_price, amount and stake_amount must be positive")
    if record.stop_loss <= 0 or record.take_profit <= 0:
        raise ValueError("stop_loss and take_profit must be positive")
    if record.stop_loss >= record.entry_price:
        raise ValueError("stop_loss must be below entry_price for spot long")
    if record.take_profit <= record.entry_price:
        raise ValueError("take_profit must be above entry_price for spot long")
    if record.closed_at is not None and record.closed_at < record.opened_at:
        raise ValueError("closed_at cannot be before opened_at")
    if record.status == "closed" and record.exit_price is None:
        raise ValueError("closed trades require exit_price")
    if record.status == "closed" and record.exit_reason is None:
        raise ValueError("closed trades require exit_reason")


def compute_mfe_mae_pct(
    *,
    entry_price: Decimal,
    opened_at_ms: int,
    closed_at_ms: int,
    candles: list[Candle],
) -> tuple[Decimal, Decimal]:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if closed_at_ms < opened_at_ms:
        raise ValueError("closed_at_ms cannot be before opened_at_ms")

    covered = [
        candle
        for candle in candles
        if candle.start_ms < closed_at_ms and candle.close_ms > opened_at_ms
    ]
    if not covered:
        raise ValueError("no candles overlap trade window")

    best_high = max(candle.high for candle in covered)
    worst_low = min(candle.low for candle in covered)
    mfe = (best_high - entry_price) / entry_price
    mae = (worst_low - entry_price) / entry_price
    return mfe, mae


def validate_against_local_trade_state(
    record: CanonicalTradeRecord,
    local_state: dict[str, Any],
) -> None:
    checks = {
        "pair": record.pair,
        "amount": str(record.amount),
        "entry_price": str(record.entry_price),
        "status": record.status,
    }
    for key, expected in checks.items():
        actual = local_state.get(key)
        if str(actual) != expected:
            raise ValueError(f"local trade state mismatch for {key}: {actual!r} != {expected!r}")


def isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
