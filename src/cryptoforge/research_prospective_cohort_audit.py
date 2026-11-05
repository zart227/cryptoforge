"""Retained prospective Bybit20pair source and exact native feature/label checks."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import tempfile

from cryptoforge import research_local_cohort_audit as native
from cryptoforge import research_cohort_http_worker as identity
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp

POLICY = {'schema_version': 'prospective-primary-cohort-audit-policy-v1', 'pairs': identity.PAIRS,
    'maximum_public_GET_attempts': 40, 'maximum_body_bytes': 128000, 'maximum_source_raw_bytes': 5120000,
    'feature_bars': 120, 'label_bars': 3, 'timeframe_seconds': 300, 'min_label_return': '0.003',
    'late_feature_recovery': False, 'model_fit_prediction_provider_actions_enabled': False,
    'production_reader_or_local_database_qualification': False, 'training_admission_enabled': False}


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'native': native.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY: raise ValueError('fixed_prospective_cohort_audit_required')


def _read(directory, name, cap=65536): return native.values.temporal._read(directory, name, cap)
def _raw(directory, name, cap=128000): return native.values.private._private_read(directory, name, cap)


def parse_body(raw, pair, anchor, limit, observed):
    """Public venue rows become typed observations, never historical publisher claims."""
    body = native.strict_json(raw.decode(), max_bytes=128000)
    if type(body) is not dict or type(body.get('retCode')) is not int or body['retCode'] != 0:
        raise ValueError('public_venue_error_response')
    result = body.get('result')
    if type(result) is not dict or result.get('category') != 'spot' or result.get('symbol') != pair.replace('/', ''):
        raise ValueError('public_venue_identity_changed')
    records = result.get('list'); server = body.get('time'); cutoff = timestamp(observed); anchor = timestamp(anchor)
    if type(server) is not int or not 1577836800000 <= server < 4102444800000 or type(records) is not list or len(records) > limit:
        raise ValueError('bounded_public_venue_rows_or_clock_required')
    if datetime.fromtimestamp(server/1000, timezone.utc) < anchor or cutoff < anchor: raise ValueError('source_close_not_observed_after_anchor')
    rows = []; last = None
    for record in records:
        if type(record) is not list or len(record) != 7 or any(type(v) is not str or not 1 <= len(v) <= 64 for v in record):
            raise ValueError('bounded_original_venue_lexemes_required')
        if not re.fullmatch('[0-9]{13}', record[0]): raise ValueError('venue_epoch_milliseconds_required')
        epoch = int(record[0]); opened = datetime.fromtimestamp(epoch/1000, timezone.utc); closed = opened+timedelta(minutes=5)
        if epoch % 300000 or closed > anchor or last is not None and opened >= last: raise ValueError('closed_descending_unique_venue_rows_required')
        last = opened
        for value in record[1:]:
            if re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,24})?', value) is None: raise ValueError('exact_public_numeric_lexemes_required')
            if Decimal(value) > Decimal('1e30'): raise ValueError('bounded_public_numeric_values_required')
        opening, high, low, close, volume, turnover = map(Decimal, record[1:])
        if not 0 < low <= min(opening, close) <= max(opening, close) <= high: raise ValueError('valid_public_OHLC_required')
        rows.append({'pair': pair, 'symbol': pair.replace('/', ''), 'open_time': opened.isoformat(), 'close_time': closed.isoformat(),
            **dict(zip(('open', 'high', 'low', 'close', 'volume', 'turnover'), record[1:])),
            'ingested_at': cutoff.isoformat(), 'observation_kind': 'current_client_source_receipt_not_database_ingest'})
    return rows


def select(plan, observations):
    anchor = timestamp(plan['feature_anchor']); selected = []; details = []
    for pair in POLICY['pairs']:
        groups = []; issues = []
        for slot, count in (('features', 120), ('labels', 3)):
            source = observations[slot][pair]
            rows = source['rows']; cutoff = timestamp(plan['decision_at'] if slot == 'features' else plan['label_information_end'])
            opens = [anchor-timedelta(minutes=5*(120-i)) for i in range(120)] if slot == 'features' else [anchor+timedelta(minutes=5*i) for i in range(3)]
            index = {timestamp(row['open_time']): row for row in rows}
            found = [index.get(opened) for opened in opens]
            missing = sum(row is None for row in found)
            if source['observed_at'] is None or timestamp(source['observed_at']) > cutoff: missing = count
            groups.append(found if not missing else None)
            issues.append({'slot': slot, 'status': source['status'], 'missing_required_rows': missing, 'observed_at': source['observed_at']})
        selected.append({'pair': pair, 'features': groups[0], 'labels': groups[1]})
        details.append({'pair': pair, 'original_feature_window_complete': groups[0] is not None,
            'original_label_horizon_complete': groups[1] is not None, 'source_status': issues, 'late_features_used': False})
    projected = {'decision_anchor': plan['feature_anchor'], 'decision_time': plan['decision_at'],
        'label_information_end': plan['label_information_end'], 'label_end_time': plan['label_close_anchor'], 'min_label_return': '0.003'}
    return projected, selected, details


def load(directory, registration):
    _guard(); directory = native.values.private._safe_directory(directory, private=True)
    registration = native.values.private._safe_directory(registration, private=True)
    plan = _read(directory, 'prospective-plan.json'); frozen = _read(directory, 'capture-freeze.json')
    if plan != _read(registration, 'prospective-plan.json') or frozen != _read(registration, 'capture-freeze.json'):
        raise ValueError('original_frozen_registered_prospective_plan_required')
    if (plan['schema_version'] != 'primary20pair-prospective-source-plan-v1' or plan['pairs'] != POLICY['pairs']
            or plan['scope'] not in ('source_only_diagnostic_not_approved_training_study', 'source_only_synthetic_fixture') or plan['maximum_public_market_GET_attempts'] != 40
            or plan['maximum_retries'] != 0 or plan['new_numerical_allowance_created'] is not False
            or plan['model_fit_prediction_forecasts_or_provider_generations'] != 0
            or not timestamp(plan['registered_at']) <= timestamp(frozen['frozen_at']) < timestamp(plan['feature_anchor'])
            or hashlib.sha256(_raw(directory, 'prospective-plan.json', 65536)).hexdigest() != frozen['plan_sha256']
            or hashlib.sha256(_raw(directory, 'collect-frozen-source.py', 65536)).hexdigest() != frozen['collector_sha256']
            or hashlib.sha256(_raw(registration, 'collector.py', 65536)).hexdigest() != frozen['collector_sha256']):
        raise ValueError('fixed_original_source_only_prospective_scope_required')
    if (plan['feature_lookback'] != 120 or plan['horizon_candles'] != 3 or plan['min_label_return'] != '0.003'
            or timestamp(plan['label_close_anchor']) != timestamp(plan['feature_anchor'])+timedelta(minutes=15)
            or timestamp(plan['decision_at']) != timestamp(plan['feature_anchor'])+timedelta(minutes=2)
            or timestamp(plan['label_information_end']) != timestamp(plan['label_close_anchor'])+timedelta(minutes=2)):
        raise ValueError('fixed_prospective_feature_target_clocks_required')
    run = native.values.private._safe_directory(directory/'collection-run', private=True)
    armed = _read(run, 'armed.json'); complete = _read(run, 'complete.json')
    if plan['scope'] != 'source_only_synthetic_fixture' and timestamp(complete['completed_at']) > datetime.now(timezone.utc):
        raise ValueError('future_real_source_completion_forbidden')
    if (armed['plan_sha256'] != frozen['plan_sha256'] or armed['collector_sha256'] != frozen['collector_sha256']
            or timestamp(armed['armed_at']) >= timestamp(plan['feature_anchor'])
            or complete['schema_version'] != 'primary20pair-source-collection-v1' or complete['plan_sha256'] != frozen['plan_sha256']
            or type(complete['actual_GET_attempts']) is not int or not 0 <= complete['actual_GET_attempts'] <= 40
            or complete['retries'] != 0 or complete['polls_completed'] != 2
            or complete['model_fit_prediction_forecasts_provider_calls_database_writes'] != 0 or complete['source_admission'] is not False):
        raise ValueError('original_prospective_source_completion_required')
    observations = {}; byte_count = attempts = 0; files = {}
    for expected_kind, expected_limit, expected_anchor, slot in zip(('features', 'labels'), (120, 3),
            (plan['feature_anchor'], plan['label_close_anchor']), plan['polls']):
        if slot['kind'] != expected_kind or slot['limit'] != expected_limit or slot['anchor'] != expected_anchor:
            raise ValueError('fixed_two_original_source_slots_required')
        current = native.values.private._safe_directory(run/expected_kind, private=True); saved = _read(current, 'slot.json')
        if saved['kind'] != expected_kind or saved['automatic_retry'] is not False or saved['source_or_model_training_admission'] is not False:
            raise ValueError('original_source_slot_scope_required')
        by_pair = {}; receipts = []
        for index, pair in enumerate(POLICY['pairs']):
            prefix = f'{index:02d}'; receipt = _read(current, prefix+'-receipt.json'); receipts.append(receipt)
            if receipt['pair'] != pair or receipt['retry'] is not False or type(receipt['HTTP_attempted']) is not bool:
                raise ValueError('original_pair_receipt_required')
            observed = receipt['completed_at']; timestamp(observed)
            data = []; status = receipt['status']
            if receipt['HTTP_attempted']:
                attempt = _read(current, prefix+'-attempt.json'); attempts += 1
                from urllib.parse import urlencode
                url = 'https://api.bybit.com/v5/market/kline?'+urlencode({'category': 'spot', 'symbol': pair.replace('/', ''),
                    'interval': '5', 'end': str(int(timestamp(slot['anchor']).timestamp())*1000-1), 'limit': str(slot['limit'])})
                if (attempt['pair'] != pair or attempt['url'] != url or attempt['method'] != 'GET' or type(attempt['attempt']) is not int or attempt['attempt'] != 1
                        or attempt['authorization_headers_or_credentials'] is not False or attempt['plan_sha256'] != frozen['plan_sha256']
                        or not timestamp(slot['starts_at']) <= timestamp(attempt['prepared_at']) <= timestamp(observed)
                        or receipt['request_url_sha256'] != hashlib.sha256(url.encode()).hexdigest()):
                    raise ValueError('fixed_source_request_or_observation_clock_changed')
                raw = _raw(current, prefix+'-body.bin'); byte_count += len(raw)
                if type(receipt['body_bytes']) is not int or receipt['body_bytes'] != len(raw) or receipt['body_sha256'] != hashlib.sha256(raw).hexdigest():
                    raise ValueError('original_source_response_body_changed')
                if status == 'captured':
                    if receipt['http_status'] != 200 or receipt['body_prefix_only'] is not False or timestamp(observed) > timestamp(slot['latest_completion']):
                        raise ValueError('original_successful_source_deadline_changed')
                    try: data = parse_body(raw, pair, slot['anchor'], slot['limit'], observed)
                    except (ValueError, TypeError, UnicodeError): status = 'source_body_not_qualified'
                for name in (prefix+'-attempt.json', prefix+'-body.bin'):
                    files[str((current/name).relative_to(directory))] = hashlib.sha256(_raw(current, name)).hexdigest()
            elif receipt['status'] != 'slot_missed_no_attempt' or receipt['body_bytes'] != 0:
                raise ValueError('original_unattempted_slot_receipt_required')
            files[str((current/(prefix+'-receipt.json')).relative_to(directory))] = hashlib.sha256(_raw(current, prefix+'-receipt.json')).hexdigest()
            by_pair[pair] = {'observed_at': observed if status == 'captured' else None, 'rows': data, 'status': status}
        if (saved['receipts'] != receipts or saved['actual_GET_attempts'] != sum(r['HTTP_attempted'] for r in receipts) or saved['valid_HTTP_captures'] != sum(r['status'] == 'captured' for r in receipts)
                or timestamp(saved['completed_at']) < max(timestamp(r['completed_at']) for r in receipts)
                or timestamp(complete['completed_at']) < timestamp(saved['completed_at'])):
            raise ValueError('original_source_slot_accounting_changed')
        observations[expected_kind] = by_pair
    if attempts != complete['actual_GET_attempts'] or byte_count != complete['total_raw_bytes'] or byte_count > 5120000:
        raise ValueError('original_source_attempt_or_byte_accounting_changed')
    for name in ('prospective-plan.json', 'capture-freeze.json', 'collect-frozen-source.py', 'collection-run/armed.json', 'collection-run/complete.json', 'collection-run/features/slot.json', 'collection-run/labels/slot.json'):
        path = directory/name; files[name] = hashlib.sha256(_raw(path.parent, path.name)).hexdigest()
    binding = {'source_directory': str(directory), 'registered_directory': str(registration), 'original_files': files,
        'plan_sha256': frozen['plan_sha256'], 'actual_source_GET_attempts': attempts, 'total_raw_bytes': byte_count}
    return binding, plan, select(plan, observations)


def compose(binding, plan, selection, result):
    _guard(); projected, selected, details = selection; packet = {'plan': projected, 'selections': selected}
    if (result['schema_version'] != 'local-cohort-native-values-v1' or result['packet_sha256'] != digest(packet)
            or result['loaded_value_runtime'] != native.values.REVIEWED_VALUE_RUNTIME
            or any(result[k] is not False for k in ('fit_performed', 'model_prediction_performed', 'provider_or_network_or_database_accessed', 'actual_production_reader_invoked', 'source_modified'))
            or [r['pair'] for r in result['samples']] != POLICY['pairs']): raise ValueError('fixed_native_prospective_value_contract_required')
    features = labels = components = mismatch = source_rows = 0
    summaries = []
    for expected, observed, detail in zip(selected, result['samples'], details):
        fm = lm = None
        if expected['features'] is not None:
            features += 1; components += 7; source_rows += 120
            reference = native.features.reference([[r[k] for k in ('open', 'high', 'low', 'close', 'volume')] for r in expected['features']])
            fm = reference == observed['feature_hex'] == observed['runtime_feature_hex']
            if expected['labels'] is not None:
                labels += 1; source_rows += 3
                reference_labels = native.labels.labels(expected['features'][-1]['close'], expected['labels'][-1]['close'], '0.003')
                lm = reference == observed['training_feature_hex'] and all(reference_labels[k] == observed[k] for k in ('future_return_hex', 'long_label', 'short_label'))
        elif any(observed[k] is not None for k in ('feature_hex', 'runtime_feature_hex', 'training_feature_hex', 'future_return_hex', 'long_label', 'short_label')):
            raise ValueError('missing_early_features_cannot_be_reconstructed_later')
        if expected['labels'] is None and any(observed[k] is not None for k in ('training_feature_hex', 'future_return_hex', 'long_label', 'short_label')):
            raise ValueError('missing_prospective_labels_cannot_be_invented')
        mismatch += int(fm is False or lm is False)
        summaries.append({**detail, 'independent_feature_values_match': fm, 'independent_label_values_match': lm})
    if type(result['source_rows_read']) is not int or result['source_rows_read'] != source_rows: raise ValueError('native_prospective_source_row_accounting_changed')
    core = {'schema_version': 'prospective-primary-cohort-audit-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'binding_sha256': digest(binding), 'plan_sha256': digest(plan), 'native_sha256': digest(result),
        'evidence_kind': plan['scope'], 'original_public_source_GET_attempts': binding['actual_source_GET_attempts'] if plan['scope'] != 'source_only_synthetic_fixture' else 0,
        'recorded_source_GET_attempts': binding['actual_source_GET_attempts'], 'feature_windows_checked': features,
        'feature_components_checked': components, 'captured_complete_label_horizons': sum(s['labels'] is not None for s in selected), 'complete_feature_and_label_samples': labels, 'source_rows_read': source_rows,
        'sample_mismatches': mismatch, 'samples': summaries, 'all20source_samples_complete': features == labels == 20,
        'clock_synchronization_independently_attested': False, 'publisher_historical_first_seen_or_revision_coverage_verified': False,
        'availability_is_current_client_observation': True, 'old_M31_M38_M40_windows_repaired': False,
        'actual_native_feature_runtime_and_example_functions_invoked': True, 'actual_production_reader_or_local_database_qualified': False,
        'training_data_protocol_or_next_budget_approved': False, 'new_numerical_allowance_created': False,
        'model_fit_prediction_provider_calls': 0, 'statistical_or_economic_advantage_demonstrated': False,
        'status': 'all20_prospective_values_match' if features == labels == 20 and not mismatch else 'partial_or_failed_source_qualification'}
    return {**core, 'audit_sha256': digest(core)}


def prepare(directory, source_directory, registration, project):
    _guard(); directory = Path(directory).absolute(); native.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_prospective_audit_pack_required')
    binding, plan, selected = load(source_directory, registration); project = native.values.private._safe_directory(project)
    binding['project'] = str(project); binding['main_profile'] = native.values.main_profile(project)
    with tempfile.TemporaryDirectory(prefix='prospective-cohort-values-', dir=directory.parent) as temp:
        result = native._native(project, {'plan': selected[0], 'selections': selected[1]}, Path(temp))
    if native.values.main_profile(project) != binding['main_profile']: raise ValueError('original_main_value_source_changed')
    report = compose(binding, plan, selected, result); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', binding), ('native.json', result), ('audit.json', report)):
        native.values.files._write(directory, name, value)
    return report


def verify(directory):
    _guard(); directory = native.values.private._safe_directory(directory, private=True)
    if _read(directory, 'policy.json') != POLICY: raise ValueError('original_prospective_audit_policy_changed')
    saved = _read(directory, 'binding.json'); binding, plan, selected = load(saved['source_directory'], saved['registered_directory'])
    binding['project'] = saved['project']; binding['main_profile'] = native.values.main_profile(Path(saved['project']))
    if binding != saved: raise ValueError('original_prospective_audit_binding_changed')
    report = compose(binding, plan, selected, _read(directory, 'native.json', 262144))
    if report != _read(directory, 'audit.json', 262144): raise ValueError('original_prospective_audit_report_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare':
            for flag in ('source', 'registration', 'project'): command.add_argument('--'+flag, type=Path, required=True)
    args = parser.parse_args(argv)
    try: result = prepare(args.directory, args.source, args.registration, args.project) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Prospective source audit refused; no recovery requests or training authorization'); return 2
    print('Prospective source audit: '+result['status']+'; training admission disabled'); return 0


if __name__ == '__main__': raise SystemExit(main())
