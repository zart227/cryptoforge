# CryptoForge - Implementation Plan

> **Authoritative execution plan**
>
> This file is the primary source of truth for implementation progress.
> Codex must copy it into the root of the `cryptoforge` repository as
> `IMPLEMENTATION_PLAN.md`, follow the phases in order, and maintain the
> checkboxes in the project copy.

## 0. Non-negotiable rules

-   [ ] Exchange scope is **Bybit only**.
-   [ ] Current market scope is **Spot only**.
-   [ ] Current implemented execution mode is **DRY-RUN / PAPER TRADING
    only** until the controlled-live phase passes audit.
-   [ ] Real-money trading remains disabled until a dedicated
    controlled-live phase is implemented, audited, and explicitly
    enabled.
-   [ ] Futures, margin and leverage remain disabled.
-   [ ] Hard risk limits cannot be modified by a strategy, ML model,
    optimizer, or Strategy Lab.
-   [ ] Existing VPS VPN/network services must not be broken.
-   [ ] Trading runtime always has priority over research, backtesting,
    optimization and ML.
-   [ ] Secrets must never be committed to Git or printed into
    logs/documentation.
-   [ ] A checkbox may be marked `[x]` only after implementation **and
    functional verification**.
-   [ ] A phase may not be declared complete while a blocking checklist
    item is unfinished.
-   [ ] Any deviation from this plan must be recorded under **Decision
    Log** with reason, impact and verification.
-   [ ] Do not silently rewrite or simplify this plan.

## 0.1 Future autonomous operating model

The user wants CryptoForge to become an autonomous trading and research
system:

-   [ ] Day mode: trade approved strategies automatically.
-   [ ] Day mode: monitor live outcomes and pause underperforming or
    unsafe behavior.
-   [ ] Night mode: train/research/backtest candidate strategies.
-   [ ] Night mode: prepare improved strategies for the next trading
    cycle.
-   [ ] Learn from what worked and what failed.
-   [ ] Prefer the fastest capital growth only inside explicit hard risk,
    liquidity, resource and safety limits.

This strategic objective does **not** authorize immediate live trading.
The implementable objective is **risk-constrained capital growth**, not
unbounded maximum short-term profit.

Forbidden even under autonomous mode:

-   [ ] Strategy/ML/optimizer self-modification of hard risk limits.
-   [ ] Live deployment of unvalidated strategies.
-   [ ] Martingale, doubling after loss, all-in behavior, unlimited
    averaging down, or stop removal to avoid realizing loss.
-   [ ] Enabling withdrawal permissions.
-   [ ] Enabling futures, margin or leverage without a separate plan
    revision and audit.
-   [ ] Research jobs starving daytime trading.

## 1. Target architecture

``` text
                         BYBIT SPOT
                             |
                             v
                      Market Data Layer
                             |
                             v
                       Market Scanner
                             |
                             v
                   Market Regime Detector
                             |
                             v
                      Strategy Engine
                             |
                             v
                        Risk Engine
                             |
                             v
                         Freqtrade
                             |
              DRY-RUN / Controlled Live Execution
                             |
              +--------------+---------------+
              |                              |
              v                              v
         Local State                   SQLite Outbox
                                             |
                                             v
                                         Supabase
                                             |
                  +--------------------------+----------------------+
                  |                          |                      |
                  v                          v                      v
             Trade Journal              Metrics              Experiments
                                                                    |
                                                                    v
                                                              Strategy Lab
                                                                    |
                                                                    v
                                                      Backtest / Validation
                                                                    |
                                                                    v
                                           Night Research / Future FreqAI
```

Current VPS: Ubuntu 24.04 LTS, 1 vCPU \~2.2 GHz, 1 GB RAM, 20 GB HDD.

Future target: 2+ CPU, 8+ GB RAM, 80+ GB SSD/NVMe.

Supabase stores durable valuable state, but it must **not** be a
critical dependency for managing an already-open position. Historical
candles and other reproducible bulk market data should normally remain
disposable/re-downloadable.

------------------------------------------------------------------------

# PHASE 0 - Existing infrastructure and VPS audit

## 0.1 Local infrastructure discovery

Before asking the user for IP, SSH user, port, key or connection
command:

-   [x] Inspect `/home/arthur/Projects/navision/vpn-ruvds` read-only.
-   [x] Find README/docs/scripts/SSH config/host aliases/deployment
    files.
-   [x] Determine the existing normal SSH connection method.
-   [x] Do not copy private keys into CryptoForge.
-   [x] Do not print private-key contents.
-   [x] Do not modify `vpn-ruvds`.
-   [x] Record only safe, non-secret connection information in
    `docs/VPS_AUDIT.md`.

## 0.2 Read-only VPS audit

-   [x] Verify CPU.
-   [x] Verify RAM.
-   [x] Verify swap.
-   [x] Verify filesystem and free disk.
-   [x] Verify inode usage.
-   [x] Inspect load average.
-   [x] Inspect running processes.
-   [x] Inspect running systemd services.
-   [x] Inspect enabled services.
-   [x] Inspect Docker and Docker Compose if present.
-   [x] Inspect running containers and compose projects.
-   [x] Inspect listening ports.
-   [x] Inspect interfaces, routes and policy routing.
-   [x] Inspect firewall/nftables/iptables/UFW without changing them.
-   [x] Inspect cron and systemd timers.
-   [x] Verify DNS.
-   [x] Verify NTP/time synchronization.
-   [x] Verify timezone.
-   [x] Check recent OOM events.
-   [x] Check relevant journal errors.
-   [x] Identify VPN/network-related services.
-   [x] Identify resource conflicts that could affect CryptoForge.

