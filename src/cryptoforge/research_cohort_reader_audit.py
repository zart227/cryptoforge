"""Pinned reader/loader replay on saved late SQL rows; original decision availability stays separate."""
import argparse
import hashlib
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_late_label_audit as late
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields

POLICY = {'schema_version': 'research-projected-cohort-reader-policy-v1', 'maximum_pairs': 20,
    'lookback_candles': 500, 'feature_lookback_candles': 120, 'horizon_candles': 3,
    'min_label_return': '0.003', 'maximum_source_age_seconds': 900, 'minimum_source_coverage': '0.8',
    'maximum_packet_bytes': 8388608, 'maximum_result_bytes': 524288, 'worker_CPU_seconds': 15,
    'worker_AS_bytes': 536870912, 'worker_wall_seconds': 25,
    'wire_kind': 'projected_SQL_numeric_lexemes_not_original_HTTP_body',
    'actual_HTTP_or_SQL_enabled': False, 'model_fit_prediction_enabled': False, 'training_admission_enabled': False}
FIELDS = ('pair', 'symbol', 'open_time', 'open', 'high', 'low', 'close', 'volume', 'ingested_at')


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256(Path(__file__).with_name('research_cohort_reader_worker.py').read_bytes()).hexdigest(),
        'late': late.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY: raise ValueError('fixed_cohort_reader_audit_required')


def load(directory):
    _guard(); directory = late.cohort.values.private._safe_directory(directory, private=True)
    report = late.verify(directory)
    saved = late.cohort.values.temporal._read(directory, 'binding.json', 262144)
    bound, plan, sources, source = late.load(saved['late_directory']); original, selected = late.select(plan, sources, source)
    if bound != saved or report['original_pairs'] != len(plan['pairs']): raise ValueError('same_verified_late_source_required')
    if (plan['min_label_return'] != POLICY['min_label_return'] or plan['horizon_candles'] != 3
            or plan['feature_lookback'] != 120 or plan['timeframe'] != '5m'):
        raise ValueError('original_fixed_cohort_target_and_feature_contract_required')
    packet = {'wire_kind': POLICY['wire_kind'], 'pairs': plan['pairs'], 'as_of': source['client_observed_at'],
        'anchor': plan['decision_anchor'], 'rows': [{k: row[k] for k in FIELDS} for row in source['rows']]}
    binding = {'late_pack_directory': str(directory), 'late_pack_files': {n: hashlib.sha256((directory/n).read_bytes()).hexdigest()
        for n in ('policy.json', 'binding.json', 'original-selection.json', 'late-selection.json', 'native.json', 'audit.json')},
        'late_audit_sha256': report['audit_sha256'], 'packet_sha256': digest(packet), 'project': plan['project']}
    return binding, packet, selected


