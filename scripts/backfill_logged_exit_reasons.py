"""Insert verified original log reasons under immutable order keys; no orders."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.execution_log_recovery import recover_exit_line
from cryptoforge.live_feedback import LiveFeedbackReader
from cryptoforge.supabase_market import SupabaseRestClient
try:
    from scripts.windows_background_runner import load_environment
except ModuleNotFoundError:
    from windows_background_runner import load_environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery-dir',type=Path,required=True)
    parser.add_argument('--missing-evidence-dir',type=Path,required=True)
    args=parser.parse_args()
    receipt=args.recovery_dir/'database-backfill.json'
    if receipt.exists():raise ValueError('backfill receipt exists; verify it before another write')
    report=json.loads((args.recovery_dir/'report.json').read_text())
    sources=json.loads((args.recovery_dir/'source-lines.json').read_text())
    recovered=json.loads((args.recovery_dir/'recovered-decisions.json').read_text())
    payload=[]
    for record in recovered:
        order_id=record['features']['order']['result']['orderId']
        path=args.missing_evidence_dir/(order_id+'.json')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=report['source_hashes'][str(path.resolve())]:
            raise ValueError('exchange evidence changed')
        evidence=json.loads(raw)
        exchange=[o for o in evidence['exchange_order_response']['result']['list'] if o['orderId']==order_id]
        lines=[s for s in sources if s['line_number']==record['features']['source_line']]
        if len(exchange)!=1 or len(lines)!=1:raise ValueError('unique original source required')
        replay=recover_exit_line(lines[0]['raw_line'],exchange[0],source=record['features']['source_log'],line_number=lines[0]['line_number'])
        if replay!=record:raise ValueError('recovered record differs from original line replay')
        # These configuration fields are stable in every nearby source row.
        for field in ('timeframe','strategy_name','strategy_version'):
            values={r[field] for r in evidence['nearby_decisions']}
            if len(values)!=1:raise ValueError('ambiguous original strategy metadata')
            record[field]=values.pop()
        payload.append(record)
    if not payload:raise ValueError('nonempty verified recovery required')
    load_environment(Path('.env'))
    client=SupabaseRestClient.from_env(timeout_seconds=15);reader=LiveFeedbackReader(client)
    filters={'idempotency_key':'in.('+','.join(r['idempotency_key'] for r in payload)+')','select':'*'}
    before,truncated=reader._rows('trade_decisions',filters)
    if truncated:raise ValueError('truncated preflight')
    expected={r['idempotency_key']:r for r in payload}
    for row in before:
        if row['reasons']!=expected[row['idempotency_key']]['reasons']:
            raise ValueError('existing order context conflicts; no overwrite permitted')
    write_json_report(args.recovery_dir/'backfill-payload.json',payload)
    client.upsert('trade_decisions',payload,on_conflict='idempotency_key',resolution='ignore-duplicates')
    after,truncated=reader._rows('trade_decisions',filters)
    if truncated or len(after)!=len(payload):raise ValueError('backfill readback incomplete')
    for row in after:
        want=expected[row['idempotency_key']]
        if any(row[field]!=want[field] for field in ('reasons','features','decision','pair')):
            raise ValueError('backfill readback differs from original evidence')
    write_json_report(receipt,{'observed_at':datetime.now(UTC).isoformat(),'previous_rows':len(before),
        'verified_rows':len(after),'idempotency_keys':list(expected),
        'payload_sha256':hashlib.sha256((args.recovery_dir/'backfill-payload.json').read_bytes()).hexdigest(),
        'old_candle_records_modified':False,'orders_placed':False,'readback_verified':True})
    print(json.dumps({'verified_rows':len(after),'previous_rows':len(before),'readback_verified':True}))


if __name__=='__main__':main()
