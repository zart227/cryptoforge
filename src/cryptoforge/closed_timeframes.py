"""Causal higher-timeframe observations from closed, complete base buckets."""
from datetime import UTC,datetime,timedelta
from decimal import Decimal
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.candle_contract import known_closed,available_at


def aggregate_closed(candles,*,as_of,minutes,base_minutes=5):
    if as_of.tzinfo is None:raise ValueError('aware aggregation cutoff required')
    if any(type(v) is not int or v<1 for v in (minutes,base_minutes)) or minutes<=base_minutes or minutes%base_minutes:
        raise ValueError('higher interval must be an integer multiple of base interval')
    epoch=datetime(1970,1,1,tzinfo=UTC);step=timedelta(minutes=base_minutes);duration=timedelta(minutes=minutes)
    buckets={};previous=None;pair=symbol=None
    for row in candles:
        if row.open_time.tzinfo is None:raise ValueError('aware base candle time required')
        stamp=row.open_time.astimezone(UTC)
        if not known_closed(row,step=step,as_of=as_of):continue
        if previous is not None and stamp<=previous:raise ValueError('base candles must be chronological and unique')
        previous=stamp
        if pair is None:pair,symbol=row.pair,row.symbol
        if (row.pair,row.symbol)!=(pair,symbol):raise ValueError('one market identity required per aggregation')
        seconds=(stamp-epoch).total_seconds()
        if seconds%(base_minutes*60):raise ValueError('base candle is not aligned to its interval')
        if not all(v.is_finite() for v in (row.open,row.high,row.low,row.close,row.volume)) or not (
            0<row.low<=min(row.open,row.close)<=max(row.open,row.close)<=row.high and row.volume>=0):
            raise ValueError('invalid closed base candle')
        start=epoch+timedelta(seconds=(seconds//(minutes*60))*(minutes*60))
        buckets.setdefault(start,[]).append(row)
    result=[];incomplete=[];unfinished=[]
    for start,rows in sorted(buckets.items()):
        if start+duration>as_of:unfinished.append(start.isoformat());continue
        expected=[start+step*i for i in range(minutes//base_minutes)]
        if [row.open_time.astimezone(UTC) for row in rows]!=expected:
            incomplete.append(start.isoformat());continue
        result.append(CandleRow(pair,symbol,start,rows[0].open,max(row.high for row in rows),
            min(row.low for row in rows),rows[-1].close,sum((row.volume for row in rows),Decimal(0)),
            cache_observed_at=max(available_at(row,step=step) for row in rows)
            if any(row.cache_observed_at is not None for row in rows) else None))
    return result,{'schema_version':'closed-higher-timeframe-v1','minutes':minutes,'base_minutes':base_minutes,
        'as_of':as_of.isoformat(),'complete_buckets':len(result),'incomplete_buckets':incomplete,
        'unfinished_buckets':unfinished,'missing_data_filled':False,'model_input_registration_allowed':False}
