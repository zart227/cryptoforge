from __future__ import annotations

from dataclasses import dataclass, field

from cryptoforge.notifications import Notification
from cryptoforge.telegram_relay import (
    RelayEvent,
    RelayState,
    StatusSnapshot,
    load_state,
    notification_from_event,
    relay_once,
    save_state,
)


@dataclass
class FakeClient:
    events: list[RelayEvent]
    since_values: list[str] = field(default_factory=list)

    def fetch_events(self, *, since_occurred_at: str, limit: int) -> list[RelayEvent]:
        self.since_values.append(since_occurred_at)
        return self.events[:limit]


@dataclass
class RecordingNotifier:
    notifications: list[Notification] = field(default_factory=list)
    fail: bool = False

    def notify(self, notification: Notification):  # type: ignore[no-untyped-def]
        self.notifications.append(notification)
        sent = not self.fail

        class Result:
            pass

        Result.sent = sent
        return Result()


def event(event_type: str, payload: dict[str, object], event_id: str = "evt-1") -> RelayEvent:
    return RelayEvent(
        id=event_id,
        occurred_at="2026-09-27T10:00:00+00:00",
        event_type=event_type,
        severity="info",
        payload=payload,
    )


def test_trade_opened_event_formats_telegram_notification() -> None:
    notification = notification_from_event(
        event(
            "trade.opened",
            {
                "pair": "BTC/USDT",
                "mode": "dry_run",
                "entry_price": "100",
                "take_profit": "103",
            },
        )
    )

    assert notification is not None
    assert notification.title == "CryptoForge: trade opened"
    assert "BTC/USDT" in notification.render()
    assert "take_profit: 103" in notification.render()


def test_trade_closed_event_includes_realized_pnl() -> None:
    notification = notification_from_event(
        event(
            "trade.closed",
            {
                "pair": "ETH/USDT",
                "exit_reason": "take_profit",
                "realized_pnl": "1.23",
                "realized_pnl_pct": "0.0123",
            },
        )
    )

    assert notification is not None
    rendered = notification.render()
    assert "CryptoForge: trade closed" in rendered
    assert "realized_pnl: 1.23" in rendered
    assert "realized_pnl_pct: 0.0123" in rendered


def test_trade_decision_event_formats_notification() -> None:
    notification = notification_from_event(
        event(
            "trade.decision",
            {
                "pair": "ETH/USDT",
                "mode": "live",
                "decision": "approve_entry",
                "reference_price": "2714.23",
                "reasons": ["pullback=True"],
            },
        )
    )

    assert notification is not None
    rendered = notification.render()
    assert "CryptoForge: trade decision" in rendered
    assert "ETH/USDT" in rendered
    assert "decision: approve_entry" in rendered


def test_health_event_formats_notification() -> None:
    notification = notification_from_event(
        event(
            "system.health",
            {
                "component": "supabase_market_sync",
                "status": "error",
                "message": "sync failed",
            },
        )
    )

    assert notification is not None
    rendered = notification.render()
    assert "CryptoForge: health alert" in rendered
    assert "supabase_market_sync" in rendered
    assert "sync failed" in rendered


def test_relay_once_sends_events_and_persists_cursor(tmp_path) -> None:
    client = FakeClient(
        [
            event("trade.opened", {"pair": "BTC/USDT"}, event_id="evt-1"),
            event("trade.closed", {"pair": "BTC/USDT", "realized_pnl": "2"}, event_id="evt-2"),
        ]
    )
    notifier = RecordingNotifier()

    result = relay_once(
        client=client,
        notifier=notifier,
        state_path=tmp_path / "relay-state.json",
    )

    assert result.scanned == 2
    assert result.sent == 2
    assert len(notifier.notifications) == 2
    assert client.since_values == ["1970-01-01T00:00:00+00:00"]

    second = relay_once(
        client=FakeClient([]),
        notifier=notifier,
        state_path=tmp_path / "relay-state.json",
    )

    assert second.scanned == 0
    assert second.last_occurred_at == "2026-09-27T10:00:00+00:00"


def test_relay_does_not_advance_cursor_past_failed_notification(tmp_path) -> None:
    client = FakeClient(
        [
            event("trade.opened", {"pair": "BTC/USDT"}, event_id="evt-1"),
        ]
    )
    notifier = RecordingNotifier(fail=True)

    result = relay_once(
        client=client,
        notifier=notifier,
        state_path=tmp_path / "relay-state.json",
    )

    assert result.failed == 1
    assert result.last_occurred_at == "1970-01-01T00:00:00+00:00"


def test_relay_state_persists_command_offset_and_alerts(tmp_path) -> None:
    path = tmp_path / "relay-state.json"
    save_state(
        path,
        RelayState(
            last_occurred_at="2026-09-27T10:00:00+00:00",
            telegram_update_offset=123,
            active_alert_keys=("executor:stale",),
        ),
    )

    state = load_state(path)

    assert state.telegram_update_offset == 123
    assert state.active_alert_keys == ("executor:stale",)


def test_status_snapshot_renders_alerts_for_stale_executor() -> None:
    snapshot = StatusSnapshot(
        generated_at=__import__("datetime").datetime(2026, 9, 27, 10, 10, tzinfo=__import__("datetime").UTC),
        last_decision_at=__import__("datetime").datetime(2026, 9, 27, 10, 0, tzinfo=__import__("datetime").UTC),
        last_decision={"mode": "live", "decision": "hold", "pair": "ETH/USDT", "reasons": []},
        market_sync={"status": "ok", "message": "synced", "observed_at": "2026-09-27T10:09:00+00:00"},
        latest_candle_ingested_at=__import__("datetime").datetime(2026, 9, 27, 10, 9, tzinfo=__import__("datetime").UTC),
        latest_candle_open_time=__import__("datetime").datetime(2026, 9, 27, 10, 5, tzinfo=__import__("datetime").UTC),
    )

    assert "executor:stale" in snapshot.alert_keys()
    assert "CryptoForge status" in snapshot.render()
