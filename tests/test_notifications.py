from dataclasses import dataclass, field

from cryptoforge.notifications import (
    Notification,
    NotificationKind,
    RateLimitedNotifier,
    TelegramNotificationSink,
    contains_unredacted_secret,
    telegram_api_url_without_secret,
    telegram_notifier_from_env,
)


@dataclass
class ManualClock:
    value: float = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass
class RecordingSink:
    messages: list[str] = field(default_factory=list)
    fail: bool = False

    def send(self, message: str) -> None:
        if self.fail:
            raise RuntimeError("telegram outage")
        self.messages.append(message)


def notification(kind: NotificationKind = NotificationKind.STARTED) -> Notification:
    return Notification(
        kind=kind,
        title="CryptoForge",
        body="runtime event",
        fields={"pair": "BTC/USDT"},
    )


def test_missing_telegram_credentials_create_noop_notifier() -> None:
    notifier = telegram_notifier_from_env({}, clock=ManualClock())

    result = notifier.notify(notification())

    assert result.sent
    assert result.reason == "sent"


def test_rate_limit_suppresses_repeated_notifications() -> None:
    clock = ManualClock()
    sink = RecordingSink()
    notifier = RateLimitedNotifier(
        sink,
        clock=clock,
        min_interval_seconds=60,
    )

    first = notifier.notify(notification(NotificationKind.QUEUE_GROWING))
    second = notifier.notify(notification(NotificationKind.QUEUE_GROWING))
    clock.advance(60)
    third = notifier.notify(notification(NotificationKind.QUEUE_GROWING))

    assert first.sent
    assert not second.sent
    assert second.reason == "rate_limited"
    assert third.sent
    assert len(sink.messages) == 2


def test_critical_notifications_have_shorter_rate_limit() -> None:
    clock = ManualClock()
    sink = RecordingSink()
    notifier = RateLimitedNotifier(sink, clock=clock, min_interval_seconds=60)

    notifier.notify(notification(NotificationKind.CRITICAL_ERROR))
    clock.advance(9)
    second = notifier.notify(notification(NotificationKind.CRITICAL_ERROR))
    clock.advance(1)
    third = notifier.notify(notification(NotificationKind.CRITICAL_ERROR))

    assert not second.sent
    assert third.sent
    assert len(sink.messages) == 2


def test_notification_rendering_redacts_secret_fields() -> None:
    message = Notification(
        kind=NotificationKind.CRITICAL_ERROR,
        title="CryptoForge",
        body="critical",
        fields={
            "api_key": "abc123456789012345678901",
            "telegram_bot_token": "123456:secret",
            "pair": "ETH/USDT",
        },
    ).render()

    assert "ETH/USDT" in message
    assert "abc123456789012345678901" not in message
    assert "123456:secret" not in message
    assert "api_key: [redacted]" in message
    assert not contains_unredacted_secret(message)


def test_notification_with_unredacted_secret_marker_is_not_sent() -> None:
    sink = RecordingSink()
    notifier = RateLimitedNotifier(sink, clock=ManualClock())

    result = notifier.notify(
        Notification(
            kind=NotificationKind.CRITICAL_ERROR,
            title="CryptoForge",
            body="api_secret=leaked",
        )
    )

    assert not result.sent
    assert result.reason == "message_contains_secret_marker"
    assert sink.messages == []


def test_sink_failure_does_not_raise_into_runtime() -> None:
    notifier = RateLimitedNotifier(RecordingSink(fail=True), clock=ManualClock())

    result = notifier.notify(notification(NotificationKind.DISK_WARNING))

    assert not result.sent
    assert result.reason.startswith("sink_failed:")


def test_telegram_sink_uses_send_message_endpoint_without_printing_secret() -> None:
    calls: list[tuple[str, bytes, dict[str, str], float]] = []

    def record(url: str, payload: bytes, headers: dict[str, str], timeout: float) -> None:
        calls.append((url, payload, headers, timeout))

    sink = TelegramNotificationSink(
        bot_token="123456:secret-token",
        chat_id="999",
        http_post=record,
    )

    sink.send("hello")

    assert len(calls) == 1
    assert calls[0][0] == "https://api.telegram.org/bot123456:secret-token/sendMessage"
    assert telegram_api_url_without_secret(calls[0][0]) == (
        "https://api.telegram.org/bot[redacted]/sendMessage"
    )
    assert b'"chat_id": "999"' in calls[0][1]
