# CryptoForge

Adaptive crypto trading and strategy research platform for Bybit.

CryptoForge is currently being bootstrapped from `IMPLEMENTATION_PLAN.md`.
The active implementation constraints are:

- Bybit only
- Spot only
- Dry-run / paper trading only
- No futures, margin, leverage, or real-money execution
- Independent hard risk controls
- Resource-conscious operation for a small VPS

## Current Status

The repository is in Phase 0/1 bootstrap. The VPS has been inspected
read-only and baseline documentation has been created. No trading runtime
has been installed or started yet.

## Repository Layout

- `IMPLEMENTATION_PLAN.md` - authoritative progress plan
- `docs/` - architecture, operations, VPS audit, and later phase docs
- `config/` - non-secret configuration templates
- `src/cryptoforge/` - application code
- `tests/` - automated tests
- `supabase/migrations/` - future Supabase schema migrations
- `user_data/strategies/` - future Freqtrade strategies

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
