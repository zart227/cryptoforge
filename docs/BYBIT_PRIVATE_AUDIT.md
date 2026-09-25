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

Read-only audit was first attempted from the local machine and Bybit
rejected it with `10010: Unmatched IP`.

The VPS IP was then added to the Bybit whitelist and the audit was run
from the VPS.

Observed from VPS:

- IP whitelist works from the VPS;
- key is read-write;
- UTA is enabled;
- Unified USDT balance is `16.138`, which satisfies the selected
  `16 USDT` pilot allocation;
- withdrawal permission was not present as `Withdraw`;
- key appears to be a master key, not a dedicated sub-account key;
- derivatives permission count was non-zero.

Real trading remains blocked until the operator creates or switches to a
dedicated limited sub-account API key and removes derivatives/futures
permissions for the Spot-only pilot.
