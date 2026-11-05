"""Bounded public minute-source ingestion for existing audited stop cases."""
import argparse,hashlib,json,shutil
from datetime import datetime,UTC,timedelta
from pathlib import Path
from cryptoforge.archive import download_archive
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.research_protocol import assert_development_range
from cryptoforge.source_contract import net_research_sources,source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources,_save_raw
from cryptoforge.research_attempts import identity
from cryptoforge.atomic_reports import write_json_report

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if args.report.stat().st_size>5*1024**2:parser.error('bounded source audit required')
    raw=args.report.read_bytes();source_sha=hashlib.sha256(raw).hexdigest();report=json.loads(raw)
    deps=net_research_sources('label_builder',build_trade_labels,runner=ROOT/'scripts/audit_trade_labels.py')
    assert_source_dependencies(report['implementation_hashes'],deps)
    load_runtime_sources(report['runtime_source_bundle'],report['implementation_hashes'])
    selected=[sample for group in report['pairs'] for sample in group['samples'] if sample['trade']['exit_reason']=='stop']
    if not selected or len(selected)>40:parser.error('bounded existing stop case set required')
    if shutil.disk_usage('.').free<(2048+2)*1024**2:print(json.dumps({'status':'deferred_disk_reserve'}));return
    directory=ROOT/'.local/intrabar-stop-cases'/source_sha
    collector={'downloader':download_archive,'client':BybitPublicClient,'runner':Path(__file__).resolve()}
    hashes=source_hashes(collector);runtime=save_runtime_sources(directory/'runtime',collector,hashes)
    protocol=json.loads((ROOT/'config/research-protocol-v1.json').read_bytes())
    client=BybitPublicClient(timeout=2,max_retries=0);cases=[];errors={}
    for sample in selected:
        case_id=identity({'pair':sample['pair'],'signal_time':sample['signal_time'],'exit_time':sample['trade']['exit_time']})
        try:
            start=datetime.fromisoformat(sample['trade']['exit_time']);end=start+timedelta(minutes=5)
            assert_development_range(protocol,start,end)
            if end>datetime.now(UTC):raise ValueError('historical closed source range required')
            result=download_archive(client,sample['pair'].replace('/',''),'1',int(start.timestamp()*1000),int(end.timestamp()*1000),directory/case_id,pause=0)
            file_sha=hashlib.sha256(Path(result['path']).read_bytes()).hexdigest()
            cases.append({'case_id':case_id,'pair':sample['pair'],'source_sample':sample,'minute_source':result,
                'mutable_file_sha256':file_sha,'complete_minute_source':result['candles']==5 and not result['missing_candles']})
        except Exception as exc:errors[case_id]=type(exc).__name__
    payload={'source_report_path':str(args.report.resolve()),'source_report_sha256':source_sha,'observed_at':datetime.now(UTC).isoformat(),
        'selected_case_count':len(selected),'cases':cases,'errors':errors,'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'stage':'public_data_ingestion_only','source_consistency_audit_completed':False,'historical_observation_time_certified':False,
        'real_fill_certified':False,'live_promotion_allowed':False}
    reference=_save_raw(directory/'receipts',json.dumps(payload,sort_keys=True,separators=(',',':')).encode())
    write_json_report(directory/'latest-ingestion.json',{'receipt':reference,'complete_cases':sum(case['complete_minute_source'] for case in cases),'errors':errors})
    print(json.dumps({'selected_cases':len(selected),'complete_cases':sum(case['complete_minute_source'] for case in cases),'errors':errors,'receipt':reference}))


if __name__=='__main__':main()
