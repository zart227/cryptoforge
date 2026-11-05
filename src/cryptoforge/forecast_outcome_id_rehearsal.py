"""Isolated synthetic-only SQLite outcome ID and crash-recovery experiment.

Not a production writer, migration, real outcome collector, or trading control.
All writers in an experiment must use this implementation against one local file.
"""
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3

from cryptoforge.forecast_memory_snapshot import _canonical, _file_sha, _schema
from cryptoforge.forecast_retention_preflight import _no_sidecars, _original, _strict_json, _time
from cryptoforge.forecast_retention_rehearsal import FORECAST_DDL, OUTCOME_DDL, INDEX_DDL

MAX_ID = 2**63 - 1


def _check_schema(db):
    schema,tables = _schema(db)
    if tables != {'primary_forecasts','primary_forecast_outcomes'} or {x[2] for x in schema} != {FORECAST_DDL,OUTCOME_DDL,INDEX_DDL}:
        raise ValueError('exact rehearsal schema required')


def create_sandbox(receipt_path, receipt_sha256, output, *, minimum_free_bytes=2 * 1024**3,
                   maximum_copy_bytes=1024**3):
    """Copy pinned split files to a new private directory; retain partial failure."""
    if (type(minimum_free_bytes) is not int or minimum_free_bytes < 0 or
            type(maximum_copy_bytes) is not int or maximum_copy_bytes < 1):
        raise ValueError('bounded sandbox limits required')
    receipt_path = _original(receipt_path)
    if receipt_path.name != 'receipt.json' or receipt_path.stat().st_size > 65536:
        raise ValueError('rehearsal receipt required')
    if _file_sha(receipt_path) != receipt_sha256:raise ValueError('rehearsal receipt pin mismatch')
    receipt = _strict_json(receipt_path.read_bytes())
    if (receipt.get('schema_version') != 'forecast-retention-rehearsal-v1' or receipt.get('integrity_check') != 'ok' or
            receipt.get('source_modified') is not False or receipt.get('writers_redirected') is not False or
            receipt.get('actual_recording_restored') is not False or receipt.get('live_promotion_allowed') is not False):
        raise ValueError('isolated split receipt required')
    paths = {name:_original(receipt_path.parent/name) for name in ('archive.sqlite','active.sqlite')}
    total = 0
    for name,path in paths.items():
        _no_sidecars(path);info=receipt['files'][name]
        if path.stat().st_size != info['bytes'] or _file_sha(path) != info['sha256']:
            raise ValueError('split file pin mismatch')
        total += info['bytes']
    output = Path(output).absolute()
    if (output.resolve() != output or output.exists() or not output.parent.is_dir() or
            output.parent == receipt_path.parent or receipt_path.parent in output.parents):
        raise ValueError('new separate sandbox directory required')
    if total > maximum_copy_bytes:raise ValueError('sandbox copy byte limit exceeded')
    if shutil.disk_usage(output.parent).free < minimum_free_bytes + total + 64 * 1024**2:
        raise ValueError('sandbox disk reserve insufficient')
    output.mkdir(mode=0o700)
    for name,source in paths.items():
        fd=os.open(output/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with source.open('rb') as src,os.fdopen(fd,'wb') as dest:
            shutil.copyfileobj(src,dest,length=1024*1024);dest.flush();os.fsync(dest.fileno())
        if _file_sha(output/name) != receipt['files'][name]['sha256'] or _file_sha(source) != receipt['files'][name]['sha256']:
            raise ValueError('sandbox copy differs from pinned source')
    if _file_sha(receipt_path) != receipt_sha256:raise ValueError('split receipt changed during copy')
    registration={'schema_version':'synthetic-outcome-id-rehearsal-v1','directory':str(output),
                  'archive_sha256':receipt['files']['archive.sqlite']['sha256'],
                  'initial_active_sha256':receipt['files']['active.sqlite']['sha256'],
                  'split_receipt_sha256':receipt_sha256,'synthetic_only':True,
                  'production_activation_allowed':False}
    fd=os.open(output/'registration.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(_canonical(registration)+b'\n');f.flush();os.fsync(f.fileno())
    return registration


def _commit(db):
    db.commit()


def append_synthetic_outcome(registration_path, registration_sha256, forecast_id, payload, observed_at, *,
                             now=None, minimum_free_bytes=2 * 1024**3, maximum_active_bytes=256 * 1024**2,
                             maximum_archive_bytes=1024**3, busy_timeout_seconds=5):
    """Append a synthetic version under SQLite's single-file write transaction.

    This guarantees ID uniqueness only among cooperating writers on this local
    active file with the pinned, immutable archive. It does not fence legacy,
    other-host, or direct writers and cannot be used for production outcomes.
    """
    if (type(minimum_free_bytes) is not int or minimum_free_bytes < 0 or
            type(maximum_active_bytes) is not int or maximum_active_bytes < 1 or
            type(maximum_archive_bytes) is not int or maximum_archive_bytes < 1 or
            type(busy_timeout_seconds) is not int or not 1 <= busy_timeout_seconds <= 30):
        raise ValueError('bounded writer limits required')
    if not isinstance(forecast_id,str) or not forecast_id or len(forecast_id)>256:
        raise ValueError('bounded forecast id required')
    if (not isinstance(payload,dict) or payload.get('scope') != 'synthetic_rehearsal_only' or
            payload.get('forecast_id') != forecast_id):raise ValueError('synthetic rehearsal payload required')
    event_id=payload.get('event_id')
    if not isinstance(event_id,str) or not event_id or len(event_id)>128:
        raise ValueError('bounded synthetic event identity required')
    payload_bytes=_canonical(payload)
    if len(payload_bytes)>65536:raise ValueError('synthetic payload limit exceeded')
    digest=hashlib.sha256(payload_bytes).hexdigest()
    now=now or datetime.now(UTC)
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:raise ValueError('aware clock required')
    now=now.astimezone(UTC);observed=_time(observed_at)
    if observed>now:raise ValueError('future observation prohibited')
    registration_path=_original(registration_path)
    if registration_path.name!='registration.json' or registration_path.stat().st_size>65536 or _file_sha(registration_path)!=registration_sha256:
        raise ValueError('pinned sandbox registration required')
    registration=_strict_json(registration_path.read_bytes());root=registration_path.parent
    if (registration.get('schema_version')!='synthetic-outcome-id-rehearsal-v1' or registration.get('directory')!=str(root) or
            registration.get('synthetic_only') is not True or registration.get('production_activation_allowed') is not False):
        raise ValueError('registered synthetic sandbox required')
    archive=_original(root/'archive.sqlite');active=_original(root/'active.sqlite')
    _no_sidecars(archive)
    if archive.stat().st_size>maximum_archive_bytes:raise ValueError('archive byte limit exceeded')
    if _file_sha(archive)!=registration['archive_sha256']:raise ValueError('archive pin mismatch')
    if any(Path(str(active)+suffix).exists() or Path(str(active)+suffix).is_symlink() for suffix in ('-wal','-shm')):
        raise ValueError('active WAL mode unsupported')
    if active.stat().st_size>=maximum_active_bytes or shutil.disk_usage(root).free<minimum_free_bytes:
        raise ValueError('active storage budget unavailable')
    ar=sqlite3.connect(archive.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=busy_timeout_seconds)
    db=sqlite3.connect(active,timeout=busy_timeout_seconds,isolation_level=None)
    try:
        db.execute('PRAGMA trusted_schema=OFF');ar.execute('PRAGMA trusted_schema=OFF')
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024*1024);ar.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024*1024)
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower()!='delete':raise ValueError('active DELETE journal required')
        page_size=db.execute('PRAGMA page_size').fetchone()[0]
        if maximum_active_bytes<page_size:raise ValueError('active storage budget unavailable')
        db.execute(f'PRAGMA max_page_count={maximum_active_bytes // page_size}')
        _check_schema(ar)
        db.execute('BEGIN IMMEDIATE')
        _check_schema(db)
        # Read the immutable archive in a separate attached read-only connection.
        db.execute('ATTACH DATABASE ? AS archive',(archive.as_uri()+'?mode=ro&immutable=1',))
        if db.execute('SELECT 1 FROM main.primary_forecasts a JOIN archive.primary_forecasts b ON a.id=b.id LIMIT 1').fetchone():
            raise ValueError('overlapping forecast ids')
        if db.execute('SELECT 1 FROM main.primary_forecast_outcomes a JOIN archive.primary_forecast_outcomes b ON a.id=b.id LIMIT 1').fetchone():
            raise ValueError('overlapping outcome ids')
        found=db.execute('SELECT payload FROM main.primary_forecasts WHERE id=? UNION ALL SELECT payload FROM archive.primary_forecasts WHERE id=?',(forecast_id,forecast_id)).fetchall()
        if len(found)!=1:raise ValueError('exactly one forecast required')
        target=_time(_strict_json(found[0][0])['target_information_end'])
        if observed<target:raise ValueError('outcome before forecast target')
        rows=db.execute('''SELECT id,digest,observed_at,payload FROM (SELECT id,digest,observed_at,payload,forecast FROM main.primary_forecast_outcomes
              UNION ALL SELECT id,digest,observed_at,payload,forecast FROM archive.primary_forecast_outcomes)
              WHERE forecast=? ORDER BY id DESC''',(forecast_id,))
        last=None;prior_event=None
        for row in rows:
            if last is None:last=row
            old_payload=_strict_json(row[3])
            if not isinstance(old_payload,dict):raise ValueError('invalid prior outcome payload')
            if old_payload.get('scope')=='synthetic_rehearsal_only' and old_payload.get('event_id')==event_id:
                if prior_event is not None:raise ValueError('duplicate synthetic event identity')
                prior_event=(row,old_payload)
        if prior_event is not None:
            row,old_payload=prior_event
            if row[1]!=digest or old_payload!=payload or _time(row[2])!=observed:
                raise ValueError('synthetic event identity conflict')
            if (_file_sha(archive)!=registration['archive_sha256'] or _file_sha(registration_path)!=registration_sha256 or
                    shutil.disk_usage(root).free<minimum_free_bytes):raise ValueError('sandbox inputs or reserve changed')
            _no_sidecars(archive)
            db.rollback();return {'status':'already_recorded','id':row[0],'synthetic_only':True}
        if last and _time(last[2])>observed:raise ValueError('backdated correction prohibited')
        old_max=max(db.execute('SELECT coalesce(max(id),0) FROM main.primary_forecast_outcomes').fetchone()[0],
                    db.execute('SELECT coalesce(max(id),0) FROM archive.primary_forecast_outcomes').fetchone()[0])
        if type(old_max) is not int or old_max<0 or old_max>=MAX_ID:raise ValueError('outcome id space exhausted')
        new_id=old_max+1
        db.execute('INSERT INTO main.primary_forecast_outcomes VALUES (?,?,?,?,?)',
                   (new_id,forecast_id,digest,observed.isoformat(),payload_bytes.decode('utf-8')))
        if (_file_sha(archive)!=registration['archive_sha256'] or _file_sha(registration_path)!=registration_sha256 or
                shutil.disk_usage(root).free<minimum_free_bytes):raise ValueError('sandbox inputs or reserve changed')
        _no_sidecars(archive)
        _commit(db)
        return {'status':'recorded','id':new_id,'synthetic_only':True}
    finally:
        db.close();ar.close()
