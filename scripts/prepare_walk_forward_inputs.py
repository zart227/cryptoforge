"""Bind original train/validation candles without reading future test history."""
import argparse,hashlib,json,sqlite3
from pathlib import Path
from datetime import datetime,UTC,timedelta
from cryptoforge.walk_forward_inputs import validate_source_rows,load_bound_candles
from cryptoforge.archive import download_archive
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.research_protocol import prepare_research
from cryptoforge.research_attempts import identity,encoded
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw
from cryptoforge.immutable_files import install_original
from cryptoforge.atomic_reports import write_json_report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--fold',type=int,default=0);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--database',type=Path,default=Path('.local/archive-stage1/historical-universe-20251001.sqlite'))
    args=parser.parse_args()
    if args.output.exists():parser.error('immutable original input binding already exists')
    prepare_research('config/research-resources-user-1024-20261014.json')
    plan_raw=args.plan.read_bytes();plan=json.loads(plan_raw)
    studies=[study for study in plan['studies'] if study['manifest']['fold_index']==args.fold]
    if len(studies)!=2:raise ValueError('both original heads for one fold required')
    with sqlite3.connect('file:.local/state/research-attempts.sqlite?mode=ro',uri=True) as db:
        for study in studies:
            stored=db.execute('select payload from studies where id=?',(study['study_sha256'],)).fetchone()
            if not stored or stored[0]!=encoded(study['manifest']) or identity(study['manifest'])!=study['study_sha256']:
                raise ValueError('original registered validation studies required')
    first=studies[0]['manifest'];fold=first['fold'];policy=first['selection_policy']
    if studies[1]['manifest']['selection_policy']!=policy:raise ValueError('same validation boundaries required')
    now=datetime.now(UTC);end=datetime.fromisoformat(policy['validation_end'])
    if now<end:raise ValueError('validation window remains unfinished')
    start=datetime.fromisoformat(fold['train_start'])-timedelta(minutes=600)
    start_ms=int(start.timestamp()*1000);end_ms=int(end.timestamp()*1000)
    deps={'validator':validate_source_rows,'loader':load_bound_candles,'download':download_archive,'client':BybitPublicClient,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps);runtime=save_runtime_sources(args.output.parent/'runtime',deps,hashes)
    design={'observed_at':now.isoformat(),'plan_sha256':hashlib.sha256(plan_raw).hexdigest(),'fold_index':args.fold,
        'study_sha256s':[study['study_sha256'] for study in studies],'start_ms':start_ms,'end_ms_exclusive':end_ms,
        'pairs':['BTC/USDT','ETH/USDT'],'prefix_bars_before_train':120,'missing_tail_policy':'public_spot_5m_only',
        'test_candles_included':False,'implementation_hashes':hashes,'runtime_source_bundle':runtime}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    install_original(args.output.with_name('input-design.json'),(json.dumps(design,sort_keys=True,indent=2)+'\n').encode())
    client=BybitPublicClient(timeout=2,max_retries=0);sources={}
    with sqlite3.connect('file:'+str(args.database.resolve())+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        for pair in design['pairs']:
            symbol=pair.replace('/','')
            rows=list(db.execute("select * from candles where symbol=? and interval='5' and start_ms>=? and start_ms<? order by start_ms",(symbol,start_ms,end_ms)))
            tail=rows[-1][2]+300000 if rows else start_ms;capture=None
            if tail<end_ms:
                capture=download_archive(client,symbol,'5',tail,end_ms,args.output.parent/'tail-sources'/symbol,pause=0)
                raw=json.loads(Path(capture['snapshot_path']).read_bytes())
                if hashlib.sha256(Path(capture['snapshot_path']).read_bytes()).hexdigest()!=capture['sha256']:raise ValueError('original tail snapshot changed')
                rows.extend((row['symbol'],row['interval'],row['start_ms'],row['open'],row['high'],row['low'],row['close'],row['volume'],row['turnover']) for row in raw)
            validate_source_rows(rows,symbol,start_ms,end_ms)
            chunks=[_save_raw(args.output.parent/'chunks',json.dumps(rows[index:index+1000],separators=(',',':')).encode()) for index in range(0,len(rows),1000)]
            sources[pair]={'candles':len(rows),'chunks':chunks,'public_tail_capture':capture}
    assert_source_dependencies(hashes,deps)
    result={**design,'completed_at':datetime.now(UTC).isoformat(),'input_design_sha256':hashlib.sha256(args.output.with_name('input-design.json').read_bytes()).hexdigest(),
        'pairs':sources,'historical_observation_times_certified':False,'historical_market_rules_certified':False,'live_promotion_allowed':False}
    write_json_report(args.output,result)
    print(json.dumps({'fold_index':args.fold,'candles':{pair:source['candles'] for pair,source in sources.items()},'test_candles_included':False}))


if __name__=='__main__':main()