## 0.3 Documentation

-   [x] Create `docs/VPS_AUDIT.md`.
-   [x] Record state **before changes**.
-   [x] Record existing services that must be preserved.
-   [x] Record resource constraints.
-   [x] Record risks.
-   [x] Record proposed changes.

### Definition of Done - Phase 0

-   [x] Existing SSH path is understood and tested.
-   [x] No existing infrastructure was modified.
-   [x] VPS audit contains enough information to make an informed
    deployment decision.
-   [x] Actual CPU/RAM/disk/network state is documented.
-   [x] Blocking conflicts are identified before installation.

------------------------------------------------------------------------

# PHASE 1 - Project bootstrap and plan adoption

-   [x] Locate/clone/open repository `cryptoforge`.
-   [x] Copy this file into repository root as `IMPLEMENTATION_PLAN.md`.
-   [x] Treat repository copy as the live authoritative plan.
-   [x] Create/update `README.md`.
-   [x] Create `.gitignore`.
-   [x] Create `.env.example` with placeholders only.
-   [x] Ensure `.env` is ignored.
-   [x] Create logical project directories only when needed.
-   [x] Create `docs/ARCHITECTURE.md`.
-   [x] Create `docs/OPERATIONS.md`.
-   [x] Create Decision Log section in this plan.
-   [x] Commit project bootstrap if repository workflow permits.

### Definition of Done - Phase 1

-   [x] `IMPLEMENTATION_PLAN.md` exists in repo root.
-   [x] Progress is tracked in the repository copy.
-   [x] Git cannot accidentally commit normal secret files.
-   [x] Project has a documented architecture and operating baseline.

------------------------------------------------------------------------

# PHASE 2 - Safe VPS preparation

-   [x] Reconfirm free disk before installation.
-   [x] Determine whether Docker is viable with current RAM.
-   [x] If Docker is used, define strict resource-conscious deployment.
-   [x] If Docker is not viable, document why and keep architecture
    containerizable.
-   [x] Configure safe swap if missing and justified.
-   [x] Document swap size and swappiness.
-   [x] Create isolated `/opt/cryptoforge` or justified equivalent.
-   [x] Keep CryptoForge resources clearly prefixed/namespaced.
-   [x] Do not alter VPN routes/firewall unless absolutely necessary.
-   [x] Back up any config before modifying it.
-   [x] Establish safe file permissions.
-   [x] Measure post-preparation RAM/disk baseline.

### Definition of Done - Phase 2

-   [x] VPS remains reachable.
-   [x] Existing VPN/network services still function.
-   [x] CryptoForge has isolated storage/runtime space.
-   [x] OOM protection is improved without exhausting disk.
-   [x] Baseline resource usage is documented.

------------------------------------------------------------------------

# PHASE 3 - Freqtrade runtime

-   [x] Verify current Freqtrade documentation/version compatibility
    with Ubuntu 24.04 and Bybit Spot.
-   [x] Verify current Bybit Spot dry-run support and limitations.
-   [x] Install minimal Freqtrade runtime.
-   [x] Configure Bybit only.
-   [x] Ensure `dry_run=true`.
-   [x] Ensure Futures/margin/leverage are disabled.
-   [x] Configure virtual balance: 1000 USDT.
-   [x] Keep credentials absent until actually required.
-   [x] Start runtime.
-   [x] Measure RAM/CPU/disk.
-   [x] Test clean stop/start.
-   [x] Test state persistence.

### Definition of Done - Phase 3

-   [x] Freqtrade starts reliably.
-   [x] Configuration cannot place real orders.
-   [x] Bybit is the only exchange configured.
-   [x] Runtime fits current VPS without unacceptable swapping/OOM.

------------------------------------------------------------------------

# PHASE 4 - Bybit public market data

-   [x] Retrieve Bybit Spot instruments.
-   [x] Identify USDT Spot pairs.
-   [x] Retrieve ticker/24h market statistics.
-   [x] Retrieve OHLCV required by strategy.
-   [x] Primary timeframe: 5m.
-   [x] Evaluate 15m and 1h as informative timeframes.
-   [x] Do not enable 1m unless its value is demonstrated.
-   [x] Handle API timeout/rate-limit/retry correctly.
-   [x] Detect stale market data.
-   [x] Stop opening new positions when market data is stale.
-   [x] Add integration tests around parsing and freshness.

### Definition of Done - Phase 4

-   [x] Public market data works without trading credentials where
    possible.
-   [x] Stale/missing data is detected.
-   [x] Rate limits/errors do not crash the runtime.
-   [x] Memory use remains controlled.

------------------------------------------------------------------------

# PHASE 5 - Supabase persistent backend

## 5.1 Schema

Design only justified tables. Candidate entities:

-   `trades`
-   `trade_features`
-   `strategies`
-   `strategy_versions`
-   `experiments`
-   `backtest_runs`
-   `walk_forward_runs`
-   `model_runs`
-   `model_metrics`
-   `daily_metrics`
-   `system_events`

