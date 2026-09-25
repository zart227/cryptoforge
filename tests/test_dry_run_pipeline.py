from decimal import Decimal

from cryptoforge.dry_run_pipeline import (
    average_true_range,
    to_freqtrade_pair,
    validate_freqtrade_dry_run_config,
)
from cryptoforge.market_data import Candle


def test_validate_freqtrade_dry_run_config_rejects_live_settings(tmp_path) -> None:
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(
        """
        {
          "dry_run": false,
          "trading_mode": "futures",
          "margin_mode": "isolated",
          "exchange": {"name": "bybit", "key": "x", "secret": "y"},
          "leverage": 5
        }
        """,
        encoding="utf-8",
    )

    errors = validate_freqtrade_dry_run_config(unsafe)

    assert "dry_run must be true" in errors
    assert "trading_mode must be spot" in errors
    assert "margin_mode must be empty" in errors
    assert "freqtrade dry-run config must not contain exchange credentials" in errors
    assert "config must not contain leverage settings" in errors


def test_baseline_dry_run_config_is_safe() -> None:
    assert validate_freqtrade_dry_run_config("config/freqtrade.baseline-dry-run.json") == []


def test_to_freqtrade_pair_converts_bybit_symbol() -> None:
    assert to_freqtrade_pair("BTCUSDT") == "BTC/USDT"
    assert to_freqtrade_pair("ETH/USDT") == "ETH/USDT"


def test_average_true_range_uses_recent_completed_window() -> None:
    candles = [
        Candle(
            symbol="BTCUSDT",
            interval="5",
            start_ms=idx * 300_000,
            open=Decimal("100") + Decimal(idx),
            high=Decimal("102") + Decimal(idx),
            low=Decimal("99") + Decimal(idx),
            close=Decimal("101") + Decimal(idx),
            volume=Decimal("1"),
            turnover=Decimal("100"),
        )
        for idx in range(20)
    ]

    assert average_true_range(candles, lookback=14) == Decimal("3")
