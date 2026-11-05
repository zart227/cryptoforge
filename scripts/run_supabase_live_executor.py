from __future__ import annotations

import argparse
import json
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.entry_account_snapshot import read_entry_account_snapshot
from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.live_trade_journal import sync_live_journal
from cryptoforge.live_risk import daily_equity_blockers
from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
from cryptoforge.decision_outbox import DecisionOutbox, DurableDecisionClient
from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient
from cryptoforge.execution_ownership import execution_lease, credential_scope
from cryptoforge.portfolio_drawdown import drawdown_blockers
from cryptoforge.fractional_risk import load_fractional_policy
from cryptoforge.execution_controls import ControlledOrderClient, control_blockers
from cryptoforge.submission_risk import SubmissionRiskClient
from cryptoforge.runtime_approval import (PinnedActiveModelRegistry, RuntimeApprovedOrderClient,
    approval_blockers, canonical, require_sha, runtime_contract, sha)
from cryptoforge.account_verification import (AccountVerifiedOrderClient,
    load_account_policy, observe_account)
from cryptoforge.account_ownership import account_execution_lease, AccountLeaseOrderClient
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
    parser.add_argument('--exit-data-fallback', action='store_true',
        help='Use validated public closed candles for exits when primary candles fail; block new entries on fallback.')
    parser.add_argument('--decision-outbox', type=Path,
        help='Persist trade decisions locally before delivery; retry records only, never exchange orders.')
    parser.add_argument('--order-submission-journal', type=Path,
        help='Persist market-order intent before submission; reconcile uncertain attempts without resending.')
    parser.add_argument('--execution-controls', type=Path,
        help='Explicit operator kill/no-new-entry JSON; reread before each order submission.')
    parser.add_argument('--submission-risk-guard', action='store_true',
        help='Recheck configured absolute stake, position and daily loss limits immediately before market Buy.')
    parser.add_argument('--spot-reservation-guard', action='store_true',
        help='Require non-borrowed cash fields and complete open Spot order pagination before Buy.')
    parser.add_argument('--local-order-reservations', action='store_true',
        help='Keep durable quote/position reserves for locally submitted buys until qualified reconciliation.')
    parser.add_argument('--settle-closed-reservations', action='store_true',
        help='Release narrow fully closed reservations only after exact original fill and zero-inventory proof.')
    parser.add_argument('--drawdown-state', type=Path, help='Existing reviewed observed-equity peak state; never auto-reset.')
    parser.add_argument('--max-portfolio-drawdown', type=Decimal,
        help='Explicit observed-equity drawdown fraction, greater than0 and at most0.10.')
    parser.add_argument('--fractional-risk-policy', type=Path,
        help='Explicit equity exposure/planned-stop-risk policy; requires remote and local reservation guards.')
    parser.add_argument('--entry-runtime-approval', type=Path,
        help='Require expiring operator approval bound to exact runtime and pinned model; not full strategy admission.')
    parser.add_argument('--entry-model-sha256',
        help='Explicit active artifact SHA256 for runtime approval; requires ML gate mode.')
    parser.add_argument('--entry-account-policy', type=Path,
        help='Check authenticated UID/subaccount/Spot-only key permissions and reviewed IPs before Buy; requires runtime approval.')
    parser.add_argument('--account-ownership-guard', action='store_true',
        help='Hold a verified UID/endpoint local lease across keys; no automatic adoption of existing journals.')
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
    if args.spot_reservation_guard and not args.submission_risk_guard:
        parser.error('--spot-reservation-guard requires --submission-risk-guard')
    if args.local_order_reservations and (not args.submission_risk_guard or args.order_submission_journal is None):
        parser.error('--local-order-reservations requires --submission-risk-guard and --order-submission-journal')
    if args.settle_closed_reservations and not args.local_order_reservations:
        parser.error('--settle-closed-reservations requires --local-order-reservations')
    if args.fractional_risk_policy is not None and (not args.spot_reservation_guard or not args.local_order_reservations):
        parser.error('--fractional-risk-policy requires --spot-reservation-guard and --local-order-reservations')
    if args.entry_runtime_approval is not None:
        if (not all((args.exit_data_fallback, args.submission_risk_guard, args.spot_reservation_guard,
                args.local_order_reservations, args.order_submission_journal, args.decision_outbox,
                args.execution_controls, args.drawdown_state, args.fractional_risk_policy)) or args.ml_mode != 'gate'):
            parser.error('runtime approval requires all risk/reservation/persistence/control paths and ML gate')
        try:
            require_sha(args.entry_model_sha256)
        except ValueError:
            parser.error('runtime approval requires explicit --entry-model-sha256')
    elif args.entry_model_sha256 is not None:
        parser.error('--entry-model-sha256 requires --entry-runtime-approval')
    if args.entry_account_policy is not None and args.entry_runtime_approval is None:
        parser.error('--entry-account-policy requires --entry-runtime-approval')
    if args.account_ownership_guard and (args.entry_account_policy is None or args.order_submission_journal is None):
        parser.error('--account-ownership-guard requires --entry-account-policy and bound order journal')
    if args.drawdown_state is not None or args.max_portfolio_drawdown is not None:
        if (args.drawdown_state is None or args.max_portfolio_drawdown is None
                or not args.submission_risk_guard or args.order_submission_journal is None):
            parser.error('drawdown guard requires state, explicit threshold, submission risk guard and bound order journal')
        if not args.max_portfolio_drawdown.is_finite() or not Decimal('0') < args.max_portfolio_drawdown <= Decimal('.10'):
            parser.error('drawdown fraction must be finite, >0 and <=0.10')
    bybit = BybitPrivateClient.from_env()
    if args.account_ownership_guard:
        with account_execution_lease(args.order_submission_journal,bybit,
                policy_path=args.entry_account_policy,
                lock_directory=Path('.local/state/executor-ownership')) as lease:
            return run_cycle(args,bybit,account_lease=lease)
    if args.order_submission_journal is not None:
        with execution_lease(args.order_submission_journal, bybit,
                lock_directory=Path('.local/state/executor-ownership')):
            return run_cycle(args, bybit)
    return run_cycle(args, bybit)


