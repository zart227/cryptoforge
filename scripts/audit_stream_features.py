"""Bounded archive/append-stream parity audit; no fitting or live qualification."""
import argparse,hashlib,json
from datetime import UTC,datetime
from pathlib import Path
from cryptoforge.archive import ArchiveReader
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.model_training import build_examples,extract_features
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import source_hashes
from cryptoforge.stream_features import ClosedFeatureStream
from cryptoforge.supabase_executor import entry_signal


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('.local/state/stream-feature-input-audit.json'))
    args=parser.parse_args(argv);protocol=prepare_research();now=datetime.now(UTC)
    functions={'stream':ClosedFeatureStream,'batch':build_examples,'features':extract_features,
        'signals':entry_signal,'archive':ArchiveReader,'guard':prepare_research,'runner':Path(__file__)}
    hashes=source_hashes(functions);cases=[]
    for pair in protocol['baseline_pairs']:
        dataset=next(row for row in protocol['datasets'] if row['pair']==pair)
        rows=ArchiveReader(Path(dataset['path']).parent,protocol=protocol).read_candles(pair,limit=2000)[:1400]
        if len(rows)!=1400:raise ValueError('complete fixed development slice required')
        stream=ClosedFeatureStream(pair,lookback_candles=120);outputs={};signal_checks=0
        for index,row in enumerate(rows):
            result=stream.push(row,as_of=now)
            if result is None:continue
            outputs[row.open_time]=result.features
            incremental=entry_signal(list(stream.rows),allow_intraday_reversion=True,allow_emerging_momentum=True)
            batch=entry_signal(rows[index-119:index+1],allow_intraday_reversion=True,allow_emerging_momentum=True)
            if incremental!=batch:raise ValueError('bounded strategy signal parity mismatch')
            signal_checks+=1
        examples=build_examples(pair,rows,horizon_candles=3,feature_lookback_candles=120)
        if any(outputs[row.open_time]!=row.features for row in examples):raise ValueError('bounded feature parity mismatch')
        cases.append({'pair':pair,'input_bars':len(rows),'compared_feature_vectors':len(examples),
            'compared_bounded_signals':signal_checks,'retained_stream_bars':len(stream.rows),
            'development_slice_sha256':hashlib.sha256(json.dumps([str(row) for row in rows]).encode()).hexdigest()})
    if hashes!=source_hashes(functions):raise ValueError('stream audit sources changed during calculation')
    result={'status':'bounded_stream_feature_parity_verified','as_of':now.isoformat(),'cases':cases,
        'implementation_hashes':hashes,'feature_contract':'bounded-window-candle-v1_120_closed_only',
        'strategy_signal_scope':'same_bounded120_window_not_full_live_execution_procedure',
        'historical_observation_times_certified':False,'model_fitting_performed':False,
        'live_policy_changed':False,'profitability_established':False}
    write_json_report(args.output,result);print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
