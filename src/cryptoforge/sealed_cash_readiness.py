"""Calendar-first cash readiness. Unfinished windows never load outcome payloads."""
from pathlib import Path
import sqlite3
from time import monotonic

from cryptoforge.local_source_provenance import parse, stamp
from cryptoforge.live_learning_protocol import evaluate_readiness, split_cutoff, validate_protocol


def guarded_cash_readiness(protocol, *, as_of, load_split, source_healthy=False):
    validate_protocol(protocol)
    now = stamp(as_of)
    if type(source_healthy) is not bool:
        raise ValueError('explicit verified source-health boolean required')
    snapshots, inspected = {}, []
    for split in ('train', 'validation'):
        if now >= stamp(protocol['windows'][split]['end_exclusive']):
            snapshots[split] = load_split(split, split_cutoff(protocol, split, now))
            if type(snapshots[split]) is not list or len(snapshots[split]) > 10000:
                raise ValueError('bounded completed-window snapshot required')
            inspected.append(split)
    # Sealed-test and paper are never loaded through this development preflight,
    # even after their end. Unblinding needs its own registered evaluation path.
    result = evaluate_readiness(protocol, snapshots, as_of=now, source_healthy=source_healthy)
    for split, summary in result['splits'].items():
        read = split in inspected
        summary['payload_inspected'] = read
        summary['outcomes_hidden'] = not read
        if not read:
            summary['counts'] = None
            summary['excluded'] = None
            summary['ready'] = False
            summary['failures'] = [dict(gate='outcome_payload_not_opened',
                reason='explicit_independent_unblinding_required' if split in ('sealed_test', 'paper') else 'window_not_finished',
                not_before=protocol['windows'][split]['end_exclusive'])]
    if inspected != ['train', 'validation']:
        result['data_ready_for_offline_fit'] = False
        result['blocked_reasons'].append('development_windows_not_both_finished')
    result['sealed_test_data_ready'] = False
    result.update(schema_version='sealed-cash-readiness-v1',
        status='calendar_only_no_outcome_payloads_read' if not inspected else 'completed_development_windows_only',
        inspected_splits=inspected, sealed_test_or_paper_payloads_read=False,
        automatic_training_allowed=False, live_promotion_allowed=False,
        source_health_qualified=source_healthy,
        scope='guarded_readiness_not_candidate_profitability_or_worker_admission')
    return result


def bounded_available_experiences(path, *, target, as_of, maximum_versions=10000,
                                  maximum_bytes=16*1024**2, maximum_seconds=5):
    """Read one bounded original snapshot only AFTER the caller's window guard.

    A missing store is empty, never created. SQLite cannot return an arbitrarily
    large payload: a CASE guard checks its byte length before fetching it.
    """
    if (type(target) is not str or not 0 < len(target.encode()) <= 256
            or type(maximum_versions) is not int or not 1 <= maximum_versions <= 10000
            or type(maximum_bytes) is not int or not 1024 <= maximum_bytes <= 16*1024**2
            or type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 5):
        raise ValueError('bounded cash snapshot policy required')
    cutoff = stamp(as_of).isoformat()
    path = Path(path).absolute()
    if path.resolve() != path:
        raise ValueError('canonical original experience store required')
    if not path.exists():
        return []
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('original experience file required')
    if any(Path(str(path)+s).exists() for s in ('-journal', '-wal', '-shm')):
        raise ValueError('experience sidecar requires separate recovery')
    def identity():
        s = path.stat()
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink
    before = identity()
    started = monotonic()
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.25)
    try:
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: int(monotonic()-started > maximum_seconds), 1000)
        db.execute('BEGIN')
        rows = db.execute('''SELECT pair,entry_order,
            CASE WHEN length(CAST(payload AS BLOB)) <= 262144 THEN payload END,
            length(CAST(payload AS BLOB))
            FROM experience_versions WHERE target=? AND observed_at<=?
            ORDER BY observed_at,id LIMIT ?''', (target, cutoff, maximum_versions+1))
        latest, size = {}, 0
        for count, (pair, order, payload, length) in enumerate(rows, 1):
            if count > maximum_versions or payload is None or type(length) is not int:
                raise ValueError('cash version or individual payload budget exhausted')
            size += length
            if size > maximum_bytes or monotonic()-started > maximum_seconds:
                raise ValueError('cash snapshot byte/wall budget exhausted')
            value = parse(payload)
            if type(value) is not dict or type(value.get('eligible', True)) is not bool:
                raise ValueError('original experience payload schema differs')
            if (value.get('pair'), value.get('entry_order'), value.get('target_version')) != (pair, order, target):
                raise ValueError('original experience metadata/payload differs')
            latest[pair, order] = value
        if identity() != before:
            raise ValueError('experience store changed during snapshot')
        return [latest[key] for key in sorted(latest) if latest[key].get('eligible', True) is True]
    except sqlite3.Error as exc:
        raise ValueError('bounded read-only cash snapshot failed') from exc
    finally:
        db.rollback()
        db.close()
