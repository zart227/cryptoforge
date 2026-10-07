from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any
from urllib import parse, request

from cryptoforge.research_selection import parse_dt
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.supabase_market import SupabaseRestClient


@dataclass(frozen=True)
class ShortShadowCandidate:
    decided_at: datetime
    pair: str
    reference_price: Decimal
    reasons: tuple[str, ...]

    @property
    def signal(self) -> bool:
        return reason_value_bool(self.reasons, "short_shadow_signal")

    @property
    def probability(self) -> float | None:
        value = reason_value(self.reasons, "ml_short_probability")
        if value is None or value == "unavailable":
            return None
        try:
            return float(value)
        except ValueError:
            return None


@dataclass(frozen=True)
class ShortShadowOutcome:
    pair: str
    decided_at: datetime
    entry_price: Decimal
    short_probability: float | None
    short_signal: bool
    return_3: float | None
    return_6: float | None
    return_12: float | None
    max_favorable: float | None
    max_adverse: float | None

    def as_payload(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "decided_at": self.decided_at.isoformat(),
            "entry_price": str(self.entry_price),
            "short_probability": self.short_probability,
            "short_signal": self.short_signal,
            "return_3": self.return_3,
            "return_6": self.return_6,
            "return_12": self.return_12,
            "max_favorable": self.max_favorable,
            "max_adverse": self.max_adverse,
        }


def reason_value(reasons: tuple[str, ...], key: str) -> str | None:
    prefix = f"{key}="
    for reason in reasons:
        if reason.startswith(prefix):
            return reason[len(prefix) :]
    return None


def reason_value_bool(reasons: tuple[str, ...], key: str) -> bool:
    return reason_value(reasons, key) == "True"


def short_return(entry: Decimal, exit_price: Decimal) -> float:
    if entry <= 0:
        raise ValueError("entry must be positive")
    return float((entry - exit_price) / entry)


def evaluate_short_outcome(
    candidate: ShortShadowCandidate,
    future_candles: list[CandleRow],
    *,
    horizons: tuple[int, ...] = (3, 6, 12),
) -> ShortShadowOutcome:
    if not future_candles:
        raise ValueError("future_candles is required")
    entry = candidate.reference_price
    returns: dict[int, float | None] = {}
    for horizon in horizons:
        returns[horizon] = (
            short_return(entry, future_candles[horizon - 1].close)
            if len(future_candles) >= horizon
            else None
        )
    observed = future_candles[: max(horizons)]
    max_favorable = max((short_return(entry, candle.low) for candle in observed), default=None)
    max_adverse = min((short_return(entry, candle.high) for candle in observed), default=None)
    return ShortShadowOutcome(
        pair=candidate.pair,
        decided_at=candidate.decided_at,
        entry_price=entry,
        short_probability=candidate.probability,
        short_signal=candidate.signal,
        return_3=returns.get(3),
        return_6=returns.get(6),
        return_12=returns.get(12),
        max_favorable=max_favorable,
        max_adverse=max_adverse,
    )


def summarize_outcomes(outcomes: list[ShortShadowOutcome]) -> dict[str, Any]:
    complete_12 = [outcome for outcome in outcomes if outcome.return_12 is not None]
    signaled = [outcome for outcome in complete_12 if outcome.short_signal]
    high_probability = [
        outcome
        for outcome in complete_12
        if outcome.short_probability is not None and outcome.short_probability >= 0.5
    ]
    return {
        "count": len(outcomes),
        "complete_12": len(complete_12),
        "signaled": aggregate_outcomes(signaled),
        "probability_ge_0_5": aggregate_outcomes(high_probability),
        "all": aggregate_outcomes(complete_12),
        "top_probability": [
            outcome.as_payload()
            for outcome in sorted(
                (item for item in complete_12 if item.short_probability is not None),
                key=lambda item: item.short_probability or 0,
                reverse=True,
            )[:10]
        ],
    }


def aggregate_outcomes(outcomes: list[ShortShadowOutcome]) -> dict[str, Any]:
    returns = [outcome.return_12 for outcome in outcomes if outcome.return_12 is not None]
    if not returns:
        return {"count": len(outcomes), "win_rate": 0.0, "mean_return_12": 0.0}
    return {
        "count": len(returns),
        "win_rate": sum(value > 0 for value in returns) / len(returns),
        "mean_return_12": sum(returns) / len(returns),
        "mean_max_favorable": mean([outcome.max_favorable for outcome in outcomes]),
        "mean_max_adverse": mean([outcome.max_adverse for outcome in outcomes]),
    }


