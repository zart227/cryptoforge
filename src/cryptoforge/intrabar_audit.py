"""Audit 5m barrier ambiguity with complete 1m observations; no trade policy change."""
from datetime import timedelta
from decimal import Decimal
from cryptoforge.closed_timeframes import aggregate_closed
from cryptoforge.candle_contract import known_closed


def audit_barrier_order(coarse,fine,*,entry_price,stop_fraction,target_fraction,as_of):
    values=(entry_price,stop_fraction,target_fraction)
    if any(not isinstance(v,Decimal) or not v.is_finite() or v<=0 for v in values) or not stop_fraction<1 or not target_fraction<1:
        raise ValueError('finite positive price and fractions below one required')
    end=coarse.open_time+timedelta(minutes=5)
    if as_of.tzinfo is None or coarse.open_time.tzinfo is None or end>as_of or not known_closed(coarse,step=timedelta(minutes=5),as_of=as_of):
        raise ValueError('known closed coarse bar required')
    if not all(v.is_finite() for v in (coarse.open,coarse.high,coarse.low,coarse.close,coarse.volume)) or not (
        0<coarse.low<=min(coarse.open,coarse.close)<=max(coarse.open,coarse.close)<=coarse.high and coarse.volume>=0):
        raise ValueError('valid coarse OHLCV required')
    stop=entry_price*(1-stop_fraction);target=entry_price*(1+target_fraction)
    base={'source_kind':'barrier_order_audit_only','trade_policy_changed':False,
          'can_certify_real_fill':False,'information_available_at':max(end,coarse.cache_observed_at or end).isoformat()}
    if coarse.open<=stop:return {**base,'status':'coarse_open_stop_gap','first_barrier':'stop','raw_price':str(coarse.open)}
    if coarse.open>=target:return {**base,'status':'coarse_open_target_gap','first_barrier':'target','raw_price':str(coarse.open)}
    if not (coarse.low<=stop and coarse.high>=target):
        side='stop' if coarse.low<=stop else 'target' if coarse.high>=target else None
        return {**base,'status':'coarse_bar_not_ambiguous','first_barrier':side,
            'raw_price':str(stop if side=='stop' else target) if side else None}
    selected=sorted([row for row in fine if coarse.open_time<=row.open_time<end
              and known_closed(row,step=timedelta(minutes=1),as_of=as_of)],key=lambda row:row.open_time)
    if any((row.pair,row.symbol)!=(coarse.pair,coarse.symbol) for row in selected):raise ValueError('fine market identity mismatch')
    aggregate,quality=aggregate_closed(selected,as_of=as_of,minutes=5,base_minutes=1)
    if len(aggregate)!=1 or aggregate[0].open_time!=coarse.open_time:
        return {**base,'status':'unresolved_incomplete_fine_history','first_barrier':'stop','raw_price':str(stop)}
    combined=aggregate[0]
    if any(getattr(combined,key)!=getattr(coarse,key) for key in ('open','high','low','close')):
        return {**base,'status':'unresolved_fine_coarse_price_mismatch','first_barrier':'stop','raw_price':str(stop)}
    observed=combined.cache_observed_at
    if observed is not None:base['information_available_at']=max(end,observed,coarse.cache_observed_at or end).isoformat()
    base['volume_matches']=combined.volume==coarse.volume
    for row in selected:
        side=None;price=None;status='ordered_fine_barrier'
        if row.open<=stop:side,price,status='stop',row.open,'ordered_fine_stop_gap'
        elif row.open>=target:side,price,status='target',row.open,'ordered_fine_target_gap'
        elif row.low<=stop:
            side,price='stop',stop
            if row.high>=target:status='unresolved_same_fine_bar_adverse_stop'
        elif row.high>=target:side,price='target',target
        if side is not None:return {**base,'status':status,'first_barrier':side,'raw_price':str(price),
            'first_touch_minute':row.open_time.isoformat(),'fine_bar_order_exact':False}
    raise ValueError('matching coarse extremes lack a fine barrier touch')
