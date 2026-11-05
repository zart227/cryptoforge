"""Independent feature-reference evidence over an existing native value pack."""
import argparse
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_feature_reference as reference
from cryptoforge import research_value_audit as values
from cryptoforge.training_diagnostics import canonical, digest, exact_fields


POLICY = {'schema_version': 'research-feature-oracle-policy-v1',
    'maximum_samples': 16, 'maximum_packet_bytes': 2097152, 'maximum_result_bytes': 262144,
    'worker_cpu_seconds': 8, 'worker_address_space_bytes': 536870912,
    'worker_file_bytes': 2097152, 'worker_open_files': 64, 'parent_timeout_seconds': 15,
    'comparison': 'exact_finite_float_hex_without_tolerance',
    'training_admission_enabled': False, 'candidate_execution_enabled': False}
PACK_NAMES = ('policy.json', 'binding.json', 'selection.json', 'target.json', 'native.json', 'audit.json')


def implementation():
    folder = Path(__file__).parent
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256((folder/'research_feature_reference_worker.py').read_bytes()).hexdigest(),
        'reference': hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
        'specification_sha256': digest(reference.SPEC), 'native_value_pack': values.implementation()}


_LOADED = implementation()
_POLICY_CANONICAL = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY_CANONICAL:
        raise ValueError('oracle_implementation_changed_restart_required')


def bind(directory):
    directory = values.private._safe_directory(directory, private=True)
    report = values.verify(directory)
    hashes = {name: hashlib.sha256(values.private._private_read(directory, name,
        POLICY['maximum_packet_bytes'])).hexdigest() for name in PACK_NAMES}
    binding = values.temporal._read(directory, 'binding.json', 16000)
    _, source, selection = values.bind_source_pack(binding['directory'])
    if len(selection) > POLICY['maximum_samples']:
        raise ValueError('oracle_sample_limit')
    native = values.temporal._read(directory, 'native.json', POLICY['maximum_result_bytes'])
    return {'directory': str(directory), 'files': hashes, 'value_audit_sha256': report['audit_sha256']}, source, selection, native, report


