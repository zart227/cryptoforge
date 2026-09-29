from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path

from cryptoforge.market_data import BybitPublicClient, MarketDataError, PRIMARY_TIMEFRAME
from cryptoforge.scanner import MarketScanner, ScannerConfig
from cryptoforge.supabase_market import SupabaseMarketError, SupabaseMarketWriter, SupabaseRestClient


def load_pairs(args: argparse.Namespace) -> list[str]:
    if args.pair:
        return args.pair
    if args.live_config:
        config = json.loads(args.live_config.read_text(encoding="utf-8"))
        if "pairs" in config:
            return list(config["pairs"])
        return list(config.get("exchange", {}).get("pair_whitelist", []))
    return []


def pair_to_bybit_symbol(pair: str) -> str:
    if pair.endswith("/USDT"):
        return pair.replace("/", "")
    if pair.endswith("USDT"):
        return pair
    raise ValueError(f"Only USDT pairs are supported: {pair}")


def scan_pairs(client: BybitPublicClient, args: argparse.Namespace) -> tuple[list[str], object]:
    config = ScannerConfig(
        cheap_shortlist_size=args.cheap_shortlist_size,
        expensive_shortlist_size=args.expensive_shortlist_size,
        output_limit=args.universe_limit,
        candle_limit=args.scanner_candle_limit,
    )
    result = MarketScanner(client, config).scan()
    return [f"{item.symbol[:-4]}/USDT" for item in result.selected], (config, result)


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
    parser.add_argument("--scan-universe", action="store_true")
    parser.add_argument("--selection-name", default="research-collector")
    parser.add_argument("--universe-limit", type=int, default=20)
    parser.add_argument("--cheap-shortlist-size", type=int, default=80)
    parser.add_argument("--expensive-shortlist-size", type=int, default=32)
    parser.add_argument("--scanner-candle-limit", type=int, default=120)
    args = parser.parse_args()

    bybit = BybitPublicClient(timeout=args.bybit_timeout, max_retries=3, retry_backoff_seconds=2.0)
    writer = SupabaseMarketWriter(
        SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    )
    scan = None
    if args.scan_universe:
        pairs, scan = scan_pairs(bybit, args)
    else:
        pairs = load_pairs(args)
    if not pairs:
        raise SystemExit("No pairs selected or supplied.")

    if scan is not None:
        scanner_config, result = scan
        writer.write_selected_universe(
            selection_name=args.selection_name,
            pairs=pairs,
            scanner_config={
                "output_limit": scanner_config.output_limit,
                "cheap_shortlist_size": scanner_config.cheap_shortlist_size,
                "expensive_shortlist_size": scanner_config.expensive_shortlist_size,
                "candle_limit": scanner_config.candle_limit,
                "timeframe": scanner_config.timeframe,
            },
            selected=[
                {
                    "pair": f"{item.symbol[:-4]}/USDT",
                    "score": str(item.score),
                    "turnover_24h": str(item.turnover_24h),
                    "atr_pct": str(item.atr_pct),
                    "oscillation_score": str(item.oscillation_score),
                    "momentum_pct": str(item.momentum_pct),
                    "emerging_score": str(item.emerging_score),
                }
                for item in result.selected
            ],
            rejected_count=len(result.rejected),
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
