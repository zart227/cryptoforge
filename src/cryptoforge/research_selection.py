from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from urllib import parse, request

from cryptoforge.supabase_market import SupabaseRestClient


ALLOWED_RECOMMENDATIONS = {"watch_for_intraday_levels", "volatile_but_wait_for_volume"}


@dataclass(frozen=True)
class ResearchPairSelection:
    pairs: tuple[str, ...]
    source: str
    generated_at: datetime | None
    reasons: tuple[str, ...]


class NightResearchSelector:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def select_pairs(
        self,
        *,
        fallback_pairs: list[str],
        max_age: timedelta = timedelta(hours=30),
        limit: int = 4,
        now: datetime | None = None,
    ) -> ResearchPairSelection:
        now = now or datetime.now(UTC)
        report = self._latest_report()
        if report is None:
            return ResearchPairSelection(tuple(fallback_pairs), "fallback", None, ("no night research report",))

        generated_at = parse_dt(str(report.get("generated_at") or ""))
        if generated_at is None:
            return ResearchPairSelection(tuple(fallback_pairs), "fallback", None, ("night report missing generated_at",))
        if now - generated_at > max_age:
            return ResearchPairSelection(
                tuple(fallback_pairs),
                "fallback",
                generated_at,
                (f"night report is stale: {generated_at.isoformat()}",),
            )

        selected: list[str] = []
        reasons: list[str] = []
        for result in report.get("results", []):
            if not isinstance(result, dict):
                continue
            pair = str(result.get("pair") or "")
            recommendation = str(result.get("recommendation") or "")
            if pair and recommendation in ALLOWED_RECOMMENDATIONS and pair not in selected:
                selected.append(pair)
                reasons.append(f"{pair}:{recommendation}:score={result.get('score')}")
            if len(selected) >= limit:
                break

        if not selected:
            return ResearchPairSelection(
                tuple(fallback_pairs),
                "fallback",
                generated_at,
                ("night report has no tradeable candidates",),
            )
        return ResearchPairSelection(tuple(selected), "night_research", generated_at, tuple(reasons))

    def _latest_report(self) -> dict[str, Any] | None:
        query = parse.urlencode(
            {
                "event_type": "eq.research.nightly_summary",
                "select": "payload",
                "order": "occurred_at.desc",
                "limit": "1",
            }
        )
        url = f"{self.client.supabase_url.rstrip('/')}/rest/v1/system_events?{query}"
        headers = {
            "apikey": self.client.service_role_key,
            "authorization": f"Bearer {self.client.service_role_key}",
            "accept": "application/json",
        }
        req = request.Request(url, headers=headers, method="GET")
        with request.urlopen(req, timeout=self.client.timeout_seconds) as response:
            rows = json.loads(response.read())
        if not rows:
            return None
        return dict(rows[0].get("payload") or {})


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
