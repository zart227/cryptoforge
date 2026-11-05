"""Original local-source observations, separately pinned from frozen paper v2.

Source times imported from cloud/cache are claims, not historical availability.
Each row becomes known conservatively at completion of THIS original read.
Polling completeness, forecasts, REST identity and host qualification are outside
this component. No database, trading, model, or existing evidence is modified.
"""
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
from uuid import UUID
from urllib.parse import urlsplit

from cryptoforge.backend import resolve_backend
from cryptoforge.local_source_observer import INTERVALS, MAX_BYTES, MAX_SECONDS, query_sql


SCHEMA = 'local-source-provenance-v1'
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
TIME_FIELDS = ('open_time', 'close_time', 'ingested_at', 'created_at', 'updated_at')
COLUMNS = [
    ('id', 'uuid'), ('exchange', 'text'), ('market_type', 'text'), ('symbol', 'text'),
    ('pair', 'text'), ('timeframe', 'text'), ('open_time', 'timestamp with time zone'),
    ('close_time', 'timestamp with time zone'),
    *[(key, 'numeric(28,12)') for key in ('open', 'high', 'low', 'close')],
    *[(key, 'numeric(36,12)') for key in ('volume', 'turnover')],
    ('source', 'text'), *[(key, 'timestamp with time zone') for key in TIME_FIELDS[2:]],
]
FLAGS = dict(source_poll_completeness_verified=False, historical_known_at_verified=False,
             rest_instance_identity_verified=False, full_worker_or_host_qualified=False,
             paper_evidence_pass=False, economic_profitability_established=False,
             live_admission_granted=False)
_RUNTIME_PATHS = {name: Path(__file__).with_name(name) for name in
                  ('local_source_provenance.py', 'local_source_observer.py', 'backend.py')}
_RUNTIME_PATHS['audit_local_source_provenance.py'] = Path(__file__).resolve().parents[2] / 'scripts/audit_local_source_provenance.py'
_LOADED_RUNTIME = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in _RUNTIME_PATHS.items()}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('original SHA256 pin required')
    return value


def parse(raw, *, decimal=False):
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise ValueError('duplicate source JSON field')
            out[key] = value
        return out
    def invalid(_):
        raise ValueError('nonfinite source JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid,
                      **({'parse_float': Decimal} if decimal else {}))


def stamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('aware original source timestamp required')
    return value.astimezone(UTC)


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError('explicit original source schema required')


def read_file(path, *, maximum=MAX_ARTIFACT_BYTES):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise ValueError('canonical source file required')
    info = path.lstat()
    if not path.is_file() or path.is_symlink() or info.st_nlink != 1 or info.st_size > maximum:
        raise ValueError('bounded private original source file required')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('source file grew beyond byte budget')
    return raw


def runtime_hashes():
    current = {name: digest(path.read_bytes()) for name, path in _RUNTIME_PATHS.items()}
    if current != _LOADED_RUNTIME:
        raise ValueError('loaded source runtime changed on disk; fresh process/contract required')
    return current


