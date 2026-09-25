# GitHub Deploy

CryptoForge can update the VPS automatically from `main`.

## VPS Layout

- repository checkout: `/opt/cryptoforge/app/cryptoforge_repo`;
- secrets file: `/opt/cryptoforge/app/.env`;
- virtualenv: `/opt/cryptoforge/app/venv`.

The `.env` file stays outside git and is not overwritten by deploys.

## Server Pull Timer

The active deployment path is a VPS-side systemd timer:

- unit: `cryptoforge-git-sync.service`;
- timer: `cryptoforge-git-sync.timer`;
- interval: every two minutes after the previous run.

This pull model works even when the VPS SSH port is not reachable from
GitHub-hosted runners. The repository is public, so the VPS can fetch it
over HTTPS without a GitHub deploy key.

## GitHub SSH Workflow

The repository also contains a manual GitHub Actions workflow for direct
SSH deploys. It is intentionally `workflow_dispatch` only because the VPS
public SSH port must be reachable from GitHub-hosted runners before it
can work reliably.

### GitHub Secrets

Add these repository secrets in GitHub:

- `VPS_HOST`: VPS public IP or hostname;
- `VPS_PORT`: SSH port, usually `22`;
- `VPS_USER`: SSH user, currently `root` unless changed later;
- `VPS_SSH_KEY`: private SSH key allowed to connect to the VPS.

The workflow `.github/workflows/deploy-vps.yml` can be started manually
with `workflow_dispatch` after public SSH access is available.

## Server Update Command

The workflow executes:

```bash
bash /opt/cryptoforge/app/cryptoforge_repo/deploy/update_vps.sh
```

That script fetches `origin/main`, checks out the exact remote branch,
installs the package into the VPS virtualenv in editable mode, runs a
compile/import smoke check, reloads systemd units, and prints the
deployed commit.
