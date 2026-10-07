from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cryptoforge.short_shadow import (
    ShortShadowCandidate,
    evaluate_short_outcome,
    reason_value,
    short_return,
    summarize_outcomes,
    ShortShadowOutcomeRunner,
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


def test_costs_turn_small_gross_gain_into_net_loss() -> None:
    candidate = ShortShadowCandidate(datetime(2026, 10, 7, tzinfo=UTC), "MINA/USDT", Decimal("100"), ())
    outcome = evaluate_short_outcome(candidate, candles_from_prices(["99.9"] * 12))
    assert outcome.as_payload()["net_return_12"] == pytest.approx(-0.002)
    summary = summarize_outcomes([outcome])["all"]
    assert summary["win_rate"] == 1
    assert summary["net_win_rate"] == 0
    assert summary["mean_net_return_12"] == pytest.approx(-0.002)


@pytest.mark.parametrize("cost", [-0.1, float("nan"), float("inf")])
def test_invalid_cost_is_rejected(cost: float) -> None:
    candidate = ShortShadowCandidate(datetime(2026, 10, 7, tzinfo=UTC), "MINA/USDT", Decimal("100"), ())
    with pytest.raises(ValueError):
        evaluate_short_outcome(candidate, candles_from_prices(["99"] * 12), round_trip_cost=cost)


@pytest.mark.parametrize("mode,complete,pending,gaps", [
    ("complete", 1, 0, 0), ("unclosed", 0, 1, 0),
    ("gap", 0, 0, 1), ("missing_first", 0, 0, 1),
])
def test_runner_excludes_gaps_and_unclosed_candles(monkeypatch, mode, complete, pending, gaps) -> None:
    start = datetime(2026, 10, 7, tzinfo=UTC)
    candidate = ShortShadowCandidate(start - timedelta(minutes=1), "MINA/USDT", Decimal("100"), ())
    candles = candles_from_prices(["99"] * 13)
    if mode == "gap":
        candles.pop(5)
    elif mode == "missing_first":
        candles.pop(0)
    candles = candles[:12]
    runner = ShortShadowOutcomeRunner(None)
    monkeypatch.setattr(runner, "fetch_candidates", lambda **kwargs: [candidate])
    monkeypatch.setattr(runner, "fetch_future_candles", lambda *args, **kwargs: candles)
    monkeypatch.setattr(runner, "publish_summary", lambda *args, **kwargs: None)
    now = start + timedelta(minutes=59 if mode == "unclosed" else 70)
    summary = runner.run(now=now)
    assert summary["complete_12"] == complete
    assert summary["pending"] == pending
    assert summary["gaps"] == gaps
