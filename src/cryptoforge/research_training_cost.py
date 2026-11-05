"""Static cost expansion of the pinned primary trainer; no fitting, prediction or reservations."""
import argparse
import ast
import hashlib
from pathlib import Path

from cryptoforge import research_primary_packet_audit as packets
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields

POLICY = {'schema_version': 'research-primary-training-cost-policy-v1',
    'primary_source_sha256': '9afb8aab375ec786aa8f9c9a7f617a5db642e49fcfbf45d311a413a05e63aeb7',
    'function_ast_sha256': {
        'train_logistic_model': '65ce7bc02d581f44d88d10cf8831f69803b8af198db0c614c5fa186be1c2f9b5',
        'fit_logistic_head': '058a7608bb155174c73aed356c3d8ee4299dbcf7cc1ccbc4fe9ac9af68c34f61',
        'evaluate_split': '29c812184c61cc751645568c32d6596acc4078a4cef82c8c8f2eb9bf5af806b5',
        'predict_probability': '99a74f97c47d729e1f505d69935c4095381386c65ced125e749fc54577359c5c'},
    'maximum_source_bytes': 131072, 'maximum_split_rows': 10000, 'maximum_epochs': 10000,
    'long_l2_trials': [0.0, 0.01, 0.1], 'short_l2': 0.0,
    'existing_budgets_may_change': False, 'native_training_execution_enabled': False}


