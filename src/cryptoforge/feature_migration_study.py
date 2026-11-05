"""Observed prospective feature comparison; never publishes or submits orders."""
from datetime import UTC,datetime,timedelta
import hashlib,json,math,sqlite3,shutil
from dataclasses import asdict
from pathlib import Path
from cryptoforge.candle_contract import closed_snapshot
from cryptoforge.model_training import FEATURE_NAMES,extract_features,predict_probability
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.supabase_executor import entry_signal
from cryptoforge.target_contracts import require_artifact_target
from cryptoforge.training_snapshot import _save_raw,save_runtime_sources,load_runtime_sources
from cryptoforge.market_data import BybitPublicClient


def dependencies():
    return {'migration':FeatureMigrationStudy,'features':extract_features,'predict':predict_probability,
        'closed_contract':closed_snapshot,'baseline':entry_signal,'target':require_artifact_target,
        'forecast_memory':PrimaryForecastMemory,'source_manifest':source_hashes,'input_capture':_save_raw,
        'market_client':BybitPublicClient,'collector_runner':Path(__file__).resolve().parents[2]/'scripts/collect_feature_migration.py'}


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


class FeatureMigrationStudy:
    def __init__(self,path,*,clock=None):
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))

    def freeze(self,*,version,artifact_raw,pairs,threshold=.5):
        now=self.clock()
        if now.tzinfo is None or not version or threshold!=.5:raise ValueError('aware observed freeze and fixed threshold0.5 required')
        artifact=json.loads(artifact_raw);require_artifact_target(artifact,expected_target='fixed-future-return-v1')
        config=artifact['config']
        expected={'timeframe':'5m','input_candle_state':'closed_only','feature_calculation_contract':'bounded-window-candle-v1','feature_lookback_candles':120,'horizon_candles':3}
        if any(config.get(key)!=value for key,value in expected.items()):raise ValueError('explicit closed bounded120 price contract required')
        if artifact.get('model_family')!='pure-python-logistic' or artifact.get('feature_names')!=list(FEATURE_NAMES):
            raise ValueError('supported frozen primary model required')
        for key in ('weights','means','stds'):
            values=artifact[key]
            if len(values)!=7 or not all(math.isfinite(value) for value in values) or (key=='stds' and min(values)<=0):
                raise ValueError('finite seven-feature model required')
        if not math.isfinite(artifact['bias']):raise ValueError('finite model bias required')
        trained=datetime.fromisoformat(artifact['trained_at'])
        if trained.tzinfo is None or not timedelta(0)<=now-trained<=timedelta(hours=36):
            raise ValueError('fresh model required at initial freeze')
        for key,limit in (('fit_information_end',trained),('evaluation_information_end',now)):
            if key in config:
                stamp=datetime.fromisoformat(config[key])
                if stamp.tzinfo is None or stamp>limit:raise ValueError('unavailable model information at migration freeze')
        if not pairs or len(set(pairs))!=len(pairs) or not set(pairs)<=set(artifact['pairs']):
            raise ValueError('explicit fixed trained-pair basket required')
        policy={key:config[key] for key in ('min_label_return','round_trip_cost')}
        if any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<1 for value in policy.values()):
            raise ValueError('explicit original candle label/cost policy required')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=5)
        try:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'migration_freezes'}:raise ValueError('isolated migration registry required')
            db.execute('CREATE TABLE IF NOT EXISTS migration_freezes (version TEXT PRIMARY KEY,sha TEXT UNIQUE,payload TEXT) WITHOUT ROWID')
            prior=db.execute('SELECT payload FROM migration_freezes WHERE version=?',(version,)).fetchone()
            if prior:
                receipt=json.loads(prior[0]);p=receipt['protocol']
                if (p['artifact_sha256']!=hashlib.sha256(artifact_raw).hexdigest() or p['pairs']!=sorted(pairs)
                        or p['threshold']!=threshold or p['implementation_hashes']!=source_hashes(dependencies())):
                    raise ValueError('observed migration version cannot change')
                return receipt
            hashes=source_hashes(dependencies())
            runtime=save_runtime_sources(self.path.parent/'runtime',dependencies(),hashes)
            protocol={'schema_version':'prospective-feature-comparison-v1','protocol_version':version,
                'observed_at':now.isoformat(),'artifact_sha256':hashlib.sha256(artifact_raw).hexdigest(),
                'artifact_payload':artifact_raw.decode(),'pairs':sorted(pairs),'threshold':threshold,
                'input_contract':expected,'label_policy':policy,'implementation_hashes':hashes,'runtime_source_bundle':runtime,
                'control':'same_bounded120_strategy_without_ML','baseline_flags':{'allow_intraday_reversion':True,'allow_emerging_momentum':True},
                'legacy_incumbent_contract_reconstructed':False,'model_updates_allowed':False,
                'model_freshness_scope':'initial_freeze_only_research_frozen_model_live_freshness_unchanged',
                'scope':'future_price_endpoints_not_executed_cash_or_live_admission','live_promotion_allowed':False}
            sha=hashlib.sha256(encode(protocol).encode()).hexdigest();receipt={'protocol_sha256':sha,'protocol':protocol}
            with db:db.execute('INSERT INTO migration_freezes VALUES (?,?,?)',(version,sha,encode(receipt)))
            self.path.chmod(0o600);return receipt
        finally:db.close()

    def verified_protocol(self,receipt):
        p=receipt['protocol']
        if hashlib.sha256(encode(p).encode()).hexdigest()!=receipt['protocol_sha256']:raise ValueError('migration receipt changed')
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:row=db.execute('SELECT payload FROM migration_freezes WHERE sha=?',(receipt['protocol_sha256'],)).fetchone()
        finally:db.close()
        if row is None or row[0]!=encode(receipt):raise ValueError('observed migration receipt unavailable')
        assert_source_dependencies(p['implementation_hashes'],dependencies())
        load_runtime_sources(p['runtime_source_bundle'],p['implementation_hashes'])
        return p

    def record(self,receipt,candles,*,source_observed_at,memory):
        now=self.clock();p=self.verified_protocol(receipt)
        expected_path=self.path.parent/receipt['protocol_sha256']/'price-forecasts.sqlite'
        if memory.path.resolve()!=expected_path.resolve():raise ValueError('isolated migration forecast namespace required')
        frozen=datetime.fromisoformat(p['observed_at'])
        if source_observed_at.tzinfo is None or not frozen<=source_observed_at<=now or now-source_observed_at>timedelta(seconds=5):
            raise ValueError('fresh post-freeze source observation required')
        rows=closed_snapshot(candles,timeframe='5m',as_of=source_observed_at)
        if len(rows)<120:raise ValueError('complete closed120 window required')
        rows=rows[-120:];pair=rows[-1].pair
        if pair not in p['pairs'] or any(row.pair!=pair or row.symbol!=pair.replace('/','') for row in rows):
            raise ValueError('frozen pair identity required')
        for candle in rows:
            if not all(value.is_finite() for value in (candle.open,candle.high,candle.low,candle.close,candle.volume)) or not (
                0<candle.low<=min(candle.open,candle.close)<=max(candle.open,candle.close)<=candle.high and candle.volume>=0):
                raise ValueError('valid closed input required')
        if now-(rows[-1].open_time+timedelta(minutes=5))>timedelta(minutes=5):raise ValueError('stale migration input')
        if rows[-1].open_time+timedelta(minutes=5)<frozen:raise ValueError('migration signal bar precedes observed freeze')
        a=json.loads(p['artifact_payload']);features=extract_features(rows,[row.volume for row in rows])
        probability=predict_probability(features,a['weights'],a['bias'],a['means'],a['stds'])
        baseline,_=entry_signal(rows,**p['baseline_flags']);bar=rows[-1].open_time.isoformat()
        if shutil.disk_usage(self.path.parent).free<(memory.minimum_free_disk_mb+2)*1024**2:
            return {'status':'disk_reserve_preserved','stored':False}
        raw=json.dumps({'rows':[asdict(row) for row in rows],'source_observed_at':source_observed_at.isoformat()},
                       default=str,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        reference=_save_raw(expected_path.parent/'input-windows',raw)
        forecast={'artifact_sha256':p['artifact_sha256'],'model_version':a['model_version'],'pair':pair,
            'predicted_at':now.isoformat(),'feature_observed_at':source_observed_at.isoformat(),
            'features':list(features),'input_contract':{'feature_version':'candle-v1','timeframe':'5m','input_candle_state':'closed_only',
                'calculation_contract':'bounded-window-candle-v1','lookback_candles':120},
            'input_candle_state':'closed_only','opportunity_bar_open_time':bar,'input_bar_open_time':bar,
            'target_version':'fixed-future-return-v1','horizon_candles':3,'reference_close':str(rows[-1].close),
            'long_probability':probability,'short_probability':None,'baseline_entry_signal':baseline,
            'label_policy_known':True,**p['label_policy'],'migration_protocol_sha256':receipt['protocol_sha256'],
            'paired_candidate_entry_signal':baseline and probability>=p['threshold'],
            'input_window_snapshot':reference,'income_established':False}
        return memory.record(forecast)
