from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptoforge.supabase_executor import CandleRow, entry_signal


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
