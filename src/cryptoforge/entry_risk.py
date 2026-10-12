"""Ex-ante ATR risk plans for research portfolios, never live risk settings."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from cryptoforge.candle_contract import known_closed,available_at


@dataclass(frozen=True)
class EntryRiskPlan:
    pair: str
    signal_time: object
    information_available_at: object
    stop_fraction: Decimal
    target_fraction: Decimal
    hold_bars: int
    schema_version: str='research-entry-risk-plan-v1'

    def __post_init__(self):
        if self.signal_time.tzinfo is None or self.information_available_at.tzinfo is None:
            raise ValueError('aware entry risk timestamps required')
        for value in (self.stop_fraction,self.target_fraction):
            if not isinstance(value,Decimal) or not value.is_finite() or not 0<value<1:
                raise ValueError('finite entry risk fractions required')
        if type(self.hold_bars) is not int or self.hold_bars<1:raise ValueError('positive risk holding bars required')
        if self.schema_version!='research-entry-risk-plan-v1':raise ValueError('known entry risk schema required')


def atr_entry_risk(candles,index,*,as_of,period=14,stop_multiple=Decimal('1.5'),target_multiple=Decimal('3'),
                   minimum_stop=Decimal('.005'),maximum_stop=Decimal('.04'),
                   minimum_target=Decimal('.01'),maximum_target=Decimal('.08'),hold_bars=12):
    if type(period) is not int or period<2 or type(index) is not int or not period<=index<len(candles):
        raise ValueError('complete past ATR window required')
    params=(stop_multiple,target_multiple,minimum_stop,maximum_stop,minimum_target,maximum_target)
    if any(not isinstance(value,Decimal) or not value.is_finite() or value<=0 for value in params):
        raise ValueError('finite positive declared ATR design required')
    if not minimum_stop<=maximum_stop<1 or not minimum_target<=maximum_target<1:
        raise ValueError('ordered ATR risk bounds required')
    window=candles[index-period:index+1]
    step=window[1].open_time-window[0].open_time
    if as_of.tzinfo is None or step!=timedelta(minutes=5):raise ValueError('aware five-minute ATR observations required')
    pair,symbol=window[0].pair,window[0].symbol
    for i,row in enumerate(window):
        if (row.pair,row.symbol)!=(pair,symbol) or (i and row.open_time-window[i-1].open_time!=step):
            raise ValueError('continuous single-market ATR history required')
        if not known_closed(row,step=step,as_of=as_of):raise ValueError('ATR observation unavailable at decision')
        if not all(v.is_finite() for v in (row.open,row.high,row.low,row.close,row.volume)) or not (
            0<row.low<=min(row.open,row.close)<=max(row.open,row.close)<=row.high and row.volume>=0):
            raise ValueError('valid ATR OHLCV required')
    ranges=[max(row.high-row.low,abs(row.high-prior.close),abs(row.low-prior.close)) for prior,row in zip(window,window[1:])]
    fraction=sum(ranges,Decimal(0))/period/window[-1].close
    stop=min(maximum_stop,max(minimum_stop,fraction*stop_multiple))
    target=min(maximum_target,max(minimum_target,fraction*target_multiple))
    return EntryRiskPlan(pair,window[-1].open_time,max(available_at(row,step=step) for row in window),stop,target,hold_bars)
