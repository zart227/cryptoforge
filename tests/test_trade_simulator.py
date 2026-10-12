from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import pytest

from cryptoforge.supabase_executor import CandleRow
from cryptoforge.trade_simulator import SimulationConfig, simulate_portfolio


def history(pair='ETH/USDT',count=5):
    start=datetime(2026,1,1,tzinfo=UTC)
    return [CandleRow(pair,pair.replace('/',''),start+timedelta(minutes=5*i),
                      D(100),D(101),D(99),D(100),D(1000)) for i in range(count)]


def run(rows,**kwargs):
    cfg=SimulationConfig(capital=D(100),stake=D(10),fee=D(0),slippage=D(0),
                         quantity_step=D('0.001'),hold_bars=2,**kwargs)
    return simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)


def test_next_open_timeout_manual_balance_and_repeatability():
    rows=history()
    rows[3]=replace(rows[3],open=D(101),high=D(102),close=D(101))
    result=run(rows)
    trade=result.trades[0]
    assert trade.entry_time==rows[1].open_time
    assert trade.exit_time==rows[3].open_time
    assert trade.exit_reason=='timeout'
    assert trade.quantity==D('0.1')
    assert trade.net_pnl==D('0.1')
    assert result.final_cash==D('100.1')
    assert result==run(rows)
    assert result.live_eligible is False


@pytest.mark.parametrize('low,high,reason,ambiguous',[
    ('97','101','stop',False),('99','105','target',False),('97','105','stop',True)])
def test_barriers_and_conservative_ambiguous_order(low,high,reason,ambiguous):
    rows=history();rows[1]=replace(rows[1],low=D(low),high=D(high))
    trade=run(rows).trades[0]
    assert trade.exit_reason==reason
    assert trade.ambiguous==ambiguous


def test_gap_stop_fills_at_open_not_stop():
    rows=history(); rows[2]=replace(rows[2],open=D(90),low=D(89),high=D(91),close=D(90))
    trade=run(rows).trades[0]
    assert trade.exit_reason=='stop_gap'
    assert trade.exit_price==D(90)
    assert trade.net_pnl==D(-1)


def test_adverse_entry_fill_does_not_exit_at_a_stop_above_the_current_market():
    rows=history();cfg=SimulationConfig(stake=D(10),fee=D(0),slippage=D('.03'),stop_fraction=D('.02'))
    trade=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg).trades[0]
    assert trade.entry_price==D(103) and trade.exit_price==D(97)
    assert trade.entry_time==trade.exit_time and trade.exit_reason=='stop_gap'
    assert trade.exit_price < trade.entry_price*(1-cfg.stop_fraction)*(1-cfg.slippage)


def test_fees_are_counted_once_and_rounding_reserves_fees():
    rows=history()
    cfg=SimulationConfig(stake=D(10),fee=D('0.001'),slippage=D(0),quantity_step=D('0.001'),hold_bars=2)
    result=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)
    trade=result.trades[0]
    assert trade.quantity==D('0.099')
    assert trade.fees==D('0.0198')
    assert trade.net_pnl==-trade.fees
    assert result.final_cash==cfg.capital-trade.fees
    more=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},replace(cfg,fee=D('0.002')))
    assert more.final_cash < result.final_cash


@pytest.mark.parametrize('capital,max_positions,reason',[('10',3,'insufficient_cash'),('100',1,'position_limit')])
def test_shared_capital_and_position_limit(capital,max_positions,reason):
    eth=history();btc=history('BTC/USDT')
    result=simulate_portfolio({'ETH/USDT':eth,'BTC/USDT':btc},
        {pair:[rows[0].open_time] for pair,rows in [('ETH/USDT',eth),('BTC/USDT',btc)]},
        SimulationConfig(capital=D(capital),stake=D(10),max_positions=max_positions))
    assert len(result.trades)==1
    assert result.trades[0].pair=='BTC/USDT'
    assert result.rejections[0]['reason']==reason


def test_intrabar_exit_cannot_fund_an_earlier_opening_entry():
    eth=history();btc=history('BTC/USDT')
    btc[2]=replace(btc[2],high=D(105))
    result=simulate_portfolio({'ETH/USDT':eth,'BTC/USDT':btc},
        {'BTC/USDT':[btc[0].open_time],'ETH/USDT':[eth[1].open_time]},
        SimulationConfig(capital=D(10),stake=D(10),fee=D(0),slippage=D(0)))
    assert result.rejections[0]['reason']=='insufficient_cash'


def test_bad_history_and_order_filters():
    rows=history()
    with pytest.raises(ValueError,match='continuous'):
        run(rows[:2]+rows[3:])
    assert run(rows,min_notional=D(20)).rejections[0]['reason']=='minimum_order'
    rows[0]=replace(rows[0],volume=D(0))
    assert run(rows).rejections[0]['reason']=='liquidity_limit'


def test_delay_end_of_data_and_no_future_bar():
    rows=history()
    result=run(rows,entry_delay_bars=3)
    assert result.trades[0].entry_time==rows[3].open_time
    assert result.trades[0].exit_reason=='end_of_data'
    result=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[-1].open_time]})
    assert result.rejections[0]['reason']=='no_future_bar'
    assert not result.trades


