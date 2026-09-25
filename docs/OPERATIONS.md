# CryptoForge Operations

## Current Deployment State

CryptoForge is not deployed yet. Phase 0 read-only VPS audit is complete.
Phase 2 created an isolated `/opt/cryptoforge` runtime directory and a
`cryptoforge` system user. Phase 3 installed Freqtrade in a venv and
performed a bounded dry-run startup test with a no-entry strategy.

## Operating Principles

- Preserve existing VPS VPN/network services.
- Begin server work with read-only inspection.
- Avoid firewall, route, SSH, WireGuard, L2TP, Hysteria, or DNS changes
  unless a later phase explicitly requires them and the change is backed
  up first.
- Keep CryptoForge isolated under a clearly named path such as
  `/opt/cryptoforge`.
- Never copy SSH private keys into this repository.
- Never print or commit secrets.

## Runtime Mode

The only permitted runtime mode during current implementation is dry-run
paper trading. Configuration and tests must guard against accidental
`dry_run=false`.

Current Freqtrade runtime path:

- venv: `/opt/cryptoforge/app/venv`
- config: `/opt/cryptoforge/config/freqtrade.dry-run.json`
- user data: `/opt/cryptoforge/app/user_data`
- dry-run DB: `/opt/cryptoforge/data/tradesv3.dry_run.sqlite`
- logs: `/opt/cryptoforge/logs`

Systemd service:

- name: `cryptoforge-freqtrade.service`
- unit source: `deploy/systemd/cryptoforge-freqtrade.service`
- installed path: `/etc/systemd/system/cryptoforge-freqtrade.service`
- boot state: disabled until monitoring/recovery/log rotation phases are
  complete

Manual dry-run control:

```text
systemctl start cryptoforge-freqtrade.service
systemctl status cryptoforge-freqtrade.service --no-pager
systemctl stop cryptoforge-freqtrade.service
```

## Recovery

Detailed recovery procedures will be added in later phases after the
runtime, outbox, monitoring, and backup tooling exist.

## VPS Notes

The current VPS is too small for a casual always-on Docker deployment.
Prefer a native virtualenv-based install until the host is upgraded.
Keep any future container deployment explicitly resource-limited and
avoid binding public ports already used by existing services.
