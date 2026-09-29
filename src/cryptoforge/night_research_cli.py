from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cryptoforge.night_research import NightResearchRunner
from cryptoforge.supabase_executor import SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseRestClient


DEFAULT_PAIRS = [
    "ETH/USDT",
    "NEAR/USDT",
    "ENA/USDT",
    "HYPE/USDT",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one lightweight CryptoForge night research cycle.")
    parser.add_argument("--pair", action="append", help="Pair such as ETH/USDT. Can be repeated.")
    parser.add_argument(
        "--pairs-file",
        type=Path,
        help="JSON file containing a top-level pairs array, such as select_live_universe.py output.",
    )
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--lookback-candles", type=int, default=240)
    parser.add_argument("--min-candles", type=int, default=80)
    parser.add_argument("--supabase-timeout", type=float, default=30.0)
    args = parser.parse_args()

    pairs = args.pair or file_pairs(args.pairs_file) or env_pairs() or DEFAULT_PAIRS
    supabase = SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    runner = NightResearchRunner(
        reader=SupabaseMarketReader(supabase),
        supabase=supabase,
        min_candles=args.min_candles,
    )
    report = runner.run(pairs, timeframe=args.timeframe, lookback_candles=args.lookback_candles)

    top = ", ".join(f"{result.pair}:{result.score:.3f}" for result in report.results[:5])
    print(f"night_research pairs={len(pairs)} results={len(report.results)} top={top}")
    return 0 if report.results else 1


def env_pairs() -> list[str]:
    value = os.environ.get("CRYPTOFORGE_RESEARCH_PAIRS", "")
    return [pair.strip() for pair in value.split(",") if pair.strip()]


def file_pairs(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [str(pair).strip() for pair in payload.get("pairs", []) if str(pair).strip()]
