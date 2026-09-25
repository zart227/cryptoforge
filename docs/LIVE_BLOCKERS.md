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
- Bybit private read-only audit is blocked by API whitelist mismatch
  (`10010: Unmatched IP`);
- real trading remains disabled.
