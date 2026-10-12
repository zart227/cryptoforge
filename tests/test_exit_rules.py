from decimal import Decimal as D
import pytest
from cryptoforge.exit_rules import price_time_exit


def check(price,elapsed=10,target=D('.04')):
    return price_time_exit(price=D(price),entry_price=D(100),stop_fraction=D('.02'),target_fraction=target,elapsed_seconds=elapsed,maximum_hold_seconds=60)


def test_stop_and_target_preserve_priority_over_same_time_timeout():
    assert check('98',60)=='stop'
    assert check('104',60)=='target'
    assert check('100',60)=='timeout'
    assert check('100') is None


def test_paper_without_declared_target_does_not_gain_take_profit():
    assert check('105',10,None) is None
    assert check('105',60,None)=='timeout'


@pytest.mark.parametrize('price',['0','NaN','Infinity'])
def test_invalid_exit_quotes_are_rejected(price):
    with pytest.raises(ValueError):check(price)


def test_negative_holding_time_is_not_a_valid_exit_observation():
    with pytest.raises(ValueError,match='duration'):check('100',-1)
