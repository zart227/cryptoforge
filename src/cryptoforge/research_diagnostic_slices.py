"""Descriptive development time slices; no fitting, inference or data admission."""
import argparse
from datetime import timedelta
import hashlib
from pathlib import Path
import re

from cryptoforge import training_diagnostics as diagnostics
from cryptoforge import research_data_protocol as temporal, research_local_export as private
from cryptoforge import semantic_source_collector as files


POLICY = {'schema_version': 'research-diagnostic-slices-policy-v1',
    'maximum_rows_per_partition': 20000, 'maximum_expected_rows_per_partition': 20000,
    'maximum_pairs': 16, 'maximum_windows': 32, 'maximum_input_bytes': 8388608,
    'maximum_report_bytes': 2097152, 'timeframe_seconds': 300,
    'analysis_kind': 'descriptive_development_only', 'training_admission_enabled': False}
GAP_METRICS = ('brier_score', 'log_loss', 'calibration_error_10')
UNAVAILABLE = {
    'regime_metrics': 'causal_regime_features_and_availability_not_supplied',
    'strategy_return_after_costs': 'prediction_rows_do_not_contain_execution_outcomes',
    'drawdown': 'prediction_rows_do_not_contain_portfolio_equity',
    'turnover': 'prediction_rows_do_not_contain_fills_or_notional',
    'execution_exposure': 'prediction_rows_do_not_contain_positions',
    'cost_sensitivity': 'prediction_rows_do_not_contain_cost_or_execution_model',
    'model_data_execution_accounting_attribution': 'independent_error_provenance_not_supplied',
    'freshness_and_historical_asof': 'original_observation_revision_receipts_not_supplied',
    'hypothesis_failure_history': 'immutable_attempt_history_not_supplied',
}


def implementation():
    return {'slices': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'prediction_metrics': hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest()}


_LOADED = implementation()
_POLICY = diagnostics.canonical(POLICY)


def _guard():
    if implementation() != _LOADED or diagnostics.canonical(POLICY) != _POLICY:
        raise ValueError('diagnostic_slice_source_or_policy_changed')


def _time(value):
    result = diagnostics.timestamp(value)
    if result.second or result.microsecond or result.minute % 5:
        raise ValueError('five_minute_grid_required')
    return result


def validate_protocol(protocol):
    diagnostics.exact_fields(protocol, {'schema_version', 'analysis_kind', 'decision_threshold',
        'pairs', 'partitions', 'windows'})
    if protocol['schema_version'] != 'research-diagnostic-slices-protocol-v1' or protocol['analysis_kind'] != POLICY['analysis_kind']:
        raise ValueError('descriptive_development_protocol_required')
    diagnostics.number(protocol['decision_threshold'], 0, 1)
    pairs = protocol['pairs']
    if (type(pairs) is not list or not 1 <= len(pairs) <= POLICY['maximum_pairs']
            or any(type(pair) is not str or re.fullmatch('[A-Z0-9]{1,20}/[A-Z0-9]{2,10}', pair) is None for pair in pairs)
            or pairs != sorted(set(pairs))):
        raise ValueError('bounded_sorted_unique_pairs_required')
    diagnostics.exact_fields(protocol['partitions'], {'train', 'validation'})
    ranges = {}
    for name, interval in protocol['partitions'].items():
        diagnostics.exact_fields(interval, {'start', 'end'})
        start, end = _time(interval['start']), _time(interval['end'])
        expected = int((end-start).total_seconds()/300)*len(pairs)
        if not start < end or not 1 <= expected <= POLICY['maximum_expected_rows_per_partition']:
            raise ValueError('bounded_development_time_range_required')
        ranges[name] = (start, end)
    if ranges['train'][1] > ranges['validation'][0]:
        raise ValueError('train_validation_time_overlap')
    windows = protocol['windows']
    if type(windows) is not list or not 2 <= len(windows) <= POLICY['maximum_windows']:
        raise ValueError('bounded_development_windows_required')
    seen = set(); grouped = {name: [] for name in ranges}
    for window in windows:
        diagnostics.exact_fields(window, {'id', 'partition', 'start', 'end'})
        identity = window['id']
        if type(identity) is not str or re.fullmatch('[a-z][a-z0-9_]{0,31}', identity) is None or identity in seen:
            raise ValueError('unique_closed_window_id_required')
        seen.add(identity)
        if window['partition'] not in grouped:
            raise ValueError('only_train_validation_windows_allowed')
        start, end = _time(window['start']), _time(window['end'])
        if not ranges[window['partition']][0] <= start < end <= ranges[window['partition']][1]:
            raise ValueError('window_outside_declared_development')
        grouped[window['partition']].append((start, end))
    for name, intervals in grouped.items():
        ordered = sorted(intervals)
        if (not ordered or ordered[0][0] != ranges[name][0] or ordered[-1][1] != ranges[name][1]
                or any(left[1] != right[0] for left, right in zip(ordered, ordered[1:]))):
            raise ValueError('windows_must_tile_partition_without_overlap_or_gaps')
    return ranges


