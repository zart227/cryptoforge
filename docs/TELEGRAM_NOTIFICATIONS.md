# Telegram Notifications

Telegram notifications are optional. If `TELEGRAM_BOT_TOKEN` or
`TELEGRAM_CHAT_ID` is empty, CryptoForge uses a no-op notification sink
and the trading runtime continues normally.

## Environment

Use local `.env` values only:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Never commit real Telegram credentials. The repository only stores empty
placeholders in `.env.example`.

## Supported Events

The notification module defines event kinds for:

- runtime started/stopped;
- trade opened/closed;
- stop-loss and take-profit;
- daily summary;
- critical error;
- Supabase offline;
- queue growing;
- disk warning;
- risk limit reached.

## Rate Limiting

`RateLimitedNotifier` suppresses repeated messages of the same kind. The
default interval is 60 seconds. Critical errors, stop-loss events and
risk-limit alerts use a shorter default interval so important runtime
events can still surface quickly.

Rate limiting is local process state. It prevents noisy loops from
spamming Telegram and from wasting network calls during outages.

## Secret Redaction

Notification fields are rendered through `Notification.render()`.
Sensitive field names such as `api_key`, `api_secret`, `token`,
`service_role`, `supabase`, `telegram`, `chat_id` and `bybit` are
redacted before sending.

If a rendered message still contains an obvious unredacted secret marker,
`RateLimitedNotifier.notify()` refuses to send it.

## Runtime Safety

Notification delivery exceptions are converted into a failed
`NotificationResult`. They do not raise into trading code and cannot stop
position management or hard-risk checks.

The module uses Python standard-library HTTP calls and is tested with
mocks. Tests do not call Telegram unless a future integration test is
explicitly added with credentials.
