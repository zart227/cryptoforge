# CryptoForge Operations

## Current Deployment State

CryptoForge is not deployed yet. Phase 0 read-only VPS audit has been
started and no server changes have been made.

## Operating Principles

- Preserve existing VPS VPN/network services.
- Begin server work with read-only inspection.
- Avoid firewall, route, SSH, WireGuard, L2TP, Hysteria, or DNS changes
  unless a later phase explicitly requires them and the change is backed
  up first.
- Keep CryptoForge isolated under a clearly named path such as
  `/opt/cryptoforge` when deployment begins.
- Never copy SSH private keys into this repository.
- Never print or commit secrets.

## Runtime Mode

The only permitted runtime mode during current implementation is dry-run
paper trading. Configuration and tests must guard against accidental
`dry_run=false`.

## Recovery

Detailed recovery procedures will be added in later phases after the
runtime, outbox, monitoring, and backup tooling exist.
