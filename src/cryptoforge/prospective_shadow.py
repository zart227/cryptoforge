"""Pre-trade predictions on factual bot opportunities; no simulated fills/orders."""
from datetime import UTC,datetime,timedelta
import hashlib
import json
from math import isfinite
from pathlib import Path
import sqlite3

from cryptoforge.live_learning_protocol import time
from cryptoforge.model_training import predict_probability


def validate_candidate(manifest,artifact,protocol,*,now):
    if manifest['protocol_version']!=protocol['protocol_version']:
        raise ValueError('candidate protocol mismatch')
    if manifest.get('live_eligible') is not False or artifact.get('live_eligible') is not False:
        raise ValueError('shadow candidate must not be live eligible')
    from cryptoforge.cash_training import FEATURE_NAMES
    if artifact.get('feature_names')!=FEATURE_NAMES:raise ValueError('candidate feature ordering mismatch')
    if artifact.get('threshold') is None or not isfinite(float(artifact['threshold'])) or float(artifact['threshold'])!=float(manifest['threshold']):
        raise ValueError('candidate artifact threshold differs from selected threshold')
    if artifact.get('model_family')!=protocol['configuration_budget']['model_family']:
        raise ValueError('candidate model family mismatch')
    if str(artifact.get('selected_l2')) not in protocol['configuration_budget']['l2_values']:
        raise ValueError('candidate regularization was not preregistered')
    config=artifact['config']
    if config.get('feature_input_contract')!=protocol.get('feature_input_contract'):
        raise ValueError('candidate feature calculation contract differs from protocol')
    if (config.get('target_version')!=protocol['target_version'] or
        config.get('input_candle_state')!=protocol['input_candle_state'] or
        artifact.get('feature_version')!=protocol['feature_version']):
        raise ValueError('candidate feature/input/target mismatch')
    selection=time(manifest['selected_at']);trained=time(artifact['trained_at'])
    selection_end=time(protocol['windows']['validation']['end_exclusive'])
    first_test=time(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    if not selection_end<=selection<first_test or not trained<=selection<=now:
        raise ValueError('candidate was not frozen before eligible test opportunities')
    if time(config['fit_information_end'])>selection_end-timedelta(seconds=protocol['embargo_seconds']):
        raise ValueError('candidate uses post-selection information')
    if trained<time(config['fit_information_end']):raise ValueError('candidate trained before its information was available')
    if manifest.get('threshold') not in protocol['configuration_budget']['thresholds']:
        raise ValueError('unregistered decision threshold')
    for field in ('weights','means','stds'):
        values=artifact[field]
        if len(values)!=7 or not all(isfinite(float(v)) for v in values):raise ValueError('invalid candidate coefficients')
    if any(float(v)<=0 for v in artifact['stds']) or not isfinite(float(artifact['bias'])):
        raise ValueError('invalid candidate standardizer or bias')


class ShadowLedger:
    def __init__(self,path: Path,*,clock=None):
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))

    def _connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=1)
        db.execute('CREATE TABLE IF NOT EXISTS predictions (candidate_sha TEXT, opportunity TEXT, pair TEXT NOT NULL, predicted_at TEXT NOT NULL, payload TEXT NOT NULL, order_id TEXT, bound_at TEXT, causal_link TEXT, PRIMARY KEY(candidate_sha,opportunity)) WITHOUT ROWID')
        columns={row[1] for row in db.execute('PRAGMA table_info(predictions)')}
        if 'causal_link' not in columns:db.execute('ALTER TABLE predictions ADD COLUMN causal_link TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_candidate_order ON predictions(candidate_sha,order_id) WHERE order_id IS NOT NULL')
        db.execute('CREATE TABLE IF NOT EXISTS candidate_freezes (manifest_sha TEXT PRIMARY KEY, candidate_sha TEXT NOT NULL, protocol_sha TEXT NOT NULL, registered_at TEXT NOT NULL, payload TEXT NOT NULL) WITHOUT ROWID')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_frozen_candidate_per_protocol ON candidate_freezes(protocol_sha)')
        db.execute('CREATE TABLE IF NOT EXISTS paper_policy_freezes (protocol_sha TEXT PRIMARY KEY,candidate_sha TEXT,policy_sha TEXT,observed_at TEXT,payload TEXT) WITHOUT ROWID')
        self.path.chmod(0o600);return db

    def freeze_candidate(self,manifest_bytes,*,registered_at):
        manifest=json.loads(manifest_bytes)
        observed=self.clock()
        if observed.tzinfo is None or abs((observed-registered_at).total_seconds())>5:
            raise ValueError('cannot register a candidate retrospectively')
        if registered_at.tzinfo is None or time(manifest['selected_at'])!=registered_at:
            raise ValueError('candidate registration must use actual selection time')
        digest=hashlib.sha256(manifest_bytes).hexdigest();db=self._connect()
        try:
            with db:db.execute('INSERT INTO candidate_freezes VALUES (?,?,?,?,?)',
                (digest,manifest['artifact_sha256'],manifest['protocol_sha256'],observed.isoformat(),manifest_bytes.decode()))
        finally:db.close()
        return digest

    def freeze_paper_policy(self,raw,*,protocol_sha,candidate_sha):
        observed=self.clock()
        if observed.tzinfo is None:raise ValueError('timezone-aware paper policy freeze required')
        digest=hashlib.sha256(raw).hexdigest();db=self._connect()
        try:
            with db:db.execute('INSERT INTO paper_policy_freezes VALUES (?,?,?,?,?)',
                (protocol_sha,candidate_sha,digest,observed.isoformat(),raw.decode()))
        finally:db.close()
        return {'protocol_sha256':protocol_sha,'candidate_sha256':candidate_sha,
                'policy_sha256':digest,'observed_at':observed.isoformat()}

    def frozen_paper_policy(self,protocol_sha):
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:row=db.execute('SELECT candidate_sha,policy_sha,observed_at,payload FROM paper_policy_freezes WHERE protocol_sha=?',(protocol_sha,)).fetchone()
        finally:db.close()
        if not row:return None
        return row[3].encode(),{'protocol_sha256':protocol_sha,'candidate_sha256':row[0],
            'policy_sha256':row[1],'observed_at':row[2]}

    def verify_paper_policy(self,raw,receipt):
        if not self.path.exists():raise ValueError('paper policy has no observed registration')
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:row=db.execute('SELECT candidate_sha,policy_sha,observed_at,payload FROM paper_policy_freezes WHERE protocol_sha=?',
                           (receipt['protocol_sha256'],)).fetchone()
        finally:db.close()
        expected=(receipt['candidate_sha256'],receipt['policy_sha256'],receipt['observed_at'],raw.decode())
        if row!=expected or hashlib.sha256(raw).hexdigest()!=receipt['policy_sha256']:
            raise ValueError('paper policy receipt differs from observed immutable freeze')

    def frozen_manifest(self,protocol_sha):
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:row=db.execute('SELECT payload FROM candidate_freezes WHERE protocol_sha=?',(protocol_sha,)).fetchone()
        finally:db.close()
        return row[0].encode() if row else None

    def verify_freeze(self,manifest_bytes):
        if not self.path.exists():raise ValueError('candidate has no observed registration')
        digest=hashlib.sha256(manifest_bytes).hexdigest()
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:row=db.execute('SELECT registered_at,payload FROM candidate_freezes WHERE manifest_sha=?',(digest,)).fetchone()
        finally:db.close()
        if not row or row[1]!=manifest_bytes.decode():raise ValueError('candidate manifest was not frozen or has changed')
        return time(row[0])

    def record(self,*,candidate_sha,opportunity,pair,features,feature_observed_at,input_state,
               probability,threshold,predicted_at,feature_input_contract=None):
        observed=self.clock()
        if predicted_at.tzinfo is None or observed.tzinfo is None or abs((observed-predicted_at).total_seconds())>5:
            raise ValueError('cannot record a prediction retrospectively')
        if predicted_at.tzinfo is None or feature_observed_at.tzinfo is None or feature_observed_at>predicted_at:
            raise ValueError('features must be known before prediction')
        if len(features)!=7 or not all(isfinite(float(v)) for v in features):raise ValueError('invalid observed features')
        if not isfinite(probability) or not 0<=probability<=1 or not 0<=threshold<=1:
            raise ValueError('invalid probability or threshold')
        payload={'candidate_sha256':candidate_sha,'opportunity':opportunity,'pair':pair,
            **({'feature_input_contract':feature_input_contract} if feature_input_contract is not None else {}),
            'features':list(features),'feature_observed_at':feature_observed_at.isoformat(),
            'input_candle_state':input_state,'probability':probability,'threshold':threshold,
            'would_enter':probability>=threshold,'baseline_would_enter':True,
            'predicted_at':predicted_at.isoformat(),'observed_at':observed.isoformat(),'fill_model':'none_factual_cohort_only'}
        db=self._connect()
        try:
            previous=db.execute('SELECT payload FROM predictions WHERE candidate_sha=? AND opportunity=?',
                                (candidate_sha,opportunity)).fetchone()
            if previous:
                prior=json.loads(previous[0]);prior.pop('observed_at',None)
                current={key:value for key,value in payload.items() if key!='observed_at'}
                if prior!=current:raise ValueError('cannot overwrite an existing prospective prediction')
                return False
            with db:db.execute('INSERT INTO predictions (candidate_sha,opportunity,pair,predicted_at,payload) VALUES (?,?,?,?,?)',
                (candidate_sha,opportunity,pair,predicted_at.astimezone(UTC).isoformat(),json.dumps(payload,sort_keys=True)))
            return True
        finally:db.close()

    def bind_order(self,candidate_sha,opportunity,order_id,*,bound_at,order_link_id=None):
        if bound_at.tzinfo is None:raise ValueError('timezone-aware binding time required')
        if order_link_id is not None and str(order_link_id)!=opportunity:
            raise ValueError('broker order link does not match recorded opportunity')
        db=self._connect()
        try:
            row=db.execute('SELECT predicted_at,order_id FROM predictions WHERE candidate_sha=? AND opportunity=?',
                           (candidate_sha,opportunity)).fetchone()
            if not row or time(row[0])>bound_at:raise ValueError('prediction must exist before order binding')
            if row[1] and row[1]!=str(order_id):raise ValueError('cannot rebind a prediction to another order')
            with db:db.execute('UPDATE predictions SET order_id=?,bound_at=COALESCE(bound_at,?),causal_link=COALESCE(causal_link,?) WHERE candidate_sha=? AND opportunity=?',
                (str(order_id),bound_at.isoformat(),order_link_id,candidate_sha,opportunity))
        finally:db.close()

    def rows(self):
        if not self.path.exists():return []
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:return [{**json.loads(payload),'order_id':order,'bound_at':bound,'causal_order_link_id':link} for payload,order,bound,link in
                    db.execute('SELECT payload,order_id,bound_at,causal_link FROM predictions ORDER BY predicted_at,candidate_sha,opportunity')]
        finally:db.close()


