from datetime import UTC,datetime,timedelta
from cryptoforge.instrument_observation_memory import InstrumentObservationMemory
import pytest

NOW=datetime(2026,10,10,tzinfo=UTC)


def payload():return {'retCode':0,'result':{'category':'spot','list':[
    {'symbol':'ETHUSDT','status':'Trading','lotSizeFilter':{'basePrecision':'.000001','maxMarketOrderQty':'6000'}}]}}


def test_future_capture_is_not_applied_to_earlier_history_and_expires(tmp_path):
    memory=InstrumentObservationMemory(tmp_path,clock=lambda:NOW)
    receipt=memory.remember(payload(),request_started_at=NOW-timedelta(seconds=1),response_observed_at=NOW)
    assert memory.state_at('ETHUSDT',as_of=NOW-timedelta(seconds=1))['status']=='no_prior_observation'
    current=memory.state_at('ETHUSDT',as_of=NOW)
    assert current['instrument']['lotSizeFilter']['maxMarketOrderQty']=='6000'
    assert not current['can_certify_historical_execution']
    assert memory.state_at('ETHUSDT',as_of=NOW+timedelta(hours=2))['status']=='stale_prior_observation'
    assert not memory.state_at('UNKNOWN',as_of=NOW)['absence_proves_delisting']


def test_backdated_or_duplicate_symbol_snapshot_is_not_registered(tmp_path):
    memory=InstrumentObservationMemory(tmp_path,clock=lambda:NOW)
    with pytest.raises(ValueError,match='observation'):memory.remember(payload(),
        request_started_at=NOW-timedelta(minutes=1),response_observed_at=NOW-timedelta(seconds=10))
    data=payload();data['result']['list']*=2
    with pytest.raises(ValueError,match='unique'):memory.remember(data,request_started_at=NOW,response_observed_at=NOW)
    assert not memory.path.exists()


def test_changed_registry_receipt_cannot_claim_complete_historical_rules(tmp_path):
    import sqlite3,json
    memory=InstrumentObservationMemory(tmp_path,clock=lambda:NOW)
    memory.remember(payload(),request_started_at=NOW,response_observed_at=NOW)
    with sqlite3.connect(memory.path) as db:
        row=json.loads(db.execute('select payload from instrument_observations').fetchone()[0])
        row['symbols_observed']=1000
        db.execute('update instrument_observations set payload=?',(json.dumps(row,sort_keys=True),))
    with pytest.raises(ValueError,match='identity'):memory.state_at('ETHUSDT',as_of=NOW)


def test_registry_time_column_cannot_backdate_original_observation(tmp_path):
    import sqlite3
    memory=InstrumentObservationMemory(tmp_path,clock=lambda:NOW)
    memory.remember(payload(),request_started_at=NOW,response_observed_at=NOW)
    with sqlite3.connect(memory.path) as db:
        db.execute('update instrument_observations set observed_at=?',((NOW-timedelta(hours=1)).isoformat(),))
    with pytest.raises(ValueError,match='identity'):memory.state_at('ETHUSDT',as_of=NOW)
