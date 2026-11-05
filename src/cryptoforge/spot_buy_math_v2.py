"""Bounded, exact finite-decimal Spot sizing for the opt-in v2 paper producer.

Integer ratios choose whole quantity steps. Decimal context never decides how
many steps are affordable. These helpers do not submit orders.
"""
from decimal import Decimal
from fractions import Fraction

from cryptoforge.spot_buy_math import SpotAcquisition, SpotSale

ALLOCATION_DECIMAL_PLACES = 512


def _ratio(value, *, zero=False, limit=128):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError('bounded finite Decimal required')
    parts = value.as_tuple()
    if len(parts.digits) > limit or abs(parts.exponent) > limit:
        raise ValueError('paper v2 decimal representation exceeds limit')
    if value < 0 or (not zero and value == 0):
        raise ValueError('positive paper v2 value required')
    return Fraction(value)


def _decimal(value):
    """Construct a terminating decimal directly, without context rounding."""
    numerator, denominator = value.numerator, value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2; twos += 1
    while denominator % 5 == 0:
        denominator //= 5; fives += 1
    if denominator != 1:
        raise ValueError('nonterminating paper v2 result')
    places = max(twos, fives)
    coefficient = abs(numerator) * 2 ** (places-twos) * 5 ** (places-fives)
    digits = tuple(map(int, str(coefficient)))
    if len(digits) > 4096 or places > 4096:
        raise ValueError('paper v2 result exceeds representation limit')
    return Decimal((int(numerator < 0), digits, -places))


def exact_product(*values):
    result = Fraction(1)
    for value in values:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError('finite Decimal product required')
        if len(value.as_tuple().digits) > 4096 or abs(value.as_tuple().exponent) > 4096:
            raise ValueError('paper v2 intermediate exceeds limit')
        result *= Fraction(value)
    return _decimal(result)


def sum_exact(values):
    result = Fraction(0)
    for value in values:
        if not isinstance(value,Decimal) or not value.is_finite() or len(value.as_tuple().digits)>4096 or abs(value.as_tuple().exponent)>4096:
            raise ValueError('bounded finite sum input required')
        result += Fraction(value)
    return _decimal(result)


def subtract_exact(left,right):
    # Copying the sign in the tuple avoids context rounding by unary minus.
    return sum_exact((left,right.copy_negate()))


def allocate_basis(basis,sold,total):
    """Floor a partial quote allocation; retain every remainder in its lot.

    A complete lot allocates its exact remaining basis. This registered rule
    keeps cash, residual basis and segment PnL conserved without an epsilon.
    """
    amount=_ratio(basis,zero=True,limit=4096)
    part=_ratio(sold,limit=4096);whole=_ratio(total,limit=4096)
    if part>whole:raise ValueError('paper v2 allocation exceeds owned quantity')
    if part==whole:return _decimal(amount)
    scale=10**ALLOCATION_DECIMAL_PLACES
    return _decimal(Fraction((amount*part/whole*scale)//1,scale))


def floor_quantity(quantity, step):
    amount = _ratio(quantity, zero=True, limit=4096); unit = _ratio(step)
    return _decimal((amount // unit) * unit)


def spot_acquisition(*, stake, price, quantity_step, fee_fraction, fee_currency):
    budget = _ratio(stake); price_ratio = _ratio(price); step = _ratio(quantity_step)
    fee = _ratio(fee_fraction, zero=True)
    if fee >= 1 or fee_currency not in {'base', 'quote'}:
        raise ValueError('explicit base/quote fee below one required')
    unit_cost = price_ratio * step * (1+fee if fee_currency == 'quote' else 1)
    units = budget // unit_cost
    gross = units * step; notional = gross * price_ratio
    equivalent = notional * fee
    net = gross * (1-fee) if fee_currency == 'base' else gross
    cost = notional if fee_currency == 'base' else notional * (1+fee)
    amount = gross * fee if fee_currency == 'base' else equivalent
    if cost > budget or (units+1)*unit_cost <= budget:
        raise ValueError('paper v2 sizing invariant failed')
    return SpotAcquisition(*map(_decimal, (gross, net, notional, cost, amount, equivalent)), fee_currency)


def spot_sale(*, quantity, price, fee_fraction, fee_currency):
    qty = _ratio(quantity, limit=4096); quote = _ratio(price, limit=4096)
    fee = _ratio(fee_fraction, zero=True)
    if fee >= 1 or fee_currency != 'quote':
        raise ValueError('explicit quote fee below one required')
    notional = qty * quote
    return SpotSale(*map(_decimal, (qty, notional, notional*(1-fee), notional*fee)), fee_currency)