Checklist:

-   [x] Design schema.
-   [x] Define primary keys/UUIDs.
-   [x] Define timestamps consistently.
-   [x] Define relationships.
-   [x] Add appropriate indexes.
-   [x] Avoid unnecessary duplication.
-   [x] Store SQL migrations in Git.
-   [x] Document schema in `docs/SUPABASE.md`.
-   [x] Keep privileged credentials server-side only.
-   [x] Define security/RLS approach if frontend access is introduced.
-   [x] Do not store model binaries as PostgreSQL BYTEA by default.

## 5.2 Storage policy

-   [x] Define model artifact metadata.
-   [x] Define future Supabase Storage path convention.
-   [x] Store checksum for important artifacts.
-   [x] Do not upload unlimited raw candles/tick/order-book data.
-   [x] Document what is critical, reproducible and temporary.

### Definition of Done - Phase 5

-   [x] Migrations can create schema reproducibly.
-   [x] Schema is documented.
-   [x] Secrets are not in Git.
-   [x] Bulk reproducible market data is excluded from uncontrolled
    long-term storage.

------------------------------------------------------------------------

# PHASE 6 - Durable local outbox and Supabase sync

Use a lightweight persistent local queue such as SQLite, not
Kafka/RabbitMQ.

-   [x] Define event envelope.
-   [x] Generate UUID/idempotency key.
-   [x] Persist event locally before remote delivery.
-   [x] Implement Supabase delivery.
-   [x] ACK only after successful remote persistence.
-   [x] Implement retry/backoff.
-   [x] Prevent duplicate remote records.
-   [x] Survive process restart.
-   [x] Survive Supabase outage.
-   [x] Monitor queue depth/oldest event age.
-   [x] Define fail-safe threshold for prolonged persistence outage.
-   [x] Test disconnect -\> queue -\> reconnect -\> flush.
-   [x] Test duplicate delivery attempts.

### Definition of Done - Phase 6

-   [x] No test event is lost during simulated Supabase outage.
-   [x] Retries are idempotent.
-   [x] Open-position management does not depend on Supabase
    availability.
-   [x] Queue growth is observable.

------------------------------------------------------------------------

# PHASE 7 - Market Scanner

Use staged filtering to save resources.

## Cheap universe filter

-   [x] Bybit Spot only.
-   [x] USDT quote only.
-   [x] Exclude unsuitable stablecoin pairs where appropriate.
-   [x] Exclude leveraged/special tokens where applicable.
-   [x] Filter insufficient history.
-   [x] Filter very low quote volume.
-   [x] Filter excessive spread.
-   [x] Filter pairs incompatible with minimum order requirements.

## Candidate scoring

Evaluate justified subset of:

-   24h quote volume
-   liquidity
-   spread
-   ATR
-   realized volatility
-   intraday range
-   volume change/anomaly
-   momentum
-   trade activity if reliably available

Checklist:

-   [x] Implement cheap first-stage filter.
-   [x] Limit expensive calculations to shortlist.
-   [x] Make thresholds configurable.
-   [x] Avoid selecting a coin solely because of extreme 24h gain.
-   [x] Add pump/illiquidity safeguards.
-   [x] Cap number of actively analyzed pairs.
-   [x] Benchmark scanner CPU/RAM.
-   [x] Unit-test filters/scoring.

### Definition of Done - Phase 7

-   [x] Scanner produces a bounded candidate set.
-   [x] Scanner does not overload 1 vCPU/1 GB VPS.
-   [x] Low-liquidity/high-spread candidates are rejected.
-   [x] Selection reasons are observable/logged without excessive
    logging.

------------------------------------------------------------------------

# PHASE 8 - Market Regime Detector

Initial transparent regimes:

-   `TREND_UP`
-   `TREND_DOWN`
-   `RANGE`
-   `HIGH_VOLATILITY`
-   `LOW_VOLATILITY`

Candidate inputs:

-   ADX
-   EMA structure
-   ATR / normalized ATR
-   realized volatility
-   broader market benchmark

Checklist:

-   [x] Define deterministic regime rules.
-   [x] Avoid future-data leakage.
-   [x] Make thresholds configurable.
-   [x] Add unit tests.
-   [x] Record regime with each trade.
-   [x] Document in `docs/MARKET_REGIME.md`.

### Definition of Done - Phase 8

-   [x] Same input produces deterministic classification.
-   [x] No future candle is used.
-   [x] Regime is persisted with trade context.

------------------------------------------------------------------------

# PHASE 9 - Baseline strategy

Purpose: control strategy, not optimized historical winner.

Candidate minimal indicators:

-   EMA
-   ADX
-   RSI
-   Volume
-   ATR

Checklist:

-   [x] Implement simple transparent baseline.
-   [x] Document entry logic.
-   [x] Document exit logic.
-   [x] Document indicator purpose.
-   [x] Avoid indicator bloat.
-   [x] Include fees in testing.
-   [x] Check lookahead bias.
-   [x] Run baseline backtest only within resource limits.
-   [x] Save baseline version metadata.

### Definition of Done - Phase 9

-   [x] Strategy is understandable and reproducible.
-   [x] Backtest completes without leakage.
-   [x] Baseline exists for future champion/challenger comparisons.

