from __future__ import annotations

from dataclasses import dataclass, replace
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
FEATURE_NAMES = ("return_1","return_3","range_12","volume_ratio","ema_gap","rsi_14","candle_body")


def model_evidence_identity(model):
    return (getattr(model,'model_version',None),getattr(model,'artifact_sha256',None),
            getattr(model,'model_run_id',None))


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
    probability_diagnostics: dict[str, Any] | None = None
    feature_reference: dict[str, Any] | None = None

    def as_artifact(self, *, pairs: list[str], trained_at: datetime, config: dict[str, Any]) -> dict[str, Any]:
        if config.get('source')=='observed_real_cash_recovery_memory':
            raise ValueError('primary price model forbids cash-target provenance')
        if 'target_version' in config and config['target_version']!='fixed-future-return-v1':
            raise ValueError('primary price model cannot relabel a different target')
        target_config={**config,'target_version':'fixed-future-return-v1'}
        return {
            "model_family": MODEL_FAMILY,
            'target_version':'fixed-future-return-v1',
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
            "probability_diagnostics": self.probability_diagnostics,
            'feature_reference':self.feature_reference,
            "config": target_config,
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
        feedback_reader: Any = None,
        round_trip_cost: float = 0.003,
        min_label_return: float | None = None,
        minimum_source_coverage: float = 0.8,
        feature_lookback_candles: int = 36,
        maximum_source_age: timedelta = timedelta(minutes=15),
    ) -> None:
        if any(type(value) is not int or value<1 for value in (lookback_candles,horizon_candles,min_examples,epochs)):
            raise ValueError('positive integer history, horizon, sample minimum and epochs required')
        if not math.isfinite(learning_rate) or learning_rate<=0:
            raise ValueError('positive finite learning rate required')
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
        self.feedback_reader = feedback_reader
        if not 0<minimum_source_coverage<=1:raise ValueError('source coverage must be in (0,1]')
        if type(feature_lookback_candles) is not int or feature_lookback_candles<36 or feature_lookback_candles>lookback_candles:
            raise ValueError('feature lookback must fit history and contain at least36 bars')
        self.feature_lookback_candles=feature_lookback_candles
        self.minimum_source_coverage=minimum_source_coverage
        if maximum_source_age<=timedelta(0):raise ValueError('positive source freshness limit required')
        self.maximum_source_age=maximum_source_age
        self.last_source_admission: dict[str,Any]={}
        self.last_feedback: dict[str, Any] = {}
        self.last_promotion: dict[str, Any] = {}

    def run(self, pairs: list[str], *, timeframe: str = "5m", now: datetime | None = None) -> TrainedModel:
        trained_at = now or datetime.now(UTC)
        from cryptoforge.training_snapshot import save_training_snapshot,save_runtime_sources
        from cryptoforge.source_contract import source_hashes,primary_training_sources
        dependencies=primary_training_sources()
        source_fingerprint=source_hashes(dependencies)
        runtime_sources=save_runtime_sources(self.artifact_dir/'input-snapshots'/'runtime',dependencies,source_fingerprint)
        pairs=list(dict.fromkeys(pairs));self.last_source_admission={}
        try:examples = self._load_examples(pairs, timeframe=timeframe, as_of=trained_at)
        except Exception as exc:
            if self.last_source_admission:
                self.last_source_admission.update(status='aborted',fatal_error_type=type(exc).__name__)
            raise
        finally:
            if self.last_source_admission:
                import os,tempfile
                directory=self.artifact_dir/'diagnostics';directory.mkdir(parents=True,exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w',dir=directory,delete=False,suffix='.tmp') as stream:
                    json.dump(self.last_source_admission,stream,indent=2);temporary=Path(stream.name)
                temporary.chmod(0o600);os.replace(temporary,directory/'last-source-admission.json')
        if self.last_source_admission['coverage_fraction']<self.minimum_source_coverage:
            raise ValueError('insufficient admitted source coverage; defer model training')
        pairs=list(self.last_source_admission['accepted_pairs'])
        if len(examples) < self.min_examples:
            raise ValueError(f"not enough training examples: {len(examples)} < {self.min_examples}")

        train, validation, test = chronological_splits(examples)
        effective_cost = self.round_trip_cost
        label_minimum = self.min_label_return
        if self.feedback_reader is not None:
            from cryptoforge.live_feedback import candidate_cost_floor
            # Cost parameters only use executions completed within train.
            # Validation/test outcomes must not tune even the cost assumption.
            feedback_cutoff = max(e.label_end_time or e.open_time for e in train)
            try:
                feedback = self.feedback_reader.read(as_of=feedback_cutoff)
                learned_floor = candidate_cost_floor(feedback)
                if learned_floor is not None:
                    effective_cost = max(effective_cost, float(learned_floor))
                    label_minimum = max(label_minimum, effective_cost)
                self.last_feedback = {
                    "status": ("unverified_accounting" if not feedback.get("accounting_quality_verified") else
                               "calibrated" if learned_floor is not None else "insufficient_prior_evidence"),
                    "information_end": feedback_cutoff.isoformat(),
                    "summary": feedback["summary"],
                    "evidence_policy": feedback.get("evidence_policy", "source_completed_executions"),
                    "learned_cost_floor": str(learned_floor) if learned_floor is not None else None,
                    "automatic_live_changes_allowed": False,
                }
            except Exception as exc:
                # Save training evidence without pretending current costs were verified.
                self.last_feedback = {"status": "unavailable", "error": type(exc).__name__,
                                      "information_end": feedback_cutoff.isoformat()}
        examples = [replace(e, label=int(e.future_return > label_minimum),
                            short_label=int(e.future_return < -label_minimum)) for e in examples]
        train, validation, test = chronological_splits(examples)
        snapshot=save_training_snapshot(self.artifact_dir/'input-snapshots',
            splits={'train':train,'validation':validation,'test':test},metadata={
                'data_snapshot_at':trained_at.isoformat(),'timeframe':timeframe,
                'feature_version':FEATURE_VERSION,'feature_names':list(FEATURE_NAMES),
                'feature_calculation_contract':'bounded-window-candle-v1',
                'feature_lookback_candles':self.feature_lookback_candles,
                'horizon_candles':self.horizon_candles,'min_label_return':label_minimum,
                'round_trip_cost':effective_cost,'implementation_hashes':source_fingerprint,
                'runtime_source_bundle':runtime_sources,
                'source_admission':self.last_source_admission})
        model = train_logistic_model(
            train,
            validation,
            test,
            learning_rate=self.learning_rate,
            epochs=self.epochs,
            trained_at=trained_at,
        )
        if source_hashes(dependencies)!=source_fingerprint:
            raise ValueError('primary training source changed during fit; defer publication')
        config = {
            "timeframe": timeframe,
            "input_candle_state": "closed_only",
            "lookback_candles": self.lookback_candles,
            "horizon_candles": self.horizon_candles,
            "feature_lookback_candles": self.feature_lookback_candles,
            "feature_calculation_contract": "bounded-window-candle-v1",
            "min_examples": self.min_examples,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "source_admission": self.last_source_admission,
            'training_input_snapshot':snapshot,
            'implementation_hashes':source_fingerprint,
            'runtime_source_bundle':runtime_sources,
        }
        from cryptoforge.model_registry import ActiveModelRegistry
        registry = self.registry or ActiveModelRegistry(self.supabase)
        # Registry/network/checksum errors abort publication; never bypass comparison.
        incumbent = registry.latest(now=datetime.now(UTC) if now is None else trained_at, max_age=timedelta(days=36500))
        candidate_reader=getattr(registry,'latest_candidate',None)
        previous_candidate=candidate_reader(now=datetime.now(UTC) if now is None else trained_at,
            max_age=timedelta(days=36500)) if candidate_reader is not None else None
        previous_evaluation_end=None
        if previous_candidate is not None:
            previous_config=previous_candidate.artifact.get('config') or {}
            prior_boundaries=[previous_config[key] for key in (
                'evaluation_information_end','evaluation_history_end') if previous_config.get(key)]
            if not prior_boundaries:prior_boundaries=[previous_candidate.occurred_at.isoformat()]
            previous_evaluation_end=max(datetime.fromisoformat(str(value).replace('Z','+00:00')) for value in prior_boundaries)
        config['promotion_reference']={'incumbent_identity':model_evidence_identity(incumbent),
            'previous_candidate_identity':model_evidence_identity(previous_candidate),
            'previous_candidate_evaluation_end':previous_evaluation_end.isoformat() if previous_evaluation_end else None}
        config["round_trip_cost"] = effective_cost
        config["min_label_return"] = label_minimum
        config["live_feedback"] = self.last_feedback
        config["training_label_end"] = max(
            example.label_end_time or example.open_time for example in train
        ).isoformat()
        config["fit_information_end"] = max(
            example.label_end_time or example.open_time for example in train + validation
        ).isoformat()
        config["evaluation_information_end"] = max(
            example.label_end_time or example.open_time for example in test
        ).isoformat()
        config['evaluation_history_end']=max(
            datetime.fromisoformat(config['evaluation_information_end']),
            previous_evaluation_end or datetime.fromisoformat(config['evaluation_information_end'])).isoformat()
        self.last_promotion = promotion_decision(
            model,
            incumbent,
            test,
            round_trip_cost=effective_cost,
            min_label_return=label_minimum,
            candidate_information_end=datetime.fromisoformat(config["fit_information_end"]),
            candidate_feature_contract={key:config[key] for key in (
                'timeframe','input_candle_state','feature_calculation_contract','feature_lookback_candles')},
            previous_evaluation_end=previous_evaluation_end,
        )
        if self.feedback_reader is not None and self.last_feedback.get("status") in {"unavailable", "unverified_accounting"}:
            self.last_promotion = {**self.last_promotion, "promoted": False,
                                   "reason": "live_feedback_unavailable"}
        if self.last_promotion.get("promoted"):
            current = registry.latest(now=datetime.now(UTC) if now is None else trained_at, max_age=timedelta(days=36500))
            if model_evidence_identity(current)!=model_evidence_identity(incumbent):
                self.last_promotion = {**self.last_promotion,"promoted":False,
                                       "reason":"champion_changed_during_training"}
            if candidate_reader is not None:
                current_candidate=candidate_reader(now=datetime.now(UTC) if now is None else trained_at,
                    max_age=timedelta(days=36500))
                if model_evidence_identity(current_candidate)!=model_evidence_identity(previous_candidate):
                    self.last_promotion={**self.last_promotion,'promoted':False,
                        'reason':'candidate_evaluation_changed_during_training'}
        published_at = datetime.now(UTC) if now is None else trained_at
        config["data_snapshot_at"] = trained_at.isoformat()
        config["training_finished_at"] = published_at.isoformat()
        artifact = model.as_artifact(pairs=pairs, trained_at=trained_at, config=config)
        artifact["promotion"] = self.last_promotion
        artifact_path, artifact_sha256 = write_model_artifact(artifact, self.artifact_dir)
        self._publish_model(
            model,
            pairs=pairs,
            artifact=artifact,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha256,
            trained_at=published_at,
            config=config,
        )
        return model

    def _load_examples(self, pairs: list[str], *, timeframe: str, as_of: datetime) -> list[TrainingExample]:
        from cryptoforge.candle_contract import closed_snapshot,TIMEFRAMES
        if timeframe not in TIMEFRAMES or as_of.tzinfo is None:raise ValueError('supported timeframe and aware training cutoff required')
        self.last_source_admission={'as_of':as_of.isoformat(),'requested_pairs':list(pairs),
            'accepted_pairs':[],'excluded_pairs':{},'coverage_fraction':0.0,
            'maximum_source_age_seconds':self.maximum_source_age.total_seconds(),'last_closed_at_by_pair':{},
            'minimum_source_coverage':self.minimum_source_coverage,'gap_filling_allowed':False,'status':'collecting'}
        examples=[]
        for pair in pairs:
            # Network/authentication/reader failures remain fatal, not silent exclusions.
            candles=self.reader.read_candles(pair,timeframe=timeframe,limit=self.lookback_candles)
            try:
                candles=closed_snapshot(candles,timeframe=timeframe,as_of=as_of)
                if not candles:raise ValueError('no known closed source candles')
                latest_closed=candles[-1].open_time+timedelta(minutes=TIMEFRAMES[timeframe])
                self.last_source_admission['last_closed_at_by_pair'][pair]=latest_closed.isoformat()
                if as_of-latest_closed>self.maximum_source_age:
                    raise ValueError('stale closed training source')
                if any(c.pair!=pair or c.symbol!=pair.replace('/','') for c in candles):
                    raise ValueError('training market identity mismatch')
                if any(not all(v.is_finite() for v in (c.open,c.high,c.low,c.close,c.volume)) or not
                    (0<c.low<=min(c.open,c.close)<=max(c.open,c.close)<=c.high and c.volume>=0) for c in candles):
                    raise ValueError('invalid training OHLCV')
                batch=build_examples(pair,candles,horizon_candles=self.horizon_candles,min_label_return=self.min_label_return,feature_lookback_candles=self.feature_lookback_candles)
                if not batch:raise ValueError('insufficient closed history for complete labels')
            except (ValueError,ArithmeticError) as exc:
                self.last_source_admission['excluded_pairs'][pair]=str(exc);continue
            self.last_source_admission['accepted_pairs'].append(pair);examples.extend(batch)
        self.last_source_admission['coverage_fraction']=len(self.last_source_admission['accepted_pairs'])/len(pairs) if pairs else 0.0
        self.last_source_admission['examples']=len(examples)
        self.last_source_admission['status']='completed'
        return sorted(examples,key=lambda example:example.open_time)

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
    feature_lookback_candles: int | None = None,
) -> list[TrainingExample]:
    if type(horizon_candles) is not int or horizon_candles<1:
        raise ValueError('positive integer label horizon required')
    if not math.isfinite(min_label_return) or not 0<=min_label_return<1:
        raise ValueError('finite label threshold in [0,1) required')
    if feature_lookback_candles is not None and (type(feature_lookback_candles) is not int or feature_lookback_candles<36):
        raise ValueError('feature lookback needs at least36 bars')
    examples: list[TrainingExample] = []
    if len(candles) < 45 + horizon_candles:
        return examples
    step=candles[1].open_time-candles[0].open_time
    if step.total_seconds()<=0 or any(b.open_time-a.open_time!=step for a,b in zip(candles,candles[1:])):
        raise ValueError("training labels cannot cross duplicate or missing candles")
    closes = [candle.close for candle in candles]
    volumes = [candle.volume for candle in candles]
    ema_fast = closes[0]
    ema_slow = closes[0]
    ema_gaps = []
    for value in closes:
        ema_fast = value * (Decimal(2)/Decimal(13)) + ema_fast * (Decimal(1)-Decimal(2)/Decimal(13))
        ema_slow = value * (Decimal(2)/Decimal(37)) + ema_slow * (Decimal(1)-Decimal(2)/Decimal(37))
        ema_gaps.append(float((ema_fast-ema_slow)/value) if value > 0 else 0.0)
    width=feature_lookback_candles or 36
    for index in range(max(36,width-1), len(candles) - horizon_candles):
        window = candles[index-width+1:index+1]
        close = closes[index]
        future_close = closes[index + horizon_candles]
        if close <= 0:
            continue
        future_return = float((future_close - close) / close)
        features = list(extract_features(window, volumes[index-width+1:index+1]))
        if feature_lookback_candles is None:features[4] = ema_gaps[index]
        if not all(math.isfinite(value) for value in (*features,future_return)) or future_return< -1:
            raise ValueError('nonfinite derived training features or return')
        examples.append(
            TrainingExample(
                pair=pair,
                open_time=candles[index].open_time,
                features=tuple(features),
                label=1 if future_return > min_label_return else 0,
                short_label=1 if future_return < -min_label_return else 0,
                future_return=future_return,
                label_end_time=candles[index + horizon_candles].open_time + step,
            )
        )
    return examples


