"""Prospectively observed primary-model diagnostics, never execution labels."""
from datetime import UTC,datetime,timedelta
import hashlib,json,math,shutil,sqlite3
from decimal import Decimal
from cryptoforge.live_learning_protocol import time


class PrimaryForecastMemory:
    def __init__(self,path,*,clock=None,minimum_free_disk_mb=2048,maximum_database_mb=256):
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))
        self.minimum_free_disk_mb=minimum_free_disk_mb;self.maximum_database_mb=maximum_database_mb

    def record(self,forecast):
        now=self.clock();predicted=time(forecast['predicted_at']);observed=time(forecast['feature_observed_at'])
        if now.tzinfo is None:raise ValueError('aware primary forecast clock required')
        now=now.astimezone(UTC)
        if now.tzinfo is None or not observed<=predicted<=now or now-predicted>timedelta(seconds=5):
            raise ValueError('cannot record primary forecast retrospectively')
        sha=forecast['artifact_sha256']
        if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('verified primary artifact SHA required')
        values=forecast['features']
        if len(values)!=7 or not all(math.isfinite(v) for v in values):raise ValueError('finite primary feature vector required')
        if forecast['target_version']!='fixed-future-return-v1' or forecast['horizon_candles']!=3:
            raise ValueError('primary candle target required, not executed-buy cash labels')
        contract=forecast['input_contract'];width=contract.get('lookback_candles')
        if (contract.get('feature_version')!='candle-v1' or contract.get('timeframe')!='5m'
            or contract.get('calculation_contract')!='bounded-window-candle-v1'
            or contract.get('input_candle_state')!=forecast['input_candle_state']
            or forecast['input_candle_state'] not in {'legacy_asof_snapshot','closed_only'}
            or type(width) is not int or not 36<=width<=1000):raise ValueError('explicit primary input contract required')
        bar=time(forecast['input_bar_open_time']);target_end=bar+timedelta(minutes=20)
        if target_end<=predicted:raise ValueError('forecast target is already historical')
        if forecast['input_candle_state']=='closed_only' and bar+timedelta(minutes=5)>observed:
            raise ValueError('closed primary input is not closed at observation')
        reference=Decimal(forecast['reference_close'])
        if not reference.is_finite() or reference<=0:raise ValueError('finite candle target reference required')
        if forecast.get('label_policy_known') is True:
            for field in ('min_label_return','round_trip_cost'):
                value=forecast.get(field)
                if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<1:
                    raise ValueError('explicit finite original price label policy required')
        for name in ('long_probability','short_probability'):
            p=forecast[name]
            if p is not None and (not math.isfinite(p) or not 0<=p<=1):raise ValueError('finite primary probability required')
        identity={name:forecast[name] for name in (
            'artifact_sha256','pair','opportunity_bar_open_time','input_bar_open_time','input_contract')}
        for name in ('opportunity_bar_open_time','input_bar_open_time'):identity[name]=time(identity[name]).isoformat()
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        if self.path.exists() and self.path.stat().st_size>=self.maximum_database_mb*1024**2:
            return {'status':'database_budget_reached','stored':False}
        existing=self.path.parent
        while not existing.exists():existing=existing.parent
        if shutil.disk_usage(existing).free<self.minimum_free_disk_mb*1024**2:
            return {'status':'disk_reserve_preserved','stored':False}
        payload={**forecast,'observed_at':now.isoformat(),'source_kind':'primary_forecast_opportunity_diagnostic',
            'predicted_at':predicted.isoformat(),'feature_observed_at':observed.isoformat(),
            'opportunity_bar_open_time':identity['opportunity_bar_open_time'],'input_bar_open_time':identity['input_bar_open_time'],
            'target_information_end':target_end.isoformat(),'prediction_lead_seconds':(target_end-predicted).total_seconds(),
            'reference_kind':'candle_target_reference_not_actual_execution_price',
            'counts_as_real_executed_buys':False,'live_promotion_allowed':False}
        self.path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path,timeout=1)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'primary_forecasts','primary_forecast_outcomes'}:raise ValueError('isolated primary forecast database required')
            db.execute('CREATE TABLE IF NOT EXISTS primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
            with db:
                cursor=db.execute('INSERT OR IGNORE INTO primary_forecasts VALUES (?,?)',(key,json.dumps(payload,sort_keys=True)))
            self.path.chmod(0o600)
            return {'status':'first_prospective_snapshot_recorded' if cursor.rowcount else 'first_snapshot_preserved',
                    'stored':bool(cursor.rowcount),'forecast_id':key}
        finally:db.close()

    def iter_rows(self):
        if not self.path.exists():return
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            for row in db.execute('SELECT id,payload FROM primary_forecasts ORDER BY id'):
                yield {**json.loads(row[1]),'forecast_id':row[0]}
        finally:db.close()

    def rows(self,*,limit=1000):
        if type(limit) is not int or limit<1:raise ValueError('positive forecast read limit required')
        from itertools import islice
        from contextlib import closing
        with closing(self.iter_rows()) as rows:return list(islice(rows,limit))

    def record_outcome(self,forecast_id,candle,*,original_policy=None):
        """Version a matured price endpoint, never a hypothetical cash fill."""
        from cryptoforge.candle_contract import known_closed
        now=self.clock()
        if now.tzinfo is None:raise ValueError('aware primary price observation clock required')
        now=now.astimezone(UTC)
        if not self.path.exists():raise ValueError('original primary forecast unavailable')
        db=sqlite3.connect(self.path,timeout=1)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'primary_forecasts','primary_forecast_outcomes'}:raise ValueError('isolated primary forecast database required')
            row=db.execute('SELECT payload FROM primary_forecasts WHERE id=?',(forecast_id,)).fetchone()
            if row is None:raise ValueError('original primary forecast unavailable')
            forecast=json.loads(row[0]);end=time(forecast['target_information_end'])
            if now.tzinfo is None or now<end or not known_closed(candle,step=timedelta(minutes=5),as_of=now):
                raise ValueError('primary price endpoint is not available yet')
            if (candle.pair!=forecast['pair'] or candle.symbol!=forecast['pair'].replace('/','')
                or candle.open_time+timedelta(minutes=5)!=end):raise ValueError('primary price endpoint identity mismatch')
            if not all(v.is_finite() for v in (candle.open,candle.high,candle.low,candle.close,candle.volume)) or not (
                0<candle.low<=min(candle.open,candle.close)<=max(candle.open,candle.close)<=candle.high and candle.volume>=0):
                raise ValueError('invalid primary endpoint OHLCV')
            reference=Decimal(forecast['reference_close']);gross=candle.close/reference-1
            known_policy=forecast.get('label_policy_known') is True
            policy=forecast
            policy_source='original_forecast_payload' if known_policy else 'unavailable'
            if not known_policy and original_policy is not None:
                if (original_policy['artifact_sha256']!=forecast['artifact_sha256']
                    or time(original_policy['trained_at'])>time(forecast['predicted_at'])):
                    raise ValueError('original price policy does not match prospective model')
                policy=original_policy;known_policy=True;policy_source='verified_original_artifact_observed_now'
            threshold=Decimal(str(policy['min_label_return'])) if known_policy else None
            cost=Decimal(str(policy['round_trip_cost'])) if known_policy else None
            if not gross.is_finite() or (known_policy and (not threshold.is_finite() or not cost.is_finite()
                or not 0<=threshold<1 or not 0<=cost<1)):raise ValueError('finite price target and assumed cost required')
            semantic={'endpoint_close':str(candle.close),'gross_candle_return':str(gross),
                'price_return_minus_assumed_cost':str(gross-cost) if known_policy else None,
                'label':int(gross>threshold) if known_policy else None,'original_label_policy_available':known_policy,
                'price_label_policy_source':policy_source}
            digest=hashlib.sha256(json.dumps(semantic,sort_keys=True).encode()).hexdigest()
            if self.path.stat().st_size>=self.maximum_database_mb*1024**2 or shutil.disk_usage(self.path.parent).free<self.minimum_free_disk_mb*1024**2:
                return {'status':'diagnostic_storage_budget_preserved','stored':False}
            db.execute('CREATE TABLE IF NOT EXISTS primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS primary_forecast_outcome_lookup ON primary_forecast_outcomes(forecast,id)')
            old=db.execute('SELECT digest,observed_at FROM primary_forecast_outcomes WHERE forecast=? ORDER BY id DESC LIMIT 1',(forecast_id,)).fetchone()
            if old and time(old[1])>now:raise ValueError('cannot backdate a primary price correction')
            if old and old[0]==digest:return {'status':'original_price_outcome_preserved','stored':False}
            payload={**semantic,'forecast_id':forecast_id,'label_available_at':now.isoformat(),
                'target_information_end':end.isoformat(),'source_kind':'primary_future_candle_return_diagnostic_v1',
                'counts_as_real_executed_buys':False,'realized_cash_pnl_available':False,'live_promotion_allowed':False}
            with db:db.execute('INSERT INTO primary_forecast_outcomes (forecast,digest,observed_at,payload) VALUES (?,?,?,?)',
                (forecast_id,digest,now.isoformat(),json.dumps(payload,sort_keys=True)))
            self.path.chmod(0o600)
            return {'status':'observed_price_outcome_version_recorded','stored':True}
        finally:db.close()

    def available_outcome(self,forecast_id,*,as_of):
        if as_of.tzinfo is None:raise ValueError('aware primary outcome cutoff required')
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='primary_forecast_outcomes'").fetchone():return None
            row=db.execute('SELECT payload FROM primary_forecast_outcomes WHERE forecast=? AND observed_at<=? ORDER BY id DESC LIMIT 1',
                (forecast_id,as_of.astimezone(UTC).isoformat())).fetchone()
            return json.loads(row[0]) if row else None
        finally:db.close()

    def matured_batch(self,*,as_of,limit=400):
        if as_of.tzinfo is None or type(limit) is not int or limit<1:raise ValueError('aware bounded primary outcome batch required')
        if not self.path.exists():return []
        cutoff=as_of.astimezone(UTC);lower=cutoff-timedelta(hours=36)
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'primary_forecasts','primary_forecast_outcomes'}:raise ValueError('isolated primary forecast database required')
            prior='EXISTS(SELECT 1 FROM primary_forecast_outcomes o WHERE o.forecast=f.id),' if 'primary_forecast_outcomes' in tables else ''
            query=f'''SELECT f.id,f.payload FROM primary_forecasts f
                WHERE json_extract(f.payload,'$.target_information_end')<=?
                  AND json_extract(f.payload,'$.target_information_end')>=?
                ORDER BY {prior}json_extract(f.payload,'$.target_information_end'),f.id LIMIT ?'''
            return [{**json.loads(row[1]),'forecast_id':row[0]} for row in db.execute(query,(cutoff.isoformat(),lower.isoformat(),limit))]
        finally:db.close()

    def iter_labeled_asof(self,*,as_of):
        if as_of.tzinfo is None:raise ValueError('aware primary outcome report time required')
        if not self.path.exists():return
        cutoff=as_of.astimezone(UTC);db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='primary_forecast_outcomes'").fetchone():return
            query='''SELECT f.id,f.payload,o.payload FROM primary_forecasts f JOIN primary_forecast_outcomes o
                ON o.id=(SELECT v.id FROM primary_forecast_outcomes v WHERE v.forecast=f.id AND v.observed_at<=?
                         ORDER BY v.id DESC LIMIT 1) WHERE json_extract(f.payload,'$.predicted_at')<=? ORDER BY f.id'''
            for row in db.execute(query,(cutoff.isoformat(),cutoff.isoformat())):
                yield row[0],json.loads(row[1]),json.loads(row[2])
        finally:db.close()
