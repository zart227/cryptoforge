"""Strict OHLCV validation and UTC aggregation without invented candles."""
from decimal import Decimal
from typing import Sequence

from cryptoforge.market_data import Candle, interval_to_milliseconds


def validate_candles(candles: Sequence[Candle], *, now_ms: int) -> dict:
    if not candles:
        return {'candles':0,'gap_ranges':[],'status':'empty'}
    symbol,interval=candles[0].symbol,candles[0].interval
    step=interval_to_milliseconds(interval)
    gaps=[];previous=None
    for candle in candles:
        values=(candle.open,candle.high,candle.low,candle.close,candle.volume,candle.turnover)
        if candle.symbol!=symbol or candle.interval!=interval or candle.start_ms%step:
            raise ValueError('inconsistent symbol/timeframe or unaligned timestamp')
        if previous is not None:
            if candle.start_ms<=previous:
                raise ValueError('duplicate or unordered candles')
            if candle.start_ms!=previous+step:
                gaps.append({'start_ms':previous+step,'end_ms_exclusive':candle.start_ms,
                             'missing_candles':(candle.start_ms-previous)//step-1})
        if not all(v.is_finite() for v in values) or not (
            0<candle.low<=min(candle.open,candle.close)<=max(candle.open,candle.close)<=candle.high
            and candle.volume>=0 and candle.turnover>=0):
            raise ValueError('invalid OHLCV values')
        if candle.close_ms>now_ms:
            raise ValueError('unclosed candle')
        previous=candle.start_ms
    return {'candles':len(candles),'gap_ranges':gaps,'status':'gapped' if gaps else 'valid'}


def aggregate_candles(candles: Sequence[Candle], target_interval: str, *, now_ms: int) -> list[Candle]:
    validate_candles(candles,now_ms=now_ms)
    if not candles:
        return []
    source=interval_to_milliseconds(candles[0].interval)
    target=interval_to_milliseconds(target_interval)
    if target<=source or target%source:
        raise ValueError('target must be an integer multiple of source interval')
    buckets={}
    for candle in candles:
        buckets.setdefault(candle.start_ms//target*target,[]).append(candle)
    result=[]
    for start,rows in sorted(buckets.items()):
        if len(rows)!=target//source or any(row.start_ms!=start+i*source for i,row in enumerate(rows)):
            continue  # Missing source bars never become an invented complete candle.
        if start+target>now_ms:
            continue
        result.append(Candle(rows[0].symbol,target_interval,start,rows[0].open,
                             max(c.high for c in rows),min(c.low for c in rows),rows[-1].close,
                             sum((c.volume for c in rows),Decimal(0)),sum((c.turnover for c in rows),Decimal(0))))
    return result
