"""Shared-wallet daily equity blocks; development uncertainty, no promotion."""
from datetime import UTC,timedelta,date
from decimal import Decimal
import math,random


def daily_changes(outcome,*,initial_capital):
    capital=Decimal(initial_capital)
    if not capital.is_finite() or capital<=0:raise ValueError('positive finite capital required')
    if outcome.equity_time_semantics!='candle_close_available_at':raise ValueError('explicit close availability contract required')
    days={};previous_time=None
    for stamp,equity in outcome.equity:
        if stamp.tzinfo is None or (previous_time is not None and stamp<=previous_time):raise ValueError('aware monotonic equity observations required')
        previous_time=stamp;value=Decimal(equity)
        if not value.is_finite() or value<0:raise ValueError('unknown or invalid equity cannot become a daily block')
        # Exactly midnight is the close of the preceding UTC bar/day.
        day=(stamp.astimezone(UTC)-timedelta(microseconds=1)).date()
        days[day]=value
    ordered=sorted(days)
    if any(b-a!=timedelta(days=1) for a,b in zip(ordered,ordered[1:])):raise ValueError('missing equity day cannot be filled')
    partial=set()
    if outcome.equity and ordered:
        spacing=outcome.equity[1][0]-outcome.equity[0][0] if len(outcome.equity)>1 else None
        if spacing is None:partial.update(ordered)
        else:
            if any(b[0]-a[0]!=spacing for a,b in zip(outcome.equity,outcome.equity[1:])):
                raise ValueError('irregular equity grid cannot certify complete days')
            window_start=(outcome.equity[0][0]-spacing).astimezone(UTC)
            window_end=outcome.equity[-1][0].astimezone(UTC)
            if window_start.time().isoformat()!='00:00:00':partial.add(ordered[0])
            if window_end.time().isoformat()!='00:00:00':partial.add(ordered[-1])
    changes={};previous=capital
    for day in ordered:
        changes[day.isoformat()]=str((days[day]-previous)/capital);previous=days[day]
    return {'partial_boundary_days':[day.isoformat() for day in sorted(partial)],
            'bootstrap_eligible_full_days':{key:value for key,value in changes.items() if date.fromisoformat(key) not in partial},
            'daily_changes_fraction_initial_capital':changes,'scope':'one_shared_wallet_all_pairs_together',
            'boundary_days_may_be_partial':True,'realized_trade_sums_used':False,'live_promotion_allowed':False}


def block_interval(changes,*,minimum_days=14,block_days=2,repetitions=2000,seed=20261009):
    if type(seed) is not int:
        raise ValueError('explicit integer bootstrap seed required')
    if any(type(v) is not int or v<1 for v in (minimum_days,block_days,repetitions)) or repetitions<100 or block_days>minimum_days:
        raise ValueError('invalid fixed bootstrap design')
    dates=[date.fromisoformat(key) for key in sorted(changes)]
    if any(day.isoformat()!=key for day,key in zip(dates,sorted(changes))) or any(b-a!=timedelta(days=1) for a,b in zip(dates,dates[1:])):
        raise ValueError('complete canonical calendar blocks required')
    values=[float(value) for key,value in sorted(changes.items())]
    if not all(math.isfinite(v) for v in values):raise ValueError('finite daily changes required')
    result={'days':len(values),'block_days':block_days,'repetitions':repetitions,'seed':seed,
            'method':'circular_time_block_bootstrap_shared_wallet','interval':'two_sided_95_percent',
            'live_promotion_allowed':False,'independent_evidence':False}
    if len(values)<minimum_days:return {**result,'status':'insufficient_calendar_days','interval_lower':None,'interval_upper':None}
    rng=random.Random(seed);draws=[]
    for _ in range(repetitions):
        sample=[]
        while len(sample)<len(values):
            start=rng.randrange(len(values));sample.extend(values[(start+i)%len(values)] for i in range(block_days))
        draws.append(sum(sample[:len(values)])/len(values))
    draws.sort()
    return {**result,'status':'development_interval_only','mean_daily_change':sum(values)/len(values),
            'interval_lower':draws[int((len(draws)-1)*.025)],'interval_upper':draws[int((len(draws)-1)*.975)]}
