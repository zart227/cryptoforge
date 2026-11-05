"""Execute one original head and its three reserved validation portfolio trials."""
import argparse,hashlib,json
from dataclasses import asdict
from datetime import datetime,UTC,timedelta
from decimal import Decimal
from pathlib import Path
from cryptoforge.walk_forward_inputs import load_bound_candles
from cryptoforge.walk_forward_validation_plan import validation_manifests
from cryptoforge.net_classifier import fit_net_classifier
from cryptoforge.trade_labels import build_trade_labels,TARGET_VERSION
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.causal_features import feature_snapshots
from cryptoforge.supabase_executor import entry_signal
from cryptoforge.paired_portfolio import compare_filtered_portfolios
from cryptoforge.research_attempts import ResearchAttempts,identity
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import net_research_sources,source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources,_save_raw
from cryptoforge.immutable_files import install_original
from cryptoforge.atomic_reports import write_json_report

ROOT=Path(__file__).resolve().parents[1]


def portfolio_summary(comparison):
    ordinary=comparison['roles']['filtered'];stress=comparison['roles']['stress_filtered']
    return {'initial_cash':comparison['initial_capital'],'net_pnl':ordinary['net_pnl'],'stress_net_pnl':stress['net_pnl'],
        'max_drawdown':ordinary['drawdown_bound'],'stress_max_drawdown':stress['drawdown_bound'],
        'trade_count':ordinary['executed_trades'],'stress_trade_count':stress['executed_trades'],
        'open_positions_at_end':ordinary['open_positions_at_end'],'stress_open_positions_at_end':stress['open_positions_at_end'],
        'exit_minimum_violations':ordinary['known_exit_minimum_violations'],'stress_exit_minimum_violations':stress['known_exit_minimum_violations']}


