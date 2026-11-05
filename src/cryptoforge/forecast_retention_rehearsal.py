"""Isolated split rehearsal of an immutable diagnostic snapshot.

No live writer, reader, service, or existing database is changed. Partial output
is retained after errors and is never eligible for activation.
"""
from datetime import UTC, datetime
import hashlib
import heapq
import json
import os
from pathlib import Path
import shutil
import sqlite3
from time import monotonic

from cryptoforge.forecast_memory_snapshot import _canonical, _file_sha, _schema
from cryptoforge.forecast_retention_preflight import _no_sidecars, _original, _strict_json, _time, assess_retention

FORECAST_DDL = 'CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID'
OUTCOME_DDL = 'CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)'
INDEX_DDL = 'CREATE INDEX primary_forecast_outcome_lookup ON primary_forecast_outcomes(forecast,id)'


def _typed_digest(rows, deadline):
    digest = hashlib.sha256(); count = 0
    for row in rows:
        if monotonic() > deadline:
            raise TimeoutError('rehearsal verification deadline')
        for value in row:
            if value is None:data = b'n'
            elif type(value) is int:data = b'i' + str(value).encode()
            elif type(value) is str:data = b's' + value.encode('utf-8')
            elif type(value) is bytes:data = b'b' + value
            else:raise ValueError('unsupported diagnostic row type')
            digest.update(len(data).to_bytes(8, 'big'));digest.update(data)
        count += 1
    return {'rows': count, 'sha256': digest.hexdigest()}


def _id_hash(ids):
    h = hashlib.sha256()
    for fid in sorted(ids):
        encoded = _canonical(fid);h.update(len(encoded).to_bytes(8, 'big') + encoded)
    return h.hexdigest()


def _candidate_ids(db, cutoff, as_of, deadline):
    """Independently recompute groups, then compare their commitment to preflight."""
    query = ('SELECT f.id,f.payload,o.id,o.observed_at FROM primary_forecasts f '
             'LEFT JOIN primary_forecast_outcomes o ON o.forecast=f.id ORDER BY f.id,o.id')
    candidates = set(); protected = set(); current = None
    def finish(item):
        if item is not None:
            (candidates if item['valid'] and item['versions'] else protected).add(item['id'])
    for fid, payload, oid, observed in db.execute(query):
        if monotonic() > deadline:raise TimeoutError('rehearsal classification deadline')
        if current is None or fid != current['id']:
            finish(current); current = {'id': fid, 'valid': True, 'versions': 0, 'target': None}
            if not isinstance(fid, str) or not isinstance(payload, str):raise ValueError('unsupported forecast row')
            try:
                parsed = _strict_json(payload)
                predicted = _time(parsed['predicted_at']);target = _time(parsed['target_information_end'])
                current['target'] = target
                if predicted > target or target > as_of or predicted >= cutoff or target >= cutoff:
                    current['valid'] = False
            except (ValueError, TypeError, KeyError, OverflowError):current['valid'] = False
        if oid is not None:
            current['versions'] += 1
            try:
                when = _time(observed)
                if when > as_of or when >= cutoff or (current['target'] is not None and when < current['target']):
                    current['valid'] = False
            except (ValueError, TypeError, OverflowError):current['valid'] = False
    finish(current)
    return candidates, protected


def _connected(path):
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=1)
    db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
    return db


