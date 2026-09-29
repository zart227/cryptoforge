from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any
from urllib import parse, request

from cryptoforge.model_training import predict_probability
from cryptoforge.research_selection import parse_dt
from cryptoforge.supabase_market import SupabaseRestClient


@dataclass(frozen=True)
class ActiveModel:
    model_run_id: str
    model_version: str
    feature_version: str
    artifact_sha256: str
    artifact_uri: str
    occurred_at: datetime
    artifact: dict[str, Any]

    def predict_probability(self, features: tuple[float, ...]) -> float:
        return predict_probability(
            features,
            list(self.artifact["weights"]),
            float(self.artifact["bias"]),
            list(self.artifact["means"]),
            list(self.artifact["stds"]),
        )


class ActiveModelRegistry:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def latest(
        self,
        *,
        max_age: timedelta = timedelta(hours=36),
        now: datetime | None = None,
    ) -> ActiveModel | None:
        now = now or datetime.now(UTC)
        row = self._latest_event()
        if row is None:
            return None
        occurred_at = parse_dt(str(row.get("occurred_at") or ""))
        if occurred_at is None or now - occurred_at > max_age:
            return None
        payload = dict(row.get("payload") or {})
        artifact = dict(payload.get("artifact") or {})
        artifact_sha256 = str(payload.get("artifact_sha256") or "")
        if not artifact or not artifact_sha256:
            return None
        raw = json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != artifact_sha256:
            raise ValueError("active model artifact checksum mismatch")
        return ActiveModel(
            model_run_id=str(payload.get("model_run_id") or ""),
            model_version=str(payload.get("model_version") or artifact.get("model_version") or ""),
            feature_version=str(payload.get("feature_version") or artifact.get("feature_version") or ""),
            artifact_sha256=artifact_sha256,
            artifact_uri=str(payload.get("artifact_uri") or ""),
            occurred_at=occurred_at,
            artifact=artifact,
        )

    def _latest_event(self) -> dict[str, Any] | None:
        query = parse.urlencode(
            {
                "event_type": "eq.model.active",
                "select": "occurred_at,payload",
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
        return dict(rows[0])
