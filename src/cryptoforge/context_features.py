"""Experimental causal market context; a distinct schema, never candle-v1 input."""
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC,timedelta
from decimal import Decimal
from math import log,sqrt,sin,cos,pi,isfinite

from cryptoforge.causal_features import feature_snapshots
from cryptoforge.closed_timeframes import aggregate_closed
from cryptoforge.candle_contract import known_closed,available_at
from cryptoforge.model_training import FEATURE_NAMES as BASE_NAMES

FEATURE_VERSION='experimental-market-context-v2'
FEATURE_NAMES=(*BASE_NAMES,'return_12','return_36','atr_14','realized_vol_12','range_position_36',
    'distance_support_30','distance_resistance_30','btc_return_12','relative_return_12','btc_vol_12',
    'trend_strength_atr','hour_sin','hour_cos','weekday_sin','weekday_cos','closed_hour_return','closed_hour_range')


@dataclass(frozen=True)
class ContextSnapshot:
    pair: str
    open_time: object
    feature_available_at: object
    features: tuple
    regime: str
    feature_version: str=FEATURE_VERSION
    input_candle_state: str='closed_only'


def _volatility(rows,index):
    returns=[log(float(rows[i].close/rows[i-1].close)) for i in range(index-11,index+1)]
    mean=sum(returns)/len(returns)
    return sqrt(sum((value-mean)**2 for value in returns)/len(returns))


def context_snapshots(pair,candles,btc_candles,*,as_of):
    step=timedelta(minutes=5)
    own=feature_snapshots(pair,candles,as_of=as_of)
    reference=feature_snapshots('BTC/USDT',btc_candles,as_of=as_of)
    known=[row for row in candles if known_closed(row,step=step,as_of=as_of)]
    btc=[row for row in btc_candles if known_closed(row,step=step,as_of=as_of)]
    indices={row.open_time:i for i,row in enumerate(known)};btc_indices={row.open_time:i for i,row in enumerate(btc)}
    btc_snapshots={row.open_time:row for row in reference}
    hours,hour_quality=aggregate_closed(candles,as_of=as_of,minutes=60)
    hour_available=[row.open_time+timedelta(hours=1) for row in hours]
    result=[];excluded={}
    for snapshot in own:
        if snapshot.open_time not in btc_snapshots:
            excluded['missing_aligned_btc_context']=excluded.get('missing_aligned_btc_context',0)+1;continue
        ref=btc_snapshots[snapshot.open_time]
        market_close=snapshot.open_time+step
        hour_index=bisect_right(hour_available,market_close)-1
        if hour_index<1:
            excluded['insufficient_closed_hour_context']=excluded.get('insufficient_closed_hour_context',0)+1;continue
        index=indices[snapshot.open_time];bi=btc_indices[snapshot.open_time];row=known[index];close=row.close
        ret12=float(close/known[index-12].close-1);ret36=float(close/known[index-36].close-1)
        atr=sum((max(known[i].high-known[i].low,abs(known[i].high-known[i-1].close),abs(known[i].low-known[i-1].close))
                 for i in range(index-13,index+1)),Decimal(0))/Decimal(14)/close
        high=max(r.high for r in known[index-35:index+1]);low=min(r.low for r in known[index-35:index+1])
        position=float((close-low)/(high-low)) if high>low else .5
        support=min(r.low for r in known[index-30:index]);resistance=max(r.high for r in known[index-30:index])
        br=float(btc[bi].close/btc[bi-12].close-1)
        strength=snapshot.features[4]/float(atr) if atr else 0.
        stamp=market_close.astimezone(UTC)
        hour_angle=2*pi*(stamp.hour*60+stamp.minute)/1440;day_angle=2*pi*stamp.weekday()/7
        hour=hours[hour_index];prior=hours[hour_index-1]
        values=(*snapshot.features,ret12,ret36,float(atr),_volatility(known,index),position,
            float((close-support)/close),float((resistance-close)/close),br,ret12-br,_volatility(btc,bi),
            strength,sin(hour_angle),cos(hour_angle),sin(day_angle),cos(day_angle),
            float(hour.close/prior.close-1),float((hour.high-hour.low)/hour.close))
        if not all(isfinite(value) for value in values):raise ValueError('nonfinite market-context features')
        regime='uptrend' if strength>1 else 'downtrend' if strength< -1 else 'range'
        information_end=max(snapshot.feature_available_at,ref.feature_available_at,
            available_at(hour,step=timedelta(hours=1)),available_at(prior,step=timedelta(hours=1)))
        result.append(ContextSnapshot(pair,snapshot.open_time,information_end,tuple(values),regime))
    return result,{'feature_version':FEATURE_VERSION,'feature_names':list(FEATURE_NAMES),'count':len(result),
        'excluded':excluded,'hour_quality':hour_quality,'unknown_context_filled':False,
        'live_model_input_allowed':False,'regime_policy':'past_ema_gap_over_atr_fixed_threshold_1'}
