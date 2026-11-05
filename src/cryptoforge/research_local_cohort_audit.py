"""Original future local-cache observation/selection/value audit; no training or prediction."""
import argparse
from datetime import timedelta
import gzip
import hashlib
import io
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_value_audit as values
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge import research_feature_reference as features, research_label_reference_worker as labels
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp

POLICY = {'schema_version': 'research-local-cohort-audit-policy-v1', 'maximum_pairs': 20,
    'maximum_rows_per_capture': 10000, 'maximum_source_bytes': 16777216, 'maximum_compressed_bytes': 4194304,
    'maximum_packet_bytes': 8388608, 'maximum_result_bytes': 262144, 'worker_wall_seconds': 15,
    'worker_cpu_seconds': 8, 'worker_memory_bytes': 536870912,
    'comparison': 'exact_binary64_hex_without_tolerance', 'late_recovered_features_used': False,
    'reported_candidate_freshness_seconds': 900,
    'production_reader_qualified': False, 'training_admission_enabled': False}
ROW_FIELDS = set(values.private.COLUMNS)|{'storage_xmin', 'observed_revision_sha256'}
VALUE_FIELDS = ('exchange', 'market_type', 'symbol', 'pair', 'timeframe', 'open_time', 'close_time',
    'open', 'high', 'low', 'close', 'volume', 'turnover', 'source')


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256(Path(__file__).with_name('research_local_cohort_value_worker.py').read_bytes()).hexdigest(),
        'values': values.implementation(), 'feature_reference': hashlib.sha256(Path(features.__file__).read_bytes()).hexdigest(),
        'label_reference': hashlib.sha256(Path(labels.__file__).read_bytes()).hexdigest()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fixed_local_cohort_audit_required')


def validate_source(plan, source, slot):
    if (source['schema_version'] != 'local-primary-cohort-observation-v1' or source['slot_index'] != slot
            or type(source['slot_index']) is not int or source['plan_sha256'] != digest(plan)
            or source['pairs'] != plan['pairs'] or source['fixed_slot'] != plan['capture_slots'][slot]
            or source['source_kind'] != 'local_cache_version_observed_at_client_completion'
            or source['historical_first_seen_backdated'] is not False or source['training_data_admitted'] is not False
            or source['production_reader_equivalence_claimed'] is not False
            or type(source['model_fit_prediction_provider_operations']) is not int or source['model_fit_prediction_provider_operations'] != 0):
        raise ValueError('original_fixed_local_source_scope_required')
    values.private._metadata(source['database']); values.private._catalog(source['columns'], source['unique_keys'])
    observed = timestamp(source['client_observed_at']); ended = timestamp(source['read_completed_at'])
    if (not timestamp(source['database']['read_started_at']) <= ended <= observed
            or not timestamp(plan['capture_slots'][slot]) <= observed <= timestamp(plan['capture_slots'][slot])+timedelta(seconds=35)
            or type(source['table_oid']) is not str or re.fullmatch(r'[0-9]{1,10}', source['table_oid']) is None
            or type(source['rows']) is not list or not 0 <= len(source['rows']) <= 10000):
        raise ValueError('bounded_local_source_clock_namespace_required')
    seen = set(); counts = {p: 0 for p in plan['pairs']}
    for row in source['rows']:
        exact_fields(row, ROW_FIELDS)
        if row['observed_revision_sha256'] != digest({k: v for k, v in row.items() if k != 'observed_revision_sha256'}):
            raise ValueError('original_physical_local_row_revision_required')
        opened = timestamp(row['open_time']); closed = timestamp(row['close_time']); identity = (row['pair'], opened)
        if (row['pair'] not in counts or row['symbol'] != row['pair'].replace('/', '') or identity in seen
                or row['exchange'] != 'bybit' or row['market_type'] != 'spot' or row['timeframe'] != '5m'
                or row['source'] != 'bybit_public_api' or opened.second or opened.microsecond or opened.minute % 5
                or closed-opened != timedelta(minutes=5) or type(row['id']) is not str
                or re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', row['id']) is None
                or type(row['storage_xmin']) is not str or re.fullmatch(r'[0-9]{1,10}', row['storage_xmin']) is None):
            raise ValueError('closed_scope_unique_local_row_required')
        for k in ('ingested_at', 'created_at', 'updated_at'): timestamp(row[k])
        for k in ('open', 'high', 'low', 'close', 'volume', 'turnover'):
            if type(row[k]) is not str or len(row[k]) > 64: raise ValueError('bounded_original_numeric_lexemes_required')
        seen.add(identity); counts[row['pair']] += 1
        if counts[row['pair']] > 500: raise ValueError('latest500_local_pair_row_cap')
    if counts != source['rows_by_pair']: raise ValueError('original_local_source_row_accounting_required')
    return source


