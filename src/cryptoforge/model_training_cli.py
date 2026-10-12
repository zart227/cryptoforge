from __future__ import annotations

import argparse
from pathlib import Path

from cryptoforge.model_training import ModelTrainingRunner, load_pairs_from_file
from cryptoforge.live_feedback import LiveFeedbackReader
from cryptoforge.feedback_memory import ObservedFeedbackReader
from cryptoforge.supabase_executor import SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseRestClient


DEFAULT_PAIRS = ["ETH/USDT", "NEAR/USDT", "ENA/USDT", "HYPE/USDT"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and publish a lightweight CryptoForge model.")
    parser.add_argument("--pair", action="append", help="Pair such as ETH/USDT. Can be repeated.")
    parser.add_argument("--pairs-file", type=Path, help="JSON file containing a top-level pairs array.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--lookback-candles", type=int, default=500)
    parser.add_argument("--feature-lookback-candles",type=int,default=120,help="Exact feature window shared with live inference.")
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
    parser.add_argument("--round-trip-cost", type=float, default=0.003,
                        help="Round-trip fee and slippage fraction (default 0.003).")
    parser.add_argument(
        "--min-label-return",
        type=float,
        default=None,
        help="Minimum future move to label long/short as positive; defaults to round-trip cost.",
    )
    parser.add_argument("--supabase-timeout", type=float, default=30.0)
    args = parser.parse_args()

    pairs = args.pair or load_pairs_from_file(args.pairs_file) or DEFAULT_PAIRS
    supabase = SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    runner = ModelTrainingRunner(
        reader=SupabaseMarketReader(supabase),
        feedback_reader=ObservedFeedbackReader(LiveFeedbackReader(supabase), Path(".local/state/feedback-memory.sqlite")),
        supabase=supabase,
        artifact_dir=args.artifact_dir,
        lookback_candles=args.lookback_candles,
        horizon_candles=args.horizon_candles,
        feature_lookback_candles=args.feature_lookback_candles,
        min_examples=args.min_examples,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        round_trip_cost=args.round_trip_cost,
        min_label_return=args.min_label_return,
    )
    model = runner.run(pairs, timeframe=args.timeframe)
    metric_text = ", ".join(
        f"{metric.split}:n={metric.count}:acc={metric.accuracy:.3f}:precision={metric.precision:.3f}:recall={metric.recall:.3f}"
        for metric in model.metrics
    )
    short_metric_text = ", ".join(
        f"{metric.split}:n={metric.count}:acc={metric.accuracy:.3f}:precision={metric.precision:.3f}:recall={metric.recall:.3f}"
        for metric in model.short_metrics
    )
    admission=runner.last_source_admission
    print(f"source_admission accepted={len(admission.get('accepted_pairs',[]))} requested={len(admission.get('requested_pairs',[]))} coverage={admission.get('coverage_fraction')} excluded={admission.get('excluded_pairs',{})}")
    print(f"promotion={runner.last_promotion}")
    print(f"model_training version={model.model_version} pairs={len(pairs)} {metric_text}")
    print(f"short_training version={model.model_version} pairs={len(pairs)} {short_metric_text}")
    for head,splits in (model.probability_diagnostics or {}).items():
        for split,values in splits.items():
            print(f"probability_quality head={head} split={split} log_loss={values['log_loss']} baseline_log_loss={values['baseline_log_loss']} brier={values['brier']} baseline_brier={values['baseline_brier']} max_probability={values['probability_max']} signals={values['signals']} threshold={values['fixed_threshold']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
