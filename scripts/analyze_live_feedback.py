"""Execution-based feedback report, read-only; never modifies trading policies."""
import argparse
from datetime import datetime,UTC
import json
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.live_feedback import LiveFeedbackReader
from cryptoforge.feedback_memory import remember_report
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.live_trade_journal import default_cache_path
from cryptoforge.inventory_audit import verify_inventory
import sqlite3
from cryptoforge.supabase_market import SupabaseRestClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lookback-days',type=int,default=14)
    parser.add_argument('--as-of')
    parser.add_argument('--output',type=Path,default=Path('.local/state/live-feedback.json'))
    args=parser.parse_args()
    if not 1<=args.lookback_days<=90:parser.error('lookback-days must be between 1 and 90')
    at=datetime.fromisoformat(args.as_of.replace('Z','+00:00')) if args.as_of else datetime.now(UTC)
    if at.tzinfo is None:parser.error('timezone-aware as-of required')
    report=LiveFeedbackReader(SupabaseRestClient.from_env(timeout_seconds=25)).read(as_of=at,lookback_days=args.lookback_days)
    try:
        bybit=BybitPrivateClient.from_env()
        cache=default_cache_path(bybit)
        db=sqlite3.connect('file:'+str(cache.resolve())+'?mode=ro',uri=True)
        try:
            fills=[json.loads(r[0]) for r in db.execute('select payload from executions')]
            transactions=[json.loads(r[0]) for r in db.execute('select payload from account_transactions')]
        finally:db.close()
        inventory=verify_inventory(fills,transactions,bybit.get_unified_wallet_coins())
        report['inventory_audit']=inventory
        report['accounting_quality_verified']=report['accounting_quality_verified'] and inventory['consistent']
    except Exception as exc:
        report['inventory_audit']={'consistent':False,'error':type(exc).__name__}
        report['accounting_quality_verified']=False
    report['memory']=remember_report(report,args.output.parent/'feedback-memory.sqlite')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json_report(args.output,report,default=str)
    print(json.dumps({'as_of':report['as_of'],'today':report['today'],'summary':report['summary'],
                      'hypotheses':report['hypotheses'],'output':str(args.output.resolve())},default=str),flush=True)


if __name__=='__main__':main()
