"""Bounded development validation search: outer test is never evaluated."""
import argparse
from dataclasses import asdict,replace
from decimal import Decimal
import hashlib
import inspect
import json
from pathlib import Path

from cryptoforge.archive import ArchiveReader
from cryptoforge.strategy_search import StrategySpec,signal
import cryptoforge.strategy_search as strategy_module
from cryptoforge.trade_simulator import SimulationConfig,simulate_portfolio
from cryptoforge.supabase_executor import exit_signal
from cryptoforge.portfolio_diagnostics import portfolio_diagnostics
from cryptoforge.equity_blocks import block_interval


def research_entry_allowed(rows,index,spec,entry_filter=None):
    if entry_filter not in {None,'no_exit_conflict'}:raise ValueError('unknown research entry filter')
    if not signal(rows,index,spec):return False
    if entry_filter=='no_exit_conflict':
        conflict,_=exit_signal(rows[max(0,index-119):index+1])
        return not conflict
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--entry-conflict-study',action='store_true',help='Development-only paired baseline/no-exit-conflict study; consumes persistent budget.')
    parser.add_argument('--max-candles',type=int,default=5000)
    parser.add_argument('--directory',type=Path,default=Path('.local/archive'))
    parser.add_argument('--output',type=Path,default=Path('.local/state/validation-search.json'))
    parser.add_argument('--hypothesis-catalog',type=Path,
        default=Path(__file__).resolve().parents[1]/'config/strategy-hypothesis-catalog-v1.json')
    args=parser.parse_args()
    from cryptoforge.research_protocol import prepare_research
    protocol = prepare_research()
    from cryptoforge.strategy_hypotheses import load_hypothesis_catalog
    catalog,catalog_sha=load_hypothesis_catalog(args.hypothesis_catalog)
    reader=ArchiveReader(args.directory, protocol=protocol)
    data={p:reader.read_candles(p,limit=args.max_candles) for p in dict.fromkeys(args.pair)}
    if not data or min(len(rows) for rows in data.values())<1000:
        parser.error('at least 1000 candles per pair required')
    # Fix bounds and candidate grid before evaluating any portfolio.
    n=len(next(iter(data.values())));start=int(n*.7);end=int(n*.85)
    development={p:rows[:end] for p,rows in data.items()}
    cfg=SimulationConfig()
    simulate_portfolio(development,{},cfg)
    grid=[{'family':family,'sensitivity':sensitivity,'hold':hold,'stop':stop,'target':target}
          for family,sensitivity in [('trend',0.001),('breakout',1.0),('reversion',45.0)]
          for hold in (12,24,48) for stop,target in [('0.01','0.02'),('0.02','0.04')]]
    if args.entry_conflict_study:
        grid=[{**candidate,'entry_filter':entry_filter} for candidate in grid for entry_filter in (None,'no_exit_conflict')]
    implementation_hashes={'strategy':hashlib.sha256(Path(inspect.getfile(signal)).read_bytes()).hexdigest(),
        'simulator':hashlib.sha256(Path(inspect.getfile(simulate_portfolio)).read_bytes()).hexdigest(),
        'rsi_dependency':hashlib.sha256(Path(inspect.getfile(strategy_module.rsi)).read_bytes()).hexdigest(),
        'shared_exit_dependency':hashlib.sha256(Path(inspect.getfile(exit_signal)).read_bytes()).hexdigest(),
        'equity_block_dependency':hashlib.sha256(Path(inspect.getfile(block_interval)).read_bytes()).hexdigest(),
        'portfolio_diagnostics':hashlib.sha256(Path(inspect.getfile(portfolio_diagnostics)).read_bytes()).hexdigest(),
        'search_runner':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest={'implementation_hashes':implementation_hashes,
              'hypothesis_catalog_sha256':catalog_sha,
              'hypothesis_provenance':'observed_live_entry_exit_conflicts' if args.entry_conflict_study else 'development_baseline_families',
              'historical_reserved_final_compatible':False if args.entry_conflict_study else None,
              'independent_final_validation_claimed':False,'scope':'development_validation_70_to_85_percent','outer_test_evaluated':False,
              'pairs':list(data),'grid':grid,'base_config':asdict(cfg),
              'ranges':{p:{'start':str(rows[start].open_time),'end':str(rows[-1].open_time)} for p,rows in development.items()},
              'dataset_sha256':hashlib.sha256(json.dumps({p:[asdict(c) for c in rows] for p,rows in development.items()},default=str,sort_keys=True).encode()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.with_suffix('.protocol.json').write_text(json.dumps(manifest,default=str,indent=2))
    from cryptoforge.research_attempts import ResearchAttempts
    ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    protocol_id=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    study=ledger.register(manifest,protocol_id=protocol_id,maximum_per_family=protocol['search_limits']['max_configurations_per_family'],protocol_version=protocol['protocol_version'])
    results=[]
    for candidate in grid:
        prior=ledger.result(study,candidate)
        if prior is not None:
            results.append(prior);continue
        try:
            spec=StrategySpec(candidate['family'],candidate['hold'],candidate['sensitivity'])
            config=replace(cfg,hold_bars=candidate['hold'],stop_fraction=Decimal(candidate['stop']),target_fraction=Decimal(candidate['target']))
            signals={p:[rows[i].open_time for i in range(start,end-config.hold_bars-config.entry_delay_bars)
                        if research_entry_allowed(rows,i,spec,candidate.get('entry_filter'))] for p,rows in development.items()}
            validation={p:rows[start:end] for p,rows in development.items()}
            outcome=simulate_portfolio(validation,signals,config)
            stress=simulate_portfolio(validation,signals,config.stress_costs(2))
            net=outcome.final_cash-config.capital
            qualified=len(outcome.trades)>=30 and net>0 and stress.final_cash>config.capital and outcome.max_drawdown<=Decimal('.05')
            activity=portfolio_diagnostics(outcome,signals,initial_capital=config.capital)
            stress_activity=portfolio_diagnostics(stress,signals,initial_capital=config.capital)
            result={'activity':activity,'stress_activity':stress_activity,'parameters':candidate,'trades':len(outcome.trades),'net_pnl':str(net),
                            'stress_net_pnl':str(stress.final_cash-config.capital),'drawdown_bound':str(outcome.max_drawdown),
                            'qualified_for_further_validation':qualified}
        except Exception as exc:
            ledger.record(study,candidate,{'parameters':candidate,'error':type(exc).__name__},failed=True)
            raise
        ledger.record(study,candidate,result);results.append(result)
    ranked=sorted(results,key=lambda r:Decimal(r['net_pnl']),reverse=True)
    from cryptoforge.parameter_stability import neighborhood_diagnostics
    report={**manifest,'research_study_sha256':study,'persistent_attempt_ledger':str(ledger.path.resolve()),'effective_configuration_budget_usage':ledger.budget_usage(protocol_id),'results':results,'ranking':ranked,'parameter_neighborhoods':neighborhood_diagnostics(results),'live_eligible':False,
            'status':'further_validation_required' if any(r['qualified_for_further_validation'] for r in results) else 'no_qualified_candidate'}
    args.output.write_text(json.dumps(report,default=str,indent=2))
    print(json.dumps({'status':report['status'],'configurations':len(results),'best':{k:v for k,v in ranked[0].items() if k not in {'activity','stress_activity'}},'outer_test_evaluated':False}))


if __name__=='__main__':
    main()
