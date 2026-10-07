from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from statistics import median
from typing import Any

from cryptoforge.supabase_executor import CandleRow, SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseRestClient


@dataclass(frozen=True)
class PairResearch:
    pair: str
    candle_count: int
    close: Decimal
    support: Decimal
    resistance: Decimal
    range_pct: Decimal
    median_candle_range_pct: Decimal
    direction_changes: int
    direction_change_ratio: Decimal
    volume_ratio: Decimal
    rsi: Decimal
    score: Decimal
    recommendation: str
    reasons: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "candle_count": self.candle_count,
            "close": decimal_text(self.close),
            "support": decimal_text(self.support),
            "resistance": decimal_text(self.resistance),
            "range_pct": decimal_text(self.range_pct),
            "median_candle_range_pct": decimal_text(self.median_candle_range_pct),
            "direction_changes": self.direction_changes,
            "direction_change_ratio": decimal_text(self.direction_change_ratio),
            "volume_ratio": decimal_text(self.volume_ratio),
            "rsi": decimal_text(self.rsi),
            "score": decimal_text(self.score),
            "recommendation": self.recommendation,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class NightResearchReport:
    generated_at: datetime
    timeframe: str
    lookback_candles: int
    results: tuple[PairResearch, ...]
    strategy_experiments: tuple[dict[str, Any], ...] = ()

    def as_event_payload(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "timeframe": self.timeframe,
            "lookback_candles": self.lookback_candles,
            "results": [result.as_payload() for result in self.results],
            "strategy_experiments": list(self.strategy_experiments),
            "top_pairs": [result.pair for result in self.results[:5]],
        }


