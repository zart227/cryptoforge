from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import error, parse, request


JsonObject = dict[str, Any]
Clock = Callable[[], float]


class DeliveryError(RuntimeError):
    """Raised when a remote event delivery attempt failed."""


class EventSink(Protocol):
    def deliver(self, event: "OutboxEvent") -> None:
        """Persist an outbox event remotely or raise DeliveryError."""


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    source: str
    payload: JsonObject
    severity: str = "info"
    occurred_at: datetime | None = None
    idempotency_key: str | None = None

    def normalized(self) -> "EventEnvelope":
        occurred_at = self.occurred_at or datetime.now(UTC)
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)

        return EventEnvelope(
            event_type=self.event_type,
            source=self.source,
            payload=self.payload,
            severity=self.severity,
            occurred_at=occurred_at,
            idempotency_key=self.idempotency_key or str(uuid.uuid4()),
        )


@dataclass(frozen=True)
class OutboxEvent:
    id: str
    event_type: str
    source: str
    severity: str
    occurred_at: str
    idempotency_key: str
    payload: JsonObject
    attempts: int
    next_attempt_at: float

    def system_event_record(self) -> JsonObject:
        return {
            "occurred_at": self.occurred_at,
            "source": self.source,
            "severity": self.severity,
            "event_type": self.event_type,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class OutboxStats:
    pending_count: int
    delivered_count: int
    dead_count: int
    oldest_pending_age_seconds: float | None

    @property
    def has_pending(self) -> bool:
        return self.pending_count > 0


@dataclass(frozen=True)
class DeliveryResult:
    delivered: int
    failed: int


class SQLiteOutbox:
    def __init__(
        self,
        db_path: str | Path,
        *,
        clock: Clock = time.time,
        max_attempts: int = 12,
        base_backoff_seconds: float = 5.0,
        max_backoff_seconds: float = 900.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.clock = clock
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def enqueue(self, envelope: EventEnvelope) -> OutboxEvent:
        normalized = envelope.normalized()
        event_id = str(uuid.uuid4())
        now = self.clock()
        occurred_at = normalized.occurred_at
        assert occurred_at is not None
        idempotency_key = normalized.idempotency_key
        assert idempotency_key is not None

        with self._connect() as conn:
            conn.execute(
                """
                insert into outbox_events (
                    id,
                    event_type,
                    source,
                    severity,
                    occurred_at,
                    idempotency_key,
                    payload_json,
                    status,
                    attempts,
                    created_at,
                    updated_at,
                    next_attempt_at
                ) values (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                """,
                (
                    event_id,
                    normalized.event_type,
                    normalized.source,
                    normalized.severity,
                    occurred_at.isoformat(),
                    idempotency_key,
                    json.dumps(normalized.payload, sort_keys=True),
                    now,
                    now,
                    now,
                ),
            )

        return self.get(event_id)

    def get(self, event_id: str) -> OutboxEvent:
        with self._connect() as conn:
            row = conn.execute(
                """
                select
                    id,
                    event_type,
                    source,
                    severity,
                    occurred_at,
                    idempotency_key,
                    payload_json,
                    attempts,
                    next_attempt_at
                from outbox_events
                where id = ?
                """,
                (event_id,),
            ).fetchone()

        if row is None:
            raise KeyError(event_id)

        return self._row_to_event(row)

    def due_events(self, *, limit: int = 100) -> list[OutboxEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select
                    id,
                    event_type,
                    source,
                    severity,
                    occurred_at,
                    idempotency_key,
                    payload_json,
                    attempts,
                    next_attempt_at
                from outbox_events
                where status = 'pending'
                  and next_attempt_at <= ?
                order by created_at asc
                limit ?
                """,
                (self.clock(), limit),
            ).fetchall()

        return [self._row_to_event(row) for row in rows]

    def flush_due(self, sink: EventSink, *, limit: int = 100) -> DeliveryResult:
        delivered = 0
        failed = 0

        for event in self.due_events(limit=limit):
            try:
                sink.deliver(event)
            except Exception as exc:  # noqa: BLE001 - all sink failures retry.
                self.mark_failed(event.id, str(exc))
                failed += 1
            else:
                self.mark_delivered(event.id)
                delivered += 1

        return DeliveryResult(delivered=delivered, failed=failed)

    def mark_delivered(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                update outbox_events
                set status = 'delivered',
                    delivered_at = ?,
                    updated_at = ?
                where id = ?
                """,
                (self.clock(), self.clock(), event_id),
            )

    def mark_failed(self, event_id: str, error_message: str) -> None:
        now = self.clock()
        with self._connect() as conn:
            row = conn.execute(
                """
                select attempts
                from outbox_events
                where id = ?
                """,
                (event_id,),
            ).fetchone()

            if row is None:
                raise KeyError(event_id)

            attempts = int(row["attempts"]) + 1
            status = "dead" if attempts >= self.max_attempts else "pending"
            backoff = min(
                self.max_backoff_seconds,
                self.base_backoff_seconds * (2 ** max(attempts - 1, 0)),
            )

            conn.execute(
                """
                update outbox_events
                set status = ?,
                    attempts = ?,
                    last_error = ?,
                    next_attempt_at = ?,
                    updated_at = ?
                where id = ?
                """,
                (status, attempts, error_message, now + backoff, now, event_id),
            )

    def stats(self) -> OutboxStats:
        now = self.clock()
        with self._connect() as conn:
            counts = {
                row["status"]: int(row["count"])
                for row in conn.execute(
                    """
                    select status, count(*) as count
                    from outbox_events
                    group by status
                    """
                )
            }
            oldest = conn.execute(
                """
                select min(created_at) as oldest
                from outbox_events
                where status = 'pending'
                """
            ).fetchone()["oldest"]

        oldest_age = None if oldest is None else max(0.0, now - float(oldest))
        return OutboxStats(
            pending_count=counts.get("pending", 0),
            delivered_count=counts.get("delivered", 0),
            dead_count=counts.get("dead", 0),
            oldest_pending_age_seconds=oldest_age,
        )

    def fail_safe_exceeded(self, *, max_oldest_pending_age_seconds: float) -> bool:
        stats = self.stats()
        if stats.oldest_pending_age_seconds is None:
            return False
        return stats.oldest_pending_age_seconds >= max_oldest_pending_age_seconds

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("pragma journal_mode = wal")
            conn.execute(
                """
                create table if not exists outbox_events (
                    id text primary key,
                    event_type text not null,
                    source text not null,
                    severity text not null,
                    occurred_at text not null,
                    idempotency_key text not null unique,
                    payload_json text not null,
                    status text not null check (
                        status in ('pending', 'delivered', 'dead')
                    ),
                    attempts integer not null default 0,
                    last_error text,
                    created_at real not null,
                    updated_at real not null,
                    next_attempt_at real not null,
                    delivered_at real
                )
                """
            )
            conn.execute(
                """
                create index if not exists outbox_pending_due_idx
                on outbox_events (status, next_attempt_at, created_at)
                """
            )
            conn.execute(
                """
                create index if not exists outbox_idempotency_key_idx
                on outbox_events (idempotency_key)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> OutboxEvent:
        return OutboxEvent(
            id=row["id"],
            event_type=row["event_type"],
            source=row["source"],
            severity=row["severity"],
            occurred_at=row["occurred_at"],
            idempotency_key=row["idempotency_key"],
            payload=json.loads(row["payload_json"]),
            attempts=int(row["attempts"]),
            next_attempt_at=float(row["next_attempt_at"]),
        )


class SupabaseSystemEventsSink:
    def __init__(
        self,
        *,
        supabase_url: str,
        service_key: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not supabase_url:
            raise ValueError("supabase_url is required")
        if not service_key:
            raise ValueError("service_key is required")

        self.supabase_url = supabase_url.rstrip("/")
        self.service_key = service_key
        self.timeout_seconds = timeout_seconds

    def deliver(self, event: OutboxEvent) -> None:
        url = (
            f"{self.supabase_url}/rest/v1/system_events?"
            f"{parse.urlencode({'on_conflict': 'idempotency_key'})}"
        )
        payload = json.dumps(event.system_event_record()).encode("utf-8")
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        req = request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status not in {200, 201, 204}:
                    raise DeliveryError(
                        f"Supabase returned unexpected status {response.status}"
                    )
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DeliveryError(
                f"Supabase HTTP {exc.code}: {body[:500]}"
            ) from exc
        except error.URLError as exc:
            raise DeliveryError(f"Supabase request failed: {exc}") from exc
