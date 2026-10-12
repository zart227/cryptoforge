"""Train an offline Spot-long classifier on simulated net trade outcomes."""
import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

from cryptoforge.archive import ArchiveReader
from cryptoforge.model_training import chronological_splits, train_logistic_model, write_model_artifact
from cryptoforge.trade_labels import TARGET_VERSION, build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig, simulate_portfolio


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--directory',type=Path,default=Path('.local/archive'))
    parser.add_argument('--max-candles',type=int,default=26000)
    parser.add_argument('--epochs',type=int,default=50)
    parser.add_argument('--hold-bars',type=int,default=12)
    args=parser.parse_args()
    from cryptoforge.research_protocol import prepare_research
    protocol = prepare_research()
    if args.max_candles<100 or args.epochs<1:
        parser.error('positive epochs and at least 100 candles required')
    config=SimulationConfig(hold_bars=args.hold_bars)
    reader=ArchiveReader(args.directory, protocol=protocol)
    data={pair:reader.read_candles(pair,limit=args.max_candles) for pair in dict.fromkeys(args.pair)}
    # Enforce identical portfolio grid before spending time training.
    simulate_portfolio(data,{},config)
    labels=[label for pair,rows in data.items() for label in build_trade_labels(pair,rows,config)]
    examples=sorted((label.example for label in labels if label.example is not None),key=lambda e:e.open_time)
    train,validation,test=chronological_splits(examples)
    if min(len(train),len(validation),len(test))<100:
        parser.error('insufficient executable examples in one or more splits')
    now=datetime.now(UTC)
    model=train_logistic_model(train,validation,test,learning_rate=0.08,epochs=args.epochs,trained_at=now)
    # No short strategy was modeled: never present a dummy short head as trained.
    artifact=model.as_artifact(pairs=list(data),trained_at=now,config={
        'target_version':TARGET_VERSION,'source':'archive_trade_simulator','timeframe':'5m',
        'simulation':asdict(config),'epochs':args.epochs,
        'fit_information_end':max(e.label_end_time for e in train+validation).isoformat(),
        'evaluation_information_end':max(e.label_end_time for e in test).isoformat()})
    for key in ('short_weights','short_bias','short_metrics'):
        artifact.pop(key,None)
    test_start=test[0].open_time
    test_end=max(e.label_end_time for e in test)
    # Execute test signals with one shared wallet; independent label PnL is not added.
    signals={pair:[] for pair in data}
    from cryptoforge.model_training import predict_probability
    for example in test:
        if predict_probability(example.features,list(model.weights),model.bias,list(model.means),list(model.stds))>=model.threshold:
            signals[example.pair].append(example.open_time)
    test_data={pair:[c for c in rows if test_start<=c.open_time<test_end] for pair,rows in data.items()}
    result=simulate_portfolio(test_data,signals,config)
    pnl=result.final_cash-config.capital
    artifact.update(target_version=TARGET_VERSION,live_eligible=False,
                    short_model_available=False,
                    label_summary={'executed':len(examples),'rejected':len(labels)-len(examples)},
                    offline_portfolio={'trades':len(result.trades),'net_pnl':str(pnl),
                                       'max_drawdown_conservative_bound':str(result.max_drawdown),
                                       'status':'development_evaluation_no_promotion'})
    # Decimal configuration must be converted before computing the artifact checksum.
    artifact=json.loads(json.dumps(artifact,default=str))
    path,_=write_model_artifact(artifact,args.directory/'trade-models')
    print(json.dumps({'artifact':str(path.resolve()),'labels':artifact['label_summary'],
                      'test_metrics':asdict(model.metrics[-1]),'portfolio':artifact['offline_portfolio']}),flush=True)


if __name__=='__main__':
    main()
