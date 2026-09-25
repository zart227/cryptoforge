# VPS Audit

Date: 2026-09-25

Mode: read-only inspection. No changes were made to the existing
infrastructure.

## Local Infrastructure Discovery

Inspected `/home/arthur/Projects/navision/vpn-ruvds` read-only.

Relevant documents/scripts found:

- `README.md`
- `RUNBOOK.md`
- `AGENTS.md`
- `docs/CONNECT.md`
- `docs/SERVER.md`
- `setup-server.sh`
- `harden-server.sh`
- `danflex-firewall.sh`
- `server/ssh/99-danflex-harden.conf`

Normal SSH path documented by the existing infrastructure:

- Connect through WireGuard to `root@10.77.0.1`
- Command pattern: `ssh -o BatchMode=yes -o ConnectTimeout=8 root@10.77.0.1`
- Public SSH listens on port 22 but firewall policy allows SSH only via
  the WireGuard interface.

No private keys or secret file contents were copied or printed.

## Read-Only VPS Measurements

Host:

- Hostname: `ruvds-xl3sl`
- Kernel: Ubuntu kernel `6.17.0-1022-azure`
- CPU count: 1
- RAM: 939 MiB total, 454 MiB available at inspection
- Swap: 1.0 GiB total, 0 B used
- Root filesystem: 20 GiB total, 4.6 GiB used, 14 GiB available, 25% used
- Root inode usage: 9%
- Uptime/load: up 23 days; load average around `0.09, 0.04, 0.02`
- Timezone: UTC
- NTP: active and synchronized

## Active Services Observed

Running services include:

- `ssh.service`
- `strongswan-starter.service`
- `xl2tpd.service`
- `x-ui.service`
- `fail2ban.service`
- `vpsguard.service`
- `cron.service`
- `systemd-timesyncd.service`
- `unattended-upgrades.service`

Enabled services include:

- `ssh.service`
- `strongswan-starter.service`
- `x-ui.service`
- `fail2ban.service`
- `danflex-firewall.service`
- `danflex-l2tp.service`
- `pin-gw-neigh.service`
- `netfilter-persistent.service`
- `cron.service`
- `systemd-timesyncd.service`
- `unattended-upgrades.service`

Largest observed processes by memory:

- `x-ui`
- `xray-linux-amd64`
- `multipathd`
- `systemd-journald`
- `fail2ban-server`
- `unattended-upgrades`

Important existing network/VPN services:

- WireGuard interface `wg0`
- strongSwan/IPsec
- L2TP via `xl2tpd`
- x-ui / xray services
- custom firewall rules under `DANFLEX-*`

## Network State Observed

Interfaces:

- `eth0`: public VPS interface
- `wg0`: `10.77.0.1/24`
- `ppp0`: active point-to-point interface

Routes include:

- default route via public gateway on `eth0`
- `10.77.0.0/24` via `wg0`
- `10.10.0.0/16` and `10.5.0.0/16` via `ppp0`

Listening services include:

- SSH on TCP 22
- x-ui / xray on TCP 443, UDP 443, UDP 8443, and loopback ports
- WireGuard UDP 51820
- IPsec UDP 500/4500
- L2TP UDP 1701
- x-ui admin bound to `10.77.0.1:33081`

Firewall:

- nftables rules are active.
- INPUT policy is drop.
- SSH/admin access is permitted through `wg0`.
- VPN-related public ports are open according to the existing ruleset.

Docker:

- Docker was not found in the inspected environment.

Timers:

- `danflex-l2tp-watchdog.timer`
- apt maintenance timers
- `systemd-tmpfiles-clean.timer`
- `fstrim.timer`

Cron:

- No root crontab output was observed.
- Standard `/etc/cron.*` directories exist with normal system entries.

DNS:

- `/etc/resolv.conf` lists `8.8.8.8` and `9.9.9.9`.
- `api.bybit.com` resolved successfully during audit.

Recent errors:

- No kernel OOM entries were found in the last 7 days.
- No priority-error journal entries were reported for the last 24 hours.
- One truncated user journal warning was printed by `journalctl`; this
  should be treated as a non-blocking observation unless later log
  inspection depends on that user journal.

## Risks

- The VPS is resource constrained: 1 CPU and less than 1 GiB RAM.
- Existing VPN/network services are production-like and must be
  preserved.
- Docker may be too heavy for the current VPS without careful resource
  limits.
- Port 443 is already used by existing services, so CryptoForge must not
  assume it can bind public HTTPS ports.
- Server work should avoid route, firewall, SSH, or VPN changes unless
  explicitly planned and backed up.

## Proposed Changes

No changes proposed in Phase 0 beyond documentation. Later deployment
should prefer an isolated path such as `/opt/cryptoforge`, low memory
limits, no public admin surface by default, and no changes to the
existing network stack.
