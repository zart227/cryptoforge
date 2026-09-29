from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptoforge.night_research import analyze_pair, count_direction_changes
from cryptoforge.night_research_cli import file_pairs
from cryptoforge.supabase_executor import CandleRow


def make_candles(count: int = 96) -> list[CandleRow]:
    start = datetime(2026, 9, 27, tzinfo=UTC)
    candles: list[CandleRow] = []
    price = Decimal("100")
    for index in range(count):
        direction = Decimal("1") if index % 2 == 0 else Decimal("-1")
        open_price = price
        close = price + direction * Decimal("1.80")
        high = max(open_price, close) + Decimal("0.45")
        low = min(open_price, close) - Decimal("0.45")
        candles.append(
            CandleRow(
                pair="ETH/USDT",
                symbol="ETHUSDT",
                open_time=start + timedelta(minutes=5 * index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=Decimal("100") + Decimal(index % 10),
            )
        )
        price = close
    return candles


def test_count_direction_changes_ignores_flat_moves() -> None:
    assert count_direction_changes([Decimal("1"), Decimal("2"), Decimal("1"), Decimal("1"), Decimal("3")]) == 2


def test_analyze_pair_scores_intraday_oscillation_candidate() -> None:
    result = analyze_pair("ETH/USDT", make_candles(), min_candles=80)

    assert result.pair == "ETH/USDT"
    assert result.candle_count == 96
    assert result.direction_changes > 80
    assert result.recommendation == "watch_for_intraday_levels"
    assert result.support < result.close < result.resistance
    assert result.score > Decimal("1")


def test_file_pairs_reads_live_universe_output(tmp_path) -> None:
    universe = tmp_path / "live-universe.json"
    universe.write_text('{"pairs": ["AAVE/USDT", "SUI/USDT"]}', encoding="utf-8")

    assert file_pairs(universe) == ["AAVE/USDT", "SUI/USDT"]
