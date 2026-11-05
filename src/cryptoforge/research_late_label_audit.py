"""Late local label values with original feature selections and deadline results preserved."""
import argparse
from copy import deepcopy
from datetime import timedelta
import gzip
import hashlib
import io
import os
import signal
import subprocess
import sys
from pathlib import Path
import tempfile

from cryptoforge import research_local_cohort_audit as cohort
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp

POLICY = {'schema_version': 'research-late-label-audit-policy-v1', 'maximum_source_transactions': 1,
    'original_source_transactions_retained': 2, 'original_features_may_be_recovered': False,
    'original_deadline_result_may_change': False, 'historical_availability_may_be_backdated': False,
    'training_admission_enabled': False, 'fit_or_prediction_enabled': False,
    'maximum_source_bytes': 16777216, 'maximum_compressed_bytes': 4194304}


def implementation():
    return {'late_audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'late_worker': hashlib.sha256(Path(__file__).with_name('research_late_label_value_worker.py').read_bytes()).hexdigest(),
        'cohort': cohort.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fixed_late_label_audit_required')


def _sha(path):
    if path.is_symlink() or not path.is_file(): raise ValueError('original_regular_source_file_required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory):
    _guard(); directory = cohort.values.private._safe_directory(directory, private=True)
    read = lambda folder, name, limit=64000: cohort.values.temporal._read(folder, name, limit)
    plan = read(directory, 'late-plan.json'); freeze = read(directory, 'capture-freeze.json')
    original = Path(plan['original_cohort_directory']); binding, original_plan, sources = cohort._load(original)
    if (plan['schema_version'] != 'late-local-primary-cohort-source-v1'
            or plan['purpose'] != 'late_retrospective_label_value_compatibility_only_not_original_deadline_repair'
            or plan['pairs'] != original_plan['pairs'] or plan['reviewed_main_profile'] != original_plan['reviewed_main_profile']
            or plan['maximum_capture_transactions'] != 1 or len(plan['capture_slots']) != 1
            or plan['original_M38_captures_consumed'] != 2 or plan['metadata_only_preflight_transactions'] != 0
            or plan['original_feature_windows_preserved'] is not True or plan['original_deadline_status_may_change'] is not False
            or plan['new_model_fit_prediction_numeric_provider_allowances'] is not False
            or plan['source_available_at_is_current_observation_only'] is not True
            or plan['original_information_end'] != original_plan['label_information_end']
            or not timestamp(original_plan['label_information_end']) < timestamp(plan['registered_at']) < timestamp(plan['capture_slots'][0])):
        raise ValueError('separate_late_only_scope_required')
    for key, expected in (('maximum_capture_transactions', 1), ('original_M38_captures_consumed', 2), ('metadata_only_preflight_transactions', 0)):
        if type(plan[key]) is not int or plan[key] != expected: raise ValueError('exact_late_source_counts_required')
    for name in ('decision_anchor', 'decision_time', 'label_end_time', 'label_information_end', 'min_label_return', 'round_trip_cost', 'project'):
        if plan[name] != original_plan[name]: raise ValueError('original_frozen_study_fields_required')
    for name, key in (('late-plan.json', 'plan_file_sha256'), ('capture-worker.py', 'worker_sha256'), ('collect-once.py', 'collector_sha256')):
        if _sha(directory/name) != freeze[key]: raise ValueError('original_late_operator_changed')
    original_freeze = read(original, 'capture-freeze.json')
    if freeze['worker_sha256'] != original_freeze['worker_sha256'] or freeze['original_journals'] != original_freeze['original_journals']:
        raise ValueError('same_fixed_source_worker_and_history_required')
    expected_old = [original/'future-plan.json', original/'capture-freeze.json']+[original/'collection-run'/n for n in
        ('source-slot-0.json.gz', 'source-slot-1.json.gz', 'receipt-0.json', 'receipt-1.json', 'registration.json', 'complete.json')]
    if set(freeze['original_cohort_files']) != {str(p) for p in expected_old}:
        raise ValueError('original_two_capture_bindings_required')
    for path, expected in {**freeze['original_cohort_files'], **freeze['original_journals']}.items():
        if _sha(Path(path)) != expected: raise ValueError('original_cohort_or_history_changed')
    run = cohort.values.private._safe_directory(directory/'collection-run', private=True)
    registration = read(run, 'registration.json'); complete = read(run, 'complete.json'); receipt = read(run, 'receipt-0.json')
    if (registration['plan_sha256'] != digest(plan) or registration['maximum_source_transactions'] != 1
            or registration['old_captures_consumed'] != 2 or registration['original_deadline_status_unchanged'] is not True
            or not timestamp(plan['registered_at']) <= timestamp(registration['registered_at']) < timestamp(plan['capture_slots'][0])
            or canonical(complete) != canonical({'source_slots_completed': [0], 'source_transactions': 1, 'plan_sha256': digest(plan),
                'original_deadline_status_unchanged': True, 'model_fit_prediction_or_provider_actions': 0, 'automatic_retries': 0})):
        raise ValueError('one_completed_late_capture_required')
    for data, fields in ((registration, {'maximum_source_transactions': 1, 'old_captures_consumed': 2}),
            (receipt, {'slot_index': 0, 'database_transactions': 1, 'HTTP_or_provider_requests': 0, 'fit_model_prediction_or_budget_actions': 0})):
        for key, expected in fields.items():
            if type(data[key]) is not int or data[key] != expected: raise ValueError('exact_late_capture_accounting_required')
    path = run/'source-slot-0.json.gz'
    if (receipt['raw_source_path'] != str(path) or receipt['slot_index'] != 0 or receipt['plan_sha256'] != digest(plan)
            or type(receipt['uncompressed_bytes']) is not int or not 0 < receipt['uncompressed_bytes'] <= POLICY['maximum_source_bytes']
            or receipt['database_transactions'] != 1 or receipt['HTTP_or_provider_requests'] != 0
            or receipt['fit_model_prediction_or_budget_actions'] != 0 or receipt['automatic_retry'] is not False or receipt['source_mutated'] is not False):
        raise ValueError('bounded_original_late_capture_required')
    raw = cohort.values.private._private_read(run, path.name, POLICY['maximum_compressed_bytes'])
    if len(raw) != receipt['compressed_bytes'] or hashlib.sha256(raw).hexdigest() != receipt['compressed_sha256']:
        raise ValueError('original_late_compressed_source_changed')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream: decoded = stream.read(receipt['uncompressed_bytes']+1)
    if len(decoded) != receipt['uncompressed_bytes'] or hashlib.sha256(decoded).hexdigest() != receipt['source_sha256']:
        raise ValueError('original_late_payload_changed')
    source = strict_json(decoded.decode(), max_bytes=POLICY['maximum_source_bytes']); cohort.validate_source(plan, source, 0)
    namespace = [source['database'][k] for k in ('database_oid', 'server_address', 'server_port')]+[source['table_oid']]
    if (namespace != binding['database_namespace'] or source['client_observed_at'] != receipt['client_observed_at']
            or len(source['rows']) != receipt['rows'] or source['rows_by_pair'] != receipt['rows_by_pair']):
        raise ValueError('same_original_database_and_capture_accounting_required')
    return {'original': binding, 'late_directory': str(directory), 'late_plan_sha256': digest(plan),
        'late_receipt_sha256': digest(receipt), 'late_compressed_sha256': receipt['compressed_sha256'],
        'late_source_sha256': receipt['source_sha256']}, original_plan, sources, source


def select(plan, sources, late):
    original = cohort.select(plan, sources); selected = deepcopy(original)
    if timestamp(late['client_observed_at']) <= timestamp(plan['label_information_end']):
        raise ValueError('separate_post_deadline_diagnostic_required')
    anchor = timestamp(plan['decision_anchor'])
    index = {(r['pair'], timestamp(r['open_time'])): r for r in late['rows'] if cohort._eligible(r, late['client_observed_at'])}
    for before, item in zip(original, selected):
        rows = [index.get((item['pair'], anchor+timedelta(minutes=5*j))) for j in range(3)]
        item['labels'] = rows if all(r is not None for r in rows) else None
        item['original_missing_label_candles'] = before['missing_label_candles']
        item['missing_label_candles'] = sum(r is None for r in rows)
        item['late_label_available_at'] = late['client_observed_at']
        item['original_label_deadline_qualified_by_this_audit'] = False
        if item['features'] != before['features'] or item['missing_feature_candles'] != before['missing_feature_candles']:
            raise ValueError('original_features_must_remain_unchanged')
    return original, selected


def compose(binding, plan, original, selected, native):
    _guard()
    if len(original) != len(selected) or [x['pair'] for x in original] != plan['pairs']:
        raise ValueError('original_all_pair_selection_required')
    for before, after in zip(original, selected):
        if (after['pair'] != before['pair'] or after['features'] != before['features']
                or after['missing_feature_candles'] != before['missing_feature_candles']
                or after['original_missing_label_candles'] != before['missing_label_candles']
                or after['original_label_deadline_qualified_by_this_audit'] is not False
                or timestamp(after['late_label_available_at']) <= timestamp(plan['label_information_end'])):
            raise ValueError('late_values_cannot_repair_original_features_or_deadline')
    exact_fields(native, {'schema_version', 'original_deadline_qualified', 'late_cutoff_by_pair', 'values'})
    if (native['schema_version'] != 'late-cohort-native-values-v1' or native['original_deadline_qualified'] is not False
            or native['late_cutoff_by_pair'] != {s['pair']: s['late_label_available_at'] for s in selected}):
        raise ValueError('explicit_late_native_cutoff_contract_required')
    values = cohort.compose(binding, plan, selected, native['values'])
    core = {'schema_version': 'research-late-label-audit-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'binding_sha256': digest(binding), 'original_selection_sha256': digest(original), 'late_selection_sha256': digest(selected),
        'native_sha256': digest(native), 'value_audit': values,
        'original_pairs': len(original), 'original_complete_feature_windows': sum(x['features'] is not None for x in original),
        'original_complete_label_horizons': sum(x['labels'] is not None for x in original),
        'late_complete_label_horizons': sum(x['labels'] is not None for x in selected),
        'late_values_checked_with_original_features': values['independent_label_windows'],
        'original_deadline_status_changed': False, 'original_features_recovered_or_replaced': False,
        'historical_availability_backdated': False, 'training_data_admitted': False,
        'model_fit_or_prediction_performed': False, 'provider_or_database_accessed_by_audit': False,
        'actual_production_reader_qualified': False, 'numeric_attempts_or_allowances_created': 0,
        'status': 'late_values_compatible_original_admission_remains_blocked' if values['independent_label_windows'] > 0
            and values['feature_component_mismatches'] == values['label_mismatch_samples'] == 0 else 'blocked'}
    return {**core, 'audit_sha256': digest(core)}



def _native(project, packet, directory):
    if len(canonical(packet).encode()) > 8388608: raise ValueError('late_native_packet_cap')
    cohort.values.files._write(directory, 'packet.json', packet)
    args = [sys.executable, '-B', str(Path(__file__).with_name('research_late_label_value_worker.py')),
        '--input', str(directory/'packet.json'), '--output', str(directory/'result.json')]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    process = None
    with os.fdopen(os.open(directory/'worker.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as log:
        try:
            process = subprocess.Popen(args, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, preexec_fn=cohort.values.revisions._limits)
            if process.wait(timeout=15) != 0: raise ValueError('fixed_late_native_worker_refused')
            return cohort.values.temporal._read(directory, 'result.json', 262144)
        finally:
            if process is not None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()


def prepare(directory, source_directory):
    _guard(); directory = Path(directory).absolute(); cohort.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_late_label_audit_directory_required')
    bound = load(source_directory); binding, plan, sources, late = bound; original, selected = select(plan, sources, late)
    profile = cohort.values.main_profile(Path(plan['project']))
    with tempfile.TemporaryDirectory(prefix='late-label-values-', dir=directory.parent) as tmp:
        native = _native(Path(plan['project']), {'plan': plan, 'selections': selected}, Path(tmp))
    if cohort.values.main_profile(Path(plan['project'])) != profile or load(source_directory) != bound:
        raise ValueError('original_late_sources_or_native_runtime_changed')
    report = compose(binding, plan, original, selected, native); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', binding), ('original-selection.json', original),
            ('late-selection.json', selected), ('native.json', native), ('audit.json', report)):
        cohort.values.files._write(directory, name, value)
    return report


def verify(directory):
    _guard(); directory = cohort.values.private._safe_directory(directory, private=True)
    read = lambda name, size=262144: cohort.values.temporal._read(directory, name, size)
    if read('policy.json') != POLICY: raise ValueError('fixed_late_label_policy_required')
    saved = read('binding.json'); binding, plan, sources, late = load(saved['late_directory']); original, selected = select(plan, sources, late)
    if (binding != saved or read('original-selection.json', 8388608) != original or read('late-selection.json', 8388608) != selected):
        raise ValueError('original_and_late_selection_changed')
    report = compose(binding, plan, original, selected, read('native.json'))
    if canonical(report) != canonical(read('audit.json')): raise ValueError('late_label_audit_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--source-directory', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.source_directory) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Late label audit refused; original training admission remains blocked'); return 2
    print('Late label audit: '+report['status']); return 0


if __name__ == '__main__': raise SystemExit(main())
