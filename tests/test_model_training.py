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
    assert model.probability_diagnostics['long']['test']['count']==len(test)
    assert model.probability_diagnostics['long']['test']['train_positive_rate']==sum(e.label for e in train)/len(train)


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

    model = runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, 15, 5, tzinfo=UTC))

    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["model_version"] == model.model_version
    from cryptoforge.training_snapshot import load_training_snapshot
    snapshot=load_training_snapshot(payload['config']['training_input_snapshot'])
    assert len(snapshot['splits']['test'])==model.metrics[-1].count
    assert snapshot['metadata']['implementation_hashes']==payload['config']['implementation_hashes']
    assert snapshot['metadata']['min_label_return']==payload['config']['min_label_return']
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
    runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, 15, 5, tzinfo=UTC))
    event = supabase.upserts[-1][1][0]

    active = FakeRegistry(
        {
            "occurred_at": event["occurred_at"],
            "payload": event["payload"],
        }
    ).latest(now=datetime(2026, 9, 29, 17, tzinfo=UTC))

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
    runner.run(["ETH/USDT"], now=datetime(2026, 9, 29, 15, 5, tzinfo=UTC))
    event = supabase.upserts[-1][1][0]
    assert event["event_type"] == "model.candidate"

    candidate = FakeRegistry(
        {
            "occurred_at": event["occurred_at"],
            "payload": event["payload"],
        }
    ).latest_candidate(now=datetime(2026, 9, 29, 17, tzinfo=UTC))

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