------------------------------------------------------------------------

# PHASE 10 - Independent Risk Engine

Initial configurable dry-run defaults:

-   virtual capital: 1000 USDT
-   risk per trade: \<= 0.5%
-   max simultaneous positions: 2
-   daily loss limit: 2%
-   max portfolio drawdown: 10%

Forbidden:

-   martingale
-   doubling after loss
-   unbounded averaging down
-   removing stop to avoid realizing a loss
-   all-in
-   strategy/ML modification of hard limits

Checklist:

-   [x] Implement central hard-risk config.
-   [x] Implement position-size calculation.
-   [x] Account for stop distance.
-   [x] Account for fees.
-   [x] Account for minimum order and precision.
-   [x] Implement max concurrent positions.
-   [x] Implement daily loss guard.
-   [x] Implement portfolio drawdown guard.
-   [x] Implement no-new-trade fail-safe.
-   [x] Unit-test boundary conditions.
-   [x] Ensure strategy cannot bypass hard limits.
-   [x] Document in `docs/RISK_MANAGEMENT.md`.

### Definition of Done - Phase 10

-   [x] Risk tests cover edge cases.
-   [x] Deliberately oversized trade requests are rejected.
-   [x] Daily/drawdown limits stop new entries.
-   [x] Hard limits are outside strategy/ML control.

------------------------------------------------------------------------

# PHASE 11 - Dynamic SL/TP and position management

## Stop loss

Evaluate:

-   ATR-based
-   swing-based
-   volatility-adjusted

## Take profit

Evaluate:

-   risk/reward target
-   ATR target
-   trailing stop
-   break-even logic

Checklist:

-   [ ] Every simulated position has defined risk protection.
-   [ ] SL distance feeds position sizing.
-   [ ] SL/TP logic is strategy-versioned.
-   [ ] Test gap/fast-move behavior realistically within Freqtrade
    limitations.
-   [ ] Test trailing/break-even logic if enabled.
-   [ ] Do not overcomplicate baseline.
-   [ ] Persist SL/TP context in journal.

### Definition of Done - Phase 11

-   [ ] No simulated trade can open without valid risk definition.
-   [ ] Position sizing and stop distance are consistent.
-   [ ] SL/TP behavior is covered by tests.

------------------------------------------------------------------------

# PHASE 12 - End-to-end Bybit Spot dry-run

-   [ ] Connect scanner -\> regime -\> strategy -\> risk -\> Freqtrade.
-   [ ] Confirm only dry-run orders are created.
-   [ ] Confirm no Futures endpoints/config.
-   [ ] Confirm no leverage.
-   [ ] Exercise at least one controlled simulated lifecycle if market
    conditions allow.
-   [ ] Verify restart behavior.
-   [ ] Verify no duplicate state after restart.
-   [ ] Measure CPU/RAM/swap/disk during normal operation.

### Definition of Done - Phase 12

-   [ ] End-to-end paper-trading pipeline works.
-   [ ] Real-money execution remains impossible under active config.
-   [ ] Runtime remains stable on current VPS.

------------------------------------------------------------------------

# PHASE 13 - Trade Journal

Persist useful context:

-   trade id
-   timestamps
-   pair
-   strategy/version
-   regime
-   timeframe
-   entry/exit
-   position size
-   SL/TP
-   fees
-   PnL / PnL %
-   duration
-   entry/exit reason
-   ATR/RSI/ADX/EMA state
-   volume/volatility/spread
-   MFE/MAE where feasible

Checklist:

-   [ ] Define canonical trade record.
-   [ ] Avoid duplicating Freqtrade data unnecessarily.
-   [ ] Persist feature snapshot.
-   [ ] Persist entry/exit reason.
-   [ ] Compute MFE/MAE where reliable.
-   [ ] Send durable events through outbox.
-   [ ] Validate records against local trade state.

### Definition of Done - Phase 13

-   [ ] A completed dry-run trade can be reconstructed from stored
    metadata.
-   [ ] Trade context survives Supabase outage via outbox.

------------------------------------------------------------------------

# PHASE 14 - Performance metrics

Compute at minimum:

-   net PnL
-   gross profit/loss
-   fees
-   trade count
-   win rate
-   profit factor
-   expectancy
-   average win/loss
-   max drawdown
-   Sharpe
-   Sortino

Checklist:

-   [ ] Define formulas and assumptions.
-   [ ] Avoid treating win rate as primary metric.
-   [ ] Produce daily metrics.
-   [ ] Produce strategy-version metrics.
-   [ ] Produce regime-specific metrics.
-   [ ] Test calculations against controlled samples.
-   [ ] Persist summaries to Supabase.

### Definition of Done - Phase 14

-   [ ] Metrics are reproducible from stored trades.
-   [ ] Controlled test cases match expected calculations.

------------------------------------------------------------------------

# PHASE 15 - Backtesting framework

-   [ ] Define historical-data download/cache process.
-   [ ] Keep candles reproducible/disposable.
-   [ ] Include fees.
-   [ ] Use realistic execution assumptions.
-   [ ] Check minimum order/precision.
-   [ ] Prevent future leakage.
-   [ ] Save summary results, not unlimited raw output.
-   [ ] Limit resource usage.
-   [ ] Run research at lower priority than trading.
-   [ ] Document backtesting procedure.