def _metrics(export, rows, threshold):
    if not rows:
        return None
    return diagnostics.build_diagnostics({**export, 'rows': rows}, threshold=threshold)


def _coverage(rows, start, end, pairs):
    slots = int((end-start).total_seconds()/300)
    counts = {pair: sum(row['pair'] == pair for row in rows) for pair in pairs}
    count = len(rows); expected = slots*len(pairs)
    return {'expected_pair_observations': expected, 'observed_pair_observations': count,
        'missing_pair_observations': expected-count, 'observation_coverage_fraction': count/expected,
        'largest_pair_observation_share': max(counts.values())/count if count else None,
        'per_pair': {pair: {'expected': slots, 'observed': counts[pair], 'missing': slots-counts[pair]}
                     for pair in pairs}}


def build(protocol, exports):
    _guard()
    if len(diagnostics.canonical({'protocol': protocol, 'exports': exports}).encode()) > POLICY['maximum_input_bytes']:
        raise ValueError('diagnostic_slice_input_byte_limit')
    ranges = validate_protocol(protocol)
    diagnostics.exact_fields(exports, {'train', 'validation'})
    full = {}; normalized = {}
    for partition, export in exports.items():
        diagnostics.exact_fields(export, diagnostics.EXPORT_FIELDS)
        if export['partition'] != partition or _time(export['development_end']) != ranges[partition][1]:
            raise ValueError('explicit_partition_information_boundary_required')
        if type(export['rows']) is not list or not 1 <= len(export['rows']) <= POLICY['maximum_rows_per_partition']:
            raise ValueError('bounded_development_observations_required')
        full[partition] = diagnostics.build_diagnostics(export, threshold=protocol['decision_threshold'])
        diagnostics.validate_diagnostics(full[partition])
        normalized[partition] = []
        for row in export['rows']:
            opened = _time(row['open_time'])
            if row['pair'] not in protocol['pairs'] or not ranges[partition][0] <= opened < ranges[partition][1]:
                raise ValueError('observation_outside_declared_partition_or_pairs')
            _time(row['label_end_time'])
            normalized[partition].append({**row, 'open_time': opened.isoformat(),
                'label_end_time': diagnostics.timestamp(row['label_end_time']).isoformat()})
        normalized[partition].sort(key=lambda row: (row['pair'], row['open_time']))
    if any(exports['train'][name] != exports['validation'][name] for name in ('dataset_sha256', 'source_sha256')):
        raise ValueError('same_declared_dataset_and_source_required')
    groups = []
    for window in sorted(protocol['windows'], key=lambda window: (_time(window['start']), window['id'])):
        partition = window['partition']; start, end = _time(window['start']), _time(window['end'])
        rows = [row for row in normalized[partition] if start <= diagnostics.timestamp(row['open_time']) < end]
        metrics = _metrics(exports[partition], rows, protocol['decision_threshold'])
        information_end = max((diagnostics.timestamp(row['label_end_time']) for row in rows), default=None)
        groups.append({'id': window['id'], 'partition': partition, 'start': start.isoformat(), 'end': end.isoformat(),
            'status': 'observed' if rows else 'unavailable',
            'coverage': _coverage(rows, start, end, protocol['pairs']),
            'metrics': metrics['evidence'] if metrics else None,
            'observations_sha256': metrics['observations_sha256'] if metrics else None,
            'label_information_end': information_end.isoformat() if information_end else None,
            'labels_ending_after_slice_boundary': sum(diagnostics.timestamp(row['label_end_time']) > end for row in rows),
            'slice_is_independent_test': False})
    gap = {name: full['validation']['evidence']['overall'][name]-full['train']['evidence']['overall'][name]
           for name in GAP_METRICS}
    spread = {}
    for partition in ('train', 'validation'):
        available = [group['metrics']['overall'] for group in groups if group['partition'] == partition and group['metrics']]
        spread[partition] = {name: max(metric[name] for metric in available)-min(metric[name] for metric in available)
            if len(available) > 1 else None for name in GAP_METRICS}
    core = {'schema_version': 'research-diagnostic-slices-v1', 'analysis_kind': POLICY['analysis_kind'],
        'protocol_sha256': diagnostics.digest(protocol), 'policy_sha256': diagnostics.digest(POLICY),
        'normalized_exports_sha256': diagnostics.digest({name: {**exports[name], 'rows': normalized[name]} for name in exports}),
        'dataset_sha256': exports['train']['dataset_sha256'], 'source_sha256': exports['train']['source_sha256'],
        'decision_threshold': protocol['decision_threshold'], 'partitions': full, 'time_windows': groups,
        'partition_coverage': {name: _coverage(normalized[name], *ranges[name], protocol['pairs']) for name in exports},
        'gap_direction': 'validation_minus_train', 'train_validation_gap': gap,
        'descriptive_window_metric_spread': spread,
        'unavailable': {name: {'value': None, 'reason': reason} for name, reason in UNAVAILABLE.items()},
        'regimes_computed': False, 'strategy_economics_computed': False,
        'upstream_data_admission_verified': False, 'original_revision_lineage_verified': False,
        'purge_and_embargo_qualified': False, 'statistical_significance_established': False,
        'independent_test_accessed': False, 'fit_performed': False, 'model_prediction_performed': False,
        'provider_called': False, 'candidate_numeric_worker_executed': False,
        'training_data_admitted': False, 'production_promotion_authorized': False, 'implementation': _LOADED}
    result = {**core, 'report_sha256': diagnostics.digest(core)}
    if len(diagnostics.canonical(result).encode()) > POLICY['maximum_report_bytes']:
        raise ValueError('diagnostic_slice_report_byte_limit')
    _guard()
    return result


