"""Closed primitive feature inputs and fixed controls; no candidate execution."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import re
from types import MappingProxyType

from cryptoforge import research_code_static as static, semantic_source_collector as files
from cryptoforge import research_training_diagnostics as diagnostics
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp


FIELDS = ('open', 'high', 'low', 'close', 'volume')
POLICY = {'schema_version': 'research-feature-input-policy-v1', 'max_window_candles': 64,
    'exchange': 'bybit', 'market_type': 'spot', 'candle_fields': list(FIELDS),
    'max_capture_candles': 1024, 'max_capture_bytes': 512000,
    'timeframe_seconds': [60, 300, 900, 3600], 'max_price': 1000000000000,
    'max_volume': 1000000000000000, 'max_abs_output': 1000000000000,
    'require_latest_closed_bar': True, 'require_contiguous_window': True,
    'candidate_execution_enabled': False}


def implementation():
    return {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in
        (('feature_windows', __file__), ('static_checker', static.__file__),
         ('canonical', diagnostics.__file__), ('private_files', files.__file__))}


_LOADED = implementation()


def _guard(policy):
    if canonical(policy) != canonical(POLICY): raise ValueError('fixed_feature_input_policy_required')
    if implementation() != _LOADED: raise ValueError('feature_input_implementation_changed_restart_required')
    if (static.POLICY['candle_fields'] != list(FIELDS)
            or static.POLICY['max_window_candles'] != POLICY['max_window_candles']):
        raise ValueError('static_input_contract_mismatch')


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError('finite_bounded_primitive_number_required')
    return 0.0 if value == 0 else float(value)


def _candle(row):
    if type(row) is not dict: raise ValueError('plain_candle_dictionary_required')
    exact_fields(row, set(FIELDS))
    out = {field: _number(row[field], 0, POLICY['max_volume'] if field == 'volume' else POLICY['max_price']) for field in FIELDS}
    if (any(out[field] <= 0 for field in FIELDS if field != 'volume')
            or not out['low'] <= min(out['open'], out['close']) <= max(out['open'], out['close']) <= out['high']):
        raise ValueError('positive_consistent_ohlc_required')
    return out


def validate_window(window):
    if type(window) not in (list, tuple) or not 1 <= len(window) <= POLICY['max_window_candles']:
        raise ValueError('bounded_nonempty_primitive_window_required')
    return [_candle(row) for row in window]


def immutable_window(window):
    return tuple(MappingProxyType(row) for row in validate_window(window))


def validate_output(output):
    if type(output) is not dict: raise ValueError('plain_feature_output_required')
    exact_fields(output, {'value'})
    return {'value': _number(output['value'], -POLICY['max_abs_output'], POLICY['max_abs_output'])}


def _stamp(value):
    parsed = timestamp(value)
    if not 1970 <= parsed.year <= 2100: raise ValueError('bounded_aware_timestamp_required')
    return parsed.astimezone(timezone.utc)


def _seconds(value):
    # Integer epoch arithmetic; no rounding through floating timestamps.
    if value.microsecond: raise ValueError('whole_second_candle_open_required')
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400 + delta.seconds


def prepare(capture, request, policy):
    _guard(policy)
    if type(capture) is not dict or type(request) is not dict:
        raise ValueError('plain_capture_and_request_required')
    if type(capture.get('candles')) is not list or not 1 <= len(capture['candles']) <= POLICY['max_capture_candles']:
        raise ValueError('bounded_candle_capture_required')
    if len(canonical(capture).encode()) > POLICY['max_capture_bytes']: raise ValueError('capture_byte_limit')
    exact_fields(capture, {'schema_version', 'origin', 'source_backend', 'source_export_sha256',
        'captured_at', 'partition', 'development_end', 'exchange', 'market_type', 'symbol', 'timeframe_seconds', 'candles'})
    if (capture['schema_version'] != 'research-candle-capture-v1'
            or capture['origin'] not in ('synthetic_fixture', 'external_unverified')
            or capture['source_backend'] != 'local_postgresql'
            or capture['exchange'] != POLICY['exchange'] or capture['market_type'] != POLICY['market_type']
            or capture['partition'] not in ('train', 'validation')
            or not isinstance(capture['symbol'], str) or re.fullmatch(r'[A-Z0-9]{1,24}USDT', capture['symbol']) is None
            or not isinstance(capture['source_export_sha256'], str)
            or re.fullmatch(r'[a-f0-9]{64}', capture['source_export_sha256']) is None
            or type(capture['timeframe_seconds']) is not int or capture['timeframe_seconds'] not in POLICY['timeframe_seconds']):
        raise ValueError('closed_local_development_capture_required')
    exact_fields(request, {'schema_version', 'decision_time', 'bars'})
    if (request['schema_version'] != 'research-window-request-v1' or type(request['bars']) is not int
            or not 1 <= request['bars'] <= POLICY['max_window_candles']):
        raise ValueError('fixed_bounded_window_request_required')
    decision, captured, development_end = (_stamp(value) for value in
        (request['decision_time'], capture['captured_at'], capture['development_end']))
    if decision > development_end: raise ValueError('decision_after_development_boundary')
    rows = capture['candles']; step = capture['timeframe_seconds']
    if type(rows) is not list or not 1 <= len(rows) <= POLICY['max_capture_candles']:
        raise ValueError('bounded_candle_capture_required')
    seen, eligible = set(), []
    for raw in rows:
        if type(raw) is not dict: raise ValueError('plain_captured_candle_required')
        exact_fields(raw, {'open_time', 'observed_at', *FIELDS})
        opened, observed = _stamp(raw['open_time']), _stamp(raw['observed_at'])
        if _seconds(opened) % step: raise ValueError('candle_grid_alignment_required')
        closed = opened + timedelta(seconds=step)
        if observed < closed: raise ValueError('closed_bar_observation_required')
        if observed > captured or closed > captured or closed > development_end:
            raise ValueError('closed_captured_development_candles_only')
        if opened in seen: raise ValueError('duplicate_or_revised_open_time_requires_separate_capture_history')
        seen.add(opened)
        values = _candle({field: raw[field] for field in FIELDS})
        available = max(closed, observed)
        if available <= decision: eligible.append((opened, available, values))
    selected = sorted(eligible, key=lambda row: row[0])[-request['bars']:]
    # A recent missing/late bar must not silently turn into an older window.
    whole_decision = decision.replace(microsecond=0)
    anchor = whole_decision - timedelta(seconds=_seconds(whole_decision) % step)
    issue = None
    if len(selected) != request['bars']: issue = 'insufficient_closed_known_bars'
    elif selected[-1][0] + timedelta(seconds=step) != anchor: issue = 'latest_closed_bar_unavailable'
    elif any(right[0] - left[0] != timedelta(seconds=step) for left, right in zip(selected, selected[1:])):
        issue = 'non_contiguous_window'
    payload = None if issue else {
        'exchange': capture['exchange'], 'market_type': capture['market_type'],
        'symbol': capture['symbol'], 'timeframe_seconds': step, 'decision_time': decision.isoformat(),
        'bars': request['bars'], 'open_times': [row[0].isoformat() for row in selected],
        'available_at': [row[1].isoformat() for row in selected],
        'window': validate_window([row[2] for row in selected])}
    core = {'schema_version': 'research-feature-window-v1', 'status': 'unavailable' if issue else 'prepared',
        'safe_error': issue, 'origin': capture['origin'], 'source_backend': capture['source_backend'],
        'partition': capture['partition'], 'capture_sha256': digest(capture), 'request_sha256': digest(request),
        'declared_source_export_sha256': capture['source_export_sha256'], 'payload': payload,
        'window_identity_sha256': digest({'policy_sha256': digest(policy), 'payload': payload}) if payload else None,
        'temporal_rules_checked': True, 'upstream_observation_times_verified': False,
        'source_backend_attested': False, 'source_export_verified': False, 'market_coverage_verified': False,
        'development_split_approved': False, 'candidate_executed': False, 'execution_authorized': False,
        'training_executed': False, 'policy_sha256': digest(policy), 'implementation': _LOADED}
    _guard(policy)
    return {**core, 'window_pack_sha256': digest(core)}


def stage_window(directory, capture, request, policy):
    result = prepare(capture, request, policy)
    directory = Path(directory); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', policy), ('request.json', request), ('window.json', result)):
        files._write(directory, name, value)
    files._sync(directory); files._sync(directory.parent)
    return result


def read_window(directory, capture):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir(): raise ValueError('private_window_directory_required')
    result = prepare(capture, files._json(directory, 'request.json', 4000), files._json(directory, 'policy.json', 4000))
    if canonical(files._json(directory, 'window.json', 64000)) != canonical(result):
        raise ValueError('frozen_window_or_implementation_changed')
    return result


def control_pack(policy):
    _guard(policy)
    def candle(value=1.0, volume=1.0): return {'open': value, 'high': value, 'low': value, 'close': value, 'volume': volume}
    windows = [
        {'id': 'single_flat', 'valid': True, 'window': [candle()]},
        {'id': 'rising', 'valid': True, 'window': [candle(1), candle(2)]},
        {'id': 'falling', 'valid': True, 'window': [candle(2), candle(1)]},
        {'id': 'zero_volume', 'valid': True, 'window': [candle(volume=0)]},
        {'id': 'full_64', 'valid': True, 'window': [candle(1 + index / 64) for index in range(64)]},
        {'id': 'small_positive', 'valid': True, 'window': [candle(1e-12)]},
        {'id': 'price_cap', 'valid': True, 'window': [candle(POLICY['max_price'])]},
        {'id': 'empty', 'valid': False, 'window': []},
        {'id': 'too_many', 'valid': False, 'window': [candle()] * 65},
        {'id': 'future_field', 'valid': False, 'window': [{**candle(), 'label': 1}]},
        {'id': 'zero_price', 'valid': False, 'window': [candle(0)]},
        {'id': 'bool_volume', 'valid': False, 'window': [candle(volume=True)]},
        {'id': 'invalid_range', 'valid': False, 'window': [{**candle(), 'low': 2}]},
    ]
    outputs = [
        {'id': 'zero', 'valid': True, 'output': {'value': 0}},
        {'id': 'negative', 'valid': True, 'output': {'value': -1}},
        {'id': 'upper_bound', 'valid': True, 'output': {'value': POLICY['max_abs_output']}},
        {'id': 'bool', 'valid': False, 'output': {'value': True}},
        {'id': 'null', 'valid': False, 'output': {'value': None}},
        {'id': 'extra', 'valid': False, 'output': {'value': 1, 'label': 1}},
        {'id': 'too_large', 'valid': False, 'output': {'value': POLICY['max_abs_output'] + 1}},
    ]
    for cases, key, validator in ((windows, 'window', validate_window), (outputs, 'output', validate_output)):
        for case in cases:
            try: validator(case[key]); accepted = True
            except ValueError: accepted = False
            if accepted is not case['valid']: raise ValueError('independent_fixture_self_check_failed')
    core = {'schema_version': 'research-feature-controls-v1', 'origin': 'fixed_synthetic_controls',
        'policy': deepcopy(policy), 'window_cases': windows, 'output_cases': outputs,
        'static_contract_sha256': digest(static.POLICY), 'implementation': _LOADED,
        'fixtures_self_checked': True, 'candidate_executed': False, 'candidate_controls_executed': False,
        'numerical_or_causal_correctness_proven': False, 'execution_authorized': False}
    return {**core, 'controls_sha256': digest(core)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify', 'controls', 'verify-controls'):
        command = sub.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name in ('prepare', 'verify'): command.add_argument('--capture', type=Path, required=True)
        if name in ('prepare', 'controls'): command.add_argument('--policy', type=Path, required=True)
        if name == 'prepare': command.add_argument('--request', type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path, maximum): return files._json(path.parent, path.name, maximum)
    if args.command == 'prepare':
        result = stage_window(args.directory, read(args.capture, POLICY['max_capture_bytes']),
            read(args.request, 4000), read(args.policy, 4000))
        code = 0 if result['status'] == 'prepared' else 2
    elif args.command == 'verify':
        result = read_window(args.directory, read(args.capture, POLICY['max_capture_bytes']))
        code = 0 if result['status'] == 'prepared' else 2
    elif args.command == 'controls':
        result = control_pack(read(args.policy, 4000)); args.directory.mkdir(mode=0o700)
        files._write(args.directory, 'controls.json', result); files._sync(args.directory); files._sync(args.directory.parent); code = 0
    else:
        if args.directory.is_symlink(): raise ValueError('private_control_directory_required')
        if canonical(files._json(args.directory, 'controls.json', 64000)) != canonical(control_pack(POLICY)):
            raise ValueError('independent_controls_changed')
        code = 0
    print('Feature input/control artifact verified; no candidate or database execution')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
