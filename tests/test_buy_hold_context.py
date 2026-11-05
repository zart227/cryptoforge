from dataclasses import replace
from decimal import Decimal as D
from cryptoforge.buy_hold_context import buy_hold_context
from cryptoforge.trade_simulator import SimulationConfig
from test_trade_simulator import history


def test_passive_stake_keeps_rest_of_capital_idle_and_counts_both_fees():
    rows=history()
    result=buy_hold_context({'ETH/USDT':rows},SimulationConfig(capital=D(100),stake=D(10),quantity_step=D('.001'),fee=D('.001'),slippage=D(0)),entry_index=1)
    assert D(result['realized_net_pnl'])==D('-.0198')
    assert D(result['final_cash'])==D('99.9802') and len(result['entries'])==1
    assert not result['stop_and_target_policy_applied'] and not result['live_promotion_allowed']


def test_passive_gap_preserves_unsellable_quantity_and_basis():
    rows=history();rows[-1]=replace(rows[-1],open=D(40),low=D(39),high=D(41),close=D(40))
    result=buy_hold_context({'ETH/USDT':rows},SimulationConfig(capital=D(100),stake=D(10),fee=D(0),slippage=D(0)),entry_index=1)
    assert result['realized_net_pnl']=='0' and result['final_cash']=='90.0'
    assert D(result['remaining_basis'])==10 and len(result['open_positions'])==1


def test_each_basket_entry_cannot_reuse_initial_capital():
    eth=history();btc=history('BTC/USDT')
    result=buy_hold_context({'ETH/USDT':eth,'BTC/USDT':btc},SimulationConfig(capital=D(10),stake=D(10),fee=D(0),slippage=D(0)),entry_index=1)
    assert len(result['entries'])==1 and result['rejections'][0]['reason']=='insufficient_cash'
