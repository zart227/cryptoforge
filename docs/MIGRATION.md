# Migration To A Stronger VPS

Migration uses a compact package. It does not copy the entire disk and
does not include reproducible candle caches by default.

## Old VPS

1. Stop research jobs.
2. Gracefully stop the trader.
3. Flush the Supabase outbox.
4. Create a compact migration export.
5. Verify the archive checksum.

Command:

```text
cryptoforge-migration export --project-root /opt/cryptoforge/app --output-dir /opt/cryptoforge/backups
cryptoforge-migration verify /opt/cryptoforge/backups/cryptoforge-migration-YYYYMMDDTHHMMSSZ.tar.gz /opt/cryptoforge/backups/cryptoforge-migration-YYYYMMDDTHHMMSSZ.tar.gz.sha256
```

## New VPS

1. Clone the repository.
2. Restore secrets securely outside git.
3. Install the runtime.
4. Import critical state.
5. Reconnect Supabase.
6. Re-download reproducible market data.
7. Start dry-run.
8. Verify monitoring health.

Command:

```text
cryptoforge-migration import /tmp/cryptoforge-migration-YYYYMMDDTHHMMSSZ.tar.gz --checksum /tmp/cryptoforge-migration-YYYYMMDDTHHMMSSZ.tar.gz.sha256 --restore-dir /opt/cryptoforge/app
```

Import into a temporary directory first during rehearsal. Import into the
live runtime directory only during a controlled migration window.

## Package Contents

Included:

- configs;
- strategies;
- Supabase migrations;
- deploy metadata;
- pending local outbox database, when present.

Excluded:

- `.env`;
- `.git`;
- virtualenvs;
- logs;
- downloaded candles;
- market-history caches;
- hyperopt/backtest bulk artifacts.

## Bybit IP-Whitelisted Keys

For future real trading, prefer Bybit API keys with IP restrictions. When
migrating to a new VPS:

1. Keep live trading disabled.
2. Add the new VPS public IP to the Bybit API key whitelist or create a
   replacement key with the new IP.
3. Store the key and secret only in the new host secret store or local
   `.env`.
4. Verify Bybit connectivity in dry-run/paper mode first.
5. Remove the old VPS IP from the whitelist after cutover.

Do not copy API keys through git, migration archives, logs or chat.

## Verification

After import:

- verify checksum before extraction;
- confirm configs and strategies exist;
- confirm `.env` is restored manually and remains untracked;
- confirm Supabase outbox can flush;
- re-download market data instead of copying old bulk caches;
- start dry-run and check monitoring status.