def test_entry_and_exit_fees_are_distinct_and_stress_keeps_both():
    rows=history(count=6)
    cfg=SimulationConfig(stake=D('10'),hold_bars=2,fee=D('0'),slippage=D('0'),entry_fee=D('.001'),exit_fee=D('.003'))
    outcome=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)
    trade=outcome.trades[0]
    assert trade.cost==trade.quantity*trade.entry_price*D('1.001')
    assert trade.proceeds==trade.quantity*trade.exit_price*D('.997')
    assert trade.fees==trade.quantity*trade.entry_price*D('.001')+trade.quantity*trade.exit_price*D('.003')
    assert trade.net_pnl==trade.proceeds-trade.cost
    stressed=cfg.stress_costs(2)
    assert stressed.entry_fee==D('.002') and stressed.exit_fee==D('.006')
    assert simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},stressed).final_cash<outcome.final_cash


def test_legacy_symmetric_fee_is_preserved_and_invalid_side_fees_rejected():
    import pytest
    rows=history(count=6);cfg=SimulationConfig(hold_bars=2)
    explicit=replace(cfg,entry_fee=cfg.fee,exit_fee=cfg.fee)
    assert simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)==simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},explicit)
    for value in (D('-1'),D('1'),D('NaN')):
        with pytest.raises(ValueError):replace(cfg,entry_fee=value)
        with pytest.raises(ValueError):replace(cfg,exit_fee=value)


def test_equity_using_close_is_available_at_bar_close_not_at_open():
    rows=history(count=6)
    outcome=simulate_portfolio({'ETH/USDT':rows},{})
    step=rows[1].open_time-rows[0].open_time
    assert [stamp for stamp,value in outcome.equity]==[row.open_time+step for row in rows]
    assert outcome.equity_time_semantics=='candle_close_available_at'
    assert outcome.final_cash==SimulationConfig().capital


@pytest.mark.parametrize('field',['max_positions','hold_bars','entry_delay_bars'])
@pytest.mark.parametrize('value',[1.5,True,float('nan'),0])
def test_fractional_or_invalid_bar_counts_and_position_limits_are_rejected(field,value):
    with pytest.raises(ValueError,match='integers'):SimulationConfig(**{field:value})


def test_immediate_open_stop_drawdown_excludes_later_bar_extremes():
    rows=history();rows[1]=replace(rows[1],low=D(1))
    cfg=SimulationConfig(stake=D(10),fee=D(0),slippage=D('.03'),stop_fraction=D('.02'))
    result=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)
    assert result.trades[0].exit_reason=='stop_gap'
    assert result.trades[0].entry_time==result.trades[0].exit_time
    assert result.max_drawdown==1-result.final_cash/cfg.capital
    assert result.max_drawdown<D('.01')
    assert result.drawdown_semantics=='conservative_ohlc_low_liquidation_bound_not_exact_execution_path'


def test_symbol_identity_cannot_disagree_with_shared_wallet_pair():
    rows=history();rows[1]=replace(rows[1],symbol='BTCUSDT')
    with pytest.raises(ValueError,match='invalid candle'):
        simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]})


def test_separate_spread_scenario_charges_ask_and_bid_once():
    rows=[replace(row,high=D(100),low=D(100)) for row in history(count=5)]
    cfg=SimulationConfig(stake=D(10),fee=D(0),slippage=D(0),spread_fraction=D('.02'),stop_fraction=D('.1'),target_fraction=D('.2'),hold_bars=2)
    result=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)
    trade=result.trades[0]
    assert trade.entry_price==D(101) and trade.exit_price==D(99)
    assert trade.fees==0 and trade.net_pnl==trade.quantity*D(-2)
    assert result.spread_assumption=='ohlc_reference_with_scenario_spread_not_historical_bid_ask'
    stressed=cfg.stress_costs(2)
    assert stressed.spread_fraction==D('.04')
    assert simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},stressed).final_cash<result.final_cash


def test_zero_spread_keeps_old_numerical_result_and_spread_bid_triggers_stop():
    rows=history(count=5);cfg=SimulationConfig(hold_bars=2)
    assert simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg)==simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},replace(cfg,spread_fraction=D(0)))
    rows=[replace(row,high=D(100),low=D(100)) for row in rows]
    wide=replace(cfg,fee=D(0),slippage=D(0),spread_fraction=D('.06'))
    trade=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},wide).trades[0]
    assert trade.entry_price==D(103) and trade.exit_price==D(97)
    assert trade.entry_time==trade.exit_time and trade.exit_reason=='stop_gap'


def test_bounded_equity_details_reconcile_cash_basis_and_open_positions():
    rows=history(count=5);cfg=SimulationConfig(stake=D(10),fee=D(0),slippage=D(0),hold_bars=2)
    result=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]},cfg,capture_equity_details=True)
    opened=result.equity_snapshots[1]
    assert opened['available_at']==rows[2].open_time
    assert opened['cash']==D(90) and opened['open_cost_basis']==D(10)
    assert opened['open_positions'][0]['quantity']==D('.1')
    for snapshot,(_,equity) in zip(result.equity_snapshots,result.equity):
        assert snapshot['cash']+snapshot['open_cost_basis']==cfg.capital+snapshot['realized_net_pnl']
        assert snapshot['equity']==equity
    assert not result.equity_snapshots[-1]['open_positions']
    assert not simulate_portfolio({'ETH/USDT':rows},{},cfg).equity_snapshots
