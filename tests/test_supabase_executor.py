from datetime import UTC, datetime, timedelta
from decimal import Decimal

from types import SimpleNamespace

from cryptoforge.supabase_executor import CandleRow, SupabaseLiveExecutor, entry_signal, short_shadow_signal


def support_bounce_candles() -> list[CandleRow]:
    start = datetime(2026, 9, 28, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("100")
    for index in range(62):
        open_price = price
        direction = Decimal("-0.04") if index % 3 else Decimal("0.03")
        close = price + direction
        high = max(open_price, close) + Decimal("0.15")
        low = min(open_price, close) - Decimal("0.15")
        volume = Decimal("100")
        if index == 60:
            open_price = Decimal("96.20")
            close = Decimal("95.90")
            high = Decimal("96.30")
            low = Decimal("95.70")
            volume = Decimal("100")
        if index == 61:
            open_price = Decimal("96.00")
            close = Decimal("97.60")
            high = Decimal("97.80")
            low = Decimal("95.50")
            volume = Decimal("95")
        candles.append(
            CandleRow(
                pair="HYPE/USDT",
                symbol="HYPEUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        price = close
    return candles


def test_intraday_reversion_requires_explicit_research_mode() -> None:
    candles = support_bounce_candles()

    default_signal, default_reasons = entry_signal(candles)
    research_signal, research_reasons = entry_signal(candles, allow_intraday_reversion=True)

    assert not default_signal
    assert research_signal
    assert "intraday_reversion=False" in default_reasons
    assert "intraday_reversion=True" in research_reasons


class FakeRegistry:
    def __init__(self, probability: float | None = None, short_probability: float | None = None) -> None:
        self.probability = probability
        self.short_probability = short_probability

    def latest(self, **kwargs):
        if self.probability is None:
            return None
        return SimpleNamespace(
            feature_version="candle-v1",
            model_version="test-model",
            predict_probability=lambda features: self.probability,
            predict_short_probability=lambda features: self.short_probability,
        )


def make_ml_executor(mode: str, probability: float | None) -> SupabaseLiveExecutor:
    return SupabaseLiveExecutor(
        reader=SimpleNamespace(),
        supabase=SimpleNamespace(),
        bybit=SimpleNamespace(),
        active_model_registry=FakeRegistry(probability),  # type: ignore[arg-type]
        ml_mode=mode,
        ml_threshold=0.55,
    )


def test_ml_shadow_records_low_probability_without_blocking() -> None:
    allowed, reasons = make_ml_executor("shadow", 0.40)._ml_entry_allows(support_bounce_candles())

    assert allowed
    assert "ml_probability=0.400000" in reasons
    assert "ml_short_probability=unavailable" in reasons
    assert "ml_shadow=observed" in reasons


def test_ml_gate_blocks_low_probability_and_missing_model() -> None:
    blocked, reasons = make_ml_executor("gate", 0.40)._ml_entry_allows(support_bounce_candles())
    fallback, fallback_reasons = make_ml_executor("gate", None)._ml_entry_allows(support_bounce_candles())

    assert not blocked
    assert "ml_gate=reject" in reasons
    assert not fallback
    assert fallback_reasons == ["ml_fallback=no_fresh_model"]


def short_breakdown_candles() -> list[CandleRow]:
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("105")
    for index in range(70):
        open_price = price
        drift = Decimal("-0.10")
        close = price + drift
        low = min(open_price, close) - Decimal("0.10")
        volume = Decimal("100")
        if index == 69:
            close = price - Decimal("1.30")
            low = close - Decimal("0.20")
            volume = Decimal("160")
        candles.append(
            CandleRow(
                pair="TEST/USDT",
                symbol="TESTUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=max(open_price, close) + Decimal("0.10"),
                low=low,
                close=close,
                volume=volume,
            )
        )
        price = close
    return candles


def test_short_shadow_signal_tracks_breakdowns_without_live_entry() -> None:
    signal, reasons = short_shadow_signal(short_breakdown_candles())

    assert signal
    assert "short_shadow_signal=True" in reasons
    assert "short_support_breakdown=True" in reasons


def test_short_ml_shadow_records_probability() -> None:
    executor = SupabaseLiveExecutor(
        reader=SimpleNamespace(),
        supabase=SimpleNamespace(),
        bybit=SimpleNamespace(),
        active_model_registry=FakeRegistry(0.20, short_probability=0.72),  # type: ignore[arg-type]
        ml_mode="shadow",
    )

    reasons = executor._ml_shadow_research_reasons(short_breakdown_candles())

    assert "short_ml_shadow=observed" in reasons
    assert "ml_short_probability=0.720000" in reasons


def short_emerging_momentum_candles() -> list[CandleRow]:
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("100")
    for index in range(70):
        open_price = price
        drift = Decimal("0.02") if index % 4 == 0 else Decimal("-0.01")
        if index >= 58:
            drift = Decimal("-0.12")
        close = price + drift
        volume = Decimal("100")
        if index == 69:
            volume = Decimal("115")
        candles.append(
            CandleRow(
                pair="TEST/USDT",
                symbol="TESTUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=max(open_price, close) + Decimal("0.05"),
                low=min(open_price, close) - Decimal("0.05"),
                close=close,
                volume=volume,
            )
        )
        price = close
    return candles


def test_short_shadow_signal_tracks_early_downside_momentum() -> None:
    signal, reasons = short_shadow_signal(short_emerging_momentum_candles())

    assert signal
    assert "short_shadow_signal=True" in reasons
    assert "short_emerging_momentum=True" in reasons


def emerging_momentum_candles() -> list[CandleRow]:
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("100")
    for index in range(70):
        open_price = price
        drift = Decimal("-0.08") if index % 3 == 0 else Decimal("0.05")
        if index >= 58:
            drift = Decimal("-0.35") if index % 4 == 0 else Decimal("0.35")
        close = price + drift
        volume = Decimal("100")
        if index >= 64:
            volume = Decimal("180")
        candles.append(
            CandleRow(
                pair="OG/USDT",
                symbol="OGUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=close + Decimal("0.25"),
                low=open_price - Decimal("0.15"),
                close=close,
                volume=volume,
            )
        )
        price = close
    return candles


def early_emerging_momentum_candles() -> list[CandleRow]:
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("100")
    for index in range(70):
        open_price = price
        drift = Decimal("-0.01") if index % 3 == 0 else Decimal("0.02")
        if index >= 58:
            drift = Decimal("0.075")
        close = price + drift
        volume = Decimal("100")
        if index == 69:
            volume = Decimal("96")
        candles.append(
            CandleRow(
                pair="INIT/USDT",
                symbol="INITUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=close + Decimal("0.08"),
                low=open_price - Decimal("0.05"),
                close=close,
                volume=volume,
            )
        )
        price = close
    return candles


def test_emerging_momentum_requires_explicit_research_mode() -> None:
    candles = emerging_momentum_candles()

    default_signal, default_reasons = entry_signal(candles)
    research_signal, research_reasons = entry_signal(candles, allow_emerging_momentum=True)

    assert research_signal
    assert default_signal in {False, True}
    assert "emerging_momentum=False" in default_reasons
    assert "emerging_momentum=True" in research_reasons


def test_early_emerging_momentum_can_enter_before_large_volume_spike() -> None:
    signal, reasons = entry_signal(early_emerging_momentum_candles(), allow_emerging_momentum=True)

    assert signal
    assert "emerging_momentum=True" in reasons


def test_ml_gate_cannot_pass_nan_or_out_of_range_probability():
    for value in (float('nan'),float('inf'),-.1,1.1):
        allowed,reasons=make_ml_executor('gate',value)._ml_entry_allows(support_bounce_candles())
        assert not allowed and 'ml_fallback=prediction_error:ValueError' in reasons


def test_bounded_live_features_match_training_window_and_short_shadow_contract():
    from cryptoforge.model_training import extract_features
    rows=support_bounce_candles();executor=make_ml_executor('gate',.9)
    executor._feature_snapshot_time=rows[-1].open_time+timedelta(minutes=5)
    config={'feature_lookback_candles':36,'input_candle_state':'closed_only'}
    features,state,_=executor._model_input_features(rows,config)
    assert features==extract_features(rows[-36:],[row.volume for row in rows[-36:]])
    assert state=='closed_only'
    assert executor._resolved_model_input_contract['lookback_candles']==36
    assert executor._resolved_model_input_contract['calculation_contract']=='bounded-window-candle-v1'


def test_market_reader_scopes_prices_to_bybit_spot_and_keeps_observation_time():
    from cryptoforge.supabase_executor import SupabaseMarketReader
    from urllib.parse import parse_qs,urlsplit
    class Reader(SupabaseMarketReader):
        def _get(self,path):self.path=path;return []
    reader=Reader(SimpleNamespace());assert reader.read_candles('ETH/USDT')==[]
    query=parse_qs(reader.path.split('?',1)[1])
    assert query['exchange']==['eq.bybit'] and query['market_type']==['eq.spot']
    assert 'ingested_at' in query['select'][0]


def test_rejected_entry_keeps_exact_probability_and_immutable_first_snapshot():
    executor=make_ml_executor('gate',.23456789);rows=support_bounce_candles();records=[]
    executor.supabase=SimpleNamespace(upsert=lambda table,values,**kwargs:records.append((values[0],kwargs)))
    executor._feature_snapshot_pair=rows[-1].pair
    executor._feature_snapshot_time=rows[-1].open_time+timedelta(minutes=1)
    allowed,reasons=executor._ml_entry_allows(rows)
    assert not allowed
    executor._record(rows[-1].pair,'reject_entry',reasons,rows,live=True)
    record,options=records[-1];features=record['features']
    assert features['long_model_probability']==.23456789 and features['long_model_version']=='test-model'
    assert features['model_feature_values']==executor._last_model_input['values']
    assert features['opportunity_only'] and ':snapshot-v1:' in record['idempotency_key']
    assert options['resolution']=='ignore-duplicates' and not record['features']['order']
    executor._feature_snapshot_time+=timedelta(seconds=10)
    executor._record(rows[-1].pair,'reject_entry',reasons,rows,live=True)
    assert records[-1][0]['idempotency_key']==record['idempotency_key']


def test_candidate_forecast_recording_error_does_not_change_buy_gate():
    class Recorder:
        def record(self,forecast):raise OSError('diagnostic storage unavailable')
    executor=make_ml_executor('gate',.9);executor.forecast_recorder=Recorder()
    model=executor.active_model_registry.latest();model.artifact_sha256='a'*64
    executor.active_model_registry=SimpleNamespace(latest=lambda **kwargs:model)
    rows=support_bounce_candles()
    reasons=executor._ml_shadow_research_reasons(rows,baseline_entry_signal=True)
    assert 'primary_forecast_memory_error=OSError' in reasons
    assert executor._last_candidate_forecast['long_probability']==.9
    assert not executor._last_candidate_forecast['counts_as_real_executed_buys']
    assert executor._ml_entry_allows(rows)[0]
