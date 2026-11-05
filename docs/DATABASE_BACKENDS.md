# Local PostgreSQL and Supabase switching

CryptoForge supports two explicitly selected durable backends:
`CRYPTOFORGE_BACKEND=local` and `CRYPTOFORGE_BACKEND=supabase`.
The default for installations without this setting remains `supabase`.
Selection applies to market collectors, executor persistence, research,
model registry, live feedback and Telegram database reads. Freqtrade's
database URL helper also follows the selection and keeps `search_path=freqtrade`.
Direct Python PostgreSQL clients require the pinned optional dependency:
`.venv/bin/python -m pip install '.[postgres]'`.

There is no automatic fallback or replication. After either database receives
writes, the other copy becomes stale. Switching a URL does not reconcile
trades, decisions, local outboxes or exchange state. Bybit remains authoritative
for balances and execution. Trading risk gates and runtime approvals still apply.
Changing the backend code invalidates an old source-bound runtime approval;
do not regenerate an approval merely to make a migrated worker start.

## Local deployment

Run commands from the repository root, using an account with Docker access:

```bash
.venv/bin/python scripts/database_backend.py init
.venv/bin/python scripts/database_backend.py start
```

`init` creates separate random database credentials and a signed local API
token in `.local/database/`, with a private directory and mode-600 secret
files. It refuses to silently overwrite existing credentials. These files
and Docker's persistent volume must be preserved across restarts.

The stack in `docker/database.compose.yml` consists of PostgreSQL 17,
PostgREST and an nginx `/rest/v1/` proxy. PostgreSQL is limited to 512 MiB,
PostgREST to 128 MiB, nginx to 32 MiB; these are caps, not reserved memory.
Only loopback host ports are published: PostgreSQL `127.0.0.1:55432` and
HTTP `127.0.0.1:54321`. Anonymous API access is disabled. The local JWT
grants the server-side `service_role` access to public app tables; it cannot
access the private Freqtrade schema. Freqtrade uses its own non-superuser role.
Supabase cloud credentials are never reused for local requests.

The stack starts empty. Restore a backup or a verified migration snapshot
before selecting it. A fresh instance has no market tables, so the switch
probe will reject it. Docker restart policies restart containers after a
Docker daemon restart. Do not run `docker compose down -v`: that removes
the persistent database volume.

## Switch an existing installation

Pause workers that write database state before moving between copies. Finish
or reconcile pending exchange submissions and preserve local order journals,
reservations, risk state and outboxes. Take a source backup, transfer changes
to the target, and verify it before restarting workers against the target.

```bash
.venv/bin/python scripts/database_backend.py switch local
.venv/bin/python scripts/database_backend.py status
# To select Supabase again, AFTER synchronizing newer local state:
.venv/bin/python scripts/database_backend.py switch supabase
```

The switch command first reads a market row from the target. If credentials,
schema or availability checks fail (including Supabase HTTP 402), it leaves
`.env` unchanged. On success it updates `.env` atomically while preserving
the original `SUPABASE_*` values. The original environment is saved privately
as `.local/database/env-before-first-switch` on the first switch.

Restart long-running workers to reload `.env`. Scheduled one-shot jobs reload
their existing environment on their next launch. For the installed Linux
Telegram relay this is `systemctl --user restart cryptoforge-telegram-relay.service`.
The CLI does not start or authorize trading and does not manage worker timers.

`CRYPTOFORGE_LOCAL_API_KEY_FILE` and `CRYPTOFORGE_LOCAL_DB_URL_FILE` can point
to absolute private paths. Optional `CRYPTOFORGE_LOCAL_API_KEY` overrides the
API key file. Local URLs must be loopback addresses. Another computer,
including an existing Windows worker, has its own environment and will not
be redirected by this machine's `.env` change.

For the repository's optional Linux application containers, use the host-network
override so container loopback reaches the host backend, and mount only the API
token into them:

```bash
docker compose -f compose.yaml -f docker/database-clients.compose.yml up -d --build
```

