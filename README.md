# CryptoForge

Adaptive crypto trading and strategy research platform for Bybit.

CryptoForge implements Bybit Spot market data, research, accounting and execution.
The local Supabase executor is installed with `--live`; the separate Freqtrade
runtime has dry-run configurations. Complete live/independent qualification remains open.

## Current Status

Database backend update (2026-10-20): local PostgreSQL is available with
explicit `local` / `supabase` selection. See
[database setup, migration and switching](docs/DATABASE_BACKENDS.md).
Cloud egress restrictions do not affect the local backend. Switching does
not synchronize databases or override live execution approval gates.

Updated 2026-11-05. The only current plan and checklists are
[docs/CURRENT_PLAN.md](docs/CURRENT_PLAN.md). No candidate has established
independent profitability. The local Supabase executor is installed with
`--live`; runtime qualification R1–R5 and live admission remain open.
The October 14 suite result, 1057 passed and 1 deselected, is a historical
slice, not a current full run.

## Repository Layout

- `docs/CURRENT_PLAN.md` - the only current plan and checklists
- `IMPLEMENTATION_PLAN.md` - historical phase plan
- `docs/` - architecture, operations, VPS audit, and later phase docs
- `config/` - non-secret configuration templates
- `src/cryptoforge/` - application code
- `tests/` - automated tests
- `supabase/migrations/` - Supabase schema migrations
- `user_data/strategies/` - Freqtrade strategies

## Local Docker Runtime

CryptoForge can run the Windows/WSL2 local runtime directly from a git
checkout with Docker Compose.

```powershell
Copy-Item .env.docker.example .env
# Fill .env with local Bybit/Supabase/Telegram values. Do not commit it.
docker compose up -d --build
docker compose ps
```

Or use the checked-in helper:

```powershell
.\scripts\start_local_docker.ps1 -Build
```

The default executor args in `.env.docker.example` run in shadow mode
because `--live` is intentionally absent. Add `--live` only after local
smoke checks pass and the VPS executor timer is disabled.

See `docs/LOCAL_DOCKER_MIGRATION.md` for the full migration runbook.

## Development Checks

```text
.venv/bin/python -m pytest tests/test_market_data.py -m 'not integration'
.venv/bin/python -m pytest tests/test_market_data.py -m integration
.venv/bin/python scripts/bybit_market_data_smoke.py
```

## TypeSafe Document Evaluation

Install the optional TypeSafe dependency and set an API key:

```text
.venv/bin/python -m pip install -e '.[typesafe]'
export TYPESAFE_API_KEY='...'
```

Evaluate documents:

```text
.venv/bin/python -m cryptoforge.document_eval_cli docs README.md \
  --json-out document-scores.json \
  --csv-out document-scores.csv
```

## Safety

Do not commit `.env`, exchange credentials, Supabase service keys,
Telegram tokens, SSH keys, or generated runtime state. Real trading is
out of scope until a separate explicit approval and audit.
