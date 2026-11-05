from decimal import Decimal
import pytest
from cryptoforge.live_feedback import candidate_cost_floor


def report(rate='0.003'):
    return {'accounting_quality_verified':True,'outcomes':[
        {'exit_controlled_by_bot':True,'exit_kind':'spot_order','fee_drag_fraction':rate}]}


@pytest.mark.parametrize('quality',['false',1,{},None])
def test_only_explicit_verified_accounting_can_calibrate(quality):
    value=report();value['accounting_quality_verified']=quality
    assert candidate_cost_floor(value,minimum_orders=1) is None


@pytest.mark.parametrize('rate',['NaN','Infinity','-0.01','1','broken',None])
def test_invalid_observed_fee_rates_remain_unavailable(rate):
    assert candidate_cost_floor(report(rate),minimum_orders=1) is None


@pytest.mark.parametrize('slip',[Decimal('NaN'),Decimal('-.001'),Decimal('1')])
def test_invalid_slippage_cannot_lower_cost_floor(slip):
    with pytest.raises(ValueError,match='slippage'):
        candidate_cost_floor(report(),minimum_orders=1,slippage_fraction=slip)


@pytest.mark.parametrize('minimum',[True,0,-1,1.5])
def test_invalid_sample_requirement_cannot_bypass_minimum(minimum):
    with pytest.raises(ValueError,match='sample minimum'):
        candidate_cost_floor(report(),minimum_orders=minimum)


def test_known_rate_includes_slippage_once():
    assert candidate_cost_floor(report(),minimum_orders=1)==Decimal('.004')
