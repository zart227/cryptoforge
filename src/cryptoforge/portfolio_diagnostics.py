"""Activity and cash diagnostics for development portfolios; no promotion."""
from collections import Counter
from datetime import UTC
from decimal import Decimal
from cryptoforge.equity_blocks import daily_changes,block_interval


def portfolio_diagnostics(outcome,signals,*,initial_capital=None):
    generated=sum(len(values) for values in signals.values());trades=outcome.trades
    reasons=Counter(row['reason'] for row in outcome.rejections)
    if generated!=len(trades)+len(outcome.rejections):
        raise ValueError('portfolio signal accounting is incomplete')
    wins=sum((trade.net_pnl for trade in trades if trade.net_pnl>0),Decimal(0))
    losses=-sum((trade.net_pnl for trade in trades if trade.net_pnl<0),Decimal(0))
    net=sum((trade.net_pnl for trade in trades),Decimal(0))
    fees=sum((trade.fees for trade in trades),Decimal(0))
    def grouped(key):
        groups={}
        for trade in trades:groups.setdefault(key(trade),[]).append(trade)
        return {name:{'trades':len(values),'net_pnl':str(sum((trade.net_pnl for trade in values),Decimal(0))),
                      'fees':str(sum((trade.fees for trade in values),Decimal(0))),
                      'positive_trades':sum(trade.net_pnl>0 for trade in values)} for name,values in sorted(groups.items())}
    by_pair=grouped(lambda trade:trade.pair)
    by_day=grouped(lambda trade:trade.entry_time.astimezone(UTC).date().isoformat())
    best=sorted((trade.net_pnl for trade in trades),reverse=True)[:2]
    report={'entry_risk_policy':'per_signal_ex_ante_plan' if outcome.entry_risk_plans else 'fixed_configuration',
        'recorded_entry_risk_plans':len(outcome.entry_risk_plans),'drawdown_semantics':outcome.drawdown_semantics,'by_pair':by_pair,'by_entry_day':by_day,
        'cash_only_baseline':{'net_pnl':'0','fees':'0','assumption':'idle_cash_no_interest'},
        'excess_net_over_cash_only':str(net),
        'net_without_two_best_trades':str(net-sum(best,Decimal(0))) if len(trades)>2 else None,
        'distinct_entry_days':len(by_day),'distinct_traded_pairs':len(by_pair),
        'maximum_pair_trade_fraction':str(Decimal(max((v['trades'] for v in by_pair.values()),default=0))/len(trades)) if trades else None,
        'maximum_entry_day_trade_fraction':str(Decimal(max((v['trades'] for v in by_day.values()),default=0))/len(trades)) if trades else None,
        'grouping_scope':'attribution_of_one_shared_wallet_not_independent_subportfolios',
        'generated_signals' :generated,'executed_trades':len(trades),'rejected_signals':len(outcome.rejections),
        'rejection_reasons':dict(reasons),'positive_trades':sum(trade.net_pnl>0 for trade in trades),
        'negative_trades':sum(trade.net_pnl<0 for trade in trades),'zero_trades':sum(trade.net_pnl==0 for trade in trades),
        'total_fees':str(fees),'net_pnl':str(net),
        'net_per_executed_trade':str(net/len(trades)) if trades else None,
        'net_per_generated_signal':str(net/generated) if generated else None,
        'profit_factor':str(wins/losses) if losses else None,
        'no_loss_sample':losses==0,'no_trade_sample':not trades,
        'fee_erased_price_gains':sum(trade.exit_price>trade.entry_price and trade.net_pnl<=0 for trade in trades),
        'independent_evidence':False}
    if initial_capital is not None:
        blocks=daily_changes(outcome,initial_capital=initial_capital)
        report['daily_equity_blocks']=blocks
        report['development_block_interval']=block_interval(blocks['bootstrap_eligible_full_days'])
    return report
