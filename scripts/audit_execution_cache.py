"""Read-only, source-bound replay of saved real fills; no orders or publication."""
import argparse
from dataclasses import asdict
from datetime import UTC,datetime
from decimal import Decimal
import hashlib,json,sqlite3
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.live_trade_journal import reconstruct_trades
import cryptoforge.live_trade_journal as journal
import cryptoforge.execution_identity as identities
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.supabase_market import bybit_symbol_to_pair


def audit_cache(path,output):
    with sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        count=db.execute('select count(*) from executions').fetchone()[0]
        if count>20000:raise ValueError('execution audit requires bounded snapshot')
        fills=[json.loads(row[0]) for row in db.execute('select payload from executions order by exec_id')]
    raw=json.dumps(fills,sort_keys=True,separators=(',',':')).encode()
    sha=hashlib.sha256(raw).hexdigest()
    snapshot=output.parent/'execution-audit-inputs'/f'{sha}.json'
    if snapshot.exists():
        if snapshot.read_bytes()!=raw:raise ValueError('immutable input snapshot changed')
    else:
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        with snapshot.open('xb') as stream:stream.write(raw)
        snapshot.chmod(0o600)
    rows,result=reconstruct_trades(fills)
    closed=[row for row in rows if row['status']=='closed']
    known=[row for row in closed if row['realized_pnl'] is not None]
    pairs={}
    for row in known:
        bucket=pairs.setdefault(row['pair'],{'closed_segments':0,'net_pnl':Decimal(0),'fee_quote_equivalent':Decimal(0),'losses_below_minus_one_percent':0})
        bucket['closed_segments']+=1
        bucket['net_pnl']+=Decimal(row['realized_pnl'])
        bucket['fee_quote_equivalent']+=Decimal(row['fee_amount'])
        bucket['losses_below_minus_one_percent']+=Decimal(row['realized_pnl_pct'])<=Decimal('-.01')
    dependencies={'fifo':reconstruct_trades,'identity':identities.unique_executions,'pair_mapping':bybit_symbol_to_pair,'audit':Path(__file__).resolve()}
    sources=source_hashes(dependencies)
    runtime=save_runtime_sources(output.parent/'execution-audit-runtime',dependencies,sources)
    report={'observed_at':datetime.now(UTC).isoformat(),'input_reference':str(snapshot.resolve()),'input_sha256':sha,'implementation_hashes':sources,'runtime_source_bundle':runtime,
        'summary':asdict(result),'by_pair':pairs,'known_closed_segments':len(known),
        'net_pnl_quote':sum((Decimal(row['realized_pnl']) for row in known),Decimal(0)),
        'open_cost_basis':sum((Decimal(row['stake_amount']) for row in rows if row['status']=='open'),Decimal(0)),
        'current_wallet_verified':False,'segments_may_share_orders':True,'source':'saved_execution_cache_readonly',
        'counts_as_new_real_buys':False,'independent_admission_granted':False,'live_promotion_allowed':False}
    write_json_report(output,report,default=str)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=audit_cache(args.cache,args.output)
    print(json.dumps({key:report[key] for key in ('summary','known_closed_segments','net_pnl_quote','open_cost_basis','input_sha256')},default=str))


if __name__=='__main__':main()
