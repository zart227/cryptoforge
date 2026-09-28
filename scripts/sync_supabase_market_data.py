from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path

from cryptoforge.market_data import BybitPublicClient, MarketDataError, PRIMARY_TIMEFRAME
from cryptoforge.supabase_market import SupabaseMarketError, SupabaseMarketWriter, SupabaseRestClient


def load_pairs(args: argparse.Namespace) -> list[str]:
    if args.pair:
        return args.pair
    if args.live_config:
        config = json.loads(args.live_config.read_text(encoding="utf-8"))
        return list(config.get("exchange", {}).get("pair_whitelist", []))
    return []


def pair_to_bybit_symbol(pair: str) -> str:
    if pair.endswith("/USDT"):
        return pair.replace("/", "")
    if pair.endswith("USDT"):
        return pair
    raise ValueError(f"Only USDT pairs are supported: {pair}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync bounded Bybit market data into Supabase.")
    parser.add_argument("--pair", action="append", help="Freqtrade pair such as ETH/USDT. Can be repeated.")
    parser.add_argument(
        "--live-config",
        type=Path,
        default=Path("/opt/cryptoforge/config/freqtrade.live-pilot.json"),
        help="Read pair whitelist from the live Freqtrade config.",
    )
    parser.add_argument("--interval", default=PRIMARY_TIMEFRAME)
    parser.add_argument("--candle-limit", type=int, default=120)
    parser.add_argument("--bybit-timeout", type=float, default=15.0)
    parser.add_argument("--supabase-timeout", type=float, default=15.0)
    args = parser.parse_args()

    pairs = load_pairs(args)
    if not pairs:
        raise SystemExit("No pairs supplied and no live config pair whitelist found.")

    bybit = BybitPublicClient(timeout=args.bybit_timeout, max_retries=3, retry_backoff_seconds=2.0)
    writer = SupabaseMarketWriter(
        SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    )

    ok_pairs: list[str] = []
    failed: dict[str, str] = {}
    for pair in pairs:
        symbol = pair_to_bybit_symbol(pair)
        try:
            tickers = bybit.get_tickers(symbol)
            candles = bybit.get_klines(symbol, interval=args.interval, limit=args.candle_limit)
            writer.write_tickers(tickers)
            writer.write_candles(candles)
        except (MarketDataError, SupabaseMarketError, OSError, ValueError) as exc:
            failed[pair] = str(exc)
            continue
        ok_pairs.append(pair)

    status = "ok" if ok_pairs and not failed else "warning" if ok_pairs else "error"
    writer.write_bot_health(
        "supabase_market_sync",
        status,
        f"synced={len(ok_pairs)} failed={len(failed)}",
        {
            "pairs": pairs,
            "synced_pairs": ok_pairs,
            "failed": failed,
            "interval": args.interval,
            "candle_limit": args.candle_limit,
            "host": socket.gethostname(),
        },
    )

    print(f"synced_pairs={','.join(ok_pairs)}")
    if failed:
        print("failed=" + json.dumps(failed, sort_keys=True))
    return 0 if ok_pairs else 1


if __name__ == "__main__":
    raise SystemExit(main())
