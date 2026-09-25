from decimal import Decimal

from cryptoforge.champion import (
    CandidateRole,
    ComparisonEvidence,
    StrategyCandidate,
    baseline_champion_candidate,
    compare_champion_challenger,
)
from tests.test_lifecycle import metrics


def challenger(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "strategy_name": "ChallengerStrategy",
        "strategy_version": "challenger-v1",
        "role": CandidateRole.CHALLENGER,
        "dataset_id": "bybit_spot_btcusdt_5m_20260923_20260925",
        "timerange": "20260923-20260925",
        "status": "CANDIDATE",
        "metadata": {"live_enabled": False},
    }
    values.update(overrides)
    return StrategyCandidate(**values)


def evidence(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "champion": metrics(
            net_pnl=Decimal("10"),
            profit_factor=Decimal("1.20"),
            expectancy=Decimal("0.5"),
            max_drawdown=Decimal("20"),
        ),
        "challenger": metrics(
            net_pnl=Decimal("20"),
            profit_factor=Decimal("1.40"),
            expectancy=Decimal("0.8"),
            max_drawdown=Decimal("18"),
        ),
        "out_of_sample": metrics(scope="oos"),
        "walk_forward": metrics(scope="walk_forward"),
        "regime_metrics": {"RANGE": metrics(scope="regime:RANGE")},
    }
    values.update(overrides)
    return ComparisonEvidence(**values)


def test_baseline_registered_as_initial_champion_control() -> None:
    candidate = baseline_champion_candidate()

    assert candidate.role == CandidateRole.CHAMPION
    assert candidate.strategy_version == "cryptoforge-baseline-v0.1.0"
    assert candidate.metadata["live_enabled"] is False


def test_challenger_can_promote_with_complete_evidence() -> None:
    decision = compare_champion_challenger(
        baseline_champion_candidate(),
        challenger(),
        evidence(),
    )

    assert decision.promote
    assert "passed" in decision.reason
    assert "champion" in decision.evidence


def test_absolute_profit_alone_cannot_replace_champion() -> None:
    decision = compare_champion_challenger(
        baseline_champion_candidate(),
        challenger(),
        evidence(
            challenger=metrics(
                net_pnl=Decimal("1000"),
                profit_factor=Decimal("0.9"),
                expectancy=Decimal("-1"),
                max_drawdown=Decimal("100"),
            ),
            out_of_sample=None,
            walk_forward=None,
            regime_metrics={},
        ),
    )

    assert not decision.promote
    assert "absolute profit alone is not enough" in decision.reason
    assert "missing out-of-sample evidence" in decision.reason


def test_equivalent_dataset_is_required() -> None:
    decision = compare_champion_challenger(
        baseline_champion_candidate(),
        challenger(dataset_id="different"),
        evidence(),
    )

    assert not decision.promote
    assert "equivalent data" in decision.reason
