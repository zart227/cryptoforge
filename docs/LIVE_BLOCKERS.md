# Live Trading Blockers

Updated: 2026-09-25.

Real trading must remain disabled until these blockers are closed by the
operator and re-tested:

- dedicated limited Bybit sub-account is confirmed;
- withdrawal permission is confirmed absent;
- API key IP whitelist is configured where feasible;
- small capital allocation is explicitly chosen: `16 USDT`;
- `.env` and VPS secrets are confirmed least-privilege on the deployment
  host;
- separate live config is created and reviewed without mutating dry-run
  configs;
- backup/restore is verified immediately before live start;
- current VPS is declared sufficient for the selected capital/scope, or
  migration is completed first;
- user-visible daily summary is implemented;
- first live pilot trades only on the dedicated limited sub-account;
- live trades are explainable from stored strategy/risk state;
- live kill switch is tested against the live execution path;
- daily/night cycle is tested without starving the VPS;
- strategy learning is reviewed against paper expectations and cannot
  bypass risk gates.

Current status:

- live pilot readiness tooling exists;
- kill switch/no-new-entry switch primitives exist;
- Telegram delivery smoke succeeded;
- first pilot capital allocation is recorded as `16 USDT`;
- Bybit AI sub-account `AIsub590123682` is connected through OAuth;
- current Bybit key appears to belong to the AI sub-account;
- current Bybit key has no withdrawal permission;
- Bybit private read-only audit from VPS confirms IP whitelist access;
- AI sub-account UTA balance is currently `0 USDT`;
- pilot capital still needs to be transferred to the AI sub-account;
- current Bybit key has non-zero derivatives permissions, which are
  blocked from live use by policy until a separate live derivatives plan
  is approved;
- real trading remains disabled.
