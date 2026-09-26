from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class CryptoForgeLongShortResearchStrategy(IStrategy):
    """Research-only long/short strategy for paper, shadow and backtests."""

    timeframe = "5m"
    startup_candle_count = 120
    can_short = True

    minimal_roi = {
        "0": 0.03,
        "45": 0.018,
        "120": 0.008,
    }
    stoploss = -0.018

    process_only_new_candles = True
    use_exit_signal = True
    ignore_roi_if_entry_signal = False

    buy_rsi = 54
    short_rsi = 46
    sell_rsi = 44
    cover_rsi = 56
    overbought_rsi = 72
    oversold_rsi = 28
    min_volume_ratio = 1.05
    breakout_volume_ratio = 1.25
    min_atr_pct = 0.0015
    max_atr_pct = 0.04
    level_window = 48
    level_atr_buffer = 0.75

    @property
    def version(self) -> str:
        return "cryptoforge-long-short-research-v0.1.0"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = dataframe["close"].ewm(span=12, adjust=False).mean()
        dataframe["ema_slow"] = dataframe["close"].ewm(span=36, adjust=False).mean()
        dataframe["rsi"] = relative_strength_index(dataframe["close"], period=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20, min_periods=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean_20"]
        dataframe["atr_pct"] = average_true_range_pct(dataframe, period=14)
        dataframe["atr"] = dataframe["atr_pct"] * dataframe["close"]
        dataframe["support"] = dataframe["low"].rolling(self.level_window, min_periods=self.level_window).min().shift(1)
        dataframe["resistance"] = dataframe["high"].rolling(self.level_window, min_periods=self.level_window).max().shift(1)
        dataframe["near_support"] = dataframe["close"] <= (
            dataframe["support"] + dataframe["atr"] * self.level_atr_buffer
        )
        dataframe["near_resistance"] = dataframe["close"] >= (
            dataframe["resistance"] - dataframe["atr"] * self.level_atr_buffer
        )
        dataframe["support_bounce"] = (
            dataframe["near_support"]
            & (dataframe["close"] > dataframe["open"])
            & (dataframe["close"] > dataframe["close"].shift(1))
        )
        dataframe["resistance_reject"] = (
            dataframe["near_resistance"]
            & (dataframe["close"] < dataframe["open"])
            & (dataframe["close"] < dataframe["close"].shift(1))
        )
        dataframe["resistance_breakout"] = (
            (dataframe["close"] > dataframe["resistance"])
            & (dataframe["close"].shift(1) <= dataframe["resistance"].shift(1))
            & (dataframe["volume_ratio"] >= self.breakout_volume_ratio)
        )
        dataframe["support_breakdown"] = (
            (dataframe["close"] < dataframe["support"])
            & (dataframe["close"].shift(1) >= dataframe["support"].shift(1))
            & (dataframe["volume_ratio"] >= self.breakout_volume_ratio)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = None

        valid_market = (
            (dataframe["volume_ratio"] >= self.min_volume_ratio)
            & (dataframe["atr_pct"] >= self.min_atr_pct)
            & (dataframe["atr_pct"] <= self.max_atr_pct)
            & (dataframe["volume"] > 0)
        )
        long_condition = (
            valid_market
            & (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["rsi"] >= self.buy_rsi)
            & (dataframe["support_bounce"] | dataframe["resistance_breakout"])
        )
        short_condition = (
            valid_market
            & (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["rsi"] <= self.short_rsi)
            & (dataframe["resistance_reject"] | dataframe["support_breakdown"])
        )

        dataframe.loc[long_condition, ["enter_long", "enter_tag"]] = (1, "research_long_level_signal")
        dataframe.loc[short_condition, ["enter_short", "enter_tag"]] = (1, "research_short_level_signal")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        dataframe["exit_tag"] = None

        long_exit = (
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            | (dataframe["rsi"] <= self.sell_rsi)
            | (dataframe["rsi"] >= self.overbought_rsi)
            | dataframe["near_resistance"]
            | dataframe["support_breakdown"]
            | (dataframe["atr_pct"] > self.max_atr_pct)
        )
        short_exit = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            | (dataframe["rsi"] >= self.cover_rsi)
            | (dataframe["rsi"] <= self.oversold_rsi)
            | dataframe["near_support"]
            | dataframe["resistance_breakout"]
            | (dataframe["atr_pct"] > self.max_atr_pct)
        )

        dataframe.loc[long_exit, ["exit_long", "exit_tag"]] = (1, "research_long_exit")
        dataframe.loc[short_exit, ["exit_short", "exit_tag"]] = (1, "research_short_exit")
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
