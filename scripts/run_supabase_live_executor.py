from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.research_selection import NightResearchSelector
from cryptoforge.supabase_executor import SupabaseLiveExecutor, SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseRestClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Supabase-backed live execution cycle.")
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="Pair to evaluate, for example ETH/USDT. Can be repeated.",
    )
    parser.add_argument("--stake-amount", default="10")
    parser.add_argument("--live", action="store_true", help="Submit a real Bybit order when the signal and guards pass.")
    parser.add_argument(
        "--use-night-research",
        action="store_true",
        help="Prefer the latest fresh night research pair selection, falling back to --pair.",
    )
    parser.add_argument("--night-research-limit", type=int, default=4)
    parser.add_argument(
        "--allow-intraday-reversion",
        action="store_true",
        help="Allow cautious support-bounce mean-reversion entries for research-selected pairs.",
    )
    parser.add_argument(
        "--allow-emerging-momentum",
        action="store_true",
        help="Allow cautious momentum entries for fresh research-selected active pairs.",
    )
    parser.add_argument(
        "--append-fallback-pairs",
        action="store_true",
        help="Evaluate all fallback pairs after the research-selected pairs.",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--ml-mode",
        choices=("off", "shadow", "gate"),
        default="shadow",
        help="Observe the active Supabase model or use it as an entry gate.",
    )
    parser.add_argument("--ml-threshold", type=float, default=0.55)
    parser.add_argument("--ml-max-age-hours", type=float, default=36.0)
    args = parser.parse_args()

    supabase = SupabaseRestClient.from_env(timeout_seconds=args.timeout)
    bybit = BybitPrivateClient.from_env()
    clock_offset_ms = bybit.synchronize_time()
    print(f"bybit_clock_offset_ms={clock_offset_ms}")
    fallback_pairs = args.pair or ["ETH/USDT"]
    pair_source = "cli"
    pair_reasons: tuple[str, ...] = ()
    pairs = fallback_pairs
    if args.use_night_research:
        selection = NightResearchSelector(supabase).select_pairs(
            fallback_pairs=fallback_pairs,
            limit=args.night_research_limit,
        )
        pairs = list(selection.pairs)
        pair_source = selection.source
        pair_reasons = selection.reasons
        generated = selection.generated_at.isoformat() if selection.generated_at else "none"
        print(f"pair_source={pair_source} generated_at={generated} reasons={'; '.join(pair_reasons)}")
    if args.append_fallback_pairs:
        pairs = list(dict.fromkeys([*pairs, *fallback_pairs]))
    pairs = include_held_pairs(bybit, pairs=pairs, candidates=fallback_pairs)

    executor = SupabaseLiveExecutor(
        reader=SupabaseMarketReader(supabase),
        supabase=supabase,
        bybit=bybit,
        stake_amount=Decimal(args.stake_amount),
        allow_intraday_reversion=args.allow_intraday_reversion and pair_source == "night_research",
        allow_emerging_momentum=args.allow_emerging_momentum and pair_source == "night_research",
        active_model_registry=ActiveModelRegistry(supabase) if args.ml_mode != "off" else None,
        ml_mode=args.ml_mode,
        ml_threshold=args.ml_threshold,
        ml_max_age=timedelta(hours=args.ml_max_age_hours),
    )
    successes = 0
    failures = 0
    for pair in pairs:
        try:
            decision = executor.run_once(pair, live=args.live)
        except Exception as exc:  # noqa: BLE001 - one bad pair must not block the rest.
            failures += 1
            print(f"decision=error pair={pair} error={exc}")
            continue
        successes += 1
        print(
            "decision={decision} pair={pair} reasons={reasons} order={order}".format(
                decision=decision.decision,
                pair=decision.pair,
                reasons="; ".join(decision.reasons),
                order=decision.order or {},
            )
        )
    return 0 if successes else min(failures, 1)


def include_held_pairs(bybit: BybitPrivateClient, *, pairs: list[str], candidates: list[str]) -> list[str]:
    selected = list(dict.fromkeys(pairs))
    for pair in candidates:
        base_coin = pair.split("/", 1)[0]
        try:
            balance = bybit.get_unified_coin_wallet_balance(base_coin)
        except Exception as exc:  # noqa: BLE001 - one balance lookup must not block execution.
            print(f"held_pair_check=error pair={pair} error={exc}")
            continue
        if balance > Decimal("0.0000001") and pair not in selected:
            selected.append(pair)
            print(f"held_pair_included pair={pair} balance={balance}")
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
