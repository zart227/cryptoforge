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

Initial master-key audit from VPS:

- IP whitelist works from the VPS;
- key is read-write;
- UTA is enabled;
- Unified USDT balance is `16.138`, which satisfies the selected
  `16 USDT` pilot allocation;
- withdrawal permission was not present as `Withdraw`;
- key appears to be a master key, not a dedicated sub-account key;
- derivatives permission count was non-zero.

The operator then authorized a Bybit AI sub-account via OAuth. The
selected account is `AIsub590123682`.

Observed from VPS after switching `.env` to the AI sub-account key:

- IP whitelist works from the VPS;
- key is read-write;
- UTA is enabled;
- key appears to belong to a sub-account;
- withdrawal permission was not present as `Withdraw`;
- Spot trade permission is enabled;
- Unified USDT balance is `16.138`, which satisfies the selected
  `16 USDT` pilot allocation;
- derivatives permission count was non-zero.

Real trading remains blocked until the final live smoke checks pass and
the operator explicitly approves starting the live pilot. Derivatives and
futures permissions are allowed only for paper/shadow research until a
separate live derivatives plan is approved.
