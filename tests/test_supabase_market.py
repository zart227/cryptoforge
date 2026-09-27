from decimal import Decimal

from cryptoforge.market_data import Candle, Ticker24h
from cryptoforge.supabase_market import candle_record, ticker_record


def test_candle_record_converts_bybit_candle_to_supabase_payload() -> None:
    candle = Candle(
        symbol="ETHUSDT",
        interval="5",
        start_ms=1_800_000_000_000,
        open=Decimal("100.1"),
        high=Decimal("101.2"),
        low=Decimal("99.9"),
        close=Decimal("100.8"),
        volume=Decimal("12.34"),
        turnover=Decimal("1234.56"),
    )

    record = candle_record(candle)

    assert record["exchange"] == "bybit"
    assert record["market_type"] == "spot"
    assert record["symbol"] == "ETHUSDT"
    assert record["pair"] == "ETH/USDT"
    assert record["timeframe"] == "5m"
    assert record["open"] == "100.1"
    assert record["volume"] == "12.34"
    assert record["open_time"].endswith("+00:00")


def test_ticker_record_converts_optional_decimals() -> None:
    ticker = Ticker24h(
        symbol="NEARUSDT",
        last_price=Decimal("4.123"),
        high_price_24h=Decimal("4.5"),
        low_price_24h=Decimal("3.9"),
        turnover_24h=Decimal("1000000"),
        volume_24h=Decimal("250000"),
        bid1_price=None,
        ask1_price=Decimal("4.124"),
    )

    record = ticker_record(ticker)

    assert record["pair"] == "NEAR/USDT"
    assert record["last_price"] == "4.123"
    assert record["bid_price"] is None
    assert record["ask_price"] == "4.124"
