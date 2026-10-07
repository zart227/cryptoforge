from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json

from cryptoforge.model_training import (
    ModelTrainingRunner,
    build_examples,
    chronological_splits,
    train_logistic_model,
)
from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.supabase_executor import CandleRow


class FakeReader:
    def __init__(self, candles):
        self.candles = candles

    def read_candles(self, pair, *, timeframe="5m", limit=120):
        return self.candles[:limit]


class FakeSupabase:
    def __init__(self):
        self.upserts = []

    def upsert(self, table, records, *, on_conflict, resolution="merge-duplicates"):
        self.upserts.append((table, records, on_conflict, resolution))


def make_training_candles(count=180):
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles = []
    price = Decimal("100")
    for index in range(count):
        drift = Decimal("0.15") if index % 8 < 5 else Decimal("-0.08")
        open_price = price
        close = price + drift + Decimal(index % 3) * Decimal("0.01")
        high = max(open_price, close) + Decimal("0.35")
        low = min(open_price, close) - Decimal("0.25")
        candles.append(
            CandleRow(
                pair="ETH/USDT",
                symbol="ETHUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=Decimal("1000") + Decimal(index % 11),
            )
        )
        price = close
    return candles


def test_build_examples_uses_future_label_without_losing_order():
    candles = make_training_candles(90)

    examples = build_examples("ETH/USDT", candles, horizon_candles=3, min_label_return=0.003)

    assert examples
    assert examples == sorted(examples, key=lambda example: example.open_time)
    assert len(examples[0].features) == 7
    assert {example.label for example in examples} <= {0, 1}
    assert {example.short_label for example in examples} <= {0, 1}


def test_build_examples_ignores_noise_inside_label_threshold():
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles = []
    price = Decimal("100")
    for index in range(60):
        close = price + (Decimal("0.01") if index % 2 else Decimal("-0.01"))
        candles.append(
            CandleRow(
                pair="ETH/USDT",
                symbol="ETHUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=price,
                high=max(price, close) + Decimal("0.02"),
                low=min(price, close) - Decimal("0.02"),
                close=close,
                volume=Decimal("1000"),
            )
        )
        price = close

    examples = build_examples("ETH/USDT", candles, horizon_candles=3, min_label_return=0.003)

    assert examples
    assert all(example.label == 0 for example in examples)
    assert all(example.short_label == 0 for example in examples)


def test_train_logistic_model_produces_split_metrics():
    examples = build_examples("ETH/USDT", make_training_candles(160), horizon_candles=3)
    train, validation, test = chronological_splits(examples)

    model = train_logistic_model(
        train,
        validation,
        test,
        learning_rate=0.05,
        epochs=20,
        trained_at=datetime(2026, 9, 29, tzinfo=UTC),
    )

    assert model.model_version.startswith("pure-python-logistic-candle-v1-20260929-")
    assert [metric.split for metric in model.metrics] == ["train", "validation", "test"]
    assert [metric.split for metric in model.short_metrics] == ["train", "validation", "test"]
    assert len(model.validation_search) == 3
    assert model.selected_l2 == min(model.validation_search, key=lambda t: t["validation_log_loss"])["l2"]
    assert all(0 <= metric.accuracy <= 1 for metric in model.metrics)
    assert all(0 <= metric.accuracy <= 1 for metric in model.short_metrics)


def test_model_training_runner_writes_artifact_and_registry(tmp_path):
    supabase = FakeSupabase()
    runner = ModelTrainingRunner(
        reader=FakeReader(make_training_candles(180)),
        supabase=supabase,
        artifact_dir=tmp_path,
        lookback_candles=180,
        min_examples=80,
        epochs=10,
        registry=type("Registry", (), {"latest": lambda self, **kwargs: None})(),
    )

    model = runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, tzinfo=UTC))

    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["model_version"] == model.model_version
    assert [call[0] for call in supabase.upserts] == ["model_runs", "model_metrics", "system_events"]
    event = supabase.upserts[-1][1][0]
    assert event["event_type"] == "model.candidate"
    assert payload["promotion"]["reason"] == "insufficient_unseen_examples"
    assert event["payload"]["artifact_sha256"]
    assert event["payload"]["artifact"]["model_version"] == model.model_version
    assert "short_weights" in event["payload"]["artifact"]
    assert event["payload"]["artifact"]["short_metrics"]
    assert "long" in event["payload"]["metrics"]
    assert "short" in event["payload"]["metrics"]


class FakeRegistry(ActiveModelRegistry):
    def __init__(self, row):
        self.row = row

    def _latest_event(self, **kwargs):
        return self.row


def test_active_model_registry_reads_embedded_artifact(tmp_path):
    supabase = FakeSupabase()
    runner = ModelTrainingRunner(
        reader=FakeReader(make_training_candles(180)),
        supabase=supabase,
        artifact_dir=tmp_path,
        lookback_candles=180,
        min_examples=80,
        epochs=10,
        registry=type("Registry", (), {"latest": lambda self, **kwargs: None})(),
    )
    runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, tzinfo=UTC))
    event = supabase.upserts[-1][1][0]

    active = FakeRegistry(
        {
            "occurred_at": event["occurred_at"],
            "payload": event["payload"],
        }
    ).latest(now=datetime(2026, 9, 29, 1, tzinfo=UTC))

    assert active is not None
    assert active.model_version == event["payload"]["model_version"]
    assert 0 <= active.predict_probability(tuple([0.0] * 7)) <= 1
    short_probability = active.predict_short_probability(tuple([0.0] * 7))
    assert short_probability is not None
    assert 0 <= short_probability <= 1


