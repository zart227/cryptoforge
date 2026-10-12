"""Compare a complete development minute slice to its frozen coarse source."""
from datetime import timedelta
from cryptoforge.closed_timeframes import aggregate_closed
from cryptoforge.research_protocol import assert_development_range


def compare_intrabar_source(fine, coarse, *, protocol, as_of):
    if not fine:raise ValueError('nonempty minute source required')
    if as_of.tzinfo is None:raise ValueError('aware source audit observation required')
    start=fine[0].open_time;end=fine[-1].open_time+timedelta(minutes=1)
    assert_development_range(protocol,start,end)
    if start.minute%5 or end.minute%5 or start.second or end.second or start.microsecond or end.microsecond:
        raise ValueError('complete aligned five-minute source range required')
    if any(b.open_time-a.open_time!=timedelta(minutes=1) for a,b in zip(fine,fine[1:])):
        raise ValueError('chronological gapless minute source required')
    combined,quality=aggregate_closed(fine,as_of=as_of,minutes=5,base_minutes=1)
    expected=int((end-start).total_seconds()/300)
    if len(combined)!=expected or quality['incomplete_buckets'] or quality['unfinished_buckets']:
        raise ValueError('complete closed minute source required')
    selected=[row for row in coarse if start<=row.open_time<end]
    if len(selected)!=expected or len({row.open_time for row in selected})!=expected:
        raise ValueError('complete unique frozen coarse source required')
    lookup={row.open_time:row for row in selected};checks=[]
    for row in combined:
        old=lookup.get(row.open_time)
        if old is None or (row.pair,row.symbol)!=(old.pair,old.symbol):
            raise ValueError('fine/coarse market identity mismatch')
        checks.append({'open_time':row.open_time.isoformat(),
            'price_matches':all(getattr(row,key)==getattr(old,key) for key in ('open','high','low','close')),
            'volume_matches':row.volume==old.volume})
    return {'observed_at':as_of.isoformat(),'scope':'development_minute_aggregation_source_consistency_only',
        'fine_candles':len(fine),'coarse_bars':len(checks),'checks':checks,'quality':quality,
        'source_consistency_pass':all(row['price_matches'] and row['volume_matches'] for row in checks),
        'real_fill_certified':False,'historical_observation_time_certified':False,'trade_policy_changed':False}
