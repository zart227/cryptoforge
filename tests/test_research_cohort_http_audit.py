"""Original HTTP bytes, native loader replay, precision loss and capture refusal."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import pytest
from test_research_value_audit import value_base
from test_research_revision_bridge import native_fixture
from cryptoforge import research_cohort_http_audit as m


def capture(directory, *, numeric_volume='10', empty=False):
    directory.mkdir(mode=0o700); responses = {}; latest = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
    for index, pair in enumerate(m.POLICY['pairs']):
        records = []
        for offset in range(0 if empty else 124):
            row = {'pair': pair, 'symbol': pair.replace('/', ''), 'open_time': (latest-timedelta(minutes=5*offset)).isoformat(),
                'open': '100', 'high': '102', 'low': '99', 'close': '101', 'volume': numeric_volume,
                'ingested_at': '2026-10-26T10:05:10+00:00'}
            raw = m.canonical(row)
            for key in m.wire.NUMERIC: raw = raw.replace(json.dumps(key)+':'+json.dumps(row[key]), json.dumps(key)+':'+row[key])
            records.append(raw)
        raw = ('['+','.join(records)+']').encode(); name = f'body-{index:02d}.json'
        m.wire.write(directory, name, raw)
        response = {'file': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'status': 200,
            'observed_at': '2026-10-26T10:05:11+00:00'}; responses[pair] = response
        query = {'pair': ['eq.'+pair], 'exchange': ['eq.bybit'], 'market_type': ['eq.spot'], 'timeframe': ['eq.5m'],
            'select': [','.join(m.wire.FIELDS)], 'order': ['open_time.desc'], 'limit': ['500']}
        m.wire.write(directory, f'attempt-{index:02d}.json', m.canonical({'pair': pair, 'attempt': 1, 'method': 'GET',
            'query': query, 'started_at': '2026-10-26T10:05:09+00:00', 'auth_values_recorded': False}).encode())
        m.wire.write(directory, f'receipt-{index:02d}.json', m.canonical(response).encode())
    saved = {'schema_version': 'native-cohort-HTTP-capture-v1', 'evidence_kind': 'synthetic_retained_HTTP_fixture', 'started_at': '2026-10-26T10:05:08+00:00',
        'completed_at': '2026-10-26T10:05:12+00:00', 'responses': responses, 'requests': 20, 'retries': 0,
        'HTTP_snapshot_is_single_database_transaction': False}
    m.wire.write(directory, 'capture.json', m.canonical(saved).encode()); return saved


@pytest.fixture(scope='module')
def scenario(value_base, tmp_path_factory):
    parent = tmp_path_factory.mktemp('HTTP-cohort'); directory = parent/'captures'; capture(directory)
    project = value_base[0]; native = m._native(project, directory, 'replay', parent/'native.json')
    return project, directory, native


def test_native_reader_and_full_loader_replay_original_numeric_HTTP_bytes(scenario):
    _, directory, native = scenario; result = m.compose(directory, native)
    assert result['status'] == 'native_HTTP_values_compatible'
    assert result['source_rows'] == 2480 and result['scalar_fields_checked'] == 12400
    assert result['scalar_mismatch_count'] == result['independent_sample_mismatches'] == 0
    assert result['independent_feature_components'] == 140 and result['independent_label_windows'] == 20
    assert result['native_all_examples'] == 40 and result['all_native_examples_equal_exact_parser']
    assert not result['native_reader_original_local_HTTP_path_exercised'] and result['evidence_kind'] == 'synthetic_retained_HTTP_fixture'
    assert native['actual_HTTP_requests_this_execution'] == 0 and not native['credentials_loaded_this_execution']
    for key in ('historical_first_seen_revision_lineage_verified', 'same_database_transaction_for_all_pairs',
                'production_service_configuration_or_all_consumers_qualified', 'old_M38_or_M40_windows_repaired',
                'approved_dataset_or_training_admission', 'new_numerical_allowance_created'):
        assert result[key] is False


def test_high_precision_volume_loss_blocks_qualification(value_base, tmp_path):
    directory = tmp_path/'captures'; capture(directory, numeric_volume='12345678901234.123456789012')
    native = m._native(value_base[0], directory, 'replay', tmp_path/'native.json')
    result = m.compose(directory, native)
    assert result['scalar_mismatch_count'] == 2480 and result['status'] == 'blocked'


def test_empty_response_is_not_qualified(value_base, tmp_path):
    directory = tmp_path/'captures'; capture(directory, empty=True)
    native = m._native(value_base[0], directory, 'replay', tmp_path/'native.json')
    result = m.compose(directory, native)
    assert result['source_rows'] == result['native_all_examples'] == result['independent_label_windows'] == 0
    assert result['status'] == 'blocked'


@pytest.mark.parametrize('mutation', [
    lambda n:n.update(actual_HTTP_requests_this_execution=True),
    lambda n:n.update(scalar_fields_checked=True),
    lambda n:n.update(model_fit_prediction_publication_performed=True),
    lambda n:n.update(historical_availability_verified=True),
    lambda n:n.update(single_database_transaction_verified=True),
    lambda n:n.update(credentials_loaded_this_execution=True),
    lambda n:n.update(capture_sha256='0'*64),
])
def test_worker_cannot_forge_counts_identity_or_qualification(scenario, mutation):
    _, directory, native = scenario; native = deepcopy(native); mutation(native)
    with pytest.raises(ValueError): m.compose(directory, native)


def test_independent_feature_or_label_mismatch_is_visible(scenario):
    _, directory, native = scenario; native = deepcopy(native)
    native['native']['selected'][0]['example']['long_label'] ^= 1
    result = m.compose(directory, native)
    assert result['status'] == 'blocked' and result['independent_sample_mismatches'] == 1


@pytest.mark.parametrize('raw', [b'[{"pair":"AERO/USDT","pair":"AERO/USDT"}]', b'[NaN]', b'{}', b'['+b' '*512000+b']'])
def test_bounded_strict_HTTP_JSON(raw):
    with pytest.raises(ValueError): m.wire.exact_rows(raw, 'AERO/USDT')


@pytest.mark.parametrize('change', [
    lambda row:row.update(pair='BTC/USDT'), lambda row:row.update(symbol='OTHER'),
    lambda row:row.update(volume=True), lambda row:row.update(open_time='2026-10-26T10:00:01Z'),
    lambda row:row.update(ingested_at='2026-10-26T10:05:00'), lambda row:row.update(high='1'),
    lambda row:row.update(close='0'), lambda row:row.update(volume='1e99999'),
])
def test_invalid_market_identity_clocks_or_numeric_domain_refused(change):
    row = {'pair': 'AERO/USDT', 'symbol': 'AEROUSDT', 'open_time': '2026-10-26T10:00:00Z',
        'ingested_at': '2026-10-26T10:05:10Z', 'open': '100', 'high': '102', 'low': '99', 'close': '101', 'volume': '10'}
    change(row)
    with pytest.raises(ValueError): m.wire.exact_rows(m.canonical([row]).encode(), 'AERO/USDT')


def test_native_query_does_not_accept_other_host_limit_or_writes():
    from urllib.parse import urlencode
    query = {'pair': 'eq.AERO/USDT', 'exchange': 'eq.bybit', 'market_type': 'eq.spot', 'timeframe': 'eq.5m',
        'select': ','.join(m.wire.FIELDS), 'order': 'open_time.desc', 'limit': '500'}
    url = m.wire.ORIGIN+'/rest/v1/market_candles?'+urlencode(query)
    assert m.wire.query(url)[0] == 'AERO/USDT'
    for altered in (url.replace('127.0.0.1', 'example.com'), url.replace('limit=500', 'limit=501'), url+'&limit=500', url+'#extra'):
        with pytest.raises(ValueError): m.wire.query(altered)


def test_changed_original_body_is_refused_without_network(scenario, tmp_path):
    import shutil
    _, original, _ = scenario; target = tmp_path/'copy'; shutil.copytree(original, target)
    body = target/'body-00.json'; body.write_bytes(body.read_bytes()+b' ')
    with pytest.raises(ValueError, match='bytes_or_clock'): m.inspect_capture(target)


def test_existing_pack_cannot_restart_capture_and_offline_verify_starts_no_worker(scenario, tmp_path, monkeypatch):
    project, captures, native = scenario; target = tmp_path/'pack'; target.mkdir(mode=0o700)
    import shutil
    shutil.copytree(captures, target/'captures')
    write = m.prior.late.cohort.values.files._write
    write(target, 'policy.json', m.POLICY); write(target, 'binding.json', {'project': str(project), 'main_profile': m.prior.late.cohort.values.main_profile(project)})
    write(target, 'native.json', native); write(target, 'audit.json', m.compose(captures, native))
    monkeypatch.setattr(m, '_native', lambda *a:pytest.fail('worker or HTTP in offline verify'))
    assert m.verify(target)['status'] == 'native_HTTP_values_compatible'
    with pytest.raises(ValueError, match='no_resume_or_retry'): m.prepare(target, project)


@pytest.mark.parametrize('interrupt', [False, True])
def test_worker_timeout_or_interrupt_kills_and_reaps(tmp_path, monkeypatch, interrupt):
    events = {}
    class Process:
        pid = 34567; calls = 0
        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                if interrupt: raise KeyboardInterrupt()
                raise subprocess.TimeoutExpired('fixed', 60)
            return 0
    process = Process(); monkeypatch.setattr(m.prior.late.cohort.values, 'main_profile', lambda *a:{})
    monkeypatch.setattr(m.subprocess, 'Popen', lambda a, **kw:events.update(args=a, **kw) or process)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig:events.update(killed=pid))
    with pytest.raises(KeyboardInterrupt if interrupt else subprocess.TimeoutExpired): m._native(tmp_path, tmp_path, 'replay', tmp_path/'native.json')
    assert events['killed'] == 34567 and process.calls == 2 and events['start_new_session']


def test_policy_and_redacted_CLI_error(tmp_path, capsys):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-cohort-http-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'private-name')]) == 2
    assert 'private-name' not in capsys.readouterr().out
