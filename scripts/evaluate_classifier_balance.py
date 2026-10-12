"""Two preregistered classifier designs, natural validation and shared wallets."""
import argparse,hashlib,json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from cryptoforge.archive import ArchiveReader
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.classifier_portfolio import ClassifierEntryScore
from cryptoforge.net_classifier import fit_net_classifier,evaluate_net_classifier
from cryptoforge.net_portfolio import net_entry_signals
from cryptoforge.net_training_snapshot import load_net_training_snapshot
from cryptoforge.paired_portfolio import compare_filtered_portfolios
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import source_hashes,net_research_sources
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.train_window import prepare_training_window
from cryptoforge.train_window_audit import audit_train_window_study,_rows
from cryptoforge.training_snapshot import save_runtime_sources


def dependencies():
    from cryptoforge.classifier_diagnostics import probability_diagnostics
    from cryptoforge.equity_blocks import block_interval
    from cryptoforge.research_evidence import verify_registered_report
    functions=net_research_sources('net_classifier',fit_net_classifier,runner=Path(__file__))
    functions.update(classifier_evaluation=evaluate_net_classifier,entry_adapter=ClassifierEntryScore,
        entry_signals=net_entry_signals,paired_comparison=compare_filtered_portfolios,
        calibration=probability_diagnostics,blocks=block_interval,guard=prepare_research,
        original_audit=audit_train_window_study,window=prepare_training_window,
        input_snapshot=load_net_training_snapshot,runtime_capture=save_runtime_sources,
        ledger=ResearchAttempts,ledger_evidence=verify_registered_report,writer=write_json_report)
    return functions


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('protocol','original','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args(argv);raw=args.protocol.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=args.protocol.with_suffix('.sha256').read_text().strip():raise ValueError('classifier protocol checksum mismatch')
    protocol=prepare_research(str(args.protocol));policy=protocol['classifier_balance_policy']
    if policy['threshold']!=.5 or policy['class_balance_values']!=[False,True]:
        raise ValueError('fixed threshold0.5 and both declared class-balance designs required')
    hashes=source_hashes(dependencies())
    if hashes!=policy['implementation_hashes'] or policy['live_eligible'] is not False:
        raise ValueError('frozen research classifier sources required')
    original_raw=args.original.read_bytes()
    if hashlib.sha256(original_raw).hexdigest()!=policy['original_report_sha256']:raise ValueError('original classifier inputs changed')
    original=json.loads(original_raw);ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    audit_train_window_study(original,ledger_path=ledger.path)
    if original['study_sha256']!=policy['original_study_sha256']:raise ValueError('original study differs from freeze')
    manifest=original['manifest'];target=manifest['base_config']['target_version']
    snapshot=load_net_training_snapshot(manifest['original_input_snapshot'],target_version=target)
    train,validation=(_rows(snapshot['splits'][name]) for name in ('train','validation'))
    start=datetime.fromisoformat(manifest['train_end']);end=datetime.fromisoformat(manifest['validation_end'])
    control=policy['control_parameters']
    if control['half_life_days'] is not None:raise ValueError('uniform recency required for isolated class-balance study')
    train=prepare_training_window(train,train_end=start,window_days=control['window_days']).rows
    cfg=SimulationConfig()
    if json.loads(json.dumps(asdict(cfg),default=str))!=manifest['study_context']['execution_config']:
        raise ValueError('classifier execution assumptions differ from original labels')
    data={};ranges={}
    for pair in protocol['baseline_pairs']:
        dataset=next(row for row in protocol['datasets'] if row['pair']==pair)
        rows=ArchiveReader(Path(dataset['path']).parent,protocol=protocol).read_candles(pair,limit=2000)
        data[pair]=[row for row in rows if row.open_time<end]
        digest=hashlib.sha256(json.dumps([asdict(row) for row in data[pair]],sort_keys=True,default=str).encode()).hexdigest()
        if digest!=manifest['study_context']['development_dataset_sha256'][pair]:raise ValueError('classifier development archive changed')
        ranges[pair]={'validation_start':start.isoformat(),'development_end':end.isoformat()}
    portfolio_data={pair:[row for row in rows if row.open_time>start] for pair,rows in data.items()}
    grid=[{'family':'net-class-balance','class_balance':balance} for balance in (False,True)]
    runtime=save_runtime_sources(Path('.local/state/classifier-balance-runtime'),dependencies(),hashes)
    study_manifest={'grid':grid,'base_config':{'execution':asdict(cfg),'learning':policy['learning'],
        'threshold':policy['threshold'],'control_parameters':control,'target_version':target},
        'bootstrap_policy':policy['bootstrap_policy'],'implementation_hashes':hashes,
        'original_study_sha256':original['study_sha256'],'original_report_sha256':policy['original_report_sha256'],
        'original_input_snapshot':manifest['original_input_snapshot'],'original_runtime_sources':runtime,
        'scope':'viewed_development_class_balance_natural_validation','outer_test_evaluated':False}
    if hashes!=source_hashes(dependencies()):raise ValueError('classifier source changed before registration')
    study=ledger.register(study_manifest,protocol_id=sha,protocol_version=protocol['protocol_version'],
        maximum_per_family=protocol['search_limits']['max_configurations_per_family'])
    results=[]
    for candidate in grid:
        prior=ledger.result(study,candidate)
        if prior is not None:results.append(prior);continue
        try:
            model=fit_net_classifier(train,target_version=target,as_of=start,
                class_balance=candidate['class_balance'],**policy['learning'])
            metrics=evaluate_net_classifier(model,validation,as_of=end,target_version=target)
            selected,baseline=net_entry_signals(ClassifierEntryScore(model,policy['threshold']),data,ranges,cfg)
            selected={pair:[stamp for stamp in stamps if stamp>start] for pair,stamps in selected.items()}
            baseline={pair:[stamp for stamp in stamps if stamp>start] for pair,stamps in baseline.items()}
            comparison=compare_filtered_portfolios(portfolio_data,baseline,selected,cfg,
                stress_multiplier=2,bootstrap_policy=policy['bootstrap_policy'])
            if hashes!=source_hashes(dependencies()):raise ValueError('classifier source changed during fitting')
            result={'parameters':candidate,'model':asdict(model),'metrics':metrics,'comparison':comparison}
            ledger.record(study,candidate,result);results.append(ledger.result(study,candidate))
        except Exception as exc:ledger.record(study,candidate,{'error':type(exc).__name__},failed=True);raise
    if hashes!=source_hashes(dependencies()):raise ValueError('classifier source changed before export')
    report={'manifest':study_manifest,'study_sha256':study,'results':results,
        'model_selection_performed':False,'probability_calibration_established':False,
        'live_promotion_allowed':False,'independent_profitability_established':False}
    write_json_report(args.output,report,default=str)
    print(json.dumps({'study_sha256':study,'results':[{'class_balance':r['parameters']['class_balance'],
        'brier':r['metrics']['brier'],'log_loss':r['metrics']['log_loss'],
        'trades':r['comparison']['roles']['filtered']['executed_trades'],
        'net_pnl':r['comparison']['roles']['filtered']['net_pnl'],
        'stress_net_pnl':r['comparison']['roles']['stress_filtered']['net_pnl']} for r in results],
        'live_promotion_allowed':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
