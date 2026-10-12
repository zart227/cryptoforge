from datetime import datetime,UTC,timedelta
from decimal import Decimal as D
from dataclasses import replace
import pytest
from cryptoforge.market_data import Candle
from cryptoforge.turnover_features import turnover_snapshots
NOW=datetime(2026,10,1,1,tzinfo=UTC)


def rows():
    start=int((NOW-timedelta(minutes=10)).timestamp()*1000)
    return [Candle('ETHUSDT','5',start,D(100),D(110),D(90),D(100),D(1),D(100)),
        Candle('ETHUSDT','5',start+300000,D(100),D(110),D(90),D(105),D(3),D(315))]


def test_true_quote_turnover_vwap_and_actual_observation_availability():
    values,quality=turnover_snapshots(rows(),observed_at=NOW,as_of=NOW,window_candles=2)
    assert values[0].quote_turnover_vwap==D('103.75')
    assert values[0].feature_available_at==NOW
    assert not quality['approximate_hlc_vwap_used'] and not quality['live_model_input_allowed']
    assert turnover_snapshots(rows(),observed_at=NOW,as_of=NOW-timedelta(seconds=1),window_candles=2)[0]==[]


def test_partial_captured_bar_does_not_become_closed_later():
    assert not turnover_snapshots(rows(),observed_at=NOW-timedelta(seconds=1),as_of=NOW,window_candles=2)[0]


def test_unknown_or_invalid_turnover_and_gaps_are_rejected():
    changed=rows();changed[0]=replace(changed[0],turnover=D(0))
    with pytest.raises(ValueError,match='inconsistent'):turnover_snapshots(changed,observed_at=NOW,as_of=NOW,window_candles=2)
    changed=rows();changed[0]=replace(changed[0],start_ms=changed[0].start_ms-300000)
    with pytest.raises(ValueError,match='missing'):turnover_snapshots(changed,observed_at=NOW,as_of=NOW,window_candles=2)


def test_zero_trade_volume_window_is_not_filled_with_price_proxy():
    changed=[replace(row,volume=D(0),turnover=D(0)) for row in rows()]
    values,quality=turnover_snapshots(changed,observed_at=NOW,as_of=NOW,window_candles=2)
    assert not values and quality['zero_volume_windows_excluded']==1
