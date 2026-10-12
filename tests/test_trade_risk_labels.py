from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from test_trade_simulator import history


def label(rows):
    return build_trade_labels('ETH/USDT',rows,SimulationConfig(stake=D(10),fee=D(0),slippage=D(0),hold_bars=3))[0]


def test_ambiguous_stop_cannot_claim_post_exit_high_as_observed_favorable_movement():
    rows=history(count=100);rows[37]=replace(rows[37],low=D(97),high=D(105))
    result=label(rows);risk=result.risk_outcome
    assert result.trade.ambiguous and result.trade.exit_reason=='stop'
    assert risk['maximum_favorable_price_fraction_lower_bound']==0
    assert risk['maximum_favorable_price_fraction_upper_bound']==D('.05')
    assert risk['maximum_adverse_price_fraction_lower_bound']==D('.02')
    assert risk['maximum_adverse_price_fraction_upper_bound']==D('.03')
    assert risk['holding_seconds_lower_bound']==0 and risk['holding_seconds_upper_bound']==300
    assert risk['outcome_available_at']==result.label_end_time


def test_timeout_excludes_extremes_after_the_opening_exit():
    rows=history(count=100)
    rows[40]=replace(rows[40],low=D(1),high=D(1000))
    risk=label(rows).risk_outcome
    assert risk['maximum_favorable_price_fraction_lower_bound']==risk['maximum_favorable_price_fraction_upper_bound']==D('.01')
    assert risk['maximum_adverse_price_fraction_lower_bound']==risk['maximum_adverse_price_fraction_upper_bound']==D('.01')
    assert risk['holding_seconds_lower_bound']==risk['holding_seconds_upper_bound']==900
    assert not risk['exit_bar_order_unknown']


def test_gap_stop_uses_open_and_ignores_later_recovery():
    rows=history(count=100);rows[38]=replace(rows[38],open=D(95),low=D(94),high=D(150))
    result=label(rows);risk=result.risk_outcome
    assert result.trade.exit_reason=='stop_gap'
    assert risk['maximum_adverse_price_fraction_lower_bound']==risk['maximum_adverse_price_fraction_upper_bound']==D('.05')
    assert risk['maximum_favorable_price_fraction_upper_bound']==D('.01')
    assert risk['holding_seconds_lower_bound']==risk['holding_seconds_upper_bound']==300


def test_future_outcomes_do_not_enter_the_entry_features():
    rows=history(count=100);before=label(rows)
    rows[37]=replace(rows[37],low=D(97),high=D(105));after=label(rows)
    assert before.example.features==after.example.features and before.risk_outcome!=after.risk_outcome
    assert not after.risk_outcome['price_bounds_include_fees']
