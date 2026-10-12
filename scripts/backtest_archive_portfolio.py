"""Offline replay using the shared Spot simulator; no publication or live orders."""
import argparse
import hashlib
from math import isfinite
from dataclasses import asdict
from datetime import datetime,UTC
from decimal import Decimal
import json
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.archive import ArchiveReader
from cryptoforge.strategy_search import StrategySpec, signal
from cryptoforge.trade_simulator import SimulationConfig, simulate_portfolio


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--directory',type=Path,default=Path('.local/archive'))
    parser.add_argument('--max-candles',type=int,default=26000)
    parser.add_argument('--detailed-equity',action='store_true',help='Export bounded close marks with cash and open inventory; at most 5000 bars.')
    parser.add_argument('--family',choices=['trend','breakout','reversion'],default='trend')
    parser.add_argument('--sensitivity',type=float,default=None)
    parser.add_argument('--output',type=Path,default=Path('.local/state/portfolio-backtest.json'))
    args=parser.parse_args(argv)
    if args.max_candles<100:parser.error('at least100 input candles required')
    args.sensitivity=args.sensitivity if args.sensitivity is not None else {'trend':.001,'breakout':1.,'reversion':45.}[args.family]
    if not isfinite(args.sensitivity) or args.sensitivity<=0:parser.error('positive finite sensitivity required')
    if args.detailed_equity and args.max_candles>5000:parser.error('detailed equity requires --max-candles <=5000')
    from cryptoforge.research_protocol import prepare_research
    protocol = prepare_research()
    from cryptoforge.research_attempts import ResearchAttempts
    from cryptoforge.source_contract import source_hashes
    from cryptoforge.exit_rules import price_time_exit
    from cryptoforge.entry_risk import atr_entry_risk
    from cryptoforge.spot_buy_math import spot_acquisition
    from cryptoforge.strategy_hypotheses import load_hypothesis_catalog
    from cryptoforge.night_research import rsi
    _,catalog_sha=load_hypothesis_catalog(Path(__file__).resolve().parents[1]/'config/strategy-hypothesis-catalog-v1.json')
    dependencies={'simulator':simulate_portfolio,'strategy':signal,'rsi':rsi,'archive':ArchiveReader,
        'exit_rules':price_time_exit,'entry_risk':atr_entry_risk,'buy_math':spot_acquisition,
        'research_guard':prepare_research,'runner':Path(__file__)}
    fingerprints=source_hashes(dependencies)
    reader=ArchiveReader(args.directory, protocol=protocol)
    config=SimulationConfig()
    data={pair:reader.read_candles(pair,limit=args.max_candles) for pair in args.pair}
    spec=StrategySpec(args.family,config.hold_bars,args.sensitivity)
    candidate={'family':args.family,'sensitivity':args.sensitivity,'hold':config.hold_bars,
        'stop':str(config.stop_fraction),'target':str(config.target_fraction),'detailed_equity':args.detailed_equity}
    manifest={'grid':[candidate],'base_config':asdict(config),'implementation_hashes':fingerprints,
        'hypothesis_catalog_sha256':catalog_sha,'scope':'development_replay_not_independent_validation',
        'dataset_sha256':hashlib.sha256(json.dumps({pair:[asdict(row) for row in rows] for pair,rows in data.items()},default=str,sort_keys=True).encode()).hexdigest()}
    ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    study=ledger.register(manifest,protocol_id=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest(),maximum_per_family=protocol['search_limits']['max_configurations_per_family'],protocol_version=protocol['protocol_version'])
    prior=ledger.result(study,candidate)
    if prior is not None:
        try:matches=json.loads(args.output.read_bytes())==prior
        except (OSError,ValueError):matches=False
        if not matches:write_json_report(args.output,prior)
        print(json.dumps({'status':'original_replay_preserved','study':study}));return
    try:
        signals={pair:[c.open_time for i,c in enumerate(rows) if i>=35 and signal(rows,i,spec)] for pair,rows in data.items()}
        result=simulate_portfolio(data,signals,config,capture_equity_details=args.detailed_equity)
        if abs(result.final_cash-config.capital-sum((t.net_pnl for t in result.trades),Decimal(0)))>Decimal('1e-20'):
            raise ValueError('portfolio cash/PnL reconciliation failed')
        if fingerprints!=source_hashes(dependencies):raise ValueError('replay source changed during calculation')
    except Exception as exc:
        ledger.record(study,candidate,{'error':type(exc).__name__},failed=True);raise
    summary={'trades':len(result.trades),'rejections':len(result.rejections),
             'net_pnl':result.final_cash-config.capital,'final_cash':result.final_cash,
             'max_drawdown_conservative_bound':result.max_drawdown,'live_eligible':False,
             'evaluation':'development_replay_not_independent_validation'}
    report={'research_study_sha256':study,'observed_at':datetime.now(UTC).isoformat(),'manifest':manifest,'summary':summary,'config':asdict(config),'strategy':asdict(spec),
            'data_ranges':{p:{'start':rows[0].open_time,'end':rows[-1].open_time,'candles':len(rows)} for p,rows in data.items()},
            'result':asdict(result)}
    def encode(value):
        if isinstance(value,(datetime,Decimal)):
            return value.isoformat() if isinstance(value,datetime) else str(value)
        raise TypeError(type(value).__name__)
    report=json.loads(json.dumps(report,default=encode,allow_nan=False))
    ledger.record(study,candidate,report)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json_report(args.output,report,default=encode)
    print(json.dumps(summary,default=encode))
    print(f'report={args.output.resolve()}')


if __name__=='__main__':
    main()