def migration_snapshot(directory):
    """Pin retained migration evidence; do not re-import or claim current equality."""
    directory = Path(directory).absolute()
    names = ('metadata.json', 'source-hashes.json', 'verification.json', 'backup-restore-verification.json')
    raws = {name: read_file(directory / name, maximum=2 * 1024 * 1024) for name in names}
    values = {name: parse(raw) for name, raw in raws.items()}
    source = values['source-hashes.json']
    if type(source) is not list or not 1 <= len(source) <= 256:
        raise ValueError('bounded retained source table inventory required')
    tables = {}
    for item in source:
        _keys(item, ('table_name', 'rows', 'content_hash'))
        if (type(item['table_name']) is not str or not re.fullmatch(r'(public|freqtrade)\.[A-Za-z_][A-Za-z0-9_]{0,62}', item['table_name'])
                or type(item['rows']) is not int or not 0 <= item['rows'] <= 2**63-1
                or type(item['content_hash']) is not str or not re.fullmatch('[0-9a-f]{32}', item['content_hash'])
                or item['table_name'] in tables):
            raise ValueError('invalid original migration table identity')
        tables[item['table_name']] = item
    metadata = values['metadata.json']
    meta_names = [t['schema'] + '.' + t['name'] for t in metadata['tables']]
    if len(meta_names) != len(tables) or set(meta_names) != set(tables) or 'public.market_candles' not in tables:
        raise ValueError('migration metadata/source table inventory differs')
    for name in names[2:]:
        value = values[name]
        retained = value['tables']
        if (value.get('all_tables_match') is not True or value['table_count'] != len(tables)
                or value['total_rows'] != sum(t['rows'] for t in tables.values())
                or type(retained) is not list or sorted(retained, key=lambda t: t['table_name']) != sorted(source, key=lambda t: t['table_name'])):
            raise ValueError('original migration/restore receipts disagree')
        stamp(value['verified_at'])
    result = dict(schema_version='retained-local-migration-snapshot-v1',
                  files={name: digest(raw) for name, raw in raws.items()},
                  table_count=len(tables), original_rows=sum(t['rows'] for t in tables.values()),
                  migrated_at=values['verification.json']['verified_at'],
                  backup_restore_verified_at=values[names[-1]]['verified_at'],
                  current_rows_equal_original_snapshot_verified=False,
                  historical_row_availability_verified=False)
    return result


def _migration(value):
    _keys(value, ('schema_version', 'files', 'table_count', 'original_rows', 'migrated_at',
                  'backup_restore_verified_at', 'current_rows_equal_original_snapshot_verified',
                  'historical_row_availability_verified'))
    _keys(value['files'], ('metadata.json', 'source-hashes.json', 'verification.json', 'backup-restore-verification.json'))
    for pin in value['files'].values():
        sha(pin)
    if (value['schema_version'] != 'retained-local-migration-snapshot-v1'
            or type(value['table_count']) is not int or not 1 <= value['table_count'] <= 256
            or type(value['original_rows']) is not int or not 0 <= value['original_rows'] <= 2**63-1
            or value['current_rows_equal_original_snapshot_verified'] is not False
            or value['historical_row_availability_verified'] is not False
            or stamp(value['backup_restore_verified_at']) < stamp(value['migrated_at'])):
        raise ValueError('original retained migration snapshot required')


def _identity(value):
    _keys(value, ('system_identifier', 'database', 'database_oid', 'server_version_num', 'relation_sha256'))
    _positive_text(value['system_identifier'], 2**64-1)
    _positive_text(value['database_oid'], 2**32-1)
    sha(value['relation_sha256'])
    if (value['database'] != 'cryptoforge' or type(value['server_version_num']) is not str
            or not re.fullmatch('17[0-9]{4}', value['server_version_num'])):
        raise ValueError('original local database identity required')


