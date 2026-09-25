from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from statistics import mean

from cryptoforge.market_data import Candle


class MarketRegime(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeConfig:
    min_candles: int = 50
    fast_ema_period: int = 12
    slow_ema_period: int = 36
    trend_slope_lookback: int = 6
    min_trend_separation_pct: Decimal = Decimal("0.004")
    min_trend_slope_pct: Decimal = Decimal("0.0015")
    high_volatility_atr_pct: Decimal = Decimal("0.025")
    low_volatility_atr_pct: Decimal = Decimal("0.004")
    range_max_trend_separation_pct: Decimal = Decimal("0.003")
    range_max_slope_pct: Decimal = Decimal("0.001")


@dataclass(frozen=True)
class RegimeClassification:
    regime: MarketRegime
    reason: str
    as_of_ms: int
    fast_ema: Decimal
    slow_ema: Decimal
    trend_separation_pct: Decimal
    trend_slope_pct: Decimal
    atr_pct: Decimal
    realized_volatility_pct: Decimal

    @property
    def trade_context_value(self) -> str:
        return self.regime.value


def classify_regime(
    candles: list[Candle] | tuple[Candle, ...],
    config: RegimeConfig | None = None,
) -> RegimeClassification:
    cfg = config or RegimeConfig()
    ordered = sorted(candles, key=lambda candle: candle.start_ms)

    if len(ordered) < cfg.min_candles:
        as_of_ms = ordered[-1].close_ms if ordered else 0
        return RegimeClassification(
            regime=MarketRegime.UNKNOWN,
            reason="insufficient candle history",
            as_of_ms=as_of_ms,
            fast_ema=Decimal("0"),
            slow_ema=Decimal("0"),
            trend_separation_pct=Decimal("0"),
            trend_slope_pct=Decimal("0"),
            atr_pct=Decimal("0"),
            realized_volatility_pct=Decimal("0"),
        )

    closes = [candle.close for candle in ordered]
    fast_series = ema_series(closes, cfg.fast_ema_period)
    slow_series = ema_series(closes, cfg.slow_ema_period)
    fast = fast_series[-1]
    slow = slow_series[-1]
    latest_close = closes[-1]
    trend_separation = safe_ratio(fast - slow, latest_close)

    slope_start_idx = max(0, len(slow_series) - 1 - cfg.trend_slope_lookback)
    trend_slope = safe_ratio(slow_series[-1] - slow_series[slope_start_idx], latest_close)
    atr = average_true_range_pct(ordered)
    realized_vol = realized_volatility_pct(ordered)

    if atr >= cfg.high_volatility_atr_pct:
        regime = MarketRegime.HIGH_VOLATILITY
        reason = "ATR exceeds high-volatility threshold"
    elif atr <= cfg.low_volatility_atr_pct:
        regime = MarketRegime.LOW_VOLATILITY
        reason = "ATR is below low-volatility threshold"
    elif (
        trend_separation >= cfg.min_trend_separation_pct
        and trend_slope >= cfg.min_trend_slope_pct
    ):
        regime = MarketRegime.TREND_UP
        reason = "fast EMA is above slow EMA with positive slow-EMA slope"
    elif (
        trend_separation <= -cfg.min_trend_separation_pct
        and trend_slope <= -cfg.min_trend_slope_pct
    ):
        regime = MarketRegime.TREND_DOWN
        reason = "fast EMA is below slow EMA with negative slow-EMA slope"
    elif (
        abs(trend_separation) <= cfg.range_max_trend_separation_pct
        and abs(trend_slope) <= cfg.range_max_slope_pct
    ):
        regime = MarketRegime.RANGE
        reason = "EMA separation and slope are small"
    else:
        regime = MarketRegime.RANGE
        reason = "no strong trend or volatility regime matched"

    return RegimeClassification(
        regime=regime,
        reason=reason,
        as_of_ms=ordered[-1].close_ms,
        fast_ema=fast,
        slow_ema=slow,
        trend_separation_pct=trend_separation,
        trend_slope_pct=trend_slope,
        atr_pct=atr,
        realized_volatility_pct=realized_vol,
    )


def ema_series(values: list[Decimal], period: int) -> list[Decimal]:
    if period <= 0:
        raise ValueError("EMA period must be positive")
    if not values:
        return []

    multiplier = Decimal("2") / Decimal(period + 1)
    series = [values[0]]
    for value in values[1:]:
        series.append((value - series[-1]) * multiplier + series[-1])
    return series


def average_true_range_pct(candles: list[Candle]) -> Decimal:
    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for candle in candles:
        if candle.close <= 0:
            previous_close = candle.close
            continue
        if previous_close is None:
            true_range = candle.high - candle.low
        else:
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range / candle.close)
        previous_close = candle.close

    if not true_ranges:
        return Decimal("0")
    return sum(true_ranges, Decimal("0")) / Decimal(len(true_ranges))


def realized_volatility_pct(candles: list[Candle]) -> Decimal:
    returns: list[Decimal] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return Decimal("0")

    avg = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = mean(float(value - avg) ** 2 for value in returns)
    return Decimal(str(variance**0.5))


def safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator
