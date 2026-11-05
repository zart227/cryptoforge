"""One bounded local 20-pair HTTP capture and sealed offline native-value audit."""
import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys

from cryptoforge import research_cohort_reader_audit as prior
from cryptoforge import research_cohort_http_worker as wire
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields

POLICY = {'schema_version': 'research-cohort-HTTP-policy-v1', 'origin': wire.ORIGIN, 'pairs': wire.PAIRS,
    'timeframe': '5m', 'lookback_candles': 500, 'feature_lookback_candles': 120, 'horizon_candles': 3,
    'min_label_return': '0.003', 'maximum_source_age_seconds': 900, 'minimum_source_coverage': '0.8',
    'maximum_local_GET_attempts': 20, 'maximum_retries': 0, 'maximum_body_bytes': 512000,
    'maximum_total_body_bytes': 10240000, 'worker_CPU_seconds': 20, 'worker_AS_bytes': 536870912,
    'worker_wall_seconds': 60, 'worker_file_bytes': 524288, 'HTTP_timeout_seconds': 3,
    'model_fit_prediction_enabled': False, 'database_writes_enabled': False, 'training_admission_enabled': False}


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest(), 'prior': prior.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY: raise ValueError('fixed_cohort_HTTP_policy_required')


def _limits():
    for name, value in ((resource.RLIMIT_CPU, 20), (resource.RLIMIT_AS, 536870912),
            (resource.RLIMIT_FSIZE, 524288), (resource.RLIMIT_NOFILE, 64), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(name, (value, value))


def _native(project, captures, mode, output):
    profile = prior.late.cohort.values.main_profile(Path(project))
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    args = [sys.executable, '-B', str(Path(wire.__file__)), '--directory', str(captures), '--mode', mode, '--output', str(output)]
    process = None
    with os.fdopen(os.open(output.with_suffix('.log'), os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as log:
        try:
            process = subprocess.Popen(args, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, preexec_fn=_limits)
            if process.wait(timeout=60) != 0: raise ValueError('native_cohort_HTTP_worker_refused_no_retry')
        finally:
            if process is not None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
    if profile != prior.late.cohort.values.main_profile(Path(project)): raise ValueError('original_main_source_changed')
    return prior.late.cohort.values.temporal._read(output.parent, output.name, 524288)


def inspect_capture(captures):
    read = lambda name, cap=65536: prior.late.cohort.values.temporal._read(captures, name, cap)
    saved = read('capture.json'); exact_fields(saved, {'schema_version', 'evidence_kind', 'started_at', 'completed_at', 'responses',
        'requests', 'retries', 'HTTP_snapshot_is_single_database_transaction'})
    if (saved['schema_version'] != 'native-cohort-HTTP-capture-v1' or saved['evidence_kind'] not in ('actual_local_HTTP_capture', 'synthetic_retained_HTTP_fixture') or type(saved['requests']) is not int or saved['requests'] != 20
            or type(saved['retries']) is not int or saved['retries'] != 0 or saved['HTTP_snapshot_is_single_database_transaction'] is not False
            or type(saved['responses']) is not dict or set(saved['responses']) != set(POLICY['pairs'])
            or wire.stamp(saved['started_at']) > wire.stamp(saved['completed_at'])):
        raise ValueError('complete_closed_cohort_capture_required')
    rows = {}; binding = {}; total = 0
    for index, pair in enumerate(POLICY['pairs']):
        item = saved['responses'][pair]; exact_fields(item, {'file', 'bytes', 'sha256', 'status', 'observed_at'})
        name = f'body-{index:02d}.json'
        if item['file'] != name or type(item['bytes']) is not int or type(item['status']) is not int or item['status'] not in (200, 206):
            raise ValueError('fixed_cohort_HTTP_receipt_required')
        raw = wire.read(captures, name, 512000); total += len(raw)
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256'] or not wire.stamp(saved['started_at']) <= wire.stamp(item['observed_at']) <= wire.stamp(saved['completed_at']):
            raise ValueError('original_cohort_HTTP_bytes_or_clock_changed')
        attempt = read(f'attempt-{index:02d}.json'); exact_fields(attempt, {'pair', 'attempt', 'method', 'query', 'started_at', 'auth_values_recorded'})
        if (attempt['pair'] != pair or type(attempt['attempt']) is not int or attempt['attempt'] != 1
                or attempt['method'] != 'GET' or attempt['auth_values_recorded'] is not False
                or not wire.stamp(saved['started_at']) <= wire.stamp(attempt['started_at']) <= wire.stamp(item['observed_at'])):
            raise ValueError('original_no_retry_attempt_required')
        expected = {'pair': ['eq.'+pair], 'exchange': ['eq.bybit'], 'market_type': ['eq.spot'], 'timeframe': ['eq.5m'],
            'select': [','.join(wire.FIELDS)], 'order': ['open_time.desc'], 'limit': ['500']}
        if attempt['query'] != expected or read(f'receipt-{index:02d}.json') != item: raise ValueError('original_native_query_required')
        rows[pair] = wire.exact_rows(raw, pair)
        binding[name] = item['sha256']
    if total > POLICY['maximum_total_body_bytes']: raise ValueError('cohort_HTTP_total_bytes_exceeded')
    return saved, rows, binding, total


def compose(captures, native):
    _guard(); saved, rows, bodies, total = inspect_capture(captures)
    exact_fields(native, {'schema_version', 'capture_sha256', 'as_of', 'trace', 'loaded_value_runtime', 'native', 'exact_parser',
        'scalar_fields_checked', 'scalar_mismatch_count', 'scalar_mismatch_examples', 'all_native_examples_equal_exact_parser',
        'model_fit_prediction_publication_performed', 'historical_availability_verified', 'single_database_transaction_verified',
        'actual_HTTP_requests_this_execution', 'credentials_loaded_this_execution'})
    if (native['schema_version'] != 'native-cohort-HTTP-worker-v1' or native['capture_sha256'] != digest(saved)
            or native['as_of'] != saved['completed_at'] or native['loaded_value_runtime'] != prior.late.cohort.values.REVIEWED_VALUE_RUNTIME
            or any(native[key] is not False for key in ('model_fit_prediction_publication_performed', 'historical_availability_verified', 'single_database_transaction_verified'))
            or type(native['actual_HTTP_requests_this_execution']) is not int or native['actual_HTTP_requests_this_execution'] not in (0, 20)
            or native['credentials_loaded_this_execution'] is not (native['actual_HTTP_requests_this_execution'] == 20)
            or type(native['scalar_fields_checked']) is not int or native['scalar_fields_checked'] != 5*sum(map(len, rows.values()))
            or type(native['scalar_mismatch_count']) is not int or not 0 <= native['scalar_mismatch_count'] <= native['scalar_fields_checked']
            or type(native['all_native_examples_equal_exact_parser']) is not bool):
        raise ValueError('fixed_native_HTTP_value_contract_required')
    if [item['pair'] for item in native['trace']] != POLICY['pairs']: raise ValueError('all_native_HTTP_queries_required')
    for item in native['trace']:
        exact_fields(item, {'pair', 'query', 'response_bytes', 'response_sha256'}); index = POLICY['pairs'].index(item['pair'])
        attempt = prior.late.cohort.values.temporal._read(captures, f'attempt-{index:02d}.json', 65536)
        body = saved['responses'][item['pair']]
        if item['query'] != attempt['query'] or item['response_bytes'] != body['bytes'] or item['response_sha256'] != body['sha256']:
            raise ValueError('native_HTTP_trace_changed')
    cutoff = wire.stamp(native['as_of']); compared = []
    for kind in ('native', 'exact_parser'):
        result = native[kind]; exact_fields(result, {'source_admission', 'all_examples', 'all_examples_sha256', 'selected'})
        if type(result['all_examples']) is not int or not 0 <= result['all_examples'] <= 10000 or result['source_admission']['requested_pairs'] != POLICY['pairs'] or [r['pair'] for r in result['selected']] != POLICY['pairs']:
            raise ValueError('bounded_native_HTTP_examples_required')
    for item in native['native']['selected']:
        exact_fields(item, {'pair', 'example'}); pair = item['pair']; example = item['example']
        feature_match = label_match = None
        if example is not None:
            exact_fields(example, {'pair', 'input_end_time', 'label_end_time', 'feature_hex', 'future_return_hex', 'long_label', 'short_label'})
            end = wire.stamp(example['input_end_time']); label_end = wire.stamp(example['label_end_time'])
            if example['pair'] != pair or label_end != end+timedelta(minutes=20): raise ValueError('fixed_selected_HTTP_label_horizon_required')
            known = {wire.stamp(row['open_time']): row for row in rows[pair]
                if wire.stamp(row['open_time'])+timedelta(minutes=5) <= wire.stamp(row['ingested_at']) <= cutoff}
            feature_times = [end-timedelta(minutes=5*i) for i in reversed(range(120))]
            label_times = [end+timedelta(minutes=5*i) for i in range(1, 4)]
            if any(t not in known for t in feature_times+label_times): raise ValueError('selected_HTTP_example_not_from_complete_known_closed_rows')
            features = prior.late.cohort.features.reference([[str(known[t][key]) for key in wire.NUMERIC] for t in feature_times])
            labels = prior.late.cohort.labels.labels(str(known[end]['close']), str(known[label_times[-1]]['close']), '0.003')
            feature_match = features == example['feature_hex']
            label_match = all(labels[k] == example[k] for k in ('future_return_hex', 'long_label', 'short_label'))
        compared.append({'pair': pair, 'selected_example': example, 'independent_features_match': feature_match, 'independent_labels_match': label_match})
    count = sum(row['selected_example'] is not None for row in compared)
    mismatch = sum(row['independent_features_match'] is False or row['independent_labels_match'] is False for row in compared)
    core = {'schema_version': 'research-cohort-HTTP-audit-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'native_sha256': digest(native), 'capture_sha256': digest(saved), 'original_body_sha256': bodies,
        'capture_started_at': saved['started_at'], 'capture_completed_at': saved['completed_at'],
        'local_HTTP_attempts_in_original_capture': 20, 'HTTP_retries': 0, 'total_original_HTTP_bytes': total,
        'source_rows': sum(map(len, rows.values())), 'scalar_fields_checked': native['scalar_fields_checked'],
        'scalar_mismatch_count': native['scalar_mismatch_count'], 'all_native_examples_equal_exact_parser': native['all_native_examples_equal_exact_parser'],
        'native_all_examples': native['native']['all_examples'], 'native_source_admission': native['native']['source_admission'],
        'independent_feature_components': 7*count, 'independent_label_windows': count, 'independent_sample_mismatches': mismatch, 'samples': compared,
        'evidence_kind': saved['evidence_kind'], 'native_reader_original_local_HTTP_path_exercised': saved['evidence_kind'] == 'actual_local_HTTP_capture', 'historical_first_seen_revision_lineage_verified': False,
        'same_database_transaction_for_all_pairs': False, 'production_service_configuration_or_all_consumers_qualified': False,
        'old_M38_or_M40_windows_repaired': False, 'approved_dataset_or_training_admission': False,
        'model_fit_prediction_provider_calls': 0, 'new_numerical_allowance_created': False,
        'status': 'native_HTTP_values_compatible' if count and not mismatch and not native['scalar_mismatch_count'] and native['all_native_examples_equal_exact_parser'] else 'blocked'}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, project):
    _guard(); directory = Path(directory).absolute(); project = prior.late.cohort.values.private._safe_directory(project)
    prior.late.cohort.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_HTTP_pack_required_no_resume_or_retry')
    profile = prior.late.cohort.values.main_profile(project)
    directory.mkdir(mode=0o700); (directory/'captures').mkdir(mode=0o700)
    write = prior.late.cohort.values.files._write
    write(directory, 'policy.json', POLICY); write(directory, 'binding.json', {'project': str(project), 'main_profile': profile})
    native = _native(project, directory/'captures', 'capture', directory/'native.json')
    report = compose(directory/'captures', native); write(directory, 'audit.json', report)
    return report


def verify(directory, *, replay_native=False):
    _guard(); directory = prior.late.cohort.values.private._safe_directory(directory, private=True)
    read = lambda name: prior.late.cohort.values.temporal._read(directory, name, 524288)
    if read('policy.json') != POLICY: raise ValueError('original_HTTP_policy_changed')
    binding = read('binding.json'); exact_fields(binding, {'project', 'main_profile'})
    if prior.late.cohort.values.main_profile(Path(binding['project'])) != binding['main_profile']: raise ValueError('original_HTTP_main_source_changed')
    native = read('native.json'); report = compose(directory/'captures', native)
    if report != read('audit.json'): raise ValueError('original_HTTP_audit_changed')
    if replay_native:
        # The optional replay is separately retained and never makes HTTP requests or reads keys.
        replay = _native(binding['project'], directory/'captures', 'replay', directory/'replay.json')
        if any(replay[k] != native[k] for k in native if k not in ('actual_HTTP_requests_this_execution', 'credentials_loaded_this_execution')) or replay['actual_HTTP_requests_this_execution'] != 0 or replay['credentials_loaded_this_execution'] is not False:
            raise ValueError('same_HTTP_native_replay_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('capture', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'capture': command.add_argument('--project', type=Path, required=True)
        else: command.add_argument('--replay-native', action='store_true')
    args = parser.parse_args(argv)
    try: result = prepare(args.directory, args.project) if args.command == 'capture' else verify(args.directory, replay_native=args.replay_native)
    except Exception:
        print('Native cohort HTTP audit refused; captures retained; no retry or training authorization'); return 2
    print('Native cohort HTTP audit: '+result['status']+'; training admission disabled'); return 0


if __name__ == '__main__': raise SystemExit(main())
