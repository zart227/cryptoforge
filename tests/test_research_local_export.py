"""Local export integrity and refusal tests; no mutable market assumptions."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType, SimpleNamespace

import pytest

from cryptoforge import research_local_export as m
from cryptoforge.training_diagnostics import digest


@pytest.fixture
def request_value():
    return {'schema_version': 'research-local-export-request-v1', 'symbol': 'BTCUSDT',
        'timeframe_seconds': 300, 'start': '2026-10-01T00:00:00+00:00',
        'end': '2026-10-01T00:10:00+00:00', 'partition': 'train',
        'development_end': '2026-10-01T00:10:00+00:00'}


@pytest.fixture
def source(request_value):
    rows = []
    for i in range(2):
        opened = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=5*i)
        rows.append({'id': f'00000000-0000-0000-0000-{i+1:012d}', 'exchange': 'bybit',
            'market_type': 'spot', 'symbol': 'BTCUSDT', 'pair': 'BTC/USDT', 'timeframe': '5m',
            'open_time': opened.isoformat(), 'close_time': (opened+timedelta(minutes=5)).isoformat(),
            'open': '100.123456789123', 'high': '102.000000000000', 'low': '98.000000000000',
            'close': '101.000000000000', 'volume': '0.000000000000', 'turnover': '0.000000000000',
            'source': 'bybit_public_api', 'created_at': opened.isoformat(),
            'ingested_at': '2026-10-01T00:10:30+00:00', 'updated_at': '2026-10-01T00:10:31+00:00', 'storage_xmin': '12345'})
    return {'schema_version': 'research-local-observation-v1', 'request_sha256': digest(request_value),
        'transport': {'host': '127.0.0.1', 'port': 55432, 'driver': 'psycopg', 'driver_version': '3.3.6'},
        'database': {'database': 'cryptoforge', 'login': 'authenticator', 'role': 'service_role',
            'server_version_num': '170010', 'read_only': 'on', 'isolation': 'repeatable read',
            'statement_timeout': '3s', 'lock_timeout': '250ms', 'idle_timeout': '5s',
            'login_superuser': False, 'database_oid': '16384', 'server_address': '172.20.0.2',
            'server_port': 5432, 'snapshot': '12346:12346:', 'read_started_at': '2026-10-01T00:11:00+00:00'},
        'columns': [{'name': n, 'type': t, 'not_null': True} for n, t in m.COLUMNS.items()],
        'unique_keys': [{'columns': m.KEY.copy()}, {'columns': ['id']}],
        'read_completed_at': '2026-10-01T00:11:01+00:00',
        'client_observed_at': '2026-10-01T00:11:02+00:00', 'rows': rows}


def stage(monkeypatch, tmp_path, source, request):
    monkeypatch.setattr(m, '_collect', lambda project, req: deepcopy(source))
    path = tmp_path/'export'; result = m.export_local(tmp_path, path, request)
    return path, result


def test_exact_source_preserved_and_no_backdated_availability(source, request_value):
    original = deepcopy(source); result = m.build(source, request_value)
    assert source == original and source['rows'][0]['open'] == '100.123456789123'
    assert result['report']['status'] == 'observed'
    assert result['report']['training_data_admitted'] is False
    assert result['report']['historical_availability_verified'] is False
    assert result['report']['append_only_revision_history_verified'] is False
    assert result['capture']['origin'] == 'external_unverified'
    assert result['capture']['source_export_sha256'] == digest(source)
    assert {r['observed_at'] for r in result['capture']['candles']} == {source['client_observed_at']}
    historical = m.windows.prepare(result['capture'], {'schema_version': 'research-window-request-v1',
        'decision_time': request_value['end'], 'bars': 2}, m.windows.POLICY)
    assert historical['status'] == 'unavailable' and historical['payload'] is None
    assert historical['safe_error'] == 'insufficient_closed_known_bars'


@pytest.mark.parametrize('field,value', [('partition', 'test'), ('partition', 'production'),
    ('symbol', 'BTCUSDT;DROP TABLE market_candles'), ('symbol', 'btcusdt'), ('symbol', 'A'*30+'USDT'),
    ('timeframe_seconds', True), ('timeframe_seconds', 120), ('start', '2026-10-01T00:00:01Z'),
    ('end', '2026-10-01T00:00:00Z'), ('end', '2026-10-03T00:00:00Z'),
    ('development_end', '2026-10-01T00:05:00Z'), ('start', '2026-10-01T00:00:00'),
    ('start', '1969-10-01T00:00:00Z'), ('schema_version', 'future')])
def test_request_refusals_before_connection(monkeypatch, tmp_path, request_value, field, value):
    request_value[field] = value
    monkeypatch.setattr(m, '_collect', lambda *_: pytest.fail('database must not be reached'))
    with pytest.raises(ValueError): m.export_local(tmp_path, tmp_path/'export', request_value)
    assert not (tmp_path/'export').exists()


def test_closed_request_fields(request_value):
    request_value['label'] = 1
    with pytest.raises(ValueError): m.validate_request(request_value)


def test_policy_cannot_change_or_widen(source, request_value):
    policy = {**m.POLICY, 'max_rows': 257}
    with pytest.raises(ValueError, match='fixed_local'): m.build(source, request_value, policy)


@pytest.mark.parametrize('field,value', [('read_only', 'off'), ('isolation', 'read committed'),
    ('login_superuser', True), ('login', 'postgres'), ('role', 'postgres'), ('database', 'cloud'),
    ('statement_timeout', '0'), ('lock_timeout', '0'), ('idle_timeout', '0'),
    ('snapshot', 'bad'), ('server_version_num', '180000')])
def test_connection_metadata_refusals(source, request_value, field, value):
    source['database'][field] = value
    with pytest.raises(ValueError): m.build(source, request_value)


@pytest.mark.parametrize('change', ['missing', 'nullable', 'type', 'duplicate', 'missing_unique', 'partial_unique'])
def test_catalog_refusals(source, request_value, change):
    if change == 'missing': source['columns'].pop()
    if change == 'nullable': source['columns'][0]['not_null'] = False
    if change == 'type': source['columns'][0]['type'] = 'text'
    if change == 'duplicate': source['columns'][-1] = deepcopy(source['columns'][0])
    if change == 'missing_unique': source['unique_keys'] = [{'columns': ['id']}]
    if change == 'partial_unique': source['unique_keys'] = [{'columns': m.KEY, 'predicate': 'symbol=BTCUSDT'}]
    with pytest.raises(ValueError): m.build(source, request_value)


@pytest.mark.parametrize('field,value', [('open', 'NaN'), ('open', '1e100'), ('open', 100),
    ('open', True), ('open', '0'), ('open', '-1'), ('open', '100.1234567891234'),
    ('volume', '-1'), ('high', '1.000000000000'), ('turnover', 'NaN'),
    ('symbol', 'ETHUSDT'), ('pair', 'ETH/USDT'), ('timeframe', '1m'), ('source', 'other'),
    ('close_time', '2026-10-01T00:06:00Z'), ('open_time', '2026-10-01T00:00:01Z'),
    ('storage_xmin', 'timestamp'), ('id', 'bad')])
def test_source_row_refusals(source, request_value, field, value):
    source['rows'][0][field] = value
    with pytest.raises(ValueError): m.build(source, request_value)


@pytest.mark.parametrize('change', ['duplicate_id', 'revised', 'reordered', 'extra_field', 'row_overflow', 'transport', 'request_binding', 'byte_limit'])
def test_source_shape_refusals(source, request_value, change):
    if change == 'duplicate_id': source['rows'][1]['id'] = source['rows'][0]['id']
    if change == 'revised': source['rows'][1]['open_time'] = source['rows'][0]['open_time']; source['rows'][1]['close_time'] = source['rows'][0]['close_time']
    if change == 'reordered': source['rows'].reverse()
    if change == 'extra_field': source['rows'][0]['label'] = 1
    if change == 'row_overflow': source['rows'] *= 129
    if change == 'transport': source['transport']['host'] = 'remote.example'
    if change == 'request_binding': source['request_sha256'] = '0'*64
    if change == 'byte_limit': source['junk'] = 'x'*512001
    with pytest.raises(ValueError): m.build(source, request_value)


@pytest.mark.parametrize('kind', ['gap', 'empty', 'partial', 'future_storage', 'created_after_update', 'open_bar'])
def test_unproven_rows_archived_but_no_capture(source, request_value, kind):
    if kind == 'gap': source['rows'].pop()
    if kind == 'empty': source['rows'].clear()
    if kind == 'partial':
        source['rows'][1]['ingested_at'] = source['rows'][1]['updated_at'] = '2026-10-01T00:09:00Z'
    if kind == 'future_storage': source['rows'][1]['updated_at'] = '2026-10-01T00:12:00Z'
    if kind == 'created_after_update': source['rows'][0]['created_at'] = '2026-10-01T00:10:59Z'
    if kind == 'open_bar': source['database']['read_started_at'] = '2026-10-01T00:09:30Z'
    result = m.build(source, request_value)
    assert result['report']['status'] == 'blocked' and result['report']['issues'] and result['capture'] is None


@pytest.mark.parametrize('field,value', [('client_observed_at', '2026-10-01T00:11:00Z'),
    ('client_observed_at', '2026-10-01T00:11:10Z'), ('read_completed_at', '2026-10-01T00:10:59Z')])
def test_clock_order_refusal(source, request_value, field, value):
    source[field] = value
    with pytest.raises(ValueError, match='clock_order'): m.build(source, request_value)


def test_private_artifact_rebuild_and_window_binding(monkeypatch, tmp_path, source, request_value):
    path, result = stage(monkeypatch, tmp_path, source, request_value)
    assert m.read_export(path) == result
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in path.iterdir())
    binding = m.bind_window(path, {'schema_version': 'research-window-request-v1', 'decision_time': request_value['end'], 'bars': 2})
    assert binding['window']['status'] == 'unavailable' and binding['training_data_admitted'] is False
    with pytest.raises(ValueError, match='new_export'): m.export_local(tmp_path, path, request_value)


@pytest.mark.parametrize('name', ['policy.json', 'request.json', 'source.json', 'capture.json', 'receipt.json'])
def test_artifact_tampering(monkeypatch, tmp_path, source, request_value, name):
    path, _ = stage(monkeypatch, tmp_path, source, request_value)
    (path/name).write_text('{}')
    with pytest.raises((ValueError, KeyError)): m.read_export(path)


def test_blocked_export_cannot_bind(monkeypatch, tmp_path, source, request_value):
    source['rows'].clear(); path, result = stage(monkeypatch, tmp_path, source, request_value)
    assert m.read_export(path) == result
    with pytest.raises(ValueError, match='no_usable_capture'): m.bind_window(path, {})


@pytest.mark.parametrize('kind', ['root', 'ancestor', 'file', 'permissions'])
def test_unsafe_artifact_paths(monkeypatch, tmp_path, source, request_value, kind):
    path, _ = stage(monkeypatch, tmp_path, source, request_value)
    if kind == 'root':
        alias = tmp_path/'alias'; alias.symlink_to(path, target_is_directory=True); path = alias
    if kind == 'ancestor':
        alias = tmp_path/'alias'; alias.symlink_to(tmp_path, target_is_directory=True); path = alias/'export'
    if kind == 'file':
        original = path/'source.json'; original.rename(path/'original.json'); original.symlink_to(path/'original.json')
    if kind == 'permissions': (path/'source.json').chmod(0o644)
    with pytest.raises(ValueError): m.read_export(path)


def test_missing_or_partial_artifact_refused(tmp_path):
    path = tmp_path/'partial'; path.mkdir(mode=0o700)
    with pytest.raises(ValueError): m.read_export(path)


def test_receipt_has_no_shared_implementation_alias(source, request_value):
    result = m.build(source, request_value)
    result['report']['implementation']['exporter'] = 'bad'
    assert m.build(source, request_value)['report']['status'] == 'observed'


class FakeDB:
    def __init__(self, source, failure=None): self.source = deepcopy(source); self.calls = []; self.closed = self.ended = False; self.failure = failure
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    @contextmanager
    def transaction(self):
        self.calls.append(('TRANSACTION', None))
        try: yield
        finally: self.ended = True
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if self.failure and sql == self.failure: raise RuntimeError('SECRET postgres://user:PASSWORD@host')
        value = None
        if sql == m.META_SQL:
            value = deepcopy(self.source['database']); value['read_started_at'] = m._utc(value['read_started_at'])
        if sql == m.COLUMNS_SQL: value = self.source['columns']
        if sql == m.KEY_SQL: value = self.source['unique_keys']
        if sql == m.ROWS_SQL:
            value = deepcopy(self.source['rows'])
            for row in value:
                for n in ('open_time', 'close_time', 'ingested_at', 'created_at', 'updated_at'): row[n] = m._utc(row[n])
        if sql == m.END_SQL: value = {'read_completed_at': m._utc(self.source['read_completed_at'])}
        return SimpleNamespace(fetchone=lambda: value, fetchmany=lambda size: value[:size])


def test_fixed_sql_readonly_transaction_and_parameter_bounds(monkeypatch, tmp_path, source, request_value):
    db = FakeDB(source); monkeypatch.setattr(m, '_connect', lambda _: db)
    observed = m._collect(tmp_path, request_value)
    assert db.closed and db.ended
    assert [sql for sql, _ in db.calls[:4]] == ['TRANSACTION',
        'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY', 'SET LOCAL ROLE service_role', "SET LOCAL TIME ZONE 'UTC'"]
    assert observed['rows'] == source['rows']
    assert [params for sql, params in db.calls if sql == m.ROWS_SQL] == [('bybit', 'spot', 'BTCUSDT', '5m',
        m._utc(request_value['start']), m._utc(request_value['end']), 257)]
    assert all(sql.startswith(('SET ', 'SELECT ', 'TRANSACTION')) for sql, _ in db.calls)
    assert all('BTCUSDT' not in sql for sql, _ in db.calls)


@pytest.mark.parametrize('failure', [m.META_SQL, m.COLUMNS_SQL, m.KEY_SQL, m.ROWS_SQL, m.END_SQL])
def test_driver_failure_closes_transaction_and_never_leaks_secrets(monkeypatch, tmp_path, source, request_value, failure):
    db = FakeDB(source, failure); monkeypatch.setattr(m, '_connect', lambda _: db)
    with pytest.raises(ValueError) as error: m._collect(tmp_path, request_value)
    assert str(error.value) == 'local_database_export_failed' and db.closed and db.ended


def test_query_overflow_not_silently_truncated(monkeypatch, tmp_path, source, request_value):
    source['rows'] *= 129; db = FakeDB(source); monkeypatch.setattr(m, '_connect', lambda _: db)
    with pytest.raises(ValueError): m._collect(tmp_path, request_value)
    assert db.closed and db.ended


def test_soft_deadline_closes_connection(monkeypatch, tmp_path, source, request_value):
    db = FakeDB(source); monkeypatch.setattr(m, '_connect', lambda _: db)
    clock = iter([0, 9]); monkeypatch.setattr(m.time, 'monotonic', lambda: next(clock))
    with pytest.raises(ValueError): m._collect(tmp_path, request_value)
    assert db.closed and db.ended and not any(sql == m.ROWS_SQL for sql, _ in db.calls)


def credential_project(tmp_path):
    (tmp_path/'.env').write_text('CRYPTOFORGE_BACKEND=local\nSUPABASE_KEY=unused\n'); (tmp_path/'.env').chmod(0o600)
    secret = tmp_path/'.local/database'; secret.mkdir(parents=True, mode=0o700)
    (secret/'compose.env').write_text('POSTGRES_PASSWORD=never-use-admin\nPOSTGREST_DB_PASSWORD=private-password\n')
    (secret/'compose.env').chmod(0o600)
    return secret


def test_pinned_loopback_connector_uses_existing_nonsuperuser_secret(monkeypatch, tmp_path):
    credential_project(tmp_path); captured = {}
    driver = ModuleType('psycopg'); driver.connect = lambda **kwargs: captured.update(kwargs) or 'connection'
    rows = ModuleType('psycopg.rows'); rows.dict_row = object()
    monkeypatch.setitem(sys.modules, 'psycopg', driver); monkeypatch.setitem(sys.modules, 'psycopg.rows', rows)
    monkeypatch.setattr(m, 'version', lambda _: '3.3.6'); monkeypatch.delenv('CRYPTOFORGE_BACKEND', raising=False)
    assert m._connect(tmp_path) == 'connection'
    assert captured['host'] == captured['hostaddr'] == '127.0.0.1' and captured['port'] == 55432
    assert captured['user'] == 'authenticator' and captured['password'] == 'private-password'
    assert captured['autocommit'] and captured['connect_timeout'] == 3 and 'default_transaction_read_only=on' in captured['options']


@pytest.mark.parametrize('kind', ['cloud', 'duplicate', 'env_conflict', 'public_secret', 'symlink_secret', 'driver', 'missing_password'])
def test_connector_refusals_without_driver_call(monkeypatch, tmp_path, kind):
    secret = credential_project(tmp_path)
    if kind == 'cloud': (tmp_path/'.env').write_text('CRYPTOFORGE_BACKEND=supabase\n')
    if kind == 'duplicate': (tmp_path/'.env').write_text('CRYPTOFORGE_BACKEND=local\nCRYPTOFORGE_BACKEND=local\n')
    if kind == 'env_conflict': monkeypatch.setenv('CRYPTOFORGE_BACKEND', 'supabase')
    if kind == 'public_secret': (secret/'compose.env').chmod(0o644)
    if kind == 'symlink_secret':
        (secret/'compose.env').rename(secret/'secret'); (secret/'compose.env').symlink_to(secret/'secret')
    if kind == 'driver': monkeypatch.setattr(m, 'version', lambda _: '0.0')
    if kind == 'missing_password': (secret/'compose.env').write_text('POSTGRES_PASSWORD=admin\n')
    with pytest.raises(ValueError): m._connect(tmp_path)


def test_cli_safe_refusal(capsys, tmp_path):
    assert m.main(['verify', '--directory', str(tmp_path/'missing')]) == 2
    assert capsys.readouterr().out == 'Local export verification refused; no training admission\n'


def test_cli_export_verify_and_unavailable_window(monkeypatch, capsys, tmp_path, source, request_value):
    monkeypatch.setattr(m, '_collect', lambda *_: deepcopy(source))
    req = tmp_path/'request.json'; req.write_text(json.dumps(request_value))
    policy = tmp_path/'policy.json'; policy.write_text(json.dumps(m.POLICY))
    path = tmp_path/'export'
    assert m.main(['export', '--directory', str(path), '--project', str(tmp_path), '--request', str(req), '--policy', str(policy)]) == 0
    assert m.main(['verify', '--directory', str(path)]) == 0
    req.write_text(json.dumps({'schema_version': 'research-window-request-v1', 'decision_time': request_value['end'], 'bars': 2}))
    assert m.main(['window', '--directory', str(path), '--request', str(req)]) == 2
    assert '100.123456789123' not in capsys.readouterr().out
