"""Fetch fresh Bybit accounting evidence without orders or remote publication.

The existing cache is read only. Every seven-day window is reread from its
original boundary; an empty response cannot silently delete cached executions.
"""
import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.conversion_journal import conversion_fills
from cryptoforge.execution_identity import unique_executions
from cryptoforge.inventory_audit import verify_inventory
from cryptoforge.live_trade_journal import DAY_MS, default_cache_path, reconstruct_trades
from cryptoforge.live_feedback import analyze_feedback
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources


def reconcile(client, cache, output, *, now=None, decisions=None):
    if output.exists():
        raise ValueError('use a new evidence directory')
    if cache.resolve() != default_cache_path(client).resolve():
        raise ValueError('cache does not match configured API key')
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError('timezone-aware observation required')
    with sqlite3.connect('file:' + str(cache.resolve()) + '?mode=ro', uri=True) as db:
        db.execute('BEGIN')
        state = db.execute('select start_ms,cursor_ms from journal_state where id=1').fetchone()
        cached = [json.loads(r[0]) for r in db.execute('select payload from executions order by exec_id')]
    if not state or not 0 <= state[0] <= int(now.timestamp()*1000):
        raise ValueError('valid original history boundary required')
    if int(now.timestamp()*1000)-state[0] > 180*DAY_MS:
        raise ValueError('history audit limited to 180 days')
    output.mkdir(parents=True, mode=0o700)
    dependencies = {'runner': Path(__file__).resolve(), 'fifo': reconstruct_trades,
                    'identity': unique_executions, 'inventory': verify_inventory,
                    'conversions': conversion_fills, 'feedback': analyze_feedback,
                    'bybit': BybitPrivateClient}
    hashes = source_hashes(dependencies)
    evidence = {'query_started_at': datetime.now(UTC).isoformat(),
                'history_start_ms': state[0], 'history_end_ms': int(now.timestamp()*1000),
                'account_key_sha256': hashlib.sha256(client.api_key.encode()).hexdigest(),
                'cached_executions': cached, 'windows': [], 'normalized_wallet': [],
                'decisions': decisions or []}
    report = {'status': 'incomplete', 'orders_placed': False, 'remote_writes': False,
              'historical_completeness_certified': False, 'original_cache_modified': False,
              'implementation_hashes': hashes,
              'runtime_source_bundle': save_runtime_sources(output/'runtime', dependencies, hashes)}
    try:
        start = state[0]
        fills, transactions, conversions = [], [], []
        while start <= evidence['history_end_ms']:
            end = min(start+7*DAY_MS-1, evidence['history_end_ms'])
            window = {'start_ms': start, 'end_ms': end}
            evidence['windows'].append(window)
            window['executions'] = client.get_spot_executions(start_ms=start, end_ms=end)
            window['transactions'] = client.get_unified_transactions(start_ms=start, end_ms=end)
            window['conversions'] = client.get_small_conversion_history(start_ms=start, end_ms=end)
            for fill in window['executions']:
                if not fill.get('execId') or not start <= int(fill['execTime']) <= end:
                    raise ValueError('exchange returned invalid execution identity or time')
            fills.extend(window['executions'])
            transactions.extend(window['transactions'])
            conversions.extend(window['conversions'])
            start = end+1
        fills = unique_executions(fills)
        # Fail on changed immutable identities, even when inventory still matches.
        unique_executions(cached + fills)
        old = {str(f['execId']) for f in cached if not str(f['execId']).startswith('conversion:')}
        fresh = {str(f['execId']) for f in fills}
        conversion_rows = {}
        for row in conversions:
            key = str(row['exchangeTxId'])
            if key in conversion_rows and conversion_rows[key] != row:
                raise ValueError('conflicting conversion identity')
            conversion_rows[key] = row
        tx_rows = {}
        for row in transactions:
            key = str(row['id'])
            if key in tx_rows and tx_rows[key] != row:
                raise ValueError('conflicting transaction identity')
            tx_rows[key] = row
        transactions = list(tx_rows.values())
        events = conversion_fills(list(conversion_rows.values()), transactions)
        all_fills = unique_executions(fills + events)
        unique_executions(cached + all_fills)
        missing_accounting = sorted({str(f['execId']) for f in cached}
                                    - {str(f['execId']) for f in all_fills})
        coins = sorted({f['symbol'][:-4] for f in fills
                        if str(f.get('orderLinkId') or '').startswith('cf-')
                        and f['symbol'].endswith('USDT')})
        evidence['normalized_wallet'] = client.get_unified_wallet_coins_for(coins) if coins else []
        inventory = verify_inventory(all_fills, transactions, evidence['normalized_wallet'])
        rows, summary = reconstruct_trades(all_fills)
        covered = {e['sourceDebitId'] for e in events}
        unknown = [t['id'] for t in transactions if t.get('currency') in coins
                   and t.get('type') != 'TRADE' and Decimal(str(t.get('change') or 0)) != 0
                   and t['id'] not in covered]
        missing = sorted(old-fresh)
        closed = [r for r in rows if r['status'] == 'closed']
        feedback = analyze_feedback(rows, decisions or [], as_of=now)
        write_json_report(output/'trades.json', rows)
        write_json_report(output/'feedback.json', feedback, default=str)
        report.update(status='reconciled' if not missing_accounting and inventory['consistent'] and not unknown
                      and not summary.unmatched_sells and not summary.incomplete_fees else 'discrepancy',
                      summary=asdict(summary), inventory=inventory,
                      new_execution_ids=sorted(fresh-old), missing_cached_execution_ids=missing,
                      missing_cached_accounting_ids=missing_accounting,
                      unmodeled_movement_ids=unknown,
                      net_pnl_quote=str(sum((Decimal(r['realized_pnl']) for r in closed
                                             if r['realized_pnl'] is not None), Decimal(0))),
                      latest_execution_ms=max((int(f['execTime']) for f in fills), default=None),
                      original_cursor_ms=state[1], decision_rows_supplied=len(decisions or []),
                      exact_entry_cost_coverage_fraction=feedback['exact_entry_cost_coverage_fraction'],
                      exact_exit_order_matches=sum(r['exit_context_match'] == 'exact_order'
                                                   for r in feedback['outcomes']),
                      outcome_orders=len(feedback['outcomes']),
                      wallet_and_history_atomic_snapshot=False,
                      strategy_attribution_complete=False)
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        raise
    finally:
        evidence['query_finished_at'] = datetime.now(UTC).isoformat()
        write_json_report(output/'inputs.json', evidence, default=str)
        report['input_sha256'] = hashlib.sha256((output/'inputs.json').read_bytes()).hexdigest()
        report['observed_at'] = evidence['query_finished_at']
        write_json_report(output/'report.json', report, default=str)
    return report


def load_env():
    for line in Path('.env').read_text().splitlines():
        key, sep, value = line.partition('=')
        key = key.strip().removeprefix('export ')
        if sep and key in {'BYBIT_API_KEY', 'BYBIT_API_SECRET'}:
            values = shlex.split(value, comments=True)
            if len(values) == 1:
                os.environ.setdefault(key, values[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--decisions', type=Path, help='Saved exact order decision rows (JSON list)')
    args = parser.parse_args()
    load_env()
    client = BybitPrivateClient.from_env()
    client.timeout_seconds = 15
    client.synchronize_time(max_attempts=1)
    result = reconcile(client, default_cache_path(client), args.output,
                       decisions=json.loads(args.decisions.read_text()) if args.decisions else None)
    print(json.dumps(result, default=str))
    return 0 if result['status'] == 'reconciled' else 1


if __name__ == '__main__':
    raise SystemExit(main())