def _backend(value):
    _keys(value, ('name', 'api_origin', 'transport'))
    parsed = urlsplit(value['api_origin'])
    if (value['name'] != 'local' or value['transport'] != 'local_docker_postgres_read_only'
            or parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError('credential-free local source backend required')


def _positive_text(value, maximum):
    if type(value) is not str or not re.fullmatch('[1-9][0-9]{0,19}', value) or int(value) > maximum:
        raise ValueError('original PostgreSQL numeric identity required')


def _relation(value):
    _keys(value, ('schema', 'schema_oid', 'table', 'table_oid', 'kind', 'persistence',
                  'rls_enabled', 'rls_forced', 'columns', 'constraints', 'indexes', 'triggers', 'policies'))
    if (value['schema'] != 'public' or value['table'] != 'market_candles'
            or value['kind'] != 'r' or value['persistence'] != 'p'
            or type(value['rls_enabled']) is not bool or type(value['rls_forced']) is not bool):
        raise ValueError('original ordinary public candle relation required')
    for key in ('schema_oid', 'table_oid'):
        _positive_text(value[key], 2**32-1)
    columns = value['columns']
    if type(columns) is not list or len(columns) != len(COLUMNS):
        raise ValueError('original candle column inventory differs')
    for i, (column, (name, datatype)) in enumerate(zip(columns, COLUMNS), 1):
        _keys(column, ('position', 'name', 'type', 'not_null', 'generated', 'identity', 'collation_oid', 'default_sha256'))
        if (type(column['position']) is not int or column['position'] != i
                or column['name'] != name or column['type'] != datatype or column['not_null'] is not True
                or column['generated'] != '' or column['identity'] != ''
                or type(column['collation_oid']) is not str or not re.fullmatch('[0-9]{1,10}', column['collation_oid'])):
            raise ValueError('original candle column contract differs')
        sha(column['default_sha256'])
    shapes = dict(constraints=('name', 'type', 'validated', 'definition_sha256'),
                  indexes=('name', 'valid', 'ready', 'definition_sha256'),
                  triggers=('name', 'enabled', 'definition_sha256', 'function_sha256'),
                  policies=('name', 'command', 'permissive', 'roles', 'using_sha256', 'check_sha256'))
    for group, keys in shapes.items():
        rows = value[group]
        if type(rows) is not list or len(rows) > 64:
            raise ValueError('bounded relation definition inventory required')
        names = []
        for row in rows:
            _keys(row, keys)
            if type(row['name']) is not str or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,62}', row['name']):
                raise ValueError('original relation object name required')
            names.append(row['name'])
            for key in keys:
                if key.endswith('_sha256'):
                    sha(row[key])
            if group == 'constraints' and (row['type'] not in ('p', 'u', 'c', 'f', 'x') or row['validated'] is not True):
                raise ValueError('validated relation constraints required')
            if group == 'indexes' and (row['valid'] is not True or row['ready'] is not True):
                raise ValueError('ready valid source indexes required')
            if group == 'triggers' and row['enabled'] not in ('O', 'A', 'D', 'R'):
                raise ValueError('original trigger state required')
            if group == 'policies' and (row['command'] not in ('*', 'r', 'a', 'w', 'd')
                    or type(row['permissive']) is not bool or type(row['roles']) is not str
                    or not re.fullmatch(r'\{[0-9]+(,[0-9]+)*\}', row['roles'])):
                raise ValueError('original RLS policy definition required')
        if names != sorted(set(names)):
            raise ValueError('ordered unique relation definitions required')


