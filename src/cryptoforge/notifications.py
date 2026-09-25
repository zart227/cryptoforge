from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol
from urllib import error, parse, request


Clock = Callable[[], float]
HttpPost = Callable[[str, bytes, dict[str, str], float], None]

SECRET_MARKERS = (
    "api_key",
    "api_secret",
    "authorization",
    "bot_token",
    "bybit",
    "chat_id",
    "secret",
    "service_role",
    "supabase",
    "telegram",
    "token",
)
SUPABASE_SECRET_PREFIX = "sb_" + "secret_"
SUPABASE_PUBLISHABLE_PREFIX = "sb_" + "publishable_"


class NotificationKind(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    DAILY_SUMMARY = "daily_summary"
    CRITICAL_ERROR = "critical_error"
    SUPABASE_OFFLINE = "supabase_offline"
    QUEUE_GROWING = "queue_growing"
    DISK_WARNING = "disk_warning"
    RISK_LIMIT_REACHED = "risk_limit_reached"


class NotificationSink(Protocol):
    def send(self, message: str) -> None:
        """Send a single already-rendered notification."""


@dataclass(frozen=True)
class Notification:
    kind: NotificationKind
    title: str
    body: str
    fields: dict[str, object] | None = None

    def render(self) -> str:
        lines = [self.title.strip(), self.body.strip()]
        if self.fields:
            for key, value in sorted(self.fields.items()):
                safe_value = redact_value(key, value)
                lines.append(f"{key}: {safe_value}")
        return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class NotificationResult:
    sent: bool
    reason: str


class NullNotificationSink:
    def send(self, message: str) -> None:
        return None


class TelegramNotificationSink:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 10.0,
        http_post: HttpPost | None = None,
    ) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")
        if not chat_id:
            raise ValueError("chat_id is required")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.http_post = http_post or post_json

    def send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        self.http_post(
            url,
            json.dumps(payload).encode("utf-8"),
            {"Content-Type": "application/json"},
            self.timeout_seconds,
        )


class RateLimitedNotifier:
    def __init__(
        self,
        sink: NotificationSink | None = None,
        *,
        clock: Clock = time.time,
        min_interval_seconds: float = 60.0,
        per_kind_interval_seconds: dict[NotificationKind, float] | None = None,
    ) -> None:
        self.sink = sink or NullNotificationSink()
        self.clock = clock
        self.min_interval_seconds = min_interval_seconds
        self.per_kind_interval_seconds = per_kind_interval_seconds or {
            NotificationKind.CRITICAL_ERROR: 10.0,
            NotificationKind.STOP_LOSS: 10.0,
            NotificationKind.RISK_LIMIT_REACHED: 10.0,
            NotificationKind.DAILY_SUMMARY: 0.0,
        }
        self._last_sent_at_by_kind: dict[NotificationKind, float] = {}

    def notify(self, notification: Notification) -> NotificationResult:
        now = self.clock()
        last_sent_at = self._last_sent_at_by_kind.get(notification.kind)
        interval = self.per_kind_interval_seconds.get(
            notification.kind,
            self.min_interval_seconds,
        )
        if last_sent_at is not None and now - last_sent_at < interval:
            return NotificationResult(False, "rate_limited")

        message = notification.render()
        if contains_unredacted_secret(message):
            return NotificationResult(False, "message_contains_secret_marker")

        try:
            self.sink.send(message)
        except Exception as exc:  # noqa: BLE001 - notifications must not break runtime.
            return NotificationResult(False, f"sink_failed: {exc}")

        self._last_sent_at_by_kind[notification.kind] = now
        return NotificationResult(True, "sent")


def telegram_notifier_from_env(
    environ: dict[str, str] | None = None,
    *,
    clock: Clock = time.time,
) -> RateLimitedNotifier:
    env = os.environ if environ is None else environ
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return RateLimitedNotifier(NullNotificationSink(), clock=clock)
    return RateLimitedNotifier(
        TelegramNotificationSink(bot_token=token, chat_id=chat_id),
        clock=clock,
    )


def redact_value(key: str, value: object) -> str:
    lowered = key.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return "[redacted]"
    text = str(value)
    if looks_like_secret(text):
        return "[redacted]"
    return text


def contains_unredacted_secret(message: str) -> bool:
    for line in message.splitlines():
        lowered = line.lower()
        if "[redacted]" in lowered:
            continue
        for marker in SECRET_MARKERS:
            if f"{marker}=" in lowered or f"{marker}:" in lowered:
                return True
    return False


def looks_like_secret(text: str) -> bool:
    if text.startswith((SUPABASE_SECRET_PREFIX, SUPABASE_PUBLISHABLE_PREFIX)):
        return True
    if len(text) >= 24 and any(char.isdigit() for char in text) and any(char.isalpha() for char in text):
        compact = text.replace("-", "").replace("_", "")
        return compact.isalnum()
    return False


def post_json(url: str, payload: bytes, headers: dict[str, str], timeout_seconds: float) -> None:
    req = request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            if response.status not in {200, 201, 204}:
                raise RuntimeError(f"Telegram returned unexpected status {response.status}")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {exc.code}: {body[:300]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Telegram request failed: {exc}") from exc


def telegram_api_url_without_secret(url: str) -> str:
    parsed = parse.urlparse(url)
    path = parsed.path
    if path.startswith("/bot"):
        path = "/bot[redacted]/sendMessage"
    return parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
