from datetime import time

import pytest

from cryptoforge.outbox import SQLiteOutbox
from cryptoforge.strategy_lab import (
    ExperimentKind,
    ResearchPolicy,
    ResourceSnapshot,
    StrategyLab,
    low_priority_research_prefix,
)


def healthy_snapshot(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "available_ram_mb": 500,
        "load_1m": 0.1,
        "free_disk_gb": 10.0,
        "trading_runtime_active": False,
    }
    values.update(overrides)
    return ResourceSnapshot(**values)


def test_strategy_lab_creates_reproducible_paper_candidate(tmp_path) -> None:
    lab = StrategyLab(SQLiteOutbox(tmp_path / "outbox.sqlite3"))

    plan = lab.create_experiment(
        kind=ExperimentKind.PARAMETER_OPTIMIZATION,
        objective="try stricter RSI threshold",
        strategy_version="cryptoforge-baseline-v0.1.0",
        dataset_id="bybit_spot_btcusdt_5m_20260923_20260925",
        parameters={"buy_rsi": 60},
        reproducibility={"git_commit": "abc", "timerange": "20260923-20260925"},
    )

    assert plan.candidate_for_paper is True
    assert plan.live_risk_changes_allowed is False
    assert plan.reproducibility["git_commit"] == "abc"


def test_strategy_lab_defers_when_trading_runtime_is_active_during_day(tmp_path) -> None:
    lab = StrategyLab(SQLiteOutbox(tmp_path / "outbox.sqlite3"))

    decision = lab.can_run(
        healthy_snapshot(trading_runtime_active=True),
        current_time=time(12, 0),
    )

    assert not decision.allowed
    assert "research deferred while trading runtime is active during trading hours" in decision.reasons


def test_strategy_lab_allows_night_research_when_resources_are_healthy(tmp_path) -> None:
    lab = StrategyLab(SQLiteOutbox(tmp_path / "outbox.sqlite3"))

    decision = lab.can_run(healthy_snapshot(), current_time=time(23, 30))

    assert decision.allowed


def test_strategy_lab_blocks_low_resources_and_heavy_search(tmp_path) -> None:
    lab = StrategyLab(
        SQLiteOutbox(tmp_path / "outbox.sqlite3"),
        ResearchPolicy(heavy_search_active=True),
    )

    decision = lab.can_run(
        healthy_snapshot(available_ram_mb=100, load_1m=1.5, free_disk_gb=1.0),
        current_time=time(23, 0),
    )

    assert not decision.allowed
    assert "heavy search is marked NOT ACTIVE on current VPS" in decision.reasons
    assert "insufficient available RAM" in decision.reasons
    assert "load average too high" in decision.reasons
    assert "insufficient free disk" in decision.reasons


def test_strategy_lab_persists_experiment_metadata(tmp_path) -> None:
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    lab = StrategyLab(outbox)
    plan = lab.create_experiment(
        kind=ExperimentKind.STRATEGY_DISCOVERY,
        objective="candidate rule set",
        strategy_version="draft-v1",
        dataset_id="dataset",
        parameters={},
        reproducibility={"seed": 1},
    )

    lab.persist_experiment(plan)

    event = outbox.due_events()[0]
    assert event.event_type == "experiment.planned"
    assert event.payload["experiment_id"] == plan.experiment_id
    assert event.payload["live_risk_changes_allowed"] is False


def test_low_priority_prefix_is_explicit() -> None:
    assert low_priority_research_prefix() == "nice -n 10 ionice -c2 -n7"


def test_heavy_ml_training_cannot_be_marked_active_on_current_vps(tmp_path) -> None:
    lab = StrategyLab(
        SQLiteOutbox(tmp_path / "outbox.sqlite3"),
        ResearchPolicy(heavy_search_active=True),
    )

    with pytest.raises(ValueError, match="heavy continuous training"):
        lab.create_experiment(
            kind=ExperimentKind.MACHINE_LEARNING,
            objective="train heavy model",
            strategy_version="ml-v1",
            dataset_id="dataset",
            parameters={},
            reproducibility={},
        )
