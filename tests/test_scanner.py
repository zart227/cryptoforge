from decimal import Decimal

from cryptoforge.market_data import Candle, Instrument, Ticker24h
from cryptoforge.scanner import (
    MarketScanner,
    ScannerConfig,
    cheap_filter,
    score_candidate,
)


def instrument(symbol: str, base: str, quote: str = "USDT") -> Instrument:
    return Instrument(
        symbol=symbol,
        base_coin=base,
        quote_coin=quote,
        status="Trading",
        min_order_qty=Decimal("0.001"),
    )


def ticker(
    symbol: str,
    turnover: str = "1000000",
    bid: str = "99",
    ask: str = "101",
) -> Ticker24h:
    return Ticker24h(
        symbol=symbol,
        last_price=Decimal("100"),
        high_price_24h=Decimal("110"),
        low_price_24h=Decimal("95"),
        turnover_24h=Decimal(turnover),
        volume_24h=Decimal("10000"),
        bid1_price=Decimal(bid),
        ask1_price=Decimal(ask),
    )


def candles(symbol: str, count: int = 80) -> list[Candle]:
    result: list[Candle] = []
    price = Decimal("100")
    for idx in range(count):
        price += Decimal("0.1")
        result.append(
            Candle(
                symbol=symbol,
                interval="5",
                start_ms=idx * 300_000,
                open=price - Decimal("0.2"),
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                volume=Decimal("1000") + Decimal(idx),
                turnover=price * Decimal("1000"),
            )
        )
    return result


def test_cheap_filter_rejects_unsuitable_pairs() -> None:
    config = ScannerConfig(min_turnover_24h_usdt=Decimal("500000"))
    instruments = [
        instrument("BTCUSDT", "BTC"),
        instrument("USDCUSDT", "USDC"),
        instrument("ABC3LUSDT", "ABC3L"),
        instrument("THINUSDT", "THIN"),
        instrument("WIDEUSDT", "WIDE"),
    ]
    tickers = {
        "BTCUSDT": ticker("BTCUSDT", bid="99.9", ask="100.1"),
        "USDCUSDT": ticker("USDCUSDT", bid="99.9", ask="100.1"),
        "ABC3LUSDT": ticker("ABC3LUSDT", bid="99.9", ask="100.1"),
        "THINUSDT": ticker("THINUSDT", turnover="10", bid="99.9", ask="100.1"),
        "WIDEUSDT": ticker("WIDEUSDT", bid="90", ask="110"),
    }

    candidates, rejected = cheap_filter(instruments, tickers, config)

    assert [candidate.instrument.symbol for candidate in candidates] == ["BTCUSDT"]
    rejected_by_symbol = {item.symbol: item.reasons for item in rejected}
    assert "stablecoin-like base asset" in rejected_by_symbol["USDCUSDT"]
    assert "leveraged/special token" in rejected_by_symbol["ABC3LUSDT"]
    assert "24h turnover below threshold" in rejected_by_symbol["THINUSDT"]
    assert "spread above threshold" in rejected_by_symbol["WIDEUSDT"]


def test_score_candidate_requires_history_and_uses_balanced_signals() -> None:
    config = ScannerConfig(min_candle_count=60)
    candidates, _ = cheap_filter(
        [instrument("BTCUSDT", "BTC")],
        {"BTCUSDT": ticker("BTCUSDT", bid="99.9", ask="100.1")},
        config,
    )

    assert score_candidate(candidates[0], candles("BTCUSDT", count=10), config) is None

    scored = score_candidate(candidates[0], candles("BTCUSDT", count=80), config)

    assert scored is not None
    assert scored.symbol == "BTCUSDT"
    assert scored.score > 0
    assert "score balances liquidity, volatility and momentum" in scored.reasons


def test_market_scanner_caps_expensive_analysis() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.kline_calls: list[str] = []

        def get_usdt_spot_instruments(self):  # type: ignore[no-untyped-def]
            return [
                instrument("AAAUSDT", "AAA"),
                instrument("BBBUSDT", "BBB"),
                instrument("CCCUSDT", "CCC"),
            ]

        def get_tickers(self):  # type: ignore[no-untyped-def]
            return [
                ticker("AAAUSDT", turnover="3000000", bid="99.9", ask="100.1"),
                ticker("BBBUSDT", turnover="2000000", bid="99.9", ask="100.1"),
                ticker("CCCUSDT", turnover="1000000", bid="99.9", ask="100.1"),
            ]

        def get_klines(self, symbol, interval, limit):  # type: ignore[no-untyped-def]
            self.kline_calls.append(symbol)
            return candles(symbol, count=80)

    client = FakeClient()
    scanner = MarketScanner(
        client,  # type: ignore[arg-type]
        ScannerConfig(expensive_shortlist_size=2, output_limit=1),
    )

    result = scanner.scan()

    assert client.kline_calls == ["AAAUSDT", "BBBUSDT"]
    assert len(result.selected) == 1
