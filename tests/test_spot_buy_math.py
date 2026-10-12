from decimal import Decimal as D
import pytest
from cryptoforge.spot_buy_math import spot_acquisition,spot_sale


def buy(currency):return spot_acquisition(stake=D(10),price=D(100),quantity_step=D('.001'),fee_fraction=D('.001'),fee_currency=currency)


def test_quote_fee_reserves_cash_before_rounding_once():
    row=buy('quote')
    assert row.gross_quantity==row.net_quantity==D('.099')
    assert row.cash_cost==D('9.9099') and row.fee_amount==row.fee_quote_equivalent==D('.0099')
    assert row.cash_cost<=D(10)


def test_base_fee_retains_fractional_net_inventory_and_full_basis():
    row=buy('base')
    assert row.gross_quantity==D('.1') and row.net_quantity==D('.0999')
    assert row.cash_cost==D(10) and row.fee_amount==D('.0001') and row.fee_quote_equivalent==D('.01')
    assert row.net_quantity+row.fee_amount==row.gross_quantity


def test_unknown_fee_currency_is_not_silently_assumed_quote():
    with pytest.raises(ValueError,match='currency'):buy('platform_token')


def test_sale_charges_quote_fee_once_and_keeps_supplied_quantity():
    sale=spot_sale(quantity=D('.0999'),price=D(100),fee_fraction=D('.002'),fee_currency='quote')
    assert sale.quantity==D('.0999') and sale.notional==D('9.99')
    assert sale.fee_amount==D('.01998') and sale.cash_proceeds==D('9.97002')
    assert sale.cash_proceeds+sale.fee_amount==sale.notional


@pytest.mark.parametrize('currency',['base','platform_token',None])
def test_sale_does_not_invent_fee_asset_conversion(currency):
    with pytest.raises(ValueError,match='quote sale fee'):
        spot_sale(quantity=D(1),price=D(100),fee_fraction=D('.001'),fee_currency=currency)
