"""Separate research hypotheses; existing strategy families and live rules stay fixed."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from cryptoforge.candle_contract import known_closed,available_at


@dataclass(frozen=True)
class ExtensionSpec:
    family: str
    support_tolerance: Decimal=Decimal('.001')
    compression_ratio: Decimal=Decimal('.5')
    volume_multiplier: Decimal=Decimal('1.5')

    def __post_init__(self):
        if self.family not in {'support_bounce','compression_breakout'}:raise ValueError('known research extension required')
        for value in (self.support_tolerance,self.compression_ratio,self.volume_multiplier):
            if not isinstance(value,Decimal) or not value.is_finite() or value<=0:raise ValueError('finite declared extension design required')
        if self.support_tolerance>=1 or self.compression_ratio>=1:raise ValueError('bounded extension fractions required')


def extension_signal(candles,index,spec,*,as_of):
    if not isinstance(spec,ExtensionSpec) or type(index) is not int or not 31<=index<len(candles):
        raise ValueError('complete closed extension context required')
    window=candles[index-31:index+1];step=timedelta(minutes=5);pair,symbol=window[0].pair,window[0].symbol
    for i,row in enumerate(window):
        if (row.pair,row.symbol)!=(pair,symbol) or (i and row.open_time-window[i-1].open_time!=step):
            raise ValueError('continuous single market extension context required')
        if not known_closed(row,step=step,as_of=as_of):raise ValueError('extension input unavailable at decision')
        if not all(v.is_finite() for v in (row.open,row.high,row.low,row.close,row.volume)) or not (
            0<row.low<=min(row.open,row.close)<=max(row.open,row.close)<=row.high and row.volume>=0):
            raise ValueError('valid extension OHLCV required')
    prior=window[:-1];last=window[-1]
    average=sum((row.volume for row in prior[-20:]),Decimal(0))/20
    allowed=False
    if average>0:
        if spec.family=='support_bounce':
            support=min(row.low for row in prior[-30:])
            allowed=(last.low<=support*(1+spec.support_tolerance) and last.close>support
                     and last.close>prior[-1].close and last.volume>=average*spec.volume_multiplier)
        else:
            ranges=[max(row.high-row.low,abs(row.high-previous.close),abs(row.low-previous.close))
                    for previous,row in zip(prior,prior[1:])]
            short=sum(ranges[-5:],Decimal(0))/5;long=sum(ranges,Decimal(0))/30
            allowed=(long>0 and short/long<=spec.compression_ratio and last.close>max(row.high for row in prior[-20:])
                     and last.volume>=average*spec.volume_multiplier)
    return {'would_enter':allowed,'family':spec.family,'signal_time':last.open_time,
        'information_available_at':max(available_at(row,step=step) for row in window),
        'signal_schema':'research-extension-signal-v1','live_eligible':False,
        'independent_profitability_established':False}
