from decimal import Decimal

from cryptoforge.market_data import Candle
from cryptoforge.regime import MarketRegime, RegimeConfig, classify_regime


def candles_from_prices(
    prices: list[Decimal],
    *,
    wiggle: Decimal = Decimal("0.5"),
) -> list[Candle]:
    result: list[Candle] = []
    for idx, price in enumerate(prices):
        result.append(
            Candle(
                symbol="BTCUSDT",
                interval="5",
                start_ms=idx * 300_000,
                open=price,
                high=price + wiggle,
                low=max(Decimal("0.01"), price - wiggle),
                close=price,
                volume=Decimal("1000"),
                turnover=price * Decimal("1000"),
            )
        )
    return result


def test_regime_classification_is_deterministic() -> None:
    prices = [Decimal("100") + Decimal(idx) * Decimal("0.2") for idx in range(80)]
    candles = candles_from_prices(prices)

    first = classify_regime(candles)
    second = classify_regime(list(reversed(candles)))

    assert first == second
    assert first.regime == MarketRegime.TREND_UP


def test_regime_detects_downtrend() -> None:
    prices = [Decimal("120") - Decimal(idx) * Decimal("0.2") for idx in range(80)]

    result = classify_regime(candles_from_prices(prices))

    assert result.regime == MarketRegime.TREND_DOWN
    assert result.trade_context_value == "TREND_DOWN"


def test_regime_detects_low_and_high_volatility_before_trend() -> None:
    low_vol_prices = [Decimal("100") for _ in range(80)]
    low_vol = classify_regime(
        candles_from_prices(low_vol_prices, wiggle=Decimal("0.05"))
    )
    assert low_vol.regime == MarketRegime.LOW_VOLATILITY

    high_vol_prices = [
        Decimal("100") + (Decimal("5") if idx % 2 == 0 else Decimal("-5"))
        for idx in range(80)
    ]
    high_vol = classify_regime(
        candles_from_prices(high_vol_prices, wiggle=Decimal("3"))
    )
    assert high_vol.regime == MarketRegime.HIGH_VOLATILITY


def test_regime_uses_only_supplied_candles_no_future_leakage() -> None:
    cfg = RegimeConfig(high_volatility_atr_pct=Decimal("0.10"))
    flat_then_future_pump = [Decimal("100") for _ in range(80)] + [
        Decimal("140") + Decimal(idx) for idx in range(20)
    ]
    without_future = classify_regime(
        candles_from_prices(flat_then_future_pump[:80], wiggle=Decimal("0.05")),
        cfg,
    )
    with_future = classify_regime(
        candles_from_prices(flat_then_future_pump, wiggle=Decimal("0.05")),
        cfg,
    )

    assert without_future.as_of_ms < with_future.as_of_ms
    assert without_future.regime == MarketRegime.LOW_VOLATILITY
    assert with_future.regime != without_future.regime


def test_regime_reports_unknown_for_insufficient_history() -> None:
    result = classify_regime(candles_from_prices([Decimal("100")] * 10))

    assert result.regime == MarketRegime.UNKNOWN
    assert result.reason == "insufficient candle history"
