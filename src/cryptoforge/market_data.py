from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BYBIT_MAINNET_BASE_URL = "https://api.bybit.com"
SPOT_CATEGORY = "spot"
PRIMARY_TIMEFRAME = "5"
INFORMATIVE_TIMEFRAMES = ("15", "60")
SUPPORTED_TIMEFRAMES = (PRIMARY_TIMEFRAME, *INFORMATIVE_TIMEFRAMES)


class MarketDataError(RuntimeError):
    """Base error for recoverable market-data failures."""


class MarketDataRateLimited(MarketDataError):
    """Raised when Bybit returns an HTTP or logical rate-limit response."""


class MarketDataTimeout(MarketDataError):
    """Raised when the market-data request times out or cannot connect."""


@dataclass(frozen=True)
class Instrument:
    symbol: str
    base_coin: str
    quote_coin: str
    status: str
    min_order_qty: Decimal | None = None
    tick_size: Decimal | None = None

    @property
    def is_trading_usdt_spot(self) -> bool:
        return self.quote_coin == "USDT" and self.status == "Trading"


@dataclass(frozen=True)
class Ticker24h:
    symbol: str
    last_price: Decimal
    high_price_24h: Decimal | None
    low_price_24h: Decimal | None
    turnover_24h: Decimal | None
    volume_24h: Decimal | None


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    start_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal

    @property
    def close_ms(self) -> int:
        return self.start_ms + interval_to_milliseconds(self.interval)


@dataclass(frozen=True)
class Freshness:
    is_fresh: bool
    age_ms: int
    max_age_ms: int
    reason: str


@dataclass(frozen=True)
class MarketDataSnapshot:
    symbol: str
    ticker: Ticker24h
    candles: tuple[Candle, ...]
    freshness: Freshness
    allow_new_entries: bool


class BybitPublicClient:
    def __init__(self, base_url: str = BYBIT_MAINNET_BASE_URL, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_spot_instruments(self) -> list[Instrument]:
        payload = self._get_json("/v5/market/instruments-info", {"category": SPOT_CATEGORY})
        return [parse_instrument(item) for item in payload["result"]["list"]]

    def get_usdt_spot_instruments(self) -> list[Instrument]:
        return [item for item in self.get_spot_instruments() if item.is_trading_usdt_spot]

    def get_tickers(self, symbol: str | None = None) -> list[Ticker24h]:
        params = {"category": SPOT_CATEGORY}
        if symbol:
            params["symbol"] = symbol
        payload = self._get_json("/v5/market/tickers", params)
        return [parse_ticker(item) for item in payload["result"]["list"]]

    def get_klines(self, symbol: str, interval: str = PRIMARY_TIMEFRAME, limit: int = 200) -> list[Candle]:
        if interval not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe {interval!r}; expected one of {SUPPORTED_TIMEFRAMES}")
        if not 1 <= limit <= 1000:
            raise ValueError("Bybit kline limit must be between 1 and 1000")
        payload = self._get_json(
            "/v5/market/kline",
            {
                "category": SPOT_CATEGORY,
                "symbol": symbol,
                "interval": interval,
                "limit": str(limit),
            },
        )
        candles = [parse_candle(symbol, interval, row) for row in payload["result"]["list"]]
        return sorted(candles, key=lambda candle: candle.start_ms)

    def get_snapshot(
        self,
        symbol: str,
        interval: str = PRIMARY_TIMEFRAME,
        limit: int = 200,
        now_ms: int | None = None,
    ) -> MarketDataSnapshot:
        tickers = self.get_tickers(symbol)
        if not tickers:
            raise MarketDataError(f"No ticker returned for {symbol}")
        candles = tuple(self.get_klines(symbol, interval=interval, limit=limit))
        freshness = candle_freshness(candles, interval=interval, now_ms=now_ms)
        return MarketDataSnapshot(
            symbol=symbol,
            ticker=tickers[0],
            candles=candles,
            freshness=freshness,
            allow_new_entries=freshness.is_fresh,
        )

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "CryptoForge/0.1 public-market-data"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code in {403, 429}:
                raise MarketDataRateLimited(f"Bybit request was rate-limited: HTTP {exc.code}") from exc
            raise MarketDataError(f"Bybit HTTP error {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise MarketDataTimeout(f"Bybit request failed or timed out: {exc}") from exc

        payload = json.loads(raw)
        ret_code = payload.get("retCode")
        if ret_code != 0:
            message = payload.get("retMsg", "unknown Bybit error")
            if ret_code in {10006, 10429} or "rate" in str(message).lower():
                raise MarketDataRateLimited(f"Bybit rate-limit response {ret_code}: {message}")
            raise MarketDataError(f"Bybit response {ret_code}: {message}")
        return payload


def parse_instrument(item: dict[str, Any]) -> Instrument:
    lot_filter = item.get("lotSizeFilter", {})
    price_filter = item.get("priceFilter", {})
    return Instrument(
        symbol=str(item["symbol"]),
        base_coin=str(item["baseCoin"]),
        quote_coin=str(item["quoteCoin"]),
        status=str(item["status"]),
        min_order_qty=parse_optional_decimal(lot_filter.get("basePrecision") or lot_filter.get("minOrderQty")),
        tick_size=parse_optional_decimal(price_filter.get("tickSize")),
    )


def parse_ticker(item: dict[str, Any]) -> Ticker24h:
    return Ticker24h(
        symbol=str(item["symbol"]),
        last_price=parse_decimal(item["lastPrice"]),
        high_price_24h=parse_optional_decimal(item.get("highPrice24h")),
        low_price_24h=parse_optional_decimal(item.get("lowPrice24h")),
        turnover_24h=parse_optional_decimal(item.get("turnover24h")),
        volume_24h=parse_optional_decimal(item.get("volume24h")),
    )


def parse_candle(symbol: str, interval: str, row: list[str]) -> Candle:
    if len(row) < 7:
        raise MarketDataError(f"Malformed Bybit kline row for {symbol}: expected 7 fields")
    return Candle(
        symbol=symbol,
        interval=interval,
        start_ms=int(row[0]),
        open=parse_decimal(row[1]),
        high=parse_decimal(row[2]),
        low=parse_decimal(row[3]),
        close=parse_decimal(row[4]),
        volume=parse_decimal(row[5]),
        turnover=parse_decimal(row[6]),
    )


def candle_freshness(
    candles: tuple[Candle, ...] | list[Candle],
    interval: str = PRIMARY_TIMEFRAME,
    now_ms: int | None = None,
    max_lag_intervals: int = 2,
) -> Freshness:
    if not candles:
        return Freshness(False, age_ms=-1, max_age_ms=0, reason="missing candles")

    latest = max(candles, key=lambda candle: candle.start_ms)
    now = int(time.time() * 1000) if now_ms is None else now_ms
    age_ms = max(0, now - latest.close_ms)
    max_age_ms = interval_to_milliseconds(interval) * max_lag_intervals
    if age_ms <= max_age_ms:
        return Freshness(True, age_ms=age_ms, max_age_ms=max_age_ms, reason="fresh")
    return Freshness(False, age_ms=age_ms, max_age_ms=max_age_ms, reason="latest candle is stale")


def interval_to_milliseconds(interval: str) -> int:
    if interval == "D":
        return 24 * 60 * 60 * 1000
    if interval == "W":
        return 7 * 24 * 60 * 60 * 1000
    if interval == "M":
        return 31 * 24 * 60 * 60 * 1000
    return int(interval) * 60 * 1000


def parse_optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return parse_decimal(value)


def parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataError(f"Invalid decimal value from Bybit: {value!r}") from exc
