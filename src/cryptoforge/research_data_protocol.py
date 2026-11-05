"""Audit development availability and split boundaries; never admits data or fits."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

from cryptoforge import research_local_export as local
from cryptoforge import semantic_source_collector as files
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields


POLICY = {
    'schema_version': 'research-data-protocol-policy-v1',
    'timeframe_seconds': 300, 'feature_window_candles': 120, 'horizon_candles': 3,
    'feature_version': 'candle-v1', 'feature_calculation_contract': 'bounded-window-candle-v1',
    'target_version': 'fixed-future-return-v1', 'max_exports': 8, 'max_rows': 2048,
    'max_symbols': 4, 'max_samples': 4096, 'max_exposures': 128,
    'max_input_bytes': 64000, 'max_report_bytes': 4194304,
    'training_admission_enabled': False,
}
PARTITIONS = ('train', 'validation', 'final_test', 'forward')
EXPORT_FILES = ('policy.json', 'request.json', 'source.json', 'capture.json', 'receipt.json')


def implementation():
    return {'protocol': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'local_export': local.implementation()}


_LOADED = implementation()


def _guard(policy):
    if canonical(policy) != canonical(POLICY):
        raise ValueError('fixed_data_protocol_policy_required')
    if implementation() != _LOADED:
        raise ValueError('data_protocol_source_changed_restart_required')


def _time(value, *, grid=False):
    result = local._utc(value).astimezone(timezone.utc)
    if grid:
        epoch = result - datetime(1970, 1, 1, tzinfo=timezone.utc)
        if result.microsecond or (epoch.days * 86400 + epoch.seconds) % POLICY['timeframe_seconds']:
            raise ValueError('five_minute_grid_required')
    return result


def _sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('source_sha256_required')
    return value


def _read(directory, name, maximum):
    raw = local._private_read(directory, name, maximum)
    return files.strict_json(raw.decode(), max_bytes=maximum)


def validate_protocol(protocol, audited_at):
    exact_fields(protocol, {'schema_version', 'registered_at', 'symbols', 'timeframe_seconds',
        'feature_window_candles', 'feature_version', 'feature_calculation_contract',
        'target_version', 'horizon_candles', 'embargo_candles', 'fit_information_end',
        'validation_information_end', 'decision_delay_seconds', 'partitions'})
    if protocol['schema_version'] != 'research-data-protocol-v1':
        raise ValueError('data_protocol_schema_required')
    for key in ('timeframe_seconds', 'feature_window_candles', 'horizon_candles'):
        if type(protocol[key]) is not int or protocol[key] != POLICY[key]:
            raise ValueError('fixed_candle_target_contract_required')
    for key in ('feature_version', 'feature_calculation_contract', 'target_version'):
        if protocol[key] != POLICY[key]:
            raise ValueError('fixed_candle_target_contract_required')
    symbols = protocol['symbols']
    if (type(symbols) is not list or not 1 <= len(symbols) <= POLICY['max_symbols']
            or any(type(s) is not str or re.fullmatch('[A-Z0-9]{1,24}USDT', s) is None for s in symbols)
            or symbols != sorted(set(symbols))):
        raise ValueError('ordered_unique_symbols_required')
    embargo = protocol['embargo_candles']
    if type(embargo) is not int or not POLICY['horizon_candles'] <= embargo <= 120:
        raise ValueError('bounded_horizon_embargo_required')
    delay = protocol['decision_delay_seconds']
    if type(delay) is not int or not 0 <= delay < POLICY['timeframe_seconds']:
        raise ValueError('bounded_explicit_decision_delay_required')
    now, registered = _time(audited_at), _time(protocol['registered_at'])
    if registered > now:
        raise ValueError('protocol_registration_cannot_be_in_future')
    exact_fields(protocol['partitions'], set(PARTITIONS))
    intervals = {}
    step = timedelta(seconds=POLICY['timeframe_seconds'])
    for name in PARTITIONS:
        raw = protocol['partitions'][name]
        exact_fields(raw, {'decision_start', 'decision_end'})
        start, end = (_time(raw[k], grid=True) for k in ('decision_start', 'decision_end'))
        if not start < end or end - start > timedelta(days=7):
            raise ValueError('bounded_nonempty_partition_required')
        intervals[name] = (start, end)
    for left, right in zip(PARTITIONS, PARTITIONS[1:]):
        if intervals[right][0] - intervals[left][1] < embargo * step:
            raise ValueError('ordered_disjoint_partitions_with_embargo_required')
    if now >= intervals['final_test'][0]:
        raise ValueError('future_unread_final_test_required')
    count = sum(int((intervals[n][1]-intervals[n][0])/step) for n in ('train', 'validation')) * len(symbols)
    if count > POLICY['max_samples']:
        raise ValueError('development_sample_budget_exceeded')
    fit, validation = _time(protocol['fit_information_end']), _time(protocol['validation_information_end'])
    if (not intervals['train'][0] <= fit <= intervals['validation'][0] - embargo * step
            or not intervals['validation'][0] <= validation <= intervals['final_test'][0] - embargo * step):
        raise ValueError('information_cutoffs_must_precede_next_partition')
    return intervals


def validate_exposures(exposure, protocol, audited_at):
    exact_fields(exposure, {'schema_version', 'coverage', 'entries'})
    if (exposure['schema_version'] != 'research-data-exposures-v1'
            or exposure['coverage'] != 'declared_only' or type(exposure['entries']) is not list
            or len(exposure['entries']) > POLICY['max_exposures']):
        raise ValueError('bounded_declared_exposure_inventory_required')
    seen = set()
    for row in exposure['entries']:
        exact_fields(row, {'symbol', 'start', 'end', 'kind', 'source_sha256'})
        if (row['symbol'] not in protocol['symbols'] or row['kind'] not in
                ('market_values_observed', 'model_selection', 'metric_review', 'final_test_used')):
            raise ValueError('closed_exposure_scope_required')
        if not _time(row['start'], grid=True) < _time(row['end'], grid=True) <= _time(audited_at):
            raise ValueError('observed_exposure_interval_required')
        _sha(row['source_sha256'])
        key = digest(row)
        if key in seen:
            raise ValueError('duplicate_exposure_entry')
        seen.add(key)


def _request_allowed(request, protocol, intervals):
    start, end, _ = local.validate_request(request)
    if request['timeframe_seconds'] != POLICY['timeframe_seconds'] or request['symbol'] not in protocol['symbols']:
        raise ValueError('source_scope_differs_from_protocol')
    if end > _time(protocol['validation_information_end']):
        raise ValueError('source_beyond_development_information_cutoff')
    step = timedelta(seconds=POLICY['timeframe_seconds'])
    for name in ('final_test', 'forward'):
        left, right = intervals[name]
        if start < right + POLICY['horizon_candles'] * step and end > left - step:
            raise ValueError('held_out_source_values_must_not_be_read')


def source_reference(directory, protocol, audited_at):
    """Check the request before reading any source/capture values."""
    intervals = validate_protocol(protocol, audited_at)
    directory = local._safe_directory(directory, private=True)
    request = _read(directory, 'request.json', 4000)
    _request_allowed(request, protocol, intervals)
    return {'directory': str(directory), 'files': {
        name: hashlib.sha256(local._private_read(directory, name,
            local.POLICY['max_source_bytes'] if name in ('source.json', 'capture.json') else 16000)).hexdigest()
        for name in EXPORT_FILES}}


def _load_sources(references, protocol, audited_at):
    if type(references) is not list or not 1 <= len(references) <= POLICY['max_exports']:
        raise ValueError('bounded_original_exports_required')
    rows, summaries, receipts = [], [], set()
    ids, candle_ids, versions = {}, {}, {}
    identity = None
    for reference in references:
        exact_fields(reference, {'directory', 'files'})
        exact_fields(reference['files'], set(EXPORT_FILES))
        if type(reference['directory']) is not str or len(reference['directory']) > 4096:
            raise ValueError('bounded_original_export_path_required')
        for value in reference['files'].values():
            _sha(value)
        before = source_reference(reference['directory'], protocol, audited_at)
        if before != reference:
            raise ValueError('original_export_pin_mismatch')
        result = local.read_export(reference['directory'])
        if result['capture'] is None:
            raise ValueError('blocked_local_export_cannot_supply_lineage')
        source = _read(reference['directory'], 'source.json', local.POLICY['max_source_bytes'])
        if source_reference(reference['directory'], protocol, audited_at) != before:
            raise ValueError('original_export_changed_during_read')
        receipt = result['report']
        if receipt['receipt_sha256'] in receipts:
            raise ValueError('duplicate_original_export')
        receipts.add(receipt['receipt_sha256'])
        current_identity = {'database_oid': source['database']['database_oid'],
            'server_address': source['database']['server_address'],
            'server_port': source['database']['server_port'], 'catalog_sha256': receipt['catalog_sha256']}
        if identity is not None and identity != current_identity:
            raise ValueError('local_source_identity_or_catalog_changed')
        identity = current_identity
        known = _time(source['client_observed_at'])
        if known > _time(audited_at):
            raise ValueError('source_observed_after_audit_context')
        for raw in source['rows']:
            opened, closed = _time(raw['open_time'], grid=True), _time(raw['close_time'], grid=True)
            if closed > known:
                raise ValueError('source_observation_precedes_candle_close')
            key = (raw['symbol'], opened.isoformat())
            revision = digest({'identity': identity, 'source_row': raw})
            row_id, version = raw['id'], raw['storage_xmin']
            if row_id in ids and ids[row_id] != key or key in candle_ids and candle_ids[key] != row_id:
                raise ValueError('source_row_identity_moved_or_replaced')
            version_key = (key, row_id, version)
            if version_key in versions and versions[version_key] != revision:
                raise ValueError('same_storage_revision_contains_different_values')
            ids[row_id], candle_ids[key], versions[version_key] = key, row_id, revision
            rows.append({'symbol': raw['symbol'], 'open_time': opened.isoformat(),
                'close_time': closed.isoformat(), 'known_at': known.isoformat(),
                'revision_sha256': revision, 'source_sha256': receipt['source_sha256']})
        if len(rows) > POLICY['max_rows']:
            raise ValueError('source_row_budget_exceeded')
        summaries.append({'source_sha256': receipt['source_sha256'], 'receipt_sha256': receipt['receipt_sha256'],
            'observed_at': known.isoformat(), 'rows': len(source['rows']), 'identity': current_identity,
            'symbol': result['capture']['symbol'], 'start': rows[-len(source['rows'])]['open_time'],
            'end': rows[-1]['close_time']})
    rows.sort(key=lambda r: (r['symbol'], r['open_time'], r['known_at'], r['revision_sha256']))
    return rows, summaries


def _choose(index, symbol, opened, cutoff):
    records = index.get((symbol, opened.isoformat()), [])
    if not records:
        return None, 'missing'
    available = [r for r in records if _time(r['known_at']) <= cutoff]
    if not available:
        return None, 'late'
    latest = max(_time(r['known_at']) for r in available)
    selected = [r for r in available if _time(r['known_at']) == latest]
    if len({r['revision_sha256'] for r in selected}) != 1:
        return None, 'ambiguous'
    return min(selected, key=lambda r: r['source_sha256']), None


def audit(protocol, exposure, references, context, policy=POLICY):
    _guard(policy)
    exact_fields(context, {'schema_version', 'audited_at'})
    if context['schema_version'] != 'research-data-audit-context-v1':
        raise ValueError('data_audit_context_required')
    audited_at = context['audited_at']
    if any(len(canonical(v).encode()) > POLICY['max_input_bytes'] for v in (protocol, exposure, references)):
        raise ValueError('data_protocol_input_byte_limit')
    intervals = validate_protocol(protocol, audited_at)
    validate_exposures(exposure, protocol, audited_at)
    rows, summaries = _load_sources(references, protocol, audited_at)
    index = {}
    for row in rows:
        index.setdefault((row['symbol'], row['open_time']), []).append(row)
    step = timedelta(seconds=POLICY['timeframe_seconds'])
    samples, issue_counts = [], {}
    for partition, next_partition, cutoff_name in (
            ('train', 'validation', 'fit_information_end'),
            ('validation', 'final_test', 'validation_information_end')):
        start, end = intervals[partition]
        cutoff = _time(protocol[cutoff_name])
        for symbol in protocol['symbols']:
            anchor = start
            while anchor < end:
                decision = anchor + timedelta(seconds=protocol['decision_delay_seconds'])
                feature_start = anchor - POLICY['feature_window_candles'] * step
                label_end = anchor + POLICY['horizon_candles'] * step
                features, labels, issues = [], [], set()
                for i in range(POLICY['feature_window_candles']):
                    row, error = _choose(index, symbol, feature_start + i * step, decision)
                    if error:
                        issues.add('feature_' + error)
                    else:
                        features.append(row)
                for i in range(POLICY['horizon_candles']):
                    row, error = _choose(index, symbol, anchor + i * step, cutoff)
                    if error:
                        issues.add('label_' + error)
                    else:
                        labels.append(row)
                if label_end >= intervals[next_partition][0]:
                    issues.add('label_crosses_next_partition_purge')
                if label_end > cutoff:
                    issues.add('label_not_complete_by_information_cutoff')
                for issue in issues:
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1
                samples.append({'partition': partition, 'symbol': symbol, 'decision_anchor': anchor.isoformat(),
                    'decision_time': decision.isoformat(),
                    'feature_window_start': feature_start.isoformat(), 'label_end_time': label_end.isoformat(),
                    'feature_rows_available': len(features), 'label_rows_available': len(labels),
                    'feature_lineage_sha256': digest(features) if len(features) == POLICY['feature_window_candles'] else None,
                    'label_lineage_sha256': digest(labels) if len(labels) == POLICY['horizon_candles'] else None,
                    'metadata_consistency_pass': not issues, 'issues': sorted(issues)})
                anchor += step
    observed_exposures = [{'symbol': s['symbol'], 'start': s['start'], 'end': s['end'],
        'kind': 'market_values_observed', 'source_sha256': s['source_sha256']} for s in summaries]
    conflicts = []
    for i, row in enumerate([*exposure['entries'], *observed_exposures]):
        for name in ('final_test', 'forward'):
            start, end = intervals[name]
            if _time(row['start']) < end + POLICY['horizon_candles'] * step and _time(row['end']) > start:
                conflicts.append({'entry': i, 'partition': name, 'symbol': row['symbol']})
    core = {'schema_version': 'research-data-audit-v1',
        'status': 'blocked' if issue_counts or conflicts else 'metadata_consistent',
        'audited_at': _time(audited_at).isoformat(), 'protocol_sha256': digest(protocol),
        'exposure_sha256': digest(exposure), 'references_sha256': digest(references),
        'context_sha256': digest(context), 'policy_sha256': digest(policy),
        'sources': summaries, 'observed_rows': len(rows), 'timeline_sha256': digest(rows),
        'unique_revisions': len({(r['symbol'], r['open_time'], r['revision_sha256']) for r in rows}),
        'samples': samples, 'sample_count': len(samples), 'sample_issue_counts': dict(sorted(issue_counts.items())),
        'samples_metadata_consistent': sum(s['metadata_consistency_pass'] for s in samples),
        'source_exposures_recorded_automatically': observed_exposures,
        'heldout_exposure_conflicts': conflicts, 'holdout_values_read': False,
        'availability_rule': 'original_client_observed_at_no_storage_timestamp_backfill',
        'feature_selection_rule': 'latest_observed_revision_at_or_before_decision',
        'label_selection_rule': 'latest_observed_revision_at_or_before_partition_information_cutoff',
        'label_end_rule': 'anchor_close_plus_horizon_times_step',
        'exposure_inventory_complete': False, 'historical_poll_completeness_verified': False,
        'append_only_source_history_verified': False, 'protocol_registration_authenticated': False,
        'source_instance_cryptographically_authenticated': False,
        'native_feature_or_label_values_recomputed': False,
        'source_features_labels_parity_verified': False, 'development_split_approved': False,
        'training_data_admitted': False, 'training_executed': False,
        'provider_called': False, 'numeric_worker_executed': False,
        'production_promotion_authorized': False, 'live_connection_rechecked': False,
        'remaining_admission_requirements': ['original_observation_revision_coverage',
            'complete_prior_exposure_inventory', 'approved_protocol_and_split',
            'source_feature_label_values_and_native_evaluator_parity'],
        'implementation': deepcopy(_LOADED)}
    report = {**core, 'audit_sha256': digest(core)}
    if len(canonical(report).encode()) > POLICY['max_report_bytes']:
        raise ValueError('data_audit_report_byte_limit')
    _guard(policy)
    return report


def prepare(directory, protocol, exposure, export_directories):
    _guard(POLICY)
    directory = Path(directory).absolute()
    local._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('new_data_audit_directory_required')
    context = {'schema_version': 'research-data-audit-context-v1',
               'audited_at': datetime.now(timezone.utc).isoformat()}
    validate_protocol(protocol, context['audited_at'])
    validate_exposures(exposure, protocol, context['audited_at'])
    if not 1 <= len(export_directories) <= POLICY['max_exports']:
        raise ValueError('bounded_original_exports_required')
    references = [source_reference(p, protocol, context['audited_at']) for p in export_directories]
    report = audit(protocol, exposure, references, context)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('protocol.json', protocol), ('exposure.json', exposure),
                        ('sources.json', references), ('context.json', context), ('audit.json', report)):
        files._write(directory, name, value)
    files._sync(directory)
    files._sync(directory.parent)
    return report


def verify(directory):
    directory = local._safe_directory(directory, private=True)
    values = {name: _read(directory, name + '.json', POLICY['max_input_bytes'])
              for name in ('policy', 'protocol', 'exposure', 'sources', 'context')}
    report = audit(values['protocol'], values['exposure'], values['sources'], values['context'], values['policy'])
    if canonical(report) != canonical(_read(directory, 'audit.json', POLICY['max_report_bytes'])):
        raise ValueError('data_audit_or_implementation_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        cmd = subs.add_parser(name)
        cmd.add_argument('--directory', type=Path, required=True)
        if name == 'prepare':
            cmd.add_argument('--protocol', type=Path, required=True)
            cmd.add_argument('--exposure', type=Path, required=True)
            cmd.add_argument('--export', dest='exports', action='append', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = verify(args.directory) if args.command == 'verify' else prepare(args.directory,
            _read(args.protocol.parent, args.protocol.name, POLICY['max_input_bytes']),
            _read(args.exposure.parent, args.exposure.name, POLICY['max_input_bytes']), args.exports)
    except Exception:
        print('Data protocol audit refused; training admission disabled')
        return 2
    print('Data protocol audit verified: ' + report['status'] + '; training admission disabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