def _load(directory):
    _guard(); directory = values.private._safe_directory(directory, private=True)
    read = lambda n, size: values.temporal._read(directory, n, size)
    plan = read('future-plan.json', 64000); freeze = read('capture-freeze.json', 64000)
    if (hashlib.sha256(values.private._private_read(directory, 'future-plan.json', 64000)).hexdigest() != freeze['plan_file_sha256']
            or plan['schema_version'] != 'future-local-primary-cohort-source-v1'
            or not 1 <= len(plan['pairs']) <= 20 or plan['pairs'] != sorted(set(plan['pairs']))
            or timestamp(plan['registered_at']) >= timestamp(plan['decision_anchor'])):
        raise ValueError('original_preregistered_local_cohort_plan_required')
    for n, key in (('capture-worker.py', 'worker_sha256'), ('collect-future.py', 'collector_sha256')):
        if hashlib.sha256((directory/n).read_bytes()).hexdigest() != freeze[key]: raise ValueError('original_local_source_operator_changed')
    for path, expected in freeze['original_journals'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected: raise ValueError('original_research_journal_changed')
    run = values.private._safe_directory(directory/'collection-run', private=True)
    registration = values.temporal._read(run, 'registration.json', 64000)
    complete = values.temporal._read(run, 'complete.json', 64000)
    if (registration['plan_sha256'] != digest(plan) or timestamp(registration['registered_at']) >= timestamp(plan['decision_anchor'])
            or complete['plan_sha256'] != digest(plan) or complete['source_slots_completed'] != [0, 1]
            or complete['source_transactions'] != 2):
        raise ValueError('two_completed_original_local_source_slots_required')
    sources = []; bindings = []
    for slot in (0, 1):
        receipt = values.temporal._read(run, 'receipt-'+str(slot)+'.json', 64000)
        path = run/('source-slot-'+str(slot)+'.json.gz')
        if (receipt['raw_source_path'] != str(path) or receipt['plan_sha256'] != digest(plan)
                or receipt['slot_index'] != slot or type(receipt['uncompressed_bytes']) is not int
                or not 0 < receipt['uncompressed_bytes'] <= 16777216):
            raise ValueError('original_bounded_local_capture_receipt_required')
        raw = values.private._private_read(run, path.name, 4194304)
        if len(raw) != receipt['compressed_bytes'] or hashlib.sha256(raw).hexdigest() != receipt['compressed_sha256']:
            raise ValueError('original_compressed_local_source_changed')
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream: decoded = stream.read(receipt['uncompressed_bytes']+1)
        if len(decoded) != receipt['uncompressed_bytes'] or hashlib.sha256(decoded).hexdigest() != receipt['source_sha256']:
            raise ValueError('original_local_source_payload_changed')
        source = strict_json(decoded.decode(), max_bytes=16777216)
        validate_source(plan, source, slot)
        if source['client_observed_at'] != receipt['client_observed_at'] or len(source['rows']) != receipt['rows']:
            raise ValueError('original_capture_delivery_accounting_required')
        sources.append(source); bindings.append({'slot': slot, 'receipt_sha256': digest(receipt),
            'compressed_sha256': receipt['compressed_sha256'], 'source_sha256': receipt['source_sha256']})
    namespace = lambda s: (s['database']['database_oid'], s['database']['server_address'], s['database']['server_port'], s['table_oid'])
    if namespace(sources[0]) != namespace(sources[1]): raise ValueError('same_original_database_namespace_required')
    return {'directory': str(directory), 'plan_sha256': digest(plan), 'capture_bindings': bindings,
        'database_namespace': list(namespace(sources[0]))}, plan, sources


def _eligible(row, observed):
    return timestamp(row['close_time']) <= timestamp(row['ingested_at']) <= timestamp(observed)


def select(plan, sources):
    anchor = timestamp(plan['decision_anchor']); decision = timestamp(plan['decision_time']); information = timestamp(plan['label_information_end'])
    indexes = [{(r['pair'], timestamp(r['open_time'])): r for r in s['rows'] if _eligible(r, s['client_observed_at'])} for s in sources]
    delivered = [{(r['pair'], timestamp(r['open_time'])): r for r in s['rows']} for s in sources]
    selected = []
    for pair in plan['pairs']:
        groups = []; missing = []; delivery = []
        for slot, opens, cutoff in ((0, [anchor-timedelta(minutes=5*(120-j)) for j in range(120)], decision),
                (1, [anchor+timedelta(minutes=5*j) for j in range(3)], information)):
            found = [indexes[slot].get((pair, opened)) for opened in opens]
            absent = sum(r is None for r in found)
            if timestamp(sources[slot]['client_observed_at']) > cutoff: absent = len(opens)
            missing.append(absent); groups.append(found if not absent else None)
            present = [delivered[slot].get((pair, opened)) for opened in opens]
            delivery.append({'not_delivered': sum(r is None for r in present),
                'delivered_but_not_known_closed': sum(r is not None and not _eligible(r, sources[slot]['client_observed_at']) for r in present)})
        first = [r for (p, _), r in indexes[0].items() if p == pair]
        latest = max((timestamp(r['close_time']) for r in first), default=None)
        recovered = sum((pair, anchor-timedelta(minutes=5*(120-j))) not in indexes[0]
            and (pair, anchor-timedelta(minutes=5*(120-j))) in indexes[1] for j in range(120))
        physical = economic = identities = 0
        if groups[0] is not None:
            for row in groups[0]:
                later = indexes[1].get((pair, timestamp(row['open_time'])))
                if later is not None:
                    physical += row['observed_revision_sha256'] != later['observed_revision_sha256']
                    economic += any(row[k] != later[k] for k in VALUE_FIELDS)
                    identities += row['id'] != later['id']
        selected.append({'pair': pair, 'features': groups[0], 'labels': groups[1],
            'missing_feature_candles': missing[0], 'missing_label_candles': missing[1],
            'latest_eligible_feature_close': None if latest is None else latest.isoformat(),
            'latest_eligible_age_at_decision_seconds': None if latest is None else (decision-latest).total_seconds(),
            'reported_candidate_900s_freshness_check': None if latest is None else (decision-latest).total_seconds() <= 900,
            'feature_row_delivery': delivery[0], 'label_row_delivery': delivery[1],
            'feature_candles_only_observed_later': recovered, 'later_feature_physical_revision_changes': physical,
            'later_feature_value_changes': economic, 'later_feature_row_identity_changes': identities,
            'late_recovered_features_used': False})
    return selected


def _native(project, packet, directory):
    if len(canonical(packet).encode()) > 8388608: raise ValueError('local_cohort_native_packet_cap')
    values.files._write(directory, 'packet.json', packet)
    args = [sys.executable, '-B', str(Path(__file__).with_name('research_local_cohort_value_worker.py')),
        '--input', str(directory/'packet.json'), '--output', str(directory/'result.json')]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    process = None
    with os.fdopen(os.open(directory/'worker.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as log:
        try:
            process = subprocess.Popen(args, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, preexec_fn=values.revisions._limits)
            if process.wait(timeout=15) != 0: raise ValueError('fixed_local_cohort_native_worker_refused')
            return values.temporal._read(directory, 'result.json', 262144)
        finally:
            if process is not None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()


def compose(binding, plan, selections, native):
    _guard()
    exact_fields(native, {'schema_version', 'packet_sha256', 'loaded_value_runtime', 'samples', 'source_rows_read',
        'fit_performed', 'model_prediction_performed', 'provider_or_network_or_database_accessed', 'actual_production_reader_invoked', 'source_modified'})
    packet = {'plan': plan, 'selections': selections}
    if (native['schema_version'] != 'local-cohort-native-values-v1' or native['packet_sha256'] != digest(packet)
            or native['loaded_value_runtime'] != values.REVIEWED_VALUE_RUNTIME or len(native['samples']) != len(selections)
            or any(native[k] is not False for k in ('fit_performed', 'model_prediction_performed',
                'provider_or_network_or_database_accessed', 'actual_production_reader_invoked', 'source_modified'))):
        raise ValueError('fixed_local_cohort_native_contract_required')
    samples = []; components = mismatches = label_windows = label_mismatches = row_count = 0
    for selected, observed in zip(selections, native['samples']):
        exact_fields(observed, {'pair', 'feature_hex', 'runtime_feature_hex', 'training_feature_hex', 'future_return_hex', 'long_label', 'short_label'})
        if observed['pair'] != selected['pair'] or selected['late_recovered_features_used'] is not False:
            raise ValueError('original_fixed_cohort_selection_required')
        feature_match = label_match = None; reference = None
        if selected['features'] is not None:
            row_count += 120; components += 7
            reference = features.reference([[r[k] for k in ('open', 'high', 'low', 'close', 'volume')] for r in selected['features']])
            lists = [observed['feature_hex'], observed['runtime_feature_hex']]
            if selected['labels'] is not None:
                lists.append(observed['training_feature_hex'])
            for array in lists:
                if type(array) is not list or len(array) != 7: raise ValueError('seven_local_native_features_required')
                for number in array: values._hex(number)
            compared = [all(array[i] == reference[i] for array in lists) for i in range(7)]
            mismatches += sum(not ok for ok in compared); feature_match = all(compared)
            if selected['labels'] is not None:
                row_count += 3; label_windows += 1
                expected = labels.labels(selected['features'][-1]['close'], selected['labels'][-1]['close'], plan['min_label_return'])
                if any(type(observed[k]) is not int or observed[k] not in (0, 1) for k in ('long_label', 'short_label')):
                    raise ValueError('binary_local_native_labels_required')
                values._hex(observed['future_return_hex'])
                label_match = all(observed[k] == expected[k] for k in ('future_return_hex', 'long_label', 'short_label'))
                label_mismatches += int(not label_match)
        if selected['features'] is None and any(observed[k] is not None for k in ('feature_hex', 'runtime_feature_hex', 'training_feature_hex')):
            raise ValueError('missing_local_features_cannot_be_fabricated')
        if (selected['features'] is None or selected['labels'] is None) and any(observed[k] is not None for k in ('training_feature_hex', 'future_return_hex', 'long_label', 'short_label')):
            raise ValueError('missing_local_training_horizon_cannot_be_fabricated')
        samples.append({k: v for k, v in selected.items() if k not in ('features', 'labels')} | {
            'feature_values_checked': selected['features'] is not None, 'label_values_checked': label_match is not None,
            'independent_feature_hex': reference, 'independent_features_match_native': feature_match, 'independent_labels_match_native': label_match})
    if type(native['source_rows_read']) is not int or native['source_rows_read'] != row_count:
        raise ValueError('local_native_row_accounting_required')
    core = {'schema_version': 'research-local-cohort-audit-v1',
        'status': 'all_declared_local_samples_compatible' if label_windows == len(samples) and components and mismatches == label_mismatches == 0 else 'blocked',
        'binding_sha256': digest(binding), 'plan_sha256': digest(plan), 'selection_sha256': digest(selections),
        'native_sha256': digest(native), 'policy_sha256': digest(POLICY), 'implementation': _LOADED,
        'samples': samples, 'pair_count': len(samples), 'native_selected_rows_read': row_count,
        'independent_feature_components': components, 'feature_component_mismatches': mismatches,
        'independent_label_windows': label_windows, 'label_mismatch_samples': label_mismatches,
        'late_recovered_features_used': False, 'raw_local_cache_observation_lineage_verified': True,
        'historical_market_publisher_first_seen_verified': False, 'actual_production_reader_invoked': False,
        'native_functions_applied_to_selected_exact_local_rows': True, 'training_data_admitted': False,
        'fit_performed': False, 'model_prediction_performed': False, 'provider_or_database_accessed': False,
        'new_numeric_candidate_actions': 0, 'production_promotion_authorized': False}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, source_directory):
    _guard(); directory = Path(directory).absolute(); values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_local_cohort_audit_directory_required')
    bound = _load(source_directory); binding, plan, sources = bound; selections = select(plan, sources)
    before = values.main_profile(Path(plan['project']))
    with tempfile.TemporaryDirectory(prefix='local-cohort-values-', dir=directory.parent) as tmp:
        native = _native(Path(plan['project']), {'plan': plan, 'selections': selections}, Path(tmp))
    if values.main_profile(Path(plan['project'])) != before or _load(source_directory) != bound:
        raise ValueError('original_local_cohort_or_runtime_changed')
    report = compose(binding, plan, selections, native); directory.mkdir(mode=0o700)
    for n, v in (('policy.json', POLICY), ('binding.json', binding), ('selection.json', selections), ('native.json', native), ('audit.json', report)):
        values.files._write(directory, n, v)
    return report


def verify(directory):
    _guard(); directory = values.private._safe_directory(directory, private=True)
    read = lambda n, size=262144: values.temporal._read(directory, n, size)
    if read('policy.json') != POLICY: raise ValueError('fixed_local_cohort_policy_required')
    saved = read('binding.json'); binding, plan, sources = _load(saved['directory']); selections = select(plan, sources)
    if binding != saved or read('selection.json', 8388608) != selections: raise ValueError('original_local_cohort_selection_changed')
    report = compose(binding, plan, selections, read('native.json'))
    if canonical(report) != canonical(read('audit.json')): raise ValueError('local_cohort_audit_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--source-directory', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.source_directory) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Original local cohort audit refused; training admission disabled'); return 2
    print('Original local cohort audit: '+report['status']+'; training admission disabled'); return 0


if __name__ == '__main__': raise SystemExit(main())
