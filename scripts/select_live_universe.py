from __future__ import annotations

import argparse
import json
from pathlib import Path

from cryptoforge.market_data import BybitPublicClient
from cryptoforge.scanner import MarketScanner, ScannerConfig


def bybit_symbol_to_freqtrade_pair(symbol: str) -> str:
    if not symbol.endswith("USDT"):
        raise ValueError(f"only USDT spot symbols are supported: {symbol}")
    return f"{symbol[:-4]}/USDT"


def main() -> int:
    parser = argparse.ArgumentParser(description="Select a bounded intraday Spot universe.")
    parser.add_argument("--output", type=Path, default=Path("/opt/cryptoforge/config/live-universe.json"))
    parser.add_argument("--live-config", type=Path)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--cheap-shortlist-size", type=int, default=20)
    parser.add_argument("--expensive-shortlist-size", type=int, default=8)
    parser.add_argument("--candle-limit", type=int, default=100)
    args = parser.parse_args()

    scanner = MarketScanner(
        BybitPublicClient(timeout=15),
        ScannerConfig(
            cheap_shortlist_size=args.cheap_shortlist_size,
            expensive_shortlist_size=args.expensive_shortlist_size,
            output_limit=args.limit,
            candle_limit=args.candle_limit,
        ),
    )
    result = scanner.scan()
    pairs = [bybit_symbol_to_freqtrade_pair(candidate.symbol) for candidate in result.selected]
    payload = {
        "pairs": pairs,
        "selected": [
            {
                "symbol": candidate.symbol,
                "pair": bybit_symbol_to_freqtrade_pair(candidate.symbol),
                "score": str(candidate.score),
                "turnover_24h": str(candidate.turnover_24h),
                "atr_pct": str(candidate.atr_pct),
                "momentum_pct": str(candidate.momentum_pct),
                "oscillation_score": str(candidate.oscillation_score),
            }
            for candidate in result.selected
        ],
        "cheap_candidates": len(result.cheap_candidates),
        "rejected": len(result.rejected),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.live_config is not None:
        config = json.loads(args.live_config.read_text(encoding="utf-8"))
        if config.get("trading_mode") != "spot" or config.get("margin_mode") not in ("", None):
            raise ValueError("refusing to update non-spot live config")
        config.setdefault("exchange", {})["pair_whitelist"] = pairs
        args.live_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"pairs={','.join(pairs)}")
    print(f"output={args.output}")
    if args.live_config is not None:
        print(f"live_config_updated={args.live_config}")
    return 0 if pairs else 1


if __name__ == "__main__":
    raise SystemExit(main())
