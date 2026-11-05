"""Review-only fit/prediction reuse graph for the existing one-parameter study.

Does not execute, cache, reserve or authorize any numerical work. Every logical
configuration remains an evaluation; only duplicate computational dependencies
are identified. Whole artifacts cannot be reused across threshold metadata.
"""
import argparse
import ast
import hashlib
from pathlib import Path

from cryptoforge import training_experiment_planner as planner
from cryptoforge import llm_training_study as study
from cryptoforge.llm_research_contracts import CATALOG
from cryptoforge.research_training_diagnostics import canonical, digest
from cryptoforge import research_local_export as private, semantic_source_collector as files

REVIEWED = {'training_experiment_planner.py': '9124124479ff9c778847cbc27140a13e327c4294d1687db2cc670090b6bae1cc',
    'llm_training_study.py': 'cfffa0403f128c6ab16033a405f5f022247b40974226a1125575df1293028e5a',
    'model_training.py': '9afb8aab375ec786aa8f9c9a7f617a5db642e49fcfbf45d311a413a05e63aeb7',
    'research_training_diagnostics.py': '85c8d646290fd30c105eeda05cd8b3a630b3783353727db69bf3a20d4687243e',
    'llm_research_contracts.py': '857acc20b5c8bcd92c3ce7a67ee4a9b6f8c331406a2780735cc6535f90db0850'}
POLICY = {'schema_version': 'research-fit-reuse-graph-policy-v1', 'reviewed_sources': REVIEWED,
    'supported_parameters': ['l2', 'threshold'], 'existing_primary_metric': 'validation_brier_score',
    'search_scope': 'baseline_plus_single_parameter_changes_only', 'maximum_configurations': 7,
    'maximum_epochs': 100, 'learning_rate': .08, 'model_execution_enabled': False,
    'cache_or_journal_mutation_enabled': False, 'new_allowance_created': False}


def source_profile():
    return {name: hashlib.sha256((Path(planner.__file__).parent/name).read_bytes()).hexdigest() for name in REVIEWED}


def implementation():
    return {'graph': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'sources': source_profile()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def review_contract():
    if implementation() != _LOADED or source_profile() != REVIEWED or canonical(POLICY) != _POLICY:
        raise ValueError('reviewed_fit_dependency_contract_changed')
    tree = ast.parse(Path(planner.__file__).read_text()); evaluate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'evaluate')
    calls = [n for n in ast.walk(evaluate) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == 'model_training']
    if sorted(n.func.attr for n in calls) != ['fit_logistic_head', 'fit_standardizer', 'predict_probability']:
        raise ValueError('reviewed_optimizer_preprocessing_prediction_shape_changed')
    if any('threshold' in ast.dump(n) for n in calls): raise ValueError('threshold_is_no_longer_fit_or_prediction_invariant')
    if not any(isinstance(n, ast.Constant) and n.value == 'validation_brier_score' for n in ast.walk(ast.parse(Path(study.__file__).read_text()))):
        raise ValueError('reviewed_study_primary_metric_changed')
    return {'reviewed_sources': REVIEWED, 'fit_and_prediction_input_parameters': ['l2'],
        'threshold_changes_classifier_decisions_not_fitted_parameters_or_probabilities': True,
        'existing_study_primary_metric': 'validation_brier_score', 'formal_verification_or_runtime_execution_performed': False}


