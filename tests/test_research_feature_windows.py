from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from cryptoforge import research_feature_windows as windows
from cryptoforge.training_diagnostics import canonical, digest


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def stamp(seconds): return (START + timedelta(seconds=seconds)).isoformat()


def row(index, *, observed=None, value=None):
    value = float(index + 1) if value is None else value
    return {'open_time': stamp(index * 60), 'observed_at': stamp((index + 1) * 60 if observed is None else observed),
        'open': value, 'high': value, 'low': value, 'close': value, 'volume': 1.0}


def capture(count=4):
    return {'schema_version': 'research-candle-capture-v1', 'origin': 'synthetic_fixture',
        'source_backend': 'local_postgresql', 'source_export_sha256': 'a' * 64,
        'captured_at': stamp(3600), 'partition': 'validation', 'development_end': stamp(7200),
        'exchange': 'bybit', 'market_type': 'spot', 'symbol': 'BTCUSDT',
        'timeframe_seconds': 60, 'candles': [row(index) for index in range(count)]}


def request(*, decision=240, bars=3):
    return {'schema_version': 'research-window-request-v1', 'decision_time': stamp(decision), 'bars': bars}


def prepare(source=None, selection=None):
    return windows.prepare(capture() if source is None else source, request() if selection is None else selection, windows.POLICY)


def test_exact_closed_window_is_sorted_copied_and_never_claims_upstream_authentication():
    source = capture(); source['candles'].reverse(); original = deepcopy(source)
    result = prepare(source)
    assert source == original and result['status'] == 'prepared'
    assert [candle['close'] for candle in result['payload']['window']] == [2.0, 3.0, 4.0]
    assert result['payload']['open_times'] == [stamp(index * 60) for index in range(1,4)]
    assert result['payload']['available_at'] == [stamp(index * 60) for index in range(2,5)]
    for name in ('source_backend_attested', 'source_export_verified', 'market_coverage_verified',
        'development_split_approved', 'upstream_observation_times_verified', 'candidate_executed', 'execution_authorized', 'training_executed'):
        assert result[name] is False
    assert result['window_pack_sha256'] == digest({k:v for k,v in result.items() if k != 'window_pack_sha256'})


def test_appending_future_rows_cannot_change_past_model_window_or_effect_identity():
    before = prepare()
    source = capture(20); source['captured_at'] = stamp(4000); source['source_export_sha256'] = 'b' * 64
    after = prepare(source)
    assert before['payload'] == after['payload']
    assert before['window_identity_sha256'] == after['window_identity_sha256']
    assert before['capture_sha256'] != after['capture_sha256']
    assert before['window_pack_sha256'] != after['window_pack_sha256']


def test_late_observation_never_backfills_earlier_decision_and_unavailable_is_not_zero():
    source = capture(); source['candles'][-1]['observed_at'] = stamp(241)
    early = prepare(source)
    assert early['status'] == 'unavailable' and early['safe_error'] == 'latest_closed_bar_unavailable'
    assert early['payload'] is None and early['window_identity_sha256'] is None
    later = prepare(source, request(decision=241))
    assert later['status'] == 'prepared' and later['payload']['available_at'][-1] == stamp(241)


@pytest.mark.parametrize('decision,expected', [(239, [1.0,2.0,3.0]), (240, [2.0,3.0,4.0]), (241, [2.0,3.0,4.0])])
def test_close_boundary_has_no_open_bar_or_float_rounding(decision, expected):
    result = prepare(selection=request(decision=decision))
    assert result['status'] == 'prepared'
    assert [candle['close'] for candle in result['payload']['window']] == expected


def test_equivalent_timezone_and_microsecond_cutoffs_select_same_closed_bars():
    selected = request(); selected['decision_time'] = '2026-01-01T03:04:00.000001+03:00'
    result = prepare(selection=selected)
    assert result['status'] == 'prepared'
    assert result['payload']['open_times'] == prepare()['payload']['open_times']


def test_missing_middle_bar_does_not_get_interpolated_or_silently_shorten_window():
    source = capture(5); source['candles'].pop(2)
    result = prepare(source, request(decision=300,bars=4))
    assert result['status'] == 'unavailable' and result['safe_error'] == 'non_contiguous_window'
    assert result['payload'] is None


def test_insufficient_history_is_explicit_and_latest_bar_is_required_even_for_one_row():
    result = prepare(capture(2))
    assert result['safe_error'] == 'insufficient_closed_known_bars'
    result = prepare(capture(3),request(bars=1))
    assert result['safe_error'] == 'latest_closed_bar_unavailable'