def run_cycle(args, bybit, *, account_lease=None):
    ownership_guard = getattr(args,'account_ownership_guard',False)
    if ownership_guard:
        if account_lease is None:
            raise ValueError('active verified account lease required before cycle')
        account_lease.assert_held(client=bybit,journal_path=args.order_submission_journal)
    fractional_policy = None; fractional_policy_sha256 = None
    if args.fractional_risk_policy is not None:
        fractional_policy, fractional_policy_sha256 = load_fractional_policy(
            args.fractional_risk_policy, stop_fraction=Decimal(args.stop_loss_percent))
    supabase = SupabaseRestClient.from_env(timeout_seconds=args.timeout)
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
    selection_blockers: tuple[str, ...] = ()
    pairs = fallback_pairs
    if args.use_night_research:
        try:
            selection = NightResearchSelector(supabase).select_pairs(
                fallback_pairs=fallback_pairs,
                limit=args.night_research_limit,
            )
            pairs = list(selection.pairs)
            pair_source = selection.source
            pair_reasons = selection.reasons
            generated = selection.generated_at.isoformat() if selection.generated_at else "none"
        except Exception as exc:  # Research outage must not prevent held-position handling.
            pairs = list(fallback_pairs)
            pair_source = 'night_research_unavailable'
            pair_reasons = (f'research_selection_error={type(exc).__name__}',)
            selection_blockers = ('research pair selection unavailable; new entries paused',)
            generated = 'none'
        print(f"pair_source={pair_source} generated_at={generated} reasons={'; '.join(pair_reasons)}")
    if args.append_fallback_pairs:
        pairs = list(dict.fromkeys([*pairs, *fallback_pairs]))
    pairs = include_held_pairs(bybit, pairs=pairs, candidates=fallback_pairs)
    refresh_stale_market_data(supabase, pairs=pairs)

    stake_amount = Decimal(args.stake_amount)
    account = None; open_positions = None; equity_capacity = None; effective_max_positions = None
    available_entry_slots = 0
    entry_blockers = []
    account_policy_path = getattr(args, 'entry_account_policy', None)
    account_policy = None; account_policy_sha256 = None; account_observation = None
    if account_policy_path is not None:
        try:
            account_policy, account_policy_sha256 = load_account_policy(account_policy_path)
            account_observation = observe_account(bybit, account_policy)
        except Exception as exc:
            entry_blockers.append('account identity or key permissions unavailable or unqualified; new entries paused')
            print(f'entry_account_verification=unavailable error_type={type(exc).__name__}')
    try:
        account, open_positions, equity_capacity, effective_max_positions, available_entry_slots, snapshot_coins = read_entry_account_snapshot(
            bybit, stake_amount=stake_amount, position_cap=args.max_open_positions)
    except Exception as exc:  # Unknown entry sizing must not bypass per-symbol exit checks.
        entry_blockers.append('account-wide risk data unavailable or invalid; new entries paused')
        print(f'entry_account_snapshot=unavailable error_type={type(exc).__name__}')
    if account is not None:
        recovered_pairs = []
        for coin in snapshot_coins:
            pair = f"{coin['coin']}/USDT"
            if coin['coin'] != 'USDT' and Decimal(str(coin['usdValue'])) >= Decimal('1') and pair not in pairs:
                pairs.append(pair); recovered_pairs.append(pair)
        if recovered_pairs:
            print(f'held_pairs_recovered_from_entry_snapshot count={len(recovered_pairs)}')
            refresh_stale_market_data(supabase, pairs=recovered_pairs)
    if account is not None:
        entry_blockers.extend(daily_equity_blockers(
            current_equity=account.total_equity_usd,
            maximum_loss=Decimal(args.max_daily_loss),
            state_path=Path(".local/state/live-equity-risk.json"),
            now=datetime.now(UTC),
        ))
    entry_blockers.extend(selection_blockers)
    drawdown_policy = None
    if args.drawdown_state is not None:
        drawdown_policy = dict(state_path=args.drawdown_state, maximum_drawdown=args.max_portfolio_drawdown,
            owner_id=hashlib.sha256(json.dumps(credential_scope(bybit), sort_keys=True).encode()).hexdigest())
        if account is not None:
            entry_blockers.extend(drawdown_blockers(current_equity=account.total_equity_usd,
                now=datetime.now(UTC), **drawdown_policy))
    if not journal_ok:
        entry_blockers.append("live trade journal unavailable; new entries paused")
    if account is not None and open_positions >= effective_max_positions:
        entry_blockers.append(
            f"dynamic position limit reached: {open_positions} >= {effective_max_positions}"
        )
    elif account is not None and available_entry_slots <= 0:
        entry_blockers.append(
            f"no funded entry slots: free_usdt={account.usdt_wallet_balance} stake={stake_amount}"
        )
    print(
        f"risk_state={'checked' if account is not None else 'unknown'} "
        f"equity={account.total_equity_usd if account is not None else 'unknown'} "
        f"usdt_wallet={account.usdt_wallet_balance if account is not None else 'unknown'} "
        f"open_positions={open_positions} equity_capacity={equity_capacity} "
        f"effective_max_positions={effective_max_positions} entry_slots={available_entry_slots} "
        f"entry_blockers={entry_blockers}"
    )

    risk_snapshot = Path(".local/state/live-risk-snapshot.json")
    snapshot = {
        "observed_at": datetime.now(UTC).isoformat(),
        "live": args.live,
        "account_risk_data_status": 'checked' if account is not None else 'unknown',
        "total_equity": str(account.total_equity_usd) if account is not None else None,
        "usdt_wallet_balance": str(account.usdt_wallet_balance) if account is not None else None,
        "evaluation_pairs": list(pairs),
        "stake_amount": str(stake_amount),
        "max_open_positions": args.max_open_positions,
        "effective_max_positions": effective_max_positions,
        "open_positions": open_positions,
        "available_entry_slots": available_entry_slots,
        "max_daily_loss": args.max_daily_loss,
        "fractional_risk_policy_sha256": fractional_policy_sha256,
        "entry_account_policy_sha256": account_policy_sha256,
        "entry_account_observation": account_observation,
        "account_ownership": account_lease.diagnostic() if ownership_guard else None,
        "stop_loss_percent": args.stop_loss_percent,
        "entry_blockers": list(entry_blockers),
    }

    decision_client = supabase
    outbox = None
    if args.decision_outbox is not None:
        outbox = DecisionOutbox(args.decision_outbox)
        outbox.flush(supabase)
        if outbox.pending():
            entry_blockers.append('decision outbox pending; new entries paused')
        decision_client = DurableDecisionClient(supabase, outbox)
    order_client = bybit
    if ownership_guard:
        order_client = AccountLeaseOrderClient(order_client,account_lease)
    approval_path = getattr(args, 'entry_runtime_approval', None)
    if approval_path is not None:
        contract_provider = lambda: runtime_contract(args, bybit, launcher_path=Path(__file__),
            fractional_policy_sha256=fractional_policy_sha256,
            account_policy_sha256=account_policy_sha256)
        try:
            contract = contract_provider()
            snapshot['runtime_approval_sha256'] = sha(canonical(contract))
            snapshot['runtime_approval_contract'] = contract
            entry_blockers.extend(approval_blockers(approval_path, contract, now=datetime.now(UTC)))
        except Exception:
            snapshot['runtime_approval_sha256'] = None
            entry_blockers.append('runtime binding unavailable or invalid; new entries paused')
        # Innermost entry wrapper: reread after risk queries and operator controls,
        # immediately before the raw submit, still inside the durable journal.
        order_client = RuntimeApprovedOrderClient(order_client, approval_path=approval_path,
            contract_provider=contract_provider,
            model_input_provider=lambda: getattr(executor, '_last_model_input', None))
    if account_policy_path is not None:
        # Fresh authenticated facts after risk/controls, then final runtime TTL
        # check (a slow private query must not extend an expired approval).
        order_client = AccountVerifiedOrderClient(order_client, policy=account_policy,
            policy_path=account_policy_path, policy_sha256=account_policy_sha256)
    if args.execution_controls is not None:
        entry_blockers.extend(control_blockers(args.execution_controls, 'Buy'))
        order_client = ControlledOrderClient(order_client, args.execution_controls)
    submission_journal = None
    if args.order_submission_journal is not None:
        submission_journal = OrderSubmissionJournal(args.order_submission_journal)
        try:
            resolved = submission_journal.reconcile(bybit)
            print(f'order_submission_reconciliation=ok resolved={resolved}')
            if outbox is not None:
                recovered = submission_journal.recover_decisions(outbox)
                outbox.flush(supabase)
                print(f'order_decision_recovery=ok recovered={recovered}')
                if outbox.pending():
                    entry_blockers.append('recovered order decisions pending; new entries paused')
            if args.settle_closed_reservations:
                from cryptoforge.reservation_settlement import settle_journal
                print(f'order_reservation_settlement={settle_journal(submission_journal, bybit)}')
        except Exception as exc:
            entry_blockers.append('order submission reconciliation unavailable; new entries paused')
            print(f'order_submission_reconciliation=error type={type(exc).__name__}')
    if args.submission_risk_guard:
        order_client = SubmissionRiskClient(order_client, maximum_stake=stake_amount,
            position_cap=args.max_open_positions, maximum_daily_loss=Decimal(args.max_daily_loss),
            state_path=Path('.local/state/live-equity-risk.json'), reservation_guard=args.spot_reservation_guard,
            submission_journal=submission_journal if args.local_order_reservations else None,
            drawdown_policy=drawdown_policy, fractional_policy=fractional_policy)
    if submission_journal is not None:
        order_client = JournaledOrderClient(order_client, submission_journal)
    snapshot['entry_blockers'] = list(entry_blockers)
    snapshot['configured_protections'] = dict(
        exit_data_fallback=args.exit_data_fallback, decision_outbox=outbox is not None,
        order_submission_journal=submission_journal is not None,
        execution_controls=args.execution_controls is not None,
        submission_risk_guard=args.submission_risk_guard,
        spot_reservation_guard=args.spot_reservation_guard,
        local_order_reservations=args.local_order_reservations,
        closed_reservation_settlement=args.settle_closed_reservations,
        observed_drawdown=drawdown_policy is not None,
        fractional_risk=fractional_policy is not None,
        entry_account_verification=account_policy_path is not None,
        verified_account_ownership=ownership_guard,
        runtime_approval=approval_path is not None)
    snapshot['protection_status_scope'] = 'configured_for_this_cycle_not_operational_qualification'
    try:
        write_json_report(risk_snapshot, snapshot)
    except OSError:
        entry_blockers.append('risk diagnostic snapshot unavailable; new entries paused')
    model_registry = ActiveModelRegistry(supabase) if args.ml_mode != 'off' else None
    if approval_path is not None:
        model_registry = PinnedActiveModelRegistry(model_registry, args.entry_model_sha256)
    executor = SupabaseLiveExecutor(
        reader=SupabaseMarketReader(supabase),
        supabase=decision_client,
        bybit=order_client,
        stake_amount=stake_amount,
        allow_intraday_reversion=args.allow_intraday_reversion and pair_source == "night_research",
        allow_emerging_momentum=args.allow_emerging_momentum and pair_source == "night_research",
        active_model_registry=model_registry,
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
            if ownership_guard:
                account_lease.assert_held(client=bybit,journal_path=args.order_submission_journal)
            decision = (run_with_exit_data_fallback(executor,
                BybitPublicClient(timeout=10, max_retries=0), pair, live=args.live)
                if args.exit_data_fallback else executor.run_once(pair, live=args.live))
            if outbox is not None and outbox.pending():
                executor.entry_blockers = (*executor.entry_blockers, 'decision outbox pending; new entries paused')
                print(f'decision_outbox=pending count={outbox.pending()}')
        except Exception as exc:  # noqa: BLE001 - one bad pair must not block the rest.
            failures += 1
            print(f"decision=error pair={pair} error={exc}")
            continue
        if decision.decision == 'recovery_required':
            failures += 1
        else:
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
    return 0 if successes and not failures and journal_ok and account is not None else 1


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
        if not isinstance(wallet_coins, list): raise ValueError('unknown wallet inventory')
    except Exception as exc:  # noqa: BLE001 - retain candidate fallback on API failure.
        print(f"held_pair_inventory=error error={exc}")
        wallet_coins = []
    for coin in wallet_coins:
        try:
            name = coin['coin']
            if not isinstance(name, str) or not name or not name.isascii() or not name.isalnum() or name != name.upper():
                raise ValueError('invalid inventory coin')
            if name == 'USDT': continue
            usd_value = Decimal(str(coin['usdValue']))
            if not usd_value.is_finite() or usd_value < 0: raise ValueError('unknown inventory value')
        except (ValueError, TypeError, KeyError, ArithmeticError):
            if isinstance(coin, dict):
                name = coin.get('coin')
                if (isinstance(name, str) and name != 'USDT' and name.isascii() and name.isalnum()
                        and name == name.upper() and f'{name}/USDT' not in selected):
                    selected.append(f'{name}/USDT')
            print('held_pair_inventory_row=unknown; retain valid coin for per-symbol check')
            continue
        pair = f"{name}/USDT"
        if name and name != "USDT" and usd_value >= Decimal("1") and pair not in selected:
            selected.append(pair)
            print(f"held_pair_included pair={pair} usd_value={usd_value}")
    for pair in candidates:
        base_coin = pair.split("/", 1)[0]
        try:
            balance = bybit.get_unified_coin_wallet_balance(base_coin)
            if not isinstance(balance, Decimal) or not balance.is_finite() or balance < 0:
                raise ValueError('invalid per-symbol inventory quantity')
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
