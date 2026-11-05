"""Bounded original candle inputs for purged walk-forward training/validation."""
from datetime import datetime,UTC
from decimal import Decimal
from cryptoforge.execution_market_evidence import _load
from cryptoforge.supabase_executor import CandleRow


def validate_source_rows(rows,symbol,start_ms,end_ms):
    expected=(end_ms-start_ms)//300000
    if not rows or len(rows)!=expected:raise ValueError('complete expected candle coverage required')
    for index,row in enumerate(rows):
        if row[0]!=symbol or str(row[1])!='5' or row[2]!=start_ms+index*300000:
            raise ValueError('continuous unique single-market candles required')
        opened,high,low,close,volume=(Decimal(row[i]) for i in (3,4,5,6,7))
        if not all(value.is_finite() for value in (opened,high,low,close,volume)) or not (
            0<low<=min(opened,close)<=max(opened,close)<=high and volume>=0):
            raise ValueError('valid finite candle OHLCV required')


def load_bound_candles(binding):
    result={}
    for pair,source in binding['pairs'].items():
        rows=[]
        for reference in source['chunks']:rows.extend(_load(reference))
        validate_source_rows(rows,pair.replace('/',''),binding['start_ms'],binding['end_ms_exclusive'])
        result[pair]=[CandleRow(pair=pair,symbol=row[0],open_time=datetime.fromtimestamp(row[2]/1000,UTC),
            **{key:Decimal(row[index]) for key,index in (('open',3),('high',4),('low',5),('close',6),('volume',7))}) for row in rows]
    return result