def validate_observation(observation):
    _keys(observation, ('prepared_at', 'completed_at', 'elapsed_seconds', 'query', 'query_sha256', 'runtime', 'raw_response'))
    before, after = stamp(observation['prepared_at']), stamp(observation['completed_at'])
    elapsed = observation['elapsed_seconds']
    if (type(elapsed) not in (float, int) or not math.isfinite(elapsed) or not 0 <= elapsed <= MAX_SECONDS
            or not 0 <= (after-before).total_seconds() <= MAX_SECONDS+2):
        raise ValueError('original bounded source clocks required')
    query = observation['query']
    _keys(query, ('pair', 'timeframe', 'limit'))
    expected_sql = query_sql(query['pair'], query['timeframe'], query['limit'], before)
    if observation['runtime'] != runtime_hashes() or observation['query_sha256'] != digest(expected_sql.encode()):
        raise ValueError('original observer runtime/query SHA differs')
    raw = observation['raw_response']
    if type(raw) is not str or len(raw) > MAX_BYTES or len(raw.encode()) > MAX_BYTES:
        raise ValueError('bounded original source response required')
    source = parse(raw)
    _keys(source, ('schema_version', 'system_identifier', 'database', 'database_oid',
                  'server_version_num', 'transaction_read_only', 'transaction_isolation',
                  'database_clock', 'snapshot', 'relation', 'rows'))
    if (source['schema_version'] != 'local-postgres-observation-v1' or source['database'] != 'cryptoforge'
            or source['transaction_read_only'] != 'on' or source['transaction_isolation'] != 'repeatable read'
            or type(source['server_version_num']) is not str or not re.fullmatch('17[0-9]{4}', source['server_version_num'])
            or not before.timestamp()-2 <= stamp(source['database_clock']).timestamp() <= after.timestamp()+2
            or type(source['snapshot']) is not str or not re.fullmatch(r'[0-9]+:[0-9]+:([0-9]+(,[0-9]+)*)?', source['snapshot'])):
        raise ValueError('original read-only PostgreSQL17 snapshot required')
    _positive_text(source['system_identifier'], 2**64-1)
    _positive_text(source['database_oid'], 2**32-1)
    _relation(source['relation'])
    identity = {key: source[key] for key in ('system_identifier', 'database', 'database_oid', 'server_version_num')}
    identity['relation_sha256'] = digest(canonical(source['relation']))
    rows = source['rows']
    if type(rows) is not list or len(rows) != query['limit']:
        raise ValueError('complete requested bounded candle window required')
    records, ids, previous = [], set(), None
    for row in rows:
        _keys(row, ('table_oid', 'row_version', 'raw_json'))
        _positive_text(row['row_version'], 2**32-1)
        if row['table_oid'] != source['relation']['table_oid'] or type(row['raw_json']) is not str or len(row['raw_json']) > 16384:
            raise ValueError('original row table/version/byte identity required')
        body = parse(row['raw_json'], decimal=True)
        _keys(body, [name for name, _ in COLUMNS])
        if (type(body['id']) is not str or str(UUID(body['id'])) != body['id'] or body['id'] in ids
                or body['exchange'] != 'bybit' or body['market_type'] != 'spot' or body['source'] != 'bybit_public_api'
                or body['pair'] != query['pair'] or body['symbol'] != query['pair'].replace('/', '')
                or body['timeframe'] != query['timeframe']):
            raise ValueError('original source row identity/scope required')
        times = {key: stamp(body[key]) for key in TIME_FIELDS}
        interval = INTERVALS[query['timeframe']]
        if (times['open_time'].microsecond or int(times['open_time'].timestamp()) % interval
                or (times['close_time']-times['open_time']).total_seconds() != interval
                or times['close_time'] > before or any(times[key] > after for key in TIME_FIELDS[2:])
                or (previous is not None and times['open_time'] != previous)):
            raise ValueError('future/gapped/misaligned source candle rejected')
        numbers = {key: Decimal(str(body[key])) for key in ('open', 'high', 'low', 'close', 'volume', 'turnover')}
        if (any(not value.is_finite() or value < 0 for value in numbers.values())
                or min(numbers[k] for k in ('open', 'high', 'low', 'close')) <= 0
                or not numbers['low'] <= min(numbers['open'], numbers['close']) <= max(numbers['open'], numbers['close']) <= numbers['high']):
            raise ValueError('invalid original candle numbers rejected')
        records.append(dict(row_id=body['id'], table_oid=row['table_oid'], row_version=row['row_version'],
                            pair=body['pair'], timeframe=body['timeframe'],
                            open_time=times['open_time'].isoformat(), close_time=times['close_time'].isoformat(),
                            raw_row_sha256=digest(row['raw_json'].encode()), revision_sha256=digest(canonical(row)),
                            known_at=after.isoformat(), known_at_basis='this_original_query_completion',
                            source_timestamp_claims={key: times[key].isoformat() for key in TIME_FIELDS[2:]},
                            historical_known_at_verified=False))
        ids.add(body['id']); previous = times['close_time']
    age = (after-stamp(records[-1]['close_time'])).total_seconds()
    return dict(identity=identity, identity_sha256=digest(canonical(identity)),
                schema_sha256=identity['relation_sha256'], prepared_at=before.isoformat(),
                completed_at=after.isoformat(), query=query, raw_response_sha256=digest(raw.encode()),
                records=records, latest_candle_age_seconds=age,
                candle_freshness_pass=age <= INTERVALS[query['timeframe']]*2,
                observation_integrity_pass=True, **FLAGS)


