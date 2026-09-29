from datetime import UTC, datetime, timedelta
from decimal import Decimal

from types import SimpleNamespace

from cryptoforge.supabase_executor import CandleRow, SupabaseLiveExecutor, entry_signal


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
    def __init__(self, probability: float | None = None) -> None:
        self.probability = probability

    def latest(self, **kwargs):
        if self.probability is None:
            return None
        return SimpleNamespace(
            feature_version="candle-v1",
            model_version="test-model",
            predict_probability=lambda features: self.probability,
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
    assert "ml_shadow=observed" in reasons


def test_ml_gate_blocks_low_probability_but_missing_model_falls_back() -> None:
    blocked, reasons = make_ml_executor("gate", 0.40)._ml_entry_allows(support_bounce_candles())
    fallback, fallback_reasons = make_ml_executor("gate", None)._ml_entry_allows(support_bounce_candles())

    assert not blocked
    assert "ml_gate=reject" in reasons
    assert fallback
    assert fallback_reasons == ["ml_fallback=no_fresh_model"]


def emerging_momentum_candles() -> list[CandleRow]:
    start = datetime(2026, 9, 29, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("100")
    for index in range(70):
        open_price = price
        drift = Decimal("-0.08") if index % 3 == 0 else Decimal("0.05")
        if index >= 58:
            drift = Decimal("0.35")
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


def test_emerging_momentum_requires_explicit_research_mode() -> None:
    candles = emerging_momentum_candles()

    default_signal, default_reasons = entry_signal(candles)
    research_signal, research_reasons = entry_signal(candles, allow_emerging_momentum=True)

    assert research_signal
    assert default_signal in {False, True}
    assert "emerging_momentum=False" in default_reasons
    assert "emerging_momentum=True" in research_reasons