class NightResearchRunner:
    def __init__(
        self,
        *,
        reader: SupabaseMarketReader,
        supabase: SupabaseRestClient,
        min_candles: int = 80,
    ) -> None:
        self.reader = reader
        self.supabase = supabase
        self.min_candles = min_candles

    def run(
        self,
        pairs: list[str],
        *,
        timeframe: str = "5m",
        lookback_candles: int = 240,
        now: datetime | None = None,
    ) -> NightResearchReport:
        generated_at = now or datetime.now(UTC)
        results: list[PairResearch] = []
        failures: dict[str, str] = {}
        experiments: list[dict[str, Any]] = []
        from cryptoforge.strategy_search import search_strategies
        for pair in pairs:
            try:
                candles = self.reader.read_candles(pair, timeframe=timeframe, limit=lookback_candles)
                results.append(analyze_pair(pair, candles, min_candles=self.min_candles))
                experiments.append({"pair": pair, **search_strategies(candles)})
            except Exception as exc:  # noqa: BLE001 - research should keep scanning other pairs.
                failures[pair] = str(exc)

        report = NightResearchReport(
            generated_at=generated_at,
            timeframe=timeframe,
            lookback_candles=lookback_candles,
            results=tuple(sorted(results, key=lambda result: result.score, reverse=True)),
            strategy_experiments=tuple(experiments),
        )
        self._write_report(report, pairs=pairs, failures=failures)
        return report

    def _write_report(
        self,
        report: NightResearchReport,
        *,
        pairs: list[str],
        failures: dict[str, str],
    ) -> None:
        payload = report.as_event_payload()
        payload["requested_pairs"] = pairs
        payload["failures"] = failures
        event_key = hashlib.sha256(
            json.dumps(
                {
                    "date": report.generated_at.date().isoformat(),
                    "timeframe": report.timeframe,
                    "pairs": sorted(pairs),
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.supabase.upsert(
            "system_events",
            [
                {
                    "occurred_at": report.generated_at.isoformat(),
                    "source": "cryptoforge.night_research",
                    "severity": "info" if report.results else "warning",
                    "event_type": "research.nightly_summary",
                    "idempotency_key": f"night-research:{event_key}",
                    "payload": payload,
                }
            ],
            on_conflict="idempotency_key",
        )


def analyze_pair(pair: str, candles: list[CandleRow], *, min_candles: int = 80) -> PairResearch:
    if len(candles) < min_candles:
        raise ValueError(f"not enough candles: {len(candles)} < {min_candles}")

    recent = candles[-min(len(candles), 144) :]
    close = recent[-1].close
    highs = [candle.high for candle in recent]
    lows = [candle.low for candle in recent]
    closes = [candle.close for candle in recent]
    volumes = [candle.volume for candle in recent]

    support = min(lows[-48:])
    resistance = max(highs[-48:])
    range_pct = pct((max(highs) - min(lows)) / close)
    candle_ranges = [pct((candle.high - candle.low) / candle.close) for candle in recent if candle.close > 0]
    median_candle_range_pct = Decimal(str(median(candle_ranges))) if candle_ranges else Decimal("0")
    direction_changes = count_direction_changes(closes)
    direction_change_ratio = Decimal(direction_changes) / Decimal(max(len(closes) - 2, 1))
    volume_mean = sum(volumes[-40:]) / Decimal(min(40, len(volumes)))
    volume_ratio = volumes[-1] / volume_mean if volume_mean > 0 else Decimal("0")
    rsi_value = rsi(closes, 14)

    score = (
        range_pct * Decimal("0.38")
        + median_candle_range_pct * Decimal("0.34")
        + pct(direction_change_ratio) * Decimal("0.20")
        + min(volume_ratio, Decimal("3")) * Decimal("0.08")
    )
    recommendation, reasons = classify_candidate(
        range_pct=range_pct,
        median_candle_range_pct=median_candle_range_pct,
        direction_change_ratio=direction_change_ratio,
        volume_ratio=volume_ratio,
        rsi_value=rsi_value,
    )
    return PairResearch(
        pair=pair,
        candle_count=len(candles),
        close=close,
        support=support,
        resistance=resistance,
        range_pct=range_pct,
        median_candle_range_pct=median_candle_range_pct,
        direction_changes=direction_changes,
        direction_change_ratio=direction_change_ratio,
        volume_ratio=volume_ratio,
        rsi=rsi_value,
        score=score,
        recommendation=recommendation,
        reasons=tuple(reasons),
    )


def classify_candidate(
    *,
    range_pct: Decimal,
    median_candle_range_pct: Decimal,
    direction_change_ratio: Decimal,
    volume_ratio: Decimal,
    rsi_value: Decimal,
) -> tuple[str, list[str]]:
    reasons = [
        f"range_pct={range_pct:.3f}",
        f"median_candle_range_pct={median_candle_range_pct:.3f}",
        f"direction_change_ratio={direction_change_ratio:.3f}",
        f"volume_ratio={volume_ratio:.3f}",
        f"rsi={rsi_value:.2f}",
    ]
    oscillates = direction_change_ratio >= Decimal("0.26")
    has_movement = range_pct >= Decimal("2.5") and median_candle_range_pct >= Decimal("0.18")
    liquid_now = volume_ratio >= Decimal("0.45")
    if oscillates and has_movement and liquid_now:
        return "watch_for_intraday_levels", reasons
    if has_movement:
        return "volatile_but_wait_for_volume", reasons
    return "low_priority", reasons


def count_direction_changes(values: list[Decimal]) -> int:
    signs: list[int] = []
    for left, right in zip(values, values[1:]):
        delta = right - left
        if delta > 0:
            signs.append(1)
        elif delta < 0:
            signs.append(-1)
    return sum(1 for left, right in zip(signs, signs[1:]) if left != right)


def rsi(values: list[Decimal], period: int) -> Decimal:
    if len(values) <= period:
        return Decimal("50")
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for left, right in zip(values[-period - 1 : -1], values[-period:]):
        delta = right - left
        gains.append(max(delta, Decimal("0")))
        losses.append(max(-delta, Decimal("0")))
    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)
    if avg_loss == 0:
        return Decimal("100")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def pct(value: Decimal) -> Decimal:
    return value * Decimal("100")


def decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")
