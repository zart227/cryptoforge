"""The independent audit must detect plausible but incorrect risk bounds."""
from dataclasses import replace
from decimal import Decimal as D
import pytest
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from test_trade_simulator import history

from scripts.audit_trade_labels import verify_trade


def test_independent_risk_audit_rejects_ordered_but_wrong_bounds():
    rows=history(count=100)
    rows[37]=replace(rows[37],low=D(97),high=D(105))
    cfg=SimulationConfig(stake=D(10),fee=D(0),slippage=D(0),hold_bars=3)
    label=build_trade_labels('ETH/USDT',rows,cfg)[0]
    verify_trade(label,rows,cfg)
    wrong={**label.risk_outcome,'maximum_favorable_price_fraction_upper_bound':D('.04')}
    with pytest.raises(AssertionError):verify_trade(replace(label,risk_outcome=wrong),rows,cfg)


def test_independent_risk_audit_rejects_plausible_but_wrong_duration():
    rows=history(count=100)
    cfg=SimulationConfig(stake=D(10),fee=D(0),slippage=D(0),hold_bars=3)
    label=build_trade_labels('ETH/USDT',rows,cfg)[0]
    verify_trade(label,rows,cfg)
    wrong={**label.risk_outcome,'holding_seconds_lower_bound':0}
    with pytest.raises(AssertionError):verify_trade(replace(label,risk_outcome=wrong),rows,cfg)


def test_independent_labels_reconcile_bid_ask_spread_and_risk_bounds():
    rows=[replace(row,high=D(100),low=D(100)) for row in history(count=100)]
    cfg=SimulationConfig(stake=D(10),entry_fee=D('.001'),exit_fee=D('.002'),slippage=D('.001'),spread_fraction=D('.02'),stop_fraction=D('.1'),target_fraction=D('.2'),hold_bars=3)
    label=build_trade_labels('ETH/USDT',rows,cfg)[0]
    verify_trade(label,rows,cfg)
    assert label.trade.entry_price==D('101.101') and label.trade.exit_price==D('98.901')
    assert label.trade.net_pnl<0