def test_active_model_registry_reads_embedded_candidate_artifact(tmp_path):
    supabase = FakeSupabase()
    runner = ModelTrainingRunner(
        reader=FakeReader(make_training_candles(180)),
        supabase=supabase,
        artifact_dir=tmp_path,
        lookback_candles=180,
        min_examples=80,
        epochs=10,
        registry=type("Registry", (), {"latest": lambda self, **kwargs: None})(),
    )
    runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, tzinfo=UTC))
    event = supabase.upserts[-1][1][0]
    assert event["event_type"] == "model.candidate"

    candidate = FakeRegistry(
        {
            "occurred_at": event["occurred_at"],
            "payload": event["payload"],
        }
    ).latest_candidate(now=datetime(2026, 9, 29, 1, tzinfo=UTC))

    assert candidate is not None
    assert candidate.model_version == event["payload"]["model_version"]


def promotion_fixture():
    from cryptoforge.model_training import TrainingExample, TrainedModel
    start = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [TrainingExample('ETH/USDT', start + timedelta(minutes=5*i),
                            (1.0 if i % 2 else -1.0,), i % 2, 1-i % 2,
                            0.01 if i % 2 else -0.01) for i in range(240)]
    model = TrainedModel('candidate', ('return',), (0.0,), (1.0,), (5.0,),
                         0.0, (-5.0,), 0.0, 0.5, ())
    return model, rows


def test_promotion_requires_baseline_and_positive_return_after_costs():
    from cryptoforge.model_training import promotion_decision
    from dataclasses import replace
    model, rows = promotion_fixture()
    assert promotion_decision(model, None, rows, round_trip_cost=0.003)['promoted']
    assert not promotion_decision(model, None, rows, round_trip_cost=0.02)['promoted']
    majority = replace(model, weights=(0.0,), bias=-5.0)
    assert not promotion_decision(majority, None, rows, round_trip_cost=0.003)['promoted']


def test_promotion_preserves_equal_incumbent_and_excludes_seen_data():
    from cryptoforge.model_training import promotion_decision, FEATURE_VERSION
    from cryptoforge.model_registry import ActiveModel
    model, rows = promotion_fixture()
    artifact = model.as_artifact(pairs=['ETH/USDT'], trained_at=rows[0].open_time-timedelta(days=1),
                                config={})
    incumbent = ActiveModel('run', 'previous', FEATURE_VERSION, '', '',
                            rows[0].open_time-timedelta(days=1), artifact)
    decision = promotion_decision(model, incumbent, rows, round_trip_cost=0.003)
    assert decision['reason'] == 'does_not_beat_incumbent'
    artifact['config']['training_label_end'] = rows[-1].open_time.isoformat()
    assert promotion_decision(model, incumbent, rows, round_trip_cost=0.003)['reason'] == 'insufficient_unseen_examples'


def test_promotion_rechecks_full_test_when_label_config_changes():
    from cryptoforge.model_training import promotion_decision, FEATURE_VERSION
    from cryptoforge.model_registry import ActiveModel
    model, rows = promotion_fixture()
    artifact = model.as_artifact(pairs=['ETH/USDT'], trained_at=rows[0].open_time-timedelta(days=1),
                                config={'min_label_return': 0.0})
    incumbent = ActiveModel('run', 'previous', FEATURE_VERSION, '', '',
                            rows[0].open_time-timedelta(days=1), artifact)
    artifact['config']['training_label_end'] = rows[-1].open_time.isoformat()

    decision = promotion_decision(
        model,
        incumbent,
        rows,
        round_trip_cost=0.003,
        min_label_return=0.003,
    )

    assert decision['count'] == len(rows)
    assert decision['reason'] == 'does_not_beat_incumbent'


def test_chronological_splits_purge_crossing_labels_and_keep_timestamps_together():
    examples = build_examples('ETH/USDT', make_training_candles(180), horizon_candles=3)
    examples = sorted(examples + examples, key=lambda e: e.open_time)
    train, validation, test = chronological_splits(examples)
    assert max(e.label_end_time for e in train) < min(e.open_time for e in validation)
    assert max(e.label_end_time for e in validation) < min(e.open_time for e in test)


def test_registry_failure_cannot_publish_active_model(tmp_path):
    import pytest
    class BrokenRegistry:
        def latest(self, **kwargs):
            raise ValueError('checksum mismatch')
    supabase = FakeSupabase()
    runner = ModelTrainingRunner(reader=FakeReader(make_training_candles()),
                                 supabase=supabase, artifact_dir=tmp_path,
                                 epochs=1, registry=BrokenRegistry())
    with pytest.raises(ValueError, match='checksum mismatch'):
        runner.run(['ETH/USDT'])
    assert supabase.upserts == []
