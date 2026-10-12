from dataclasses import replace
from decimal import Decimal as D
import pytest

from test_trade_simulator import history
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig, simulate_portfolio
from cryptoforge.model_training import chronological_splits


def config(**kwargs):
    return SimulationConfig(stake=D(10),fee=D(0),slippage=D(0),hold_bars=3,**kwargs)


@pytest.mark.parametrize('low,high,reason,label',[
    ('99','105','target',1),('97','101','stop',0),('97','105','stop',0)])
def test_labels_match_simulator_and_net_outcome(low,high,reason,label):
    rows=history(count=100)
    rows[37]=replace(rows[37],low=D(low),high=D(high))
    result=build_trade_labels('ETH/USDT',rows,config())[0]
    assert result.example.label==label
    assert result.trade.exit_reason==reason
    reference=simulate_portfolio({'ETH/USDT':rows[36:41]},
                                 {'ETH/USDT':[rows[36].open_time]},config())
    assert result.trade==reference.trades[0]
    assert result.net_return==float(result.trade.net_pnl/result.trade.cost)
    assert result.label_end_time==result.trade.exit_time+(rows[1].open_time-rows[0].open_time)


def test_fees_rejections_and_no_incomplete_horizon_labels():
    rows=history(count=100)
    labelled=build_trade_labels('ETH/USDT',rows,SimulationConfig(hold_bars=3))
    assert labelled[0].example.label==0
    assert labelled[0].net_return<0
    assert all(row.trade.exit_reason!='end_of_data' for row in labelled)
    rejected=build_trade_labels('ETH/USDT',rows,config(min_notional=D(20)))
    assert all(row.status=='rejected' and row.example is None for row in rejected)
    assert rejected[0].rejection_reason=='minimum_order'


def test_future_changes_affect_labels_not_features_and_purge_is_preserved():
    rows=history(count=160)
    changed=list(rows)
    changed[37]=replace(changed[37],high=D(105))
    original=build_trade_labels('ETH/USDT',rows,config())
    altered=build_trade_labels('ETH/USDT',changed,config())
    assert original[0].example.features==altered[0].example.features
    assert original[0].example.label!=altered[0].example.label
    train,validation,test=chronological_splits([row.example for row in altered])
    assert max(e.label_end_time for e in train)<validation[0].open_time
    assert max(e.label_end_time for e in validation)<test[0].open_time


def test_gap_rejected_before_labeling():
    rows=history(count=100)
    with pytest.raises(ValueError,match='continuous'):
        build_trade_labels('ETH/USDT',rows[:70]+rows[71:],config())


def test_numeric_target_is_net_return_even_when_fees_erase_price_gain():
    from cryptoforge.trade_labels import TARGET_VERSION
    rows=history(count=100)
    for index in range(37,41):rows[index]=replace(rows[index],open=D('100.1'),close=D('100.1'),high=D('100.2'),low=D('99.9'))
    rows[37]=replace(rows[37],open=D('100'),close=D('100'))
    cfg=SimulationConfig(stake=D('10'),hold_bars=3,fee=D('.0018'),slippage=D('0'))
    outcome=build_trade_labels('ETH/USDT',rows,cfg)[0]
    assert outcome.trade.exit_price>outcome.trade.entry_price
    assert outcome.example.label==0 and outcome.example.future_return<0
    assert outcome.example.future_return==outcome.net_return
    assert TARGET_VERSION=='spot-long-trade-net-v2'


def test_independent_arithmetic_audit_supports_asymmetric_fees():
    from scripts.audit_trade_labels import verify_trade
    rows=history(count=100)
    cfg=SimulationConfig(stake=D('10'),hold_bars=3,entry_fee=D('.001'),exit_fee=D('.003'))
    label=build_trade_labels('ETH/USDT',rows,cfg)[0]
    verify_trade(label,rows,cfg)
    assert label.example.future_return==label.net_return
