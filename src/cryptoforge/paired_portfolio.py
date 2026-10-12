"""Paired development diagnostics for a baseline strategy and its ML filter."""
from decimal import Decimal

from cryptoforge.trade_simulator import simulate_portfolio
from cryptoforge.portfolio_diagnostics import portfolio_diagnostics
from cryptoforge.equity_blocks import daily_changes, block_interval


def compare_filtered_portfolios(data, baseline_signals, filtered_signals, config, *,
                                stress_multiplier, bootstrap_policy, entry_risks=None,
                                reference_signals=None):
    """Paired shared-wallet simulations; no signal selection or fitting.

    Each arm starts with the same capital. The filter can only remove original
    baseline opportunities. Paired uncertainty uses the difference of the same
    full UTC equity days, preserving all pairs together in each wallet.
    An optional frozen reference filter provides candidate-versus-current-model
    comparisons under the same ordinary and stressed execution assumptions.
    The caller must preregister inputs/configuration/bootstrap before calling.
    """
    if set(baseline_signals)-set(data) or set(filtered_signals)-set(data):
        raise ValueError('signal pairs must belong to comparison history')
    baseline,filtered={},{}
    for pair in data:
        base=tuple(baseline_signals.get(pair,()))
        selected=tuple(filtered_signals.get(pair,()))
        if len(set(base))!=len(base) or len(set(selected))!=len(selected):
            raise ValueError('duplicate comparison signal')
        if not set(selected)<=set(base):
            raise ValueError('ML filter must be a subset of baseline signals')
        baseline[pair]=base;filtered[pair]=selected
    reference=None
    if reference_signals is not None:
        if set(reference_signals)-set(data):raise ValueError('reference pair missing from history')
        reference={}
        for pair in data:
            stamps=tuple(reference_signals.get(pair,()))
            if len(set(stamps))!=len(stamps) or not set(stamps)<=set(baseline[pair]):
                raise ValueError('reference filter requires unique baseline subset')
            reference[pair]=stamps
    if entry_risks is not None:
        expected={(pair,stamp) for pair,stamps in baseline.items() for stamp in stamps}
        if set(entry_risks)!=expected:
            raise ValueError('exact baseline risk plan coverage required')
    if set(bootstrap_policy)!= {'minimum_days','block_days','repetitions','seed'}:
        raise ValueError('explicit fixed bootstrap policy required')
    # Validate the declared design before any simulations, including no-day case.
    block_interval({},**bootstrap_policy)
    stress=config.stress_costs(stress_multiplier)
    roles={};outcomes={}
    arms=[('baseline',baseline,config),('filtered',filtered,config),
          ('stress_baseline',baseline,stress),('stress_filtered',filtered,stress)]
    if reference is not None:arms.extend((('reference',reference,config),('stress_reference',reference,stress)))
    for name,signals,cfg in arms:
        risks=({(pair,stamp):entry_risks[(pair,stamp)] for pair,stamps in signals.items() for stamp in stamps}
               if entry_risks is not None else None)
        outcome=simulate_portfolio(data,signals,cfg,entry_risks=risks)
        outcomes[name]=outcome
        roles[name]=portfolio_diagnostics(outcome,signals)
        roles[name]['drawdown_bound']=str(outcome.max_drawdown)
        roles[name]['final_cash']=str(outcome.final_cash)
    differences={}
    comparisons=[(prefix,control) for prefix in ('','stress_')
                 for control in (('baseline','reference') if reference is not None else ('baseline',))]
    for prefix,control in comparisons:
        left,right=(outcomes[prefix+name] for name in ('filtered',control))
        if tuple(stamp for stamp,_ in left.equity)!=tuple(stamp for stamp,_ in right.equity):
            raise ValueError('paired portfolios require identical equity time grids')
        a=daily_changes(left,initial_capital=config.capital)
        b=daily_changes(right,initial_capital=config.capital)
        a_days,b_days=(item['bootstrap_eligible_full_days'] for item in (a,b))
        if set(a_days)!=set(b_days):
            raise ValueError('paired complete-day coverage mismatch')
        paired={day:str(Decimal(a_days[day])-Decimal(b_days[day])) for day in sorted(a_days)}
        differences[prefix+'filtered_minus_'+control]={
            'net_pnl_difference':str(left.final_cash-right.final_cash),
            'daily_equity_difference_fraction_initial_capital':paired,
            'excluded_partial_boundary_days':a['partial_boundary_days'],
            'block_interval':block_interval(paired,**bootstrap_policy)}
    return {'roles':roles,'paired_differences':differences,
            'initial_capital':str(config.capital),'stress_multiplier':str(stress_multiplier),
            'cash_only_baseline':{'final_cash':str(config.capital),'net_pnl':'0'},
            'filter_subset_of_baseline_verified':True,'model_selection_performed':False,
            'scope':'paired_development_shared_wallet_not_independent_profitability',
            'live_promotion_allowed':False,'independent_evidence':False}
