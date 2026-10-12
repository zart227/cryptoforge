from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
from scripts.collect_primary_forecast_outcomes import original_policy_resolver


def artifact():
    return {'model_family':'pure-python-logistic','feature_version':'candle-v1',
        'trained_at':datetime(2026,10,1,tzinfo=UTC).isoformat(),
        'config':{'timeframe':'5m','horizon_candles':3,'target_version':'fixed-future-return-v1',
                  'min_label_return':.0046,'round_trip_cost':.0046}}


def save(tmp_path,value):
    raw=json.dumps(value).encode();sha=hashlib.sha256(raw).hexdigest()
    path=tmp_path/('pure-python-logistic-original-'+sha[:12]+'.json');path.write_bytes(raw)
    return sha,path


def test_policy_comes_from_matching_full_artifact_hash_not_current_cache(tmp_path):
    sha,path=save(tmp_path,artifact());resolve=original_policy_resolver(tmp_path)
    policy=resolve(sha)
    assert policy['artifact_sha256']==sha and policy['min_label_return']==.0046
    path.write_text('changed')
    assert original_policy_resolver(tmp_path)(sha) is None


def test_cash_or_missing_label_configuration_cannot_relabel_primary_price_targets(tmp_path):
    value=artifact();value['config']['target_version']='spot-long-real-cash-recovery-dust-zero-v1'
    sha,_=save(tmp_path,value);assert original_policy_resolver(tmp_path)(sha) is None
    value=artifact();del value['config']['min_label_return']
    sha,_=save(tmp_path,value);assert original_policy_resolver(tmp_path)(sha) is None