@pytest.mark.parametrize('change', ['target', 'test_partition', 'cloud_backend', 'fake_attestation',
    'wrong_origin', 'missing_hash', 'bad_symbol', 'bad_timeframe', 'boolean_timeframe',
    'misaligned_open', 'naive_timestamp', 'after_capture', 'open_bar', 'after_development',
    'observed_before_close', 'duplicate', 'revised_duplicate', 'wrong_exchange', 'derivative_market'])
def test_label_or_inconsistent_capture_never_becomes_a_feature_input(change):
    source = capture()
    if change == 'target': source['candles'][0]['label'] = 1
    elif change == 'test_partition': source['partition'] = 'test'
    elif change == 'cloud_backend': source['source_backend'] = 'supabase'
    elif change == 'fake_attestation': source['source_verified'] = True
    elif change == 'wrong_origin': source['origin'] = 'verified_local_database'
    elif change == 'missing_hash': source['source_export_sha256'] = 'bad'
    elif change == 'bad_symbol': source['symbol'] = '../BTCUSDT'
    elif change == 'bad_timeframe': source['timeframe_seconds'] = 7
    elif change == 'boolean_timeframe': source['timeframe_seconds'] = True
    elif change == 'misaligned_open': source['candles'][0]['open_time'] = stamp(1)
    elif change == 'naive_timestamp': source['candles'][0]['observed_at'] = '2026-01-01T00:01:00'
    elif change == 'after_capture': source['candles'][0]['observed_at'] = stamp(4000)
    elif change == 'open_bar': source['captured_at'] = stamp(239)
    elif change == 'after_development': source['development_end'] = stamp(239)
    elif change == 'observed_before_close': source['candles'][0]['observed_at'] = stamp(59)
    elif change == 'wrong_exchange': source['exchange'] = 'other'
    elif change == 'derivative_market': source['market_type'] = 'linear'
    elif change == 'duplicate': source['candles'].append(deepcopy(source['candles'][0]))
    else:
        changed = deepcopy(source['candles'][0]); changed.update(open=10, high=10, low=10, close=10, observed_at=stamp(100))
        source['candles'].append(changed)
    with pytest.raises(ValueError): prepare(source)


@pytest.mark.parametrize('change', ['boolean_bars', 'zero', 'too_many', 'later_cutoff', 'extra_field', 'missing_time'])
def test_request_is_bounded_and_has_no_candidate_selected_extra_fields(change):
    selected = request()
    if change == 'boolean_bars': selected['bars'] = True
    elif change == 'zero': selected['bars'] = 0
    elif change == 'too_many': selected['bars'] = 65
    elif change == 'later_cutoff': selected['decision_time'] = stamp(7201)
    elif change == 'extra_field': selected['future_label'] = 1
    else: del selected['decision_time']
    with pytest.raises(ValueError): prepare(selection=selected)


@pytest.mark.parametrize('window', [[], [{'open':1}], 'window',
    [{'open':True,'high':1,'low':1,'close':1,'volume':1}],
    [{'open':1,'high':1,'low':1,'close':float('nan'),'volume':1}],
    [{'open':1,'high':float('inf'),'low':1,'close':1,'volume':1}],
    [{'open':0,'high':1,'low':0,'close':1,'volume':1}],
    [{'open':1,'high':1,'low':2,'close':1,'volume':1}],
    [{'open':1,'high':1,'low':1,'close':1,'volume':-1}],
    [{'open':1,'high':1,'low':1,'close':1,'volume':10**1000}],
])
def test_runtime_window_contract_refuses_non_primitive_invalid_or_unbounded_data(window):
    with pytest.raises(ValueError): windows.validate_window(window)


def test_immutable_window_does_not_alias_mutable_callers_and_has_no_custom_objects():
    source = [{'open':1,'high':1,'low':1,'close':1,'volume':-0.0}]
    frozen = windows.immutable_window(source)
    source[0]['close'] = 100; source.append(source[0])
    assert len(frozen) == 1 and frozen[0]['close'] == 1.0 and frozen[0]['volume'] == 0.0
    with pytest.raises(TypeError): frozen[0]['close'] = 2
    class Malicious(dict):
        def __getitem__(self,key): pytest.fail('custom candle object executed')
    with pytest.raises(ValueError): windows.validate_window([Malicious(source[0])])


@pytest.mark.parametrize('output', [[], {'value':True}, {'value':None}, {'value':float('inf')},
    {'value':float('nan')}, {'value':1,'extra':2}, {'label':1}, {'value':10**1000}])
def test_feature_output_contract_is_finite_closed_and_bounded(output):
    with pytest.raises(ValueError): windows.validate_output(output)


