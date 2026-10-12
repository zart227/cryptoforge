from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from cryptoforge.net_portfolio import net_entry_signals
from cryptoforge.trade_simulator import SimulationConfig
from test_trade_simulator import history


def test_net_signals_use_only_available_features_and_respect_fixed_closeout():
    rows=history(count=100);cfg=SimulationConfig(hold_bars=3)
    ranges={'ETH/USDT':{'validation_start':rows[50].open_time.isoformat(),'development_end':rows[85].open_time.isoformat()}}
    class Head:
        def predict(self,features):return .01
    selected,baseline=net_entry_signals(Head(),{'ETH/USDT':rows},ranges,cfg)
    assert selected==baseline and selected['ETH/USDT'][0]==rows[50].open_time
    assert selected['ETH/USDT'][-1]+timedelta(minutes=5*(cfg.hold_bars+cfg.entry_delay_bars+1))<rows[85].open_time
    changed=rows[:85]+[replace(row,close=D(-1)) for row in rows[85:]]
    assert net_entry_signals(Head(),{'ETH/USDT':changed},ranges,cfg)==(selected,baseline)


def test_nonpositive_forecast_does_not_create_a_trade_opportunity_for_candidate():
    rows=history(count=100);ranges={'ETH/USDT':{'validation_start':rows[50].open_time.isoformat(),'development_end':rows[85].open_time.isoformat()}}
    class Head:
        def predict(self,features):return 0
    selected,baseline=net_entry_signals(Head(),{'ETH/USDT':rows},ranges,SimulationConfig())
    assert not selected['ETH/USDT'] and baseline['ETH/USDT']


def test_late_history_revision_cannot_finance_an_entry_before_it_was_observed():
    rows=history(count=100);revision=rows[70].open_time+timedelta(minutes=5)
    rows[0]=replace(rows[0],cache_observed_at=revision)
    ranges={'ETH/USDT':{'validation_start':rows[50].open_time.isoformat(),'development_end':rows[95].open_time.isoformat()}}
    class Head:
        def predict(self,features):return .01
    selected,baseline=net_entry_signals(Head(),{'ETH/USDT':rows},ranges,SimulationConfig(hold_bars=3))
    assert selected==baseline and selected['ETH/USDT'][0]==rows[70].open_time
    assert all(stamp+timedelta(minutes=5)>=revision for stamp in selected['ETH/USDT'])
