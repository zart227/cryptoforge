"""Independent original-source future label audit; no native rerun or admission."""
import argparse
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_feature_oracle as features
from cryptoforge import research_label_reference_worker as reference
from cryptoforge.training_diagnostics import canonical, digest, exact_fields

values = features.values
POLICY = {'schema_version': 'research-label-oracle-policy-v1', 'maximum_samples': 16,
    'maximum_packet_bytes': 2097152, 'maximum_result_bytes': 262144,
    'worker_cpu_seconds': 8, 'worker_address_space_bytes': 536870912,
    'worker_file_bytes': 2097152, 'worker_open_files': 64, 'parent_timeout_seconds': 15,
    'comparison': 'exact_endpoint_lexemes_times_binary64_hex_and_binary_labels',
    'training_admission_enabled': False, 'candidate_execution_enabled': False}
NATIVE_FIELDS = ('reference_close', 'future_close', 'future_return_hex', 'long_label',
    'short_label', 'training_input_end_time', 'label_end_time')


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
        'source_reader_helpers': hashlib.sha256(Path(reference.stamp.__code__.co_filename).read_bytes()).hexdigest(),
        'quote_parser': hashlib.sha256(Path(reference.quote.__code__.co_filename).read_bytes()).hexdigest(),
        'specification_sha256': digest(reference.SPEC), 'native_value_pack': values.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('label_oracle_implementation_changed_restart_required')


def bind(directory):
    _guard(); bound = features.bind(directory)
    target = values.temporal._read(Path(bound[0]['directory']), 'target.json', 4000)
    values.validate_target(target)
    return (*bound, target)


