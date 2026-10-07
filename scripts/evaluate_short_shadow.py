from __future__ import annotations

import argparse
import json
import math

from cryptoforge.short_shadow import ShortShadowOutcomeRunner
from cryptoforge.supabase_market import SupabaseRestClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate short shadow outcomes from Supabase trade decisions.")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--supabase-timeout", type=float, default=30.0)
    parser.add_argument("--round-trip-cost", type=float, default=0.003)
    args = parser.parse_args()
    if args.lookback_hours < 1 or args.limit < 1:
        parser.error("lookback-hours and limit must be positive")
    if not math.isfinite(args.round_trip_cost) or args.round_trip_cost < 0:
        parser.error("round-trip-cost must be finite and nonnegative")
    summary = ShortShadowOutcomeRunner(
        SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    ).run(lookback_hours=args.lookback_hours, limit=args.limit, round_trip_cost=args.round_trip_cost)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
