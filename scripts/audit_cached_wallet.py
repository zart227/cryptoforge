"""Capture explicit current balances and reconcile a read-only execution cache."""
import argparse
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.inventory_audit import verify_inventory
from cryptoforge.execution_identity import unique_executions
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.source_contract import source_hashes, assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources, _save_raw


def audit(client, cache, output):
    if output.exists():raise ValueError('immutable wallet audit already exists')
    with sqlite3.connect('file:'+str(cache.resolve())+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        count=db.execute('select count(*) from executions').fetchone()[0]
        tx_count=db.execute('select count(*) from account_transactions').fetchone()[0]
        if count>20000 or tx_count>40000:raise ValueError('bounded cached accounting snapshot required')
        fills=[json.loads(row[0]) for row in db.execute('select payload from executions order by exec_id')]
        transactions=[json.loads(row[0]) for row in db.execute('select payload from account_transactions')]
    fills=unique_executions(fills)
    coins=sorted({str(row['symbol'])[:-4] for row in fills if row.get('execType','Trade')=='Trade'
        and str(row.get('symbol','')).endswith('USDT') and str(row.get('orderLinkId') or '').startswith('cf-')})
    deps={'wallet':BybitPrivateClient,'inventory':verify_inventory,'identity':unique_executions,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps)
    started=datetime.now(UTC)
    wallet=client.get_unified_wallet_coins_for(coins) if coins else []
    observed=datetime.now(UTC)
    result=verify_inventory(fills,transactions,wallet)
    # These are adapter-returned balances, not raw HTTP transport receipts.
    inputs={'fills':fills,'transactions':transactions,'normalized_wallet_coins':wallet,
            'requested_coins':coins,'query_started_at':started.isoformat(),'query_finished_at':observed.isoformat()}
    raw=json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()
    ref=_save_raw(output.parent/'wallet-audit-inputs',raw)
    report={'observed_at':observed.isoformat(),'account_scope':hashlib.sha256(client.api_key.encode()).hexdigest(),
        'inventory_audit':result,'input_reference':ref,'implementation_hashes':hashes,
        'runtime_source_bundle':save_runtime_sources(output.parent/'wallet-audit-runtime',deps,hashes),
        'cached_history_freshness_verified':False,'wallet_scope':'explicit_current_tracked_base_balances',
        'raw_http_response_preserved':False,'historical_fills_complete_certified':False,
        'live_promotion_allowed':False,'orders_placed':False}
    assert_source_dependencies(hashes,deps)
    write_json_report(output,report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for line in Path('.env').read_text().splitlines():
        key,sep,value=line.partition('=');key=key.strip().removeprefix('export ')
        if sep and key in {'BYBIT_API_KEY','BYBIT_API_SECRET'}:
            values=shlex.split(value,comments=True)
            if len(values)==1:os.environ.setdefault(key,values[0])
    client=BybitPrivateClient.from_env();client.timeout_seconds=2;client.synchronize_time(max_attempts=1)
    report=audit(client,args.cache,args.output)
    print(json.dumps({'consistent':report['inventory_audit']['consistent'],'tracked_coins':len(report['inventory_audit']['coins']),
        'unknown_wallet_coins':sum(row['wallet_inventory'] is None for row in report['inventory_audit']['coins'])}))


if __name__=='__main__':main()
