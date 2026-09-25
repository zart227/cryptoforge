from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from cryptoforge.outbox import EventEnvelope, OutboxEvent, SQLiteOutbox


@dataclass
class ManualClock:
    value: float = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass
class RecordingSink:
    fail_times: int = 0
    delivered: list[OutboxEvent] = field(default_factory=list)

    def deliver(self, event: OutboxEvent) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("simulated outage")
        self.delivered.append(event)


def test_enqueue_creates_persistent_event_envelope(tmp_path) -> None:
    clock = ManualClock()
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3", clock=clock)

    event = outbox.enqueue(
        EventEnvelope(
            event_type="trade.opened",
            source="test",
            severity="info",
            occurred_at=datetime(2026, 9, 25, tzinfo=UTC),
            idempotency_key="trade-opened-1",
            payload={"pair": "BTC/USDT"},
        )
    )

    reopened = SQLiteOutbox(tmp_path / "outbox.sqlite3", clock=clock)
    assert reopened.get(event.id).idempotency_key == "trade-opened-1"
    assert reopened.stats().pending_count == 1
    assert reopened.stats().oldest_pending_age_seconds == 0


def test_flush_acks_only_after_success(tmp_path) -> None:
    clock = ManualClock()
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3", clock=clock)
    outbox.enqueue(
        EventEnvelope(
            event_type="system.test",
            source="test",
            payload={"ok": True},
            idempotency_key="event-1",
        )
    )

    failing_sink = RecordingSink(fail_times=1)
    failed = outbox.flush_due(failing_sink)
    assert failed.delivered == 0
    assert failed.failed == 1
    assert outbox.stats().pending_count == 1

    clock.advance(5)
    succeeding_sink = RecordingSink()
    delivered = outbox.flush_due(succeeding_sink)

    assert delivered.delivered == 1
    assert delivered.failed == 0
    assert outbox.stats().pending_count == 0
    assert outbox.stats().delivered_count == 1
    assert len(succeeding_sink.delivered) == 1


def test_duplicate_idempotency_key_is_rejected_locally(tmp_path) -> None:
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3")
    envelope = EventEnvelope(
        event_type="system.test",
        source="test",
        payload={},
        idempotency_key="same-key",
    )

    outbox.enqueue(envelope)

    with pytest.raises(Exception):
        outbox.enqueue(envelope)


def test_retry_backoff_and_dead_letter(tmp_path) -> None:
    clock = ManualClock()
    outbox = SQLiteOutbox(
        tmp_path / "outbox.sqlite3",
        clock=clock,
        max_attempts=2,
        base_backoff_seconds=10,
    )
    event = outbox.enqueue(
        EventEnvelope(
            event_type="system.test",
            source="test",
            payload={},
            idempotency_key="retry-key",
        )
    )

    outbox.mark_failed(event.id, "first failure")
    assert outbox.due_events() == []

    clock.advance(10)
    assert len(outbox.due_events()) == 1

    outbox.mark_failed(event.id, "second failure")
    stats = outbox.stats()
    assert stats.pending_count == 0
    assert stats.dead_count == 1


def test_fail_safe_exposes_old_pending_age(tmp_path) -> None:
    clock = ManualClock()
    outbox = SQLiteOutbox(tmp_path / "outbox.sqlite3", clock=clock)
    outbox.enqueue(
        EventEnvelope(
            event_type="system.test",
            source="test",
            payload={},
            idempotency_key="age-key",
        )
    )

    clock.advance(3_601)

    assert outbox.stats().oldest_pending_age_seconds == 3_601
    assert outbox.fail_safe_exceeded(max_oldest_pending_age_seconds=3_600)
