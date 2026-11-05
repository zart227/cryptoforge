"""Reserve declared future validation trials in the existing global budget."""
import argparse,hashlib,json
from dataclasses import asdict
from datetime import datetime,UTC
from pathlib import Path
from cryptoforge.walk_forward_validation_plan import validation_manifests
from cryptoforge.walk_forward_schedule import make_schedule
from cryptoforge.walk_forward import folds
from cryptoforge.walk_forward_selection import fold_payload
from cryptoforge.validation_threshold import select_validation_threshold
from cryptoforge.validation_evidence import select_registered_validation_reports
from cryptoforge.net_classifier import fit_net_classifier
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.source_contract import source_hashes,net_research_sources,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources
from cryptoforge.immutable_files import install_original


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--calendar',type=Path,required=True)
    parser.add_argument('--version',choices=('v1','v2'),default='v1')
    args=parser.parse_args();raw=args.calendar.read_bytes();sha=hashlib.sha256(raw).hexdigest();calendar=json.loads(raw)
    if args.calendar.parent.name!=sha:raise ValueError('original calendar identity required')
    original={'schedule':make_schedule,'folds':folds,'fold_payload':fold_payload,'runner':Path(__file__).with_name('freeze_walk_forward_calendar.py').resolve()}
    assert_source_dependencies(calendar['implementation_hashes'],original)
    load_runtime_sources(calendar['runtime_source_bundle'],calendar['implementation_hashes'])
    if datetime.now(UTC)>=datetime.fromisoformat(calendar['folds'][0]['test_start']):
        raise ValueError('cannot declare selection grid after first test begins')
    output=Path('.local/state/walk-forward-validation-plans')/sha/('plan.json' if args.version=='v1' else 'plan-v2.json')
    if output.exists():raise ValueError('original declared plan already exists; do not replace')
    gates_raw=Path('config/net-classifier-balance-research-v1.json').read_bytes()
    if hashlib.sha256(gates_raw).hexdigest()!=Path('config/net-classifier-balance-research-v1.sha256').read_text().strip():
        raise ValueError('original economic gates changed')
    gates=json.loads(gates_raw)['paper_candidate_gates']
    deps=net_research_sources('learner',fit_net_classifier,runner=Path(__file__).resolve())
    deps.update(label_builder=build_trade_labels,plan=validation_manifests)
    hashes=source_hashes(deps);runtime=save_runtime_sources(output.parent/'runtime',deps,hashes)
    selection_sources=source_hashes({'selector':select_validation_threshold,'evidence_verifier':select_registered_validation_reports,'source_guard':assert_source_dependencies})
    manifests=validation_manifests(calendar,calendar_sha256=sha,base_config=json.loads(json.dumps(asdict(SimulationConfig(exit_minimum_policy='preserve_inventory')),default=str)),
        implementation_hashes=hashes,selection_source_hashes=selection_sources,runtime_source_bundle=runtime,
        minimum_trades=gates['min_out_of_sample_trades'],maximum_drawdown=gates['max_portfolio_drawdown'])
    protocol=json.loads(Path('config/research-protocol-v1.json').read_bytes())
    budget=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
    ids=[ledger.register(manifest,protocol_id=budget,maximum_per_family=protocol['search_limits']['max_configurations_per_family'],
        protocol_version=protocol['protocol_version']) for manifest in manifests]
    assert_source_dependencies(hashes,deps)
    receipt={'observed_at':datetime.now(UTC).isoformat(),'calendar_sha256':sha,'budget_protocol_id':budget,
        'studies':[{ 'study_sha256':study,'manifest':manifest} for study,manifest in zip(ids,manifests)],
        'reserved_validation_trials':sum(len(manifest['grid']) for manifest in manifests),
        'actual_fits_completed':0,'actual_validation_trials_completed':0,'test_rewards_read':False,
        'complete_execution_pipeline_preregistered':False,'live_promotion_allowed':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    install_original(output,(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({'path':str(output.resolve()),'studies':len(ids),'reserved_validation_trials':receipt['reserved_validation_trials'],'actual_fits_completed':0}))


if __name__=='__main__':main()