### Definition of Done - Phase 15

-   [ ] Baseline backtest is reproducible.
-   [ ] Resource usage is bounded.
-   [ ] Backtest does not interfere materially with trader runtime.

------------------------------------------------------------------------

# PHASE 16 - Strategy evaluation and lifecycle

Lifecycle:

`DRAFT -> BACKTESTED -> OUT_OF_SAMPLE_TESTED -> WALK_FORWARD_TESTED -> PAPER_TRADING -> CANDIDATE -> APPROVED`

Approval does **not** enable real money.

Checklist:

-   [ ] Implement lifecycle metadata.
-   [ ] Prevent invalid state transitions.
-   [ ] Define evaluation criteria.
-   [ ] Compare return and drawdown.
-   [ ] Compare profit factor/expectancy.
-   [ ] Compare Sharpe/Sortino.
-   [ ] Require adequate trade count.
-   [ ] Evaluate stability.
-   [ ] Store evaluation evidence.
-   [ ] Keep human approval boundary for real trading.

### Definition of Done - Phase 16

-   [ ] Strategy state is traceable.
-   [ ] A high-profit but unstable/overfit strategy is not automatically
    promoted.
-   [ ] Autonomous promotion cannot bypass hard risk gates.

------------------------------------------------------------------------

# PHASE 17 - Champion / Challenger framework

-   [ ] Register baseline as initial control/champion candidate.
-   [ ] Define challenger metadata.
-   [ ] Compare on equivalent datasets/windows.
-   [ ] Compare out-of-sample.
-   [ ] Compare walk-forward.
-   [ ] Compare by market regime.
-   [ ] Do not replace champion based solely on absolute historical
    profit.
-   [ ] Record promotion/rejection reason.

### Definition of Done - Phase 17

-   [ ] Every promotion/rejection is evidence-backed and auditable.
-   [ ] Strategy history remains available.

------------------------------------------------------------------------

# PHASE 18 - Strategy Lab skeleton

Distinguish clearly:

1.  Parameter optimization
2.  Machine learning
3.  Strategy discovery

Potential research dimensions:

-   parameters
-   indicator combinations
-   entry/exit rules
-   regime-specific strategies
-   ML features
-   model parameters

Current VPS constraints:

-   [ ] No massive parallel search.
-   [ ] No thousands of concurrent backtests.
-   [ ] Check free RAM/load/disk before research job.
-   [ ] Use `nice`/`ionice` where appropriate.
-   [ ] Defer research when trading resources are constrained.
-   [ ] Persist experiment metadata/results.
-   [ ] Avoid keeping large failed artifacts.
-   [ ] Implement experiment IDs and reproducibility metadata.
-   [ ] Implement day/night scheduling policy.
-   [ ] Keep research disabled or low priority during trading hours.
-   [ ] Candidate strategies are prepared for review/paper deployment,
    not uncontrolled live replacement.

### Definition of Done - Phase 18

-   [ ] Lightweight experiment pipeline exists.
-   [ ] It cannot starve the trading process.
-   [ ] Heavy search is explicitly marked NOT ACTIVE on current VPS.
-   [ ] Night research can produce candidate recommendations without
    changing live risk limits.

------------------------------------------------------------------------

# PHASE 19 - Future FreqAI architecture

Do not pretend ML is active if it is not.

Future candidates:

-   LightGBM
-   XGBoost
-   CatBoost

Candidate features:

-   returns
-   ATR
-   RSI
-   ADX
-   EMA distances
-   MACD
-   Bollinger width
-   VWAP distance
-   volume/anomaly
-   momentum
-   realized volatility
-   regime
-   time features

Checklist:

-   [ ] Document future FreqAI architecture.
-   [ ] Define chronological train/validation/test.
-   [ ] Define walk-forward process.
-   [ ] Define feature versioning.
-   [ ] Define model versioning.
-   [ ] Define artifact metadata/checksum.
-   [ ] Define retraining triggers.
-   [ ] Define anti-leakage checks.
-   [ ] Define champion/challenger ML evaluation.
-   [ ] Mark heavy continuous training as NOT ACTIVE until resources
    allow.
-   [ ] Define retraining windows, initially night-only.
-   [ ] Define shadow-mode validation before any live deployment.
-   [ ] Define drift detection and automatic deactivation criteria.

### Definition of Done - Phase 19

-   [ ] `docs/FREQAI.md` provides an implementable upgrade path.
-   [ ] Current runtime does not waste resources pretending to run heavy
    ML.
-   [ ] ML cannot autonomously increase live exposure.

------------------------------------------------------------------------

# PHASE 20 - Monitoring and fail-safe

Monitor:

-   trader process
-   Bybit connectivity
-   last candle freshness
-   CPU/load
-   RAM
-   swap
-   disk
-   Supabase sync
-   outbox depth/age
-   database errors
-   strategy errors

Checklist:

-   [ ] Implement health checks.
-   [ ] Implement stale-market-data guard.
-   [ ] Implement Supabase-offline indicator.
-   [ ] Implement queue-growth warning.
-   [ ] Implement disk warning.
-   [ ] Implement risk-limit alerts.
-   [ ] Define fail-safe no-new-entry states.
-   [ ] Existing positions remain manageable during remote-backend
    outage.
-   [ ] Document recovery procedures.

