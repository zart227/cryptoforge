"""Experimental cash recovery labels: tiny residual inventory is valued at zero.

This is a separate conservative objective, never a fully closed trade result.
One buy order yields one example; closing fills are not independent samples.
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from math import isfinite

from cryptoforge.live_experience import _order, _time,original_input_contract
from cryptoforge.model_training import FEATURE_VERSION, TrainingExample

TARGET_VERSION = 'spot-long-real-cash-recovery-dust-zero-v1'
MAX_RESIDUAL_COST_FRACTION = Decimal('.01')


def build_cash_recovery(trades, decisions, observations, *, observed_at: datetime,
                        source_as_of: datetime, accounting_quality_verified: bool,
                        truncated=False):
    if observed_at.tzinfo is None or source_as_of.tzinfo is None or source_as_of>observed_at:
        raise ValueError('ordered timezone-aware snapshot times required')
    result={'target_version':TARGET_VERSION,'examples':[],'excluded':[],
            'snapshot_observed_at':observed_at.isoformat(),'source_as_of':source_as_of.isoformat(),
            'accounting_quality_verified':accounting_quality_verified,'snapshot_truncated':bool(truncated),
            'residual_value_policy':'zero_conservative_cash_recovery_not_total_equity',
            'maximum_residual_cost_fraction':str(MAX_RESIDUAL_COST_FRACTION),
            'live_eligible':False,'automatic_training_allowed':False}
    if not accounting_quality_verified or truncated:
        result['excluded']=[{'reason':'unverified_or_truncated_snapshot'}];return result
    contexts={};groups={};seen=set()
    for context in decisions:
        if context.get('decision')!='approve_entry':continue
        context_features=context.get('features') or {}
        context_order=context_features.get('order') or {}
        order_result=context_order.get('result') or {}
        order=order_result.get('orderId') if isinstance(order_result,dict) else None
        if order:contexts[context['pair'],str(order)]=context
    for row in trades:
        identity=str(row.get('idempotency_key') or '')
        if not identity.startswith('bybit:spot:fifo:') or row.get('mode')!='live':continue
        if identity in seen:raise ValueError('duplicate execution row')
        seen.add(identity)
        if _time(row['opened_at'])>source_as_of:continue
        order=_order(row.get('entry_reason'))
        if order:groups.setdefault((row['pair'],order),[]).append(row)
    for (pair,order),rows in groups.items():
        try:
            example=_example(pair,order,rows,contexts.get((pair,order)),observations.get(pair),
                             observed_at,source_as_of)
        except (ValueError,ArithmeticError,TypeError,KeyError) as error:
            result['excluded'].append({'pair':pair,'entry_order':order,'reason':str(error)});continue
        result['examples'].append(example)
    return result


def _example(pair,order,rows,context,observation,observed,cutoff):
    closed=[row for row in rows if row['status']=='closed']
    remaining=[row for row in rows if str(row['idempotency_key']).endswith(':remaining')]
    if not closed or not remaining:raise ValueError('no_closed_execution_or_remainder_proof')
    if any(_time(row['closed_at'])>cutoff for row in closed):raise ValueError('future_close_not_available')
    if any('origin=cryptoforge' not in str(row.get('entry_reason')) for row in closed+remaining):
        raise ValueError('external_acquisition')
    if any('origin=cryptoforge' not in str(row.get('exit_reason')) or
           (_order(row.get('exit_reason')) or '').startswith('conversion:') for row in closed):
        raise ValueError('external_exit')
    if any(row.get('fee_amount') is None or row.get('realized_pnl') is None for row in closed):
        raise ValueError('unknown_fees_or_pnl')
    if any(not Decimal(str(row['stake_amount'])).is_finite() or Decimal(str(row['stake_amount']))<=0
           or not Decimal(str(row['amount'])).is_finite() or Decimal(str(row['amount']))<=0 for row in closed):
        raise ValueError('invalid_closed_execution_cost_or_quantity')
    fees=[Decimal(str(row['fee_amount'])) for row in closed]
    if not all(fee.is_finite() for fee in fees):raise ValueError('nonfinite_fees')
    features=(context or {}).get('features') or {}
    if features.get('feature_capture_status')!='complete' or features.get('feature_version')!=FEATURE_VERSION:
        raise ValueError('missing_original_features')
    feature_time=_time(features['feature_observed_at'])
    if feature_time.tzinfo is None or feature_time>min(_time(row['opened_at']) for row in closed):
        raise ValueError('features_not_known_before_entry')
    values=tuple(float(value) for value in features['model_feature_values'])
    if len(values)!=7 or not all(isfinite(value) for value in values):raise ValueError('invalid_features')
    input_contract=original_input_contract(features)
    quantities=[];costs=[]
    for row in remaining:
        qty=Decimal(str(row['amount']));cost=Decimal(str(row.get('stake_amount','0')))
        if not qty.is_finite() or not cost.is_finite() or qty<0 or cost<0:
            raise ValueError('invalid_remainder')
        if row['status'] not in {'open','cancelled'} or (row['status']=='cancelled' and (qty or cost)):
            raise ValueError('unresolved_remainder_status')
        quantities.append(qty);costs.append(cost)
    residual_qty=sum(quantities,Decimal(0));residual_cost=sum(costs,Decimal(0))
    closed_cost=sum((Decimal(str(row['stake_amount'])) for row in closed),Decimal(0))
    closed_pnl=sum((Decimal(str(row['realized_pnl'])) for row in closed),Decimal(0))
    total_cost=closed_cost+residual_cost
    if not all(value.is_finite() for value in (closed_cost,closed_pnl,total_cost)) or closed_cost<=0:
        raise ValueError('invalid_cost_or_pnl')
    if bool(residual_qty)!=bool(residual_cost):raise ValueError('inconsistent_remainder_cost')
    if residual_cost/total_cost>MAX_RESIDUAL_COST_FRACTION:
        raise ValueError('material_residual_cost')
    dust_reason='zero_remainder'
    if residual_qty:
        if not observation or _time(observation['observed_at'])>observed:
            raise ValueError('instrument_observation_unavailable')
        instrument_time=_time(observation['observed_at'])
        quote_time=_time(observation['quote_observed_at'])
        if not timedelta(0)<=observed-instrument_time<=timedelta(minutes=5) or not instrument_time<=quote_time<=observed:
            raise ValueError('stale_or_future_instrument_quote')
        if _time(observation['observed_at'])<max(_time(row['closed_at']) for row in closed):
            raise ValueError('instrument_observation_before_exit')
        raw=observation['instrument']
        if observation.get('category')!='spot' or raw['symbol']!=pair.replace('/','') or raw.get('status')!='Trading':
            raise ValueError('instrument_identity_or_status_unknown')
        lot=raw['lotSizeFilter'];step=Decimal(str(lot['basePrecision']))
        minimum=Decimal(str(lot['minOrderAmt']))
        if not step.is_finite() or not minimum.is_finite() or step<=0 or minimum<=0:
            raise ValueError('invalid_instrument_filters')
        rounded=(residual_qty/step).to_integral_value(rounding=ROUND_DOWN)*step
        if not rounded:dust_reason='below_observed_quantity_precision'
        else:
            bid=Decimal(str(observation['bid_price']))
            if not bid.is_finite() or bid<=0:raise ValueError('unknown_market_bid')
            if rounded*bid>=minimum:raise ValueError('residual_market_sellable')
            dust_reason='below_observed_market_minimum_notional'
    net=closed_pnl-residual_cost
    model_example=TrainingExample(pair,feature_time,values,int(net>0),0,float(net/total_cost),observed)
    return {'pair':pair,'entry_order':order,'example':model_example,
            **({'feature_input_contract':input_contract} if input_contract is not None else {}),
            'target_version':TARGET_VERSION,'feature_version':FEATURE_VERSION,
            'entry_at':min(_time(row['opened_at']) for row in closed+remaining).isoformat(),
            'input_candle_state':features.get('model_input_candle_state','unknown'),
            'closed_cost':str(closed_cost),'residual_cost':str(residual_cost),
            'residual_quantity':str(residual_qty),'cost':str(total_cost),'closed_net_pnl':str(closed_pnl),
            'cash_recovery_net':str(net),'dust_reason':dust_reason,'source_segments':len(closed),
            'closed_at':max(_time(row['closed_at']) for row in closed).isoformat(),
            'earliest_close_at':min(_time(row['closed_at']) for row in closed).isoformat(),
            'label_available_at':observed.isoformat(),'instrument_observation':observation if residual_qty else None,
            'fully_closed':residual_qty==0,'actual_residual_inventory_preserved':True}
