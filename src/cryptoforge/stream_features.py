"""Append-only closed bounded-window candle-v1 features; no future labels."""
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from math import isfinite
from cryptoforge.candle_contract import known_closed,available_at
from cryptoforge.model_training import extract_features


@dataclass(frozen=True)
class StreamingFeatures:
    pair: str
    open_time: object
    available_at: object
    computed_at: object
    features: tuple
    lookback_candles: int
    feature_version: str='candle-v1'
    calculation_contract: str='bounded-window-candle-v1'
    input_candle_state: str='closed_only'


class ClosedFeatureStream:
    def __init__(self,pair,*,lookback_candles=120):
        if type(lookback_candles) is not int or not 36<=lookback_candles<=1000:
            raise ValueError('explicit supported bounded feature window required')
        self.pair=pair;self.width=lookback_candles;self.rows=deque(maxlen=lookback_candles)
        self.last_asof=None

    def push(self,row,*,as_of):
        step=timedelta(minutes=5)
        if as_of.tzinfo is None or as_of.utcoffset() is None or row.open_time.tzinfo is None:
            raise ValueError('aware streaming timestamps required')
        if self.last_asof is not None and as_of<self.last_asof:
            raise ValueError('stream observation clock cannot go backwards')
        if not known_closed(row,step=step,as_of=as_of):
            raise ValueError('stream accepts only observed closed bars')
        if row.pair!=self.pair or row.symbol!=self.pair.replace('/',''):
            raise ValueError('stream market identity mismatch')
        if self.rows and row.open_time-self.rows[-1].open_time!=step:
            raise ValueError('stream requires consecutive bars; revisions need explicit reset/replay')
        if not all(v.is_finite() for v in (row.open,row.high,row.low,row.close,row.volume)) or not (
                0<row.low<=min(row.open,row.close)<=max(row.open,row.close)<=row.high and row.volume>=0):
            raise ValueError('valid streaming OHLCV required')
        proposed=[*self.rows,row][-self.width:]
        result=None
        if len(proposed)==self.width:
            features=extract_features(proposed,[c.volume for c in proposed])
            if not all(isfinite(value) for value in features):raise ValueError('finite streaming features required')
            result=StreamingFeatures(self.pair,row.open_time,max(available_at(c,step=step) for c in proposed),
                                     as_of,features,self.width)
        # Failed validation/computation never partially advances the state.
        self.rows.append(row);self.last_asof=as_of
        return result
