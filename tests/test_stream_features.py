from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.stream_features import ClosedFeatureStream
from cryptoforge.model_training import build_examples
from test_trade_simulator import history


def candles():
    return [replace(row,open=D(100)+D(i)/100,close=D(100)+D(i+1)/100,
        high=D(101)+D(i)/100,low=D(99)+D(i)/100,volume=D(100+i%13))
        for i,row in enumerate(history(count=170))]


def test_stream_matches_bounded_archive_examples_exactly_and_keeps_memory_bounded():
    rows=candles();stream=ClosedFeatureStream('ETH/USDT');outputs={}
    for row in rows:
        result=stream.push(row,as_of=row.open_time+timedelta(minutes=5))
        if result:outputs[row.open_time]=result
    batch=build_examples('ETH/USDT',rows,horizon_candles=3,feature_lookback_candles=120)
    assert batch and all(outputs[row.open_time].features==row.features for row in batch)
    assert len(stream.rows)==120
    assert all(value.available_at<=value.computed_at for value in outputs.values())


def test_partial_duplicate_gap_and_wrong_market_do_not_advance_stream():
    rows=candles();stream=ClosedFeatureStream('ETH/USDT');stream.push(rows[0],as_of=rows[1].open_time)
    for row,clock in ((rows[1],rows[1].open_time),(rows[0],rows[1].open_time),
                      (rows[2],rows[3].open_time),(replace(rows[1],symbol='BTCUSDT'),rows[2].open_time)):
        with pytest.raises(ValueError):stream.push(row,as_of=clock)
        assert list(stream.rows)==rows[:1]
    stream.push(rows[1],as_of=rows[2].open_time)
    assert len(stream.rows)==2


def test_cached_unfinished_values_do_not_become_final_after_time_passes():
    row=replace(candles()[0],cache_observed_at=candles()[0].open_time+timedelta(minutes=1))
    with pytest.raises(ValueError,match='closed bars'):
        ClosedFeatureStream('ETH/USDT').push(row,as_of=row.open_time+timedelta(hours=1))


def test_late_old_revision_only_affects_availability_while_inside_bounded_window():
    rows=candles();clock=rows[-1].open_time+timedelta(minutes=5)
    rows[0]=replace(rows[0],cache_observed_at=clock)
    stream=ClosedFeatureStream('ETH/USDT');outputs=[]
    for row in rows[:121]:
        result=stream.push(row,as_of=clock)
        if result:outputs.append(result)
    assert outputs[0].available_at==clock
    assert outputs[1].available_at==rows[120].open_time+timedelta(minutes=5)
    assert outputs[0].computed_at==outputs[1].computed_at==clock


def test_observation_clock_cannot_rewind_even_for_closed_consecutive_bar():
    rows=candles();stream=ClosedFeatureStream('ETH/USDT')
    stream.push(rows[0],as_of=rows[0].open_time+timedelta(hours=1))
    with pytest.raises(ValueError,match='backwards'):
        stream.push(rows[1],as_of=rows[1].open_time+timedelta(minutes=5))
    assert list(stream.rows)==rows[:1]
