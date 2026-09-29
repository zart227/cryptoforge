from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import json
import os
from typing import Any
from urllib import error, parse, request

from cryptoforge.market_data import Candle, Ticker24h, interval_to_milliseconds


JsonObject = dict[str, Any]


class SupabaseMarketError(RuntimeError):
    """Raised when Supabase market-data persistence fails."""


@dataclass(frozen=True)
class SupabaseRestClient:
    supabase_url: str
    service_role_key: str
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls, *, timeout_seconds: float = 15.0) -> "SupabaseRestClient":
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or os.environ.get("SUPABASE_SECRET_KEY", "")
        if not url:
            raise ValueError("SUPABASE_URL is required")
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY is required")
        return cls(url, key, timeout_seconds=timeout_seconds)

    def upsert(
        self,
        table: str,
        records: list[JsonObject],
        *,
        on_conflict: str,
        resolution: str = "merge-duplicates",
    ) -> None:
        if not records:
            return
        query = parse.urlencode({"on_conflict": on_conflict})
        url = f"{self.supabase_url.rstrip('/')}/rest/v1/{table}?{query}"
        payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
        headers = {
            "apikey": self.service_role_key,
            "authorization": f"Bearer {self.service_role_key}",
            "content-type": "application/json",
            "prefer": f"resolution={resolution}",
        }
        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status not in {200, 201, 204}:
                    raise SupabaseMarketError(f"Supabase returned HTTP {response.status}")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise SupabaseMarketError(f"Supabase HTTP {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise SupabaseMarketError(f"Supabase request failed: {exc}") from exc

    def insert(self, table: str, records: list[JsonObject]) -> None:
        if not records:
            return
        url = f"{self.supabase_url.rstrip('/')}/rest/v1/{table}"
        payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
        headers = {
            "apikey": self.service_role_key,
            "authorization": f"Bearer {self.service_role_key}",
            "content-type": "application/json",
        }
        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status not in {200, 201, 204}:
                    raise SupabaseMarketError(f"Supabase returned HTTP {response.status}")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise SupabaseMarketError(f"Supabase HTTP {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise SupabaseMarketError(f"Supabase request failed: {exc}") from exc


@dataclass(frozen=True)
class SupabaseMarketWriter:
    client: SupabaseRestClient

    def write_candles(self, candles: list[Candle], *, market_type: str = "spot") -> None:
        records = [candle_record(candle, market_type=market_type) for candle in candles]
        self.client.upsert(
            "market_candles",
            records,
            on_conflict="exchange,market_type,symbol,timeframe,open_time",
        )

    def write_tickers(self, tickers: list[Ticker24h], *, market_type: str = "spot") -> None:
        records = [ticker_record(ticker, market_type=market_type) for ticker in tickers]
        self.client.upsert(
            "market_tickers",
            records,
            on_conflict="exchange,market_type,symbol",
        )

    def write_bot_health(self, component: str, status: str, message: str, payload: JsonObject) -> None:
        self.client.upsert(
            "bot_health",
            [
                {
                    "component": component,
                    "status": status,
                    "message": message,
                    "payload": payload,
                    "observed_at": datetime.now(UTC).isoformat(),
                }
            ],
            on_conflict="component",
        )

    def write_selected_universe(
        self,
        *,
        selection_name: str,
        pairs: list[str],
        scanner_config: JsonObject,
        selected: list[JsonObject],
        rejected_count: int,
    ) -> None:
        self.client.insert(
            "selected_universe",
            [
                {
                    "exchange": "bybit",
                    "market_type": "spot",
                    "selection_name": selection_name,
                    "selected_at": datetime.now(UTC).isoformat(),
                    "pairs": pairs,
                    "scanner_config": scanner_config,
                    "selected": selected,
                    "rejected_count": rejected_count,
                    "is_active": True,
                }
            ],
        )


def candle_record(candle: Candle, *, market_type: str = "spot") -> JsonObject:
    open_time = datetime.fromtimestamp(candle.start_ms / 1000, tz=UTC)
    close_time = datetime.fromtimestamp(
        (candle.start_ms + interval_to_milliseconds(candle.interval)) / 1000,
        tz=UTC,
    )
    return {
        "exchange": "bybit",
        "market_type": market_type,
        "symbol": candle.symbol,
        "pair": bybit_symbol_to_pair(candle.symbol),
        "timeframe": f"{candle.interval}m" if candle.interval.isdigit() else candle.interval,
        "open_time": open_time.isoformat(),
        "close_time": close_time.isoformat(),
        "open": decimal_text(candle.open),
        "high": decimal_text(candle.high),
        "low": decimal_text(candle.low),
        "close": decimal_text(candle.close),
        "volume": decimal_text(candle.volume),
        "turnover": decimal_text(candle.turnover),
        "source": "bybit_public_api",
        "ingested_at": datetime.now(UTC).isoformat(),
    }


def ticker_record(ticker: Ticker24h, *, market_type: str = "spot") -> JsonObject:
    return {
        "exchange": "bybit",
        "market_type": market_type,
        "symbol": ticker.symbol,
        "pair": bybit_symbol_to_pair(ticker.symbol),
        "last_price": decimal_text(ticker.last_price),
        "bid_price": optional_decimal_text(ticker.bid1_price),
        "ask_price": optional_decimal_text(ticker.ask1_price),
        "high_price_24h": optional_decimal_text(ticker.high_price_24h),
        "low_price_24h": optional_decimal_text(ticker.low_price_24h),
        "turnover_24h": optional_decimal_text(ticker.turnover_24h),
        "volume_24h": optional_decimal_text(ticker.volume_24h),
        "observed_at": datetime.now(UTC).isoformat(),
    }


def bybit_symbol_to_pair(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}/USDT"
    return symbol


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def optional_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return decimal_text(value)
