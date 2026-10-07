from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.live_trade_journal import sync_live_journal
from cryptoforge.live_risk import count_open_spot_positions, daily_equity_blockers, dynamic_entry_capacity
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.order_observer import BybitOrderObserver, executor_instance_id
from cryptoforge.research_selection import NightResearchSelector
from cryptoforge.supabase_executor import SupabaseLiveExecutor, SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseMarketWriter, SupabaseRestClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Supabase-backed live execution cycle.")
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="Pair to evaluate, for example ETH/USDT. Can be repeated.",
    )
    parser.add_argument("--stake-amount", default="5")
    parser.add_argument(
        "--max-open-positions",
        type=int,
        default=6,
        help="Hard safety cap; the effective limit is reduced automatically from account equity.",
    )
    parser.add_argument("--max-daily-loss", default="2")
    parser.add_argument("--stop-loss-percent", default="0.04")
    parser.add_argument("--max-dust-fraction", default="0.01")
    parser.add_argument("--live", action="store_true", help="Submit a real Bybit order when the signal and guards pass.")
    parser.add_argument(
        "--use-night-research",
        action="store_true",
        help="Prefer the latest fresh night research pair selection, falling back to --pair.",
    )
    parser.add_argument("--night-research-limit", type=int, default=12)
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
    journal_ok = reconcile_journal(bybit, supabase)
    instance_id = executor_instance_id()
    try:
        observed_buys = BybitOrderObserver(
            bybit=bybit,
            supabase=supabase,
            instance_id=instance_id,
        ).observe_filled_buys()
        foreign_buys = [order for order in observed_buys if order.origin != "this_instance"]
        print(
            f"buy_observer=ok instance={instance_id} "
            f"filled_buys={len(observed_buys)} foreign_or_legacy={len(foreign_buys)}"
        )
        for order in foreign_buys:
            print(
                f"buy_observer=warning symbol={order.symbol} order_id={order.order_id} "
                f"origin={order.origin} occurred_at={order.occurred_at}"
            )
    except Exception as exc:  # noqa: BLE001 - monitoring failure must not stop risk/exit handling.
        print(f"buy_observer=error instance={instance_id} error={exc}")
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
    refresh_stale_market_data(supabase, pairs=pairs)

    account = bybit.get_unified_usdt_balance()
    open_positions = count_open_spot_positions(bybit.get_unified_wallet_coins())
    stake_amount = Decimal(args.stake_amount)
    equity_capacity, effective_max_positions, available_entry_slots = dynamic_entry_capacity(
        total_equity=account.total_equity_usd,
        free_usdt=account.usdt_wallet_balance,
        stake_amount=stake_amount,
        open_positions=open_positions,
        hard_position_cap=args.max_open_positions,
    )
    entry_blockers = list(
        daily_equity_blockers(
            current_equity=account.total_equity_usd,
            maximum_loss=Decimal(args.max_daily_loss),
            state_path=Path(".local/state/live-equity-risk.json"),
            now=datetime.now(UTC),
        )
    )
    if not journal_ok:
        entry_blockers.append("live trade journal unavailable; new entries paused")
    if open_positions >= effective_max_positions:
        entry_blockers.append(
            f"dynamic position limit reached: {open_positions} >= {effective_max_positions}"
        )
    elif available_entry_slots <= 0:
        entry_blockers.append(
            f"no funded entry slots: free_usdt={account.usdt_wallet_balance} stake={stake_amount}"
        )
    print(
        f"risk_state=checked equity={account.total_equity_usd} free_usdt={account.usdt_wallet_balance} "
        f"open_positions={open_positions} equity_capacity={equity_capacity} "
        f"effective_max_positions={effective_max_positions} entry_slots={available_entry_slots} "
        f"entry_blockers={entry_blockers}"
    )

    risk_snapshot = Path(".local/state/live-risk-snapshot.json")
    risk_snapshot.parent.mkdir(parents=True, exist_ok=True)
    risk_temp = risk_snapshot.with_suffix(".tmp")
    risk_temp.write_text(json.dumps({
        "observed_at": datetime.now(UTC).isoformat(),
        "live": args.live,
        "stake_amount": str(stake_amount),
        "max_open_positions": args.max_open_positions,
        "effective_max_positions": effective_max_positions,
        "open_positions": open_positions,
        "available_entry_slots": available_entry_slots,
        "max_daily_loss": args.max_daily_loss,
        "stop_loss_percent": args.stop_loss_percent,
        "entry_blockers": entry_blockers,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    risk_temp.replace(risk_snapshot)

    executor = SupabaseLiveExecutor(
        reader=SupabaseMarketReader(supabase),
        supabase=supabase,
        bybit=bybit,
        stake_amount=stake_amount,
        allow_intraday_reversion=args.allow_intraday_reversion and pair_source == "night_research",
        allow_emerging_momentum=args.allow_emerging_momentum and pair_source == "night_research",
        active_model_registry=ActiveModelRegistry(supabase) if args.ml_mode != "off" else None,
        ml_mode=args.ml_mode,
        ml_threshold=args.ml_threshold,
        ml_max_age=timedelta(hours=args.ml_max_age_hours),
        entry_blockers=tuple(entry_blockers),
        entry_slots=available_entry_slots,
        stop_loss_percent=Decimal(args.stop_loss_percent),
        max_dust_fraction=Decimal(args.max_dust_fraction),
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
    journal_ok = reconcile_journal(bybit, supabase)
    return 0 if successes and journal_ok else 1


def reconcile_journal(bybit: BybitPrivateClient, supabase: SupabaseRestClient) -> bool:
    try:
        result = sync_live_journal(bybit=bybit, supabase=supabase)
        print(f"live_journal=ok {result}")
        return True
    except Exception as exc:
        print(f"live_journal=error error_type={type(exc).__name__}")
        try:
            SupabaseMarketWriter(supabase).write_bot_health(
                "live_trade_journal", "error", "Journal reconciliation failed; new entries paused",
                {"error_type": type(exc).__name__},
            )
        except Exception:
            pass
        return False


def include_held_pairs(bybit: BybitPrivateClient, *, pairs: list[str], candidates: list[str]) -> list[str]:
    selected = list(dict.fromkeys(pairs))
    try:
        wallet_coins = bybit.get_unified_wallet_coins()
    except Exception as exc:  # noqa: BLE001 - retain candidate fallback on API failure.
        print(f"held_pair_inventory=error error={exc}")
        wallet_coins = []
    for coin in wallet_coins:
        name = str(coin.get("coin") or "")
        usd_value = Decimal(str(coin.get("usdValue") or "0"))
        pair = f"{name}/USDT"
        if name and name != "USDT" and usd_value >= Decimal("1") and pair not in selected:
            selected.append(pair)
            print(f"held_pair_included pair={pair} usd_value={usd_value}")
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


def refresh_stale_market_data(
    supabase: SupabaseRestClient,
    *,
    pairs: list[str],
    maximum_age: timedelta = timedelta(minutes=9),
) -> None:
    reader = SupabaseMarketReader(supabase)
    public = BybitPublicClient(timeout=15, max_retries=2, retry_backoff_seconds=1)
    writer = SupabaseMarketWriter(supabase)
    now = datetime.now(UTC)
    for pair in pairs:
        try:
            candles = reader.read_candles(pair, limit=1)
            if candles and now - candles[-1].open_time <= maximum_age:
                continue
        except Exception:  # noqa: BLE001 - public refresh below is the fallback.
            pass
        symbol = pair.replace("/", "")
        try:
            writer.write_tickers(public.get_tickers(symbol))
            writer.write_candles(public.get_klines(symbol, interval="5", limit=120))
            print(f"stale_market_refresh=ok pair={pair}")
        except Exception as exc:  # noqa: BLE001 - stale-data guard will safely reject this pair.
            print(f"stale_market_refresh=error pair={pair} error={exc}")


if __name__ == "__main__":
    raise SystemExit(main())
