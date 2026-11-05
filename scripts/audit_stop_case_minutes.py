"""Resource-gated source/first-touch audit of a complete fixed stop case set."""
import argparse,json,hashlib
from datetime import datetime,UTC
from decimal import Decimal
from pathlib import Path
from cryptoforge.research_protocol import prepare_research
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.execution_market_evidence import _load
from cryptoforge.archive import ArchiveReader,download_archive
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.intrabar_source_audit import compare_intrabar_source
from cryptoforge.intrabar_audit import audit_barrier_order
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources

ROOT=Path(__file__).resolve().parents[1]


def candle(raw):
    value={**raw,'open_time':datetime.fromisoformat(raw['open_time']),**{key:Decimal(raw[key]) for key in ('open','high','low','close','volume')}}
    if value.get('cache_observed_at') is not None:value['cache_observed_at']=datetime.fromisoformat(value['cache_observed_at'])
    return CandleRow(**value)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ingestion',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resource-protocol',type=Path,default=Path('config/research-protocol-v1.json'))
    args=parser.parse_args()
    if args.output.exists():parser.error('immutable observed output already exists')
    try:protocol=prepare_research(str(args.resource_protocol))
    except ValueError as exc:
        if any(str(exc).startswith(text) for text in ('insufficient resources:','another offline research worker')):
            status={'observed_at':datetime.now(UTC).isoformat(),'status':'deferred_resource_or_worker_guard','completed':False,'live_promotion_allowed':False}
            write_json_report(args.output.with_name(args.output.stem+'-status.json'),status);print(json.dumps(status));return
        raise
    wrapper=json.loads(args.ingestion.read_bytes());receipt=_load(wrapper['receipt'])
    collector={'downloader':download_archive,'client':BybitPublicClient,'runner':ROOT/'scripts/capture_stop_case_minutes.py'}
    assert_source_dependencies(receipt['implementation_hashes'],collector);load_runtime_sources(receipt['runtime_source_bundle'],receipt['implementation_hashes'])
    if receipt['errors'] or len(receipt['cases'])!=receipt['selected_case_count']:raise ValueError('complete selected ingestion required')
    original_path=Path(receipt['source_report_path']);raw=original_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt['source_report_sha256']:raise ValueError('original source report changed')
    original=json.loads(raw);refs={(sample['pair'],sample['signal_time']):ref for group in original['pairs'] for sample,ref in zip(group['samples'],group['sample_source_references'])}
    samples={(sample['pair'],sample['signal_time']):sample for group in original['pairs'] for sample in group['samples'] if sample['trade']['exit_reason']=='stop'}
    if len(samples)!=receipt['selected_case_count']:raise ValueError('original selected stop coverage changed')
    cfg=original['config']
    if Decimal(cfg['spread_fraction'])!=0:raise ValueError('raw candle first-touch audit requires declared zero spread')
    deps={'compare':compare_intrabar_source,'barrier':audit_barrier_order,'reader':ArchiveReader,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps);runtime=save_runtime_sources(args.output.parent/'stop-case-audit-runtime',deps,hashes)
    now=datetime.now(UTC);results=[];seen=set()
    for case in receipt['cases']:
        sample=case['source_sample'];key=(sample['pair'],sample['signal_time'])
        if key in seen or samples.get(key)!=sample:raise ValueError('unique original paired source cases required')
        seen.add(key)
        path=Path(case['minute_source']['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['mutable_file_sha256']:raise ValueError('minute inputs changed')
        fine=ArchiveReader(path.parent).read_candles(sample['pair'],timeframe='1m',limit=6)
        if len(fine)!=5:raise ValueError('exact five-minute case coverage required')
        coarse=[candle(row) for row in _load(refs[key]['input_reference'])]
        comparison=compare_intrabar_source(fine,coarse,protocol=protocol,as_of=now)
        row=next(row for row in coarse if row.open_time==datetime.fromisoformat(sample['trade']['exit_time']))
        barrier=(audit_barrier_order(row,fine,entry_price=Decimal(sample['trade']['entry_price']),stop_fraction=Decimal(cfg['stop_fraction']),target_fraction=Decimal(cfg['target_fraction']),as_of=now,inspect_unambiguous=True)
                 if comparison['source_consistency_pass'] else None)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['mutable_file_sha256']:
            raise ValueError('minute source changed during comparison')
        assumed=Decimal(sample['trade']['exit_price'])/(1-Decimal(cfg['slippage']))
        results.append({'case_id':case['case_id'],'pair':sample['pair'],'source_consistency':comparison,'first_touch':barrier,
            'five_minute_assumed_raw_exit':str(assumed),'fine_reference_more_adverse':bool(barrier and barrier.get('raw_price') and Decimal(barrier['raw_price'])<assumed-Decimal('1e-20'))})
    assert_source_dependencies(hashes,deps)
    output={'observed_at':now.isoformat(),'cases':results,'completed_cases':len(results),'source_report_sha256':receipt['source_report_sha256'],'original_ingestion_receipt':wrapper['receipt'],
        'resource_protocol':protocol,'resource_protocol_sha256':hashlib.sha256(args.resource_protocol.read_bytes()).hexdigest(),
        'implementation_hashes':hashes,'runtime_source_bundle':runtime,'real_fill_certified':False,'historical_observation_time_certified':False,'trade_policy_changed':False,'live_promotion_allowed':False}
    write_json_report(args.output,output);write_json_report(args.output.with_name(args.output.stem+'-status.json'),{'status':'completed_source_audit','completed':True,'cases':len(results),'live_promotion_allowed':False})
    print(json.dumps({'cases':len(results),'source_matches':sum(result['source_consistency']['source_consistency_pass'] for result in results),'more_adverse_fine_references':sum(result['fine_reference_more_adverse'] for result in results)}))


if __name__=='__main__':main()
