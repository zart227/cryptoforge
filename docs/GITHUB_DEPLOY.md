# GitHub Deploy

CryptoForge can update the VPS automatically from `main`.

## VPS Layout

- repository checkout: `/opt/cryptoforge/app/cryptoforge_repo`;
- secrets file: `/opt/cryptoforge/app/.env`;
- virtualenv: `/opt/cryptoforge/app/venv`.

The `.env` file stays outside git and is not overwritten by deploys.

## Self-Hosted GitHub Actions Runner

The preferred GitHub Actions path is a self-hosted runner installed on
the VPS with label `cryptoforge-vps`.

This avoids inbound SSH from GitHub-hosted runners. The VPS only needs
outbound HTTPS access to GitHub.

After the runner is online, `.github/workflows/deploy-vps.yml` runs on
every push to `main` and executes the local deploy script on the VPS.

To register the runner, open GitHub:

`Settings -> Actions -> Runners -> New self-hosted runner -> Linux x64`

Copy the short registration token from GitHub and run:

```bash
bash /opt/cryptoforge/app/cryptoforge_repo/deploy/install_github_runner.sh '<token>'
```

The helper installs the runner into:

```bash
/opt/github-actions/cryptoforge
```

It registers the runner with label:

```bash
cryptoforge-vps
```

## Server Pull Timer

The fallback deployment path is a VPS-side systemd timer:

- unit: `cryptoforge-git-sync.service`;
- timer: `cryptoforge-git-sync.timer`;
- interval: every two minutes after the previous run.

This pull model works even when the VPS SSH port is not reachable and
the GitHub Actions runner is offline. The repository is public, so the
VPS can fetch it over HTTPS without a GitHub deploy key.

## GitHub SSH Workflow

The repository keeps a disabled direct SSH deploy job as a reference.
It should stay disabled while public SSH from GitHub-hosted runners is
not reachable.

### GitHub Secrets

Add these repository secrets in GitHub:

- `VPS_HOST`: VPS public IP or hostname;
- `VPS_PORT`: SSH port, usually `22`;
- `VPS_USER`: SSH user, currently `root` unless changed later;
- `VPS_SSH_KEY`: private SSH key allowed to connect to the VPS.

These secrets are not needed for the self-hosted runner path.

## Server Update Command

The workflow executes:

```bash
bash /opt/cryptoforge/app/cryptoforge_repo/deploy/update_vps.sh
```

That script fetches `origin/main`, checks out the exact remote branch,
installs the package into the VPS virtualenv in editable mode, runs a
compile/import smoke check, reloads systemd units, and prints the
deployed commit.
