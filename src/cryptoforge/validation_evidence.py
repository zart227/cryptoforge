"""Read-only verification of registered validation threshold report evidence."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from cryptoforge.research_attempts import encoded, identity
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.validation_threshold import ValidationPortfolio, select_validation_threshold


def _time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('aware evidence timestamp required')
    return result


def select_registered_validation_reports(ledger_path, *, study_sha256, reports,
                                        validation_start, validation_end,
                                        minimum_trades, maximum_drawdown):
    """Reports map candidate identities to local paths; no fitting or DB writes.

    The strict report format is intentionally separate from legacy development
    reports. Old evidence cannot acquire a preregistration timestamp retroactively.
    """
    uri = Path(ledger_path).resolve().as_uri() + '?mode=ro'
    db = sqlite3.connect(uri, uri=True)
    try:
        study = db.execute('SELECT payload,observed_at FROM studies WHERE id=?',
                           (study_sha256,)).fetchone()
        if study is None:
            raise ValueError('registered study required')
        manifest = json.loads(study[0])
        if identity(manifest) != study_sha256:
            raise ValueError('study manifest identity mismatch')
        if manifest.get('scope') != 'validation_threshold_selection':
            raise ValueError('explicit validation threshold study required')
        assert_source_dependencies(manifest.get('selection_source_hashes', {}), {
            'selector': select_validation_threshold,
            'evidence_verifier': select_registered_validation_reports,
            'source_guard': assert_source_dependencies})
        policy = manifest['selection_policy']
        if (policy['validation_start'] != validation_start.isoformat()
                or policy['validation_end'] != validation_end.isoformat()
                or policy['minimum_trades'] != minimum_trades
                or Decimal(str(policy['maximum_drawdown'])) != Decimal(str(maximum_drawdown))):
            raise ValueError('selection policy differs from preregistration')
        grid = manifest['grid']
        keys = {identity(candidate) for candidate in grid}
        if len(keys) != len(grid) or set(reports) != keys:
            raise ValueError('exact complete registered report grid required')
        rows = []
        for candidate in grid:
            key = identity(candidate)
            attempt = db.execute('SELECT status,payload,observed_at,completed_at FROM attempts '
                                 'WHERE study=? AND configuration=?', (study_sha256,key)).fetchone()
            if attempt is None or attempt[0] != 'completed':
                raise ValueError('completed registered attempt required')
            path = Path(reports[key])
            if path.stat().st_size > 1024 * 1024:
                raise ValueError('bounded validation summary required')
            raw = path.read_bytes()
            payload = json.loads(raw)
            if encoded(payload) != attempt[1]:
                raise ValueError('report differs from immutable registered result')
            if (payload['study_sha256'] != study_sha256 or payload['candidate'] != candidate
                    or payload['role'] != 'validation'):
                raise ValueError('report scope/configuration mismatch')
            started, finished = map(_time, (payload['execution_started_at'],payload['execution_finished_at']))
            if not (_time(study[1]) <= _time(attempt[2]) <= started <= finished <= _time(attempt[3])):
                raise ValueError('execution must follow observed preregistration')
            metrics = payload['portfolio']
            rows.append(ValidationPortfolio(
                Decimal(str(candidate['threshold'])), payload['role'],
                _time(payload['validation_start']), _time(payload['validation_end']),
                study_sha256, hashlib.sha256(raw).hexdigest(),
                *(Decimal(str(metrics[name])) for name in ('initial_cash','net_pnl',
                    'stress_net_pnl','max_drawdown','stress_max_drawdown')),
                metrics['trade_count'],metrics['stress_trade_count']))
        result = select_validation_threshold(rows,
            declared_thresholds=[candidate['threshold'] for candidate in grid],
            validation_start=validation_start, validation_end=validation_end,
            study_sha256=study_sha256,minimum_trades=minimum_trades,
            maximum_drawdown=maximum_drawdown)
        result.update(report_checksums_verified_by_selector=True,
                      registered_results_verified=True,study_sha256=study_sha256)
        return result
    finally:
        db.close()
