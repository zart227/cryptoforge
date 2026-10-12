"""First-observed, versioned experimental examples; repeat runs are not new samples."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3


def remember_experiences(report: dict, path: Path, *, observed_at: datetime) -> dict:
    if observed_at.tzinfo is None:raise ValueError('timezone-aware observed time required')
    if not report.get('accounting_quality_verified'):
        return {'status':'unverified_not_stored','stored_versions':0}
    seen=observed_at.astimezone(UTC).isoformat();target=report['target_version']
    path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS experience_versions (id INTEGER PRIMARY KEY, target TEXT NOT NULL, pair TEXT NOT NULL, entry_order TEXT NOT NULL, digest TEXT NOT NULL, observed_at TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS experience_current (target TEXT, pair TEXT, entry_order TEXT, version_id INTEGER NOT NULL, PRIMARY KEY(target,pair,entry_order)) WITHOUT ROWID')
        with db:
            for row in report['examples']:
                if datetime.fromisoformat(row['label_available_at'])>observed_at:
                    raise ValueError('cannot store experience before source observation')
                example=row['example']
                semantic={key:row[key] for key in ('target_version','pair','entry_order','cost',
                    'cash_recovery_net','residual_cost','residual_quantity','dust_reason','closed_at')}
                semantic['feature_time']=str(example['open_time']);semantic['features']=example['features']
                semantic['input_candle_state']=row.get('input_candle_state','unknown')
                if 'feature_input_contract' in row:semantic['feature_input_contract']=row['feature_input_contract']
                semantic['entry_at']=row.get('entry_at','unknown')
                digest=hashlib.sha256(json.dumps(semantic,sort_keys=True,default=str).encode()).hexdigest()
                old=db.execute('SELECT v.digest,v.observed_at FROM experience_current c JOIN experience_versions v ON v.id=c.version_id WHERE c.target=? AND c.pair=? AND c.entry_order=?',
                               (target,row['pair'],row['entry_order'])).fetchone()
                if old and datetime.fromisoformat(old[1])>observed_at:
                    raise ValueError('cannot backdate an experience correction')
                if old and old[0]==digest:continue
                payload={**row,'label_available_at':seen,'example':{**example,'label_end_time':seen}}
                cursor=db.execute('INSERT INTO experience_versions (target,pair,entry_order,digest,observed_at,payload) VALUES (?,?,?,?,?,?)',
                    (target,row['pair'],row['entry_order'],digest,seen,json.dumps(payload,default=str,sort_keys=True)))
                db.execute('INSERT INTO experience_current VALUES (?,?,?,?) ON CONFLICT(target,pair,entry_order) DO UPDATE SET version_id=excluded.version_id',
                           (target,row['pair'],row['entry_order'],cursor.lastrowid))
            # Only explicit, verified corrections withdraw an existing example.
            # Missing coverage or a transient market request never implies deletion.
            withdrawal_reasons={'external_exit','external_acquisition','missing_original_features',
                'features_not_known_before_entry','invalid_features','unknown_fees_or_pnl',
                'invalid_original_input_contract',
                'invalid_closed_execution_cost_or_quantity','invalid_cost_or_pnl','inconsistent_remainder_cost',
                'unresolved_remainder_status'}
            accepted={(r['pair'],r['entry_order']) for r in report['examples']}
            if report.get('source_binding_verified') is True and not report.get('snapshot_truncated'):
                for row in report.get('excluded',[]):
                    pair,order=row.get('pair'),row.get('entry_order');reason=row['reason']
                    if not pair or not order or (pair,order) in accepted or reason not in withdrawal_reasons:continue
                    old=db.execute('SELECT v.digest,v.observed_at FROM experience_current c JOIN experience_versions v ON v.id=c.version_id WHERE c.target=? AND c.pair=? AND c.entry_order=?',
                        (target,pair,order)).fetchone()
                    if not old:continue
                    if datetime.fromisoformat(old[1])>observed_at:raise ValueError('cannot backdate an experience withdrawal')
                    digest=hashlib.sha256(json.dumps({'eligible':False,'reason':reason},sort_keys=True).encode()).hexdigest()
                    if old[0]==digest:continue
                    payload={'eligible':False,'withdrawal_reason':reason,'pair':pair,'entry_order':order,
                             'target_version':target,'label_available_at':seen}
                    cursor=db.execute('INSERT INTO experience_versions (target,pair,entry_order,digest,observed_at,payload) VALUES (?,?,?,?,?,?)',
                        (target,pair,order,digest,seen,json.dumps(payload,sort_keys=True)))
                    db.execute('UPDATE experience_current SET version_id=? WHERE target=? AND pair=? AND entry_order=?',
                        (cursor.lastrowid,target,pair,order))
        total=db.execute('SELECT count(*) FROM experience_current WHERE target=?',(target,)).fetchone()[0]
        count=sum(json.loads(raw).get('eligible',True) for raw, in db.execute('SELECT v.payload FROM experience_current c JOIN experience_versions v ON v.id=c.version_id WHERE c.target=?',(target,)))
        versions=db.execute('SELECT count(*) FROM experience_versions WHERE target=?',(target,)).fetchone()[0]
        return {'status':'stored','distinct_buy_orders':count,'historical_distinct_buy_orders':total,'withdrawn_buy_orders':total-count,'stored_versions':versions,
                'policy':'one_version_per_buy_at_cutoff_no_duplicate_sampling','path':str(path.resolve())}
    finally:db.close();path.chmod(0o600)


def available_experiences(path: Path, *, target: str, as_of: datetime) -> list[dict]:
    if as_of.tzinfo is None:raise ValueError('timezone-aware example cutoff required')
    if not path.exists():return []
    db=sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)
    try:
        rows=db.execute('SELECT pair,entry_order,payload FROM experience_versions WHERE target=? AND observed_at<=? ORDER BY observed_at,id',
                        (target,as_of.astimezone(UTC).isoformat()))
        latest={}
        for pair,order,payload in rows:latest[pair,order]=json.loads(payload)
        return [latest[key] for key in sorted(latest) if latest[key].get('eligible',True)]
    finally:db.close()
