from datetime import UTC, datetime
from decimal import Decimal

from cryptoforge.live_risk import count_open_spot_positions, daily_equity_blockers


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