### Definition of Done - Phase 20

-   [ ] Simulated failures produce safe behavior.
-   [ ] Critical conditions are visible and documented.

------------------------------------------------------------------------

# PHASE 21 - Telegram notifications

Prepare notifications for:

-   started/stopped
-   trade opened/closed
-   SL/TP
-   daily summary
-   critical error
-   Supabase offline
-   queue growing
-   disk warning
-   risk limit reached

Checklist:

-   [ ] Add `.env.example` placeholders.
-   [ ] Do not commit token/chat ID.
-   [ ] Implement rate-conscious notifications.
-   [ ] Avoid secret leakage.
-   [ ] Test with mocks unless credentials are explicitly supplied.

### Definition of Done - Phase 21

-   [ ] Notification subsystem is optional and cannot break trading
    runtime.

------------------------------------------------------------------------

# PHASE 22 - Disk policy, log rotation and guard

Classify:

**Critical** - configs - strategies - trade metadata - pending outbox -
important model/experiment metadata

**Reproducible** - candles - downloaded market history

**Temporary** - cache - debug logs - failed experiment artifacts -
temporary backtests

Checklist:

-   [ ] Configure bounded log rotation/compression.
-   [ ] Define disk thresholds.
-   [ ] `<70%` normal.
-   [ ] `70-80%` warning.
-   [ ] `80-90%` clean only safe temp/reproducible data.
-   [ ] `>90%` stop research and emit critical warning.
-   [ ] Never auto-delete critical data.
-   [ ] Test cleanup on safe synthetic data.

### Definition of Done - Phase 22

-   [ ] Logs cannot grow without bound.
-   [ ] Disk guard never deletes critical state.
-   [ ] Research stops before filesystem exhaustion.

------------------------------------------------------------------------

# PHASE 23 - Backup and restore

Local backup should remain compact because durable research state is in
Supabase.

Include:

-   configs
-   strategies
-   critical local state
-   pending outbox
-   migration metadata

Checklist:

-   [ ] Create backup command/script.
-   [ ] Timestamp archive.
-   [ ] Compress.
-   [ ] Generate checksum.
-   [ ] Verify archive after creation.
-   [ ] Create restore command/script.
-   [ ] Restore into controlled test location.
-   [ ] Verify restored contents.
-   [ ] Document `docs/BACKUP_RESTORE.md`.
-   [ ] Do not include huge candle cache by default.

### Definition of Done - Phase 23

-   [ ] A backup has been created and verified.
-   [ ] A restore test has succeeded.

------------------------------------------------------------------------

# PHASE 24 - Migration to stronger VPS

Target workflow:

Old VPS: 1. stop research 2. gracefully stop trader 3. flush Supabase
queue 4. create compact export

New VPS: 1. clone repo 2. restore secrets securely 3. install runtime 4.
import critical state 5. reconnect Supabase 6. re-download reproducible
market data 7. start dry-run 8. verify health

Checklist:

-   [ ] Create `docs/MIGRATION.md`.
-   [ ] Create export/import tooling.
-   [ ] Exclude bulk reproducible candles by default.
-   [ ] Verify archive checksum.
-   [ ] Document handling of IP-whitelisted Bybit keys for future real
    trading.
-   [ ] Test export locally without destructive migration.

### Definition of Done - Phase 24

-   [ ] Compact migration package can be produced.
-   [ ] Migration procedure does not depend on copying the entire 20 GB
    disk.

------------------------------------------------------------------------

# PHASE 25 - Reboot/crash recovery

-   [ ] Define startup order.
-   [ ] Trader starts before research.
-   [ ] Heavy research does not auto-start during constrained recovery.
-   [ ] Test process crash.
-   [ ] Test controlled service restart.
-   [ ] Test server reboot only if safe for existing VPS services.
-   [ ] Verify outbox recovery.
-   [ ] Verify local state.
-   [ ] Verify no duplicate trades/events.

### Definition of Done - Phase 25

-   [ ] CryptoForge recovers safely without requiring manual database
    repair.
-   [ ] Existing VPS services remain healthy.

------------------------------------------------------------------------

# PHASE 26 - Security audit

-   [ ] Search working tree for secrets.
-   [ ] Inspect Git status/history as appropriate for accidental
    secrets.
-   [ ] Check `.env` permissions.
-   [ ] Check listening ports.
-   [ ] Check container exposure.
-   [ ] Check admin/API exposure.
-   [ ] Check logs for secrets.
-   [ ] Check Supabase privileged key handling.
-   [ ] Review RLS if applicable.
-   [ ] Confirm Bybit withdrawal permission is never required.
-   [ ] Confirm real trading remains disabled.
-   [ ] Confirm Futures/leverage remain disabled.

### Definition of Done - Phase 26

-   [ ] No known plaintext secret is committed/exposed.
-   [ ] No unnecessary public administrative endpoint exists.

------------------------------------------------------------------------

# PHASE 27 - Quant audit

Explicitly inspect:

-   [ ] Lookahead bias.
-   [ ] Data leakage.
-   [ ] Future candles.
-   [ ] Incorrect indicator shifting.
-   [ ] Unrealistic fills.
-   [ ] Fees.
-   [ ] Spread assumptions.
-   [ ] Minimum order sizes.
-   [ ] Precision.
-   [ ] Selection bias.
-   [ ] Hyperparameter overfitting.
-   [ ] Insufficient trade count.
-   [ ] Chronological split.
-   [ ] Out-of-sample separation.
-   [ ] Walk-forward methodology.

