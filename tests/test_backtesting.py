from pathlib import Path

import pytest

from cryptoforge.backtesting import (
    BacktestSpec,
    baseline_backtest_spec,
    find_obvious_future_leakage,
)


def test_baseline_backtest_spec_builds_bounded_commands() -> None:
    spec = baseline_backtest_spec()
    download = spec.download_command("freqtrade")
    backtest = spec.backtest_command("freqtrade")

    assert "--timerange" in download
    assert "20260923-20260925" in download
    assert "--no-parallel-download" in download
    assert "--fee" in backtest
    assert "0.001" in backtest
    assert "--export" in backtest
    assert "none" in backtest
    assert "--cache" in backtest
    assert spec.low_priority_shell_command(backtest).startswith("nice -n 10 ionice -c2 -n7")


def test_backtest_spec_rejects_unbounded_or_unlimited_output() -> None:
    with pytest.raises(ValueError, match="bounded timerange"):
        BacktestSpec(
            config_path="c",
            userdir="u",
            datadir="d",
            strategy_path="s",
            strategy="S",
            pairs=("BTC/USDT",),
            timeframe="5m",
            timerange="",
            fee="0.001",
            max_open_trades=1,
            stake_amount="10",
            dry_run_wallet="1000",
        ).validate()

    spec = baseline_backtest_spec()
    with pytest.raises(ValueError, match="unlimited exports"):
        BacktestSpec(**{**spec.__dict__, "export": "trades"}).validate()


def test_find_obvious_future_leakage_accepts_baseline_strategy() -> None:
    assert (
        find_obvious_future_leakage(
            "user_data/strategies/CryptoForgeBaselineStrategy.py"
        )
        == []
    )


def test_find_obvious_future_leakage_flags_common_patterns(tmp_path) -> None:
    strategy = tmp_path / "LeakyStrategy.py"
    strategy.write_text(
        """
def populate_indicators(dataframe, metadata):
    dataframe['future'] = dataframe['close'].shift(-1)
    dataframe['centered'] = dataframe['close'].rolling(5, center=True).mean()
    dataframe['last'] = dataframe.iloc[-1]
    return dataframe
        """,
        encoding="utf-8",
    )

    findings = find_obvious_future_leakage(Path(strategy))

    assert "negative shift() can introduce future leakage" in findings
    assert "center=True rolling window can introduce future leakage" in findings
    assert "direct .iloc[-1] usage can hide full-dataframe leakage" in findings
