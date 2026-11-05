from decimal import Decimal
import json

import pytest
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.fractional_risk import FractionalRiskPolicy, fractional_risk_blockers, load_fractional_policy
from test_submission_risk import setup, BUY


def policy(**changes):
    values = dict(maximum_position_fraction=Decimal('.05'), maximum_planned_risk_fraction=Decimal('.005'),
        stop_fraction=Decimal('.04'), round_trip_cost_fraction=Decimal('.06'))
    values.update(changes); return FractionalRiskPolicy(**values)


def test_exact_exposure_and_planned_risk_boundaries_accept_without_resizing():
    assert fractional_risk_blockers(policy(), equity=Decimal('1000'), quote_notional=Decimal('50'),
        existing_symbol_value=Decimal('0')) == ()
    reasons = fractional_risk_blockers(policy(), equity=Decimal('1000'), quote_notional=Decimal('50.00001'),
        existing_symbol_value=Decimal('0'))
    assert len(reasons) == 2


def test_existing_dust_counts_towards_post_buy_exposure():
    assert 'exposure' in fractional_risk_blockers(policy(), equity=Decimal('1000'), quote_notional=Decimal('50'),
        existing_symbol_value=Decimal('.01'))[0]


def test_explicit_roundtrip_costs_can_independently_exceed_risk_budget():
    reasons = fractional_risk_blockers(policy(maximum_planned_risk_fraction=Decimal('.001')),
        equity=Decimal('1000'), quote_notional=Decimal('20'), existing_symbol_value=Decimal('0'))
    assert len(reasons) == 1 and 'planned stop' in reasons[0]


@pytest.mark.parametrize('field,value', [('maximum_position_fraction','.051'),
    ('maximum_planned_risk_fraction','.006'), ('stop_fraction','0'), ('stop_fraction','1'),
    ('round_trip_cost_fraction','-0.001'), ('round_trip_cost_fraction','NaN')])
def test_policy_cannot_weaken_supported_caps_or_guess_invalid_fractions(field,value):
    with pytest.raises(ValueError): policy(**{field: Decimal(value)})


def test_policy_file_requires_explicit_decimal_cost_and_preserves_sha(tmp_path):
    path = tmp_path/'policy.json'
    source = dict(schema_version='fractional-entry-risk-v1', maximum_position_fraction='.05',
        maximum_planned_risk_fraction='.005', round_trip_cost_fraction='.002')
    path.write_text(json.dumps(source))
    result, sha = load_fractional_policy(path, stop_fraction=Decimal('.04'))
    assert result.round_trip_cost_fraction == Decimal('.002') and len(sha) == 64
    del source['round_trip_cost_fraction']; path.write_text(json.dumps(source))
    with pytest.raises(ValueError): load_fractional_policy(path, stop_fraction=Decimal('.04'))


def test_submission_guard_uses_current_equity_and_keeps_sell_available(tmp_path):
    guard, account, _, sent = setup(tmp_path)
    guard.fractional_policy = policy()
    with pytest.raises(OrderControlBlocked, match='exposure'):
        guard.create_spot_market_order(**BUY)
    assert sent == []
    # This test changes only the account observation, not order amount or limits.
    account.total_equity_usd = Decimal('1000')
    guard.create_spot_market_order(**BUY)
    guard.client.get_unified_usdt_balance = lambda: pytest.fail('sell depends on entry percentages')
    guard.create_spot_market_order(**dict(BUY, side='Sell', qty=Decimal('.01')))
    assert len(sent) == 2


def test_bad_equity_never_establishes_fractional_permission():
    for value in ('0', 'NaN', 'Infinity', '-1'):
        assert fractional_risk_blockers(policy(), equity=Decimal(value), quote_notional=Decimal('5'),
            existing_symbol_value=Decimal('0'))
