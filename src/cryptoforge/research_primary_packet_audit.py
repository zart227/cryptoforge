"""Read saved primary examples and reported diagnostics without fitting or inference."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import math
from pathlib import Path
import re

from cryptoforge import research_model_inventory as registry
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp

private = registry.local; files = registry.files
POLICY = {'schema_version': 'research-primary-packet-policy-v1', 'maximum_compressed_bytes': 4194304,
    'maximum_uncompressed_bytes': 4194304, 'maximum_runtime_bytes': 1048576,
    'maximum_examples': 10000, 'maximum_pairs': 32, 'maximum_sources': 16,
    'maximum_report_bytes': 262144, 'feature_count': 7, 'timeframe_seconds': 300,
    'horizon_candles': 3, 'reported_prediction_threshold': 0.5,
    'training_admission_enabled': False, 'model_prediction_enabled': False}
SPLITS = ('train', 'validation', 'test')
META_KEYS = ('data_snapshot_at', 'timeframe', 'feature_calculation_contract', 'feature_lookback_candles',
    'horizon_candles', 'min_label_return', 'round_trip_cost', 'implementation_hashes',
    'source_admission', 'runtime_source_bundle')


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'registry': registry.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fixed_primary_packet_implementation_required')


def _gzip(reference, project, schema, maximum):
    if reference.get('schema_version') != schema or reference.get('compression') != 'gzip':
        raise ValueError('fixed_primary_snapshot_reference_required')
    size = reference.get('uncompressed_bytes'); checksum = reference.get('sha256')
    registry.bridge._sha(checksum)
    path = Path(reference['path']); base = project/'.local/models/input-snapshots'
    if (not path.is_absolute() or path.resolve() != path or not path.is_relative_to(base)
            or path.name != checksum+'.json.gz' or type(size) is not int or not 0 < size <= maximum):
        raise ValueError('original_bounded_content_addressed_snapshot_required')
    private._safe_directory(path.parent)
    raw = private._private_read(path.parent, path.name, POLICY['maximum_compressed_bytes'])
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        decoded = stream.read(size+1)
    if len(decoded) != size or hashlib.sha256(decoded).hexdigest() != checksum:
        raise ValueError('original_primary_snapshot_checksum_required')
    return strict_json(decoded.decode(), max_bytes=maximum), {'path': str(path),
        'compressed_sha256': hashlib.sha256(raw).hexdigest(), 'uncompressed_sha256': checksum,
        'compressed_bytes': len(raw), 'uncompressed_bytes': size}


def bind(directory, project):
    _guard(); directory = private._safe_directory(directory, private=True); project = private._safe_directory(project)
    registry.verify(directory)
    saved = registry.bridge._read(directory, 'snapshot.json', registry.POLICY['max_snapshot_bytes'])
    rows = saved['events']['model.candidate']
    if not rows or type(rows[0]['payload'].get('artifact')) is not dict:
        raise ValueError('original_embedded_candidate_required')
    artifact = rows[0]['payload']['artifact']; config = artifact['config']
    snapshot, source = _gzip(config['training_input_snapshot'], project,
        'primary-training-input-snapshot-v1', POLICY['maximum_uncompressed_bytes'])
    runtime, bundle = _gzip(config['runtime_source_bundle'], project,
        'primary-runtime-sources-v1', POLICY['maximum_runtime_bytes'])
    hashes = {n: hashlib.sha256(private._private_read(directory, n, 1048576)).hexdigest()
        for n in ('policy.json', 'snapshot.json', 'native-replay.json', 'inventory.json')}
    binding = {'schema_version': 'research-primary-packet-binding-v1', 'registry': str(directory),
        'project': str(project), 'registry_files': hashes, 'candidate_event_id': rows[0]['id'],
        'candidate_artifact_sha256': rows[0]['payload']['artifact_sha256'], 'candidate_event_time': rows[0]['occurred_at'],
        'snapshot': source, 'runtime_bundle': bundle}
    return binding, artifact, snapshot, runtime


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('finite_primary_packet_number_required')
    return value


def _metric(metric, diagnostics, labels, train_rate):
    n = len(labels); positive = sum(labels)
    exact_fields(metric, {'split', 'count', 'accuracy', 'precision', 'recall', 'positive_rate'})
    if type(metric['count']) is not int or metric['count'] != n:
        raise ValueError('saved_metric_count_differs_from_snapshot')
    for k in ('accuracy', 'precision', 'recall', 'positive_rate'):
        _number(metric[k], 0, 1)
    signals = round(metric['positive_rate']*n); tp = round(metric['precision']*signals)
    fp = signals-tp; fn = positive-tp; tn = n-positive-fp
    if (min(tp, fp, fn, tn) < 0 or metric['accuracy'] != (tp+tn)/n
            or metric['precision'] != tp/max(signals, 1) or metric['recall'] != tp/max(positive, 1)
            or metric['positive_rate'] != signals/n):
        raise ValueError('reported_confusion_counts_inconsistent_with_original_labels')
    if (diagnostics['count'] != n or type(diagnostics['count']) is not int
            or diagnostics['observed_positive_rate'] != positive/n
            or diagnostics['train_positive_rate'] != train_rate
            or diagnostics['fixed_threshold'] != .5 or diagnostics['signals'] != signals
            or type(diagnostics['signals']) is not int or diagnostics['selection_uses_these_diagnostics'] is not False
            or diagnostics['live_profitability_established'] is not False):
        raise ValueError('reported_diagnostics_inconsistent_with_original_labels')
    baseline = min(max(train_rate, 1e-12), 1-1e-12)
    baseline_brier = sum((baseline-y)**2 for y in labels)/n
    baseline_log_loss = sum(-y*math.log(baseline)-(1-y)*math.log(1-baseline) for y in labels)/n
    if diagnostics['baseline_brier'] != baseline_brier or diagnostics['baseline_log_loss'] != baseline_log_loss:
        raise ValueError('train_prior_baseline_differs_from_original_labels')
    brier = _number(diagnostics['brier'], 0, 1); log_loss = _number(diagnostics['log_loss'], 0, 100)
    negative_accuracy = (n-positive)/n
    return {'count': n, 'target_positives': positive, 'target_prevalence': positive/n,
        'reported_predicted_positives': signals, 'reported_prediction_positive_rate': signals/n,
        'reported_confusion_counts': {'true_positive': tp, 'false_positive': fp, 'true_negative': tn, 'false_negative': fn},
        'reported_accuracy': metric['accuracy'], 'always_negative_class_accuracy': negative_accuracy,
        'accuracy_minus_always_negative_class': metric['accuracy']-negative_accuracy,
        'reported_model_brier': brier, 'independent_train_prior_brier': baseline_brier,
        'reported_brier_improvement': baseline_brier-brier,
        'reported_model_log_loss': log_loss, 'independent_train_prior_log_loss': baseline_log_loss,
        'reported_log_loss_improvement': baseline_log_loss-log_loss,
        'reported_average_precision': diagnostics['average_precision'],
        'model_predictions_independently_recomputed': False}


def compose(binding, artifact, snapshot, runtime, audited_at):
    _guard(); now = timestamp(audited_at); config = artifact['config']; metadata = snapshot['metadata']
    exact_fields(snapshot, {'schema_version', 'metadata', 'splits', 'target_version', 'source_kind', 'counts_as_real_executed_buys'})
    exact_fields(metadata, {*META_KEYS, 'feature_names', 'feature_version'})
    exact_fields(runtime, {'schema_version', 'sources', 'python_version', 'python_implementation', 'machine',
        'automatically_execute_archived_code'})
    if (snapshot.get('schema_version') != 'primary-training-input-snapshot-v1'
            or snapshot.get('target_version') != 'fixed-future-return-v1'
            or snapshot.get('counts_as_real_executed_buys') is not False
            or snapshot.get('source_kind') != 'historical_candle_primary_examples'
            or artifact['model_family'] != 'pure-python-logistic' or artifact['feature_version'] != 'candle-v1'
            or artifact['threshold'] != .5 or any(metadata[k] != config[k] for k in META_KEYS)
            or metadata['timeframe'] != '5m' or metadata['horizon_candles'] != 3
            or metadata['feature_lookback_candles'] != 120
            or metadata['feature_calculation_contract'] != 'bounded-window-candle-v1'
            or artifact['feature_names'] != ['return_1', 'return_3', 'range_12', 'volume_ratio', 'ema_gap', 'rsi_14', 'candle_body']
            or metadata['feature_names'] != artifact['feature_names'] or metadata['feature_version'] != 'candle-v1'
            or runtime['schema_version'] != 'primary-runtime-sources-v1'):
        raise ValueError('fixed_primary_packet_contract_required')
    as_of = timestamp(metadata['data_snapshot_at']); threshold = _number(config['min_label_return'], 0, .1)
    _number(config['round_trip_cost'], 0, .1)
    if as_of > now: raise ValueError('primary_packet_audit_before_capture')
    exact_fields(snapshot['splits'], set(SPLITS))
    pairs = artifact['pairs']
    if (type(pairs) is not list or not 1 <= len(pairs) <= 32 or len(set(pairs)) != len(pairs)
            or any(type(p) is not str or re.fullmatch(r'[A-Z0-9]{1,24}/USDT', p) is None for p in pairs)):
        raise ValueError('bounded_primary_pairs_required')
    if type(runtime.get('sources')) is not dict or not 1 <= len(runtime['sources']) <= 16 or runtime.get('automatically_execute_archived_code') is not False:
        raise ValueError('bounded_nonexecuted_runtime_bundle_required')
    expected = config['implementation_hashes']; actual = {}; current = {}
    for name, record in runtime['sources'].items():
        if type(record['source_utf8']) is not str or len(record['source_utf8'].encode()) > 512000:
            raise ValueError('bounded_archived_source_required')
        actual[name] = hashlib.sha256(record['source_utf8'].encode()).hexdigest()
        if actual[name] != record['sha256']: raise ValueError('original_runtime_source_checksum_required')
        filename = record['module_filename']
        if type(filename) is not str or re.fullmatch(r'[a-z_]{1,80}\.py', filename) is None:
            raise ValueError('plain_runtime_module_filename_required')
        path = Path(binding['project'])/'src/cryptoforge'/filename
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 512000:
            raise ValueError('bounded_current_primary_source_required')
        current[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected: raise ValueError('runtime_bundle_differs_from_fitted_source')
    seen = set(); summary = {}; total = 0
    for split in SPLITS:
        rows = snapshot['splits'][split]
        if type(rows) is not list or not rows or total+len(rows) > 10000:
            raise ValueError('bounded_nonempty_primary_splits_required')
        total += len(rows); opened = []; ends = []; counts = Counter()
        for row in rows:
            exact_fields(row, {'pair', 'open_time', 'label_end_time', 'features', 'future_return', 'label', 'short_label'})
            start, end = timestamp(row['open_time']), timestamp(row['label_end_time'])
            if (row['pair'] not in pairs or (row['pair'], start) in seen or start.second or start.microsecond or start.minute % 5
                    or (end-start).total_seconds() != 1200 or not start < end <= as_of
                    or type(row['features']) is not list or len(row['features']) != 7):
                raise ValueError('original_primary_example_identity_or_horizon_required')
            seen.add((row['pair'], start)); opened.append(start); ends.append(end); counts[row['pair']] += 1
            for feature in row['features']: _number(feature, -1e100, 1e100)
            future = _number(row['future_return'], -1, 1e100)
            if (any(type(row[k]) is not int or row[k] not in (0, 1) for k in ('label', 'short_label'))
                    or row['label'] != int(future > threshold) or row['short_label'] != int(future < -threshold)):
                raise ValueError('original_primary_label_vs_return_required')
        if opened != sorted(opened): raise ValueError('chronological_primary_examples_required')
        summary[split] = {'count': len(rows), 'first_input_open': min(opened).isoformat(),
            'last_input_open': max(opened).isoformat(), 'last_label_end': max(ends).isoformat(), 'by_pair_counts': dict(sorted(counts.items()))}
    if {s: summary[s]['count'] for s in SPLITS} != config['training_input_snapshot']['split_counts']:
        raise ValueError('original_snapshot_split_counts_required')
    for left, right in zip(SPLITS, SPLITS[1:]):
        if timestamp(summary[left]['last_label_end']) >= timestamp(summary[right]['first_input_open']):
            raise ValueError('primary_purged_split_boundary_required')
    if (config['training_label_end'] != summary['train']['last_label_end']
            or config['fit_information_end'] != summary['validation']['last_label_end']
            or config['evaluation_information_end'] != summary['test']['last_label_end']):
        raise ValueError('primary_packet_information_boundaries_required')
    heads = {}
    for head, label, key in (('long', 'label', 'metrics'), ('short', 'short_label', 'short_metrics')):
        metrics = artifact[key]
        if type(metrics) is not list or len(metrics) != 3 or {m['split'] for m in metrics} != set(SPLITS):
            raise ValueError('three_reported_primary_metrics_required')
        train_labels = [r[label] for r in snapshot['splits']['train']]; prior = sum(train_labels)/len(train_labels)
        heads[head] = {split: _metric(next(m for m in metrics if m['split'] == split),
            artifact['probability_diagnostics'][head][split], [r[label] for r in snapshot['splits'][split]], prior) for split in SPLITS}
    admission = config['source_admission']; original = admission['examples']
    if type(original) is not int or original < total: raise ValueError('source_admission_example_accounting_required')
    core = {'schema_version': 'research-primary-packet-audit-v1', 'status': 'saved_primary_packet_consistent',
        'audited_at': now.isoformat(), 'binding_sha256': digest(binding), 'implementation': _LOADED,
        'policy_sha256': digest(POLICY), 'candidate_artifact_sha256': binding['candidate_artifact_sha256'],
        'candidate_event_time': binding['candidate_event_time'], 'model_version': artifact['model_version'],
        'snapshot_examples': total, 'source_admission_reported_examples': original,
        'examples_not_in_saved_splits': original-total, 'splits': summary, 'heads': heads,
        'declared_pair_count': len(pairs), 'reported_source_coverage': admission['coverage_fraction'],
        'data_snapshot_at': metadata['data_snapshot_at'], 'fit_information_end': config['fit_information_end'],
        'evaluation_information_end': config['evaluation_information_end'],
        'all_archived_source_hashes_match_fitted_source': True, 'current_source_matches_fitted_source': current == actual,
        'runtime_source_count': len(actual), 'derived_examples_only_no_original_OHLCV_rows': True,
        'historical_first_seen_revision_lineage_verified': False, 'native_reader_selection_verified': False,
        'model_metrics_independently_recomputed': False, 'reported_metrics_label_consistency_verified': True,
        'all_existing_splits_now_declared_exposed_development_data': True,
        'exposures': [{'pair': pair, 'split': split, 'input_start': summary[split]['first_input_open'],
            'input_end': summary[split]['last_input_open'], 'label_end': summary[split]['last_label_end'],
            'labels_and_reported_metrics_observed': True} for split in SPLITS for pair in pairs],
        'training_data_admitted': False, 'fit_performed': False, 'standardizer_refit_performed': False,
        'model_prediction_performed': False, 'archived_source_executed': False, 'database_accessed': False,
        'provider_called': False, 'new_budget_actions': 0, 'production_promotion_authorized': False,
        'classification_baselines_are_trading_profitability_evidence': False}
    report = {**core, 'audit_sha256': digest(core)}
    if len(canonical(report).encode()) > POLICY['maximum_report_bytes']: raise ValueError('primary_packet_report_byte_limit')
    return report


def prepare(directory, registry_pack, project):
    _guard(); directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_primary_packet_audit_directory_required')
    bound = bind(registry_pack, project); now = datetime.now(timezone.utc).isoformat(); report = compose(*bound, now)
    if bind(registry_pack, project) != bound: raise ValueError('primary_packet_changed_during_audit')
    directory.mkdir(mode=0o700)
    for n, v in (('policy.json', POLICY), ('binding.json', bound[0]), ('audit.json', report)): files._write(directory, n, v)
    files._sync(directory); return report


def verify(directory):
    _guard(); directory = private._safe_directory(directory, private=True)
    read = lambda n: registry.bridge._read(directory, n, 262144)
    if read('policy.json') != POLICY: raise ValueError('fixed_primary_packet_policy_required')
    binding = read('binding.json'); bound = bind(binding['registry'], binding['project']); saved = read('audit.json')
    if binding != bound[0]: raise ValueError('original_primary_packet_binding_changed')
    report = compose(*bound, saved['audited_at'])
    if canonical(report) != canonical(saved): raise ValueError('primary_packet_audit_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare':
            command.add_argument('--registry-pack', type=Path, required=True); command.add_argument('--project', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.registry_pack, args.project) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Saved primary packet audit refused; model training and prediction disabled'); return 2
    print('Saved primary packet audit: '+report['status']+'; training admission disabled'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
