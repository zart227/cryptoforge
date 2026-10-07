from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cryptoforge.short_shadow import (
    ShortShadowCandidate,
    evaluate_short_outcome,
    reason_value,
    short_return,
    summarize_outcomes,
)
from cryptoforge.supabase_executor import CandleRow


def candles_from_prices(prices: list[str]) -> list[CandleRow]:
    start = datetime(2026, 10, 7, tzinfo=UTC)
    return [
        CandleRow(
            pair="MINA/USDT",
            symbol="MINAUSDT",
            open_time=start + timedelta(minutes=5 * index),
            open=Decimal(price),
            high=Decimal(price) + Decimal("0.5"),
            low=Decimal(price) - Decimal("0.5"),
            close=Decimal(price),
            volume=Decimal("1000"),
        )
        for index, price in enumerate(prices)
    ]


def test_short_return_is_positive_when_price_falls() -> None:
    assert short_return(Decimal("100"), Decimal("95")) == pytest.approx(0.05)
    assert short_return(Decimal("100"), Decimal("105")) == pytest.approx(-0.05)


def test_evaluate_short_outcome_tracks_horizons_and_excursions() -> None:
    candidate = ShortShadowCandidate(
        decided_at=datetime(2026, 10, 7, tzinfo=UTC),
        pair="MINA/USDT",
        reference_price=Decimal("100"),
        reasons=("short_shadow_signal=True", "ml_short_probability=0.61"),
    )

    outcome = evaluate_short_outcome(
        candidate,
        candles_from_prices(["99", "98", "97", "96", "95", "94", "96", "97", "98", "99", "100", "101"]),
    )

    assert outcome.short_signal
    assert outcome.short_probability == pytest.approx(0.61)
    assert outcome.return_3 == pytest.approx(0.03)
    assert outcome.return_6 == pytest.approx(0.06)
    assert outcome.return_12 == pytest.approx(-0.01)
    assert outcome.max_favorable == pytest.approx(0.065)
    assert outcome.max_adverse == pytest.approx(-0.015)


def test_summarize_outcomes_separates_signals_and_probability_thresholds() -> None:
    base = ShortShadowCandidate(
        decided_at=datetime(2026, 10, 7, tzinfo=UTC),
        pair="MINA/USDT",
        reference_price=Decimal("100"),
        reasons=("short_shadow_signal=True", "ml_short_probability=0.61"),
    )
    winner = evaluate_short_outcome(base, candles_from_prices(["99"] * 12))
    loser = evaluate_short_outcome(
        ShortShadowCandidate(
            decided_at=base.decided_at,
            pair="PONS/USDT",
            reference_price=Decimal("100"),
            reasons=("short_shadow_signal=False", "ml_short_probability=0.40"),
        ),
        candles_from_prices(["101"] * 12),
    )

    summary = summarize_outcomes([winner, loser])

    assert reason_value(base.reasons, "ml_short_probability") == "0.61"
    assert summary["count"] == 2
    assert summary["complete_12"] == 2
    assert summary["signaled"]["count"] == 1
    assert summary["signaled"]["win_rate"] == 1
    assert summary["probability_ge_0_5"]["count"] == 1
    assert summary["all"]["win_rate"] == 0.5
