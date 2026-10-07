from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    future_return: float = 0.0
    label_end_time: datetime | None = None


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
    selected_l2: float = 0.0
    validation_search: tuple[dict[str, Any], ...] = ()

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
            "selected_l2": self.selected_l2,
            "validation_search": list(self.validation_search),
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
        registry: Any = None,
        round_trip_cost: float = 0.003,
        min_label_return: float | None = None,
    ) -> None:
        self.reader = reader
        self.supabase = supabase
        self.artifact_dir = artifact_dir
        self.lookback_candles = lookback_candles
        self.horizon_candles = horizon_candles
        self.min_examples = min_examples
        self.learning_rate = learning_rate
        self.epochs = epochs
        if not 0 <= round_trip_cost < 1:
            raise ValueError("round_trip_cost must be in [0, 1)")
        self.round_trip_cost = round_trip_cost
        self.min_label_return = round_trip_cost if min_label_return is None else min_label_return
        if not 0 <= self.min_label_return < 1:
            raise ValueError("min_label_return must be in [0, 1)")
        self.registry = registry
        self.last_promotion: dict[str, Any] = {}

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
        from cryptoforge.model_registry import ActiveModelRegistry
        registry = self.registry or ActiveModelRegistry(self.supabase)
        # Registry/network/checksum errors abort publication; never bypass comparison.
        incumbent = registry.latest(now=trained_at, max_age=timedelta(days=36500))
        config["round_trip_cost"] = self.round_trip_cost
        config["min_label_return"] = self.min_label_return
        config["training_label_end"] = max(
            example.label_end_time or example.open_time for example in train
        ).isoformat()
        self.last_promotion = promotion_decision(
            model,
            incumbent,
            test,
            round_trip_cost=self.round_trip_cost,
            min_label_return=self.min_label_return,
        )
        artifact = model.as_artifact(pairs=pairs, trained_at=trained_at, config=config)
        artifact["promotion"] = self.last_promotion
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
            examples.extend(
                build_examples(
                    pair,
                    candles,
                    horizon_candles=self.horizon_candles,
                    min_label_return=self.min_label_return,
                )
            )
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
        artifact_uri = artifact_path.resolve().as_uri()
        metric_summary = {
            "long": {metric.split: metric.__dict__ for metric in model.metrics},
            "short": {metric.split: metric.__dict__ for metric in model.short_metrics},
        }
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
                "metric_name": f"long_{name}",
                "metric_value": str(value),
            }
            for metric in model.metrics
            for name, value in metric.__dict__.items()
            if name not in {"split", "count"}
        ] + [
            {
                "model_run_id": model_run_id,
                "split": metric.split,
                "metric_name": f"short_{name}",
                "metric_value": str(value),
            }
            for metric in model.short_metrics
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
                    "event_type": "model.active" if self.last_promotion["promoted"] else "model.candidate",
                    "idempotency_key": f"model-training:{event_key}",
                    "payload": payload,
                }
            ],
            on_conflict="idempotency_key",
        )


def build_examples(
    pair: str,
    candles: list[CandleRow],
    *,
    horizon_candles: int,
    min_label_return: float = 0.0,
) -> list[TrainingExample]:
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
                label=1 if future_return > min_label_return else 0,
                short_label=1 if future_return < -min_label_return else 0,
                future_return=future_return,
                label_end_time=candles[index + horizon_candles].open_time,
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
    # Keep all pairs at a timestamp together and purge labels crossing a boundary.
    validation_start = examples[min(train_end, len(examples) - 1)].open_time
    test_start = examples[min(validation_end, len(examples) - 1)].open_time
    train = [e for e in examples if e.open_time < validation_start and
             (e.label_end_time or e.open_time) < validation_start]
    validation = [e for e in examples if validation_start <= e.open_time < test_start and
                  (e.label_end_time or e.open_time) < test_start]
    test = [e for e in examples if e.open_time >= test_start]
    return train, validation, test


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
    # Choose regularization using validation only; test remains untouched.
    trials = []
    for l2 in (0.0, 0.01, 0.1):
        candidate_weights, candidate_bias = fit_logistic_head(
            train, means, stds, learning_rate=learning_rate, epochs=epochs,
            label_attr="label", l2=l2,
        )
        loss = 0.0
        for example in validation:
            probability = predict_probability(example.features, candidate_weights, candidate_bias, means, stds)
            probability = min(max(probability, 1e-12), 1-1e-12)
            loss -= example.label * math.log(probability) + (1-example.label) * math.log(1-probability)
        trials.append((loss/max(len(validation),1), l2, candidate_weights, candidate_bias))
    _, selected_l2, weights, bias = min(trials, key=lambda trial: trial[0])
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
        selected_l2=selected_l2,
        validation_search=tuple({"l2": t[1], "validation_log_loss": t[0]} for t in trials),
    )


