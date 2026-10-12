from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.closed_timeframes import aggregate_closed
from test_trade_simulator import history


def test_hour_is_available_only_at_close_and_preserves_ohlcv():
    rows=history(count=24);start=rows[0].open_time
    candles,report=aggregate_closed(rows,as_of=start+timedelta(minutes=59),minutes=60)
    assert not candles
    candles,report=aggregate_closed(rows,as_of=start+timedelta(hours=1),minutes=60)
    assert len(candles)==1 and candles[0].open_time==start
    assert candles[0].open==rows[0].open and candles[0].close==rows[11].close
    assert candles[0].volume==sum((row.volume for row in rows[:12]),D(0))
    assert not report['missing_data_filled']


def test_missing_base_candle_and_partial_first_bucket_are_not_filled():
    rows=history(count=24);as_of=rows[0].open_time+timedelta(hours=2)
    candles,report=aggregate_closed(rows[:4]+rows[5:],as_of=as_of,minutes=60)
    assert len(candles)==1 and len(report['incomplete_buckets'])==1
    candles,report=aggregate_closed(rows[6:],as_of=as_of,minutes=60)
    assert len(candles)==1 and len(report['incomplete_buckets'])==1


def test_future_price_changes_do_not_change_closed_higher_timeframe():
    rows=history(count=24);as_of=rows[0].open_time+timedelta(hours=1)
    before=aggregate_closed(rows,as_of=as_of,minutes=15)[0]
    changed=rows[:12]+[replace(row,open=D(200),close=D(200),high=D(201),low=D(199)) for row in rows[12:]]
    assert aggregate_closed(changed,as_of=as_of,minutes=15)[0]==before
    with pytest.raises(ValueError,match='unique'):aggregate_closed(rows[:12]+[rows[5]],as_of=as_of,minutes=60)
    with pytest.raises(ValueError,match='identity'):aggregate_closed([rows[0],replace(rows[1],pair='BTC/USDT')],as_of=as_of,minutes=60)



def test_future_incomplete_or_wrong_market_rows_do_not_affect_past_buckets():
    rows=history(count=24);as_of=rows[0].open_time+timedelta(hours=1)
    known=aggregate_closed(rows[:12],as_of=as_of,minutes=60)[0]
    future=replace(rows[15],pair='UNKNOWN/USDT',open=D(-1))
    assert aggregate_closed(rows[:12]+[future,future],as_of=as_of,minutes=60)[0]==known


def test_cache_captured_before_base_close_cannot_complete_an_hour():
    rows=history(count=12);as_of=rows[0].open_time+timedelta(hours=2)
    rows[-1]=replace(rows[-1],cache_observed_at=rows[-1].open_time+timedelta(minutes=1))
    candles,report=aggregate_closed(rows,as_of=as_of,minutes=60)
    assert not candles and len(report['incomplete_buckets'])==1


def test_hour_keeps_late_base_revision_observation_time():
    from cryptoforge.candle_contract import closed_snapshot
    rows=history(count=24);start=rows[0].open_time;revision=start+timedelta(hours=2)
    rows[0]=replace(rows[0],cache_observed_at=revision)
    hours,_=aggregate_closed(rows,as_of=revision,minutes=60)
    assert hours[0].cache_observed_at==revision
    assert closed_snapshot(hours,timeframe='1h',as_of=start+timedelta(hours=1))==[]
