from decimal import Decimal

from cryptoforge.supabase_executor import quantity_step, quantize_down


def test_quantity_step_limits_eth_decimals_for_bybit_spot() -> None:
    assert quantity_step("ETHUSDT") == Decimal("0.00001")
    assert quantize_down(Decimal("0.00370629"), quantity_step("ETHUSDT")) == Decimal("0.00370")


def test_quantity_step_uses_coarser_altcoin_steps() -> None:
    assert quantity_step("ENAUSDT") == Decimal("1")
    assert quantity_step("HYPEUSDT") == Decimal("0.001")


def test_quantized_dust_remains_below_sellable_minimum() -> None:
    balance = Decimal("0.00000629")
    sellable = quantize_down(balance, Decimal("0.00001"))

    assert sellable == Decimal("0")
    assert sellable * Decimal("2670") < Decimal("5")


def test_position_near_exchange_minimum_is_not_dust() -> None:
    balance = Decimal("48.4127")
    price = Decimal("0.10325")

    assert balance * price >= Decimal("1")
    assert balance * price < Decimal("5.01")
