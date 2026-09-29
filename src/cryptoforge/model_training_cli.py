from __future__ import annotations

import argparse
from pathlib import Path

from cryptoforge.model_training import ModelTrainingRunner, load_pairs_from_file
from cryptoforge.supabase_executor import SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseRestClient


DEFAULT_PAIRS = ["ETH/USDT", "NEAR/USDT", "ENA/USDT", "HYPE/USDT"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and publish a lightweight CryptoForge model.")
    parser.add_argument("--pair", action="append", help="Pair such as ETH/USDT. Can be repeated.")
    parser.add_argument("--pairs-file", type=Path, help="JSON file containing a top-level pairs array.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--lookback-candles", type=int, default=500)
    parser.add_argument("--horizon-candles", type=int, default=3)
    parser.add_argument("--min-examples", type=int, default=80)
    parser.add_argument("--epochs", type=int, default=450)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".local/models"),
        help="Local directory where model artifacts are stored.",
    )
    parser.add_argument("--supabase-timeout", type=float, default=30.0)
    args = parser.parse_args()

    pairs = args.pair or load_pairs_from_file(args.pairs_file) or DEFAULT_PAIRS
    supabase = SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    runner = ModelTrainingRunner(
        reader=SupabaseMarketReader(supabase),
        supabase=supabase,
        artifact_dir=args.artifact_dir,
        lookback_candles=args.lookback_candles,
        horizon_candles=args.horizon_candles,
        min_examples=args.min_examples,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
    )
    model = runner.run(pairs, timeframe=args.timeframe)
    metric_text = ", ".join(
        f"{metric.split}:n={metric.count}:acc={metric.accuracy:.3f}:precision={metric.precision:.3f}:recall={metric.recall:.3f}"
        for metric in model.metrics
    )
    print(f"model_training version={model.model_version} pairs={len(pairs)} {metric_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
