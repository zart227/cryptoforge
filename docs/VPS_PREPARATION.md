# VPS Preparation

Date: 2026-09-25

Mode: minimal safe preparation after Phase 0 read-only audit.

## Resource Baseline Before Installation

- Root filesystem: 20 GiB total, 14 GiB available, 25% used
- Inodes: 9% used
- RAM: 939 MiB total, about 481-482 MiB available during checks
- Swap: 1.0 GiB total, 0 B used
- Swappiness: `0`
- Load average: approximately `0.36, 0.23, 0.11`

## Docker Decision

Docker is not installed on the VPS. With 1 vCPU and less than 1 GiB RAM,
continuous Docker operation is not a good default for the current host.
CryptoForge should start with a native virtualenv-based deployment and
strict service limits.

The project should remain containerizable for a later, stronger VPS.
Future Docker deployment must define explicit memory, CPU, restart, log,
and disk policies before use.

## Swap Decision

Swap already exists:

- Size: 1.0 GiB
- Used during audit: 0 B
- Swappiness: `0`

No new swap file was created and no sysctl setting was changed. This
avoids touching global host behavior while still confirming that an OOM
buffer is present.

## Isolated Runtime Path

Created:

- `/opt/cryptoforge`
- `/opt/cryptoforge/app`
- `/opt/cryptoforge/config`
- `/opt/cryptoforge/data`
- `/opt/cryptoforge/logs`
- `/opt/cryptoforge/outbox`
- `/opt/cryptoforge/backups`

Created system user:

- `cryptoforge`
- home: `/opt/cryptoforge`
- shell: `/usr/sbin/nologin`

Permissions:

- owner: `cryptoforge:cryptoforge`
- mode: `0750`

## Network and Config Safety

No firewall, route, SSH, WireGuard, L2TP, Hysteria/x-ui, DNS, or VPN
configuration was changed.

No existing configuration file was edited, so no configuration backup was
needed in this phase.

## Post-Preparation Verification

The VPS remained reachable over SSH.

Existing services verified active after preparation:

- `ssh`
- `strongswan-starter`
- `xl2tpd`
- `x-ui`
- `fail2ban`

The `wg0` interface remained present as `10.77.0.1/24`.

Post-preparation resources remained effectively unchanged:

- Root filesystem: 20 GiB total, 14 GiB available, 25% used
- RAM: 939 MiB total, about 481 MiB available
- Swap: 1.0 GiB total, 0 B used
