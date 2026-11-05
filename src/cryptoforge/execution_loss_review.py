"""Describe observed FIFO losses without inferring strategy or counterfactual fills."""
from decimal import Decimal


def review_losses(rows, *, recent_limit=20):
    if type(recent_limit) is not int or not 1 <= recent_limit <= 200:
        raise ValueError('bounded positive recent case limit required')
    closed=[row for row in rows if row['status']=='closed']
    identities=[row['external_trade_id'] for row in closed]
    if len(set(identities))!=len(identities):
        raise ValueError('unique FIFO segment identities required')
    known=[];unknown=0
    for row in closed:
        if row['realized_pnl'] is None or row['fee_amount'] is None:
            unknown+=1;continue
        pnl=Decimal(row['realized_pnl']);fee=Decimal(row['fee_amount']);basis=Decimal(row['stake_amount'])
        if not all(value.is_finite() for value in (pnl,fee,basis)) or basis<=0:
            raise ValueError('finite known result and positive basis required')
        pct=pnl/basis
        if Decimal(row['realized_pnl_pct'])!=pct:
            raise ValueError('recorded return differs from allocated basis')
        known.append({'source_segment':dict(row), 'net_return':str(pct),
            'recorded_fee_quote_equivalent':str(fee), 'fee_equivalent_over_basis':str(fee/basis),
            'net_plus_recorded_fee_equivalent':str(pnl+fee),
            'fee_equivalent_erased_nonnegative_result':pnl<0 and pnl+fee>=0,
            'loss_at_least_one_percent':pct<=Decimal('-.01'),
            'strategy_attribution_known':False,
            'counterfactual_no_fee_profit_certified':False})
    known.sort(key=lambda case:(case['source_segment']['closed_at'],case['source_segment']['external_trade_id']))
    return {'known_closed_segments':len(known),'unknown_fee_or_pnl_segments':unknown,
        'loss_segments':sum(Decimal(case['net_return'])<0 for case in known),
        'loss_at_least_one_percent_segments':sum(case['loss_at_least_one_percent'] for case in known),
        'fee_equivalent_erased_nonnegative_segments':sum(case['fee_equivalent_erased_nonnegative_result'] for case in known),
        'recent_cases':known[-recent_limit:], 'recent_limit':recent_limit,
        'segments_may_share_orders':True,'independent_trades_certified':False,
        'strategy_improvement_established':False,'live_promotion_allowed':False}