def _limits():
    for name, limit in ((resource.RLIMIT_CPU, 15), (resource.RLIMIT_AS, 536870912),
            (resource.RLIMIT_FSIZE, 2097152), (resource.RLIMIT_NOFILE, 64), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(name, (limit, limit))


def _native(project, packet, directory):
    if len(canonical(packet).encode()) > POLICY['maximum_packet_bytes']: raise ValueError('cohort_reader_packet_cap')
    late.cohort.values.files._write(directory, 'packet.json', packet)
    args = [sys.executable, '-B', str(Path(__file__).with_name('research_cohort_reader_worker.py')),
        '--input', str(directory/'packet.json'), '--output', str(directory/'result.json')]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    process = None
    with os.fdopen(os.open(directory/'worker.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as log:
        try:
            process = subprocess.Popen(args, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, preexec_fn=_limits)
            if process.wait(timeout=25) != 0: raise ValueError('native_projected_cohort_reader_refused')
            return late.cohort.values.temporal._read(directory, 'result.json', POLICY['maximum_result_bytes'])
        finally:
            if process is not None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()


def compose(binding, packet, selected, native):
    _guard()
    exact_fields(native, {'schema_version', 'packet_sha256', 'loaded_value_runtime', 'trace', 'native', 'exact_numeric_parser',
        'all_native_examples_equal_exact_numeric_parser', 'scalar_fields_checked', 'scalar_mismatch_count', 'scalar_mismatch_examples',
        'actual_reader_and_loader_functions_invoked', 'actual_HTTP_or_database_requests', 'original_HTTP_wire_captured',
        'fit_or_prediction_performed', 'real_credentials_loaded', 'production_publication_or_source_modified'})
    if (native['schema_version'] != 'native-projected-cohort-reader-v1' or native['packet_sha256'] != digest(packet)
            or native['loaded_value_runtime'] != late.cohort.values.REVIEWED_VALUE_RUNTIME
            or native['actual_reader_and_loader_functions_invoked'] is not True
            or any(native[k] is not False for k in ('original_HTTP_wire_captured', 'fit_or_prediction_performed',
                'real_credentials_loaded', 'production_publication_or_source_modified'))
            or type(native['actual_HTTP_or_database_requests']) is not int or native['actual_HTTP_or_database_requests'] != 0
            or type(native['scalar_fields_checked']) is not int or native['scalar_fields_checked'] != 5*len(packet['rows'])
            or type(native['scalar_mismatch_count']) is not int or not 0 <= native['scalar_mismatch_count'] <= native['scalar_fields_checked']
            or len(native['trace']) != len(packet['pairs']) or [x['pair'] for x in native['trace']] != packet['pairs']):
        raise ValueError('fixed_native_projected_reader_contract_required')
    for mode in ('native', 'exact_numeric_parser'):
        result = native[mode]
        if [s['pair'] for s in result['selected']] != packet['pairs']: raise ValueError('all_original_pair_loader_results_required')
        if (type(result['all_examples']) is not int or not 0 <= result['all_examples'] <= 10000
                or result['source_admission']['requested_pairs'] != packet['pairs']):
            raise ValueError('bounded_native_loader_accounting_required')
    compared = []; components = labels = missing = mismatch = 0
    for expected, actual in zip(selected, native['native']['selected']):
        if expected['pair'] != actual['pair']: raise ValueError('original_selected_pair_order_required')
        eligible = expected['features'] is not None and expected['labels'] is not None
        example = actual['example']; feature_match = label_match = None
        if eligible:
            if example is None: missing += 1
            else:
                reference = late.cohort.features.reference([[r[k] for k in ('open', 'high', 'low', 'close', 'volume')] for r in expected['features']])
                target = late.cohort.labels.labels(expected['features'][-1]['close'], expected['labels'][-1]['close'], POLICY['min_label_return'])
                feature_match = example['feature_hex'] == reference
                label_match = all(example[k] == target[k] for k in ('future_return_hex', 'long_label', 'short_label'))
                components += 7; labels += 1; mismatch += int(not feature_match or not label_match)
        compared.append({'pair': expected['pair'], 'original_predecision_feature_window_available': expected['features'] is not None,
            'original_features_recovered_from_late_source': False, 'late_native_loader_example_available': example is not None,
            'eligible_for_original_feature_late_label_comparison': eligible,
            'independent_features_match_native_loader': feature_match, 'independent_labels_match_native_loader': label_match})
    complete = sum(s['features'] is not None and s['labels'] is not None for s in selected)
    core = {'schema_version': 'research-projected-cohort-reader-audit-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'binding_sha256': digest(binding), 'packet_sha256': digest(packet), 'native_sha256': digest(native),
        'original_comparable_windows': complete, 'native_missing_comparable_windows': missing,
        'independent_feature_components': components, 'independent_label_windows': labels, 'sample_value_mismatches': mismatch,
        'scalar_fields_checked': native['scalar_fields_checked'], 'scalar_mismatch_count': native['scalar_mismatch_count'],
        'all_native_examples_equal_exact_numeric_parser': native['all_native_examples_equal_exact_numeric_parser'],
        'native_source_admission': native['native']['source_admission'], 'exact_numeric_source_admission': native['exact_numeric_parser']['source_admission'],
        'native_all_examples': native['native']['all_examples'], 'samples': compared,
        'original_HTTP_wire_captured': False, 'actual_local_REST_or_SQL_requests': 0, 'production_service_reader_configuration_qualified': False,
        'late_data_proves_original_deadline_availability': False, 'model_fit_or_prediction_performed': False,
        'training_data_admitted': False, 'new_numerical_allowance_created': False,
        'status': 'native_loader_values_compatible_on_available_original_windows' if complete > 0 and labels == complete
            and missing == mismatch == native['scalar_mismatch_count'] == 0 and native['all_native_examples_equal_exact_numeric_parser'] is True else 'blocked'}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, late_pack):
    _guard(); directory = Path(directory).absolute(); late.cohort.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_cohort_reader_pack_required')
    bound = load(late_pack); binding, packet, selected = bound; profile = late.cohort.values.main_profile(Path(binding['project']))
    with tempfile.TemporaryDirectory(prefix='cohort-reader-', dir=directory.parent) as tmp:
        native = _native(Path(binding['project']), packet, Path(tmp))
    if late.cohort.values.main_profile(Path(binding['project'])) != profile or load(late_pack) != bound:
        raise ValueError('original_cohort_reader_source_changed')
    report = compose(binding, packet, selected, native); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', binding), ('native.json', native), ('audit.json', report)):
        late.cohort.values.files._write(directory, name, value)
    return report


def verify(directory):
    _guard(); directory = late.cohort.values.private._safe_directory(directory, private=True)
    read = lambda name: late.cohort.values.temporal._read(directory, name, 524288)
    if read('policy.json') != POLICY: raise ValueError('fixed_cohort_reader_policy_required')
    saved = read('binding.json'); binding, packet, selected = load(saved['late_pack_directory'])
    if saved != binding: raise ValueError('original_cohort_reader_binding_changed')
    report = compose(binding, packet, selected, read('native.json'))
    if canonical(read('audit.json')) != canonical(report): raise ValueError('saved_cohort_reader_report_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--late-pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.late_pack) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Saved cohort reader audit refused; training admission remains disabled'); return 2
    print('Saved cohort reader audit: '+report['status']); return 0


if __name__ == '__main__': raise SystemExit(main())