def _worker(source, selection, directory):
    packet = {'reference': source, 'selections': selection}
    if len(canonical(packet).encode()) > POLICY['maximum_packet_bytes']:
        raise ValueError('bounded_oracle_packet_required')
    values.files._write(directory, 'packet.json', packet)
    args = [sys.executable, '-B', str(Path(__file__).with_name('research_feature_reference_worker.py')),
        '--input', str(directory/'packet.json'), '--output', str(directory/'oracle.json')]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).parents[1]),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    process = None
    with os.fdopen(os.open(directory/'worker.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        try:
            process = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=stream, start_new_session=True, preexec_fn=values.revisions._limits)
            if process.wait(timeout=POLICY['parent_timeout_seconds']) != 0:
                raise ValueError('independent_feature_worker_refused')
            return values.temporal._read(directory, 'oracle.json', POLICY['maximum_result_bytes'])
        finally:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()


def compose(binding, source, selection, native, value_report, oracle):
    _guard()
    exact_fields(oracle, {'schema_version', 'reference_sha256', 'selection_sha256', 'samples',
        'source_rows_read', 'trainer_or_runtime_imported', 'model_prediction_performed', 'fit_performed',
        'source_modified', 'network_request_performed'})
    if (oracle['schema_version'] != 'research-feature-reference-values-v1'
            or oracle['reference_sha256'] != digest(source) or oracle['selection_sha256'] != digest(selection)
            or any(oracle[name] is not False for name in ('trainer_or_runtime_imported', 'model_prediction_performed',
                'fit_performed', 'source_modified', 'network_request_performed'))
            or type(oracle['samples']) is not list or len(oracle['samples']) != len(selection)):
        raise ValueError('independent_oracle_contract_required')
    checked = components = mismatch = rows_read = 0; summaries = []
    for selected, saved, actual in zip(selection, native['samples'], oracle['samples']):
        exact_fields(actual, {'id', 'feature_hex', 'selected_raw_sha256'})
        if type(actual['id']) is not int or actual['id'] != selected['id'] or saved['id'] != selected['id']:
            raise ValueError('fixed_oracle_sample_identity_required')
        available = selected['features'] is not None
        comparisons = None
        if available:
            checked += 1; components += 7; rows_read += 120
            hashes = [row['revision_sha256'] for row in selected['features']]
            if actual['selected_raw_sha256'] != digest(hashes):
                raise ValueError('original_selected_raw_hashes_required')
            if type(actual['feature_hex']) is not list or len(actual['feature_hex']) != 7:
                raise ValueError('seven_independent_features_required')
            comparisons = []
            for index, name in enumerate(reference.FEATURES):
                values._hex(actual['feature_hex'][index])
                # Saved native values were revalidated against their frozen source pack.
                training = saved['training_feature_hex'][index] if saved['training_status'] == 'checked' else None
                compared = [actual['feature_hex'][index], saved['extractor_feature_hex'][index], saved['runtime_feature_hex'][index]]
                if training is not None:
                    compared.append(training)
                comparisons.append({'feature': name, 'reference_hex': actual['feature_hex'][index],
                    'native_extractor_hex': saved['extractor_feature_hex'][index],
                    'runtime_hex': saved['runtime_feature_hex'][index],
                    'training_hex': training, 'exact_match': len(set(compared)) == 1})
            mismatch += sum(not component['exact_match'] for component in comparisons)
        elif actual['feature_hex'] is not None or actual['selected_raw_sha256'] is not None:
            raise ValueError('missing_source_cannot_be_invented')
        summaries.append({'id': selected['id'], 'symbol': selected['symbol'],
            'decision_time': selected['decision_time'], 'feature_values_checked': available,
            'metadata_issues': selected['metadata_issues'], 'components': comparisons})
    if type(oracle['source_rows_read']) is not int or oracle['source_rows_read'] != rows_read:
        raise ValueError('oracle_source_read_count_mismatch')
    core = {'schema_version': 'research-feature-oracle-audit-v1',
        'status': 'reference_matches' if checked and mismatch == 0 else 'blocked',
        'binding_sha256': digest(binding), 'reference_sha256': digest(source),
        'selection_sha256': digest(selection), 'native_sha256': digest(native), 'oracle_sha256': digest(oracle),
        'specification_sha256': digest(reference.SPEC), 'policy_sha256': digest(POLICY),
        'samples': summaries, 'feature_windows_checked': checked, 'components_checked': components,
        'component_mismatches': mismatch, 'source_rows_read': rows_read,
        'all_available_components_match': bool(checked and mismatch == 0),
        'source_value_audit_status': value_report['status'],
        'native_features_rerun': False, 'independent_reference_recomputed': True,
        'real_labels_verified': False, 'actual_main_trainer_source_selection_verified': False,
        'cross_environment_qualification_complete': False, 'statistical_patch_validation_complete': False,
        'training_data_admitted': False, 'candidate_numeric_worker_executed': False,
        'provider_called': False, 'fit_performed': False, 'model_prediction_performed': False,
        'production_promotion_authorized': False, 'implementation': _LOADED}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, value_pack):
    _guard(); directory = Path(directory).absolute()
    values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('new_oracle_audit_directory_required')
    bound = bind(value_pack)
    with tempfile.TemporaryDirectory(prefix='independent-features-', dir=directory.parent) as temporary:
        oracle = _worker(bound[1], bound[2], Path(temporary))
    if bind(value_pack) != bound:
        raise ValueError('original_value_pack_changed_during_oracle')
    report = compose(*bound, oracle)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('spec.json', reference.SPEC), ('binding.json', bound[0]),
                        ('selection.json', bound[2]), ('oracle.json', oracle), ('audit.json', report)):
        values.files._write(directory, name, value)
    values.files._sync(directory); values.files._sync(directory.parent)
    return report


def verify(directory):
    _guard(); directory = values.private._safe_directory(directory, private=True)
    read = lambda name, size: values.temporal._read(directory, name, size)
    if read('policy.json', 16000) != POLICY or read('spec.json', 16000) != reference.SPEC:
        raise ValueError('frozen_reference_specification_required')
    binding = read('binding.json', 16000); bound = bind(binding['directory'])
    if bound[0] != binding or read('selection.json', POLICY['maximum_packet_bytes']) != bound[2]:
        raise ValueError('oracle_original_binding_changed')
    with tempfile.TemporaryDirectory(prefix='verify-independent-features-', dir=directory.parent) as temporary:
        oracle = _worker(bound[1], bound[2], Path(temporary))
    if oracle != read('oracle.json', POLICY['maximum_result_bytes']) or bind(binding['directory']) != bound:
        raise ValueError('independent_source_replay_changed')
    report = compose(*bound, oracle)
    if canonical(report) != canonical(read('audit.json', POLICY['maximum_result_bytes'])):
        raise ValueError('independent_oracle_audit_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare':
            command.add_argument('--value-pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(args.directory, args.value_pack) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Independent feature audit refused; training admission disabled'); return 2
    print('Independent feature audit verified: '+report['status']+'; training admission disabled'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
