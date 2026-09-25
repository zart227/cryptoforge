# Durable Outbox

CryptoForge persists outbound operational events to local SQLite before
attempting remote delivery. This keeps trading safety decisions local:
Supabase can be offline without losing events or blocking open-position
management.

## Event Envelope

Each event has:

- `id`: local UUID primary key.
- `event_type`: stable event name such as `trade.opened`.
- `source`: producing component.
- `severity`: `debug`, `info`, `warning`, `error` or `critical`.
- `occurred_at`: event timestamp.
- `idempotency_key`: unique delivery key used locally and remotely.
- `payload`: compact JSON payload.

The local SQLite table also stores status, attempts, retry timing, last
error and delivery timestamp.

## Delivery

`SQLiteOutbox.flush_due()` reads due pending events and sends them to an
`EventSink`. The current Supabase sink writes to `system_events` through
the REST API with `on_conflict=idempotency_key` and upsert conflict
resolution. A local event is marked delivered only after the sink returns
success.

Failures keep the event pending until `max_attempts` is reached. Retry
delay uses bounded exponential backoff. After too many failures, the
event becomes `dead` and requires operator attention.

## Fail-Safe Signal

`SQLiteOutbox.stats()` exposes queue depth and oldest pending age.
`fail_safe_exceeded()` can be used by later runtime phases to stop new
position openings when persistence has been degraded for too long.

Recommended initial threshold: stop new entries if the oldest pending
event is older than 1 hour. This does not force-close existing positions.