def test_promotion_excludes_seen_data_when_label_config_changes():
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

    assert decision['count'] == 0
    assert decision['reason'] == 'insufficient_unseen_examples'


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
        runner.run(['ETH/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    assert supabase.upserts == []


def test_promotion_excludes_validation_and_previous_evaluation():
    from cryptoforge.model_training import promotion_decision, FEATURE_VERSION
    from cryptoforge.model_registry import ActiveModel
    model, rows = promotion_fixture()
    artifact = model.as_artifact(pairs=['ETH/USDT'], trained_at=rows[0].open_time,
                                config={'fit_information_end': rows[20].open_time.isoformat(),
                                        'evaluation_information_end': rows[40].open_time.isoformat()})
    incumbent = ActiveModel('run','previous',FEATURE_VERSION,'','',rows[0].open_time,artifact)
    result = promotion_decision(model,incumbent,rows,round_trip_cost=0.003,
                                candidate_information_end=rows[60].open_time)
    assert result['count'] == 179
    assert result['reason'] == 'insufficient_unseen_examples'


def test_promotion_rejects_invalid_boundaries():
    from cryptoforge.model_training import promotion_decision
    model, rows = promotion_fixture()
    result = promotion_decision(model,None,rows,round_trip_cost=0.003,
                                candidate_information_end=datetime(2026,10,1))
    assert result['reason'] == 'invalid_information_boundary'


def test_promotion_does_not_compare_legacy_or_different_feature_windows():
    from cryptoforge.model_training import promotion_decision, FEATURE_VERSION
    from cryptoforge.model_registry import ActiveModel
    model,rows=promotion_fixture()
    contract={'timeframe':'5m','input_candle_state':'closed_only',
              'feature_calculation_contract':'bounded-window-candle-v1','feature_lookback_candles':120}
    artifact=model.as_artifact(pairs=['ETH/USDT'],trained_at=rows[0].open_time-timedelta(days=1),config={})
    incumbent=ActiveModel('run','previous',FEATURE_VERSION,'','',rows[0].open_time-timedelta(days=1),artifact)
    for config in ({},{**contract,'feature_lookback_candles':36},{**contract,'timeframe':'15m'}):
        artifact['config']=config
        result=promotion_decision(model,incumbent,rows,round_trip_cost=.003,candidate_feature_contract=contract)
        assert result['reason']=='incompatible_feature_calculation_contract' and not result['promoted']
        assert result['candidate']['signals']==120 and result['count']==240
        assert result['comparison_blocked_reason']=='incompatible_feature_calculation_contract'
    artifact['config']=contract
    assert promotion_decision(model,incumbent,rows,round_trip_cost=.003,candidate_feature_contract=contract)['reason']=='does_not_beat_incumbent'


def test_empty_purged_splits_cannot_select_regularization():
    import pytest
    examples=build_examples('ETH/USDT',make_training_candles(160),horizon_candles=3)
    train,validation,test=chronological_splits(examples)
    with pytest.raises(ValueError,match='nonempty'):
        train_logistic_model(train,[],test,learning_rate=.05,epochs=1,trained_at=examples[-1].open_time)
    assert chronological_splits(list(reversed(examples)))==(train,validation,test)


def test_rejected_candidate_test_period_is_not_fresh_promotion_evidence():
    from cryptoforge.model_training import promotion_decision
    model,rows=promotion_fixture()
    assert promotion_decision(model,None,rows,round_trip_cost=.003)['promoted']
    result=promotion_decision(model,None,rows,round_trip_cost=.003,previous_evaluation_end=rows[40].open_time)
    assert result['count']==199 and result['reason']=='insufficient_unseen_examples'
    result=promotion_decision(model,None,rows,round_trip_cost=.003,previous_evaluation_end=rows[-1].open_time)
    assert result['count']==0 and not result['promoted']


def test_candidate_evaluation_history_survives_a_narrower_later_dataset(tmp_path):
    from types import SimpleNamespace
    previous_end=datetime(2026,9,30,23,59,tzinfo=UTC)
    previous=SimpleNamespace(model_version='rejected',occurred_at=previous_end,
        artifact={'config':{'evaluation_information_end':datetime(2026,9,30,tzinfo=UTC).isoformat(),
                            'evaluation_history_end':previous_end.isoformat()}})
    class Registry:
        def latest(self,**kwargs):return None
        def latest_candidate(self,**kwargs):return previous
    from dataclasses import replace
    shift=datetime(2026,9,30,8,50,tzinfo=UTC)-datetime(2026,9,29,tzinfo=UTC)
    fresh=[replace(row,open_time=row.open_time+shift) for row in make_training_candles()]
    runner=ModelTrainingRunner(reader=FakeReader(fresh),supabase=FakeSupabase(),
        artifact_dir=tmp_path,epochs=1,registry=Registry())
    runner.run(['ETH/USDT'],now=datetime(2026,10,1,tzinfo=UTC))
    payload=json.loads(next(tmp_path.glob('*.json')).read_text())
    assert payload['config']['evaluation_history_end']==previous_end.isoformat()
    assert payload['promotion']['count']==0
    assert payload['promotion']['reason']=='insufficient_unseen_examples'


def test_invalid_costs_and_duplicate_outcomes_cannot_pass_promotion():
    from cryptoforge.model_training import promotion_decision
    from dataclasses import replace
    model,rows=promotion_fixture()
    for cost in (float('nan'),float('inf'),-.001,1.):
        assert promotion_decision(model,None,rows,round_trip_cost=cost)['reason']=='invalid_promotion_parameters'
    assert promotion_decision(model,None,rows+rows,round_trip_cost=.003)['reason']=='invalid_evaluation_examples'
    altered=[replace(rows[0],future_return=float('inf'))]+rows[1:]
    assert promotion_decision(model,None,altered,round_trip_cost=.003)['reason']=='invalid_evaluation_examples'
    assert not promotion_decision(model,None,rows,round_trip_cost=.003,min_signals=0)['promoted']


def test_runner_records_all_information_boundaries(tmp_path):
    supabase = FakeSupabase()
    runner = ModelTrainingRunner(reader=FakeReader(make_training_candles()),supabase=supabase,
                                 artifact_dir=tmp_path,epochs=1,
                                 registry=type('Registry',(),{'latest':lambda self,**kwargs:None})())
    runner.run(['ETH/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    artifact = json.loads(next(tmp_path.glob('*.json')).read_text())
    config = artifact['config']
    assert config['training_label_end'] < config['fit_information_end'] < config['evaluation_information_end']


def test_probability_predictor_rejects_silent_feature_truncation_and_invalid_numbers():
    import pytest
    from cryptoforge.model_training import predict_probability
    assert predict_probability((0.,),[0.],0.,[0.],[1.])==.5
    for features,weights,bias,means,stds in [
        ((0.,1.),[0.],0.,[0.],[1.]),((float('nan'),),[0.],0.,[0.],[1.]),
        ((0.,),[float('inf')],0.,[0.],[1.]),((0.,),[0.],float('nan'),[0.],[1.]),
        ((0.,),[0.],0.,[0.],[0.]),((1e308,),[1e308],0.,[0.],[1.])]:
        with pytest.raises(ValueError):predict_probability(features,weights,bias,means,stds)


def test_one_gapped_source_is_explicitly_excluded_without_filling_or_fake_pairs(tmp_path):
    from dataclasses import replace
    rows=make_training_candles(180);pairs=['ETH/USDT','BTC/USDT','SOL/USDT','XRP/USDT','BAD/USDT']
    class Reader:
        def read_candles(self,pair,**kwargs):
            data=[replace(row,pair=pair,symbol=pair.replace('/','')) for row in rows]
            return data[:80]+data[81:] if pair=='BAD/USDT' else data
    runner=ModelTrainingRunner(reader=Reader(),supabase=FakeSupabase(),artifact_dir=tmp_path,epochs=2,
        registry=type('Registry',(),{'latest':lambda self,**kwargs:None})())
    runner.run(pairs,now=datetime(2026,9,29,15,5,tzinfo=UTC))
    assert runner.last_source_admission['coverage_fraction']==.8
    assert 'BAD/USDT' in runner.last_source_admission['excluded_pairs']
    artifact=json.loads(next(path for path in tmp_path.glob('pure-python*.json')).read_bytes())
    assert artifact['pairs']==pairs[:-1] and not artifact['config']['source_admission']['gap_filling_allowed']


def test_insufficient_source_coverage_aborts_before_model_or_publication(tmp_path):
    import pytest
    rows=make_training_candles(180)
    class Reader:
        def read_candles(self,pair,**kwargs):return rows if pair=='ETH/USDT' else rows[:80]+rows[81:]
    supabase=FakeSupabase();runner=ModelTrainingRunner(reader=Reader(),supabase=supabase,artifact_dir=tmp_path,epochs=2)
    with pytest.raises(ValueError,match='source coverage'):runner.run(['ETH/USDT','BAD/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    assert not supabase.upserts and (tmp_path/'diagnostics/last-source-admission.json').exists()


def test_bounded_model_features_match_live_window_including_ema_initialization():
    from cryptoforge.model_training import extract_features
    rows=make_training_candles(500)
    examples=build_examples('ETH/USDT',rows,horizon_candles=3,feature_lookback_candles=120)
    indices={row.open_time:i for i,row in enumerate(rows)}
    for example in examples:
        index=indices[example.open_time];window=rows[index-119:index+1]
        assert example.features==extract_features(window,[row.volume for row in window])


def test_nonfinite_derived_pair_is_excluded_before_whole_fit_fails(tmp_path):
    from dataclasses import replace
    pairs=['ETH/USDT','BTC/USDT','SOL/USDT','XRP/USDT','BAD/USDT'];rows=make_training_candles()
    class Reader:
        def read_candles(self,pair,**kwargs):
            return [replace(row,pair=pair,symbol=pair.replace('/',''),
                high=Decimal('1e400') if pair=='BAD/USDT' else row.high) for row in rows]
    runner=ModelTrainingRunner(reader=Reader(),supabase=FakeSupabase(),artifact_dir=tmp_path,epochs=1,
        registry=type('Registry',(),{'latest':lambda self,**kwargs:None})())
    runner.run(pairs,now=datetime(2026,9,29,15,5,tzinfo=UTC))
    assert runner.last_source_admission['coverage_fraction']==.8
    assert 'nonfinite derived' in runner.last_source_admission['excluded_pairs']['BAD/USDT']


def test_empty_ragged_and_nonfinite_standardizer_data_do_not_silently_truncate():
    import pytest
    from cryptoforge.model_training import fit_standardizer
    for rows in ([],[()],[(1.,),(1.,2.)],[(float('nan'),)],[(1e308,),(-1e308,)]):
        with pytest.raises(ValueError):fit_standardizer(rows)


def test_continuous_but_stale_history_cannot_be_admitted_as_a_fresh_fit(tmp_path):
    import pytest
    supabase=FakeSupabase();runner=ModelTrainingRunner(reader=FakeReader(make_training_candles()),
        supabase=supabase,artifact_dir=tmp_path,epochs=1)
    with pytest.raises(ValueError,match='source coverage'):
        runner.run(['ETH/USDT'],now=datetime(2026,10,1,tzinfo=UTC))
    assert runner.last_source_admission['excluded_pairs']['ETH/USDT']=='stale closed training source'
    assert runner.last_source_admission['maximum_source_age_seconds']==900
    assert not supabase.upserts and not list(tmp_path.glob('*.json'))


def test_model_version_includes_normalization_even_when_standardized_fit_is_identical():
    from dataclasses import replace
    from cryptoforge.model_training import TrainingExample
    now=datetime(2026,10,1,tzinfo=UTC)
    rows=[TrainingExample('ETH/USDT',now-timedelta(days=1)+timedelta(minutes=i),
        ((1. if i%2 else -1.),)+(0.,)*6,i%2,1-i%2,.01 if i%2 else -.01) for i in range(28)]
    def fit(values):return train_logistic_model(values[:12],values[12:20],values[20:],
        learning_rate=.05,epochs=3,trained_at=now)
    original=fit(rows);shifted=fit([replace(row,features=(row.features[0]+10,)+row.features[1:]) for row in rows])
    assert original.weights==shifted.weights and original.bias==shifted.bias
    assert original.means!=shifted.means and original.model_version!=shifted.model_version


def test_same_version_with_different_artifact_or_run_is_changed_evidence():
    from types import SimpleNamespace
    from cryptoforge.model_training import model_evidence_identity
    original=SimpleNamespace(model_version='m1',artifact_sha256='a'*64,model_run_id='run1')
    changed=SimpleNamespace(model_version='m1',artifact_sha256='b'*64,model_run_id='run1')
    republished=SimpleNamespace(model_version='m1',artifact_sha256='a'*64,model_run_id='run2')
    assert model_evidence_identity(original)!=model_evidence_identity(changed)
    assert model_evidence_identity(original)!=model_evidence_identity(republished)


def test_primary_artifact_declares_price_target_without_mutating_config():
    import pytest
    model,rows=promotion_fixture();config={'horizon_candles':3}
    artifact=model.as_artifact(pairs=['ETH/USDT'],trained_at=rows[0].open_time,config=config)
    assert artifact['target_version']==artifact['config']['target_version']=='fixed-future-return-v1'
    assert config=={'horizon_candles':3}
    with pytest.raises(ValueError,match='relabel'):
        model.as_artifact(pairs=['ETH/USDT'],trained_at=rows[0].open_time,
                         config={'target_version':'spot-long-trade-net-v2'})
    with pytest.raises(ValueError,match='provenance'):
        model.as_artifact(pairs=['ETH/USDT'],trained_at=rows[0].open_time,
                         config={'source':'observed_real_cash_recovery_memory'})