def rehearse_split(manifest_path, manifest_sha256, preflight_path, preflight_sha256, output, *,
                   minimum_free_bytes=2 * 1024**3, maximum_source_bytes=1024**3,
                   maximum_rows=200000, maximum_seconds=180):
    """Copy every typed row into new private SQLite files and verify their union."""
    if (type(minimum_free_bytes) is not int or minimum_free_bytes < 0 or
            type(maximum_source_bytes) is not int or maximum_source_bytes < 1 or
            type(maximum_rows) is not int or maximum_rows < 1 or
            type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 600):
        raise ValueError('bounded rehearsal limits required')
    start = datetime.now(UTC);deadline = monotonic() + maximum_seconds
    manifest_path = _original(manifest_path); preflight_path = _original(preflight_path)
    if preflight_path.stat().st_size > 65536 or _file_sha(preflight_path) != preflight_sha256:
        raise ValueError('pinned preflight receipt required')
    preflight = _strict_json(preflight_path.read_bytes())
    verified = assess_retention(manifest_path, manifest_sha256, as_of=preflight['as_of'],
                                cutoff=preflight['cutoff'], maximum_rows=maximum_rows,
                                maximum_bytes=maximum_source_bytes, maximum_seconds=maximum_seconds)
    if verified != preflight:raise ValueError('preflight receipt does not match snapshot')
    if preflight['orphan_outcomes']:raise ValueError('orphan outcomes block rehearsal')
    manifest = _strict_json(manifest_path.read_bytes())
    snapshot = _original(manifest_path.parent / 'forecast-snapshot.sqlite')
    output = Path(output).absolute()
    source_parent = Path(manifest['source']).parent
    if (output.resolve() != output or output.exists() or not output.parent.is_dir() or
            output.parent in (manifest_path.parent, source_parent, preflight_path.parent) or
            snapshot.parent in output.parents or source_parent in output.parents):
        raise ValueError('new separate rehearsal directory required')
    size = snapshot.stat().st_size
    if shutil.disk_usage(output.parent).free < minimum_free_bytes + 2 * size + 64 * 1024**2:
        raise ValueError('insufficient rehearsal disk reserve')
    if monotonic() > deadline:raise TimeoutError('rehearsal preparation deadline')
    _no_sidecars(snapshot)
    source = _connected(snapshot); out = []
    try:
        schema, tables = _schema(source)
        if tables != {'primary_forecasts','primary_forecast_outcomes'} or {r[2] for r in schema} != {FORECAST_DDL,OUTCOME_DDL,INDEX_DDL}:
            raise ValueError('exact known forecast schema required')
        candidates, protected = _candidate_ids(source, _time(preflight['cutoff']), _time(preflight['as_of']), deadline)
        for name, ids in [('archive_candidates', candidates), ('protected', protected)]:
            bucket = preflight['buckets'][name]
            if len(ids) != bucket['forecasts'] or _id_hash(ids) != bucket['forecast_ids_sha256']:
                raise ValueError('independent forecast classification mismatch')
        output.mkdir(mode=0o700)
        for name in ('archive.sqlite','active.sqlite'):
            path = output/name
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600);os.close(fd)
            db = sqlite3.connect(path);out.append(db)
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-8192')
            db.execute('PRAGMA temp_store=MEMORY')
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            db.execute(f'PRAGMA max_page_count={max(1, maximum_source_bytes // page_size)}')
            db.execute(FORECAST_DDL);db.execute(OUTCOME_DDL);db.execute(INDEX_DDL)
        counts = [{'forecasts':0,'outcomes':0},{'forecasts':0,'outcomes':0}]
        for index, table, query in ((0,'forecasts','SELECT id,payload FROM primary_forecasts ORDER BY id'),
                                    (1,'outcomes','SELECT id,forecast,digest,observed_at,payload FROM primary_forecast_outcomes ORDER BY id')):
            for n,row in enumerate(source.execute(query), 1):
                if n % 1000 == 0:
                    if monotonic() > deadline:raise TimeoutError('rehearsal copy deadline')
                    if shutil.disk_usage(output).free < minimum_free_bytes:raise ValueError('rehearsal disk reserve exhausted')
                fid = row[0] if index == 0 else row[1]
                if fid in candidates:which = 0
                elif fid in protected:which = 1
                else:raise ValueError('outcome without classified forecast')
                out[which].execute('INSERT INTO primary_forecasts VALUES (?,?)' if index == 0 else 'INSERT INTO primary_forecast_outcomes VALUES (?,?,?,?,?)',row)
                counts[which][table] += 1
        for db in out:db.commit()
        for which,name in enumerate(('archive_candidates','protected')):
            if (counts[which]['forecasts'] != preflight['buckets'][name]['forecasts'] or
                    counts[which]['outcomes'] != preflight['buckets'][name]['outcome_versions']):
                raise ValueError('split counts do not match preflight')
        for db in out:
            db.set_progress_handler(lambda: int(monotonic() > deadline),10000)
            if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok']:
                raise ValueError('split database integrity failure')
        comparisons = {}
        for label,query in [('forecast_rows','SELECT id,payload FROM primary_forecasts ORDER BY id'),
                            ('outcome_rows','SELECT id,forecast,digest,observed_at,payload FROM primary_forecast_outcomes ORDER BY id')]:
            union = heapq.merge(out[0].execute(query),out[1].execute(query),key=lambda row:row[0])
            comparisons[label] = _typed_digest(union,deadline)
            if comparisons[label] != manifest[label]:raise ValueError('split row digest mismatch')
    finally:
        source.close()
        for db in out:db.close()
    _no_sidecars(snapshot)
    if (_file_sha(snapshot) != manifest['snapshot_sha256'] or _file_sha(manifest_path) != manifest_sha256 or
            _file_sha(preflight_path) != preflight_sha256):raise ValueError('input changed during rehearsal')
    if monotonic() > deadline:raise TimeoutError('rehearsal deadline')
    files = {name:{'bytes':(output/name).stat().st_size,'sha256':_file_sha(output/name)} for name in ('archive.sqlite','active.sqlite')}
    if monotonic() > deadline:raise TimeoutError('rehearsal finalization deadline')
    result = {'schema_version':'forecast-retention-rehearsal-v1','started_at':start.isoformat(),
              'completed_at':datetime.now(UTC).isoformat(),'snapshot_sha256':manifest['snapshot_sha256'],
              'manifest_sha256':manifest_sha256,'preflight_sha256':preflight_sha256,
              'files':files,'counts':{'archive':counts[0],'active':counts[1]},'union_rows':comparisons,
              'integrity_check':'ok','source_modified':False,'writers_redirected':False,
              'actual_recording_restored':False,'live_promotion_allowed':False,
              'scope':'isolated snapshot rehearsal only; no activation authorized'}
    fd = os.open(output/'receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(_canonical(result)+b'\n');stream.flush();os.fsync(stream.fileno())
    return result
