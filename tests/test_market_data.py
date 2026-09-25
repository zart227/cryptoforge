from decimal import Decimal

import pytest

from cryptoforge.market_data import (
    BybitPublicClient,
    Candle,
    MarketDataError,
    PRIMARY_TIMEFRAME,
    candle_freshness,
    parse_candle,
    parse_instrument,
    parse_ticker,
)


def test_parse_spot_usdt_instrument() -> None:
    instrument = parse_instrument(
        {
            "symbol": "BTCUSDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "status": "Trading",
            "lotSizeFilter": {"basePrecision": "0.000001"},
            "priceFilter": {"tickSize": "0.01"},
        }
    )

    assert instrument.symbol == "BTCUSDT"
    assert instrument.is_trading_usdt_spot
    assert instrument.min_order_qty == Decimal("0.000001")
    assert instrument.tick_size == Decimal("0.01")


def test_parse_ticker_preserves_decimal_precision() -> None:
    ticker = parse_ticker(
        {
            "symbol": "BTCUSDT",
            "lastPrice": "64250.12",
            "highPrice24h": "65000.00",
            "lowPrice24h": "63000.50",
            "turnover24h": "123456789.123",
            "volume24h": "987.654321",
        }
    )

    assert ticker.last_price == Decimal("64250.12")
    assert ticker.turnover_24h == Decimal("123456789.123")
    assert ticker.volume_24h == Decimal("987.654321")


def test_parse_candle_rejects_malformed_rows() -> None:
    with pytest.raises(MarketDataError):
        parse_candle("BTCUSDT", PRIMARY_TIMEFRAME, ["1", "2"])


def test_candle_freshness_accepts_recent_closed_candle() -> None:
    candle = Candle(
        symbol="BTCUSDT",
        interval="5",
        start_ms=1_000_000,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("10"),
        turnover=Decimal("15"),
    )
    now_ms = candle.close_ms + 60_000

    freshness = candle_freshness([candle], interval="5", now_ms=now_ms)

    assert freshness.is_fresh
    assert freshness.reason == "fresh"


def test_candle_freshness_rejects_missing_and_stale_data() -> None:
    missing = candle_freshness([], interval="5", now_ms=10_000)
    assert not missing.is_fresh
    assert missing.reason == "missing candles"

    candle = Candle(
        symbol="BTCUSDT",
        interval="5",
        start_ms=1_000_000,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("10"),
        turnover=Decimal("15"),
    )
    stale = candle_freshness([candle], interval="5", now_ms=candle.close_ms + 11 * 60_000)
    assert not stale.is_fresh
    assert stale.reason == "latest candle is stale"


def test_client_sorts_reverse_bybit_klines() -> None:
    class FakeClient(BybitPublicClient):
        def _get_json(self, path, params):  # type: ignore[no-untyped-def]
            assert path == "/v5/market/kline"
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        ["2000", "2", "3", "1", "2.5", "10", "25"],
                        ["1000", "1", "2", "0.5", "1.5", "8", "12"],
                    ]
                },
            }

    candles = FakeClient().get_klines("BTCUSDT", limit=2)

    assert [candle.start_ms for candle in candles] == [1000, 2000]


@pytest.mark.integration
def test_bybit_public_market_data_live() -> None:
    client = BybitPublicClient(timeout=15)

    instruments = client.get_usdt_spot_instruments()
    symbols = {item.symbol for item in instruments}
    assert "BTCUSDT" in symbols

    snapshot = client.get_snapshot("BTCUSDT", limit=5)
    assert snapshot.ticker.symbol == "BTCUSDT"
    assert len(snapshot.candles) > 0
    assert snapshot.candles[-1].interval == PRIMARY_TIMEFRAME
