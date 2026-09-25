from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class CryptoForgeBaselineStrategy(IStrategy):
    """Transparent control strategy for dry-run champion/challenger comparisons."""

    timeframe = "5m"
    startup_candle_count = 80
    can_short = False

    minimal_roi = {
        "0": 0.025,
        "60": 0.015,
        "180": 0.005,
    }
    stoploss = -0.02

    process_only_new_candles = True
    use_exit_signal = True
    ignore_roi_if_entry_signal = False

    buy_rsi = 55
    sell_rsi = 45
    min_volume_ratio = 1.05
    min_atr_pct = 0.0015
    max_atr_pct = 0.04

    @property
    def version(self) -> str:
        return "cryptoforge-baseline-v0.1.0"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = dataframe["close"].ewm(span=12, adjust=False).mean()
        dataframe["ema_slow"] = dataframe["close"].ewm(span=36, adjust=False).mean()
        dataframe["rsi"] = relative_strength_index(dataframe["close"], period=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20, min_periods=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean_20"]
        dataframe["atr_pct"] = average_true_range_pct(dataframe, period=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = None

        entry_condition = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_fast"])
            & (dataframe["rsi"] >= self.buy_rsi)
            & (dataframe["volume_ratio"] >= self.min_volume_ratio)
            & (dataframe["atr_pct"] >= self.min_atr_pct)
            & (dataframe["atr_pct"] <= self.max_atr_pct)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[entry_condition, ["enter_long", "enter_tag"]] = (
            1,
            "ema_rsi_volume_atr_baseline",
        )
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = None

        exit_condition = (
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            | (dataframe["rsi"] <= self.sell_rsi)
            | (dataframe["atr_pct"] > self.max_atr_pct)
        )
        dataframe.loc[exit_condition, ["exit_long", "exit_tag"]] = (
            1,
            "baseline_exit_signal",
        )
        return dataframe


def relative_strength_index(close, period: int = 14):  # type: ignore[no-untyped-def]
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def average_true_range_pct(dataframe: DataFrame, period: int = 14):  # type: ignore[no-untyped-def]
    previous_close = dataframe["close"].shift(1)
    true_range = DataFrame(
        {
            "high_low": dataframe["high"] - dataframe["low"],
            "high_close": (dataframe["high"] - previous_close).abs(),
            "low_close": (dataframe["low"] - previous_close).abs(),
        }
    ).max(axis=1)
    atr = true_range.rolling(period, min_periods=period).mean()
    return atr / dataframe["close"]
