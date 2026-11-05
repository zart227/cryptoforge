"""Bounded, read-only observation of the selected local PostgreSQL source.

Only the repository's local Docker database is supported. No SQL, credentials,
table names or executable arguments are accepted from market data or the CLI.
This observer does not establish the identity of the separate REST endpoint.
"""
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import selectors
import subprocess
from time import monotonic


INTERVALS = {'1m': 60, '5m': 300, '15m': 900, '60m': 3600, 'D': 86400}
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 15

# Explicit catalog qualification avoids search_path-dependent functions/types.
# Definitions are hashed in PostgreSQL, so default/function bodies cannot leak
# credentials into an evidence file. The source table alone is in this scope.
CATALOG_SQL = """
SELECT pg_catalog.json_build_object(
 'schema', n.nspname, 'schema_oid', n.oid::text,
 'table', c.relname, 'table_oid', c.oid::text,
 'kind', c.relkind, 'persistence', c.relpersistence,
 'rls_enabled', c.relrowsecurity, 'rls_forced', c.relforcerowsecurity,
 'columns', (SELECT pg_catalog.json_agg(pg_catalog.json_build_object(
   'position', a.attnum, 'name', a.attname,
   'type', pg_catalog.format_type(a.atttypid, a.atttypmod),
   'not_null', a.attnotnull, 'generated', a.attgenerated,
   'identity', a.attidentity, 'collation_oid', a.attcollation::text,
   'default_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       coalesce(pg_catalog.pg_get_expr(d.adbin, d.adrelid), ''), 'UTF8')), 'hex'))
   ORDER BY a.attnum)
   FROM pg_catalog.pg_attribute a
   LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
   WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
 'constraints', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_object(
   'name', x.conname, 'type', x.contype, 'validated', x.convalidated,
   'definition_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       pg_catalog.pg_get_constraintdef(x.oid), 'UTF8')), 'hex')) ORDER BY x.conname), '[]')
   FROM pg_catalog.pg_constraint x WHERE x.conrelid=c.oid),
 'indexes', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_object(
   'name', i.relname, 'valid', x.indisvalid, 'ready', x.indisready,
   'definition_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       pg_catalog.pg_get_indexdef(x.indexrelid), 'UTF8')), 'hex')) ORDER BY i.relname), '[]')
   FROM pg_catalog.pg_index x JOIN pg_catalog.pg_class i ON i.oid=x.indexrelid
   WHERE x.indrelid=c.oid),
 'triggers', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_object(
   'name', x.tgname, 'enabled', x.tgenabled,
   'definition_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       pg_catalog.pg_get_triggerdef(x.oid), 'UTF8')), 'hex'),
   'function_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       pg_catalog.pg_get_functiondef(x.tgfoid), 'UTF8')), 'hex')) ORDER BY x.tgname), '[]')
   FROM pg_catalog.pg_trigger x WHERE x.tgrelid=c.oid AND NOT x.tgisinternal),
 'policies', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_object(
   'name', p.polname, 'command', p.polcmd, 'permissive', p.polpermissive,
   'roles', p.polroles::text,
   'using_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       coalesce(pg_catalog.pg_get_expr(p.polqual,p.polrelid), ''), 'UTF8')), 'hex'),
   'check_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
       coalesce(pg_catalog.pg_get_expr(p.polwithcheck,p.polrelid), ''), 'UTF8')), 'hex')) ORDER BY p.polname), '[]')
   FROM pg_catalog.pg_policy p WHERE p.polrelid=c.oid))
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname='market_candles'
""".strip()


