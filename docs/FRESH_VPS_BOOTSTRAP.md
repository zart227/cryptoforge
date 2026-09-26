# Fresh VPS Bootstrap

Use this after a full VPS wipe. Run as `root` on a fresh Ubuntu host.

## One Command

```bash
curl -fsSL https://raw.githubusercontent.com/zart227/cryptoforge/main/deploy/bootstrap_fresh_vps.sh -o /tmp/bootstrap_cryptoforge.sh
bash /tmp/bootstrap_cryptoforge.sh
```

The script installs system packages, creates the `cryptoforge` user,
clones the repository, creates `/opt/cryptoforge/app/venv`, installs the
project and Freqtrade, installs systemd units, creates a placeholder
`/opt/cryptoforge/app/.env`, and enables the git-sync timer.

## Restore Secrets

The bootstrap script does not contain real secrets. After it finishes,
restore `/opt/cryptoforge/app/.env` from a trusted local copy or password
manager.

Required values include:

- `BYBIT_API_KEY`;
- `BYBIT_API_SECRET`;
- `BYBIT_AI_SUB_MEMBER_ID`;
- `SUPABASE_URL`;
- `SUPABASE_SECRET_KEY`;
- alert channel settings such as `NTFY_TOPIC`.

Set permissions:

```bash
chown cryptoforge:cryptoforge /opt/cryptoforge/app/.env
chmod 600 /opt/cryptoforge/app/.env
```

If you copied the env file to the fresh VPS, run:

```bash
bash /opt/cryptoforge/app/cryptoforge_repo/deploy/post_bootstrap_restore.sh /path/to/.env
```

With a GitHub self-hosted runner registration token:

```bash
bash /opt/cryptoforge/app/cryptoforge_repo/deploy/post_bootstrap_restore.sh /path/to/.env '<runner-token>'
```

The post-bootstrap helper syncs strategies, optionally installs the
runner, selects the current intraday Spot universe, and runs the no-trade
live smoke check.

## Bybit Whitelist

If the Bybit API key is IP-whitelisted, add the new VPS public IP in
Bybit before running private API checks.

## Verify

```bash
cd /opt/cryptoforge/app/cryptoforge_repo
set -a
. /opt/cryptoforge/app/.env
set +a
PYTHONPATH=src /opt/cryptoforge/app/venv/bin/python scripts/live_pilot_smoke.py \
  --env-file /opt/cryptoforge/app/.env \
  --project-root /opt/cryptoforge/app/cryptoforge_repo
```

Do not start live trading until the smoke check is green.

## Live Service

The live pilot service is installed but not enabled by default:

```bash
systemctl status cryptoforge-live-pilot.service
```

Start only after final approval:

```bash
systemctl start cryptoforge-live-pilot.service
journalctl -u cryptoforge-live-pilot.service -f
```
