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

    examples = build_examples("ETH/USDT", candles, horizon_candles=3)

    assert examples
    assert examples == sorted(examples, key=lambda example: example.open_time)
    assert len(examples[0].features) == 7
    assert {example.label for example in examples} <= {0, 1}


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
    assert all(0 <= metric.accuracy <= 1 for metric in model.metrics)


def test_model_training_runner_writes_artifact_and_registry(tmp_path):
    supabase = FakeSupabase()
    runner = ModelTrainingRunner(
        reader=FakeReader(make_training_candles(180)),
        supabase=supabase,
        artifact_dir=tmp_path,
        lookback_candles=180,
        min_examples=80,
        epochs=10,
    )

    model = runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, tzinfo=UTC))

    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["model_version"] == model.model_version
    assert [call[0] for call in supabase.upserts] == ["model_runs", "model_metrics", "system_events"]
    event = supabase.upserts[-1][1][0]
    assert event["event_type"] == "model.active"
    assert event["payload"]["artifact_sha256"]
    assert event["payload"]["artifact"]["model_version"] == model.model_version


class FakeRegistry(ActiveModelRegistry):
    def __init__(self, row):
        self.row = row

    def _latest_event(self):
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
