"""Stream fixed barrier geometries from development OHLCV; no strategy search."""
import argparse,hashlib,json,sqlite3
from decimal import Decimal
from pathlib import Path
from datetime import datetime,UTC
from cryptoforge.research_protocol import prepare_research
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw


def geometry(row,previous):
    opened,high,low=(Decimal(row[i]) for i in (3,4,5))
    if not all(value.is_finite() and value>0 for value in (opened,high,low)):
        raise ValueError('finite positive source prices required')
    categories=[]
    if low<=opened*Decimal('.98') and high>=opened*Decimal('1.04'):
        categories.append('both_barriers_from_bar_open')
    if previous and previous[0]==row[0] and row[2]-previous[2]==300000:
        close=Decimal(previous[6])
        if opened<=close*Decimal('.98'):categories.append('opening_drop_at_least_two_percent')
    return categories


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=Path('.local/archive-stage1/historical-universe-20251001.sqlite'))
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('immutable edge scan already exists')
    protocol=prepare_research('config/research-resources-user-1024-20261014.json')
    end=datetime(2026,10,1,tzinfo=UTC)
    if end>datetime.fromisoformat(protocol['data_policy']['development_end']):raise ValueError('development-only range required')
    deps={'geometry':geometry,'runner':Path(__file__).resolve()};hashes=source_hashes(deps)
    runtime=save_runtime_sources(args.output.parent/'edge-scan-runtime',deps,hashes)
    counts={};samples={};previous=None;digest=hashlib.sha256();total=0;first=last=None
    with sqlite3.connect('file:'+str(args.database.resolve())+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        cursor=db.execute("SELECT * FROM candles WHERE interval='5' AND start_ms<? ORDER BY symbol,start_ms",(int(end.timestamp()*1000),))
        for row in cursor:
            total+=1
            if total>3000000:raise ValueError('bounded three-million-row scan required')
            digest.update((json.dumps(row,separators=(',',':'))+'\n').encode())
            first=row[2] if first is None else min(first,row[2]);last=row[2] if last is None else max(last,row[2])
            for category in geometry(row,previous):
                counts[category]=counts.get(category,0)+1;cases=samples.setdefault(category,[])
                if len(cases)<20:
                    reference=_save_raw(args.output.parent/'edge-scan-inputs',json.dumps({'columns':['symbol','interval','start_ms','open','high','low','close','volume','turnover'],
                        'previous_row':previous if previous and previous[0]==row[0] else None,'row':row},sort_keys=True).encode())
                    cases.append({'symbol':row[0],'open_time':datetime.fromtimestamp(row[2]/1000,UTC).isoformat(),'input_snapshot':reference})
            previous=row
    assert_source_dependencies(hashes,deps)
    result={'observed_at':datetime.now(UTC).isoformat(),'database':str(args.database.resolve()),'rows_scanned':total,
        'source_stream_sha256':digest.hexdigest(),'first_ms':first,'last_ms':last,'end_exclusive':end.isoformat(),
        'query':"interval=5,start_ms<2026-10-01UTC,order=symbol/start_ms",'counts':counts,'first_twenty_per_category':samples,
        'stop_fraction':'0.02','target_fraction':'0.04','resource_protocol':protocol,'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'source_geometry_only':True,'actual_strategy_signal_verified':False,'real_fill_certified':False,'profitability_established':False,'live_promotion_allowed':False}
    write_json_report(args.output,result);print(json.dumps({'rows':total,'counts':counts}))


if __name__=='__main__':main()
