from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.entry_risk import atr_entry_risk,EntryRiskPlan
from cryptoforge.trade_simulator import simulate_portfolio,SimulationConfig
from test_trade_simulator import history


def test_atr_uses_only_past_complete_closed_window():
    rows=history(count=40);now=rows[15].open_time
    before=atr_entry_risk(rows,14,as_of=now,hold_bars=2)
    assert before.stop_fraction==D('.03') and before.target_fraction==D('.06')
    changed=rows[:15]+[replace(row,open=D(200),close=D(200),high=D(250),low=D(1)) for row in rows[15:]]
    assert atr_entry_risk(changed,14,as_of=now,hold_bars=2)==before
    assert before.information_available_at==now


def test_explicit_fixed_plans_preserve_default_numerical_portfolio():
    rows=history(count=30);stamp=rows[14].open_time;cfg=SimulationConfig(hold_bars=2)
    plan=EntryRiskPlan('ETH/USDT',stamp,rows[15].open_time,cfg.stop_fraction,cfg.target_fraction,cfg.hold_bars)
    baseline=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[stamp]},cfg)
    actual=simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[stamp]},cfg,entry_risks={('ETH/USDT',stamp):plan})
    assert actual.trades==baseline.trades and actual.equity==baseline.equity
    assert actual.max_drawdown==baseline.max_drawdown and actual.entry_risk_plans==(plan,)


def test_each_position_keeps_its_own_risk_and_holding_limit():
    eth=history(count=30);btc=history('BTC/USDT',count=30)
    btc[15]=replace(btc[15],low=D(98))
    stamp=eth[14].open_time;available=eth[15].open_time
    risks={('BTC/USDT',stamp):EntryRiskPlan('BTC/USDT',stamp,available,D('.01'),D('.05'),2),
           ('ETH/USDT',stamp):EntryRiskPlan('ETH/USDT',stamp,available,D('.05'),D('.08'),3)}
    result=simulate_portfolio({'ETH/USDT':eth,'BTC/USDT':btc},{'ETH/USDT':[stamp],'BTC/USDT':[stamp]},
        SimulationConfig(stake=D(10),fee=D(0),slippage=D(0)),entry_risks=risks)
    trades={t.pair:t for t in result.trades}
    assert trades['BTC/USDT'].exit_reason=='stop' and trades['BTC/USDT'].exit_price==D(99)
    assert trades['ETH/USDT'].exit_reason=='timeout' and trades['ETH/USDT'].exit_time==eth[18].open_time


def test_late_or_missing_risk_plan_cannot_enter_portfolio():
    rows=history(count=30);stamp=rows[14].open_time
    plan=atr_entry_risk(rows,14,as_of=rows[15].open_time)
    with pytest.raises(ValueError,match='coverage'):
        simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[stamp]},entry_risks={})
    late=replace(plan,information_available_at=plan.information_available_at+timedelta(seconds=1))
    with pytest.raises(ValueError,match='unavailable'):
        simulate_portfolio({'ETH/USDT':rows},{'ETH/USDT':[stamp]},entry_risks={('ETH/USDT',stamp):late})


def test_missing_or_unobserved_atr_candles_are_rejected():
    rows=history(count=30);now=rows[15].open_time
    changed=rows[:];changed[5]=replace(changed[5],cache_observed_at=now+timedelta(seconds=1))
    with pytest.raises(ValueError,match='unavailable'):atr_entry_risk(changed,14,as_of=now)
    changed=rows[:];changed[5]=replace(changed[5],open_time=changed[5].open_time-timedelta(minutes=1))
    with pytest.raises(ValueError,match='continuous'):atr_entry_risk(changed,14,as_of=now)