def compare_observations(previous, current):
    """Compare two original reads; never infer completeness of unseen polls."""
    left, right = validate_observation(previous), validate_observation(current)
    if left['identity'] != right['identity'] or left['query'] != right['query'] or stamp(left['completed_at']) > stamp(right['prepared_at']):
        raise ValueError('source/schema/query identity or original ordering differs')
    old = {(row['pair'], row['timeframe'], row['open_time']): row for row in left['records']}
    old_ids = {row['row_id']: (row['pair'], row['timeframe'], row['open_time']) for row in left['records']}
    result = []
    for row in right['records']:
        key = (row['pair'], row['timeframe'], row['open_time'])
        if row['row_id'] in old_ids and old_ids[row['row_id']] != key:
            raise ValueError('original UUID moved to a different source candle')
        prior = old.get(key)
        if prior and prior['row_id'] != row['row_id']:
            raise ValueError('same candle replaced under a different original row ID')
        result.append(dict(row_id=row['row_id'], status='new' if prior is None else
                           ('unchanged' if prior['revision_sha256'] == row['revision_sha256'] else 'revised'),
                           previous_revision_sha256=prior['revision_sha256'] if prior else None,
                           revision_sha256=row['revision_sha256'], known_at=row['known_at']))
    return dict(rows=result, scope='two_delivered_reads_only', **FLAGS)


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_new(path, value):
    raw = canonical(value)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError('bounded source artifact required')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError('source artifact write did not advance')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync(path.parent)
    return digest(raw)


def _new_root(root, forbidden=()):
    root = Path(root).absolute()
    project = Path(__file__).resolve().parents[2]
    forbidden = (*forbidden, project / '.local/database', project / '.local/database-transfer')
    if root.resolve() != root or any(root == Path(p).absolute() or Path(p).absolute() in root.parents for p in forbidden):
        raise ValueError('new separate canonical source namespace required')
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    _sync(root.parent)
    return root


def freeze_contract(root, *, backend_env, migration, identity, study_sha256, pairs,
                    start, end, expected_migration_sha256, expected_identity_sha256, clock=None):
    sha(study_sha256); sha(expected_migration_sha256); sha(expected_identity_sha256)
    _migration(migration); _identity(identity)
    if digest(canonical(migration)) != expected_migration_sha256 or digest(canonical(identity)) != expected_identity_sha256:
        raise ValueError('original migration/instance pins differ')
    now = stamp((clock or (lambda: datetime.now(UTC)))())
    start, end = stamp(start), stamp(end)
    if not now < start < end or type(pairs) is not list or not 1 <= len(pairs) <= 20 or pairs != sorted(set(pairs)):
        raise ValueError('new bounded prospective source contract required')
    for pair in pairs:
        query_sql(pair, '5m', 120, now)
    backend = resolve_backend(backend_env)
    if backend.name != 'local':
        raise ValueError('explicit local backend required; no fallback')
    value = dict(schema_version=SCHEMA, root=str(Path(root).absolute()), registered_at=now.isoformat(),
                 start=start.isoformat(), end=end.isoformat(), study_sha256=study_sha256,
                 backend=dict(name='local', api_origin=backend.url, transport='local_docker_postgres_read_only'),
                 identity=identity, identity_sha256=expected_identity_sha256, migration=migration,
                 migration_sha256=expected_migration_sha256, pairs=pairs,
                 supported_table='public.market_candles', supported_timeframes=list(INTERVALS),
                 maximum_rows=120, maximum_query_bytes=MAX_BYTES, maximum_query_seconds=MAX_SECONDS,
                 maximum_candle_lag_intervals=2,
                 runtime=runtime_hashes(), scope='source_rows_only_requires_polling_forecasts_runner_qualification', **FLAGS)
    if len(canonical(value)) > 65536 or not now <= stamp((clock or (lambda: datetime.now(UTC)))()) < start:
        raise ValueError('source registration missed original start')
    root = _new_root(root)
    pin = _write_new(root / 'source-contract.json', value)
    completed = stamp((clock or (lambda: datetime.now(UTC)))())
    if not now <= completed < start:
        raise ValueError('durable source contract missed original start; cannot adopt')
    ready = _write_new(root / 'registered.json', dict(contract_sha256=pin, registered_at=completed.isoformat()))
    if not completed <= stamp((clock or (lambda: datetime.now(UTC)))()) < start:
        (root / 'registered.json').unlink(); _sync(root)
        raise ValueError('source ready marker missed original start; cannot adopt')
    return dict(root=str(root), contract_sha256=pin, registration_sha256=ready, **FLAGS)


