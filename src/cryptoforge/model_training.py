from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptoforge.night_research_cli import file_pairs
from cryptoforge.supabase_executor import CandleRow, SupabaseMarketReader, rsi
from cryptoforge.supabase_market import SupabaseRestClient


FEATURE_VERSION = "candle-v1"
MODEL_FAMILY = "pure-python-logistic"


@dataclass(frozen=True)
class TrainingExample:
    pair: str
    open_time: datetime
    features: tuple[float, ...]
    label: int
    short_label: int


@dataclass(frozen=True)
class SplitMetrics:
    split: str
    count: int
    accuracy: float
    precision: float
    recall: float
    positive_rate: float


@dataclass(frozen=True)
class TrainedModel:
    model_version: str
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    stds: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    short_weights: tuple[float, ...]
    short_bias: float
    threshold: float
    metrics: tuple[SplitMetrics, ...]
    short_metrics: tuple[SplitMetrics, ...] = ()

    def as_artifact(self, *, pairs: list[str], trained_at: datetime, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "model_family": MODEL_FAMILY,
            "model_version": self.model_version,
            "feature_version": FEATURE_VERSION,
            "trained_at": trained_at.isoformat(),
            "pairs": pairs,
            "feature_names": list(self.feature_names),
            "means": list(self.means),
            "stds": list(self.stds),
            "weights": list(self.weights),
            "bias": self.bias,
            "short_weights": list(self.short_weights),
            "short_bias": self.short_bias,
            "threshold": self.threshold,
            "metrics": [metric.__dict__ for metric in self.metrics],
            "short_metrics": [metric.__dict__ for metric in self.short_metrics],
            "config": config,
        }