def query_sql(pair, timeframe, limit, cutoff):
    if (type(pair) is not str or not re.fullmatch(r'[A-Z0-9]{1,24}/USDT', pair)
            or timeframe not in INTERVALS or type(limit) is not int or not 1 <= limit <= 120
            or not isinstance(cutoff, datetime) or cutoff.tzinfo is None):
        raise ValueError('bounded Spot candle query required')
    at = cutoff.astimezone(UTC).isoformat()
    # All interpolated fields are closed choices, integers or validated literals.
    return """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '2000ms';
SET LOCAL lock_timeout = '250ms';
SET LOCAL idle_in_transaction_session_timeout = '5000ms';
SET LOCAL TIME ZONE 'UTC';
SET LOCAL search_path = pg_catalog;
SELECT pg_catalog.json_build_object(
 'schema_version', 'local-postgres-observation-v1',
 'system_identifier', (SELECT system_identifier::text FROM pg_catalog.pg_control_system()),
 'database', pg_catalog.current_database(),
 'database_oid', (SELECT oid::text FROM pg_catalog.pg_database WHERE datname=pg_catalog.current_database()),
 'server_version_num', pg_catalog.current_setting('server_version_num'),
 'transaction_read_only', pg_catalog.current_setting('transaction_read_only'),
 'transaction_isolation', pg_catalog.current_setting('transaction_isolation'),
 'database_clock', pg_catalog.clock_timestamp(),
 'snapshot', pg_catalog.pg_current_snapshot()::text,
 'relation', (""" + CATALOG_SQL + """),
 'rows', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_object(
   'table_oid', t.table_oid, 'row_version', t.row_version, 'raw_json', t.raw_json)
   ORDER BY t.open_time), '[]') FROM (
     SELECT c.tableoid::text AS table_oid, c.xmin::text AS row_version,
       pg_catalog.row_to_json(c)::text AS raw_json, c.open_time
     FROM public.market_candles c
     WHERE c.exchange='bybit' AND c.market_type='spot'
       AND c.pair='""" + pair + """' AND c.timeframe='""" + timeframe + """'
       AND c.close_time <= '""" + at + """'::timestamptz
     ORDER BY c.open_time DESC LIMIT """ + str(limit) + """
   ) t));
ROLLBACK;
"""


def bounded_process(command, sql, *, maximum_bytes=MAX_BYTES, maximum_seconds=MAX_SECONDS):
    """Drain one merged pipe with a hard byte/wall bound; never print stderr."""
    import tempfile
    if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_BYTES:
        raise ValueError('bounded observer output required')
    if type(maximum_seconds) is not int or not 1 <= maximum_seconds <= MAX_SECONDS:
        raise ValueError('bounded observer wall time required')
    deadline = monotonic() + maximum_seconds
    with tempfile.TemporaryFile() as source:
        source.write(sql.encode()); source.seek(0)
        with subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, close_fds=True) as process:
            try:
                output = bytearray()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        left = deadline - monotonic()
                        if left <= 0 or not selector.select(left):
                            raise ValueError('local source observation timed out')
                        chunk = os.read(process.stdout.fileno(), min(65536, maximum_bytes + 1 - len(output)))
                        if not chunk:
                            break
                        output.extend(chunk)
                        if len(output) > maximum_bytes:
                            raise ValueError('local source observation byte budget exhausted')
                if process.wait(timeout=max(0.001, deadline - monotonic())) != 0:
                    raise ValueError('local read-only source command failed')
                return bytes(output)
            except BaseException:
                if process.poll() is None:
                    process.kill()
                process.wait()
                raise


class LocalPostgresObserver:
    def __init__(self, repository, *, maximum_bytes=MAX_BYTES, maximum_seconds=MAX_SECONDS):
        self.repository = Path(repository).absolute()
        if self.repository.resolve() != self.repository:
            raise ValueError('canonical local repository required')
        self.maximum_bytes, self.maximum_seconds = maximum_bytes, maximum_seconds

    def read(self, *, pair, timeframe='5m', limit=120):
        from cryptoforge.local_source_provenance import runtime_hashes, digest
        runtime = runtime_hashes()
        prepared = datetime.now(UTC)
        started = monotonic()
        sql = query_sql(pair, timeframe, limit, prepared)
        command = ['docker', 'compose', '--env-file', str(self.repository / '.local/database/compose.env'),
                   '-f', str(self.repository / 'docker/database.compose.yml'), 'exec', '-T',
                   'db', 'psql', '-X', '-qAt', '-U', 'postgres', '-d', 'cryptoforge',
                   '-v', 'ON_ERROR_STOP=1']
        raw = bounded_process(command, sql, maximum_bytes=self.maximum_bytes,
                              maximum_seconds=self.maximum_seconds)
        completed = datetime.now(UTC)
        elapsed = monotonic() - started
        if completed < prepared or elapsed > self.maximum_seconds or runtime_hashes() != runtime:
            raise ValueError('local source observation clock/wall budget changed')
        return dict(prepared_at=prepared.isoformat(), completed_at=completed.isoformat(),
                    elapsed_seconds=elapsed, query=dict(pair=pair, timeframe=timeframe, limit=limit),
                    query_sha256=digest(sql.encode()), runtime=runtime, raw_response=raw.decode('utf-8'))
