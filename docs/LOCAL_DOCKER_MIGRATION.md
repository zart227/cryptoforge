# Local Docker Migration

This runbook moves CryptoForge's recurring work from the small VPS to a
Windows computer running Docker Desktop.

## Target Split

Run locally:

- Supabase market feeder;
- Supabase-backed executor;
- night research;
- Telegram relay;
- venv/build/test/backtest work.

Keep on the VPS only until cutover is confirmed:

- the existing fallback CryptoForge install;
- no regular git sync/deploy timer;
- no heavy research or venv rebuilds.

## Windows Setup

1. Install Docker Desktop with WSL2 backend.
2. Clone the repository on the Windows machine.
3. Copy `.env.docker.example` to `.env`.
4. Fill `.env` with real Bybit, Supabase and optional Telegram values.
5. Confirm the Bybit key belongs to the dedicated sub-account, has no
   withdrawal permission and has the intended IP policy.

Do not commit `.env`.

The checked-in helper can perform the first-run copy/check/start flow:

```powershell
.\scripts\start_local_docker.ps1 -Build
```

## First Shadow Start

Build and start only non-trading services first:

```powershell
docker compose up -d --build market-feeder night-research telegram-relay
docker compose logs -f market-feeder
```

Then start the executor in shadow mode. The default
`CRYPTOFORGE_LIVE_EXECUTOR_ARGS` intentionally does not include `--live`.

```powershell
docker compose up -d live-executor
docker compose logs -f live-executor
```

Expected shadow evidence:

- market feeder prints `synced_pairs=...`;
- executor prints `decision=...` rows;
- Supabase `trade_decisions.mode` is `shadow`;
- no Bybit order is submitted.

## Live Cutover

Only after shadow mode is healthy:

1. Put the VPS executor in a maintenance window.
2. Disable the VPS executor timer:

   ```bash
   systemctl disable --now cryptoforge-supabase-executor.timer
   ```

3. Confirm no executor service is currently running on the VPS:

   ```bash
   systemctl status cryptoforge-supabase-executor.service --no-pager
   ```

4. Add `--live` to `CRYPTOFORGE_LIVE_EXECUTOR_ARGS` in local `.env`.
5. Restart only the local executor:

   ```powershell
   docker compose up -d --force-recreate live-executor
   docker compose logs -f live-executor
   ```

## Reboot Recovery

Docker Compose services use `restart: unless-stopped`. In Docker Desktop,
enable startup with Windows sign-in. After reboot, verify:

```powershell
docker compose ps
docker compose logs --tail 100 market-feeder live-executor telegram-relay
```

If Docker Desktop was not running at login, start it manually and then run:

```powershell
docker compose up -d
```

## VPS Cleanup After Stable Local Operation

After at least several healthy local cycles, disable the noisy deploy loop:

```bash
systemctl disable --now cryptoforge-git-sync.timer
```

Keep the VPS code and secrets as rollback material until the local setup
has survived a Windows reboot and a Docker Desktop restart.

## Why This Relieves The VPS

The old VPS git sync can run every two minutes and may perform `git fetch`,
`git reset`, `git clean`, `pip install -e .`, bytecode compilation and
unit-file copying. On a 1 CPU, 1 GB RAM VPS that also runs VPN/x-ui/xray,
Docker, Guacamole and Postgres, that can create disk queueing and high
I/O wait. Moving build, deploy, polling and research to the local computer
leaves the VPS free for its existing infrastructure.