def fit_logistic_head(
    train: list[TrainingExample],
    means: list[float],
    stds: list[float],
    *,
    learning_rate: float,
    epochs: int,
    label_attr: str,
    l2: float = 0.0,
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
        weights = [weight - scale * grad - learning_rate * l2 * weight
                   for weight, grad in zip(weights, grad_w)]
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


def promotion_decision(model: TrainedModel, incumbent: Any, test: list[TrainingExample], *,
                       round_trip_cost: float, min_examples: int = 200,
                       min_signals: int = 30,
                       min_label_return: float | None = None) -> dict[str, Any]:
    """Conservative signal screen, not a portfolio backtest or profitability guarantee."""
    eligible = test
    if incumbent is not None:
        if incumbent.feature_version != FEATURE_VERSION:
            return {"promoted": False, "reason": "incompatible_incumbent"}
        config = incumbent.artifact.get("config", {})
        same_label_config = (
            min_label_return is None
            or float(config.get("min_label_return", 0.0)) == float(min_label_return)
        )
        if same_label_config:
            cutoff = datetime.fromisoformat(config.get("training_label_end") or
                                            incumbent.artifact.get("trained_at") or
                                            incumbent.occurred_at.isoformat())
            eligible = [e for e in test if e.open_time > cutoff]
    result: dict[str, Any] = {"promoted": False, "count": len(eligible),
                              "incumbent": getattr(incumbent, "model_version", None)}
    if len(eligible) < min_examples:
        return {**result, "reason": "insufficient_unseen_examples"}

    def score(predict):
        signals = [e for e in eligible if predict(e.features) >= model.threshold]
        returns = [e.future_return - round_trip_cost for e in signals]
        return {"signals": len(signals),
                "net_return_per_example": sum(returns) / len(eligible),
                "mean_net_signal_return": sum(returns) / max(len(signals), 1)}

    candidate = score(lambda f: predict_probability(f, list(model.weights), model.bias,
                                                    list(model.means), list(model.stds)))
    measured = evaluate_split("promotion", eligible, list(model.weights), model.bias,
                              list(model.means), list(model.stds))
    baseline = max(sum(e.label for e in eligible), sum(1-e.label for e in eligible)) / len(eligible)
    result.update(candidate=candidate, accuracy=measured.accuracy, majority_baseline=baseline,
                  round_trip_cost=round_trip_cost)
    if candidate["signals"] < min_signals:
        return {**result, "reason": "insufficient_signals"}
    if measured.accuracy <= baseline or candidate["mean_net_signal_return"] <= 0:
        return {**result, "reason": "fails_baseline_or_costs"}
    if incumbent is not None:
        previous = score(incumbent.predict_probability)
        previous_metrics = evaluate_split("promotion", eligible, incumbent.artifact["weights"],
                                          incumbent.artifact["bias"], incumbent.artifact["means"],
                                          incumbent.artifact["stds"])
        result["previous"] = {**previous, "accuracy": previous_metrics.accuracy}
        if measured.accuracy < previous_metrics.accuracy or candidate["net_return_per_example"] <= previous["net_return_per_example"]:
            return {**result, "reason": "does_not_beat_incumbent"}
    return {**result, "promoted": True, "reason": "passed_quality_screen"}