### Definition of Done - Phase 27

-   [ ] Findings are documented.
-   [ ] Blocking quant flaws are fixed before claiming strategy
    validity.

------------------------------------------------------------------------

# PHASE 28 - Resource audit

Measure actual:

-   [ ] Trader RAM.
-   [ ] Total CryptoForge RAM.
-   [ ] Swap usage.
-   [ ] Idle CPU.
-   [ ] Scanner CPU.
-   [ ] Light backtest CPU/RAM.
-   [ ] Disk footprint.
-   [ ] Outbox footprint.
-   [ ] Log growth.
-   [ ] Supabase sync behavior.

Record results in `FINAL_AUDIT.md`.

### Definition of Done - Phase 28

-   [ ] Resource measurements are real, not estimates.
-   [ ] Current VPS limitations are explicit.
-   [ ] Upgrade triggers are documented.

------------------------------------------------------------------------

# PHASE 29 - Code-quality audit

Search for:

-   [ ] `TODO`
-   [ ] `FIXME`
-   [ ] `pass`
-   [ ] `NotImplemented`
-   [ ] stubs/placeholders
-   [ ] production mocks
-   [ ] hardcoded secrets
-   [ ] broad/empty exception handling
-   [ ] disabled tests
-   [ ] dead code
-   [ ] unsafe defaults
-   [ ] unbounded loops
-   [ ] unbounded storage
-   [ ] accidental `dry_run=false`

### Definition of Done - Phase 29

-   [ ] Every relevant finding is fixed or explicitly documented as
    technical debt.

------------------------------------------------------------------------

# PHASE 30 - Final end-to-end audit

Create `FINAL_AUDIT.md` with:

-   Executive Summary
-   Working
-   Partially Working
-   Not Implemented
-   Test Results
-   Resource Usage
-   Security
-   Bybit Integration
-   Supabase Integration
-   Outbox/Data Integrity
-   Risk Management
-   Market Scanner
-   Market Regime
-   Baseline Strategy
-   Backtest Quality
-   Strategy Lab
-   FreqAI Status
-   Known Limitations
-   Technical Debt
-   VPS Bottlenecks
-   Migration Readiness
-   What Changes After 2 CPU / 8 GB Upgrade
-   Next Phase

Final checklist:

-   [ ] Bybit public data works.
-   [ ] Market Scanner works.
-   [ ] Market Regime works.
-   [ ] Baseline strategy works.
-   [ ] Independent Risk Engine works.
-   [ ] Freqtrade dry-run works.
-   [ ] Trade Journal works.
-   [ ] Supabase sync works.
-   [ ] Local outbox works through outage/recovery.
-   [ ] Monitoring/fail-safe works.
-   [ ] Backup and tested restore work.
-   [ ] Migration export is ready.
-   [ ] Real trading is still disabled.
-   [ ] Futures are still disabled.
-   [ ] Leverage is still disabled.
-   [ ] Heavy FreqAI is honestly marked inactive if not running.
-   [ ] `FINAL_AUDIT.md` accurately distinguishes working/partial/not
    implemented.

------------------------------------------------------------------------

# PHASE 31 - Controlled autonomous live trading pilot

This phase supports the revised long-term objective: autonomous daytime
trading and nighttime learning. It may begin only after Phase 30 is
complete and no blocking security, quant, risk, backup, restore,
monitoring or resource audit item remains open.

Live trading scope for the first pilot:

-   [ ] Bybit only.
-   [ ] Spot only.
-   [ ] Dedicated sub-account only.
-   [ ] No withdrawal permission.
-   [ ] No futures.
-   [ ] No margin.
-   [ ] No leverage.
-   [ ] No martingale or martingale-like recovery logic.
-   [ ] IP-whitelisted API key where feasible.
-   [ ] Small capital allocation chosen explicitly by the user.

Pre-live checklist:

-   [ ] Confirm `.env` and VPS secrets are set with least privilege.
-   [ ] Confirm `dry_run=false` is impossible without an explicit live
    config file and explicit operator command.
-   [ ] Create separate live config; do not mutate dry-run config.
-   [ ] Verify live config has Spot only.
-   [ ] Verify live config has no leverage/futures/margin settings.
-   [ ] Verify withdrawal permission is absent.
-   [ ] Verify kill switch.
-   [ ] Verify no-new-entry switch.
-   [ ] Verify daily loss guard.
-   [ ] Verify max drawdown guard.
-   [ ] Verify max position size.
-   [ ] Verify max simultaneous positions.
-   [ ] Verify minimum order/precision handling.
-   [ ] Verify monitoring alerts.
-   [ ] Verify backup/restore immediately before live start.
-   [ ] Verify current VPS resources are sufficient or migrate first.

Autonomous day mode:

-   [ ] Run only approved live strategies.
-   [ ] Monitor strategy health.
-   [ ] Pause strategy after configured abnormal loss/drift/error.
-   [ ] Never edit live strategy code in place while positions are open.
-   [ ] Persist all decisions and trade context.
-   [ ] Keep user-visible daily summary.

Autonomous night mode:

