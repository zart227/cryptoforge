#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from cryptoforge.market_data import (
    INFORMATIVE_TIMEFRAMES,
    PRIMARY_TIMEFRAME,
    BybitPublicClient,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Bybit Spot public market data.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    client = BybitPublicClient(timeout=args.timeout)
    instruments = client.get_usdt_spot_instruments()
    usdt_symbols = {instrument.symbol for instrument in instruments}
    if args.symbol not in usdt_symbols:
        raise SystemExit(f"{args.symbol} is not an active Bybit Spot USDT instrument")

    snapshot = client.get_snapshot(args.symbol, interval=PRIMARY_TIMEFRAME, limit=args.limit)
    informative = {
        interval: len(client.get_klines(args.symbol, interval=interval, limit=args.limit))
        for interval in INFORMATIVE_TIMEFRAMES
    }

    print(
        json.dumps(
            {
                "symbol": args.symbol,
                "active_usdt_spot_pairs": len(usdt_symbols),
                "ticker_last_price": str(snapshot.ticker.last_price),
                "primary_timeframe": f"{PRIMARY_TIMEFRAME}m",
                "primary_candles": len(snapshot.candles),
                "informative_candles": informative,
                "fresh": snapshot.freshness.is_fresh,
                "freshness_reason": snapshot.freshness.reason,
                "allow_new_entries": snapshot.allow_new_entries,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
