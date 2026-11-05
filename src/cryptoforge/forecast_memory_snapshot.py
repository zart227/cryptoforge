"""Create a bounded, verified, isolated snapshot of price-forecast diagnostics.

This is a backup and inventory, not a rotation, writer cutover or cash label.
The original database is opened read-only; unknown rows and versions are retained.
"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from time import monotonic


FORECASTS = ('id', 'payload')
OUTCOMES = ('id', 'forecast', 'digest', 'observed_at', 'payload')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def _file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _schema(db):
    rows = list(db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))
    tables = {name for kind, name, _ in rows if kind == 'table'}
    allowed = {('table', 'primary_forecasts'), ('table', 'primary_forecast_outcomes'),
               ('index', 'primary_forecast_outcome_lookup')}
    if not {'primary_forecasts'} <= tables <= {'primary_forecasts', 'primary_forecast_outcomes'}:
        raise ValueError('expected isolated forecast tables required')
    if any((kind, name) not in allowed or not sql for kind, name, sql in rows):
        raise ValueError('unexpected forecast schema object')
    if tuple(row[1] for row in db.execute('PRAGMA table_info(primary_forecasts)')) != FORECASTS:
        raise ValueError('unexpected forecast columns')
    if 'primary_forecast_outcomes' in tables and tuple(row[1] for row in db.execute('PRAGMA table_info(primary_forecast_outcomes)')) != OUTCOMES:
        raise ValueError('unexpected outcome columns')
    return rows, tables


def _count(db, tables):
    return {'forecasts': db.execute('SELECT count(*) FROM primary_forecasts').fetchone()[0],
            'outcomes': db.execute('SELECT count(*) FROM primary_forecast_outcomes').fetchone()[0]
            if 'primary_forecast_outcomes' in tables else 0}


def _logical_hash(db, query, deadline):
    """Hash ordered typed SQLite values with length prefixes, including raw JSON."""
    h = hashlib.sha256(); count = 0
    for row in db.execute(query):
        if monotonic() > deadline:
            raise TimeoutError('forecast snapshot audit deadline')
        for value in row:
            if value is None:
                data = b'n'
            elif type(value) is int:
                data = b'i' + str(value).encode()
            elif type(value) is str:
                data = b's' + value.encode('utf-8')
            elif type(value) is bytes:
                data = b'b' + value
            else:
                raise ValueError('unsupported diagnostic row type')
            h.update(len(data).to_bytes(8, 'big')); h.update(data)
        count += 1
    return {'rows': count, 'sha256': h.hexdigest()}


def create_forecast_snapshot(source, output, *, minimum_free_bytes=2 * 1024**3,
                             maximum_source_bytes=1024**3, maximum_seconds=120):
    """Copy one SQLite read transaction into a new private directory.

    A partial directory is deliberately retained on any failure. No operation
    truncates the source, modifies writer settings, or resumes a failed copy.
    """
    if (type(minimum_free_bytes) is not int or minimum_free_bytes < 0
            or type(maximum_source_bytes) is not int or maximum_source_bytes < 1
            or type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 600):
        raise ValueError('bounded snapshot limits required')
    source = Path(source).absolute(); output = Path(output).absolute()
    if (source.resolve() != source or not source.is_file() or source.stat().st_nlink != 1
            or output.resolve() != output or output.exists() or not output.parent.is_dir()):
        raise ValueError('original source and new output directory required')
    size = source.stat().st_size
    if size < 1 or size > maximum_source_bytes:
        raise ValueError('forecast source byte limit exceeded')
    # Account for a new snapshot and a separate potential rollback/restore copy.
    if shutil.disk_usage(output.parent).free < minimum_free_bytes + 2 * size + 64 * 1024**2:
        raise ValueError('forecast snapshot disk reserve insufficient')
    start = datetime.now(UTC); deadline = monotonic() + maximum_seconds
    output.mkdir(mode=0o700); target = output / 'forecast-snapshot.sqlite'
    db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=1)
    try:
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF')
        db.execute('BEGIN')
        schema, tables = _schema(db); source_counts = _count(db, tables)
        baseline = {'page_size': db.execute('PRAGMA page_size').fetchone()[0],
                    'page_count': db.execute('PRAGMA page_count').fetchone()[0],
                    'journal_mode': db.execute('PRAGMA journal_mode').fetchone()[0]}
        if baseline['page_size'] * baseline['page_count'] > maximum_source_bytes:
            raise ValueError('forecast logical database byte limit exceeded')
        logical_bytes = baseline['page_size'] * baseline['page_count']
        if shutil.disk_usage(output).free < minimum_free_bytes + 2 * logical_bytes + 64 * 1024**2:
            raise ValueError('forecast snapshot logical database disk reserve insufficient')
        dest = sqlite3.connect(target)
        try:
            os.chmod(target, 0o600)
            def progress(status, remaining, total):
                if monotonic() > deadline:
                    raise TimeoutError('forecast snapshot copy deadline')
            db.backup(dest, pages=256, progress=progress, sleep=.05)
        finally:
            dest.close()
        db.rollback()
    finally:
        db.close()
    if target.stat().st_size > maximum_source_bytes:
        raise ValueError('snapshot byte limit exceeded')
    snapshot = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=1)
    try:
        snapshot.execute('PRAGMA query_only=ON'); snapshot.execute('PRAGMA trusted_schema=OFF')
        snapshot.set_progress_handler(lambda: int(monotonic() > deadline), 10000)
        copied_schema, copied_tables = _schema(snapshot)
        if copied_schema != schema or _count(snapshot, copied_tables) != source_counts:
            raise ValueError('snapshot schema or row counts differ from source transaction')
        integrity = [row[0] for row in snapshot.execute('PRAGMA integrity_check')]
        if integrity != ['ok']:
            raise ValueError('forecast snapshot integrity check failed')
        forecasts = _logical_hash(snapshot, 'SELECT id,payload FROM primary_forecasts ORDER BY id', deadline)
        outcomes = (_logical_hash(snapshot, 'SELECT id,forecast,digest,observed_at,payload FROM primary_forecast_outcomes ORDER BY id', deadline)
                    if 'primary_forecast_outcomes' in copied_tables else {'rows': 0, 'sha256': hashlib.sha256().hexdigest()})
        orphan_count = (snapshot.execute('SELECT count(*) FROM primary_forecast_outcomes o LEFT JOIN primary_forecasts f ON f.id=o.forecast WHERE f.id IS NULL').fetchone()[0]
                        if 'primary_forecast_outcomes' in copied_tables else 0)
    finally:
        snapshot.close()
    if monotonic() > deadline:
        raise TimeoutError('forecast snapshot audit deadline')
    result = {'schema_version': 'primary-price-forecast-snapshot-v1', 'source': str(source),
              'started_at': start.isoformat(), 'completed_at': datetime.now(UTC).isoformat(),
              'snapshot': str(target), 'snapshot_bytes': target.stat().st_size, 'snapshot_sha256': _file_sha(target),
              'source_observed_file_bytes': size, 'source_transaction': baseline,
              'source_transaction_counts': source_counts, 'snapshot_counts_match_source_transaction': True,
              'schema_sha256': hashlib.sha256(_canonical(schema)).hexdigest(), 'integrity_check': 'ok',
              'forecast_rows': forecasts, 'outcome_rows': outcomes, 'orphan_outcomes': orphan_count,
              'scope': 'price_diagnostics_snapshot_not_live_migration_or_cash_labels',
              'source_modified': False, 'writers_redirected': False, 'live_promotion_allowed': False}
    manifest = output / 'manifest.json'
    fd = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(_canonical(result) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    return result