class ModelTrainingRunner:
    def __init__(
        self,
        *,
        reader: SupabaseMarketReader,
        supabase: SupabaseRestClient,
        artifact_dir: Path,
        lookback_candles: int = 500,
        horizon_candles: int = 3,
        min_examples: int = 80,
        learning_rate: float = 0.08,
        epochs: int = 450,
    ) -> None:
        self.reader = reader
        self.supabase = supabase
        self.artifact_dir = artifact_dir
        self.lookback_candles = lookback_candles
        self.horizon_candles = horizon_candles
        self.min_examples = min_examples
        self.learning_rate = learning_rate
        self.epochs = epochs

    def run(self, pairs: list[str], *, timeframe: str = "5m", now: datetime | None = None) -> TrainedModel:
        trained_at = now or datetime.now(UTC)
        examples = self._load_examples(pairs, timeframe=timeframe)
        if len(examples) < self.min_examples:
            raise ValueError(f"not enough training examples: {len(examples)} < {self.min_examples}")

        train, validation, test = chronological_splits(examples)
        model = train_logistic_model(
            train,
            validation,
            test,
            learning_rate=self.learning_rate,
            epochs=self.epochs,
            trained_at=trained_at,
        )
        config = {
            "timeframe": timeframe,
            "lookback_candles": self.lookback_candles,
            "horizon_candles": self.horizon_candles,
            "min_examples": self.min_examples,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
        }
        artifact = model.as_artifact(pairs=pairs, trained_at=trained_at, config=config)
        artifact_path, artifact_sha256 = write_model_artifact(artifact, self.artifact_dir)
        self._publish_model(
            model,
            pairs=pairs,
            artifact=artifact,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha256,
            trained_at=trained_at,
            config=config,
        )
        return model

    def _load_examples(self, pairs: list[str], *, timeframe: str) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        for pair in pairs:
            candles = self.reader.read_candles(pair, timeframe=timeframe, limit=self.lookback_candles)
            examples.extend(build_examples(pair, candles, horizon_candles=self.horizon_candles))
        return sorted(examples, key=lambda example: example.open_time)

    def _publish_model(
        self,
        model: TrainedModel,
        *,
        pairs: list[str],
        artifact: dict[str, Any],
        artifact_path: Path,
        artifact_sha256: str,
        trained_at: datetime,
        config: dict[str, Any],
    ) -> None:
        model_run_id = str(uuid4())
        artifact_uri = artifact_path.as_uri()
        metric_summary = {metric.split: metric.__dict__ for metric in model.metrics}
        self.supabase.upsert(
            "model_runs",
            [
                {
                    "id": model_run_id,
                    "model_family": MODEL_FAMILY,
                    "feature_version": FEATURE_VERSION,
                    "artifact_uri": artifact_uri,
                    "artifact_sha256": artifact_sha256,
                    "metrics": metric_summary,
                    "status": "completed",
                    "created_at": trained_at.isoformat(),
                    "updated_at": trained_at.isoformat(),
                }
            ],
            on_conflict="id",
        )
        metric_records = [
            {
                "model_run_id": model_run_id,
                "split": metric.split,
                "metric_name": name,
                "metric_value": str(value),
            }
            for metric in model.metrics
            for name, value in metric.__dict__.items()
            if name not in {"split", "count"}
        ]
        self.supabase.upsert(
            "model_metrics",
            metric_records,
            on_conflict="model_run_id,split,metric_name",
        )
        payload = {
            "model_run_id": model_run_id,
            "model_family": MODEL_FAMILY,
            "model_version": model.model_version,
            "feature_version": FEATURE_VERSION,
            "artifact_uri": artifact_uri,
            "artifact_sha256": artifact_sha256,
            "artifact": artifact,
            "pairs": pairs,
            "config": config,
            "metrics": metric_summary,
        }
        event_key = hashlib.sha256(
            json.dumps(
                {"model_version": model.model_version, "artifact_sha256": artifact_sha256},
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.supabase.upsert(
            "system_events",
            [
                {
                    "occurred_at": trained_at.isoformat(),
                    "source": "cryptoforge.model_training",
                    "severity": "info",
                    "event_type": "model.active",
                    "idempotency_key": f"model-active:{event_key}",
                    "payload": payload,
                }
            ],
            on_conflict="idempotency_key",
        )


def build_examples(pair: str, candles: list[CandleRow], *, horizon_candles: int) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    if len(candles) < 45 + horizon_candles:
        return examples
    closes = [candle.close for candle in candles]
    volumes = [candle.volume for candle in candles]
    for index in range(36, len(candles) - horizon_candles):
        window = candles[: index + 1]
        close = closes[index]
        future_close = closes[index + horizon_candles]
        if close <= 0:
            continue
        future_return = float((future_close - close) / close)
        examples.append(
            TrainingExample(
                pair=pair,
                open_time=candles[index].open_time,
                features=extract_features(window, volumes[: index + 1]),
                label=1 if future_return > 0 else 0,
                short_label=1 if future_return < 0 else 0,
            )
        )
    return examples


def extract_features(candles: list[CandleRow], volumes: list[Decimal]) -> tuple[float, ...]:
    closes = [candle.close for candle in candles]
    last = candles[-1]
    previous = candles[-2]
    close = last.close
    return_1 = (last.close - previous.close) / previous.close
    return_3 = (last.close - candles[-4].close) / candles[-4].close
    high_12 = max(candle.high for candle in candles[-12:])
    low_12 = min(candle.low for candle in candles[-12:])
    range_12 = (high_12 - low_12) / close
    volume_mean = sum(volumes[-20:]) / Decimal(min(20, len(volumes)))
    volume_ratio = last.volume / volume_mean if volume_mean > 0 else Decimal("0")
    ema_fast = ema_decimal(closes, 12)
    ema_slow = ema_decimal(closes, 36)
    ema_gap = (ema_fast - ema_slow) / close
    rsi_value = rsi(closes, 14) / Decimal("100")
    candle_body = (last.close - last.open) / close
    return tuple(
        float(value)
        for value in (
            return_1,
            return_3,
            range_12,
            volume_ratio,
            ema_gap,
            rsi_value,
            candle_body,
        )
    )


def chronological_splits(
    examples: list[TrainingExample],
) -> tuple[list[TrainingExample], list[TrainingExample], list[TrainingExample]]:
    train_end = max(1, int(len(examples) * 0.70))
    validation_end = max(train_end + 1, int(len(examples) * 0.85))
    return examples[:train_end], examples[train_end:validation_end], examples[validation_end:]


def train_logistic_model(
    train: list[TrainingExample],
    validation: list[TrainingExample],
    test: list[TrainingExample],
    *,
    learning_rate: float,
    epochs: int,
    trained_at: datetime,
) -> TrainedModel:
    feature_names = (
        "return_1",
        "return_3",
        "range_12",
        "volume_ratio",
        "ema_gap",
        "rsi_14",
        "candle_body",
    )
    means, stds = fit_standardizer([example.features for example in train])
    weights, bias = fit_logistic_head(
        train,
        means,
        stds,
        learning_rate=learning_rate,
        epochs=epochs,
        label_attr="label",
    )
    short_weights, short_bias = fit_logistic_head(
        train,
        means,
        stds,
        learning_rate=learning_rate,
        epochs=epochs,
        label_attr="short_label",
    )

    metrics = (
        evaluate_split("train", train, weights, bias, means, stds, label_attr="label"),
        evaluate_split("validation", validation, weights, bias, means, stds, label_attr="label"),
        evaluate_split("test", test, weights, bias, means, stds, label_attr="label"),
    )
    short_metrics = (
        evaluate_split("train", train, short_weights, short_bias, means, stds, label_attr="short_label"),
        evaluate_split("validation", validation, short_weights, short_bias, means, stds, label_attr="short_label"),
        evaluate_split("test", test, short_weights, short_bias, means, stds, label_attr="short_label"),
    )
    model_hash = hashlib.sha256(
        json.dumps(
            {
                "trained_at": trained_at.isoformat(),
                "weights": weights,
                "bias": bias,
                "short_weights": short_weights,
                "short_bias": short_bias,
                "metrics": [metric.__dict__ for metric in metrics],
                "short_metrics": [metric.__dict__ for metric in short_metrics],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()[:10]
    return TrainedModel(
        model_version=f"{MODEL_FAMILY}-{FEATURE_VERSION}-{trained_at:%Y%m%d}-{model_hash}",
        feature_names=feature_names,
        means=tuple(means),
        stds=tuple(stds),
        weights=tuple(weights),
        bias=bias,
        short_weights=tuple(short_weights),
        short_bias=short_bias,
        threshold=0.5,
        metrics=metrics,
        short_metrics=short_metrics,
    )


def fit_logistic_head(
    train: list[TrainingExample],
    means: list[float],
    stds: list[float],
    *,
    learning_rate: float,
    epochs: int,
    label_attr: str,
) -> tuple[list[float], float]:
    train_x = [standardize(example.features, means, stds) for example in train]
    train_y = [int(getattr(example, label_attr)) for example in train]
    weights = [0.0 for _ in means]
    bias = 0.0
    for _ in range(epochs):
        grad_w = [0.0 for _ in weights]
        grad_b = 0.0
        for features, label in zip(train_x, train_y):
            prediction = sigmoid(dot(weights, features) + bias)
            error = prediction - label
            for index, value in enumerate(features):
                grad_w[index] += error * value
            grad_b += error
        scale = learning_rate / max(len(train_x), 1)
        weights = [weight - scale * grad for weight, grad in zip(weights, grad_w)]
        bias -= scale * grad_b
    return weights, bias


def evaluate_split(
    split: str,
    examples: list[TrainingExample],
    weights: list[float],
    bias: float,
    means: list[float],
    stds: list[float],
    *,
    label_attr: str = "label",
) -> SplitMetrics:
    if not examples:
        return SplitMetrics(split, 0, 0.0, 0.0, 0.0, 0.0)
    true_positive = false_positive = true_negative = false_negative = positives = 0
    for example in examples:
        probability = predict_probability(example.features, weights, bias, means, stds)
        predicted = 1 if probability >= 0.5 else 0
        label = int(getattr(example, label_attr))
        positives += predicted
        if predicted == 1 and label == 1:
            true_positive += 1
        elif predicted == 1 and label == 0:
            false_positive += 1
        elif predicted == 0 and label == 0:
            true_negative += 1
        else:
            false_negative += 1
    count = len(examples)
    accuracy = (true_positive + true_negative) / count
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    positive_rate = positives / count
    return SplitMetrics(split, count, accuracy, precision, recall, positive_rate)


def predict_probability(
    features: tuple[float, ...],
    weights: list[float],
    bias: float,
    means: list[float],
    stds: list[float],
) -> float:
    return sigmoid(dot(weights, standardize(features, means, stds)) + bias)


def fit_standardizer(rows: list[tuple[float, ...]]) -> tuple[list[float], list[float]]:
    columns = list(zip(*rows))
    means = [sum(column) / len(column) for column in columns]
    stds = []
    for mean, column in zip(means, columns):
        variance = sum((value - mean) ** 2 for value in column) / max(len(column), 1)
        stds.append(math.sqrt(variance) or 1.0)
    return means, stds


def standardize(features: tuple[float, ...], means: list[float], stds: list[float]) -> tuple[float, ...]:
    return tuple((value - mean) / std for value, mean, std in zip(features, means, stds))


def dot(left: list[float] | tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def ema_decimal(values: list[Decimal], period: int) -> Decimal:
    alpha = Decimal("2") / Decimal(period + 1)
    current = values[0]
    for value in values[1:]:
        current = value * alpha + current * (Decimal("1") - alpha)
    return current


def write_model_artifact(payload: dict[str, Any], artifact_dir: Path) -> tuple[Path, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    path = artifact_dir / f"{payload['model_version']}-{checksum[:12]}.json"
    path.write_bytes(raw)
    return path, checksum


def load_pairs_from_file(path: Path | None) -> list[str]:
    return file_pairs(path)
