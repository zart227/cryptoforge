from decimal import Decimal

from cryptoforge.supabase_executor import quantity_step, quantize_down


def test_quantity_step_limits_eth_decimals_for_bybit_spot() -> None:
    assert quantity_step("ETHUSDT") == Decimal("0.00001")
    assert quantize_down(Decimal("0.00370629"), quantity_step("ETHUSDT")) == Decimal("0.00370")


def test_quantity_step_uses_coarser_altcoin_steps() -> None:
    assert quantity_step("ENAUSDT") == Decimal("1")
    assert quantity_step("HYPEUSDT") == Decimal("0.001")