Use this instead of the unmodified app compose file when selecting `local`.
Do not start a second executor if a native systemd executor already owns the
account. This override requires Linux host networking (or explicitly enabled
equivalent support in Docker Desktop).

## Backups and restore

```bash
.venv/bin/python scripts/database_backend.py backup
# On an EMPTY replacement local stack initialized with the local roles:
.venv/bin/python scripts/database_backend.py restore /absolute/path/to/cryptoforge-TIMESTAMP.dump
```

Backups use PostgreSQL custom format and preserve app schemas, indexes,
constraints, triggers, grants and ownership. They are placed in the private
`.local/database/backups/` directory. Restore is a single transaction and
does not delete or overwrite existing tables. PostgreSQL and application
roles are initialized by the stack; the dump does not contain role passwords.
Preserve the secret files separately and keep an additional backup on a
different device if protection against disk failure is needed.

For a future migration with direct cloud database credentials, use PostgreSQL
17 or newer `pg_dump` against the Supabase session pooler. Do not pass the
database password in shell history or logs. Export application schemas
`public`, `internal`, `freqtrade` and audit source dependencies, role grants
and Supabase-only objects before restoring into ordinary PostgreSQL.

## Migration on 2026-10-20

The source is Supabase project `ogpfdkpslzkxftyrorhk` (CryptoForge).
Its regular REST API was returning HTTP 402 for exhausted organization egress.
No direct cloud database password was available, so data was exported through
the authorized Management SQL interface using read-only catalog/data queries.

The snapshot covers all 23 application tables in `public` and `freqtrade`,
including private Freqtrade settings, plus the required internal timestamp
trigger function, column defaults, enum, sequence positions, constraints,
indexes and triggers. Supabase's managed Auth/Storage/Realtime services are
not reproduced by this lean local stack. The source had zero Auth users and
zero Storage objects, verified with exact counts. Cloud schema migration history is
not used as a local application's database schema.

Snapshot files and source checksums are private under `.local/database-transfer/`.
Large chunks use pgcrypto's compressed PGP envelope to stay within Management
response size limits. The fixed transport passphrase is encoding machinery,
not an at-rest protection mechanism; directory permissions protect the files.
Row JSON is passed directly back to PostgreSQL, preserving exact numerics.

`scripts/import_database_snapshot.py` restores the reviewed metadata and chunks
into an empty local database in one transaction, verifies chunk SHA-256 values,
then validates constraints and restores local role isolation. Unsupported
identity/generated columns stop the import rather than being guessed.
`scripts/verify_database_snapshot.py .local/database-transfer` compares exact row counts and a sorted digest of
every row in each table, not only samples. Verification results and the final
manifest are saved alongside the private snapshot.

The cloud source is retained. New local writes are not copied back to it.

Verified result: all 23 application tables and 479,884 source rows matched
before workers resumed. The restored local database occupied about 287 MiB.
The initial 64 MiB custom-format backup was restored into a separate temporary
database and all 23 table digests matched the source again; the test database
was then removed. The local API passed authenticated candle reads, a temporary
health upsert/read/delete, and rejection of missing/invalid credentials.
Public-table RLS and the private Freqtrade role boundary were checked.
The actual SQLAlchemy/psycopg Freqtrade connection also passed; its role could
read its four settings rows and was denied access to `public.trades`.

The workstation's `.env` now selects `local`; its six previously active
database-related timers were resumed. The collector and executor both
completed their first scheduled runs successfully after switching. This
confirms process completion, not permission to bypass any trading guard.

An unrelated pre-existing problem was found in the Telegram relay:
`data/telegram-relay-state.json` is empty (last modified 2026-10-10).
The relay exits with JSONDecodeError. It has been stopped to prevent restart
loops; the empty file was retained. Its lost notification cursor and command
offset were not guessed, and historical events were not replayed. Recover or
explicitly reinitialize that cursor before restarting the relay. Database
reads through the relay client itself work with the local backend.
