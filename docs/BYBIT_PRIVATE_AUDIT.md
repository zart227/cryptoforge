# Bybit Private Audit

Updated: 2026-09-25.

CryptoForge includes a read-only Bybit V5 private audit helper:

- `/v5/user/query-api`;
- `/v5/account/wallet-balance` with `accountType=UNIFIED`.

It checks:

- key is read-write;
- UTA is enabled;
- key appears to belong to a sub-account;
- withdrawal permission is absent;
- IP whitelist count;
- Spot trade permission;
- Contract/Derivatives permissions are empty;
- Unified USDT balance is at least the selected pilot capital.

## Current Result

Read-only audit was attempted from the local machine and Bybit rejected it
with `10010: Unmatched IP`.

This means the API key is IP-restricted and the request source IP is not
currently whitelisted. Real trading remains blocked until the operator
adds the trading host IP to the Bybit API whitelist or creates a new key
bound to the correct trading host.

For the planned VPS runtime, whitelist the VPS public IP, not the local
desktop IP.

After whitelist update, rerun the private audit before any live pilot.
