from copy import deepcopy
import pytest
from cryptoforge.development_screen import screen_development_comparison
from test_paired_portfolio import compare
from test_trade_simulator import history


def screen(comparison):
    return screen_development_comparison(comparison,minimum_trades=10,minimum_profit_factor='1.2',maximum_drawdown='.05')


def test_cash_and_fee_losses_are_rejected_without_champion_admission():
    rows=history();base={'ETH/USDT':[rows[0].open_time]}
    result=screen(compare({'ETH/USDT':rows},base,{}))
    assert not result['economic_screen_passed']
    assert {'no_trade_sample','positive_net_pnl','minimum_trades','profit_factor'}<={f['gate'] for f in result['failures']}
    assert not result['independent_admission_granted']
    result=screen(compare({'ETH/USDT':rows},base,base))
    assert any(f['gate']=='positive_net_pnl' and f['role']=='stress_filtered' for f in result['failures'])


def test_corrupt_cash_balance_cannot_be_screened_as_income():
    rows=history();comparison=deepcopy(compare({'ETH/USDT':rows},{},{}))
    comparison['roles']['filtered']['net_pnl']='100'
    with pytest.raises(ValueError,match='inconsistent'):
        screen(comparison)


def test_economic_pass_still_cannot_grant_independent_or_live_admission():
    rows=history();comparison=deepcopy(compare({'ETH/USDT':rows},{},{}))
    for name in ('filtered','stress_filtered'):
        comparison['roles'][name].update(executed_trades=20,positive_trades=15,negative_trades=5,
            zero_trades=0,generated_signals=20,rejected_signals=0,
            net_pnl='1',final_cash='101',profit_factor='1.5',drawdown_bound='.01')
    result=screen(comparison)
    assert result['economic_screen_passed']
    assert not result['independent_admission_granted'] and not result['live_promotion_allowed']
    comparison['roles']['filtered']['known_exit_minimum_violations']=1
    failed=screen(comparison)
    assert not failed['economic_screen_passed']
    assert any(row['gate']=='exit_minimum_violations' for row in failed['failures'])


def test_inflated_trade_count_is_not_support(tmp_path):
    rows=history();comparison=deepcopy(compare({'ETH/USDT':rows},{},{}))
    comparison['roles']['filtered']['executed_trades']=100
    with pytest.raises(ValueError,match='outcome counts'):screen(comparison)


@pytest.mark.parametrize('field',['open_positions_at_end','open_cost_basis_at_end','known_exit_minimum_violations'])
def test_missing_execution_accounting_cannot_be_an_economic_pass(field):
    rows=history();comparison=deepcopy(compare({'ETH/USDT':rows},{},{}))
    for name in ('filtered','stress_filtered'):
        comparison['roles'][name].update(executed_trades=20,positive_trades=15,negative_trades=5,
            zero_trades=0,generated_signals=20,rejected_signals=0,
            net_pnl='1',final_cash='101',profit_factor='1.5',drawdown_bound='.01')
    comparison['roles']['filtered'].pop(field)
    result=screen(comparison)
    assert not result['economic_screen_passed']
    assert {'role':'filtered','gate':'unknown_execution_accounting','field':field} in result['failures']


def test_strict_open_inventory_is_rejected_with_reconciled_cash_and_basis():
    from dataclasses import replace
    from decimal import Decimal as D
    from cryptoforge.paired_portfolio import compare_filtered_portfolios
    from cryptoforge.trade_simulator import SimulationConfig
    from test_paired_portfolio import POLICY
    rows=history()
    rows=[replace(row,open=D(40),high=D(41),low=D(39),close=D(40)) if i>=2 else row for i,row in enumerate(rows)]
    signals={'ETH/USDT':[rows[0].open_time]}
    comparison=compare_filtered_portfolios({'ETH/USDT':rows},signals,signals,
        SimulationConfig(capital=D(100),stake=D(10),fee=D(0),slippage=D(0),exit_minimum_policy='preserve_inventory'),
        stress_multiplier=2,bootstrap_policy=POLICY)
    result=screen(comparison)
    assert not result['economic_screen_passed']
    assert any(row['gate']=='unclosed_inventory' for row in result['failures'])