def prepare(directory, protocol, exports):
    directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('new_diagnostic_slice_directory_required')
    report = build(protocol, exports)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('protocol.json', protocol), ('train-export.json', exports['train']),
                        ('validation-export.json', exports['validation']), ('report.json', report)):
        files._write(directory, name, value)
    files._sync(directory); files._sync(directory.parent)
    return report


def verify(directory):
    directory = private._safe_directory(directory, private=True)
    read = lambda name, maximum: temporal._read(directory, name, maximum)
    if read('policy.json', 16000) != POLICY:
        raise ValueError('fixed_diagnostic_slice_policy_required')
    report = build(read('protocol.json', 32000), {name: read(name+'-export.json', POLICY['maximum_input_bytes'])
                                              for name in ('train', 'validation')})
    if diagnostics.canonical(report) != diagnostics.canonical(read('report.json', POLICY['maximum_report_bytes'])):
        raise ValueError('diagnostic_slice_evidence_or_implementation_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--input', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            payload = temporal._read(args.input.parent, args.input.name, POLICY['maximum_input_bytes'])
            diagnostics.exact_fields(payload, {'schema_version', 'protocol', 'exports'})
            if payload['schema_version'] != 'research-diagnostic-slices-input-v1':
                raise ValueError('closed_development_slice_input_required')
            report = prepare(args.directory, payload['protocol'], payload['exports'])
        else:
            report = verify(args.directory)
    except Exception:
        print('Development diagnostic slices refused; training admission disabled'); return 2
    print('Development diagnostic slices verified: '+str(len(report['time_windows']))+' windows; training admission disabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
