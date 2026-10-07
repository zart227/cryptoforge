"""Offline archive experiment: never publishes an active model or places orders."""
import argparse
from datetime import UTC, datetime
from pathlib import Path

from cryptoforge.archive import ArchiveReader
from cryptoforge.model_training import build_examples, chronological_splits, train_logistic_model, write_model_artifact, promotion_decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', action='append', required=True)
    parser.add_argument('--directory', type=Path, default=Path('.local/archive'))
    parser.add_argument('--timeframe', choices=['5m','15m','1h'], default='5m')
    parser.add_argument('--max-candles', type=int, default=26000)
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--horizon-candles', type=int, default=3)
    parser.add_argument('--round-trip-cost', type=float, default=0.003)
    args = parser.parse_args()
    if args.epochs < 1 or args.max_candles < 100 or args.horizon_candles < 1 or not 0 <= args.round_trip_cost < 1:
        parser.error('invalid training parameters')
    reader = ArchiveReader(args.directory)
    examples=[]
    for pair in args.pair:
        examples.extend(build_examples(pair,reader.read_candles(pair,timeframe=args.timeframe,limit=args.max_candles),
                                       horizon_candles=args.horizon_candles,min_label_return=args.round_trip_cost))
    examples.sort(key=lambda e:e.open_time)
    train,validation,test=chronological_splits(examples)
    if min(len(train),len(validation),len(test)) < 100:
        parser.error('insufficient examples in one or more splits')
    now=datetime.now(UTC)
    model=train_logistic_model(train,validation,test,learning_rate=0.08,epochs=args.epochs,trained_at=now)
    artifact=model.as_artifact(pairs=args.pair,trained_at=now,config={
        'timeframe':args.timeframe,'horizon_candles':args.horizon_candles,'epochs':args.epochs,
        'round_trip_cost':args.round_trip_cost,'min_label_return':args.round_trip_cost,
        'source':'local_bybit_archive','training_label_end':max(e.label_end_time for e in train).isoformat(),
        'validation_end':max(e.label_end_time for e in validation).isoformat(),
        'test_start':test[0].open_time.isoformat(),'test_end':test[-1].label_end_time.isoformat(),
    })
    artifact['offline_quality_screen']=promotion_decision(model,None,test,round_trip_cost=args.round_trip_cost)
    artifact['live_eligible']=False
    path,_=write_model_artifact(artifact,args.directory/'models')
    print(f'artifact={path.resolve()}')
    print(f'splits train={len(train)} validation={len(validation)} test={len(test)}')
    print(f'test_metrics={model.metrics[-1]}')
    print(f'quality_screen={artifact["offline_quality_screen"]}')


if __name__ == '__main__':
    main()