def implementation():
    return {'cost_audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'packets': packets.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY: raise ValueError('fixed_training_cost_audit_required')


def inspect_source(source):
    _guard()
    if (type(source) is not str or len(source.encode()) > POLICY['maximum_source_bytes']
            or hashlib.sha256(source.encode()).hexdigest() != POLICY['primary_source_sha256']):
        raise ValueError('reviewed_primary_training_source_required')
    tree = ast.parse(source); result = {}
    for name, expected in POLICY['function_ast_sha256'].items():
        matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(matches) != 1: raise ValueError('unique_reviewed_function_required')
        actual = hashlib.sha256(ast.dump(matches[0], include_attributes=False).encode()).hexdigest()
        if actual != expected: raise ValueError('reviewed_primary_call_shape_required')
        result[name] = actual
    return result


def estimate(counts, epochs, *, logical_bundles=1):
    _guard(); exact_fields(counts, {'train', 'validation', 'test'})
    if (any(type(n) is not int or not 1 <= n <= POLICY['maximum_split_rows'] for n in counts.values())
            or type(epochs) is not int or not 1 <= epochs <= POLICY['maximum_epochs']
            or type(logical_bundles) is not int or not 1 <= logical_bundles <= 100):
        raise ValueError('bounded_exact_training_work_counts_required')
    heads = len(POLICY['long_l2_trials'])+1; total = sum(counts.values())
    single = {'logical_trainer_calls': 1, 'train_standardizer_fits': 1, 'long_optimizer_head_fits': heads-1,
        'short_optimizer_head_fits': 1, 'optimizer_head_fits': heads, 'optimizer_epoch_passes': heads*epochs,
        'optimizer_training_row_presentations_and_sigmoid_evaluations': heads*epochs*counts['train'],
        'validation_selection_probability_evaluations': (heads-1)*counts['validation'],
        'selected_long_short_split_metric_probability_evaluations': 2*total,
        'selected_long_short_diagnostic_probability_evaluations': 2*total}
    single['probability_function_calls_outside_optimization'] = (heads-1)*counts['validation']+4*total
    return {'schema_version': 'primary-training-static-work-counts-v1', 'counts': counts, 'epochs': epochs,
        'single_bundle': single, 'logical_bundles': logical_bundles, 'expanded': {k: v*logical_bundles for k, v in single.items()},
        'interpretation': 'conditional_operation_counts_if_pinned_train_logistic_model_completed_on_these_rows',
        'elapsed_time_memory_energy_or_actual_consumption_measured': False,
        'promotion_incumbent_evaluation_data_preparation_and_provider_work_included': False,
        'training_or_prediction_executed_to_estimate': False}


def proposal(work):
    _guard()
    return {'schema_version': 'primary-training-continuation-accounting-draft-v1', 'status': 'review_only_not_approved',
        'scope': 'accounting_scenario_for_unchanged_primary_trainer_not_an_executable_study',
        'baseline_logical_bundles': 1, 'ordinary_search_logical_bundles': 3, 'LLM_search_logical_bundles': 3,
        'total_logical_bundles': 7, 'shared_baseline_cost_reported_separately': True,
        'illustrative_cost_on_original_saved_row_counts': work, 'old_numeric_lifetime': '3/3 completed-cache-only',
        'old_numeric_ledger_or_caps_may_change': False, 'historical_expenses_may_be_refunded': False,
        'new_fit_or_prediction_or_provider_allowance_created': False, 'operational_command_available': False,
        'unknown_or_unapproved': ['actual_dataset_and_observation_revision_coverage', 'global_past_exposure_inventory',
            'frozen_train_validation_outer_forward_windows', 'baseline_and_evaluator_integration',
            'search_catalog_and_stopping_rule', 'primary_metric_minimum_useful_effect_and_uncertainty',
            'parent_worker_server_disk_and_provider_resource_caps', 'historical_budget_overlap_resolution',
            'explicit_next_numerical_protocol_and_budget_decision'],
        'candidate_registry_is_automatically_active_baseline': False, 'production_promotion_authorized': False}


def compose(binding, artifact, snapshot, runtime, packet_report):
    _guard()
    if packets.compose(binding, artifact, snapshot, runtime, packet_report['audited_at']) != packet_report:
        raise ValueError('original_verified_packet_report_required')
    source = runtime['sources']['primary_training']['source_utf8']; ast_hashes = inspect_source(source)
    config = artifact['config']; counts = {k: len(snapshot['splits'][k]) for k in ('train', 'validation', 'test')}
    trials = artifact['validation_search']
    if len(trials) != 3 or [row['l2'] for row in trials] != POLICY['long_l2_trials']:
        raise ValueError('original_reported_l2_grid_differs_from_reviewed_source')
    work = estimate(counts, config['epochs']); scenario = proposal(estimate(counts, config['epochs'], logical_bundles=7))
    core = {'schema_version': 'research-primary-training-cost-audit-v1', 'implementation': _LOADED,
        'policy_sha256': digest(POLICY), 'binding_sha256': digest(binding), 'packet_audit_sha256': packet_report['audit_sha256'], 'function_ast_sha256': ast_hashes,
        'candidate_artifact_sha256': binding['candidate_artifact_sha256'], 'candidate_event_time': binding['candidate_event_time'],
        'source_is_archived_and_matches_current_primary': True, 'reported_l2_trials': POLICY['long_l2_trials'],
        'original_static_work_counts': work, 'review_only_continuation': scenario,
        'logical_trainer_call_is_single_optimizer_head_fit': False,
        'historical_original_gradient_loops_reexecuted': False, 'model_fit_prediction_or_provider_performed': False,
        'actual_historical_resource_consumption_verified': False, 'training_data_admitted': False,
        'existing_accounting_retroactively_rewritten': False, 'new_budget_actions_or_allowances': 0}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, packet_directory):
    _guard(); directory = Path(directory).absolute(); packets.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_training_cost_directory_required')
    original = packets.verify(packet_directory); binding = packets.registry.bridge._read(Path(packet_directory), 'binding.json', 262144)
    bound = packets.bind(binding['registry'], binding['project'])
    if bound[0] != binding or original['candidate_artifact_sha256'] != binding['candidate_artifact_sha256']:
        raise ValueError('same_original_primary_packet_required')
    report = compose(*bound, original); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', {'packet_directory': str(Path(packet_directory).absolute()), 'original_binding': binding}),
            ('audit.json', report), ('continuation-draft.json', report['review_only_continuation'])):
        packets.files._write(directory, name, value)
    return report


def verify(directory):
    _guard(); directory = packets.private._safe_directory(directory, private=True)
    read = lambda name: packets.registry.bridge._read(directory, name, 262144)
    if read('policy.json') != POLICY: raise ValueError('fixed_training_cost_policy_required')
    saved = read('binding.json'); original = packets.verify(saved['packet_directory'])
    bound = packets.bind(saved['original_binding']['registry'], saved['original_binding']['project'])
    if bound[0] != saved['original_binding']: raise ValueError('original_training_cost_binding_changed')
    report = compose(*bound, original)
    if read('audit.json') != report or read('continuation-draft.json') != report['review_only_continuation']:
        raise ValueError('saved_training_cost_or_draft_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--packet-directory', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.packet_directory) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Static training cost audit refused; no numerical allowance created'); return 2
    print('Static training cost audit: '+str(report['original_static_work_counts']['single_bundle']['optimizer_head_fits'])+' optimizer head fits per logical trainer call; review only'); return 0


if __name__ == '__main__': raise SystemExit(main())
