from datetime import timedelta
from dataclasses import replace
import pytest

from cryptoforge.candle_contract import closed_snapshot
from cryptoforge.model_training import build_examples
from test_model_training import make_training_candles,FakeRegistry


def test_unclosed_future_and_gapped_candles_are_not_training_targets():
    rows=make_training_candles(100)
    cutoff=rows[-1].open_time+timedelta(minutes=2)
    closed=closed_snapshot(rows,timeframe='5m',as_of=cutoff)
    assert len(closed)==99
    examples=build_examples('ETH/USDT',closed,horizon_candles=3)
    assert max(e.label_end_time for e in examples)<=cutoff
    with pytest.raises(ValueError,match='gapped'):
        closed_snapshot(rows[:50]+rows[51:],timeframe='5m',as_of=cutoff)
    naive=[replace(rows[0],open_time=rows[0].open_time.replace(tzinfo=None))]
    with pytest.raises(ValueError,match='naive'):closed_snapshot(naive,timeframe='5m',as_of=cutoff)


def test_registry_does_not_load_a_model_from_the_future():
    from datetime import datetime,UTC
    registry=FakeRegistry({'occurred_at':'2026-10-08T00:00:00+00:00','payload':{}})
    assert registry.latest(now=datetime(2026,10,7,tzinfo=UTC)) is None


def test_cached_partial_values_do_not_become_final_just_because_clock_advanced():
    from dataclasses import replace
    from datetime import timedelta
    from test_trade_simulator import history
    rows=history(count=10);as_of=rows[-1].open_time+timedelta(minutes=30)
    rows[-1]=replace(rows[-1],cache_observed_at=rows[-1].open_time+timedelta(minutes=1))
    assert closed_snapshot(rows,timeframe='5m',as_of=as_of)==rows[:-1]
    rows[-1]=replace(rows[-1],cache_observed_at=rows[-1].open_time+timedelta(minutes=6))
    assert closed_snapshot(rows,timeframe='5m',as_of=as_of)==rows


def test_later_cache_revision_is_not_available_in_an_earlier_snapshot():
    rows=make_training_candles(10)
    cutoff=rows[-1].open_time+timedelta(minutes=5)
    rows[-1]=replace(rows[-1],cache_observed_at=cutoff+timedelta(seconds=1))
    assert closed_snapshot(rows,timeframe='5m',as_of=cutoff)==rows[:-1]
    assert closed_snapshot(rows,timeframe='5m',as_of=cutoff+timedelta(seconds=1))==rows
