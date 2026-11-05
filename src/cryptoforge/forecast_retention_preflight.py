"""Read-only candidate inventory for a possible forecast ledger split.

This does not authorize a split: consumers, writer coordination, backup and
cutover/rollback still require independent verification.
"""
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from time import monotonic

from cryptoforge.forecast_memory_snapshot import _canonical, _count, _file_sha, _schema


def _time(value):
    if not isinstance(value, str):
        raise ValueError('timestamp string required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return parsed.astimezone(UTC)


def _strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=pairs)


def _original(path):
    path = Path(path).absolute()
    if path.resolve() != path or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('canonical original file required')
    return path


def _no_sidecars(path):
    if any(Path(str(path) + suffix).exists() or Path(str(path) + suffix).is_symlink()
           for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('snapshot must not have SQLite sidecars')


def assess_retention(manifest_path, manifest_sha256, *, as_of, cutoff,
                     maximum_rows=200000, maximum_bytes=1024**3, maximum_seconds=120):
    """Classify every forecast and all its versions without changing any store."""
    if (type(maximum_rows) is not int or maximum_rows < 1 or
            type(maximum_bytes) is not int or maximum_bytes < 1 or
            type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 600):
        raise ValueError('bounded preflight limits required')
    if not re.fullmatch(r'[0-9a-f]{64}', manifest_sha256 or ''):
        raise ValueError('externally pinned manifest SHA-256 required')
    as_of = _time(as_of); cutoff = _time(cutoff)
    if cutoff > as_of - timedelta(hours=36):
        raise ValueError('cutoff must preserve at least the last 36 hours')
    deadline = monotonic() + maximum_seconds
    manifest_path = _original(manifest_path)
    if manifest_path.name != 'manifest.json' or manifest_path.stat().st_size > 65536:
        raise ValueError('snapshot manifest required')
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError('manifest hash mismatch')
    manifest = _strict_json(raw)
    if raw != _canonical(manifest) + b'\n':
        raise ValueError('canonical manifest required')
    if (manifest.get('schema_version') != 'primary-price-forecast-snapshot-v1' or
            manifest.get('integrity_check') != 'ok' or
            manifest.get('source_modified') is not False or
            manifest.get('writers_redirected') is not False or
            manifest.get('snapshot_counts_match_source_transaction') is not True or
            _time(manifest['completed_at']) > as_of):
        raise ValueError('snapshot manifest is not suitable for this observation time')
    snapshot = _original(manifest_path.parent / 'forecast-snapshot.sqlite')
    if manifest.get('snapshot') != str(snapshot) or snapshot.stat().st_size != manifest.get('snapshot_bytes'):
        raise ValueError('snapshot identity or size mismatch')
    if snapshot.stat().st_size > maximum_bytes:
        raise ValueError('snapshot byte limit exceeded')
    _no_sidecars(snapshot)
    snapshot_hash = _file_sha(snapshot)
    if snapshot_hash != manifest.get('snapshot_sha256'):
        raise ValueError('snapshot hash mismatch')
    db = sqlite3.connect(snapshot.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=1)
    buckets = {name: {'forecasts': 0, 'outcome_versions': 0, 'logical_bytes': 0,
                      'forecast_ids_sha256': hashlib.sha256()}
               for name in ('archive_candidates', 'protected')}
    reasons = {}
    forecasts = outcomes = 0
    try:
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF')
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
        db.set_progress_handler(lambda: int(monotonic() > deadline), 10000)
        schema, tables = _schema(db)
        counts = _count(db, tables)
        if (hashlib.sha256(_canonical(schema)).hexdigest() != manifest['schema_sha256'] or
                counts != manifest['source_transaction_counts'] or
                counts['forecasts'] != manifest['forecast_rows']['rows'] or
                counts['outcomes'] != manifest['outcome_rows']['rows'] or
                sum(counts.values()) > maximum_rows):
            raise ValueError('snapshot schema, counts or row limit mismatch')
        has_outcomes = 'primary_forecast_outcomes' in tables
        orphans = (db.execute('SELECT count(*) FROM primary_forecast_outcomes o LEFT JOIN primary_forecasts f ON f.id=o.forecast WHERE f.id IS NULL').fetchone()[0]
                   if has_outcomes else 0)
        if orphans != manifest['orphan_outcomes']:
            raise ValueError('orphan count mismatch')
        query = ('SELECT f.id,f.payload,o.id,o.forecast,o.digest,o.observed_at,o.payload '
                 'FROM primary_forecasts f LEFT JOIN primary_forecast_outcomes o ON o.forecast=f.id ORDER BY f.id,o.id') if has_outcomes else (
                 'SELECT f.id,f.payload,NULL,NULL,NULL,NULL,NULL FROM primary_forecasts f ORDER BY f.id')
        current = None
        def flush(group):
            if group is None:
                return
            reason = group['reason']
            if not group['versions']:
                reason = reason or 'unresolved'
            if orphans:
                reason = reason or 'orphan_outcomes_block_split'
            bucket = buckets['protected' if reason else 'archive_candidates']
            bucket['forecasts'] += 1
            bucket['outcome_versions'] += group['versions']
            bucket['logical_bytes'] += group['bytes']
            encoded = _canonical(group['id'])
            bucket['forecast_ids_sha256'].update(len(encoded).to_bytes(8, 'big') + encoded)
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        for fid, payload, oid, ofid, digest, observed, opayload in db.execute(query):
            if monotonic() > deadline:
                raise TimeoutError('retention preflight deadline')
            if current is None or fid != current['id']:
                flush(current)
                forecasts += 1
                if not isinstance(fid, str) or not isinstance(payload, str):
                    raise ValueError('unsupported forecast row type')
                current = {'id': fid, 'versions': 0, 'bytes': len(_canonical([fid, payload])), 'reason': None, 'target': None}
                try:
                    parsed = _strict_json(payload)
                    predicted = _time(parsed['predicted_at']); target = _time(parsed['target_information_end'])
                    current['target'] = target
                    if predicted > target or target > as_of:
                        current['reason'] = 'invalid_or_future_forecast_time'
                    elif predicted >= cutoff or target >= cutoff:
                        current['reason'] = 'recent_forecast'
                except (ValueError, TypeError, KeyError, OverflowError):
                    current['reason'] = 'invalid_or_future_forecast_time'
            if oid is not None:
                outcomes += 1; current['versions'] += 1
                current['bytes'] += len(_canonical([oid, ofid, digest, observed, opayload]))
                try:
                    when = _time(observed)
                    if when > as_of or (current['target'] is not None and when < current['target']):
                        current['reason'] = current['reason'] or 'invalid_or_future_outcome_time'
                    elif when >= cutoff:
                        current['reason'] = current['reason'] or 'recent_outcome_version'
                except (ValueError, TypeError, OverflowError):
                    current['reason'] = current['reason'] or 'invalid_or_future_outcome_time'
        flush(current)
        if forecasts != counts['forecasts'] or outcomes + orphans != counts['outcomes']:
            raise ValueError('classified row counts do not reconcile')
    finally:
        db.close()
    _no_sidecars(snapshot)
    if monotonic() > deadline:
        raise TimeoutError('retention preflight deadline')
    if _file_sha(snapshot) != snapshot_hash or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_sha256:
        raise ValueError('snapshot or manifest changed during preflight')
    if monotonic() > deadline:
        raise TimeoutError('retention preflight deadline')
    for bucket in buckets.values():
        bucket['forecast_ids_sha256'] = bucket['forecast_ids_sha256'].hexdigest()
    return {'schema_version': 'forecast-retention-preflight-v1', 'as_of': as_of.isoformat(),
            'cutoff': cutoff.isoformat(), 'manifest_sha256': manifest_sha256, 'snapshot_sha256': snapshot_hash,
            'source_counts': counts, 'orphan_outcomes': orphans, 'buckets': buckets,
            'protected_reasons_first_match': reasons, 'split_readiness': False,
            'logical_bytes_definition': 'UTF-8 compact JSON row encodings; not SQLite file sizes',
            'scope': 'hypothetical inventory only; no retention or migration authorized',
            'source_modified': False, 'data_deleted': False, 'writers_redirected': False,
            'live_promotion_allowed': False}