def mean(values: list[float | None]) -> float:
    present = [value for value in values if value is not None]
    return sum(present) / max(len(present), 1)


class ShortShadowOutcomeRunner:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def run(
        self,
        *,
        lookback_hours: int = 24,
        limit: int = 500,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        since = now - timedelta(hours=lookback_hours)
        candidates = self.fetch_candidates(since=since, limit=limit)
        outcomes: list[ShortShadowOutcome] = []
        pending = 0
        for candidate in candidates:
            candles = self.fetch_future_candles(candidate, limit=12)
            if len(candles) < 12:
                pending += 1
                continue
            outcomes.append(evaluate_short_outcome(candidate, candles))
        summary = summarize_outcomes(outcomes)
        summary.update(
            {
                "generated_at": now.isoformat(),
                "lookback_hours": lookback_hours,
                "pending": pending,
                "candidate_count": len(candidates),
                "outcomes": [outcome.as_payload() for outcome in outcomes[-100:]],
            }
        )
        self.publish_summary(summary, generated_at=now)
        return summary

    def fetch_candidates(self, *, since: datetime, limit: int) -> list[ShortShadowCandidate]:
        query = parse.urlencode(
            {
                "select": "decided_at,pair,reference_price,reasons",
                "decided_at": f"gte.{since.isoformat()}",
                "order": "decided_at.desc",
                "limit": str(limit),
            }
        )
        rows = self._get(f"trade_decisions?{query}")
        candidates: list[ShortShadowCandidate] = []
        for row in rows:
            decided_at = parse_dt(str(row.get("decided_at") or ""))
            pair = str(row.get("pair") or "")
            reference_price = Decimal(str(row.get("reference_price") or "0"))
            reasons = tuple(str(item) for item in row.get("reasons") or ())
            if (
                decided_at is not None
                and pair
                and reference_price > 0
                and "short_ml_shadow=observed" in reasons
            ):
                candidates.append(ShortShadowCandidate(decided_at, pair, reference_price, reasons))
        return sorted(candidates, key=lambda candidate: candidate.decided_at)

    def fetch_future_candles(self, candidate: ShortShadowCandidate, *, limit: int) -> list[CandleRow]:
        symbol = candidate.pair.replace("/", "")
        query = parse.urlencode(
            {
                "pair": f"eq.{candidate.pair}",
                "timeframe": "eq.5m",
                "open_time": f"gt.{candidate.decided_at.isoformat()}",
                "select": "pair,symbol,open_time,open,high,low,close,volume",
                "order": "open_time.asc",
                "limit": str(limit),
            }
        )
        rows = self._get(f"market_candles?{query}")
        return [
            CandleRow(
                pair=str(row.get("pair") or candidate.pair),
                symbol=str(row.get("symbol") or symbol),
                open_time=parse_dt(str(row.get("open_time") or "")) or candidate.decided_at,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
            )
            for row in rows
        ]

    def publish_summary(self, summary: dict[str, Any], *, generated_at: datetime) -> None:
        event_key = hashlib.sha256(
            json.dumps(
                {
                    "generated_at": generated_at.replace(minute=0, second=0, microsecond=0).isoformat(),
                    "lookback_hours": summary.get("lookback_hours"),
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.client.upsert(
            "system_events",
            [
                {
                    "occurred_at": generated_at.isoformat(),
                    "source": "cryptoforge.short_shadow",
                    "severity": "info",
                    "event_type": "research.short_shadow_outcomes",
                    "idempotency_key": f"short-shadow-outcomes:{event_key}",
                    "payload": summary,
                }
            ],
            on_conflict="idempotency_key",
        )

    def _get(self, path: str) -> list[dict[str, Any]]:
        url = f"{self.client.supabase_url.rstrip('/')}/rest/v1/{path}"
        headers = {
            "apikey": self.client.service_role_key,
            "authorization": f"Bearer {self.client.service_role_key}",
            "accept": "application/json",
        }
        req = request.Request(url, headers=headers, method="GET")
        with request.urlopen(req, timeout=self.client.timeout_seconds) as response:
            return list(json.loads(response.read()))
