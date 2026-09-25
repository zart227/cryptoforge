# Security Audit

Audit date: 2026-09-25.

## Repository

Checks performed:

- searched the working tree for exchange, Supabase and Telegram secret
  assignment patterns;
- searched git history for the same secret patterns;
- checked tracked files for `.env`, private keys and SSH key names;
- added static tests for committed dry-run configs.

Result:

- no known plaintext exchange/Supabase/Telegram secret is committed;
- no `.env` or private key file is tracked;
- only documentation placeholders are present for TypeSafe examples.

## Local Host

Checks performed:

- `.env` permissions;
- listening ports;
- container exposure;
- local logs/runtime data secret patterns.

Result:

- local `.env` permission is `600`;
- no CryptoForge container is running;
- no CryptoForge public admin endpoint was identified;
- local runtime data/log scan did not find configured secret patterns.

## VPS

Checks performed read-only over SSH:

- listening ports;
- Docker containers;
- `cryptoforge-freqtrade.service` status;
- `/opt/cryptoforge/logs` and `/opt/cryptoforge/data` secret patterns.

Result:

- `cryptoforge-freqtrade.service` is `disabled` and `inactive`;
- no Docker container exposure was reported by `docker ps`;
- open ports belong to existing VPS services such as SSH/VPN/x-ui, not
  CryptoForge;
- VPS CryptoForge logs/data scan did not find configured secret patterns.

## Supabase

The committed schema grants server-side access to `service_role` only.
Client roles are revoked by the initial migration. The service role key
must stay server-side only and must not be placed in browser code,
frontends, migration archives, logs or git.

## Bybit

Committed configs remain:

- `dry_run=true`;
- Bybit Spot only;
- no futures;
- no margin;
- no leverage;
- no exchange credentials in Freqtrade JSON;
- no withdrawal permission required or allowed.

For future real trading, Bybit API keys should use IP restrictions and
only the minimum Trade permission needed for Spot trading. Withdrawal
permission is never required for CryptoForge.

## Remaining Gate

Real trading remains disabled. Before any real-money start, repeat this
audit after deployment, after secrets are restored on the host, and after
Bybit IP whitelisting is finalized.
