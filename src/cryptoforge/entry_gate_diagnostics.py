"""Explain recent entry decisions without relaxing an execution or learning gate."""
from collections import Counter
from datetime import timedelta
from cryptoforge.live_learning_protocol import time

SIGNAL_FLAGS={'trend','breakout','bounce','pullback','emerging_momentum','intraday_reversion'}
FIXED_CONSTRAINTS={'not enough candles':'insufficient_candles','latest candle is stale':'stale_candle',
    'open order already exists':'open_order','no entry slots remaining in this cycle':'cycle_position_limit',
    'insufficient USDT balance':'insufficient_cash','order below minimum notional':'entry_minimum',
    'ml_gate=reject':'model_probability'}


def _constraint(reason):
    if reason in FIXED_CONSTRAINTS:return FIXED_CONSTRAINTS[reason]
    if reason.startswith('entry rejected: exit would be below exchange minimum'):return 'exit_minimum'
    if reason.startswith('dust risk too high:'):return 'dust_budget'
    if reason.startswith('ml_fallback='):return 'model_fallback'
    return None


def analyze_entry_decisions(rows, *, as_of, truncated=False, lookback_minutes=15):
    if as_of.tzinfo is None or type(lookback_minutes) is not int or not 1<=lookback_minutes<=60:
        raise ValueError('aware bounded decision window required')
    start=as_of-timedelta(minutes=lookback_minutes);counts=Counter();fallbacks=Counter();included=0
    pairs={};constraints=Counter();flags=Counter();unclassified_rejections=0
    for row in rows:
        stamp=time(row['decided_at'])
        if not start<=stamp<=as_of:continue
        included+=1;counts[row['decision']]+=1
        pair=str(row.get('pair') or 'unknown_pair')
        group=pairs.setdefault(pair,{'decisions':Counter(),'ml_fallback_rejections':Counter(),
                                    'entry_constraints':Counter(),'observed_signal_flags':Counter()})
        group['decisions'][row['decision']]+=1
        row_constraints=set()
        for reason in set(str(reason) for reason in (row.get('reasons') or [])):
            key,separator,value=reason.partition('=')
            if separator and key in SIGNAL_FLAGS and value in {'True','False'}:
                flags[reason]+=1;group['observed_signal_flags'][reason]+=1
            if row['decision'] in {'hold','reject_entry'}:
                category=_constraint(reason)
                if category:row_constraints.add(category)
        for category in row_constraints:
            constraints[category]+=1;group['entry_constraints'][category]+=1
        if row['decision']=='reject_entry' and not row_constraints:unclassified_rejections+=1
        if row['decision']=='reject_entry':
            for reason in set(row.get('reasons') or []):
                if str(reason).startswith('ml_fallback='):
                    fallbacks[str(reason)]+=1;group['ml_fallback_rejections'][str(reason)]+=1
    stale=fallbacks['ml_fallback=no_fresh_model']
    status='observed_no_fresh_model_rejections' if stale else 'no_fresh_model_rejection_not_observed'
    if truncated:status='partial_decision_window'
    return {'as_of':as_of.isoformat(),'requested_start':start.isoformat(),'returned_rows':len(rows),
        'included_rows':included,'truncated':bool(truncated),'decisions':dict(counts),'ml_fallback_rejections':dict(fallbacks),
        'status':status,'no_fresh_model_rejections':stale,'sample_growth_guaranteed':False,
        'by_pair':{pair:{key:dict(value) for key,value in group.items()} for pair,group in sorted(pairs.items())},
        'entry_constraints':dict(constraints),'observed_signal_flags':dict(flags),
        'unclassified_rejections':unclassified_rejections,
        'signal_flags_are_observations_not_individual_causal_blockers':True,
        'scope':'observed_decisions_not_active_registry_certification_or_future_buy_guarantee',
        'changes_readiness_gates':False,'live_policy_changed':False}


def current_gate_diagnostic(report, *, now, maximum_age_seconds=300):
    try:
        age=(now-time(report['as_of'])).total_seconds()
        if not 0<=age<=maximum_age_seconds:return {'status':'recent_decision_diagnostic_stale_or_future','live_policy_changed':False}
        return report
    except (KeyError,ValueError,TypeError):
        return {'status':'recent_decision_diagnostic_unavailable','live_policy_changed':False}
