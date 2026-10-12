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

## Local Relay

If Telegram is unavailable from the VPS, keep Telegram disabled in the
VPS trading runtime and run the relay on a machine that can reach
`api.telegram.org`.

The VPS should continue delivering operational events to Supabase
`system_events`. The local relay reads new `trade.opened`,
`trade.closed` and `performance.daily_summary` events from Supabase and
sends compact Telegram messages with order status, realized PnL and
daily benefit metrics.

Required local environment:

```text
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
CRYPTOFORGE_TELEGRAM_RELAY_STATE=./data/telegram-relay-state.json
```

Run once:

```bash
cryptoforge-telegram-relay
```

Run continuously:

```bash
cryptoforge-telegram-relay --watch --interval-seconds 60
```

The relay stores its cursor locally and keeps the most recent delivered
event ids to avoid duplicates across restarts.

## Freqtrade Position Monitor

For actual Freqtrade paper/live positions, run the local trade monitor against
the Freqtrade SQLite database. It sends one Telegram message when a position is
first seen open and one message when it is closed, including realized PnL and
PnL percent.

Paper database:

```bash
cryptoforge-trade-monitor \
  --db-path data/live-pilot/tradesv3.paper.sqlite \
  --state-path data/freqtrade-trade-monitor-state.json \
  --watch \
  --interval-seconds 30
```

VPS dry-run database example:

```bash
cryptoforge-trade-monitor \
  --db-path /opt/cryptoforge/data/tradesv3.dry_run.sqlite \
  --state-path /opt/cryptoforge/data/freqtrade-trade-monitor-state.json \
  --watch \
  --interval-seconds 30
```

The monitor uses the same `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and optional
`TELEGRAM_PROXY_URL` environment values as the relay. Its state file prevents
duplicate alerts across restarts.

### Live trade notices

Trade decisions are retained in Supabase for `/status` and `/risk`, but are
not fetched or sent as push notifications. The live journal publishes
actual executed purchases and sales as `trade.opened` / `trade.closed`
events. New fills from the same order within one reconciliation are grouped
in one message, including all FIFO allocations for that sale. Later partial
executions can produce another message with their additional executed amount.
Closing messages show net profit/loss in USDT, net return in percent and
total allocated acquisition plus sale fees in USDT. Unknown costs or fees
are explicitly marked unavailable. Trade notices have no per-kind cooldown.
The first reconciliation after enabling notices seeds existing executions
without sending historical messages. Execution-based event keys prevent
reconciliation retries from generating duplicate events.

Night research summaries remain stored for analysis but are not sent to Telegram.

Partial market-sync `warning` events are no longer pushed to Telegram,
including the watcher's `feeder:warning` alert. They remain visible through
`/status`. Error/critical health events and stale/missing data alerts remain
active, including failures that pause new entries in the live journal.

Daily results are sent by the relay at or after 00:05 Europe/Moscow for the
previous Moscow calendar day. The report includes live closed-sale count,
profitable/loss-making/breakeven outcomes, net realized PnL, allocated fees,
and the current Bybit account equity and USDT wallet balance. FIFO segments
from the same sale order count once; a partial sale counts as a realized
closure. Account equity includes unrealized valuation and is not daily PnL.
A healthy journal reconciliation after the period end is required. Pending
reports retry on later polls; successful dates persist separately in
`telegram-daily-summary-state.json`. Enabling starts with the current day;
previous history is not pushed. Missed days are delivered one per poll,
with the balance explicitly dated to the time of sending.
