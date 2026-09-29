from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from freqtrade.persistence import Trade

from cryptoforge.live_pilot import read_switch
from cryptoforge.risk import (
    HardRiskConfig,
    PortfolioState,
    RiskEngine,
    TradeRiskRequest,
)
from CryptoForgeBaselineStrategy import CryptoForgeBaselineStrategy


class CryptoForgeSmallBalancePilotStrategy(CryptoForgeBaselineStrategy):
    """Balance-bounded Spot pilot with an entry-time CryptoForge hard-risk gate."""

    minimal_roi = {"0": 0.015}
    stoploss = -0.005
    timeframe = "5m"
    startup_candle_count = 80
    can_short = False

    allocation_usdt = Decimal("10.40884583")
    max_order_notional_usdt = Decimal("5.02")
    max_daily_loss_pct = Decimal("0.02")
    max_open_positions = 1
    stop_distance_pct = Decimal("0.005")
    fee_pct_per_side = Decimal("0.001")

    def entry_pair_allowed(self, pair: str) -> bool:
        return pair == "XRP/USDT"

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        if side != "long" or not self.entry_pair_allowed(pair):
            return False
        if self.config.get("dry_run") is False:
            if not read_switch(Path("data/live-pilot/live-enabled")):
                return False
        if read_switch(Path("data/live-pilot/kill-switch")):
            return False
        if read_switch(Path("data/live-pilot/no-new-entry")):
            return False

        closed = Trade.get_trades_proxy(is_open=False)
        todays = [
            trade for trade in closed
            if trade.close_date and trade.close_date.date() == current_time.date()
        ]
        daily_realized = sum(
            (Decimal(str(trade.close_profit_abs or 0)) for trade in todays),
            Decimal("0"),
        )
        all_realized = sum(
            (Decimal(str(trade.close_profit_abs or 0)) for trade in closed),
            Decimal("0"),
        )
        equity = max(Decimal("0"), self.allocation_usdt + all_realized)
        peak_equity = max(
            [self.allocation_usdt]
            + [self.allocation_usdt + sum(
                (Decimal(str(t.close_profit_abs or 0)) for t in closed
                 if t.close_date and t.close_date <= point.close_date),
                Decimal("0"),
            ) for point in closed if point.close_date]
        )
        risk = RiskEngine(
            HardRiskConfig(
                virtual_capital=self.allocation_usdt,
                risk_per_trade_pct=Decimal("0.005"),
                max_simultaneous_positions=self.max_open_positions,
                daily_loss_limit_pct=self.max_daily_loss_pct,
                max_portfolio_drawdown_pct=Decimal("0.10"),
                taker_fee_pct=self.fee_pct_per_side,
                min_order_notional=Decimal("5"),
                max_position_notional_usdt=self.max_order_notional_usdt,
            )
        )
        result = risk.evaluate(
            TradeRiskRequest(
                pair=pair,
                entry_price=Decimal(str(rate)),
                stop_price=Decimal(str(rate)) * (Decimal("1") - self.stop_distance_pct),
                requested_notional=Decimal(str(amount)) * Decimal(str(rate)),
            ),
            PortfolioState(
                equity=equity,
                peak_equity=peak_equity,
                daily_realized_pnl=daily_realized,
                open_positions=len(Trade.get_open_trades()),
            ),
        )
        return result.approved