-   [ ] Stop or avoid resource-heavy jobs if trading runtime is active
    and constrained.
-   [ ] Run bounded backtests/research.
-   [ ] Compare candidates against champion.
-   [ ] Produce candidate recommendations.
-   [ ] Promote only through configured gates.
-   [ ] Deploy first to shadow/paper mode.

Objective:

-   [ ] Optimize for risk-adjusted capital growth.
-   [ ] Penalize drawdown, instability, illiquidity and excessive
    turnover.
-   [ ] Reject strategies optimized only for maximum historical profit.
-   [ ] Reject strategies that seek "fastest money" by violating risk
    limits.

### Definition of Done - Phase 31

-   [ ] First live pilot trades only on a dedicated limited sub-account.
-   [ ] All live trades are explainable from stored strategy/risk state.
-   [ ] A live kill switch works.
-   [ ] Daily/night cycle works without starving the VPS.
-   [ ] Strategy learning improves recommendations without bypassing
    risk gates.
-   [ ] Live performance is reviewed against paper expectations.

------------------------------------------------------------------------

# Progress rules for Codex

For every phase:

1.  **Inspect**
2.  **Plan**
3.  **Implement**
4.  **Test**
5.  **Review**
6.  **Fix**
7.  **Document**
8.  **Update this checklist**
9.  **Commit logically related changes when appropriate**
10. **Only then continue**

Do not use successful command exit status as the sole proof of
completion.

If a blocking test fails: - keep the checkbox unchecked; - diagnose
it; - fix it; - retest; - document the result.

If a requirement cannot safely be implemented on the current VPS: - do
not fake it; - mark it clearly as deferred; - explain the constraint; -
preserve the architecture needed for the later 2+ CPU / 8+ GB VPS.

## Priority order

1.  Safety
2.  Existing VPS services
3.  Risk protection
4.  Trading runtime stability
5.  Data integrity
6.  Security
7.  Bybit connectivity
8.  Supabase persistence
9.  Monitoring
10. Research
11. ML
12. UI

------------------------------------------------------------------------

# Decision Log

Codex must append entries here when deviating from the plan.

Template:

``` text
## YYYY-MM-DD - Decision title

Phase:
Decision:
Reason:
Alternatives considered:
Risk/impact:
Verification:
Follow-up:
```

Do not delete previous decisions.

## 2026-09-25 - Revised autonomous trading objective

Phase:
Global planning / future Phase 31.
Decision:
Added a future controlled autonomous live-trading pilot with day trading
and night research, while keeping current implementation dry-run until
all pre-live gates pass.
Reason:
The user explicitly changed the long-term product objective: the bot
should eventually trade autonomously during the day, learn/research at
night, evaluate what worked, edit or prepare strategies, and improve
over time.
Alternatives considered:
Immediately enabling live trading; rewriting the plan around maximum
short-term profit; keeping the original dry-run-only endpoint.
Risk/impact:
Immediate live trading and unbounded "fastest money" optimization were
rejected as unsafe. The plan now supports autonomous live trading only
through a dedicated limited sub-account, hard risk gates, no withdrawal
permission, Spot-only first pilot, and explicit audit requirements.
Verification:
Added `docs/AUTONOMOUS_TRADING_POLICY.md`, future operating-model rules,
day/night Strategy Lab requirements, FreqAI retraining gates, and Phase
31 controlled-live checklist.
Follow-up:
Continue building the current dry-run, risk, persistence, monitoring and
audit phases before any live pilot.

## 2026-09-25 - TypeSafe document evaluation CLI

Phase:
Out-of-order user-requested utility work after Phase 4.
Decision:
Implemented a standalone TypeSafe-powered CLI for evaluating supplied
documents across configurable Score dimensions before continuing to
Phase 5.
Reason:
The user explicitly requested this CLI and asked to use the installed
TypeSafe skill.
Alternatives considered:
Deferring until later Strategy Lab phases, or building a hardcoded
one-off script.
Risk/impact:
No trading runtime behavior changed. The CLI is optional, requires
`TYPESAFE_API_KEY`, and stores no secrets.
Verification:
Added unit tests with a fake TypeSafe client, validated CLI help and
missing-key behavior, and ran the non-integration test suite.
Follow-up:
Continue the main CryptoForge plan from Phase 5 unless the user asks for
more TypeSafe CLI refinements.

## 2026-09-25 - Portable Supabase schema migration

Phase:
Phase 5 - Supabase persistent backend.
Decision:
Authored the initial Supabase schema as a SQL migration in Git and made
client-role revokes conditional so the migration works in Supabase and
can also be verified against a clean local PostgreSQL instance.
Reason:
Supabase project credentials are not configured locally yet, but Phase 5
requires a reproducible schema and documented persistence boundaries.
Local PostgreSQL does not define Supabase roles such as `anon` and
`authenticated` by default.
Alternatives considered:
Waiting for live Supabase credentials; creating Supabase roles in local
test databases; writing docs without a migration.
Risk/impact:
No production database was modified. The migration keeps RLS enabled and
still revokes access from Supabase client roles when they exist.
Verification:
Applied the migration successfully with `pg_virtualenv psql`, added
schema tests, and ran the non-integration test suite.
Follow-up:
When Supabase credentials are added, apply the migration to the real
project through the Supabase workflow and verify remote table/RLS state.
