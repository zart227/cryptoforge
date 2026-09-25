# GitHub Deploy

CryptoForge can update the VPS automatically after each push to `main`.

## VPS Layout

- repository checkout: `/opt/cryptoforge/app/cryptoforge_repo`;
- secrets file: `/opt/cryptoforge/app/.env`;
- virtualenv: `/opt/cryptoforge/app/venv`.

The `.env` file stays outside git and is not overwritten by deploys.

## GitHub Secrets

Add these repository secrets in GitHub:

- `VPS_HOST`: VPS public IP or hostname;
- `VPS_PORT`: SSH port, usually `22`;
- `VPS_USER`: SSH user, currently `root` unless changed later;
- `VPS_SSH_KEY`: private SSH key allowed to connect to the VPS.

The workflow `.github/workflows/deploy-vps.yml` runs on every push to
`main` and can also be started manually with `workflow_dispatch`.

## Server Update Command

The workflow executes:

```bash
bash /opt/cryptoforge/app/cryptoforge_repo/deploy/update_vps.sh
```

That script fetches `origin/main`, checks out the exact remote branch,
installs the package into the VPS virtualenv in editable mode, runs a
compile/import smoke check, reloads systemd units, and prints the
deployed commit.
