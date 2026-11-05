"""Read-only reader for pinned, isolated rehearsal files; not live wiring."""
from contextlib import closing, contextmanager
from datetime import UTC, timedelta
import hashlib
from itertools import islice
import json
from pathlib import Path
import sqlite3
from time import monotonic

from cryptoforge.forecast_memory_snapshot import _file_sha, _schema
from cryptoforge.forecast_retention_preflight import _no_sidecars, _original, _strict_json
from cryptoforge.forecast_retention_rehearsal import FORECAST_DDL, OUTCOME_DDL, INDEX_DDL


class RehearsalForecastReader:
    """Emulate existing reads on a fixed, verified two-file split only."""
    def __init__(self, receipt, receipt_sha256, *, maximum_bytes=1024**3, maximum_rows=200000, maximum_seconds=180):
        if (type(maximum_bytes) is not int or maximum_bytes < 1 or type(maximum_rows) is not int or maximum_rows < 1 or
                type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 600):
            raise ValueError('bounded reader limits required')
        self.receipt = _original(receipt);self.receipt_sha256 = receipt_sha256
        self.maximum_bytes = maximum_bytes;self.maximum_rows = maximum_rows;self.maximum_seconds = maximum_seconds

    @contextmanager
    def _open(self):
        deadline=monotonic()+self.maximum_seconds
        receipt=self.receipt
        if receipt.name != 'receipt.json' or receipt.stat().st_size > 65536:
            raise ValueError('canonical rehearsal receipt required')
        raw=receipt.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.receipt_sha256:raise ValueError('rehearsal receipt hash mismatch')
        r=_strict_json(raw)
        if (r.get('schema_version')!='forecast-retention-rehearsal-v1' or r.get('integrity_check')!='ok' or
                r.get('source_modified') is not False or r.get('writers_redirected') is not False or
                r.get('actual_recording_restored') is not False or r.get('live_promotion_allowed') is not False):
            raise ValueError('isolated rehearsal receipt required')
        paths={name:_original(receipt.parent/(name+'.sqlite')) for name in ('archive','active')}
        for name,path in paths.items():
            _no_sidecars(path); info=r['files'][name+'.sqlite']
            if path.stat().st_size!=info['bytes'] or path.stat().st_size>self.maximum_bytes or _file_sha(path)!=info['sha256']:
                raise ValueError('pinned rehearsal file mismatch')
        if monotonic()>deadline:raise TimeoutError('rehearsal reader deadline')
        db=sqlite3.connect(':memory:',uri=True)
        try:
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-8192')
            db.set_progress_handler(lambda:int(monotonic()>deadline),10000)
            for name,path in paths.items():
                db.execute(f'ATTACH DATABASE ? AS {name}',(path.as_uri()+'?mode=ro&immutable=1',))
                # _schema expects main; inspect each separate database without changing it.
                check=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
                try:schema,tables=_schema(check)
                finally:check.close()
                if tables != {'primary_forecasts','primary_forecast_outcomes'} or {row[2] for row in schema}!={FORECAST_DDL,OUTCOME_DDL,INDEX_DDL}:
                    raise ValueError('unknown split schema')
                counts={'forecasts':db.execute(f'SELECT count(*) FROM {name}.primary_forecasts').fetchone()[0],
                        'outcomes':db.execute(f'SELECT count(*) FROM {name}.primary_forecast_outcomes').fetchone()[0]}
                if counts!=r['counts'][name]:raise ValueError('split row counts mismatch')
            if sum(sum(c.values()) for c in r['counts'].values())>self.maximum_rows:raise ValueError('reader row limit exceeded')
            if db.execute('SELECT 1 FROM archive.primary_forecasts a JOIN active.primary_forecasts b ON a.id=b.id LIMIT 1').fetchone():
                raise ValueError('overlapping forecast ids')
            if db.execute('SELECT 1 FROM archive.primary_forecast_outcomes a JOIN active.primary_forecast_outcomes b ON a.id=b.id LIMIT 1').fetchone():
                raise ValueError('overlapping outcome ids')
            orphan='''WITH forecasts AS (SELECT id FROM archive.primary_forecasts UNION ALL SELECT id FROM active.primary_forecasts),
            outcomes AS (SELECT forecast FROM archive.primary_forecast_outcomes UNION ALL SELECT forecast FROM active.primary_forecast_outcomes)
            SELECT 1 FROM outcomes o WHERE NOT EXISTS (SELECT 1 FROM forecasts f WHERE f.id=o.forecast) LIMIT 1'''
            if db.execute(orphan).fetchone():raise ValueError('orphan outcome')
            yield db
        finally:
            db.close()
            if (hashlib.sha256(receipt.read_bytes()).hexdigest()!=self.receipt_sha256 or
                    any(_file_sha(path)!=r['files'][name+'.sqlite']['sha256'] for name,path in paths.items())):
                raise ValueError('rehearsal files changed during read')
            for path in paths.values():_no_sidecars(path)
            if monotonic()>deadline:raise TimeoutError('rehearsal reader deadline')

    def iter_rows(self):
        with self._open() as db:
            query='SELECT id,payload FROM archive.primary_forecasts UNION ALL SELECT id,payload FROM active.primary_forecasts ORDER BY id'
            for fid,payload in db.execute(query):yield {**json.loads(payload),'forecast_id':fid}

    def rows(self, *, limit=1000):
        if type(limit) is not int or limit<1:raise ValueError('positive forecast read limit required')
        with closing(self.iter_rows()) as rows:return list(islice(rows,limit))

    def matured_batch(self, *, as_of, limit=400):
        if as_of.tzinfo is None or as_of.utcoffset() is None or type(limit) is not int or limit<1:
            raise ValueError('aware bounded primary outcome batch required')
        cutoff=as_of.astimezone(UTC);lower=cutoff-timedelta(hours=36)
        with self._open() as db:
            query='''WITH forecasts AS (SELECT * FROM archive.primary_forecasts UNION ALL SELECT * FROM active.primary_forecasts),
                outcomes AS (SELECT * FROM archive.primary_forecast_outcomes UNION ALL SELECT * FROM active.primary_forecast_outcomes)
                SELECT f.id,f.payload FROM forecasts f WHERE json_extract(f.payload,'$.target_information_end')<=?
                AND json_extract(f.payload,'$.target_information_end')>=?
                ORDER BY EXISTS(SELECT 1 FROM outcomes o WHERE o.forecast=f.id),
                json_extract(f.payload,'$.target_information_end'),f.id LIMIT ?'''
            return [{**json.loads(payload),'forecast_id':fid} for fid,payload in db.execute(query,(cutoff.isoformat(),lower.isoformat(),limit))]

    def available_outcome(self, forecast_id, *, as_of):
        if as_of.tzinfo is None or as_of.utcoffset() is None:raise ValueError('aware cutoff required')
        cutoff=as_of.astimezone(UTC).isoformat()
        with self._open() as db:
            query='''SELECT payload FROM (SELECT id,forecast,observed_at,payload FROM archive.primary_forecast_outcomes
                UNION ALL SELECT id,forecast,observed_at,payload FROM active.primary_forecast_outcomes)
                WHERE forecast=? AND observed_at<=? ORDER BY id DESC LIMIT 1'''
            row=db.execute(query,(forecast_id,cutoff)).fetchone()
            return json.loads(row[0]) if row else None

    def iter_labeled_asof(self, *, as_of):
        if as_of.tzinfo is None or as_of.utcoffset() is None:raise ValueError('aware cutoff required')
        cutoff=as_of.astimezone(UTC).isoformat()
        with self._open() as db:
            query='''WITH forecasts AS (SELECT * FROM archive.primary_forecasts UNION ALL SELECT * FROM active.primary_forecasts),
                outcomes AS (SELECT * FROM archive.primary_forecast_outcomes UNION ALL SELECT * FROM active.primary_forecast_outcomes)
                SELECT f.id,f.payload,o.payload FROM forecasts f JOIN outcomes o ON o.id=(SELECT v.id FROM outcomes v
                WHERE v.forecast=f.id AND v.observed_at<=? ORDER BY v.id DESC LIMIT 1)
                WHERE json_extract(f.payload,'$.predicted_at')<=? ORDER BY f.id'''
            for fid,forecast,outcome in db.execute(query,(cutoff,cutoff)):
                yield fid,json.loads(forecast),json.loads(outcome)
