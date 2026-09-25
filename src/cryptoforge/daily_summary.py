from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptoforge.metrics import PerformanceMetrics
from cryptoforge.monitoring import MonitoringSummary


@dataclass(frozen=True)
class DailySummary:
    date: str
    mode: str
    metrics: PerformanceMetrics
    monitoring: MonitoringSummary
    open_positions: int
    notes: tuple[str, ...] = ()

    def render_text(self) -> str:
        lines = [
            f"CryptoForge daily summary - {self.date}",
            f"mode: {self.mode}",
            f"trades: {self.metrics.trade_count}",
            f"net_pnl: {self.metrics.net_pnl}",
            f"max_drawdown: {self.metrics.max_drawdown}",
            f"expectancy: {self.metrics.expectancy}",
            f"profit_factor: {self.metrics.profit_factor}",
            f"monitoring: {self.monitoring.status.value}",
            f"allow_new_entries: {self.monitoring.allow_new_entries}",
            f"open_positions: {self.open_positions}",
        ]
        if self.monitoring.no_new_entry_reasons:
            lines.append("no_new_entry_reasons:")
            lines.extend(f"- {reason}" for reason in self.monitoring.no_new_entry_reasons)
        if self.notes:
            lines.append("notes:")
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)


def empty_daily_metrics(scope: str = "daily") -> PerformanceMetrics:
    return PerformanceMetrics(
        scope=scope,
        trade_count=0,
        net_pnl=Decimal("0"),
        gross_profit=Decimal("0"),
        gross_loss=Decimal("0"),
        fees=Decimal("0"),
        win_rate=Decimal("0"),
        profit_factor=None,
        expectancy=Decimal("0"),
        average_win=Decimal("0"),
        average_loss=Decimal("0"),
        max_drawdown=Decimal("0"),
        sharpe=None,
        sortino=None,
    )
