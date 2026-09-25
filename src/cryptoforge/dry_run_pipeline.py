from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptoforge.market_data import BybitPublicClient, Candle
from cryptoforge.position_management import PositionProtectionPlanner, ProtectedEntry
from cryptoforge.regime import RegimeClassification, classify_regime
from cryptoforge.risk import PortfolioState
from cryptoforge.scanner import MarketScanner, ScannerConfig, ScoredCandidate


@dataclass(frozen=True)
class DryRunPipelineConfig:
    scanner: ScannerConfig = ScannerConfig(
        cheap_shortlist_size=12,
        expensive_shortlist_size=4,
        output_limit=3,
        candle_limit=120,
    )
    atr_lookback: int = 14
    timeframe: str = "5"


@dataclass(frozen=True)
class DryRunCandidatePlan:
    candidate: ScoredCandidate
    regime: RegimeClassification
    protected_entry: ProtectedEntry
    candles_used: int

    def as_summary(self) -> dict[str, Any]:
        position_size = self.protected_entry.risk_result.position_size
        return {
            "symbol": self.candidate.symbol,
            "regime": self.regime.regime.value,
            "risk_decision": self.protected_entry.risk_result.decision.value,
            "risk_reasons": list(self.protected_entry.risk_result.reasons),
            "candles_used": self.candles_used,
            "entry_price": str(self.protected_entry.plan.entry_price),
            "stop_loss": str(self.protected_entry.plan.stop_loss),
            "take_profit": str(self.protected_entry.plan.take_profit),
            "position_notional": None if position_size is None else str(position_size.notional),
            "position_qty": None if position_size is None else str(position_size.qty),
            "protection": self.protected_entry.plan.journal_context(),
        }


class DryRunPipeline:
    def __init__(
        self,
        client: BybitPublicClient,
        protection_planner: PositionProtectionPlanner,
        config: DryRunPipelineConfig | None = None,
    ) -> None:
        self.client = client
        self.protection_planner = protection_planner
        self.config = config or DryRunPipelineConfig()

    def build_plan(self, portfolio: PortfolioState) -> list[DryRunCandidatePlan]:
        scanner = MarketScanner(self.client, self.config.scanner)
        scan = scanner.scan()
        plans: list[DryRunCandidatePlan] = []

        for candidate in scan.selected:
            candles = self.client.get_klines(
                candidate.symbol,
                interval=self.config.timeframe,
                limit=max(self.config.scanner.candle_limit, 120),
            )
            if not candles:
                continue

            entry_price = candles[-1].close
            atr = average_true_range(candles, lookback=self.config.atr_lookback)
            regime = classify_regime(candles)
            protected_entry = self.protection_planner.evaluate_entry(
                pair=to_freqtrade_pair(candidate.symbol),
                entry_price=entry_price,
                atr=atr,
                portfolio=portfolio,
            )
            plans.append(
                DryRunCandidatePlan(
                    candidate=candidate,
                    regime=regime,
                    protected_entry=protected_entry,
                    candles_used=len(candles),
                )
            )

        return plans


def average_true_range(candles: list[Candle], lookback: int = 14) -> Decimal:
    if len(candles) < lookback + 1:
        raise ValueError("not enough candles to calculate ATR")

    ranges: list[Decimal] = []
    first_idx = len(candles) - lookback
    for full_idx in range(first_idx, len(candles)):
        candle = candles[full_idx]
        previous_close = candles[full_idx - 1].close if full_idx > 0 else candle.close
        ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return sum(ranges, Decimal("0")) / Decimal(len(ranges))


def to_freqtrade_pair(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}/USDT"
    raise ValueError(f"Cannot convert symbol to Freqtrade pair: {symbol}")


def validate_freqtrade_dry_run_config(path: str | Path) -> list[str]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    errors: list[str] = []

    if config.get("dry_run") is not True:
        errors.append("dry_run must be true")
    if config.get("trading_mode") != "spot":
        errors.append("trading_mode must be spot")
    if config.get("margin_mode") not in ("", None):
        errors.append("margin_mode must be empty")
    exchange = config.get("exchange", {})
    if exchange.get("name") != "bybit":
        errors.append("exchange must be bybit")
    if exchange.get("key") or exchange.get("secret"):
        errors.append("freqtrade dry-run config must not contain exchange credentials")
    if "leverage" in json.dumps(config).lower():
        errors.append("config must not contain leverage settings")

    return errors
