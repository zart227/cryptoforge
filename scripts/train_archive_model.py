"""Offline archive experiment: never publishes an active model or places orders."""
import argparse
from datetime import UTC, datetime
from pathlib import Path

from cryptoforge.archive import ArchiveReader
from cryptoforge.model_training import build_examples, chronological_splits, train_logistic_model, write_model_artifact, promotion_decision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', action='append', required=True)
    parser.add_argument('--directory', type=Path, default=Path('.local/archive'))
    parser.add_argument('--timeframe', choices=['5m','15m','1h'], default='5m')
    parser.add_argument('--max-candles', type=int, default=26000)
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--feature-lookback-candles',type=int,default=120)
    parser.add_argument('--horizon-candles', type=int, default=3)
    parser.add_argument('--round-trip-cost', type=float, default=0.003)
    args = parser.parse_args(argv)
    from cryptoforge.research_protocol import prepare_research
    protocol = prepare_research()
    if args.epochs < 1 or args.max_candles < 100 or args.horizon_candles < 1 or args.feature_lookback_candles<36 or not 0 <= args.round_trip_cost < 1:
        parser.error('invalid training parameters')
    from cryptoforge.source_contract import primary_training_sources,source_hashes
    from cryptoforge.training_snapshot import save_training_snapshot,save_runtime_sources
    dependencies={**primary_training_sources(),'offline_archive_runner':main}
    fingerprints=source_hashes(dependencies)
    reader = ArchiveReader(args.directory, protocol=protocol)
    examples=[]
    for pair in args.pair:
        examples.extend(build_examples(pair,reader.read_candles(pair,timeframe=args.timeframe,limit=args.max_candles),
                                       horizon_candles=args.horizon_candles,min_label_return=args.round_trip_cost,
                                       feature_lookback_candles=args.feature_lookback_candles))
    examples.sort(key=lambda e:e.open_time)
    train,validation,test=chronological_splits(examples)
    if min(len(train),len(validation),len(test)) < 100:
        parser.error('insufficient examples in one or more splits')
    now=datetime.now(UTC)
    runtime=save_runtime_sources(args.directory/'models'/'runtime-sources',dependencies,fingerprints)
    admission={'status':'frozen_archive_development_only','pairs':list(dict.fromkeys(args.pair)),
        'historical_observation_times_certified':False,'datasets':protocol['datasets']}
    metadata={'data_snapshot_at':now.isoformat(),'timeframe':args.timeframe,
        'feature_calculation_contract':'bounded-window-candle-v1',
        'feature_lookback_candles':args.feature_lookback_candles,'horizon_candles':args.horizon_candles,
        'min_label_return':args.round_trip_cost,'round_trip_cost':args.round_trip_cost,
        'implementation_hashes':fingerprints,'runtime_source_bundle':runtime,'source_admission':admission}
    snapshot=save_training_snapshot(args.directory/'models'/'input-snapshots',
        splits={'train':train,'validation':validation,'test':test},metadata=metadata)
    model=train_logistic_model(train,validation,test,learning_rate=0.08,epochs=args.epochs,trained_at=now)
    if source_hashes(dependencies)!=fingerprints:raise ValueError('offline training runtime changed during fit')
    artifact=model.as_artifact(pairs=args.pair,trained_at=now,config={
        **metadata,'training_input_snapshot':snapshot,'input_candle_state':'closed_only',
        'target_version':'fixed-future-return-v1','learning_rate':0.08,
        'timeframe':args.timeframe,'horizon_candles':args.horizon_candles,'epochs':args.epochs,
        'round_trip_cost':args.round_trip_cost,'min_label_return':args.round_trip_cost,
        'source':'local_bybit_archive','training_label_end':max(e.label_end_time for e in train).isoformat(),
        'validation_end':max(e.label_end_time for e in validation).isoformat(),
        'fit_information_end':max(e.label_end_time for e in train+validation).isoformat(),
        'evaluation_information_end':max(e.label_end_time for e in test).isoformat(),
        'test_start':test[0].open_time.isoformat(),'test_end':test[-1].label_end_time.isoformat(),
    })
    artifact['offline_quality_screen']=promotion_decision(model,None,test,round_trip_cost=args.round_trip_cost)
    artifact['live_eligible']=False
    artifact['research_scope']='development_diagnostic_not_independent_final_validation'
    artifact['automatic_publication_allowed']=False
    path,_=write_model_artifact(artifact,args.directory/'models')
    print(f'artifact={path.resolve()}')
    print(f'splits train={len(train)} validation={len(validation)} test={len(test)}')
    print(f'test_metrics={model.metrics[-1]}')
    print(f'quality_screen={artifact["offline_quality_screen"]}')


if __name__ == '__main__':
    main()
