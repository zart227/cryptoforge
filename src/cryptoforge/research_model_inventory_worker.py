"""Trusted offline replay against the main checkout; never opens a model URI."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from cryptoforge import model_registry, model_training, target_contracts


def stamp(value):
    value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('aware timestamp required')
    return value.astimezone(timezone.utc)


def evaluate(packet):
    now=stamp(packet['observed_at']);age=timedelta(hours=packet['max_age_hours'])
    result={}
    for kind,rows in packet['events'].items():
        if not rows:
            result[kind]={'status':'absent','registry_available':False,'selection_ambiguous':False};continue
        row=rows[0];payload=row['payload'];artifact=payload.get('artifact') or {}
        ambiguous=len(rows)>1 and stamp(rows[0]['occurred_at'])==stamp(rows[1]['occurred_at'])
        class FrozenRegistry(model_registry.ActiveModelRegistry):
            def _latest_event(self,*,event_type='model.active'):
                if event_type!=kind:raise ValueError('wrong event route')
                return {'occurred_at':row['occurred_at'],'payload':payload}
        raw=json.dumps(artifact,indent=2,sort_keys=True).encode()
        checksum=bool(artifact) and hashlib.sha256(raw).hexdigest()==payload.get('artifact_sha256')
        vectors=all(type(artifact.get(k)) is list and len(artifact[k])==len(model_training.FEATURE_NAMES)
            and all(type(x) in (int,float) and math.isfinite(x) for x in artifact[k]) for k in ('weights','means','stds'))
        vectors=vectors and all(x>0 for x in artifact['stds'])
        for prefix in ('short_',):
            if prefix+'weights' in artifact:
                vectors=vectors and type(artifact[prefix+'weights']) is list and len(artifact[prefix+'weights'])==len(model_training.FEATURE_NAMES) and all(type(x) in (int,float) and math.isfinite(x) for x in artifact[prefix+'weights'])
                vectors=vectors and type(artifact.get(prefix+'bias')) in (int,float) and math.isfinite(artifact[prefix+'bias'])
        vectors=vectors and type(artifact.get('bias')) in (int,float) and math.isfinite(artifact['bias'])
        available=False;error=None
        if not ambiguous:
            try:
                registry=FrozenRegistry(None)
                selected=registry.latest(max_age=age,now=now) if kind=='model.active' else registry.latest_candidate(max_age=age,now=now)
                available=selected is not None
            except Exception as exc:error=type(exc).__name__
        config=artifact.get('config') or {};target=None
        try:target=target_contracts.require_artifact_target(artifact,expected_target='fixed-future-return-v1',allow_legacy_price=True)
        except Exception:pass
        def safe_name(value):return value if type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value) else None
        def safe_number(value):return value if type(value) in (int,float) and math.isfinite(value) and abs(value)<=1e9 else None
        def age_seconds(value):
            try:return (now-stamp(value)).total_seconds()
            except Exception:return None
        fields=('timeframe','horizon_candles','lookback_candles','feature_lookback_candles','input_candle_state','feature_calculation_contract')
        declared={k:(safe_name(config[k]) if type(config[k]) is str else safe_number(config[k])) if k in config else None for k in fields}
        result[kind]={'status':'ambiguous' if ambiguous else 'available' if available else 'unavailable',
            'registry_available':available,'selection_ambiguous':ambiguous,'native_error_type':error,
            'event_time':row['occurred_at'],'event_age_seconds':age_seconds(row['occurred_at']),
            'training_age_seconds':age_seconds(artifact.get('trained_at')),
            'model_version':safe_name(artifact.get('model_version')),'artifact_sha256':payload.get('artifact_sha256'),
            'artifact_threshold':safe_number(artifact.get('threshold')),
            'declared_live_eligible':artifact.get('live_eligible') if type(artifact.get('live_eligible')) is bool else None,
            'embedded_checksum_valid':checksum,'numeric_vector_shape_finite':vectors,
            'feature_order_matches':artifact.get('feature_names')==list(model_training.FEATURE_NAMES),
            'model_family_matches':artifact.get('model_family')==model_training.MODEL_FAMILY,
            'target_contract':target,'declared_input_contract':declared,
            'declared_input_field_presence':{k:k in config for k in fields},
            'effective_input_candle_state':declared['input_candle_state'] if 'input_candle_state' in config else 'legacy_asof_snapshot',
            'actual_execution_window_verified':False,'artifact_uri_read':False,'prediction_performed':False}
    return {'schema_version':'research-main-model-replay-v1','events':result,
        'main_model_family':model_training.MODEL_FAMILY,'main_feature_version':model_training.FEATURE_VERSION,
        'main_feature_names':list(model_training.FEATURE_NAMES),'max_age_hours':packet['max_age_hours'],
        'loaded_source_hashes':{n:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for n,m in
            (('model_registry',model_registry),('model_training',model_training),('target_contracts',target_contracts))},
        'model_or_registry_mutated':False,'live_executor_run':False,'prediction_performed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    raw=args.input.read_bytes()
    if len(raw)>1048576:raise ValueError('bounded snapshot required')
    result=evaluate(json.loads(raw))
    raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(raw)>32000:raise ValueError('bounded inventory required')
    import os
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


if __name__=='__main__':main()
