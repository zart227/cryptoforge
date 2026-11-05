"""Bounded local PostgreSQL observations; no historical training admission or writes."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import re
import stat
import time
from uuid import UUID

from cryptoforge import research_feature_windows as windows
from cryptoforge import semantic_source_collector as files
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp

POLICY = {'schema_version': 'research-local-export-policy-v1', 'host': '127.0.0.1',
    'port': 55432, 'database': 'cryptoforge', 'login': 'authenticator', 'role': 'service_role',
    'driver_version': '3.3.6', 'max_rows': 256, 'max_source_bytes': 512000,
    'connect_timeout_seconds': 3, 'statement_timeout_ms': 3000, 'lock_timeout_ms': 250,
    'idle_transaction_timeout_ms': 5000, 'database_soft_deadline_seconds': 8,
    'isolation': 'repeatable read', 'read_only': True, 'training_admission_enabled': False}
TIMEFRAMES = {60: '1m', 300: '5m', 900: '15m', 3600: '60m'}
COLUMNS = {'id': 'uuid', **{n: 'text' for n in ('exchange', 'market_type', 'symbol', 'pair', 'timeframe', 'source')},
    **{n: 'timestamp with time zone' for n in ('open_time', 'close_time', 'ingested_at', 'created_at', 'updated_at')},
    **{n: 'numeric(28,12)' for n in ('open', 'high', 'low', 'close')},
    **{n: 'numeric(36,12)' for n in ('volume', 'turnover')}}
KEY = ['exchange', 'market_type', 'symbol', 'timeframe', 'open_time']
META_SQL = """SELECT current_database() AS database, session_user::text AS login,
 current_user::text AS role, current_setting('server_version_num') AS server_version_num,
 current_setting('transaction_read_only') AS read_only,
 current_setting('transaction_isolation') AS isolation,
 current_setting('statement_timeout') AS statement_timeout,
 current_setting('lock_timeout') AS lock_timeout,
 current_setting('idle_in_transaction_session_timeout') AS idle_timeout,
 (SELECT rolsuper FROM pg_roles WHERE rolname=session_user) AS login_superuser,
 (SELECT oid::text FROM pg_database WHERE datname=current_database()) AS database_oid,
 inet_server_addr()::text AS server_address, inet_server_port() AS server_port,
 pg_current_snapshot()::text AS snapshot, clock_timestamp() AS read_started_at"""
COLUMNS_SQL = """SELECT a.attname::text AS name, format_type(a.atttypid,a.atttypmod) AS type,
 a.attnotnull AS not_null FROM pg_attribute a
 WHERE a.attrelid='public.market_candles'::regclass AND a.attnum>0 AND NOT a.attisdropped
 ORDER BY a.attnum"""
KEY_SQL = """SELECT array_agg(a.attname::text ORDER BY k.ord) AS columns
 FROM pg_index i CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord)
 JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum
 WHERE i.indrelid='public.market_candles'::regclass AND i.indisunique AND i.indisvalid
 AND i.indpred IS NULL AND i.indexprs IS NULL AND k.ord<=i.indnkeyatts
 GROUP BY i.indexrelid"""
ROWS_SQL = """SELECT id::text AS id, exchange, market_type, symbol, pair, timeframe,
 open_time, close_time, open::text AS open, high::text AS high, low::text AS low,
 close::text AS close, volume::text AS volume, turnover::text AS turnover,
 source, ingested_at, created_at, updated_at, xmin::text AS storage_xmin
 FROM public.market_candles WHERE exchange=%s AND market_type=%s AND symbol=%s
 AND timeframe=%s AND open_time>=%s AND open_time<%s
 ORDER BY open_time,id LIMIT %s"""
END_SQL = 'SELECT clock_timestamp() AS read_completed_at'


def implementation():
    return {'exporter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'feature_inputs': windows.implementation()}


_LOADED = implementation()


def _guard(policy):
    if canonical(policy) != canonical(POLICY): raise ValueError('fixed_local_export_policy_required')
    if implementation() != _LOADED: raise ValueError('local_export_implementation_changed_restart_required')


def _utc(value):
    result = timestamp(value)
    if not 1970 <= result.year <= 2100: raise ValueError('bounded_aware_timestamp_required')
    return result


def _stamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None: raise ValueError('database_aware_timestamp_required')
    return value.astimezone(timezone.utc).isoformat()


def validate_request(value):
    if type(value) is not dict: raise ValueError('plain_export_request_required')
    exact_fields(value, {'schema_version', 'symbol', 'timeframe_seconds', 'start', 'end', 'partition', 'development_end'})
    if (value['schema_version'] != 'research-local-export-request-v1'
            or type(value['symbol']) is not str or re.fullmatch(r'[A-Z0-9]{1,24}USDT', value['symbol']) is None
            or type(value['timeframe_seconds']) is not int or value['timeframe_seconds'] not in TIMEFRAMES
            or value['partition'] not in ('train', 'validation')):
        raise ValueError('bounded_local_development_request_required')
    start, end, boundary = (_utc(value[n]) for n in ('start', 'end', 'development_end'))
    step = value['timeframe_seconds']; epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if (not start < end <= boundary or any(t.microsecond or int((t-epoch).total_seconds()) % step for t in (start, end))
            or (end-start).total_seconds() > step * POLICY['max_rows']):
        raise ValueError('bounded_aligned_development_range_required')
    return start, end, boundary


def _safe_directory(path, private=False):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink(): raise ValueError('symlink_directory_refused')
    if not path.is_dir(): raise ValueError('existing_directory_required')
    if private and (stat.S_IMODE(path.stat().st_mode) != 0o700 or path.stat().st_uid != os.getuid()):
        raise ValueError('owner_private_directory_required')
    return path


def _private_read(directory, name, maximum, mode=0o600):
    _safe_directory(directory)
    path = Path(directory)/name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != mode or info.st_size > maximum):
                raise ValueError('bounded_owner_private_file_required')
            raw = stream.read(maximum+1)
    except OSError:
        raise ValueError('private_file_unavailable') from None
    if len(raw) > maximum: raise ValueError('private_file_byte_limit')
    return raw


def _setting(raw, name):
    # Read only one explicitly named setting. Never emit secret-bearing input/errors.
    try:
        values = [line.split('=', 1)[1].strip().strip('"\'') for line in raw.decode().splitlines()
                  if line.strip().startswith(name+'=')]
    except (UnicodeError, IndexError): raise ValueError('local_setting_invalid') from None
    if len(values) != 1 or not values[0] or len(values[0]) > 512: raise ValueError('unique_local_setting_required')
    return values[0]


def _connect(project):
    project = _safe_directory(project)
    # The selector can contain other credentials; only this setting is consumed.
    if _setting(_private_read(project, '.env', 65536), 'CRYPTOFORGE_BACKEND') != 'local':
        raise ValueError('explicit_local_backend_required')
    if os.environ.get('CRYPTOFORGE_BACKEND', 'local') != 'local': raise ValueError('local_backend_environment_conflict')
    secret_dir = _safe_directory(project/'.local/database', private=True)
    password = _setting(_private_read(secret_dir, 'compose.env', 8192), 'POSTGREST_DB_PASSWORD')
    if version('psycopg') != POLICY['driver_version'] or version('psycopg-binary') != POLICY['driver_version']:
        raise ValueError('pinned_postgres_driver_required')
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=55432,
        dbname='cryptoforge', user='authenticator', password=password, autocommit=True,
        connect_timeout=3, sslmode='disable', gssencmode='disable', row_factory=dict_row,
        application_name='cryptoforge-research-local-export',
        options='-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000')


def _metadata(meta):
    exact_fields(meta, {'database', 'login', 'role', 'server_version_num', 'read_only', 'isolation',
        'statement_timeout', 'lock_timeout', 'idle_timeout', 'login_superuser', 'database_oid',
        'server_address', 'server_port', 'snapshot', 'read_started_at'})
    if (meta['database'] != 'cryptoforge' or meta['login'] != 'authenticator' or meta['role'] != 'service_role'
            or meta['read_only'] != 'on' or meta['isolation'] != 'repeatable read' or meta['login_superuser'] is not False
            or meta['statement_timeout'] != '3s' or meta['lock_timeout'] != '250ms' or meta['idle_timeout'] != '5s'
            or type(meta['server_port']) is not int or not 1 <= meta['server_port'] <= 65535
            or type(meta['server_address']) is not str or len(meta['server_address']) > 64
            or type(meta['server_version_num']) is not str or not re.fullmatch(r'17\d{4}', meta['server_version_num'])
            or type(meta['database_oid']) is not str or not re.fullmatch(r'\d{1,10}', meta['database_oid'])
            or type(meta['snapshot']) is not str or not re.fullmatch(r'\d{1,20}:\d{1,20}:(?:\d{1,20}(?:,\d{1,20})*)?', meta['snapshot'])):
        raise ValueError('observed_readonly_local_connection_required')
    _utc(meta['read_started_at'])


def _catalog(columns, keys):
    if type(columns) is not list or len(columns) != len(COLUMNS): raise ValueError('market_schema_changed')
    names = []
    for col in columns:
        exact_fields(col, {'name', 'type', 'not_null'})
        if col['name'] not in COLUMNS or col['type'] != COLUMNS[col['name']] or col['not_null'] is not True:
            raise ValueError('market_schema_changed')
        names.append(col['name'])
    if len(set(names)) != len(COLUMNS) or type(keys) is not list or not 1 <= len(keys) <= 16:
        raise ValueError('market_schema_changed')
    if any(type(k) is not dict or set(k) != {'columns'} or type(k['columns']) is not list
           or not 1 <= len(k['columns']) <= 32 or any(type(n) is not str or n not in COLUMNS for n in k['columns']) for k in keys):
        raise ValueError('market_unique_keys_invalid')
    if {'columns': KEY} not in keys: raise ValueError('market_scope_unique_index_required')


def _collect(project, request):
    start, end, _ = validate_request(request); began = time.monotonic()
    def deadline():
        if time.monotonic()-began > POLICY['database_soft_deadline_seconds']:
            raise ValueError('local_database_soft_deadline')
    try:
        with _connect(project) as db:
            with db.transaction():
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                db.execute('SET LOCAL ROLE service_role')
                db.execute("SET LOCAL TIME ZONE 'UTC'")
                meta = dict(db.execute(META_SQL).fetchone()); meta['read_started_at'] = _stamp(meta['read_started_at'])
                _metadata(meta); deadline()
                columns = [dict(row) for row in db.execute(COLUMNS_SQL).fetchmany(19)]
                keys = [dict(row) for row in db.execute(KEY_SQL).fetchmany(17)]
                _catalog(columns, keys); deadline()
                rows = [dict(row) for row in db.execute(ROWS_SQL, ('bybit', 'spot', request['symbol'],
                    TIMEFRAMES[request['timeframe_seconds']], start, end, POLICY['max_rows']+1)).fetchmany(POLICY['max_rows']+1)]
                if len(rows) > POLICY['max_rows']: raise ValueError('source_row_limit')
                completed = _stamp(db.execute(END_SQL).fetchone()['read_completed_at']); deadline()
        observed = _stamp(datetime.now(timezone.utc))
        for row in rows:
            for field in ('open_time', 'close_time', 'created_at', 'ingested_at', 'updated_at'): row[field] = _stamp(row[field])
        return {'schema_version': 'research-local-observation-v1', 'request_sha256': digest(request),
            'transport': {'host': '127.0.0.1', 'port': 55432, 'driver': 'psycopg', 'driver_version': '3.3.6'},
            'database': meta, 'columns': columns, 'unique_keys': keys,
            'read_completed_at': completed, 'client_observed_at': observed, 'rows': rows}
    except (KeyboardInterrupt, SystemExit): raise
    except Exception:
        # Driver messages can include credentials, SQL, endpoints or connection strings.
        raise ValueError('local_database_export_failed') from None


def _decimal(value, maximum, positive=False):
    if type(value) is not str or len(value) > 64 or re.fullmatch(r'-?\d{1,36}(?:\.\d{1,12})?', value) is None:
        raise ValueError('exact_decimal_source_required')
    number = Decimal(value)
    if not (0 < number <= maximum if positive else 0 <= number <= maximum):
        raise ValueError('source_decimal_out_of_bounds')
    return number


def build(source, request, policy=POLICY):
    """Rebuild offline evidence. Hashes do not authenticate a database/publisher."""
    _guard(policy); start, end, boundary = validate_request(request)
    if type(source) is not dict or len(canonical(source).encode()) > POLICY['max_source_bytes']:
        raise ValueError('bounded_source_object_required')
    exact_fields(source, {'schema_version', 'request_sha256', 'transport', 'database', 'columns',
        'unique_keys', 'read_completed_at', 'client_observed_at', 'rows'})
    if (source['schema_version'] != 'research-local-observation-v1' or source['request_sha256'] != digest(request)
            or source['transport'] != {'host': '127.0.0.1', 'port': 55432, 'driver': 'psycopg', 'driver_version': '3.3.6'}):
        raise ValueError('fixed_local_source_binding_required')
    _metadata(source['database']); _catalog(source['columns'], source['unique_keys'])
    began = _utc(source['database']['read_started_at']); completed = _utc(source['read_completed_at'])
    observed = _utc(source['client_observed_at'])
    if not began <= completed <= observed or observed-completed > timedelta(seconds=5):
        raise ValueError('observation_clock_order_required')
    rows = source['rows']
    if type(rows) is not list or len(rows) > POLICY['max_rows']: raise ValueError('bounded_source_rows_required')
    candles, ids, opens, issues = [], set(), [], set()
    for row in rows:
        if type(row) is not dict: raise ValueError('plain_source_row_required')
        exact_fields(row, {*COLUMNS, 'storage_xmin'})
        if (type(row['id']) is not str or str(UUID(row['id'])) != row['id'] or row['id'] in ids
                or type(row['storage_xmin']) is not str or re.fullmatch(r'\d{1,10}', row['storage_xmin']) is None):
            raise ValueError('source_storage_identity_invalid')
        ids.add(row['id'])
        if (row['exchange'] != 'bybit' or row['market_type'] != 'spot' or row['symbol'] != request['symbol']
                or row['pair'] != request['symbol'][:-4]+'/USDT' or row['timeframe'] != TIMEFRAMES[request['timeframe_seconds']]
                or row['source'] != 'bybit_public_api'):
            raise ValueError('source_market_scope_mismatch')
        opened, closed, created, ingested, updated = (_utc(row[n]) for n in
            ('open_time', 'close_time', 'created_at', 'ingested_at', 'updated_at'))
        step = timedelta(seconds=request['timeframe_seconds'])
        if (not start <= opened < end or closed != opened+step or closed > end
                or opened.microsecond or (opened-start).total_seconds() % request['timeframe_seconds']):
            raise ValueError('source_candle_range_invalid')
        if opens and opened <= opens[-1]: raise ValueError('source_candle_order_or_revision_invalid')
        opens.append(opened)
        values = {name: _decimal(row[name], windows.POLICY['max_volume'] if name == 'volume' else windows.POLICY['max_price'], name != 'volume')
                  for name in windows.FIELDS}
        _decimal(row['turnover'], Decimal('1e24'))
        if not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
            raise ValueError('source_ohlc_inconsistent')
        if closed > began: issues.add('candle_not_closed_before_read')
        if max(ingested, updated) < closed: issues.add('stored_before_candle_close')
        if not created <= updated <= began or ingested > began or created < opened or ingested < opened:
            issues.add('source_storage_clock_order_unproven')
        candles.append({'open_time': opened.isoformat(), 'observed_at': observed.isoformat(),
                        **{name: float(number) for name, number in values.items()}})
    expected = int((end-start).total_seconds()) // request['timeframe_seconds']
    if len(opens) != expected or any(t != start+i*timedelta(seconds=request['timeframe_seconds']) for i, t in enumerate(opens)):
        issues.add('requested_interval_coverage_incomplete')
    capture = None if issues else {'schema_version': 'research-candle-capture-v1', 'origin': 'external_unverified',
        'source_backend': 'local_postgresql', 'source_export_sha256': digest(source), 'captured_at': observed.isoformat(),
        'partition': request['partition'], 'development_end': boundary.isoformat(),
        'exchange': 'bybit', 'market_type': 'spot', 'symbol': request['symbol'],
        'timeframe_seconds': request['timeframe_seconds'], 'candles': candles}
    if capture is not None:
        windows.prepare(capture, {'schema_version': 'research-window-request-v1',
            'decision_time': end.isoformat(), 'bars': min(expected, 64)}, windows.POLICY)
    report = {'schema_version': 'research-local-export-receipt-v1', 'status': 'blocked' if issues else 'observed',
        'source_sha256': digest(source), 'request_sha256': digest(request), 'policy_sha256': digest(policy),
        'catalog_sha256': digest({'columns': source['columns'], 'unique_keys': source['unique_keys']}),
        'capture_sha256': digest(capture), 'row_count': len(rows), 'expected_rows': expected, 'issues': sorted(issues),
        'connection_checks_recorded': True, 'live_connection_rechecked': False,
        'decimal_source_preserved': True, 'feature_numeric_conversion': 'binary64',
        'value_observation_rule': 'client_observed_at_only', 'storage_xmin_is_commit_time': False,
        'historical_availability_verified': False, 'upstream_publisher_authenticated': False,
        'append_only_revision_history_verified': False, 'database_identity_cryptographically_authenticated': False,
        'development_split_approved': False, 'training_data_admitted': False, 'training_executed': False,
        'candidate_executed': False, 'implementation': deepcopy(_LOADED)}
    return {'report': {**report, 'receipt_sha256': digest(report)}, 'capture': capture}


def export_local(project, directory, request, policy=POLICY):
    _guard(policy); validate_request(request)
    directory = Path(directory).absolute(); _safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_export_directory_required')
    source = _collect(project, request); result = build(source, request, policy)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', policy), ('request.json', request), ('source.json', source),
                        ('capture.json', result['capture']), ('receipt.json', result['report'])):
        files._write(directory, name, value)
    files._sync(directory); files._sync(directory.parent)
    return result


def read_export(directory):
    directory = _safe_directory(directory, private=True)
    def read(name, maximum):
        return files.strict_json(_private_read(directory, name, maximum).decode(), max_bytes=maximum)
    policy = read('policy.json', 4000); request = read('request.json', 4000)
    result = build(read('source.json', POLICY['max_source_bytes']), request, policy)
    if canonical(read('capture.json', POLICY['max_source_bytes'])) != canonical(result['capture']):
        raise ValueError('export_capture_changed')
    if canonical(read('receipt.json', 16000)) != canonical(result['report']):
        raise ValueError('export_receipt_changed')
    return result


def bind_window(directory, request):
    result = read_export(directory)
    if result['capture'] is None: raise ValueError('export_has_no_usable_capture')
    window = windows.prepare(result['capture'], request, windows.POLICY)
    return {'schema_version': 'research-local-window-binding-v1',
        'export_receipt_sha256': result['report']['receipt_sha256'],
        'capture_sha256': result['report']['capture_sha256'], 'window': window,
        'live_connection_rechecked': False, 'training_data_admitted': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('export', 'verify', 'window'):
        cmd = sub.add_parser(name); cmd.add_argument('--directory', type=Path, required=True)
        if name == 'export':
            cmd.add_argument('--project', type=Path, required=True); cmd.add_argument('--request', type=Path, required=True)
            cmd.add_argument('--policy', type=Path, required=True)
        if name == 'window': cmd.add_argument('--request', type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path): return files._json(path.parent, path.name, 4000)
    try:
        if args.command == 'export': result = export_local(args.project, args.directory, read(args.request), read(args.policy)); status = result['report']['status']
        elif args.command == 'verify': result = read_export(args.directory); status = result['report']['status']
        else: result = bind_window(args.directory, read(args.request)); status = result['window']['status']
    except Exception:
        print('Local export verification refused; no training admission')
        return 2
    # No SQL/data/connection exception contents printed to terminal or providers.
    print('Local export artifact: '+status+'; training admission disabled')
    return 0 if status in ('observed', 'prepared') else 2


if __name__ == '__main__':
    raise SystemExit(main())
