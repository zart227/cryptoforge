from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any
from urllib import parse, request

from cryptoforge.model_training import predict_probability,FEATURE_VERSION,FEATURE_NAMES,MODEL_FAMILY
from cryptoforge.research_selection import parse_dt
from cryptoforge.supabase_market import SupabaseRestClient
from cryptoforge.target_contracts import require_artifact_target


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

    def predict_short_probability(self, features: tuple[float, ...]) -> float | None:
        short_weights = self.artifact.get("short_weights")
        if short_weights is None or "short_bias" not in self.artifact:
            return None
        return predict_probability(
            features,
            list(short_weights),
            float(self.artifact["short_bias"]),
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
        return self._latest_by_event_type("model.active", max_age=max_age, now=now)

    def latest_candidate(
        self,
        *,
        max_age: timedelta = timedelta(hours=36),
        now: datetime | None = None,
    ) -> ActiveModel | None:
        return self._latest_by_event_type("model.candidate", max_age=max_age, now=now)

    def _latest_by_event_type(
        self,
        event_type: str,
        *,
        max_age: timedelta,
        now: datetime | None,
    ) -> ActiveModel | None:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:raise ValueError('aware model evaluation time required')
        row = self._latest_event(event_type=event_type)
        if row is None:
            return None
        occurred_at = parse_dt(str(row.get("occurred_at") or ""))
        if occurred_at is None or occurred_at > now or now - occurred_at > max_age:
            return None
        payload = dict(row.get("payload") or {})
        artifact = dict(payload.get("artifact") or {})
        artifact_sha256 = str(payload.get("artifact_sha256") or "")
        if not artifact or not artifact_sha256:
            return None
        raw = json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != artifact_sha256:
            raise ValueError("active model artifact checksum mismatch")
        for field in ('model_version','feature_version'):
            if payload.get(field) and artifact.get(field) and payload[field]!=artifact[field]:
                raise ValueError('model event metadata differs from embedded artifact')
        def artifact_time(value):
            try:stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            except ValueError as exc:raise ValueError('model information timestamp required') from exc
            if stamp.tzinfo is None:raise ValueError('aware model information timestamp required')
            return stamp.astimezone(UTC)
        trained_at=artifact_time(artifact.get('trained_at'))
        if trained_at>occurred_at or trained_at>now:raise ValueError('model training time is in the future')
        if now-trained_at>max_age:return None
        config=artifact.get('config') or {}
        if config.get('fit_information_end') and artifact_time(config['fit_information_end'])>trained_at:
            raise ValueError('model uses information unavailable at training')
        if config.get('evaluation_information_end') and artifact_time(config['evaluation_information_end'])>occurred_at:
            raise ValueError('model evaluation uses information unavailable at publication')
        if config.get('evaluation_information_end') and now-artifact_time(config['evaluation_information_end'])>max_age:
            return None
        if config.get('evaluation_history_end') and artifact_time(config['evaluation_history_end'])>occurred_at:
            raise ValueError('model evaluation history uses information unavailable at publication')
        if artifact.get('model_family')!=MODEL_FAMILY:raise ValueError('unsupported probability model family')
        target=require_artifact_target(artifact,expected_target='fixed-future-return-v1',allow_legacy_price=True)
        if 'target_version' in payload and payload['target_version']!=target['version']:
            raise ValueError('model event target metadata differs from artifact target')
        if event_type=='model.active' and artifact.get('live_eligible') is False:
            raise ValueError('research-only artifact cannot be an active model')
        effective_version=str(payload.get('feature_version') or artifact.get('feature_version') or '')
        if effective_version==FEATURE_VERSION and artifact.get('feature_names')!=list(FEATURE_NAMES):
            raise ValueError('model candle-v1 feature ordering mismatch')
        return ActiveModel(
            model_run_id=str(payload.get("model_run_id") or ""),
            model_version=str(payload.get("model_version") or artifact.get("model_version") or ""),
            feature_version=str(payload.get("feature_version") or artifact.get("feature_version") or ""),
            artifact_sha256=artifact_sha256,
            artifact_uri=str(payload.get("artifact_uri") or ""),
            occurred_at=occurred_at,
            artifact=artifact,
        )

    def _latest_event(self, *, event_type: str = "model.active") -> dict[str, Any] | None:
        query = parse.urlencode(
            {
                "event_type": f"eq.{event_type}",
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