def validation_prices(data,start,end):
    return {pair:[row for row in rows if start<=row.open_time and row.open_time+timedelta(minutes=5)<end]
            for pair,rows in data.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--binding',type=Path,required=True);parser.add_argument('--balanced',type=int,choices=(0,1),required=True)
    parser.add_argument('--directory',type=Path,required=True);args=parser.parse_args()
    if (args.directory/'completed.json').exists():parser.error('original completed execution is immutable')
    prepare_research('config/research-resources-user-1024-20261014.json')
    plan_raw=args.plan.read_bytes();plan=json.loads(plan_raw);bound_raw=args.binding.read_bytes();binding=json.loads(bound_raw)
    if hashlib.sha256(plan_raw).hexdigest()!=binding['plan_sha256'] or binding['test_candles_included'] is not False:
        raise ValueError('original input binding belongs to another plan or includes test')
    studies=[item for item in plan['studies'] if item['manifest']['fold_index']==binding['fold_index']
             and item['manifest']['training_policy']['class_balance']==bool(args.balanced)]
    if len(studies)!=1:raise ValueError('one original head study required')
    study=studies[0];manifest=study['manifest'];policy=manifest['training_policy'];fold=manifest['fold']
    if policy['target']!=TARGET_VERSION:raise ValueError('original net target differs from label producer')
    deadline=datetime.fromisoformat(fold['test_start'])
    if datetime.now(UTC)>=deadline:raise ValueError('unregistered execution cannot begin after first test starts')
    original=net_research_sources('learner',fit_net_classifier,runner=ROOT/'scripts/register_walk_forward_validation.py')
    original.update(label_builder=build_trade_labels,plan=validation_manifests)
    assert_source_dependencies(manifest['implementation_hashes'],original)
    load_runtime_sources(manifest['runtime_source_bundle'],manifest['implementation_hashes'])
    ledger=ResearchAttempts(ROOT/'.local/state/research-attempts.sqlite')
    for candidate in manifest['grid']:ledger.result(study['study_sha256'],candidate)
    numeric={name for name,value in asdict(SimulationConfig()).items() if isinstance(value,Decimal)}|{'entry_fee','exit_fee'}
    cfg=SimulationConfig(**{key:Decimal(value) if key in numeric and value is not None else value for key,value in manifest['base_config'].items()})
    deps=net_research_sources('learner',fit_net_classifier,runner=Path(__file__).resolve())
    deps.update(binding=load_bound_candles,native_control=entry_signal,comparison=compare_filtered_portfolios,summary=portfolio_summary)
    hashes=source_hashes(deps);runtime=save_runtime_sources(args.directory/'runtime',deps,hashes)
    bootstrap={'minimum_days':14,'block_days':2,'repetitions':2000,'seed':20261015}
    design={'observed_at':datetime.now(UTC).isoformat(),'study_sha256':study['study_sha256'],
        'binding_sha256':hashlib.sha256(bound_raw).hexdigest(),'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'native_flags':{'allow_intraday_reversion':True,'allow_emerging_momentum':True},'bootstrap':bootstrap,
        'validation_only':True,'test_rewards_read':False,'live_promotion_allowed':False}
    args.directory.mkdir(parents=True,exist_ok=True)
    install_original(args.directory/'execution-design.json',(json.dumps(design,sort_keys=True,indent=2)+'\n').encode())
    data=load_bound_candles(binding)
    if set(data)!={'BTC/USDT','ETH/USDT'}:raise ValueError('fixed BTC/ETH source universe required')
    start=datetime.fromisoformat(manifest['selection_policy']['validation_start']);end=datetime.fromisoformat(manifest['selection_policy']['validation_end'])
    if binding['end_ms_exclusive']!=int(end.timestamp()*1000) or end>datetime.now(UTC):raise ValueError('original completed validation range required')
    cutoff=datetime.fromisoformat(policy['train_label_cutoff']);train_start=datetime.fromisoformat(fold['train_start']);train=[]
    for pair,rows in data.items():
        history=[row for row in rows if row.open_time+timedelta(minutes=5)<cutoff]
        labels=build_trade_labels(pair,history,cfg)
        train.extend(label.example for label in labels if label.example is not None
            and label.signal_time>=train_start and label.label_end_time<cutoff)
        del labels
    train.sort(key=lambda row:(row.open_time,row.pair))
    train_ref=_save_raw(args.directory/'inputs',json.dumps([asdict(row) for row in train],sort_keys=True,default=str).encode())
    model=fit_net_classifier(train,target_version=TARGET_VERSION,as_of=cutoff,class_balance=policy['class_balance'],
        epochs=policy['epochs'],learning_rate=policy['learning_rate'],l2=policy['l2'])
    model_ref=_save_raw(args.directory/'models',json.dumps(asdict(model),sort_keys=True,default=str).encode())
    baseline={};probabilities={};step=timedelta(minutes=5);horizon=step*(cfg.hold_bars+cfg.entry_delay_bars)
    for pair,rows in data.items():
        indices={row.open_time:index for index,row in enumerate(rows)};base=[];scores={}
        for snapshot in feature_snapshots(pair,rows,as_of=end):
            if not start<=snapshot.open_time or snapshot.feature_available_at+horizon>=end:continue
            index=indices[snapshot.open_time]
            if index<119 or not entry_signal(rows[index-119:index+1],**design['native_flags'])[0]:continue
            base.append(snapshot.open_time);scores[snapshot.open_time]=model.predict_probability(snapshot.features)
        baseline[pair]=base;probabilities[pair]=scores
    portfolio_data=validation_prices(data,start,end)
    reports=[]
    for candidate in manifest['grid']:
        prior=ledger.result(study['study_sha256'],candidate)
        if prior is not None:
            reports.append(prior);continue
        started=datetime.now(UTC);threshold=float(candidate['threshold'])
        selected={pair:[stamp for stamp in values if probabilities[pair][stamp]>=threshold] for pair,values in baseline.items()}
        comparison=compare_filtered_portfolios(portfolio_data,baseline,selected,cfg,stress_multiplier=2,bootstrap_policy=bootstrap)
        finished=datetime.now(UTC)
        if finished>=deadline:raise ValueError('validation execution completed after first test began')
        assert_source_dependencies(hashes,deps)
        report={'study_sha256':study['study_sha256'],'candidate':candidate,'role':'validation',
            'validation_start':start.isoformat(),'validation_end':end.isoformat(),'execution_started_at':started.isoformat(),
            'execution_finished_at':finished.isoformat(),'portfolio':portfolio_summary(comparison),
            'evaluation_information_end':max(row.open_time+step for rows in portfolio_data.values() for row in rows).isoformat(),
            'model_snapshot':model_ref,'train_input_snapshot':train_ref,'binding_sha256':design['binding_sha256'],
            'execution_design_sha256':hashlib.sha256((args.directory/'execution-design.json').read_bytes()).hexdigest(),
            'comparison_snapshot':_save_raw(args.directory/'comparisons',json.dumps(comparison,sort_keys=True,default=str).encode()),
            'test_rewards_read':False,'historical_execution_certified':False,'live_promotion_allowed':False}
        ledger.record(study['study_sha256'],candidate,report)
        write_json_report(args.directory/(identity(candidate)+'.json'),report)
        reports.append(report)
    write_json_report(args.directory/'completed.json',{'study_sha256':study['study_sha256'],'train_examples':len(train),
        'validation_trials_completed':len(reports),'reports':reports,'test_rewards_read':False,'live_promotion_allowed':False})
    print(json.dumps({'train_examples':len(train),'trials':len(reports),'net_pnl':[row['portfolio']['net_pnl'] for row in reports]}))


if __name__=='__main__':main()