def _worker(source, selection, target, directory):
    packet = {'reference': source, 'selections': selection, 'target': target}
    if len(canonical(packet).encode()) > POLICY['maximum_packet_bytes']:
        raise ValueError('bounded_label_packet_required')
    values.files._write(directory, 'packet.json', packet)
    args = [sys.executable, '-B', str(Path(reference.__file__)), '--input', str(directory/'packet.json'),
        '--output', str(directory/'oracle.json')]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).parents[1]),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    process = None
    with os.fdopen(os.open(directory/'worker.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        try:
            process = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=stream, start_new_session=True, preexec_fn=values.revisions._limits)
            if process.wait(timeout=POLICY['parent_timeout_seconds']) != 0:
                raise ValueError('independent_label_worker_refused')
            return values.temporal._read(directory, 'oracle.json', POLICY['maximum_result_bytes'])
        finally:
            if process is not None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()


def compose(binding, source, selection, native, value_report, target, oracle):
    _guard(); values.validate_target(target)
    exact_fields(oracle, {'schema_version', 'reference_sha256', 'selection_sha256', 'target_sha256',
        'specification_sha256', 'samples', 'source_rows_read', 'trainer_or_runtime_imported',
        'network_request_performed', 'fit_performed', 'model_prediction_performed', 'source_modified'})
    if (oracle['schema_version'] != 'research-label-reference-values-v1'
            or oracle['reference_sha256'] != digest(source) or oracle['selection_sha256'] != digest(selection)
            or oracle['target_sha256'] != digest(target) or oracle['specification_sha256'] != digest(reference.SPEC)
            or any(oracle[k] is not False for k in ('trainer_or_runtime_imported', 'network_request_performed',
                'fit_performed', 'model_prediction_performed', 'source_modified'))
            or type(oracle['samples']) is not list or len(oracle['samples']) != len(selection)
            or len(native['samples']) != len(selection)):
        raise ValueError('independent_label_contract_required')
    checked = mismatch = 0; samples = []
    for selected, saved, observed in zip(selection, native['samples'], oracle['samples']):
        exact_fields(observed, {'id', 'values', 'selected_raw_sha256'})
        if type(observed['id']) is not int or observed['id'] != selected['id'] or saved['id'] != selected['id']:
            raise ValueError('fixed_label_identity_required')
        available = selected['features'] is not None and selected['labels'] is not None
        comparisons = None
        if available:
            checked += 1
            chosen = [selected['features'][-1], *selected['labels']]
            if observed['selected_raw_sha256'] != digest([r['revision_sha256'] for r in chosen]):
                raise ValueError('original_label_raw_hashes_required')
            actual = observed['values']
            exact_fields(actual, {*NATIVE_FIELDS, 'exact_return_numerator', 'exact_return_denominator'})
            expected = reference.labels(actual['reference_close'], actual['future_close'], target['min_label_return'])
            if (any(actual[k] != v for k, v in expected.items())
                    or any(type(actual[k]) is not int for k in ('long_label', 'short_label'))
                    or actual['training_input_end_time'] != selected['features'][-1]['open_time']
                    or actual['label_end_time'] != selected['label_end_time']):
                raise ValueError('fixed_independent_label_result_required')
            for k in ('long_label', 'short_label'):
                if type(saved[k]) is not int or saved[k] not in (0, 1):
                    raise ValueError('binary_native_labels_required')
            values._hex(saved['future_return_hex'])
            if saved['training_status'] != 'checked':
                raise ValueError('native_label_availability_required')
            comparisons = {k: {'reference': actual[k], 'native': saved[k], 'exact_match': actual[k] == saved[k]}
                for k in NATIVE_FIELDS}
            mismatch += int(any(not v['exact_match'] for v in comparisons.values()))
        elif observed['values'] is not None or observed['selected_raw_sha256'] is not None:
            raise ValueError('missing_label_source_cannot_be_invented')
        samples.append({'id': selected['id'], 'symbol': selected['symbol'], 'partition': selected['partition'],
            'label_values_checked': available, 'metadata_issues': selected['metadata_issues'], 'comparisons': comparisons})
    if type(oracle['source_rows_read']) is not int or oracle['source_rows_read'] != checked*4:
        raise ValueError('label_source_row_accounting_required')
    core = {'schema_version': 'research-label-oracle-audit-v1',
        'status': 'available_labels_match' if checked and mismatch == 0 else 'blocked',
        'binding_sha256': digest(binding), 'reference_sha256': digest(source), 'selection_sha256': digest(selection),
        'native_sha256': digest(native), 'target_sha256': digest(target), 'oracle_sha256': digest(oracle),
        'specification_sha256': digest(reference.SPEC), 'policy_sha256': digest(POLICY), 'implementation': _LOADED,
        'samples': samples, 'sample_count': len(selection), 'label_windows_checked': checked,
        'endpoint_values_checked': checked*2, 'binary_labels_checked': checked*2,
        'source_rows_read': checked*4, 'mismatch_samples': mismatch,
        'all_samples_have_label_comparisons': bool(selection and checked == len(selection)),
        'source_value_audit_status': value_report['status'], 'independent_source_endpoints_recomputed': True,
        'historical_audit_context_replayed': True, 'current_future_holdout_status_verified': False,
        'native_values_rerun': False, 'training_data_admitted': False, 'target_parameters_approved': False,
        'source_collection_performed': False, 'candidate_numeric_worker_executed': False,
        'provider_called': False, 'fit_performed': False, 'model_prediction_performed': False,
        'production_promotion_authorized': False, 'statistical_validation_complete': False}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, value_pack):
    _guard(); directory = Path(directory).absolute(); values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('new_label_oracle_directory_required')
    bound = bind(value_pack)
    with tempfile.TemporaryDirectory(prefix='independent-labels-', dir=directory.parent) as temp:
        oracle = _worker(bound[1], bound[2], bound[5], Path(temp))
    if bind(value_pack) != bound:
        raise ValueError('original_value_pack_changed_during_label_audit')
    report = compose(*bound, oracle); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('spec.json', reference.SPEC), ('binding.json', bound[0]),
        ('selection.json', bound[2]), ('target.json', bound[5]), ('oracle.json', oracle), ('audit.json', report)):
        values.files._write(directory, name, value)
    values.files._sync(directory); values.files._sync(directory.parent)
    return report


def verify(directory):
    _guard(); directory = values.private._safe_directory(directory, private=True)
    read = lambda name, size: values.temporal._read(directory, name, size)
    if read('policy.json', 16000) != POLICY or read('spec.json', 16000) != reference.SPEC:
        raise ValueError('frozen_label_reference_required')
    binding = read('binding.json', 16000); bound = bind(binding['directory'])
    if (bound[0] != binding or read('selection.json', POLICY['maximum_packet_bytes']) != bound[2]
            or read('target.json', 4000) != bound[5]):
        raise ValueError('label_original_binding_changed')
    with tempfile.TemporaryDirectory(prefix='verify-labels-', dir=directory.parent) as temp:
        oracle = _worker(bound[1], bound[2], bound[5], Path(temp))
    if oracle != read('oracle.json', POLICY['maximum_result_bytes']) or bind(binding['directory']) != bound:
        raise ValueError('independent_label_replay_changed')
    report = compose(*bound, oracle)
    if canonical(report) != canonical(read('audit.json', POLICY['maximum_result_bytes'])):
        raise ValueError('label_oracle_audit_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--value-pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try: result = prepare(args.directory, args.value_pack) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Independent label audit refused; training admission disabled'); return 2
    print('Independent label audit: '+result['status']+'; training admission disabled'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
