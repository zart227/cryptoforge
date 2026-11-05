"""Read-only health of the primary price-diagnostic store, not a trading gate."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import sqlite3
from time import monotonic


def inspect_forecast_health(path, *, now=None, maximum_database_bytes=256 * 1024**2,
                            minimum_free_bytes=2048 * 1024**2, maximum_seconds=10):
    if (type(maximum_database_bytes) is not int or maximum_database_bytes <= 0
            or type(minimum_free_bytes) is not int or minimum_free_bytes < 0
            or type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 120):
        raise ValueError('bounded diagnostic health limits required')
    now = now or datetime.now(UTC)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware observation time required')
    now = now.astimezone(UTC); path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink() or not path.parent.is_dir():
        raise ValueError('canonical diagnostic database path required')
    usage = shutil.disk_usage(path.parent); exists = path.exists()
    if exists and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('original diagnostic database file required')
    size = path.stat().st_size if exists else 0
    wal = Path(str(path) + '-wal')
    if wal.is_symlink():raise ValueError('original diagnostic WAL required')
    wal_size = wal.stat().st_size if wal.is_file() else 0
    reasons = []
    if size >= maximum_database_bytes:reasons.append('database_budget_reached')
    if usage.free < minimum_free_bytes:reasons.append('disk_reserve_preserved')
    result = {'schema_version': 'primary-price-forecast-health-v1', 'observed_at': now.isoformat(),
              'database_exists': exists, 'database_bytes': size, 'wal_bytes_observed': wal_size,
              'maximum_database_bytes': maximum_database_bytes, 'free_disk_bytes': usage.free,
              'minimum_free_bytes': minimum_free_bytes, 'capacity_blockers': reasons,
              'recording_capacity_blocked': bool(reasons), 'last_36_hours_window_start': (now-timedelta(hours=36)).isoformat(),
              'pending_last_36_hours': 0, 'older_unresolved_matured_forecasts': 0,
              'forecasts_not_yet_mature': 0,
              'total_forecasts': 0, 'total_outcome_versions': 0,
              'last_forecast_at': None, 'last_outcome_at': None,
              'forecasts_with_future_prediction_time': 0, 'forecasts_missing_target_time': 0,
              'source_mutated': False, 'future_cash_labels_created': False, 'live_promotion_allowed': False,
              'scope': 'bounded_read_only_price_diagnostics_not_worker_activity_or_cash_evidence'}
    if not exists:return result
    deadline = monotonic() + maximum_seconds
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)
    try:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
        db.set_progress_handler(lambda: int(monotonic() > deadline), 10000);db.execute('BEGIN')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not {'primary_forecasts'} <= tables <= {'primary_forecasts','primary_forecast_outcomes'}:
            raise ValueError('isolated forecast database required')
        count,last = db.execute("SELECT count(*),max(json_extract(payload,'$.predicted_at')) FROM primary_forecasts").fetchone()
        result.update(total_forecasts=count,last_forecast_at=last)
        result['forecasts_with_future_prediction_time'] = db.execute(
            "SELECT count(*) FROM primary_forecasts WHERE json_extract(payload,'$.predicted_at')>?", (now.isoformat(),)).fetchone()[0]
        result['forecasts_missing_target_time'] = db.execute(
            "SELECT count(*) FROM primary_forecasts WHERE json_extract(payload,'$.target_information_end') IS NULL").fetchone()[0]
        has_outcomes = 'primary_forecast_outcomes' in tables
        if has_outcomes:
            count,last = db.execute('SELECT count(*),max(observed_at) FROM primary_forecast_outcomes').fetchone()
            result.update(total_outcome_versions=count,last_outcome_at=last)
        missing = ('NOT EXISTS(SELECT 1 FROM primary_forecast_outcomes o WHERE o.forecast=f.id AND o.observed_at<=?)' if has_outcomes else '1')
        target = "json_extract(f.payload,'$.target_information_end')"
        cutoff = now.isoformat(); lower = (now-timedelta(hours=36)).isoformat()
        result['forecasts_not_yet_mature'] = db.execute(
            f"SELECT count(*) FROM primary_forecasts f WHERE {target}>? "
            "AND json_extract(f.payload,'$.predicted_at')<=?", (cutoff,cutoff)).fetchone()[0]
        result['pending_last_36_hours'] = db.execute(
            f'SELECT count(*) FROM primary_forecasts f WHERE {target}<=? AND {target}>=? AND {missing}',
            (cutoff,lower,cutoff) if has_outcomes else (cutoff,lower)).fetchone()[0]
        result['older_unresolved_matured_forecasts'] = db.execute(
            f'SELECT count(*) FROM primary_forecasts f WHERE {target}<? AND {missing}',
            (lower,cutoff) if has_outcomes else (lower,)).fetchone()[0]
        if monotonic() > deadline:raise TimeoutError('diagnostic health deadline')
    finally:
        db.close()
    return result
