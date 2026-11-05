"""Match saved missing exit orders to original stdout without remote writes."""
import argparse
import hashlib
import json
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.execution_log_recovery import recover_exit_line
from cryptoforge.live_feedback import analyze_feedback
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources
from datetime import datetime


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log',type=Path,required=True)
    parser.add_argument('--audit-dir',type=Path,required=True)
    parser.add_argument('--missing-evidence-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():raise ValueError('new output directory required')
    candidates={};source_hashes_by_path={}
    for path in sorted(args.missing_evidence_dir.glob('*.json')):
        raw=path.read_bytes();case=json.loads(raw)
        if 'case' not in case:continue
        order_id=case['case']['exit_order']
        orders=[o for o in case['exchange_order_response']['result']['list'] if o['orderId']==order_id]
        if len(orders)!=1:raise ValueError('one exact source order required')
        candidates[order_id]=orders[0]
        source_hashes_by_path[str(path.resolve())]=hashlib.sha256(raw).hexdigest()
    recovered={};captured=[];prefix=hashlib.sha256()
    # Read only the size observed at open; appending by the running executor is safe.
    with args.log.open('rb') as stream:
        remaining=args.log.stat().st_size
        for line_number,raw in enumerate(stream,1):
            if len(raw)>remaining:break
            remaining-=len(raw);prefix.update(raw)
            if not raw.startswith(b'decision=approve_exit '):continue
            line=raw.decode('utf-8')
            for order_id,order in candidates.items():
                if order_id not in line:continue
                row=recover_exit_line(line,order,source=str(args.log.resolve()),line_number=line_number)
                if order_id in recovered and recovered[order_id]['reasons']!=row['reasons']:
                    raise ValueError('conflicting original log reasons')
                recovered[order_id]=row
                captured.append({'line_number':line_number,'raw_line':line})
            if remaining==0:break
    args.output_dir.mkdir(parents=True,mode=0o700)
    base_path=args.audit_dir/'decision-rows.json';base=json.loads(base_path.read_text())
    rows=base+list(recovered.values())
    trades_path=args.audit_dir/'trades.json';trades=json.loads(trades_path.read_text())
    as_of=json.loads((args.audit_dir/'feedback.json').read_text())['as_of']
    feedback=analyze_feedback(trades,rows,as_of=datetime.fromisoformat(as_of))
    write_json_report(args.output_dir/'decision-rows.json',rows)
    write_json_report(args.output_dir/'recovered-decisions.json',list(recovered.values()))
    write_json_report(args.output_dir/'source-lines.json',captured)
    write_json_report(args.output_dir/'feedback.json',feedback,default=str)
    deps={'recovery':recover_exit_line,'runner':Path(__file__).resolve(),'feedback':analyze_feedback}
    hashes=source_hashes(deps)
    report={'recovered_exit_orders':sorted(recovered),'still_missing_exit_orders':sorted(set(candidates)-set(recovered)),
        'exact_bot_exit_matches':sum(o['exit_controlled_by_bot'] and o['exit_context_match']=='exact_order' for o in feedback['outcomes']),
        'bot_exit_orders':sum(o['exit_controlled_by_bot'] for o in feedback['outcomes']),
        'source_log_prefix_sha256':prefix.hexdigest(),'source_hashes':source_hashes_by_path,
        'base_decisions_sha256':hashlib.sha256(base_path.read_bytes()).hexdigest(),
        'trades_sha256':hashlib.sha256(trades_path.read_bytes()).hexdigest(),
        'implementation_hashes':hashes,'runtime_source_bundle':save_runtime_sources(args.output_dir/'runtime',deps,hashes),
        'remote_writes':False,'orders_placed':False,'original_decision_timestamps_recovered':False,
        'original_model_features_recovered':False}
    write_json_report(args.output_dir/'report.json',report)
    print(json.dumps({k:report[k] for k in ('exact_bot_exit_matches','bot_exit_orders','recovered_exit_orders','still_missing_exit_orders')}))


if __name__=='__main__':main()
