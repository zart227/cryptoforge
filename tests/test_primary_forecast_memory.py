from datetime import UTC,datetime,timedelta
import pytest
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory

NOW=datetime(2026,10,10,12,tzinfo=UTC)


def forecast():
    return {'pair':'ETH/USDT','artifact_sha256':'a'*64,'features':[0.,0.,.01,1.,0.,.5,0.],
        'predicted_at':NOW.isoformat(),'feature_observed_at':(NOW-timedelta(seconds=1)).isoformat(),
        'input_bar_open_time':(NOW-timedelta(minutes=10)).isoformat(),
        'opportunity_bar_open_time':(NOW-timedelta(minutes=5)).isoformat(),
        'input_candle_state':'closed_only','input_contract':{'feature_version':'candle-v1','timeframe':'5m',
            'input_candle_state':'closed_only','calculation_contract':'bounded-window-candle-v1','lookback_candles':120},
        'target_version':'fixed-future-return-v1','horizon_candles':3,'long_probability':.4,
        'short_probability':.6,'baseline_entry_signal':True,'reference_close':'100',
        'min_label_return':0.,'round_trip_cost':0.,'label_policy_known':True}


def test_first_forecast_is_prospective_and_never_a_cash_buy(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    assert memory.record(forecast())['stored']
    updated=forecast();updated['long_probability']=.9
    assert not memory.record(updated)['stored']
    row=memory.rows()[0]
    assert row['long_probability']==.4 and not row['counts_as_real_executed_buys']
    assert row['target_information_end']==(NOW+timedelta(minutes=10)).isoformat()
    assert row['prediction_lead_seconds']==600
    assert memory.path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('change',[{'predicted_at':(NOW-timedelta(seconds=10)).isoformat()},
    {'artifact_sha256':'unverified'},{'features':[float('nan')]*7},{'input_bar_open_time':(NOW-timedelta(hours=1)).isoformat()},
    {'target_version':'spot-long-real-cash-recovery-dust-zero-v1'},{'reference_close':'NaN'}])
def test_invalid_or_retrospective_forecasts_create_no_database(tmp_path,change):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    with pytest.raises(ValueError):memory.record({**forecast(),**change})
    assert not memory.path.exists()


def test_disk_reserve_defers_diagnostics_without_deleting_older_evidence(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=10**15)
    assert memory.record(forecast())['status']=='disk_reserve_preserved'
    assert not memory.path.exists()


def test_price_outcome_waits_for_close_and_late_correction_has_its_own_availability(tmp_path):
    from dataclasses import replace
    from decimal import Decimal as D
    from cryptoforge.supabase_executor import CandleRow
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    receipt=memory.record({**forecast(),'min_label_return':.003,'round_trip_cost':.003})
    candle=CandleRow('ETH/USDT','ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))
    with pytest.raises(ValueError,match='available'):memory.record_outcome(receipt['forecast_id'],candle)
    first=NOW+timedelta(minutes=11);memory.clock=lambda:first
    assert memory.record_outcome(receipt['forecast_id'],candle)['stored']
    assert memory.available_outcome(receipt['forecast_id'],as_of=NOW+timedelta(minutes=10)) is None
    original=memory.available_outcome(receipt['forecast_id'],as_of=first)
    assert original['label']==1 and original['price_return_minus_assumed_cost']=='0.007'
    later=first+timedelta(minutes=1);memory.clock=lambda:later
    assert memory.record_outcome(receipt['forecast_id'],replace(candle,close=D(99)))['stored']
    assert memory.available_outcome(receipt['forecast_id'],as_of=first)==original
    corrected=memory.available_outcome(receipt['forecast_id'],as_of=later)
    assert corrected['label']==0 and not corrected['counts_as_real_executed_buys']
    assert not corrected['realized_cash_pnl_available']


def test_timezone_alias_keeps_one_first_forecast_and_canonical_observation_time(tmp_path):
    from datetime import timezone
    zone=timezone(timedelta(hours=3))
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW.astimezone(zone),minimum_free_disk_mb=0)
    first=memory.record(forecast());alias=forecast()
    for key in ('predicted_at','feature_observed_at','input_bar_open_time','opportunity_bar_open_time'):
        alias[key]=datetime.fromisoformat(alias[key]).astimezone(zone).isoformat()
    second=memory.record(alias)
    assert first['forecast_id']==second['forecast_id'] and not second['stored']
    assert memory.rows()[0]['observed_at']==NOW.isoformat()


def test_missing_original_label_policy_keeps_price_only_and_does_not_infer_zero_cost(tmp_path):
    from decimal import Decimal as D
    from cryptoforge.supabase_executor import CandleRow
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    data=forecast()
    for key in ('label_policy_known','min_label_return','round_trip_cost'):data.pop(key)
    receipt=memory.record(data);as_of=NOW+timedelta(minutes=11);memory.clock=lambda:as_of
    candle=CandleRow('ETH/USDT','ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))
    memory.record_outcome(receipt['forecast_id'],candle)
    row=memory.available_outcome(receipt['forecast_id'],as_of=as_of)
    assert row['gross_candle_return']=='0.01' and row['label'] is None
    assert row['price_return_minus_assumed_cost'] is None and not row['original_label_policy_available']
    later=as_of+timedelta(seconds=1);memory.clock=lambda:later
    memory.record_outcome(receipt['forecast_id'],candle,original_policy={'artifact_sha256':'a'*64,
        'trained_at':(NOW-timedelta(hours=1)).isoformat(),'min_label_return':.003,'round_trip_cost':.003})
    assert memory.available_outcome(receipt['forecast_id'],as_of=as_of)==row
    restored=memory.available_outcome(receipt['forecast_id'],as_of=later)
    assert restored['label']==1 and restored['price_return_minus_assumed_cost']=='0.007'
    assert restored['price_label_policy_source']=='verified_original_artifact_observed_now'
