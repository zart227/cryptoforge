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


class ReportClient:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.paths = []

    def _get_rows(self, path):
        self.paths.append(path)
        return self.rows.get(path.split('?')[0], [])


def test_menu_commands_respond_with_empty_sources(monkeypatch):
    from cryptoforge import telegram_relay as relay
    from cryptoforge.bybit_private import BybitPrivateClient

    class Exchange:
        def get_unified_wallet_coins(self):
            return [{'coin': 'ETH', 'walletBalance': '0.1', 'usdValue': '200'}]

        def get_open_orders(self, *, symbol):
            assert symbol == ''
            return [{'symbol': 'ETHUSDT', 'side': 'Buy', 'qty': '1'}]

        def get_order_history(self, *, limit):
            return [{'symbol': 'ETHUSDT', 'side': 'Sell', 'orderStatus': 'Filled', 'cumExecQty': '1', 'avgPrice': '2000'}]

    monkeypatch.setattr(BybitPrivateClient, 'from_env', lambda: Exchange())
    client = ReportClient()
    for command in ['/open', '/closed', '/pnl', '/summary', '/risk', '/help']:
        assert relay.render_command(client, command)
    assert 'ETHUSDT' in relay.render_command(client, '/open')
    assert 'без расчёта PnL' in relay.render_command(client, '/closed')
    assert 'не означает нулевую' in relay.render_command(client, '/pnl')
    assert 'closed_at=gte.' in client.paths[-3] or any('closed_at=gte.' in p for p in client.paths)


def test_pnl_keeps_live_and_dry_run_separate():
    from cryptoforge.telegram_relay import render_command
    client = ReportClient({'trades': [
        {'mode': 'live', 'realized_pnl': '1.2', 'fee_amount': '0.1'},
        {'mode': 'dry_run', 'realized_pnl': '900', 'fee_amount': None},
    ]})
    reply = render_command(client, '/pnl')
    assert 'live: сделок=1, PnL=1.20000000, комиссии=0.10000000' in reply
    assert 'dry_run: сделок=1, PnL=900.00000000' in reply
    assert 'неполных записей=1' in reply


def test_command_backend_failure_does_not_stop_help(monkeypatch, tmp_path):
    from cryptoforge import telegram_relay as relay
    replies = []
    monkeypatch.setattr(relay, 'telegram_get_json', lambda *a, **kw: {'ok': True, 'result': [
        {'update_id': 1, 'message': {'chat': {'id': 42}, 'text': '/status@Bot'}},
        {'update_id': 2, 'message': {'chat': {'id': 42}, 'text': '/help'}},
        {'update_id': 3, 'message': {'chat': {'id': 99}, 'text': '/help'}},
    ]})
    monkeypatch.setattr(relay.TelegramNotificationSink, 'send', lambda self, text: replies.append(text))
    monkeypatch.setattr(relay, 'fetch_status', lambda c: (_ for _ in ()).throw(RuntimeError('secret-token')))
    path = tmp_path / 'state.json'
    assert relay.process_telegram_commands(client=ReportClient(), state_path=path, bot_token='token', chat_id='42', timeout_seconds=1) == 2
    assert 'Не удалось' in replies[0]
    assert 'secret-token' not in replies[0]
    assert '/risk' in replies[1]
    assert relay.load_state(path).telegram_update_offset == 4


def test_command_send_failure_keeps_update_pending(monkeypatch, tmp_path):
    from cryptoforge import telegram_relay as relay
    monkeypatch.setattr(relay, 'telegram_get_json', lambda *a, **kw: {'ok': True, 'result': [
        {'update_id': 10, 'message': {'chat': {'id': 42}, 'text': '/help'}},
    ]})
    monkeypatch.setattr(relay.TelegramNotificationSink, 'send', lambda *a: (_ for _ in ()).throw(RuntimeError('offline')))
    path = tmp_path / 'state.json'
    assert relay.process_telegram_commands(client=ReportClient(), state_path=path, bot_token='token', chat_id='42', timeout_seconds=1) == 0
    assert relay.load_state(path).telegram_update_offset == 10


def test_command_reply_splits_long_text():
    from cryptoforge.telegram_relay import send_command_reply
    class Sink:
        def __init__(self): self.messages = []
        def send(self, text): self.messages.append(text)
    sink = Sink()
    send_command_reply(sink, 'a' * 9000)
    assert ''.join(sink.messages) == 'a' * 9000
    assert max(map(len, sink.messages)) <= 1800


def test_relay_retains_cursor_event_even_with_many_old_ids(tmp_path):
    path = tmp_path / 'state.json'
    save_state(path, RelayState('2026-09-26T00:00:00+00:00', tuple(f'z-{i}' for i in range(600))))
    client = FakeClient([event('trade.opened', {'pair': 'ETH/USDT'}, event_id='a-current')])
    notifier = RecordingNotifier()
    assert relay_once(client=client, notifier=notifier, state_path=path).sent == 1
    assert load_state(path).delivered_event_ids == ('a-current',)
    assert relay_once(client=client, notifier=notifier, state_path=path).sent == 0
