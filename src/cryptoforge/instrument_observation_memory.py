"""Forward-observed public Spot rules, never backfilled into old history."""
from datetime import UTC,datetime,timedelta
import hashlib,json,sqlite3
from pathlib import Path
from cryptoforge.live_learning_protocol import time
from cryptoforge.training_snapshot import _save_raw


class InstrumentObservationMemory:
    def __init__(self,root,*,clock=None):
        self.root=Path(root);self.path=self.root/'observations.sqlite'
        self.clock=clock or (lambda:datetime.now(UTC))

    def remember(self,payload,*,request_started_at,response_observed_at):
        now=self.clock()
        if any(stamp.tzinfo is None for stamp in (now,request_started_at,response_observed_at)) or not (
            request_started_at<=response_observed_at<=now and now-response_observed_at<=timedelta(seconds=5)):
            raise ValueError('actual instrument response observation required')
        result=payload.get('result') or {};rows=result.get('list')
        if payload.get('retCode')!=0 or result.get('category')!='spot' or not isinstance(rows,list) or not rows:
            raise ValueError('verified nonempty public Spot response required')
        symbols=[row.get('symbol') for row in rows]
        if any(not isinstance(symbol,str) or not symbol for symbol in symbols) or len(set(symbols))!=len(symbols):
            raise ValueError('unique public instrument symbols required')
        raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        reference=_save_raw(self.root/'sources',raw)
        observed=response_observed_at.astimezone(UTC).isoformat()
        receipt={'schema_version':'observed-public-spot-instruments-v1','observed_at':observed,
            'request_started_at':request_started_at.astimezone(UTC).isoformat(),'source':reference,
            'source_endpoint':'https://api.bybit.com/v5/market/instruments-info?category=spot',
            'source_hash_semantics':'canonical_parsed_response_not_raw_transport_bytes',
            'symbols_observed':len(rows),'response_has_more_pages':bool(result.get('nextPageCursor')),
            'effective_change_times_known':False,'can_certify_historical_execution':False,'live_promotion_allowed':False}
        key=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()
        self.root.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path,timeout=5)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'instrument_observations'}:raise ValueError('isolated instrument observation database required')
            db.execute('CREATE TABLE IF NOT EXISTS instrument_observations (id TEXT PRIMARY KEY,observed_at TEXT,payload TEXT) WITHOUT ROWID')
            with db:db.execute('INSERT OR IGNORE INTO instrument_observations VALUES (?,?,?)',(key,observed,json.dumps(receipt,sort_keys=True)))
            self.path.chmod(0o600)
        finally:db.close()
        return receipt

    def state_at(self,symbol,*,as_of,maximum_age=timedelta(hours=1)):
        if as_of.tzinfo is None or maximum_age<=timedelta(0):raise ValueError('aware bounded instrument observation cutoff required')
        if not self.path.exists():return {'status':'no_prior_observation','can_certify_historical_execution':False}
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:row=db.execute('SELECT payload FROM instrument_observations WHERE observed_at<=? ORDER BY observed_at DESC LIMIT 1',
            (as_of.astimezone(UTC).isoformat(),)).fetchone()
        finally:db.close()
        if row is None:return {'status':'no_prior_observation','can_certify_historical_execution':False}
        receipt=json.loads(row[0]);age=as_of-time(receipt['observed_at'])
        if age>maximum_age:return {'status':'stale_prior_observation','observed_at':receipt['observed_at'],'can_certify_historical_execution':False}
        reference=receipt['source']
        import gzip
        with gzip.open(reference['path'],'rb') as stream:raw=stream.read(reference['uncompressed_bytes']+1)
        if len(raw)!=reference['uncompressed_bytes'] or hashlib.sha256(raw).hexdigest()!=reference['sha256']:
            raise ValueError('instrument observation source checksum mismatch')
        rows=json.loads(raw)['result']['list'];instrument=next((r for r in rows if r['symbol']==symbol),None)
        return {'status':'observed_in_public_response' if instrument else 'not_in_observed_response',
            'observed_at':receipt['observed_at'],'instrument':instrument,
            'response_has_more_pages':receipt['response_has_more_pages'],
            'absence_proves_delisting':False,'can_certify_historical_execution':False,
            'rule_change_between_observations_excluded':False}
