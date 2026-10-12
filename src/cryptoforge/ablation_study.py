"""Registered leave-one-feature-out research, with an immutable frozen control."""
from dataclasses import asdict
from datetime import datetime
from cryptoforge.net_ablation import fit_ablated_net_regressor, ablation_description
from cryptoforge.net_regression import evaluate_net_regressor
from cryptoforge.net_training_snapshot import load_net_training_snapshot
from cryptoforge.research_attempts import identity,ResearchAttempts
from cryptoforge.model_training import fit_standardizer
from cryptoforge.source_contract import source_hashes
from cryptoforge.train_window import prepare_training_window
from cryptoforge.train_window_audit import audit_train_window_study, _rows
from cryptoforge.training_snapshot import save_runtime_sources


def dependencies():
    return {'ablation_runner':run_registered_ablation,'ablation_head':fit_ablated_net_regressor,
        'net_evaluation':evaluate_net_regressor,'snapshot_loader':load_net_training_snapshot,
        'original_audit':audit_train_window_study,'window':prepare_training_window,
        'runtime_capture':save_runtime_sources,'ledger':ResearchAttempts,
        'standardizer':fit_standardizer,'source_guard':source_hashes}


def run_registered_ablation(original, *, control_parameters, removed_grid, ledger,
                            protocol_id, protocol_version, maximum_per_family):
    audit_train_window_study(original,ledger_path=ledger.path)
    matches=[result for result in original['results'] if result['parameters']==control_parameters]
    if len(matches)!=1:raise ValueError('exact frozen original control required')
    control=matches[0];manifest=original['manifest'];target=manifest['base_config']['target_version']
    snapshot=load_net_training_snapshot(manifest['original_input_snapshot'],target_version=target)
    train,validation=(_rows(snapshot['splits'][name]) for name in ('train','validation'))
    end=datetime.fromisoformat(manifest['train_end']);validation_end=datetime.fromisoformat(manifest['validation_end'])
    window=prepare_training_window(train,train_end=end,window_days=control_parameters['window_days'],
                                    half_life_days=control_parameters['half_life_days'])
    grid=[]
    for removed in removed_grid:
        if (not removed or len(set(removed))!=len(removed) or len(removed)>=7
                or any(type(index) is not int or not 0<=index<7 for index in removed)):
            raise ValueError('explicit proper unique feature subset required')
        candidate={'family':'net-feature-ablation','removed_indices':sorted(removed)}
        if candidate in grid:raise ValueError('duplicate effective ablation')
        grid.append(candidate)
    if not grid:raise ValueError('nonempty declared ablation grid required')
    hashes=source_hashes(dependencies())
    runtime=save_runtime_sources(ledger.path.parent/'net-ablation-runtime',dependencies(),hashes)
    study_manifest={'grid':grid,'base_config':{'control_parameters':control_parameters,
        'ridge':manifest['base_config']['ridge'],'target_version':target},
        'implementation_hashes':hashes,'original_study_sha256':original['study_sha256'],
        'control_model_sha256':identity(control['model']),'original_input_snapshot':manifest['original_input_snapshot'],
        'original_runtime_sources':runtime,'scope':'viewed_development_leave_features_out',
        'outer_test_evaluated':False,'feature_selection_performed':False}
    study=ledger.register(study_manifest,protocol_id=protocol_id,protocol_version=protocol_version,
                          maximum_per_family=maximum_per_family)
    results=[]
    for candidate in grid:
        prior=ledger.result(study,candidate)
        if prior is not None:results.append(prior);continue
        try:
            model=fit_ablated_net_regressor(window.rows,removed_indices=candidate['removed_indices'],
                target_version=target,ridge=manifest['base_config']['ridge'],as_of=end,sample_weights=window.weights)
            metrics=evaluate_net_regressor(model,validation,target_version=target,as_of=validation_end)
            if source_hashes(dependencies())!=hashes:raise ValueError('ablation source changed during fit')
            result={'parameters':candidate,'model':asdict(model),'metrics':metrics,
                'ablation':ablation_description(model),'train_count':len(window.rows),
                'rmse_difference_from_control':metrics['rmse']-control['metrics']['rmse'],
                'mae_difference_from_control':metrics['mae']-control['metrics']['mae']}
            ledger.record(study,candidate,result);results.append(ledger.result(study,candidate))
        except Exception as exc:ledger.record(study,candidate,{'error':type(exc).__name__},failed=True);raise
    if source_hashes(dependencies())!=hashes:raise ValueError('ablation source changed before export')
    return {'manifest':study_manifest,'study_sha256':study,'results':results,
        'original_control_metrics':control['metrics'],'feature_selection_performed':False,
        'live_promotion_allowed':False,'independent_profitability_established':False}