def extract_features(candles: list[CandleRow], volumes: list[Decimal]) -> tuple[float, ...]:
    if len(candles)<36 or len(volumes)!=len(candles):raise ValueError('complete paired feature history required')
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
    features=tuple(
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
    if not all(math.isfinite(value) for value in features):raise ValueError('nonfinite derived candle features')
    return features


def chronological_splits(
    examples: list[TrainingExample],
) -> tuple[list[TrainingExample], list[TrainingExample], list[TrainingExample]]:
    if not examples:raise ValueError('nonempty chronological examples required')
    examples=sorted(examples,key=lambda example:example.open_time)
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
    if not train or not validation or not test:
        raise ValueError('nonempty train, validation and test splits required')
    if not math.isfinite(learning_rate) or learning_rate<=0 or type(epochs) is not int or epochs<=0:
        raise ValueError('positive finite learning rate and positive integer epochs required')
    feature_names = FEATURE_NAMES
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
    from cryptoforge.classifier_diagnostics import split_diagnostics
    from cryptoforge.feature_drift import training_feature_reference
    feature_reference=training_feature_reference([row.features for row in train],names=feature_names,means=means,stds=stds)
    diagnostics = {}
    for name, head_weights, head_bias, label_attr in (
        ('long', weights, bias, 'label'), ('short', short_weights, short_bias, 'short_label')
    ):
        train_rate = sum(getattr(e,label_attr) for e in train)/len(train)
        diagnostics[name] = {split: split_diagnostics(rows,
            [predict_probability(e.features,head_weights,head_bias,means,stds) for e in rows],
            train_positive_rate=train_rate,threshold=0.5,label_attr=label_attr)
            for split,rows in (('train',train),('validation',validation),('test',test))}
    model_hash = hashlib.sha256(
        json.dumps(
            {
                "trained_at": trained_at.isoformat(),
                'feature_names':feature_names,'means':means,'stds':stds,'threshold':0.5,
                'selected_l2':selected_l2,
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
        probability_diagnostics=diagnostics,
        feature_reference=feature_reference,
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
    if not features or len(weights)!=len(features) or not math.isfinite(float(bias)):
        raise ValueError('invalid probability model shape or bias')
    score=dot([float(value) for value in weights],standardize(features,means,stds))+float(bias)
    if not math.isfinite(score):raise ValueError('nonfinite probability score')
    return sigmoid(score)


def fit_standardizer(rows: list[tuple[float, ...]]) -> tuple[list[float], list[float]]:
    if not rows or not rows[0] or any(len(row)!=len(rows[0]) or not all(math.isfinite(v) for v in row) for row in rows):
        raise ValueError('finite nonempty consistent standardizer rows required')
    columns = list(zip(*rows))
    means = [sum(column) / len(column) for column in columns]
    stds = []
    for mean, column in zip(means, columns):
        try:variance = sum((value - mean) ** 2 for value in column) / len(column)
        except ArithmeticError as exc:raise ValueError('unstable standardizer variance') from exc
        stds.append(math.sqrt(variance) or 1.0)
    if not all(math.isfinite(value) for value in (*means,*stds)):
        raise ValueError('nonfinite fitted standardizer')
    return means, stds


def standardize(features: tuple[float, ...], means: list[float], stds: list[float]) -> tuple[float, ...]:
    if not features or not len(features)==len(means)==len(stds):
        raise ValueError('feature/standardizer dimensions differ')
    values=tuple(float(value) for value in features);centers=[float(value) for value in means];scales=[float(value) for value in stds]
    if not all(math.isfinite(value) for value in (*values,*centers,*scales)) or any(value<=0 for value in scales):
        raise ValueError('finite features and positive standard deviations required')
    result=tuple((value-mean)/std for value,mean,std in zip(values,centers,scales))
    if not all(math.isfinite(value) for value in result):raise ValueError('nonfinite standardized features')
    return result


def dot(left: list[float] | tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left)!=len(right):raise ValueError('coefficient/feature dimensions differ')
    result=sum(a*b for a,b in zip(left,right))
    if not math.isfinite(result):raise ValueError('nonfinite model dot product')
    return result


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
    import os,re,tempfile
    version=payload.get('model_version')
    if not isinstance(version,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',version):
        raise ValueError('safe model version filename required')
    artifact_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, sort_keys=True,allow_nan=False).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    path = artifact_dir / f"{payload['model_version']}-{checksum[:12]}.json"
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('existing model artifact differs from content address')
        path.chmod(0o600)
        return path,checksum
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=artifact_dir,delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return path, checksum


def load_pairs_from_file(path: Path | None) -> list[str]:
    return file_pairs(path)


def promotion_decision(model: TrainedModel, incumbent: Any, test: list[TrainingExample], *,
                       round_trip_cost: float, min_examples: int = 200,
                       min_signals: int = 30,
                       min_label_return: float | None = None,
                       candidate_information_end: datetime | None = None,
                       candidate_feature_contract: dict[str, Any] | None = None,
                       previous_evaluation_end: datetime | None = None) -> dict[str, Any]:
    """Conservative signal screen, not a portfolio backtest or profitability guarantee."""
    if (not math.isfinite(round_trip_cost) or not 0<=round_trip_cost<1
        or not math.isfinite(model.threshold) or not 0<=model.threshold<=1
        or any(type(value) is not int or value<1 for value in (min_examples,min_signals))):
        return {'promoted':False,'reason':'invalid_promotion_parameters'}
    if (len({(e.pair,e.open_time) for e in test})!=len(test)
        or any(e.label not in (0,1) or not math.isfinite(e.future_return) or e.future_return< -1
               or e.open_time.tzinfo is None for e in test)):
        return {'promoted':False,'reason':'invalid_evaluation_examples'}
    eligible = test
    cutoffs: list[datetime] = []
    if candidate_information_end is not None:
        cutoffs.append(candidate_information_end)
    if previous_evaluation_end is not None:
        cutoffs.append(previous_evaluation_end)
    comparison_blocked=None;contract_details={}
    if incumbent is not None:
        if incumbent.feature_version != FEATURE_VERSION:
            comparison_blocked='incompatible_incumbent'
        config = incumbent.artifact.get("config") or {}
        if candidate_feature_contract is not None and any(
            config.get(key)!=value for key,value in candidate_feature_contract.items()
        ):
            comparison_blocked=comparison_blocked or 'incompatible_feature_calculation_contract'
            contract_details={'candidate_feature_contract':candidate_feature_contract,
                    'incumbent_feature_contract':{key:config.get(key) for key in candidate_feature_contract}}
        # Promotion itself used evaluation data, so it must also remain excluded.
        values = [config.get(key) for key in (
            "fit_information_end", "evaluation_information_end", "evaluation_history_end", "validation_end", "training_label_end"
        ) if config.get(key)]
        if not config.get("fit_information_end"):
            # Older artifacts lack complete selection boundaries: use publication time.
            values.append(incumbent.artifact.get("trained_at") or incumbent.occurred_at.isoformat())
        try:
            cutoffs.extend(datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in values)
        except (ValueError, TypeError):
            return {"promoted": False, "reason": "invalid_information_boundary"}
    if any(cutoff.tzinfo is None or cutoff.utcoffset() is None for cutoff in cutoffs):
        return {"promoted": False, "reason": "invalid_information_boundary"}
    if cutoffs:
        cutoff = max(cutoffs)
        eligible = [e for e in test if e.open_time > cutoff]
    result: dict[str, Any] = {"promoted": False, "count": len(eligible),
                              "incumbent": getattr(incumbent, "model_version", None),**contract_details}
    if comparison_blocked:result['comparison_blocked_reason']=comparison_blocked
    result['previous_candidate_evaluation_end']=previous_evaluation_end.isoformat() if previous_evaluation_end is not None else None
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
                  round_trip_cost=round_trip_cost,
                  scope='fixed_candle_return_signal_screen_not_executed_cash_or_portfolio_income')
    if candidate["signals"] < min_signals:
        return {**result, "reason": "insufficient_signals"}
    if measured.accuracy <= baseline or candidate["mean_net_signal_return"] <= 0:
        return {**result, "reason": "fails_baseline_or_costs"}
    if comparison_blocked:return {**result,'reason':comparison_blocked}
    if incumbent is not None:
        previous = score(incumbent.predict_probability)
        previous_metrics = evaluate_split("promotion", eligible, incumbent.artifact["weights"],
                                          incumbent.artifact["bias"], incumbent.artifact["means"],
                                          incumbent.artifact["stds"])
        result["previous"] = {**previous, "accuracy": previous_metrics.accuracy}
        if measured.accuracy < previous_metrics.accuracy or candidate["net_return_per_example"] <= previous["net_return_per_example"]:
            return {**result, "reason": "does_not_beat_incumbent"}
    return {**result, "promoted": True, "reason": "passed_quality_screen"}
