from datetime import UTC, datetime
from decimal import Decimal

from cryptoforge.live_risk import count_open_spot_positions, daily_equity_blockers, dynamic_entry_capacity


def test_counts_only_material_non_usdt_positions() -> None:
    coins = [
        {"coin": "USDT", "usdValue": "5"},
        {"coin": "QNT", "usdValue": "5.8"},
        {"coin": "CELO", "usdValue": "5.4"},
        {"coin": "ETH", "usdValue": "0.01"},
    ]
    assert count_open_spot_positions(coins) == 2


def test_daily_equity_guard_persists_start_and_blocks_loss(tmp_path) -> None:
    state = tmp_path / "equity.json"
    now = datetime(2026, 9, 30, tzinfo=UTC)
    assert daily_equity_blockers(
        current_equity=Decimal("16"), maximum_loss=Decimal("2"), state_path=state, now=now
    ) == ()
    blockers = daily_equity_blockers(
        current_equity=Decimal("13.9"), maximum_loss=Decimal("2"), state_path=state, now=now
    )
    assert "daily equity loss limit reached" in blockers[0]


def test_dynamic_capacity_uses_equity_cash_and_hard_cap() -> None:
    assert dynamic_entry_capacity(
        total_equity=Decimal("16.30"),
        free_usdt=Decimal("5.55"),
        stake_amount=Decimal("5"),
        open_positions=2,
        hard_position_cap=6,
    ) == (3, 3, 1)
    assert dynamic_entry_capacity(
        total_equity=Decimal("50"),
        free_usdt=Decimal("30"),
        stake_amount=Decimal("5"),
        open_positions=2,
        hard_position_cap=6,
    ) == (10, 6, 4)
