from pandas import DataFrame

from freqtrade.strategy import IStrategy


class CryptoForgeNoEntryStrategy(IStrategy):
    """Safety bootstrap strategy used only to verify dry-run runtime startup."""

    timeframe = "5m"
    startup_candle_count = 20
    can_short = False

    minimal_roi = {"0": 0.01}
    stoploss = -0.02

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = "bootstrap_no_entry"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe
