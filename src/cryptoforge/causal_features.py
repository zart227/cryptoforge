"""Closed candle-v1 snapshots without future-price labels."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from math import isfinite
from cryptoforge.model_training import extract_features,FEATURE_VERSION
from cryptoforge.candle_contract import known_closed,available_at


@dataclass(frozen=True)
class FeatureSnapshot:
    pair: str
    open_time: object
    feature_available_at: object
    features: tuple
    feature_version: str=FEATURE_VERSION
    input_candle_state: str='closed_only'


def feature_snapshots(pair,candles,*,as_of,minutes=5):
    if as_of.tzinfo is None or type(minutes) is not int or minutes<1:raise ValueError('aware feature cutoff and positive interval required')
    step=timedelta(minutes=minutes);known=[];previous=None;symbol=None
    for row in candles:
        if row.open_time.tzinfo is None:raise ValueError('aware feature candle time required')
        if not known_closed(row,step=step,as_of=as_of):continue
        if row.pair!=pair or (symbol is not None and row.symbol!=symbol):raise ValueError('feature market identity mismatch')
        symbol=row.symbol
        if previous is not None and row.open_time-previous!=step:raise ValueError('features cannot cross missing or duplicate bars')
        previous=row.open_time
        if not all(v.is_finite() for v in (row.open,row.high,row.low,row.close,row.volume)) or not (
            0<row.low<=min(row.open,row.close)<=max(row.open,row.close)<=row.high and row.volume>=0):
            raise ValueError('invalid known feature candle')
        known.append(row)
    result=[];fast=slow=None;information_end=None;alpha_fast=Decimal(2)/Decimal(13);alpha_slow=Decimal(2)/Decimal(37)
    for index,row in enumerate(known):
        row_available=available_at(row,step=step)
        information_end=max(information_end,row_available) if information_end is not None else row_available
        if fast is None:fast=slow=row.close
        fast=row.close*alpha_fast+fast*(Decimal(1)-alpha_fast)
        slow=row.close*alpha_slow+slow*(Decimal(1)-alpha_slow)
        if index<36:continue
        window=known[index-35:index+1]
        features=list(extract_features(window,[c.volume for c in window]))
        features[4]=float((fast-slow)/row.close)
        if not all(isfinite(v) for v in features):raise ValueError('nonfinite causal features')
        result.append(FeatureSnapshot(pair,row.open_time,information_end,tuple(features)))
    return result
