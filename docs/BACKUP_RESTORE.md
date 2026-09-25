# Backup And Restore

CryptoForge backups are compact by default because durable research state
belongs in Supabase and reproducible market data can be downloaded again.

## Included By Default

`cryptoforge-backup create` includes:

- `config/`;
- `user_data/strategies/`;
- `supabase/migrations/`;
- `deploy/`;
- `data/outbox.sqlite3`, when present.

The backup also stores `BACKUP_MANIFEST.json` inside the archive.

## Excluded By Default

The backup excludes:

- `.env`;
- `.git`;
- virtualenvs;
- logs;
- caches;
- downloaded candles and market-history cache;
- hyperopt/backtest result bulk.

Secrets must be restored securely from the operator's password manager or
host secret store. Do not put real exchange, Supabase or Telegram
credentials in a backup archive committed to git.

## Commands

Create:

```text
cryptoforge-backup create --project-root /opt/cryptoforge/app --output-dir /opt/cryptoforge/backups
```

Verify:

```text
cryptoforge-backup verify /opt/cryptoforge/backups/cryptoforge-backup-YYYYMMDDTHHMMSSZ.tar.gz /opt/cryptoforge/backups/cryptoforge-backup-YYYYMMDDTHHMMSSZ.tar.gz.sha256
```

Restore into a controlled test location:

```text
cryptoforge-backup restore /opt/cryptoforge/backups/cryptoforge-backup-YYYYMMDDTHHMMSSZ.tar.gz --checksum /opt/cryptoforge/backups/cryptoforge-backup-YYYYMMDDTHHMMSSZ.tar.gz.sha256 --restore-dir /tmp/cryptoforge-restore-test
```

Only restore into the live runtime directory during a controlled
maintenance window after verifying the archive in a separate directory.

## Checksum

Every archive receives a sidecar `.sha256` file. Verification recomputes
the archive checksum and confirms the manifest exists.

Restore with `--checksum` should be the normal path. A checksum mismatch
means the archive must not be used.

## Safety

Restore rejects unsafe archive paths that would escape the selected
restore directory. Tests cover creation, verification, restore and
path-traversal rejection.
