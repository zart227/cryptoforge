"""Inspect the preselected first twenty source geometries with current minute history."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,UTC
from decimal import Decimal
from cryptoforge.research_protocol import prepare_research
from cryptoforge.execution_market_evidence import _load
from cryptoforge.archive import download_archive,ArchiveReader
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.intrabar_source_audit import compare_intrabar_source
from cryptoforge.intrabar_audit import audit_barrier_order
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources,save_runtime_sources
from cryptoforge.atomic_reports import write_json_report
from scripts.find_archive_edge_cases import geometry


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--scan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('immutable source inspection already exists')
    protocol=prepare_research('config/research-resources-user-1024-20261014.json')
    raw=args.scan.read_bytes();scan=json.loads(raw)
    originaldeps={'geometry':geometry,'runner':Path(__file__).with_name('find_archive_edge_cases.py').resolve()}
    assert_source_dependencies(scan['implementation_hashes'],originaldeps);load_runtime_sources(scan['runtime_source_bundle'],scan['implementation_hashes'])
    cases=scan['first_twenty_per_category']['both_barriers_from_bar_open']
    if len(cases)!=20:raise ValueError('complete original first twenty selection required')
    deps={'client':BybitPublicClient,'download':download_archive,'reader':ArchiveReader,'compare':compare_intrabar_source,
          'barrier':audit_barrier_order,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps);runtime=save_runtime_sources(args.output.parent/'ambiguous-minute-runtime',deps,hashes)
    client=BybitPublicClient(timeout=2,max_retries=0);results=[]
    directory=args.output.parent/'ambiguous-minute-inputs'/hashlib.sha256(raw).hexdigest()
    for index,case in enumerate(cases):
        item={'source_case':case,'completed':False}
        try:
            source=_load(case['input_snapshot']);row=source['row'];start=row[2];end=start+300000
            captured=download_archive(client,row[0],'1',start,end,directory/str(index),pause=0)
            item['minute_capture']=captured
            fine=ArchiveReader(directory/str(index)).read_candles(row[0][:-4]+'/USDT',timeframe='1m',limit=6)
            if len(fine)!=5:raise ValueError('complete original minute interval required')
            coarse=CandleRow(pair=row[0][:-4]+'/USDT',symbol=row[0],open_time=datetime.fromtimestamp(start/1000,UTC),
                open=Decimal(row[3]),high=Decimal(row[4]),low=Decimal(row[5]),close=Decimal(row[6]),volume=Decimal(row[7]),
                cache_observed_at=datetime.fromisoformat(scan['observed_at']))
            now=datetime.now(UTC);comparison=compare_intrabar_source(fine,[coarse],protocol=protocol,as_of=now)
            item['source_consistency']=comparison
            item['first_touch']=audit_barrier_order(coarse,fine,entry_price=coarse.open,stop_fraction=Decimal('.02'),target_fraction=Decimal('.04'),as_of=now) if comparison['source_consistency_pass'] else None
            item['completed']=True
        except Exception as exc:item['error_class']=type(exc).__name__
        results.append(item)
    assert_source_dependencies(hashes,deps)
    report={'observed_at':datetime.now(UTC).isoformat(),'original_scan_sha256':hashlib.sha256(raw).hexdigest(),
        'cases':results,'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'selected_cases':20,'completed_cases':sum(row['completed'] for row in results),
        'source_geometry_only':True,'actual_strategy_signal_verified':False,'historical_observation_time_certified':False,'live_promotion_allowed':False}
    write_json_report(args.output,report)
    print(json.dumps({'completed':report['completed_cases'],'source_matches':sum(row.get('source_consistency',{}).get('source_consistency_pass',False) for row in results)}))


if __name__=='__main__':main()
