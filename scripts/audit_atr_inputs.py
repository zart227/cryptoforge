"""Resource-gated development input audit; no search, fitting, publication or orders."""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,UTC,timedelta
from cryptoforge.archive import ArchiveReader
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.entry_risk import atr_entry_risk
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import source_hashes


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('.local/state/atr-entry-risk-input-audit.json'))
    args=parser.parse_args(argv)
    status_path=args.output.with_name(args.output.stem+'-status.json')
    now=datetime.now(UTC)
    try:protocol=prepare_research()
    except ValueError as exc:
        if str(exc).startswith(('insufficient resources:','another offline research worker')):
            result={'observed_at':now.isoformat(),'status':'deferred_by_resource_or_worker_guard','completed':False,'fit_performed':False,'orders_allowed':False}
            write_json_report(status_path,result);print(json.dumps(result));return 0
        raise
    from cryptoforge.candle_contract import known_closed
    dependencies={'entry_risk':atr_entry_risk,'candle_contract':known_closed,'archive':ArchiveReader,
        'audit_runner':Path(__file__),'research_guard':prepare_research,'source_hash_dependency':source_hashes}
    hashes=source_hashes(dependencies)
    identity=hashlib.sha256(json.dumps({'protocol':protocol,'sources':hashes,'input_policy':'tail2000_first1400_every14_v1'},sort_keys=True).encode()).hexdigest()
    if args.output.exists():
        prior=json.loads(args.output.read_bytes())
        if prior.get('audit_identity')==identity and prior.get('status')=='completed_input_audit':
            result={'observed_at':now.isoformat(),'status':'original_completed_audit_preserved','completed':True,'audit_identity':identity,'fit_performed':False,'orders_allowed':False}
            write_json_report(status_path,result);print(json.dumps(result));return 0
    cases=[]
    for pair in protocol['baseline_pairs']:
        dataset=next(row for row in protocol['datasets'] if row['pair']==pair)
        rows=ArchiveReader(Path(dataset['path']).parent,protocol=protocol).read_candles(pair,limit=2000)[:1400]
        if len(rows)!=1400:raise ValueError('complete declared ATR audit slice required')
        plans=[]
        for index in range(14,len(rows)-1,14):
            plan=atr_entry_risk(rows,index,as_of=rows[index].open_time+timedelta(minutes=5))
            if plan.information_available_at>rows[index+1].open_time:raise ValueError('risk plan unavailable at next open')
            plans.append(plan)
        cases.append({'pair':pair,'input_cases_checked':len(plans),'unavailable_at_next_open':0,
            'start':rows[0].open_time.isoformat(),'end':rows[-1].open_time.isoformat(),
            'minimum_stop':str(min(plan.stop_fraction for plan in plans)),
            'maximum_stop':str(max(plan.stop_fraction for plan in plans)),
            'minimum_target':str(min(plan.target_fraction for plan in plans)),
            'maximum_target':str(max(plan.target_fraction for plan in plans))})
    if hashes!=source_hashes(dependencies):raise ValueError('ATR audit source changed during calculation')
    result={'observed_at':datetime.now(UTC).isoformat(),'status':'completed_input_audit','audit_identity':identity,
        'source_hashes':hashes,'datasets':protocol['datasets'],'cases':cases,'development_only':True,
        'historical_observation_times_certified':False,'strategy_outcomes_evaluated':False,'fit_performed':False,'orders_allowed':False}
    write_json_report(args.output,result)
    write_json_report(status_path,{'observed_at':result['observed_at'],'status':'completed_input_audit','completed':True,'audit_identity':identity,'fit_performed':False,'orders_allowed':False})
    print(json.dumps({'status':result['status'],'cases':cases,'fit_performed':False,'orders_allowed':False}));return 0


if __name__=='__main__':raise SystemExit(main())
