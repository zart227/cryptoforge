from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation
from math import sqrt
from typing import Any, Callable

from cryptoforge.outbox import EventEnvelope, SQLiteOutbox
from cryptoforge.trade_journal import CanonicalTradeRecord


@dataclass(frozen=True)
class PerformanceMetrics:
    scope: str
    trade_count: int
    net_pnl: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    fees: Decimal
    win_rate: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal
    average_win: Decimal
    average_loss: Decimal
    max_drawdown: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None

    def as_payload(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "trade_count": self.trade_count,
            "net_pnl": str(self.net_pnl),
            "gross_profit": str(self.gross_profit),
            "gross_loss": str(self.gross_loss),
            "fees": str(self.fees),
            "win_rate": str(self.win_rate),
            "profit_factor": None if self.profit_factor is None else str(self.profit_factor),
            "expectancy": str(self.expectancy),
            "average_win": str(self.average_win),
            "average_loss": str(self.average_loss),
            "max_drawdown": str(self.max_drawdown),
            "sharpe": None if self.sharpe is None else str(self.sharpe),
            "sortino": None if self.sortino is None else str(self.sortino),
        }


def compute_metrics(
    trades: list[CanonicalTradeRecord],
    *,
    scope: str = "all",
) -> PerformanceMetrics:
    closed = [trade for trade in trades if trade.status == "closed" and trade.realized_pnl is not None]
    pnls = [trade.realized_pnl or Decimal("0") for trade in closed]
    returns = [trade.realized_pnl_pct or Decimal("0") for trade in closed]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]

    trade_count = len(closed)
    net_pnl = sum(pnls, Decimal("0"))
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    fees = sum((trade.fee_amount for trade in closed), Decimal("0"))
    win_rate = safe_decimal_ratio(Decimal(len(wins)), Decimal(trade_count))
    profit_factor = None if gross_loss == 0 else gross_profit / abs(gross_loss)
    expectancy = safe_decimal_ratio(net_pnl, Decimal(trade_count))
    average_win = safe_decimal_ratio(gross_profit, Decimal(len(wins)))
    average_loss = safe_decimal_ratio(gross_loss, Decimal(len(losses)))
    max_drawdown = compute_max_drawdown(pnls)
    sharpe = ratio_from_returns(returns, downside_only=False)
    sortino = ratio_from_returns(returns, downside_only=True)

    return PerformanceMetrics(
        scope=scope,
        trade_count=trade_count,
        net_pnl=net_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        fees=fees,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        average_win=average_win,
        average_loss=average_loss,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        sortino=sortino,
    )


def daily_metrics(trades: list[CanonicalTradeRecord]) -> dict[date, PerformanceMetrics]:
    return grouped_metrics(
        trades,
        lambda trade: (trade.closed_at or trade.opened_at).date(),
        scope_prefix="daily",
    )


def strategy_version_metrics(trades: list[CanonicalTradeRecord]) -> dict[str, PerformanceMetrics]:
    return grouped_metrics(
        trades,
        lambda trade: trade.strategy_version,
        scope_prefix="strategy_version",
    )


def regime_metrics(trades: list[CanonicalTradeRecord]) -> dict[str, PerformanceMetrics]:
    return grouped_metrics(
        trades,
        lambda trade: trade.regime,
        scope_prefix="regime",
    )


def grouped_metrics(
    trades: list[CanonicalTradeRecord],
    key_fn: Callable[[CanonicalTradeRecord], Any],
    *,
    scope_prefix: str,
) -> dict[Any, PerformanceMetrics]:
    groups: dict[Any, list[CanonicalTradeRecord]] = defaultdict(list)
    for trade in trades:
        groups[key_fn(trade)].append(trade)
    return {
        key: compute_metrics(group, scope=f"{scope_prefix}:{key}")
        for key, group in groups.items()
    }


class MetricsPublisher:
    def __init__(self, outbox: SQLiteOutbox) -> None:
        self.outbox = outbox

    def publish(self, metrics: PerformanceMetrics, *, idempotency_key: str) -> None:
        self.outbox.enqueue(
            EventEnvelope(
                event_type="metrics.summary",
                source="cryptoforge.metrics",
                severity="info",
                idempotency_key=idempotency_key,
                payload=metrics.as_payload(),
            )
        )


def compute_max_drawdown(pnls: list[Decimal]) -> Decimal:
    equity = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def ratio_from_returns(
    returns: list[Decimal],
    *,
    downside_only: bool,
) -> Decimal | None:
    if len(returns) < 2:
        return None

    avg = sum(returns, Decimal("0")) / Decimal(len(returns))
    sample = [item for item in returns if not downside_only or item < 0]
    if len(sample) < 2:
        return None

    denominator_values = [(float(item - avg) ** 2) for item in sample]
    variance = sum(denominator_values) / (len(sample) - 1)
    if variance == 0:
        return None
    return Decimal(str(float(avg) / sqrt(variance)))


def safe_decimal_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    try:
        if denominator == 0:
            return Decimal("0")
        return numerator / denominator
    except (DivisionByZero, InvalidOperation):
        return Decimal("0")