def analyze(dataset, *, epochs=50):
    contract = review_contract()
    if type(epochs) is not int or not 1 <= epochs <= 100: raise ValueError('bounded_graph_epoch_count_required')
    dataset = Path(dataset).absolute(); data, splits = planner.load_development(dataset)
    context = {'schema_version': 'offline-long-head-fit-identity-review-v1', 'dataset_sha256': digest(data),
        'implementation_hashes': planner.implementation_hashes(), 'epochs': epochs, 'learning_rate': .08,
        'target_version': data['target_version'], 'feature_version': data['feature_version'], 'feature_names': data['feature_names'],
        'fit_label': 'label', 'train_rows': len(splits['train']), 'validation_rows': len(splits['validation'])}
    configs = [dict(planner.BASELINE)]
    for parameter in POLICY['supported_parameters']:
        for value in CATALOG[parameter]:
            if value != planner.BASELINE[parameter]: configs.append({**planner.BASELINE, parameter: float(value)})
    if len(configs) != 7 or len({digest(c) for c in configs}) != 7: raise ValueError('reviewed_one_parameter_catalog_changed')
    standardizer = digest(['train_only_standardizer', context]); fits = {}; evaluations = []
    for config in configs:
        fit_key = digest(['long_optimizer_and_probabilities', context, config['l2']])
        if fit_key not in fits:
            fits[fit_key] = {'fit_key': fit_key, 'l2': config['l2'], 'standardizer_key': standardizer,
                'prediction_key': digest(['train_and_validation_probabilities', fit_key, context['dataset_sha256']]), 'configurations': []}
        configuration_key = digest(['logical_configuration', context, config]); fits[fit_key]['configurations'].append(configuration_key)
        evaluations.append({'configuration_key': configuration_key, 'configuration': config, 'fit_key': fit_key,
            'full_artifact_key_must_include_threshold': True, 'logical_evaluation_and_budget_charge_still_required': True})
    count = len(configs); groups = len(fits); rows = context['train_rows']; prediction_rows = rows+context['validation_rows']
    core = {'schema_version': 'research-fit-reuse-graph-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'source_contract_review': contract, 'context': context, 'standardizer_key': standardizer,
        'fit_nodes': sorted(fits.values(), key=lambda n:n['l2']), 'logical_evaluations': evaluations,
        'conditional_operation_counts': {'logical_configuration_evaluations_unchanged': count, 'naive_standardizer_fits': count,
            'proposed_shared_standardizer_fits': 1, 'naive_long_head_fits': count, 'proposed_unique_long_head_fits': groups,
            'naive_optimizer_training_row_presentations': count*epochs*rows,
            'proposed_optimizer_training_row_presentations': groups*epochs*rows,
            'naive_train_validation_probability_evaluations': count*prediction_rows,
            'proposed_cached_train_validation_probability_evaluations': groups*prediction_rows,
            'diagnostics_and_logical_evaluations_still_required': count},
        'primary_objective_review': {'distinct_l2_values': groups, 'threshold_only_changes': 3,
            'threshold_only_changes_can_change_Brier_on_same_probabilities': False,
            'baseline_plus_three_other_l2_values_cover_existing_Brier_fit_catalog': True,
            'recommended_exhaustive_L2_control_before_LLM_comparison': True,
            'threshold_decision_or_economic_effects_verified': False, 'LLM_advantage_measured': False},
        'scope': 'existing_isolated_long_head_study_not_native_primary_trainer_integration',
        'actual_model_fits_predictions_provider_requests': 0, 'old_artifacts_or_fit_cache_reused': False,
        'ledger_mutations_or_refunds_or_new_allowance': False, 'execution_command_available': False,
        'old_numeric_lifetime': '3/3 completed-cache-only', 'new_numerical_protocol_approved': False,
        'wall_CPU_memory_or_whole_server_consumption_measured': False,
        'artifact_metadata_must_be_rebuilt_and_bound_per_logical_configuration': True}
    return {**core, 'graph_sha256': digest(core)}


def prepare(directory, dataset, *, epochs=50):
    directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_fit_graph_review_directory_required')
    dataset = Path(dataset).absolute(); graph = analyze(dataset, epochs=epochs)
    bound = {'dataset': str(dataset), 'file_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(), 'epochs': epochs}
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', bound), ('graph.json', graph)): files._write(directory, name, value)
    return graph


def verify(directory):
    from cryptoforge import research_data_protocol as temporal
    review_contract(); directory = private._safe_directory(directory, private=True)
    read = lambda name: temporal._read(directory, name, 262144)
    if read('policy.json') != POLICY: raise ValueError('original_fit_graph_policy_changed')
    bound = read('binding.json'); dataset = Path(bound['dataset'])
    if hashlib.sha256(dataset.read_bytes()).hexdigest() != bound['file_sha256']: raise ValueError('original_fit_graph_dataset_changed')
    graph = analyze(dataset, epochs=bound['epochs'])
    if graph != read('graph.json'): raise ValueError('original_fit_graph_review_changed')
    return graph


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'inspect': command.add_argument('--dataset', type=Path, required=True)
    args = parser.parse_args(argv)
    try: result = prepare(args.directory, args.dataset) if args.command == 'inspect' else verify(args.directory)
    except Exception:
        print('Fit graph review refused; no model actions or budget allowance'); return 2
    counts = result['conditional_operation_counts']
    print('Review-only graph: '+str(counts['logical_configuration_evaluations_unchanged'])+' logical evaluations, '+str(counts['proposed_unique_long_head_fits'])+' proposed fit nodes; execution disabled'); return 0


if __name__ == '__main__': raise SystemExit(main())
