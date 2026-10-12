"""Reject weak development portfolios without granting independent admission."""
from decimal import Decimal


def _number(value):
    result=Decimal(str(value))
    if isinstance(value,bool) or not result.is_finite():raise ValueError('finite screening metric required')
    return result


def screen_development_comparison(comparison, *, minimum_trades, minimum_profit_factor,
                                  maximum_drawdown):
    if type(minimum_trades) is not int or minimum_trades<1:raise ValueError('positive trade floor required')
    pf_floor=_number(minimum_profit_factor);dd_limit=_number(maximum_drawdown)
    if pf_floor<=1 or not 0<dd_limit<=1:raise ValueError('explicit profit/risk screening bounds required')
    capital=_number(comparison['initial_capital'])
    if capital<=0:raise ValueError('positive shared capital required')
    failures=[]
    for name in ('filtered','stress_filtered'):
        role=comparison['roles'][name]
        count=role['executed_trades']
        if type(count) is not int or count<0:raise ValueError('nonnegative executed trade count required')
        counts=[role[key] for key in ('positive_trades','negative_trades','zero_trades')]
        if any(type(value) is not int or value<0 for value in counts) or sum(counts)!=count:
            raise ValueError('inconsistent trade outcome counts')
        generated,rejected=role['generated_signals'],role['rejected_signals']
        if any(type(value) is not int or value<0 for value in (generated,rejected)) or generated!=count+rejected:
            raise ValueError('inconsistent signal accounting')
        if _number(role['total_fees'])<0:raise ValueError('nonnegative fees required')
        pnl=_number(role['net_pnl']);cash=_number(role['final_cash']);drawdown=_number(role['drawdown_bound'])
        if cash<0 or not 0<=drawdown<=1 or abs(cash-capital-pnl)>Decimal('1e-18'):
            raise ValueError('inconsistent shared-wallet screening metrics')
        pf=None if role['profit_factor'] is None else _number(role['profit_factor'])
        if pf is not None and pf<0:raise ValueError('nonnegative profit factor required')
        if count<minimum_trades:failures.append({'role':name,'gate':'minimum_trades','actual':count,'required':minimum_trades})
        if pnl<=0:failures.append({'role':name,'gate':'positive_net_pnl','actual':str(pnl)})
        if count==0:failures.append({'role':name,'gate':'no_trade_sample'})
        # Unknown PF from a no-loss sample is not promoted to infinity.
        if pf is None or pf<pf_floor:
            failures.append({'role':name,'gate':'profit_factor','actual':None if pf is None else str(pf),'required':str(pf_floor)})
        if drawdown>dd_limit:failures.append({'role':name,'gate':'drawdown','actual':str(drawdown),'maximum':str(dd_limit)})
    return {'economic_screen_passed':not failures,'failures':failures,
        'independent_admission_granted':False,'live_promotion_allowed':False,
        'scope':'descriptive_development_screen_not_independent_test_or_execution_qualification'}
