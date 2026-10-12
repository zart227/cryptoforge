"""Frozen net head versus all-bar baseline on viewed validation; no orders."""
from dataclasses import asdict
from decimal import Decimal
from datetime import UTC,datetime
import hashlib,json
from pathlib import Path

from cryptoforge.archive import ArchiveReader
from cryptoforge.causal_features import feature_snapshots
from cryptoforge.net_regression import NetRegressor,fit_net_regressor
from cryptoforge.source_contract import assert_source_dependencies,net_research_sources,source_hashes
from cryptoforge.paired_portfolio import compare_filtered_portfolios
from cryptoforge.equity_blocks import block_interval
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.net_portfolio import net_entry_signals
from cryptoforge.trade_simulator import SimulationConfig,simulate_portfolio
from cryptoforge.portfolio_diagnostics import portfolio_diagnostics
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.live_learning_protocol import time


def main():
    path=Path('config/net-portfolio-diagnostic-v2.json');raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=path.with_suffix('.sha256').read_text().strip():raise ValueError('portfolio protocol checksum mismatch')
    from cryptoforge.research_protocol import prepare_research
    protocol=prepare_research(str(path));policy=protocol['portfolio_diagnostic_policy']
    runtime={'head':NetRegressor,'features':feature_snapshots,'entry':net_entry_signals,
        'simulator':simulate_portfolio,'diagnostics':portfolio_diagnostics,'runner':main,
        'paired_comparison':compare_filtered_portfolios,'equity_blocks':block_interval,
        'report_writer':write_json_report,'research_guard':prepare_research}
    runtime.update(net_research_sources('fitted_net_head_dependency',fit_net_regressor))
    original_sources=source_hashes(runtime)
    report=json.loads(Path('.local/state/archive-net-head-report.json').read_bytes())
    if report['protocol_sha256']!=policy['source_net_protocol_sha256'] or report['study_sha256']!=policy['source_net_study_sha256']:
        raise ValueError('source net study differs from frozen portfolio policy')
    if policy['net_entry_threshold']!='0' or policy['live_promotion_allowed'] is not False:raise ValueError('fixed zero-threshold research-only policy required')
    dependencies=assert_source_dependencies(report['implementation_hashes'],net_research_sources('net_head',fit_net_regressor))
    model_data=next(row['model'] for row in report['results'] if row['parameters']['ridge']==report['selected_ridge'])
    if hashlib.sha256(json.dumps(model_data,sort_keys=True).encode()).hexdigest()!=policy['frozen_model_sha256']:
        raise ValueError('selected net head changed after portfolio freeze')
    if model_data['live_eligible'] is not False or model_data['model_family']!='experimental-ridge-net-return-v1':raise ValueError('experimental net head required')
    model=NetRegressor(**{key:tuple(value) if key in {'means','stds','weights'} else value for key,value in model_data.items()})
    cfg=SimulationConfig()
    if json.loads(json.dumps(asdict(cfg),default=str))!=report['base_config']:raise ValueError('net label and portfolio assumptions differ')
    reader=ArchiveReader(Path('.local/archive'),protocol=protocol);data={}
    for pair in protocol['baseline_pairs']:
        end=time(report['ranges'][pair]['development_end'])
        rows=reader.read_candles(pair,limit=protocol['net_head_policy']['max_candles_per_pair'])
        data[pair]=[row for row in rows if row.open_time<end]
        digest=hashlib.sha256(json.dumps([asdict(row) for row in data[pair]],default=str,sort_keys=True).encode()).hexdigest()
        if digest!=report['dataset_sha256'][pair]:raise ValueError('net head development snapshot changed')
    selected,baseline=net_entry_signals(model,data,report['ranges'],cfg)
    validation={pair:[row for row in rows if row.open_time>=time(report['ranges'][pair]['validation_start'])] for pair,rows in data.items()}
    candidate={'family':'frozen-net-portfolio','model_sha256':policy['frozen_model_sha256'],'threshold':'0'}
    bootstrap_policy={'minimum_days':14,'block_days':2,'repetitions':2000,'seed':20261011}
    manifest={'frozen_feature_dependencies':dependencies,'grid':[candidate],'base_config':asdict(cfg),'ranges':report['ranges'],'dataset_sha256':report['dataset_sha256'],
        'scope':policy['scope'],'outer_test_evaluated':False,
        'implementation_hashes':original_sources,'paired_bootstrap_policy':bootstrap_policy,
        'stress_comparison':'same_multiplier_2_for_candidate_and_baseline'}
    if source_hashes(runtime)!=original_sources:raise ValueError('portfolio source changed during input preparation')
    ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    study=ledger.register(manifest,protocol_id=hashlib.sha256(raw).hexdigest(),protocol_version=protocol['protocol_version'],maximum_per_family=1)
    result=ledger.result(study,candidate)
    if result is None:
        try:
            comparison=compare_filtered_portfolios(validation,baseline,selected,cfg,
                stress_multiplier=2,bootstrap_policy=bootstrap_policy)
            result={'roles':{name:comparison['roles'][source] for name,source in (
                ('candidate','filtered'),('baseline_all_bar','baseline'),
                ('stress_candidate','stress_filtered'),('stress_baseline_all_bar','stress_baseline'))},
                'paired_differences':comparison['paired_differences'],
                'cash_only_baseline':comparison['cash_only_baseline']}
            if source_hashes(runtime)!=original_sources:raise ValueError('portfolio source changed during comparison')
        except Exception as exc:ledger.record(study,candidate,{'error':type(exc).__name__},failed=True);raise
        ledger.record(study,candidate,result)
    output={**manifest,'protocol_version':protocol['protocol_version'],'study_sha256':study,'as_of':datetime.now(UTC).isoformat(),**result,'live_promotion_allowed':False,
        'historical_reserved_final_compatible':False,'independent_evidence':False}
    if source_hashes(runtime)!=original_sources:raise ValueError('portfolio source changed before report export')
    target=Path('.local/state/net-portfolio-diagnostic.json');write_json_report(target,output,default=str)
    print(json.dumps({'scope':policy['scope'],'roles':{role:{key:value[key] for key in ('generated_signals','executed_trades','net_pnl','net_per_executed_trade')} for role,value in result['roles'].items()},'live_promotion_allowed':False}))


if __name__=='__main__':main()
