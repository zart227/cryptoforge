from dataclasses import replace
from decimal import Decimal as D
import pytest
from cryptoforge.market_data import Candle
from cryptoforge.archive_quality import validate_candles,aggregate_candles


def candles(count=60):
    return [Candle('BTCUSDT','1',i*60000,D(100),D(102),D(99),D(101),D(2),D(200)) for i in range(count)]


@pytest.mark.parametrize('change',[{'low':D(103)},{'close':D(0)},{'volume':D(-1)},{'turnover':D('NaN')},{'start_ms':1}])
def test_rejects_bad_market_data(change):
    rows=candles();rows[0]=replace(rows[0],**change)
    with pytest.raises(ValueError):
        validate_candles(rows,now_ms=3600000)


def test_duplicate_unclosed_and_gap_reporting():
    rows=candles()
    with pytest.raises(ValueError,match='duplicate'):
        validate_candles([rows[0],rows[0]],now_ms=3600000)
    with pytest.raises(ValueError,match='unclosed'):
        validate_candles(rows,now_ms=3599999)
    quality=validate_candles(rows[:5]+rows[7:],now_ms=3600000)
    assert quality['gap_ranges']==[{'start_ms':300000,'end_ms_exclusive':420000,'missing_candles':2}]


def test_utc_aggregation_never_fills_missing_bars():
    rows=candles()
    aggregated=aggregate_candles(rows,'5',now_ms=3600000)
    assert len(aggregated)==12
    assert aggregated[0].volume==D(10)
    assert aggregated[0].turnover==D(1000)
    hourly=aggregate_candles(aggregated,'60',now_ms=3600000)
    assert len(hourly)==1 and hourly[0].volume==D(120)
    assert len(aggregate_candles(rows[:2]+rows[3:],'5',now_ms=3600000))==11
