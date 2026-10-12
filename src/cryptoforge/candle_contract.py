"""Closed-bar time contract for training and newly published model inputs."""
from datetime import timedelta

TIMEFRAMES={'1m':1,'5m':5,'15m':15,'1h':60}


def available_at(candle,*,step):
    """Market close is a lower bound; a recorded cache revision may be later."""
    closed_at=candle.open_time+step
    observed=getattr(candle,'cache_observed_at',None)
    if observed is not None and observed.tzinfo is None:raise ValueError('naive cache observation timestamp')
    return max(closed_at,observed) if observed is not None else closed_at


def closed_snapshot(candles,*,timeframe,as_of):
    if timeframe not in TIMEFRAMES or as_of.tzinfo is None:
        raise ValueError('supported timeframe and timezone-aware cutoff required')
    step=timedelta(minutes=TIMEFRAMES[timeframe])
    if any(c.open_time.tzinfo is None for c in candles):raise ValueError('naive candle timestamp')
    rows=[c for c in candles if known_closed(c,step=step,as_of=as_of)]
    if any(b.open_time-a.open_time!=step for a,b in zip(rows,rows[1:])):
        raise ValueError('duplicate, unordered or gapped training candles')
    return rows



def known_closed(candle,*,step,as_of):
    if candle.open_time+step>as_of:return False
    observed=getattr(candle,'cache_observed_at',None)
    if observed is not None and observed.tzinfo is None:raise ValueError('naive cache observation timestamp')
    return observed is None or candle.open_time+step<=observed<=as_of
