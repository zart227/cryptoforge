"""Causal revision selection and split/refusal behavior without fit or DB access."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import stat

import pytest

from cryptoforge import research_data_protocol as m
from cryptoforge.research_training_diagnostics import canonical, digest


UTC = timezone.utc
AUDITED = '2026-10-23T01:00:00+00:00'
STEP = timedelta(minutes=5)


@pytest.fixture(autouse=True)
def fixed_synthetic_audit_clock(monkeypatch):
    class ScenarioClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(AUDITED).astimezone(tz)
    monkeypatch.setattr(m, 'datetime', ScenarioClock)


@pytest.fixture
def protocol():
    def interval(start, end):
        return {'decision_start': start, 'decision_end': end}
    return {'schema_version': 'research-data-protocol-v1', 'registered_at': '2026-10-23T00:00:00Z',
        'symbols': ['BTCUSDT'], 'timeframe_seconds': 300, 'feature_window_candles': 120,
        'feature_version': 'candle-v1', 'feature_calculation_contract': 'bounded-window-candle-v1',
        'target_version': 'fixed-future-return-v1', 'horizon_candles': 3, 'embargo_candles': 3,
        'decision_delay_seconds': 60, 'fit_information_end': '2026-10-21T12:20:00Z',
        'validation_information_end': '2026-10-21T13:20:00Z', 'partitions': {
            'train': interval('2026-10-21T12:00:00Z', '2026-10-21T12:05:00Z'),
            'validation': interval('2026-10-21T13:00:00Z', '2026-10-21T13:05:00Z'),
            'final_test': interval('2026-10-24T00:00:00Z', '2026-10-25T00:00:00Z'),
            'forward': interval('2026-10-26T00:00:00Z', '2026-10-27T00:00:00Z')}}


@pytest.fixture
def exposure():
    return {'schema_version': 'research-data-exposures-v1', 'coverage': 'declared_only', 'entries': []}


def write_export(path, source, request):
    result = m.local.build(source, request)
    assert result['capture'] is not None
    path.mkdir(mode=0o700, exist_ok=True)
    for name, value in (('policy.json', m.local.POLICY), ('request.json', request),
                        ('source.json', source), ('capture.json', result['capture']), ('receipt.json', result['report'])):
        p = path / name
        p.write_text(canonical(value) + '\n')
        p.chmod(0o600)
    return path


def make_export(path, opened, count, known):
    end = opened + count * STEP
    request = {'schema_version': 'research-local-export-request-v1', 'symbol': 'BTCUSDT',
        'timeframe_seconds': 300, 'start': opened.isoformat(), 'end': end.isoformat(),
        'partition': 'train', 'development_end': end.isoformat()}
    began = known - timedelta(milliseconds=300)
    rows = []
    for i in range(count):
        start = opened + i * STEP
        close = start + STEP
        rows.append({'id': '00000000-0000-0000-0000-' + f'{int(start.timestamp()) // 300:012d}',
            'exchange': 'bybit', 'market_type': 'spot', 'symbol': 'BTCUSDT', 'pair': 'BTC/USDT',
            'timeframe': '5m', 'open_time': start.isoformat(), 'close_time': close.isoformat(),
            'open': '100.123456789123', 'high': '110.000000000000', 'low': '90.000000000000',
            'close': '101.000000000000', 'volume': '20.000000000000', 'turnover': '2000.000000000000',
            'source': 'bybit_public_api', 'created_at': start.isoformat(),
            'updated_at': close.isoformat(), 'ingested_at': close.isoformat(), 'storage_xmin': '1000'})
    source = {'schema_version': 'research-local-observation-v1', 'request_sha256': digest(request),
        'transport': {'host': '127.0.0.1', 'port': 55432, 'driver': 'psycopg', 'driver_version': '3.3.6'},
        'database': {'database': 'cryptoforge', 'login': 'authenticator', 'role': 'service_role',
            'server_version_num': '170010', 'read_only': 'on', 'isolation': 'repeatable read',
            'statement_timeout': '3s', 'lock_timeout': '250ms', 'idle_timeout': '5s', 'login_superuser': False,
            'database_oid': '16384', 'server_address': '172.20.0.2', 'server_port': 5432,
            'snapshot': '3000:3000:', 'read_started_at': began.isoformat()},
        'columns': [{'name': n, 'type': t, 'not_null': True} for n, t in m.local.COLUMNS.items()],
        'unique_keys': [{'columns': m.local.KEY.copy()}],
        'read_completed_at': (known-timedelta(milliseconds=100)).isoformat(),
        'client_observed_at': known.isoformat(), 'rows': rows}
    return write_export(path, source, request)


@pytest.fixture
def exports(tmp_path):
    train = datetime(2026, 10, 21, 12, tzinfo=UTC)
    validation = train + timedelta(hours=1)
    return [make_export(tmp_path/'train-features', train-120*STEP, 120, train+timedelta(seconds=1)),
            make_export(tmp_path/'train-labels', train, 3, train+3*STEP+timedelta(seconds=1)),
            make_export(tmp_path/'validation-features', validation-120*STEP, 120, validation+timedelta(seconds=1)),
            make_export(tmp_path/'validation-labels', validation, 3, validation+3*STEP+timedelta(seconds=1))]


def run_audit(protocol, exposure, exports):
    refs = [m.source_reference(p, protocol, AUDITED) for p in exports]
    context = {'schema_version': 'research-data-audit-context-v1', 'audited_at': AUDITED}
    return m.audit(protocol, exposure, refs, context)


def test_expired_final_test_gate_still_uses_explicit_audit_time(protocol):
    with pytest.raises(ValueError, match='future_unread_final_test_required'):
        m.validate_protocol(protocol, '2026-10-26T00:00:00+00:00')


def rewrite(path, change):
    source = json.loads((path/'source.json').read_text())
    request = json.loads((path/'request.json').read_text())
    change(source)
    return write_export(path, source, request)


def test_complete_metadata_is_never_training_admission(protocol, exposure, exports):
    report = run_audit(protocol, exposure, exports)
    assert report['status'] == 'metadata_consistent'
    assert report['observed_rows'] == 246 and report['unique_revisions'] == 135
    assert report['sample_count'] == 2 and report['samples_metadata_consistent'] == 2
    assert report['sample_issue_counts'] == {}
    assert report['samples'][0]['feature_rows_available'] == 120
    assert report['samples'][0]['label_rows_available'] == 3
    assert report['samples'][0]['label_end_time'] == '2026-10-21T12:15:00+00:00'
    assert report['samples'][0]['decision_time'] == '2026-10-21T12:01:00+00:00'
    for key in ('training_data_admitted', 'training_executed', 'source_features_labels_parity_verified',
                'exposure_inventory_complete', 'append_only_source_history_verified',
                'protocol_registration_authenticated', 'provider_called', 'numeric_worker_executed',
                'production_promotion_authorized', 'holdout_values_read'):
        assert report[key] is False
    assert run_audit(protocol, exposure, exports)['audit_sha256'] == report['audit_sha256']


def test_later_correction_never_rewrites_earlier_features(protocol, exposure, exports):
    before = run_audit(protocol, exposure, exports)
    def correction(source):
        source['rows'][0]['close'] = '102.000000000000'
        source['rows'][0]['storage_xmin'] = '1001'
    rewrite(exports[2], correction)
    after = run_audit(protocol, exposure, exports)
    assert before['samples'][0]['feature_lineage_sha256'] == after['samples'][0]['feature_lineage_sha256']
    assert before['samples'][1]['feature_lineage_sha256'] != after['samples'][1]['feature_lineage_sha256']
    assert after['unique_revisions'] == before['unique_revisions'] + 1


def test_same_storage_revision_cannot_change_value(protocol, exposure, exports):
    rewrite(exports[2], lambda s: s['rows'][0].update(close='102.000000000000'))
    with pytest.raises(ValueError, match='same_storage_revision'):
        run_audit(protocol, exposure, exports)


def test_created_ingested_updated_times_do_not_backdate_availability(protocol, exposure, exports):
    protocol['decision_delay_seconds'] = 0
    report = run_audit(protocol, exposure, exports)
    assert report['samples'][0]['metadata_consistency_pass'] is False
    assert 'feature_late' in report['samples'][0]['issues']
    assert report['samples'][0]['feature_lineage_sha256'] is None


def test_missing_latest_bar_cannot_fall_back_to_older_window(protocol, exposure, exports):
    # Only the later validation snapshot contains this candle; it is too late for training.
    train = datetime(2026, 10, 21, 12, tzinfo=UTC)
    make_export(exports[0], train-121*STEP, 120, train+timedelta(seconds=1))
    report = run_audit(protocol, exposure, exports)
    assert 'feature_late' in report['samples'][0]['issues']
    assert report['samples'][0]['feature_rows_available'] == 119


def test_label_known_after_fit_information_end_is_unavailable(protocol, exposure, exports):
    protocol['fit_information_end'] = '2026-10-21T12:15:00Z'
    report = run_audit(protocol, exposure, exports)
    assert 'label_late' in report['samples'][0]['issues']
    assert report['samples'][0]['label_lineage_sha256'] is None


def test_fit_cutoff_before_label_close_is_explicit(protocol, exposure, exports):
    protocol['fit_information_end'] = '2026-10-21T12:10:00Z'
    report = run_audit(protocol, exposure, exports)
    assert 'label_not_complete_by_information_cutoff' in report['samples'][0]['issues']


def test_absent_label_does_not_become_zero(protocol, exposure, exports):
    report = run_audit(protocol, exposure, exports[:1])
    assert report['samples'][0]['label_rows_available'] == 0
    assert 'label_missing' in report['samples'][0]['issues']
    assert report['samples'][0]['label_lineage_sha256'] is None


def test_tied_conflicting_revisions_are_ambiguous(protocol, exposure, exports, tmp_path):
    duplicate = tmp_path/'conflict'
    source = json.loads((exports[0]/'source.json').read_text())
    request = json.loads((exports[0]/'request.json').read_text())
    source['rows'][0].update(close='102.000000000000', storage_xmin='1001')
    write_export(duplicate, source, request)
    report = run_audit(protocol, exposure, [*exports, duplicate])
    assert 'feature_ambiguous' in report['samples'][0]['issues']
    assert report['samples'][0]['feature_lineage_sha256'] is None


def test_input_order_does_not_change_asof_selection(protocol, exposure, exports):
    one = run_audit(protocol, exposure, exports)
    two = run_audit(protocol, exposure, list(reversed(exports)))
    assert one['timeline_sha256'] == two['timeline_sha256']
    assert one['samples'] == two['samples']


def test_all_read_source_windows_recorded_even_when_declared_inventory_empty(protocol, exposure, exports):
    report = run_audit(protocol, exposure, exports)
    recorded = report['source_exposures_recorded_automatically']
    assert len(recorded) == 4 and all(r['kind'] == 'market_values_observed' for r in recorded)
    assert recorded[0]['start'] == '2026-10-21T02:00:00+00:00'
    assert recorded[0]['end'] == '2026-10-21T12:00:00+00:00'
    assert report['exposure_inventory_complete'] is False


def test_tied_identical_revisions_are_deterministic():
    opened = datetime(2026, 10, 21, 12, tzinfo=UTC)
    row = {'known_at': '2026-10-21T12:01:00Z', 'revision_sha256': 'a'*64, 'source_sha256': 'c'*64}
    other = {**row, 'source_sha256': 'b'*64}
    index = {('BTCUSDT', opened.isoformat()): [row, other]}
    chosen, error = m._choose(index, 'BTCUSDT', opened, opened+timedelta(minutes=1))
    assert error is None and chosen['source_sha256'] == 'b'*64


def test_changed_original_during_replay_is_refused(monkeypatch, protocol, exposure, exports):
    refs = [m.source_reference(p, protocol, AUDITED) for p in exports]
    original = m.source_reference
    calls = []
    def changed(*args):
        value = original(*args); calls.append(1)
        if len(calls) == 2: value['files']['source.json'] = 'a'*64
        return value
    monkeypatch.setattr(m, 'source_reference', changed)
    with pytest.raises(ValueError, match='changed_during_read'):
        m.audit(protocol, exposure, refs, {'schema_version': 'research-data-audit-context-v1', 'audited_at': AUDITED})


@pytest.mark.parametrize('count', [0, 9])
def test_export_count_refused_before_read(monkeypatch, protocol, exposure, count):
    monkeypatch.setattr(m, 'source_reference', lambda *_: pytest.fail('no source reads'))
    with pytest.raises(ValueError, match='bounded_original'):
        m.audit(protocol, exposure, [{}]*count, {'schema_version': 'research-data-audit-context-v1', 'audited_at': AUDITED})


def test_invalid_exposure_refused_before_source_values(monkeypatch, tmp_path, protocol, exposure, exports):
    exposure['coverage'] = 'complete'
    monkeypatch.setattr(m, 'source_reference', lambda *_: pytest.fail('no source reads'))
    with pytest.raises(ValueError, match='exposure_inventory'):
        m.prepare(tmp_path/'pack', protocol, exposure, exports)


@pytest.mark.parametrize('field,value', [
    ('timeframe_seconds', True), ('timeframe_seconds', 60), ('feature_window_candles', 64),
    ('horizon_candles', 4), ('feature_version', 'candle-v2'), ('target_version', 'profit-v1'),
    ('feature_calculation_contract', 'legacy'), ('embargo_candles', 2), ('embargo_candles', True),
    ('decision_delay_seconds', -1), ('decision_delay_seconds', 300), ('decision_delay_seconds', True),
    ('registered_at', '2026-10-24T00:00:00Z'), ('registered_at', '2026-10-21T00:00:00'),
    ('symbols', ['BTCUSDT', 'BTCUSDT']), ('symbols', ['BTCUSDT;DROP']),
    ('fit_information_end', '2026-10-21T13:00:00Z'),
    ('validation_information_end', '2026-10-24T00:00:00Z'),
])
def test_protocol_refuses_changed_contract_before_source_reads(monkeypatch, protocol, field, value):
    protocol[field] = value
    monkeypatch.setattr(m.local, 'read_export', lambda *_: pytest.fail('source must not be read'))
    with pytest.raises(ValueError):
        m.validate_protocol(protocol, AUDITED)


@pytest.mark.parametrize('change', ['extra', 'overlap', 'embargo', 'grid', 'past_holdout', 'too_many_samples'])
def test_partition_refusals(protocol, change):
    if change == 'extra':
        protocol['partitions']['shadow'] = deepcopy(protocol['partitions']['train'])
    elif change == 'overlap':
        protocol['partitions']['validation']['decision_start'] = '2026-10-21T12:00:00Z'
    elif change == 'embargo':
        protocol['partitions']['validation']['decision_start'] = '2026-10-21T12:15:00Z'
    elif change == 'grid':
        protocol['partitions']['train']['decision_start'] = '2026-10-21T12:00:01Z'
    elif change == 'past_holdout':
        protocol['partitions']['final_test'] = {'decision_start': '2026-10-22T00:00:00Z', 'decision_end': '2026-10-22T01:00:00Z'}
    else:
        protocol['partitions']['train'] = {'decision_start': '2026-10-01T00:00:00Z', 'decision_end': '2026-10-08T00:00:00Z'}
        protocol['partitions']['validation'] = {'decision_start': '2026-10-09T00:00:00Z', 'decision_end': '2026-10-16T00:00:00Z'}
        protocol['fit_information_end'] = '2026-10-08T01:00:00Z'
        protocol['validation_information_end'] = '2026-10-16T01:00:00Z'
        protocol['symbols'] = ['BTCUSDT', 'ETHUSDT']
    with pytest.raises(ValueError):
        m.validate_protocol(protocol, AUDITED)


@pytest.mark.parametrize('change', ['complete_claim', 'unknown_kind', 'unknown_symbol', 'future', 'sha', 'duplicate', 'extra'])
def test_exposure_refusals(protocol, exposure, change):
    entry = {'symbol': 'BTCUSDT', 'start': '2026-10-21T10:00:00Z', 'end': '2026-10-21T11:00:00Z',
             'kind': 'metric_review', 'source_sha256': 'a'*64}
    exposure['entries'] = [entry]
    if change == 'complete_claim': exposure['coverage'] = 'complete'
    if change == 'unknown_kind': entry['kind'] = 'secret'
    if change == 'unknown_symbol': entry['symbol'] = 'ETHUSDT'
    if change == 'future': entry['end'] = '2026-10-24T11:00:00Z'
    if change == 'sha': entry['source_sha256'] = 'path or secret'
    if change == 'duplicate': exposure['entries'].append(deepcopy(entry))
    if change == 'extra': entry['approved'] = True
    with pytest.raises(ValueError): m.validate_exposures(exposure, protocol, AUDITED)


def test_source_beyond_validation_cutoff_refused_before_values_read(monkeypatch, protocol, exports):
    original = m.local._private_read
    def tracked(directory, name, maximum, **kwargs):
        assert name == 'request.json', 'market values must not be opened'
        return original(directory, name, maximum, **kwargs)
    monkeypatch.setattr(m.local, '_private_read', tracked)
    protocol['validation_information_end'] = '2026-10-21T13:05:00Z'
    with pytest.raises(ValueError, match='beyond_development'):
        m.source_reference(exports[-1], protocol, AUDITED)


def test_export_pin_changed_is_refused(protocol, exposure, exports):
    refs = [m.source_reference(p, protocol, AUDITED) for p in exports]
    p = exports[0]/'source.json'
    p.write_text(p.read_text()+' ')
    with pytest.raises(ValueError, match='pin_mismatch'):
        m.audit(protocol, exposure, refs, {'schema_version': 'research-data-audit-context-v1', 'audited_at': AUDITED})


def test_duplicate_export_refused(protocol, exposure, exports):
    with pytest.raises(ValueError, match='duplicate_original'):
        run_audit(protocol, exposure, [*exports, exports[0]])


@pytest.mark.parametrize('change', ['oid', 'schema', 'uuid_replaced'])
def test_cross_export_identity_refusals(protocol, exposure, exports, change):
    def modify(source):
        if change == 'oid': source['database']['database_oid'] = '12345'
        elif change == 'schema': source['unique_keys'].append({'columns': ['id']})
        else: source['rows'][0]['id'] = '99999999-0000-0000-0000-000000000000'
    rewrite(exports[2], modify)
    with pytest.raises(ValueError, match='identity|catalog'):
        run_audit(protocol, exposure, exports)


def test_private_artifacts_no_overwrite_offline_replay_and_tampering(tmp_path, protocol, exposure, exports):
    directory = tmp_path/'pack'
    one = m.prepare(directory, protocol, exposure, exports)
    assert m.verify(directory) == one
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for p in directory.iterdir(): assert stat.S_IMODE(p.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match='new_data_audit'):
        m.prepare(directory, protocol, exposure, exports)
    data = json.loads((directory/'audit.json').read_text())
    data['training_data_admitted'] = True
    data['audit_sha256'] = digest({k: v for k, v in data.items() if k != 'audit_sha256'})
    (directory/'audit.json').write_text(canonical(data)+'\n')
    with pytest.raises(ValueError, match='audit_or_implementation'):
        m.verify(directory)


def test_symlink_and_nonprivate_source_refusals(tmp_path, protocol, exports):
    link = tmp_path/'alias'
    link.symlink_to(exports[0], target_is_directory=True)
    with pytest.raises(ValueError): m.source_reference(link, protocol, AUDITED)
    (exports[0]/'source.json').chmod(0o644)
    with pytest.raises(ValueError): m.source_reference(exports[0], protocol, AUDITED)


def test_blocked_data_has_valid_cli_audit_without_database_or_fit(tmp_path, protocol, exposure, exports, capsys, monkeypatch):
    protocol['decision_delay_seconds'] = 0
    for name, value in (('protocol', protocol), ('exposure', exposure)):
        p = tmp_path/(name+'.json')
        p.write_text(canonical(value)+'\n'); p.chmod(0o600)
    monkeypatch.setattr(m.local, '_connect', lambda *_: pytest.fail('no live database'))
    directory = tmp_path/'audit'
    assert m.main(['prepare', '--directory', str(directory), '--protocol', str(tmp_path/'protocol.json'),
                   '--exposure', str(tmp_path/'exposure.json'), '--export', str(exports[0])]) == 0
    assert m.main(['verify', '--directory', str(directory)]) == 0
    assert 'blocked; training admission disabled' in capsys.readouterr().out


def test_safe_cli_error_does_not_relay_path_or_exception(tmp_path, capsys):
    assert m.main(['verify', '--directory', str(tmp_path/'secret-token-value')]) == 2
    output = capsys.readouterr().out
    assert 'secret-token-value' not in output and 'Traceback' not in output


def test_fixed_policy_config_and_no_silent_extensions(protocol, exposure, exports):
    config = Path(m.__file__).parents[2]/'config/research-data-protocol-v1.json'
    assert json.loads(config.read_text()) == m.POLICY
    refs = [m.source_reference(p, protocol, AUDITED) for p in exports]
    context = {'schema_version': 'research-data-audit-context-v1', 'audited_at': AUDITED}
    with pytest.raises(ValueError, match='fixed_data_protocol'):
        m.audit(protocol, exposure, refs, context, {**m.POLICY, 'training_admission_enabled': True})
