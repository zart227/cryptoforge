from datetime import UTC,datetime,timedelta
from dataclasses import replace
import json
import pytest
from cryptoforge.feature_migration_study import FeatureMigrationStudy
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.model_training import FEATURE_NAMES
from test_trade_simulator import history

NOW=datetime(2026,10,12,tzinfo=UTC)


def setup(tmp_path):
    clock=[NOW];study=FeatureMigrationStudy(tmp_path/'migration.sqlite',clock=lambda:clock[0])
    artifact={'model_family':'pure-python-logistic','target_version':'fixed-future-return-v1',
        'feature_names':list(FEATURE_NAMES),'model_version':'test','trained_at':(NOW-timedelta(hours=1)).isoformat(),
        'pairs':['ETH/USDT'],'weights':[0.]*7,'means':[0.]*7,'stds':[1.]*7,'bias':0.,
        'config':{'target_version':'fixed-future-return-v1','timeframe':'5m','input_candle_state':'closed_only',
            'feature_calculation_contract':'bounded-window-candle-v1','feature_lookback_candles':120,
            'horizon_candles':3,'min_label_return':.003,'round_trip_cost':.003}}
    raw=json.dumps(artifact).encode();receipt=study.freeze(version='test-v1',artifact_raw=raw,pairs=['ETH/USDT'])
    memory=PrimaryForecastMemory(tmp_path/receipt['protocol_sha256']/'price-forecasts.sqlite',clock=lambda:clock[0],minimum_free_disk_mb=0)
    rows=[replace(row,open_time=NOW-timedelta(minutes=5*(120-index))) for index,row in enumerate(history(count=120))]
    return study,receipt,memory,rows,clock,raw


def test_observed_frozen_model_comparison_records_only_price_endpoints(tmp_path):
    study,receipt,memory,rows,clock,raw=setup(tmp_path)
    assert receipt==study.freeze(version='test-v1',artifact_raw=raw,pairs=['ETH/USDT'])
    result=study.record(receipt,rows,source_observed_at=NOW,memory=memory)
    assert result['stored']
    forecast=memory.rows()[0]
    assert forecast['migration_protocol_sha256']==receipt['protocol_sha256']
    assert not forecast['counts_as_real_executed_buys'] and not forecast['live_promotion_allowed']
    assert not study.record(receipt,rows,source_observed_at=NOW,memory=memory)['stored']


def test_pre_freeze_old_inputs_and_shared_memory_are_rejected(tmp_path):
    study,receipt,memory,rows,clock,raw=setup(tmp_path)
    with pytest.raises(ValueError,match='post-freeze'):
        study.record(receipt,rows,source_observed_at=NOW-timedelta(seconds=1),memory=memory)
    old=[replace(row,open_time=row.open_time-timedelta(days=1)) for row in rows]
    with pytest.raises(ValueError,match='stale'):study.record(receipt,old,source_observed_at=NOW,memory=memory)
    other=PrimaryForecastMemory(tmp_path/'global.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    with pytest.raises(ValueError,match='namespace'):study.record(receipt,rows,source_observed_at=NOW,memory=other)


def test_frozen_version_cannot_change_candidate_weights(tmp_path):
    study,receipt,memory,rows,clock,raw=setup(tmp_path)
    changed=json.loads(raw);changed['bias']=1.
    with pytest.raises(ValueError,match='cannot change'):
        study.freeze(version='test-v1',artifact_raw=json.dumps(changed).encode(),pairs=['ETH/USDT'])


def test_pre_freeze_signal_close_is_not_a_new_independent_observation(tmp_path):
    study,receipt,memory,rows,clock,raw=setup(tmp_path)
    shifted=[replace(row,open_time=row.open_time-timedelta(minutes=1)) for row in rows]
    with pytest.raises(ValueError,match='precedes observed freeze'):
        study.record(receipt,shifted,source_observed_at=NOW,memory=memory)


def test_future_price_endpoint_remains_non_cash_training_evidence(tmp_path):
    study,receipt,memory,rows,clock,raw=setup(tmp_path)
    study.record(receipt,rows,source_observed_at=NOW,memory=memory)
    forecast=memory.rows()[0];clock[0]=NOW+timedelta(minutes=15)
    endpoint=replace(rows[-1],open_time=NOW+timedelta(minutes=10),close=rows[-1].close+1,
                     high=rows[-1].high+1,cache_observed_at=clock[0])
    memory.record_outcome(forecast['forecast_id'],endpoint)
    labeled=list(memory.iter_labeled_asof(as_of=clock[0]))
    assert len(labeled)==1
    assert not labeled[0][1]['counts_as_real_executed_buys']