def test_feature_output_accepts_zero_negative_and_normalizes_only_primitives():
    assert windows.validate_output({'value':-1}) == {'value':-1.0}
    assert windows.validate_output({'value':-0.0}) == {'value':0.0}
    class Evil(dict): pass
    with pytest.raises(ValueError): windows.validate_output(Evil(value=1))


def test_capture_and_source_bounds_are_enforced_without_truncation():
    for source in (capture(0), {**capture(),'candles':[row(0)]*1025},
        {**capture(),'source_export_sha256':'x'*512001}):
        with pytest.raises(ValueError): prepare(source)


@pytest.mark.parametrize('field,value', [('max_window_candles',128), ('require_latest_closed_bar',False),
    ('candidate_execution_enabled',True), ('candidate_execution_enabled',0), ('max_abs_output',10**20)])
def test_policy_cannot_silently_widen_or_enable_execution(field,value):
    with pytest.raises(ValueError): windows.prepare(capture(),request(),{**windows.POLICY,field:value})


def test_frozen_input_verification_rebuilds_against_original_capture_and_detects_tampering(tmp_path):
    directory = tmp_path/'window';result = windows.stage_window(directory,capture(),request(),windows.POLICY)
    assert windows.read_window(directory,capture()) == result
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
    with pytest.raises(FileExistsError): windows.stage_window(directory,capture(),request(),windows.POLICY)
    changed = capture(); changed['candles'][0]['volume'] = 2
    with pytest.raises(ValueError,match='frozen_window'): windows.read_window(directory,changed)
    (directory/'window.json').write_text('{}')
    with pytest.raises(ValueError,match='frozen_window'): windows.read_window(directory,capture())


def test_window_reader_rejects_symlinked_directory_and_files(tmp_path):
    directory=tmp_path/'window';windows.stage_window(directory,capture(),request(),windows.POLICY)
    alias=tmp_path/'alias';alias.symlink_to(directory,target_is_directory=True)
    with pytest.raises(ValueError):windows.read_window(alias,capture())
    target=tmp_path/'external-request.json';target.write_text(canonical(request()))
    (directory/'request.json').unlink();(directory/'request.json').symlink_to(target)
    with pytest.raises((ValueError,OSError)):windows.read_window(directory,capture())


def test_fixed_independent_controls_self_check_and_are_not_candidate_test_results():
    pack=windows.control_pack(windows.POLICY)
    assert len(pack['window_cases']) == 13 and len(pack['output_cases']) == 7
    assert pack['fixtures_self_checked'] and not pack['candidate_controls_executed']
    assert not pack['numerical_or_causal_correctness_proven'] and not pack['candidate_executed']
    assert pack['controls_sha256'] == digest({k:v for k,v in pack.items() if k!='controls_sha256'})
    pack['window_cases'][0]['window'][0]['close']=100
    assert windows.control_pack(windows.POLICY)['window_cases'][0]['window'][0]['close']==1.0


def test_changed_implementation_is_rejected_before_materialization(tmp_path,monkeypatch):
    changed=deepcopy(windows._LOADED);changed['feature_windows']='0'*64
    monkeypatch.setattr(windows,'_LOADED',changed)
    with pytest.raises(ValueError,match='implementation_changed'):
        windows.stage_window(tmp_path/'window',capture(),request(),windows.POLICY)
    assert not (tmp_path/'window').exists()


def test_cli_materializes_and_verifies_window_controls_and_unavailable_status(tmp_path):
    source=tmp_path/'capture.json';source.write_text(canonical(capture()))
    selected=tmp_path/'request.json';selected.write_text(canonical(request()))
    policy=tmp_path/'policy.json';policy.write_text(canonical(windows.POLICY))
    directory=tmp_path/'window'
    assert windows.main(['prepare','--directory',str(directory),'--capture',str(source),'--request',str(selected),'--policy',str(policy)])==0
    assert windows.main(['verify','--directory',str(directory),'--capture',str(source)])==0
    controls=tmp_path/'controls'
    assert windows.main(['controls','--directory',str(controls),'--policy',str(policy)])==0
    assert windows.main(['verify-controls','--directory',str(controls)])==0
    (controls/'controls.json').write_text('{}')
    with pytest.raises(ValueError,match='controls_changed'):windows.main(['verify-controls','--directory',str(controls)])
    unavailable=tmp_path/'unavailable';selected.write_text(canonical(request(bars=64)))
    assert windows.main(['prepare','--directory',str(unavailable),'--capture',str(source),'--request',str(selected),'--policy',str(policy)])==2
    assert windows.main(['verify','--directory',str(unavailable),'--capture',str(source)])==2


def test_checked_in_policy_matches_exact_input_contract():
    assert json.loads(Path('config/research-feature-input-v1.json').read_text())==windows.POLICY
