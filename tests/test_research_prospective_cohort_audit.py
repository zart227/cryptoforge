"""Registered point-in-time venue receipts, no late feature repair or model operations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlencode

import pytest
from test_research_value_audit import value_base
from test_research_revision_bridge import native_fixture
from cryptoforge import research_prospective_cohort_audit as m


def write(directory, name, value):
    raw = value if type(value) is bytes else (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()
    path = directory/name; path.parent.mkdir(parents=True, exist_ok=True); path.parent.chmod(0o700)
    path.write_bytes(raw); path.chmod(0o600); return raw


def fixture_source(parent, *, missing_feature=None, missing_label=None, venue_error=None):
    source = parent/'source'; registration = parent/'registered'; source.mkdir(mode=0o700); registration.mkdir(mode=0o700)
    anchor = datetime(2026, 10, 26, 13, tzinfo=timezone.utc)
    plan = {'schema_version': 'primary20pair-prospective-source-plan-v1', 'registered_at': '2026-10-26T12:00:00Z',
        'pairs': m.POLICY['pairs'], 'scope': 'source_only_synthetic_fixture', 'maximum_public_market_GET_attempts': 40,
        'maximum_retries': 0, 'new_numerical_allowance_created': False, 'model_fit_prediction_forecasts_or_provider_generations': 0,
        'feature_anchor': anchor.isoformat(), 'decision_at': (anchor+timedelta(minutes=2)).isoformat(),
        'label_close_anchor': (anchor+timedelta(minutes=15)).isoformat(), 'label_information_end': (anchor+timedelta(minutes=17)).isoformat(),
        'feature_lookback': 120, 'horizon_candles': 3, 'min_label_return': '0.003', 'polls': []}
    for kind, offset, limit in (('features', 0, 120), ('labels', 15, 3)):
        boundary = anchor+timedelta(minutes=offset)
        plan['polls'].append({'kind': kind, 'anchor': boundary.isoformat(), 'starts_at': (boundary+timedelta(seconds=10)).isoformat(),
            'latest_completion': (boundary+timedelta(seconds=100)).isoformat(), 'limit': limit})
    raw = write(source, 'prospective-plan.json', plan); code = write(source, 'collect-frozen-source.py', b'# synthetic collector fixture never executed\n')
    freeze = {'frozen_at': '2026-10-26T12:10:00Z', 'plan_sha256': hashlib.sha256(raw).hexdigest(), 'collector_sha256': hashlib.sha256(code).hexdigest()}
    write(source, 'capture-freeze.json', freeze); write(registration, 'prospective-plan.json', plan)
    write(registration, 'capture-freeze.json', freeze); write(registration, 'collector.py', code)
    run = source/'collection-run'; run.mkdir(mode=0o700)
    write(run, 'armed.json', {'armed_at': '2026-10-26T12:11:00Z', 'plan_sha256': freeze['plan_sha256'], 'collector_sha256': freeze['collector_sha256']})
    total_bytes = 0
    for slot in plan['polls']:
        directory = run/slot['kind']; directory.mkdir(mode=0o700); receipts = []; boundary = datetime.fromisoformat(slot['anchor'])
        for index, pair in enumerate(plan['pairs']):
            records = []
            for offset in range(slot['limit']):
                opened = boundary-timedelta(minutes=5*(offset+1)); close = '101' if slot['kind'] == 'features' else '102'
                records.append([str(int(opened.timestamp())*1000), '100', '103', '99', close, '10', '1000'])
            if slot['kind'] == 'features' and pair == missing_feature: records.pop(10)
            if slot['kind'] == 'labels' and pair == missing_label: records.pop(1)
            raw = json.dumps({'retCode': 1 if pair == venue_error else 0, 'result': {'category': 'spot', 'symbol': pair.replace('/', ''), 'list': records},
                'time': int((boundary+timedelta(seconds=10)).timestamp())*1000}).encode()
            prefix = f'{index:02d}'; write(directory, prefix+'-body.bin', raw); total_bytes += len(raw)
            url = 'https://api.bybit.com/v5/market/kline?'+urlencode({'category': 'spot', 'symbol': pair.replace('/', ''), 'interval': '5',
                'end': str(int(boundary.timestamp())*1000-1), 'limit': str(slot['limit'])})
            write(directory, prefix+'-attempt.json', {'pair': pair, 'url': url, 'method': 'GET', 'attempt': 1,
                'prepared_at': slot['starts_at'], 'authorization_headers_or_credentials': False, 'plan_sha256': freeze['plan_sha256']})
            receipt = {'pair': pair, 'status': 'captured', 'HTTP_attempted': True, 'retry': False, 'http_status': 200, 'body_prefix_only': False,
                'body_bytes': len(raw), 'body_sha256': hashlib.sha256(raw).hexdigest(), 'completed_at': (boundary+timedelta(seconds=11)).isoformat(),
                'request_url_sha256': hashlib.sha256(url.encode()).hexdigest()}
            write(directory, prefix+'-receipt.json', receipt); receipts.append(receipt)
        write(directory, 'slot.json', {'kind': slot['kind'], 'automatic_retry': False, 'source_or_model_training_admission': False,
            'completed_at': (boundary+timedelta(seconds=12)).isoformat(), 'actual_GET_attempts': 20, 'valid_HTTP_captures': 20, 'receipts': receipts})
    write(run, 'complete.json', {'schema_version': 'primary20pair-source-collection-v1', 'plan_sha256': freeze['plan_sha256'],
        'completed_at': (anchor+timedelta(minutes=15, seconds=13)).isoformat(), 'actual_GET_attempts': 40, 'retries': 0,
        'polls_completed': 2, 'total_raw_bytes': total_bytes, 'model_fit_prediction_forecasts_provider_calls_database_writes': 0, 'source_admission': False})
    return source, registration


@pytest.fixture(scope='module')
def prepared(value_base, tmp_path_factory):
    parent = tmp_path_factory.mktemp('prospective20'); source, registration = fixture_source(parent)
    report = m.prepare(parent/'pack', source, registration, value_base[0])
    return parent/'pack', source, registration, report, value_base[0]


def test_all20_synthetic_source_windows_match_fraction_and_actual_native_functions(prepared):
    pack, _, _, report, _ = prepared
    assert report['status'] == 'all20_prospective_values_match' and report['all20source_samples_complete']
    assert report['feature_components_checked'] == 140 and report['complete_feature_and_label_samples'] == 20
    assert report['captured_complete_label_horizons'] == 20 and report['source_rows_read'] == 2460
    assert report['sample_mismatches'] == 0 and report['original_public_source_GET_attempts'] == 0
    assert report['recorded_source_GET_attempts'] == 40 and report['evidence_kind'] == 'source_only_synthetic_fixture'
    assert not report['training_data_protocol_or_next_budget_approved'] and not report['new_numerical_allowance_created']
    assert not report['actual_production_reader_or_local_database_qualified'] and report['model_fit_prediction_provider_calls'] == 0
    assert m.verify(pack) == report


@pytest.mark.parametrize('kind', ['features', 'labels', 'venue_error'])
def test_missing_original_or_invalid_venue_rows_stay_partial_without_retry(value_base, tmp_path, kind):
    kwargs = {'missing_feature' if kind == 'features' else 'missing_label' if kind == 'labels' else 'venue_error': 'AERO/USDT'}
    source, registration = fixture_source(tmp_path, **kwargs); report = m.prepare(tmp_path/'pack', source, registration, value_base[0])
    assert report['status'] == 'partial_or_failed_source_qualification' and not report['all20source_samples_complete']
    assert report['complete_feature_and_label_samples'] == 19 and report['sample_mismatches'] == 0
    assert report['samples'][0]['late_features_used'] is False
    if kind == 'features': assert report['captured_complete_label_horizons'] == 20 and report['feature_windows_checked'] == 19
    if kind == 'labels': assert report['feature_windows_checked'] == 20 and report['captured_complete_label_horizons'] == 19


def test_late_feature_observation_never_backdates_the_original_decision(prepared):
    _, source, registration, _, _ = prepared; binding, plan, _ = m.load(source, registration)
    row = {'pair': 'AERO/USDT', 'symbol': 'AEROUSDT', 'open_time': '2026-10-26T12:55:00Z', 'close_time': '2026-10-26T13:00:00Z',
        'open': '100', 'high': '103', 'low': '99', 'close': '101', 'volume': '10', 'ingested_at': '2026-10-26T13:03:00Z'}
    observations = {slot: {pair: {'observed_at': '2026-10-26T13:03:00Z', 'rows': [row] if pair == 'AERO/USDT' else [], 'status': 'captured'} for pair in m.POLICY['pairs']} for slot in ('features', 'labels')}
    _, selected, _ = m.select(plan, observations)
    assert selected[0]['features'] is None


@pytest.mark.parametrize('change', [
    lambda body:body.update(retCode=True), lambda body:body['result'].update(symbol='BTCUSDT'),
    lambda body:body.update(time=0), lambda body:body['result']['list'][0].__setitem__(4, 'NaN'),
    lambda body:body['result']['list'][0].__setitem__(0, '1793019600001'),
    lambda body:body['result']['list'][0].__setitem__(2, '1'),
])
def test_public_body_identity_numbers_grid_and_OHLC_are_checked(change):
    anchor = datetime(2026, 10, 26, 13, tzinfo=timezone.utc)
    body = {'retCode': 0, 'time': int(anchor.timestamp())*1000+10000, 'result': {'category': 'spot', 'symbol': 'AEROUSDT',
        'list': [[str(int((anchor-timedelta(minutes=5)).timestamp())*1000), '100', '103', '99', '101', '10', '1000']]}}
    change(body)
    with pytest.raises(ValueError): m.parse_body(json.dumps(body).encode(), 'AERO/USDT', anchor.isoformat(), 120, (anchor+timedelta(seconds=11)).isoformat())


def test_retained_body_or_frozen_registration_changes_are_refused_without_network(prepared, tmp_path):
    _, original, reg, _, _ = prepared; copied = tmp_path/'copy'; shutil.copytree(original, copied)
    body = copied/'collection-run/features/00-body.bin'; body.write_bytes(body.read_bytes()+b' ')
    with pytest.raises(ValueError, match='body_changed'): m.load(copied, reg)
    body.write_bytes(body.read_bytes()[:-1]); (copied/'prospective-plan.json').write_text('{}')
    with pytest.raises(ValueError, match='registered_prospective'): m.load(copied, reg)


def test_offline_verification_cannot_reexecute_native_worker(prepared, monkeypatch):
    pack, _, _, report, _ = prepared
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k:pytest.fail('offline verify cannot create child'))
    assert m.verify(pack) == report


@pytest.mark.parametrize('change', [lambda n:n.update(fit_performed=True), lambda n:n.update(actual_production_reader_invoked=True), lambda n:n.update(source_rows_read=True)])
def test_native_worker_scope_and_counts_cannot_be_forged(prepared, change):
    pack, source, registration, _, _ = prepared; saved = m._read(pack, 'binding.json'); binding, plan, selected = m.load(source, registration)
    binding.update(project=saved['project'], main_profile=saved['main_profile']); result = deepcopy(m._read(pack, 'native.json', 262144)); change(result)
    with pytest.raises(ValueError): m.compose(binding, plan, selected, result)


def test_missing_input_safe_error_and_policy(tmp_path, capsys):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-prospective-cohort-audit-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'private-name')]) == 2
    assert 'private-name' not in capsys.readouterr().out
