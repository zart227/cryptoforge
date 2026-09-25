from decimal import Decimal

import pytest

from cryptoforge.lifecycle import (
    EvaluationCriteria,
    StrategyLifecycleMetadata,
    StrategyStatus,
    evaluate_strategy,
    recommend_next_status,
    transition_status,
)
from cryptoforge.metrics import PerformanceMetrics


def metrics(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "scope": "candidate",
        "trade_count": 40,
        "net_pnl": Decimal("100"),
        "gross_profit": Decimal("160"),
        "gross_loss": Decimal("-60"),
        "fees": Decimal("5"),
        "win_rate": Decimal("0.45"),
        "profit_factor": Decimal("2.66"),
        "expectancy": Decimal("2.5"),
        "average_win": Decimal("8"),
        "average_loss": Decimal("-4"),
        "max_drawdown": Decimal("20"),
        "sharpe": Decimal("1.2"),
        "sortino": Decimal("1.5"),
    }
    values.update(overrides)
    return PerformanceMetrics(**values)


def test_lifecycle_allows_only_traceable_transitions() -> None:
    assert (
        transition_status(StrategyStatus.DRAFT, StrategyStatus.BACKTESTED)
        == StrategyStatus.BACKTESTED
    )

    with pytest.raises(ValueError, match="invalid lifecycle transition"):
        transition_status(StrategyStatus.DRAFT, StrategyStatus.APPROVED)


def test_high_profit_unstable_strategy_is_not_promoted() -> None:
    result = evaluate_strategy(
        metrics(
            net_pnl=Decimal("10000"),
            profit_factor=Decimal("4"),
            expectancy=Decimal("100"),
            max_drawdown=Decimal("200"),
        ),
        criteria=EvaluationCriteria(max_drawdown=Decimal("50")),
    )

    assert not result.passed
    assert "drawdown above threshold" in result.reasons
    assert recommend_next_status(StrategyStatus.PAPER_TRADING, result) == StrategyStatus.REJECTED


def test_insufficient_trade_count_blocks_promotion() -> None:
    result = evaluate_strategy(metrics(trade_count=5))

    assert not result.passed
    assert "insufficient trade count" in result.reasons


def test_passing_evaluation_recommends_only_next_state() -> None:
    result = evaluate_strategy(metrics())

    assert result.passed
    assert (
        recommend_next_status(StrategyStatus.BACKTESTED, result)
        == StrategyStatus.OUT_OF_SAMPLE_TESTED
    )
    assert (
        recommend_next_status(StrategyStatus.CANDIDATE, result)
        == StrategyStatus.APPROVED
    )


def test_metadata_preserves_human_live_approval_boundary() -> None:
    metadata = StrategyLifecycleMetadata(
        strategy_name="CryptoForgeBaselineStrategy",
        strategy_version="cryptoforge-baseline-v0.1.0",
        status=StrategyStatus.BACKTESTED,
        evidence={"backtest": "phase9"},
    )

    payload = metadata.as_payload()

    assert payload["status"] == "BACKTESTED"
    assert payload["human_live_approval_required"] is True