def load_contract(root, *, expected_contract_sha256, expected_registration_sha256):
    root = Path(root).absolute()
    if root.resolve() != root or {p.name for p in root.iterdir()} != {'source-contract.json', 'registered.json'}:
        raise ValueError('original separate source contract namespace required')
    raw, ready_raw = read_file(root / 'source-contract.json', maximum=65536), read_file(root / 'registered.json', maximum=65536)
    if digest(raw) != sha(expected_contract_sha256) or digest(ready_raw) != sha(expected_registration_sha256):
        raise ValueError('original source contract/registration pin differs')
    value, ready = parse(raw), parse(ready_raw)
    _keys(value, ('schema_version', 'root', 'registered_at', 'start', 'end', 'study_sha256', 'backend',
                  'identity', 'identity_sha256', 'migration', 'migration_sha256', 'pairs', 'supported_table',
                  'supported_timeframes', 'maximum_rows', 'maximum_query_bytes', 'maximum_query_seconds',
                  'maximum_candle_lag_intervals', 'runtime', 'scope', *FLAGS))
    _keys(ready, ('contract_sha256', 'registered_at'))
    _identity(value['identity']); _migration(value['migration']); _backend(value['backend']); sha(value['study_sha256'])
    if (value['supported_table'] != 'public.market_candles' or value['supported_timeframes'] != list(INTERVALS)
            or type(value['pairs']) is not list or not 1 <= len(value['pairs']) <= 20
            or value['pairs'] != sorted(set(value['pairs'])) or type(value['maximum_rows']) is not int
            or value['maximum_rows'] != 120 or type(value['maximum_query_bytes']) is not int
            or value['maximum_query_bytes'] != MAX_BYTES or type(value['maximum_query_seconds']) is not int
            or value['maximum_query_seconds'] != MAX_SECONDS
            or type(value['maximum_candle_lag_intervals']) is not int or value['maximum_candle_lag_intervals'] != 2
            or value['scope'] != 'source_rows_only_requires_polling_forecasts_runner_qualification'):
        raise ValueError('original fixed source policy differs')
    for pair in value['pairs']:
        query_sql(pair, '5m', 120, stamp(value['registered_at']))
    if (value['schema_version'] != SCHEMA or value['root'] != str(root) or value['runtime'] != runtime_hashes()
            or ready['contract_sha256'] != expected_contract_sha256
            or not stamp(value['registered_at']) <= stamp(ready['registered_at']) < stamp(value['start']) < stamp(value['end'])
            or digest(canonical(value['identity'])) != value['identity_sha256']
            or digest(canonical(value['migration'])) != value['migration_sha256']
            or any(value.get(k) is not False for k in FLAGS)):
        raise ValueError('original source contract lineage/runtime differs')
    return value


def bound_contract(reference):
    if reference is None:
        return None
    _keys(reference, ('root', 'contract_sha256', 'registration_sha256'))
    return load_contract(reference['root'], expected_contract_sha256=reference['contract_sha256'],
                         expected_registration_sha256=reference['registration_sha256'])


