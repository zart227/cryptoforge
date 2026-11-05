"""Audit full counterfactual trade labels for the fixed source-geometry case set."""
import argparse,hashlib,json,sqlite3
from dataclasses import asdict
from datetime import datetime,UTC,timedelta
from decimal import Decimal
from pathlib import Path
from cryptoforge.execution_market_evidence import _load
from cryptoforge.research_protocol import prepare_research
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.source_contract import net_research_sources,source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw
from cryptoforge.atomic_reports import write_json_report
from scripts.audit_trade_labels import verify_trade


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--scan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('source case audit output is immutable')
    protocol=prepare_research('config/research-resources-user-1024-20261014.json')
    raw=args.scan.read_bytes();scan=json.loads(raw);cases=scan['first_twenty_per_category']['both_barriers_from_bar_open']
    if len(cases)!=20:raise ValueError('original fixed twenty cases required')
    cfg=SimulationConfig(exit_minimum_policy='preserve_inventory')
    deps=net_research_sources('labels',build_trade_labels,runner=Path(__file__).resolve());deps['arithmetic']=verify_trade
    hashes=source_hashes(deps);runtime=save_runtime_sources(args.output.parent/'edge-label-runtime',deps,hashes)
    results=[]
    with sqlite3.connect('file:'+str(Path(scan['database']).resolve())+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        for case in cases:
            original=_load(case['input_snapshot'])['row'];symbol=original[0];entry_ms=original[2]
            source=list(db.execute("SELECT * FROM candles WHERE symbol=? AND interval='5' AND start_ms>=? AND start_ms<? ORDER BY start_ms",
                (symbol,entry_ms-120*300000,entry_ms+13*300000)))
            if len(source)!=133 or list(source[120])!=original:raise ValueError('complete original paired source window required')
            pair=symbol[:-4]+'/USDT'
            rows=[CandleRow(pair=pair,symbol=symbol,open_time=datetime.fromtimestamp(row[2]/1000,UTC),
                **{name:Decimal(row[index]) for name,index in (('open',3),('high',4),('low',5),('close',6),('volume',7))}) for row in source]
            if rows[-1].open_time+timedelta(minutes=5)>datetime.fromisoformat(protocol['data_policy']['development_end']):
                raise ValueError('case exceeds development range')
            signal=rows[119].open_time
            matched=[label for label in build_trade_labels(pair,rows,cfg) if label.signal_time==signal]
            if len(matched)!=1:raise ValueError('exact original counterfactual signal label required')
            label=matched[0]
            if label.trade is not None:verify_trade(label,rows,cfg)
            reference=_save_raw(args.output.parent/'edge-label-inputs',json.dumps([asdict(row) for row in rows],sort_keys=True,default=str).encode())
            results.append({'source_case':case,'label':asdict(label),'full_window_snapshot':reference,
                'arithmetic_checked':label.trade is not None,'unresolved_is_not_negative_label':label.example is None})
    assert_source_dependencies(hashes,deps)
    result={'observed_at':datetime.now(UTC).isoformat(),'source_scan_sha256':hashlib.sha256(raw).hexdigest(),
        'config':asdict(cfg),'cases':results,'completed_cases':len(results),'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'actual_strategy_entry_verified':False,'case_selection_used_source_geometry':True,
        'feature_preprocessing_certified':False,'historical_execution_rules_certified':False,'manual_review_complete':False,'live_promotion_allowed':False}
    write_json_report(args.output,result,default=str)
    print(json.dumps({'cases':len(results),'executed':sum(case['label']['status']=='executed' for case in results),
        'ambiguous':sum(bool(case['label']['trade'] and case['label']['trade']['ambiguous']) for case in results)}))


if __name__=='__main__':main()
