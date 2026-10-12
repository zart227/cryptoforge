from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.causal_features import feature_snapshots
from cryptoforge.model_training import build_examples
from test_trade_simulator import history


def test_causal_features_exactly_match_archival_candle_v1_values():
    rows=history(count=100)
    rows=[replace(row,open=D(100)+D(i)/100,close=D(100)+D(i+1)/100,high=D(101)+D(i)/100,low=D(99)+D(i)/100) for i,row in enumerate(rows)]
    snapshots=feature_snapshots('ETH/USDT',rows,as_of=rows[-1].open_time+timedelta(minutes=5))
    labels=build_examples('ETH/USDT',rows,horizon_candles=3)
    mapping={row.open_time:row for row in snapshots}
    assert all(mapping[row.open_time].features==row.features for row in labels)
    assert all(snapshot.feature_available_at==snapshot.open_time+timedelta(minutes=5) for snapshot in snapshots)


def test_prefix_and_future_changes_do_not_change_available_features():
    rows=history(count=100);as_of=rows[60].open_time+timedelta(minutes=5)
    prefix=feature_snapshots('ETH/USDT',rows[:61],as_of=as_of)
    changed=rows[:61]+[replace(row,pair='UNKNOWN',close=D(-1)) for row in rows[61:]]
    assert feature_snapshots('ETH/USDT',changed,as_of=as_of)==prefix
    for index in range(37,61):
        snapshot=feature_snapshots('ETH/USDT',rows[:index+1],as_of=rows[index].open_time+timedelta(minutes=5))[-1]
        assert snapshot==prefix[index-36]


def test_current_partial_bar_and_missing_history_do_not_become_features():
    rows=history(count=100)
    snapshots=feature_snapshots('ETH/USDT',rows,as_of=rows[40].open_time+timedelta(minutes=1))
    assert snapshots[-1].open_time==rows[39].open_time
    with pytest.raises(ValueError,match='missing'):feature_snapshots('ETH/USDT',rows[:40]+rows[41:],as_of=rows[-1].open_time+timedelta(minutes=5))


def test_cached_unfinished_values_remain_excluded_after_wall_clock_passes_close():
    rows=history(count=100);as_of=rows[-1].open_time+timedelta(hours=1)
    rows[-1]=replace(rows[-1],cache_observed_at=rows[-1].open_time+timedelta(minutes=1))
    snapshots=feature_snapshots('ETH/USDT',rows,as_of=as_of)
    assert snapshots[-1].open_time==rows[-2].open_time


def test_late_revision_of_ema_history_moves_feature_availability():
    rows=history(count=100);as_of=rows[-1].open_time+timedelta(hours=1)
    revised_at=rows[80].open_time+timedelta(minutes=5)
    rows[0]=replace(rows[0],cache_observed_at=revised_at)
    snapshots=feature_snapshots('ETH/USDT',rows,as_of=as_of)
    assert snapshots[0].feature_available_at==revised_at
    assert snapshots[-1].feature_available_at==rows[-1].open_time+timedelta(minutes=5)