def publish_observation(root, *, observation, migration, backend_env, contract=None):
    contract = bound_contract(contract)
    _migration(migration)
    facts = validate_observation(observation)
    backend = resolve_backend(backend_env)
    if backend.name != 'local':
        raise ValueError('explicit local source required')
    if contract is not None:
        if (facts['candle_freshness_pass'] is not True or facts['identity'] != contract['identity'] or digest(canonical(migration)) != contract['migration_sha256']
                or backend.url != contract['backend']['api_origin'] or facts['query']['pair'] not in contract['pairs']
                or not stamp(contract['start']) <= stamp(facts['prepared_at']) <= stamp(facts['completed_at']) <= stamp(contract['end'])
                or contract['runtime'] != runtime_hashes()):
            raise ValueError('observation source/migration/window/contract differs')
    value = dict(schema_version=SCHEMA, scope='registered_source_observation' if contract else 'diagnostic_source_probe_only',
                 backend=dict(name='local', api_origin=backend.url, transport='local_docker_postgres_read_only'),
                 observation=observation, migration=migration, migration_sha256=digest(canonical(migration)),
                 contract_sha256=digest(canonical(contract)) if contract else None,
                 runtime=runtime_hashes(), derived=facts, **FLAGS)
    root = _new_root(root, (Path(contract['root']),) if contract else ())
    pin = _write_new(root / 'observation.json', value)
    ready = _write_new(root / 'complete.json', dict(observation_sha256=pin))
    return dict(root=str(root), observation_sha256=pin, completion_sha256=ready, **FLAGS)


def audit_observation(root, *, expected_observation_sha256, expected_completion_sha256, contract=None):
    """Pure offline replay of raw original catalog/row bytes and availability."""
    root = Path(root).absolute()
    if root.resolve() != root or {p.name for p in root.iterdir()} != {'observation.json', 'complete.json'}:
        raise ValueError('original sealed observation namespace required')
    raw, ready_raw = read_file(root / 'observation.json'), read_file(root / 'complete.json', maximum=65536)
    if digest(raw) != sha(expected_observation_sha256) or digest(ready_raw) != sha(expected_completion_sha256):
        raise ValueError('original observation/completion SHA differs')
    value, ready = parse(raw), parse(ready_raw)
    contract = bound_contract(contract)
    _keys(value, ('schema_version', 'scope', 'backend', 'observation', 'migration', 'migration_sha256',
                  'contract_sha256', 'runtime', 'derived', *FLAGS))
    _backend(value['backend']); _migration(value['migration'])
    if (value['schema_version'] != SCHEMA or ready != dict(observation_sha256=expected_observation_sha256)
            or value['runtime'] != runtime_hashes() or any(value.get(k) is not False for k in FLAGS)
            or digest(canonical(value['migration'])) != value['migration_sha256']):
        raise ValueError('original observation lineage/runtime differs')
    facts = validate_observation(value['observation'])
    if value['derived'] != facts:
        raise ValueError('stored original row IDs/known_at/schema facts differ from source')
    if value['contract_sha256'] is not None:
        if (value['scope'] != 'registered_source_observation' or contract is None or value['contract_sha256'] != digest(canonical(contract))
                or facts['candle_freshness_pass'] is not True or facts['identity'] != contract['identity'] or value['migration_sha256'] != contract['migration_sha256']
                or value['backend'] != contract['backend'] or facts['query']['pair'] not in contract['pairs']
                or not stamp(contract['start']) <= stamp(facts['prepared_at']) <= stamp(facts['completed_at']) <= stamp(contract['end'])):
            raise ValueError('offline original source contract binding differs')
    elif contract is not None or value['scope'] != 'diagnostic_source_probe_only':
        raise ValueError('diagnostic observation cannot be adopted into a future study')
    return dict(observation_sha256=expected_observation_sha256, rows_checked=len(facts['records']),
                identity_sha256=facts['identity_sha256'], schema_sha256=facts['schema_sha256'],
                migration_sha256=value['migration_sha256'], scope=value['scope'],
                candle_freshness_pass=facts['candle_freshness_pass'],
                latest_candle_age_seconds=facts['latest_candle_age_seconds'],
                original_source_snapshot_integrity_pass=True, **FLAGS)
