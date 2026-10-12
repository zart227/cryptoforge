"""Registered comparison of all frozen feature-ablation models on viewed development data."""
import argparse,hashlib,json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from cryptoforge.archive import ArchiveReader
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.net_regression import NetRegressor
from cryptoforge.net_ablation import AblatedNetRegressor
from cryptoforge.ablation_audit import audit_ablation_study
from cryptoforge.net_portfolio import net_entry_signals
from cryptoforge.paired_portfolio import compare_filtered_portfolios
from cryptoforge.research_attempts import ResearchAttempts,identity
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import source_hashes
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.train_window_audit import audit_train_window_study


def dependencies():
    from cryptoforge.source_contract import net_research_sources
    from cryptoforge.net_regression import fit_net_regressor
    from cryptoforge.equity_blocks import block_interval
    from cryptoforge.research_evidence import verify_registered_report
    from cryptoforge.net_training_snapshot import load_net_training_snapshot
    from cryptoforge.training_snapshot import load_runtime_sources
    functions=net_research_sources('net_head',fit_net_regressor,runner=Path(__file__))
    functions.update(entry_signals=net_entry_signals,paired=compare_filtered_portfolios,
        equity_blocks=block_interval,guard=prepare_research,report_writer=write_json_report,
        original_model_audit=audit_train_window_study,ledger=ResearchAttempts.register,
        ledger_evidence=verify_registered_report,net_snapshot=load_net_training_snapshot,
        runtime_snapshot=load_runtime_sources,ablation_audit=audit_ablation_study,ablation_head=AblatedNetRegressor)
    return functions


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--control',type=Path,required=True)
    args=parser.parse_args(argv)
    raw=args.protocol.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=args.protocol.with_suffix('.sha256').read_text().strip():raise ValueError('frozen portfolio checksum mismatch')
    protocol=prepare_research(str(args.protocol));policy=protocol['ablation_portfolio_policy']
    hashes=source_hashes(dependencies())
    if hashes!=policy['implementation_hashes']:raise ValueError('frozen portfolio sources changed')
    report_raw=args.report.read_bytes()
    if hashlib.sha256(report_raw).hexdigest()!=policy['original_report_sha256']:raise ValueError('original window report changed')
    report=json.loads(report_raw);ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    control_raw=args.control.read_bytes()
    if hashlib.sha256(control_raw).hexdigest()!=policy['control_report_sha256']:raise ValueError('original control report changed')
    control=json.loads(control_raw)
    audit_ablation_study(report,control,ledger_path=ledger.path)
    if report['study_sha256']!=policy['original_study_sha256'] or policy['live_eligible'] is not False:
        raise ValueError('research-only frozen original study required')
    cfg=SimulationConfig()
    if json.loads(json.dumps(asdict(cfg),default=str))!=control['manifest']['study_context']['execution_config']:
        raise ValueError('label/portfolio execution assumptions differ')
    start=datetime.fromisoformat(control['manifest']['train_end'])
    end=datetime.fromisoformat(control['manifest']['validation_end'])
    data={};ranges={}
    for pair in protocol['baseline_pairs']:
        dataset=next(row for row in protocol['datasets'] if row['pair']==pair)
        rows=ArchiveReader(Path(dataset['path']).parent,protocol=protocol).read_candles(pair,limit=2000)
        data[pair]=[row for row in rows if row.open_time<end]
        digest=hashlib.sha256(json.dumps([asdict(row) for row in data[pair]],sort_keys=True,default=str).encode()).hexdigest()
        if digest!=control['manifest']['study_context']['development_dataset_sha256'][pair]:raise ValueError('original development history mismatch')
        ranges[pair]={'validation_start':start.isoformat(),'development_end':end.isoformat()}
    validation={pair:[row for row in rows if row.open_time>start] for pair,rows in data.items()}
    control_model=next(r['model'] for r in control['results'] if r['parameters']==report['manifest']['base_config']['control_parameters'])
    reference_selected,_=net_entry_signals(NetRegressor(**control_model),data,ranges,cfg)
    reference_selected={pair:[stamp for stamp in stamps if stamp>start] for pair,stamps in reference_selected.items()}
    grid=[{'family':'ablation-net-portfolio','original_parameters':result['parameters'],
           'model_sha256':identity(result['model'])} for result in report['results']]
    manifest={'grid':grid,'base_config':asdict(cfg),'implementation_hashes':hashes,
        'original_study_sha256':report['study_sha256'],'original_report_sha256':policy['original_report_sha256'],
        'bootstrap_policy':policy['bootstrap_policy'],'entry_threshold':'0',
        'scope':'viewed_development_paired_portfolio_diagnostics','outer_test_evaluated':False,
        'historical_reserved_final_compatible':False}
    if hashes!=source_hashes(dependencies()):raise ValueError('portfolio source changed during inputs')
    study=ledger.register(manifest,protocol_id=sha,protocol_version=protocol['protocol_version'],
        maximum_per_family=protocol['search_limits']['max_configurations_per_family'])
    results=[]
    for candidate,original in zip(grid,report['results']):
        prior=ledger.result(study,candidate)
        if prior is not None:results.append(prior);continue
        try:
            model=AblatedNetRegressor(**{**original['model'],'fitted':NetRegressor(**original['model']['fitted']),'removed_indices':tuple(original['model']['removed_indices'])})
            selected,baseline=net_entry_signals(model,data,ranges,cfg)
            # The first validation bar is prefix context, not an executable signal.
            selected={pair:[stamp for stamp in stamps if stamp>start] for pair,stamps in selected.items()}
            baseline={pair:[stamp for stamp in stamps if stamp>start] for pair,stamps in baseline.items()}
            comparison=compare_filtered_portfolios(validation,baseline,selected,cfg,
                stress_multiplier=2,bootstrap_policy=policy['bootstrap_policy'],reference_signals=reference_selected)
            if hashes!=source_hashes(dependencies()):raise ValueError('portfolio sources changed during simulation')
            result={'parameters':candidate,'comparison':comparison}
            ledger.record(study,candidate,result);results.append(ledger.result(study,candidate))
        except Exception as exc:ledger.record(study,candidate,{'error':type(exc).__name__},failed=True);raise
    if hashes!=source_hashes(dependencies()):raise ValueError('portfolio sources changed before export')
    output={'manifest':manifest,'study_sha256':study,'results':results,
            'model_selection_performed':False,'live_promotion_allowed':False,'independent_evidence':False}
    write_json_report(args.output,output,default=str)
    print(json.dumps({'study_sha256':study,'results':[{'parameters':r['parameters'],
        'candidate':r['comparison']['roles']['filtered'],'baseline':r['comparison']['roles']['baseline']}
        for r in results],'live_promotion_allowed':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
