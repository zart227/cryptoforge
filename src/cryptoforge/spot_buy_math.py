"""Shared Spot cash math with explicit fee currency and retained net quantity."""
from dataclasses import dataclass
from decimal import Decimal,ROUND_DOWN


@dataclass(frozen=True)
class SpotAcquisition:
    gross_quantity: Decimal
    net_quantity: Decimal
    notional: Decimal
    cash_cost: Decimal
    fee_amount: Decimal
    fee_quote_equivalent: Decimal
    fee_currency: str


def spot_acquisition(*,stake,price,quantity_step,fee_fraction,fee_currency):
    for value in (stake,price,quantity_step):
        if not isinstance(value,Decimal) or not value.is_finite() or value<=0:raise ValueError('positive finite acquisition inputs required')
    if not isinstance(fee_fraction,Decimal) or not fee_fraction.is_finite() or not 0<=fee_fraction<1:
        raise ValueError('finite fee fraction required')
    if fee_currency not in {'base','quote'}:raise ValueError('explicit base or quote fee currency required')
    budget_price=price*(1+fee_fraction) if fee_currency=='quote' else price
    gross=(stake/budget_price/quantity_step).to_integral_value(rounding=ROUND_DOWN)*quantity_step
    notional=gross*price;equivalent=notional*fee_fraction
    net=gross*(1-fee_fraction) if fee_currency=='base' else gross
    cost=notional if fee_currency=='base' else notional*(1+fee_fraction)
    amount=gross*fee_fraction if fee_currency=='base' else equivalent
    return SpotAcquisition(gross,net,notional,cost,amount,equivalent,fee_currency)


@dataclass(frozen=True)
class SpotSale:
    quantity: Decimal
    notional: Decimal
    cash_proceeds: Decimal
    fee_amount: Decimal
    fee_currency: str


def spot_sale(*,quantity,price,fee_fraction,fee_currency):
    """Quote-fee proceeds for already rounded/allocated inventory.

    Venue rounding, minimums, partial fills and dust ownership belong to callers.
    Other fee assets require their own accounting and are never inferred here.
    """
    for value in (quantity,price):
        if not isinstance(value,Decimal) or not value.is_finite() or value<=0:
            raise ValueError('positive finite sale inputs required')
    if not isinstance(fee_fraction,Decimal) or not fee_fraction.is_finite() or not 0<=fee_fraction<1:
        raise ValueError('finite sale fee fraction required')
    if fee_currency!='quote':raise ValueError('explicit quote sale fee required')
    notional=quantity*price
    return SpotSale(quantity,notional,notional*(1-fee_fraction),notional*fee_fraction,fee_currency)