class LocalShadowObserver:
    """An absent candidate is inert. Errors are diagnostics and never a trade gate."""
    def __init__(self,manifest_path=Path('.local/state/cash-shadow-candidate.json'),
                 ledger_path=Path('.local/state/cash-shadow-predictions.sqlite'),*,protocol_path=None,use_study_namespace=False):
        self.manifest_path=manifest_path;self.ledger=ShadowLedger(ledger_path);self.protocol_path=protocol_path
        self.use_study_namespace=use_study_namespace

    @classmethod
    def from_env(cls):
        import os
        path=os.environ.get('CRYPTOFORGE_CASH_SHADOW_PROTOCOL')
        return cls(protocol_path=Path(path),use_study_namespace=True) if path else cls()

    def before_buy(self,*,pair,opportunity,model_input,feature_observed_at,now=None):
        if self.use_study_namespace:
            from cryptoforge.cash_study_paths import load_cash_study
            from cryptoforge.cash_study_registry import require_collection_freeze
            _,study=load_cash_study(self.protocol_path);require_collection_freeze(study)
            self.manifest_path=study.candidate;self.ledger=ShadowLedger(study.predictions)
        if not self.manifest_path.exists():return None
        from cryptoforge.live_learning_protocol import load_protocol
        now=now or datetime.now(UTC)
        manifest_bytes=self.manifest_path.read_bytes()
        registered_at=self.ledger.verify_freeze(manifest_bytes)
        manifest=json.loads(manifest_bytes)
        protocol_path=self.protocol_path or Path(manifest.get('protocol_path','config/live-cash-recovery-protocol-v1.json'))
        from cryptoforge.cash_study_paths import load_cash_study
        from cryptoforge.cash_study_registry import require_collection_freeze
        protocol,study=load_cash_study(protocol_path);require_collection_freeze(study)
        first_test=time(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds'])
        if not time(manifest['selected_at'])<=registered_at<=now or registered_at>=first_test:
            raise ValueError('unverified or late actual candidate registration')
        if manifest['protocol_sha256']!=study.protocol_sha256:
            raise ValueError('candidate frozen protocol checksum mismatch')
        artifact_bytes=Path(manifest['artifact_path']).read_bytes()
        digest=hashlib.sha256(artifact_bytes).hexdigest()
        if digest!=manifest['artifact_sha256']:raise ValueError('candidate artifact checksum mismatch')
        artifact=json.loads(artifact_bytes);validate_candidate(manifest,artifact,protocol,now=now)
        if not model_input or model_input['pair']!=pair or model_input['state']!=protocol['input_candle_state']:
            raise ValueError('current opportunity has incompatible input state')
        if protocol.get('feature_input_contract') is not None and model_input.get('input_contract')!=protocol['feature_input_contract']:
            raise ValueError('current opportunity has incompatible feature calculation contract')
        eligible=any(time(protocol['windows'][split]['start'])+timedelta(seconds=protocol['embargo_seconds'])<=now<
                     time(protocol['windows'][split]['end_exclusive']) for split in ('sealed_test','paper'))
        if not eligible:return None
        values=tuple(float(v) for v in model_input['values'])
        probability=predict_probability(values,[float(v) for v in artifact['weights']],float(artifact['bias']),
                                        [float(v) for v in artifact['means']],[float(v) for v in artifact['stds']])
        self.ledger.record(candidate_sha=digest,opportunity=opportunity,pair=pair,features=values,
            feature_observed_at=feature_observed_at,input_state=model_input['state'],probability=probability,
            threshold=float(manifest['threshold']),predicted_at=now,
            feature_input_contract=model_input.get('input_contract'))
        return {'candidate_sha256':digest,'opportunity':opportunity,'probability':probability,'recorded_at':now.isoformat()}

    def after_buy(self,receipt,order):
        if not receipt:return
        result=(order or {}).get('result') or {};order_id=result.get('orderId')
        if order.get('retCode',0)!=0 or not order_id:return
        self.ledger.bind_order(receipt['candidate_sha256'],receipt['opportunity'],order_id,bound_at=datetime.now(UTC),order_link_id=result.get('orderLinkId'))


def compare_factual_cohort(predictions,outcomes,protocol,*,candidate_sha,split,as_of):
    """Conditional ranking of executed baseline buys; no portfolio/counterfactual PnL."""
    from decimal import Decimal
    window=protocol['windows'][split]
    start=time(window['start'])+timedelta(seconds=protocol['embargo_seconds'])
    end=time(window['end_exclusive']);cutoff=end-timedelta(seconds=protocol['embargo_seconds'])
    selected=[row for row in predictions if row['candidate_sha256']==candidate_sha
              and start<=time(row['predicted_at'])<end]
    result={'split':split,'candidate_sha256':candidate_sha,'recorded_opportunities':len(selected),
            'full_paper_execution_harness_implemented':False,'live_promotion_allowed':False,
            'scope':'conditional_factual_executed_baseline_buys_no_counterfactual_fills_or_reallocation'}
    if as_of<end:
        return {**result,'status':'sealed_until_window_end','performance_hidden':True}
    by_order={}
    for row in outcomes:
        key=(row['pair'],row['entry_order'])
        if key in by_order:raise ValueError('duplicate buy outcome versions')
        by_order[key]=row
    matched=[];excluded=[];used=set()
    for prediction in selected:
        key=(prediction['pair'],prediction.get('order_id'))
        if not prediction.get('order_id'):
            excluded.append('not_bound_to_factual_buy');continue
        if key in used:raise ValueError('duplicate factual order binding')
        used.add(key);outcome=by_order.get(key)
        if not outcome:
            excluded.append('no_available_verified_outcome');continue
        example=outcome['example']
        required_contract=protocol.get('feature_input_contract')
        if (required_contract is not None and (prediction.get('feature_input_contract')!=required_contract
            or outcome.get('feature_input_contract')!=required_contract)) or (
            prediction.get('feature_input_contract') is not None
            and prediction['feature_input_contract']!=outcome.get('feature_input_contract')):
            excluded.append('incompatible_feature_calculation_contract');continue
        if not prediction.get('observed_at'):
            excluded.append('prospective_record_observation_time_unknown');continue
        causal_request_proof=prediction.get('causal_order_link_id')==prediction['opportunity']
        if ((not causal_request_proof and time(prediction['predicted_at'])>time(outcome['entry_at'])) or
            time(outcome['label_available_at'])>min(cutoff,as_of) or
            outcome['input_candle_state']!=prediction['input_candle_state'] or
            tuple(float(v) for v in example['features'])!=tuple(float(v) for v in prediction['features']) or
            time(example['open_time'])!=time(prediction['feature_observed_at'])):
            excluded.append('late_prediction_or_incompatible_evidence');continue
        if outcome['target_version']!=protocol['target_version']:
            excluded.append('incompatible_target');continue
        pnl=Decimal(outcome['cash_recovery_net'])
        if not pnl.is_finite():raise ValueError('nonfinite factual outcome')
        matched.append((prediction,pnl))
    baseline=sum((pnl for _,pnl in matched),Decimal(0))
    accepted=[pnl for prediction,pnl in matched if prediction['would_enter']]
    rejected=[pnl for prediction,pnl in matched if not prediction['would_enter']]
    return {**result,'status':'factual_cohort_diagnostic_only','performance_hidden':False,
        'matched_factual_buys':len(matched),'unmatched_reasons':excluded,
        'all_bound_factual_buys_resolved':len(matched)==sum(bool(row.get('order_id')) for row in selected),
        'baseline_factual_cash_recovery':str(baseline),
        'candidate_accepted_factual_cash_recovery':str(sum(accepted,Decimal(0))),
        'candidate_rejected_factual_cash_recovery':str(sum(rejected,Decimal(0))),
        'accepted_buys':len(accepted),'rejected_buys':len(rejected),
        'profitability_established':False,'portfolio_income_claim_allowed':False}
