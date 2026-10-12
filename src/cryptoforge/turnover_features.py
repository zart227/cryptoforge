"""Quote-turnover VWAP from observed closed bars; never approximate it with HLC."""
from dataclasses import dataclass
from datetime import datetime,UTC
from decimal import Decimal
from math import isfinite
from cryptoforge.archive_quality import validate_candles

FEATURE_VERSION='experimental-observed-turnover-vwap-v1'


@dataclass(frozen=True)
class TurnoverSnapshot:
    symbol: str
    open_time: object
    feature_available_at: object
    window_candles: int
    source_interval: str
    quote_turnover_vwap: Decimal
    close_to_vwap_fraction: float
    feature_version: str=FEATURE_VERSION


def turnover_snapshots(candles,*,observed_at,as_of,window_candles=12):
    if observed_at.tzinfo is None or as_of.tzinfo is None or type(window_candles) is not int or not 2<=window_candles<=288:
        raise ValueError('aware observed turnover and bounded window required')
    quality={'feature_version':FEATURE_VERSION,'count':0,'live_model_input_allowed':False,
        'historical_observation_times_inferred':False,'approximate_hlc_vwap_used':False,'observation_time_independently_certified':False}
    if observed_at>as_of:return [],{**quality,'status':'source_not_observed_yet'}
    cutoff=int(min(observed_at,as_of).timestamp()*1000)
    closed=[row for row in candles if row.close_ms<=cutoff]
    validated=validate_candles(closed,now_ms=cutoff)
    if validated['gap_ranges']:raise ValueError('turnover feature cannot cross missing bars')
    for row in closed:
        if row.volume==0 and row.turnover!=0:raise ValueError('turnover without base volume')
        if row.volume>0 and not row.low<=row.turnover/row.volume<=row.high:
            raise ValueError('quote/base turnover ratio inconsistent with price range')
    result=[];empty=0
    for index in range(window_candles-1,len(closed)):
        window=closed[index-window_candles+1:index+1]
        base=sum((row.volume for row in window),Decimal(0));quote=sum((row.turnover for row in window),Decimal(0))
        if base==0:empty+=1;continue
        vwap=quote/base;deviation=float(closed[index].close/vwap-1)
        if not isfinite(deviation):raise ValueError('finite turnover feature required')
        result.append(TurnoverSnapshot(closed[index].symbol,
            datetime.fromtimestamp(closed[index].start_ms/1000,UTC),observed_at,window_candles,closed[index].interval,vwap,deviation))
    return result,{**quality,'count':len(result),'status':'observed_closed_turnover_only',
        'zero_volume_windows_excluded':empty,'source_quality':validated}
