"""Versioned execution lessons; delayed corrections cannot leak into older cutoffs."""
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path
import sqlite3


def remember_report(report: dict,path: Path,*,observed_at=None) -> dict:
    observed_at=observed_at or datetime.now(UTC)
    if observed_at.tzinfo is None:raise ValueError('timezone-aware observation time required')
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS execution_outcomes (pair TEXT, exit_order TEXT, information_end TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(pair,exit_order)) WITHOUT ROWID')
        db.execute('CREATE TABLE IF NOT EXISTS outcome_versions (pair TEXT, exit_order TEXT, payload_sha256 TEXT, information_end TEXT NOT NULL, observed_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(pair,exit_order,payload_sha256)) WITHOUT ROWID')
        with db:
            for outcome in report['outcomes']:
                payload=json.dumps({**outcome,'accounting_quality_verified':report.get('accounting_quality_verified',False)},sort_keys=True,default=str)
                digest=hashlib.sha256(payload.encode()).hexdigest()
                db.execute('INSERT INTO outcome_versions VALUES (?,?,?,?,?,?) ON CONFLICT(pair,exit_order,payload_sha256) DO NOTHING',
                    (outcome['pair'],outcome['exit_order'],digest,outcome['effective_information_end'],observed_at.isoformat(),payload))
                db.execute('INSERT INTO execution_outcomes VALUES (?,?,?,?) ON CONFLICT(pair,exit_order) DO UPDATE SET information_end=excluded.information_end,payload=excluded.payload',
                    (outcome['pair'],outcome['exit_order'],outcome['effective_information_end'],payload))
        count=db.execute('SELECT count(*) FROM execution_outcomes').fetchone()[0]
        versions=db.execute('SELECT count(*) FROM outcome_versions').fetchone()[0]
        return {'stored_exit_orders':count,'versions':versions,'source_as_of':report['as_of'],
                'observed_at':observed_at.isoformat(),'path':str(path.resolve()),
                'policy':'facts_and_hypotheses_only_no_live_policy_updates'}
    finally:
        db.close();path.chmod(0o600)


def prior_outcomes(path: Path,as_of: datetime) -> list[dict]:
    if as_of.tzinfo is None:raise ValueError('timezone-aware memory cutoff required')
    db=sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)
    try:
        result={}
        rows=db.execute('SELECT pair,exit_order,information_end,observed_at,payload FROM outcome_versions')
        for pair,order,end,observed,payload in rows:
            end_time=datetime.fromisoformat(end.replace('Z','+00:00'))
            seen_time=datetime.fromisoformat(observed.replace('Z','+00:00'))
            if end_time>as_of or seen_time>as_of:continue
            parsed=json.loads(payload)
            if not parsed.get('accounting_quality_verified'):continue
            key=(pair,order)
            if key not in result or seen_time>result[key][0]:result[key]=(seen_time,parsed)
        return [result[key][1] for key in sorted(result)]
    finally:db.close()


class ObservedFeedbackReader:
    """Calibrate only with versions actually observed before the training cutoff.

    Current source health still gates publication. Its retrospective outcome
    rows are deliberately excluded from calibration: corrections lack their
    original observation time outside the versioned memory.
    """
    def __init__(self, source_reader, path: Path):
        self.source_reader = source_reader
        self.path = path

    def read(self, *, as_of: datetime, lookback_days: int = 14) -> dict:
        from datetime import timedelta
        from decimal import Decimal
        health = self.source_reader.read(as_of=as_of, lookback_days=lookback_days)
        outcomes = prior_outcomes(self.path, as_of) if self.path.exists() else []
        since = as_of - timedelta(days=lookback_days)
        outcomes = [row for row in outcomes
                    if datetime.fromisoformat(row['closed_at'].replace('Z', '+00:00')) >= since]
        return {'as_of':as_of.isoformat(), 'outcomes':outcomes,
                'accounting_quality_verified':health.get('accounting_quality_verified',False),
                'trades_truncated':health.get('trades_truncated',False),
                'decisions_truncated':health.get('decisions_truncated',False),
                'summary':{'closed_exit_orders':len(outcomes),
                           'net_pnl_usdt':str(sum((Decimal(row['net_pnl']) for row in outcomes),Decimal(0)))},
                'evidence_policy':'verified_versions_observed_before_train_cutoff',
                'memory_available':self.path.exists()}
