# VPS Resource Cleanup

Use this only after the local Docker runtime is prepared or when the VPS
is overloaded by CryptoForge maintenance work.

## Safe First Step

The safest cleanup stops the git/deploy loop but does not touch live
execution:

```bash
cd /opt/cryptoforge/app/cryptoforge_repo
bash deploy/cleanup_vps_resources.sh --apply
```

This disables `cryptoforge-git-sync.timer`, stops a running
`cryptoforge-git-sync.service`, removes Python bytecode caches, removes
old CryptoForge rotated logs and clears the cryptoforge pip cache when it
exists.

## After Local Executor Cutover

Only after the local Docker executor is healthy and the operator approves
moving live/shadow execution off the VPS:

```bash
cd /opt/cryptoforge/app/cryptoforge_repo
bash deploy/cleanup_vps_resources.sh --apply --include-live
```

To remove the VPS virtualenv too:

```bash
bash deploy/cleanup_vps_resources.sh --apply --include-live --remove-venv
```

## Journal Cleanup

If `journalctl --disk-usage` shows large journal usage:

```bash
bash deploy/cleanup_vps_resources.sh --apply --vacuum-journal
```

The script never removes `.env`, configs, trade databases, Supabase
state, Docker volumes, Postgres data, Guacamole data or VPN/x-ui files.
