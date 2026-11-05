# Future FreqAI Architecture

Current distinction (2026-10-14): own lightweight trainers/registry and prospective
collectors are implemented. Heavy FreqAI integration remains inactive. Neither
status establishes independent profitability. See
[implementation reconciliation](IMPLEMENTATION_RECONCILIATION_20261014.md).

FreqAI is **NOT ACTIVE** in the current runtime. CryptoForge does not spend
CPU/RAM pretending to train heavy ML on the current 1 vCPU / 1 GB VPS.
This document defines the upgrade path for a later resource-approved
phase.

## Candidate Model Families

Initial candidates:

- LightGBM
- XGBoost
- CatBoost

These are future options only. Continuous heavy training is **NOT
ACTIVE** until hardware, monitoring and validation gates explicitly allow
it.

## Feature Set

Candidate feature families:

- returns
- ATR
- RSI
- ADX
- EMA distances
- MACD
- Bollinger width
- VWAP distance
- volume and volume anomaly
- momentum
- realized volatility
- market regime
- time features

Every feature set receives a `feature_version`. Feature definitions must
be deterministic and calculated using only data available at prediction
time.

## Chronological Splits

ML experiments must use chronological splits:

```text
train -> validation -> test
```

No shuffled time-series splits. No feature normalization fitted on
future validation/test data. No target leakage from future candles,
future volume, future order outcomes or final trade labels.

## Walk-Forward Process

Walk-forward validation should use repeated windows:

```text
train[a:b] -> validate[b:c] -> test[c:d]
train[b:c] -> validate[c:d] -> test[d:e]
...
```

Each window stores:

- dataset ID;
- train/validation/test ranges;
- feature version;
- model version;
- parameters;
- metrics;
- artifact URI and checksum.

## Versioning

Model version format:

```text
{model_family}-{feature_version}-{yyyymmdd}-{short_hash}
```

Artifact metadata:

- model family;
- model version;
- feature version;
- train/validation/test ranges;
- parameter hash;
- artifact URI;
- SHA-256 checksum;
- metrics payload;
- creation time;
- producing Git commit.

Artifacts belong in object storage, not PostgreSQL BYTEA. PostgreSQL
stores metadata and checksums.

## Retraining Triggers

Retraining may be queued when:

- paper/live performance drifts below expected range;
- regime mix changes materially;
- data freshness or liquidity profile changes;
- model age exceeds configured window;
- champion/challenger review requests a new candidate.

Initial retraining window: night-only, and only when Strategy Lab
resource gates pass.

## Anti-Leakage Checks

Required checks:

- chronological train/validation/test split;
- no negative shifts;
- no centered rolling windows;
- no `.iloc[-1]` full-dataframe leakage in strategy code;
- feature scalers fitted only on training data;
- labels aligned strictly after feature timestamps;
- walk-forward windows do not overlap improperly;
- final test data not used for parameter selection.

## Champion / Challenger ML Evaluation

ML candidates must beat the champion on:

- out-of-sample metrics;
- walk-forward metrics;
- regime-specific metrics;
- drawdown;
- profit factor;
- expectancy;
- Sharpe/Sortino;
- adequate trade count and stability.

Absolute historical profit is insufficient.

## Shadow Mode Before Deployment

Every ML strategy first runs in shadow or paper mode. It records
predictions, features, confidence and suggested actions without live
execution. Promotion can only proceed through lifecycle gates and human
live approval boundaries.

The Supabase-backed executor supports three explicit modes:

- `off`: do not load the active model;
- `shadow` (default): load the latest `model.active` event, verify the embedded
  artifact checksum and freshness, and record probability without changing the
  conventional strategy decision;
- `gate`: after the conventional entry signal passes, reject entry when the
  fresh compatible model probability is below the configured threshold.

In `gate`, missing, stale, corrupt, unreachable or feature-incompatible models
block new entries; shadow can continue conventional entry evaluation. Model
registry failures do not prevent the existing position-exit path.
Runtime snapshot on 7 October 2026 records the systemd executor in `gate` with
threshold `0.50`, live flag set, stake 6 USDT and max positions 6. This is a
read-only snapshot of existing settings, not approval of model profitability.
Re-check runtime rather than relying on this dated snapshot.

## Drift And Deactivation

Automatic deactivation criteria:

- daily loss or drawdown guard breach;
- prediction distribution drift;
- feature distribution drift;
- actual performance diverges from paper expectation;
- stale data or missing features;
- outbox/monitoring failure beyond fail-safe threshold.

Deactivation means no new entries. Existing positions remain managed by
runtime/risk rules.

## Exposure Boundary

ML cannot autonomously increase live exposure, edit hard risk limits,
enable leverage, enable futures/margin, enable withdrawals, or deploy
itself to live trading. Any such change requires a separate audited plan
revision and explicit human approval.

## Lightweight model promotion

Training saves every run, but emits `model.active` only after a quality screen;
rejected runs emit `model.candidate` and leave the registry unchanged. Split
boundaries group equal timestamps and purge labels extending into the next split.
The common comparison set must be later than both models' training labels
(legacy artifacts conservatively use their training timestamp). At least 200
unseen examples and 30 candidate signals are required. The candidate must beat
majority-class accuracy, have positive mean signal return after round-trip costs,
and achieve strictly better net return per example without worse accuracy than
the incumbent. Registry errors abort publication rather than bypassing the screen.

`--round-trip-cost` defaults to 0.003 (0.2% round-trip fees plus 0.1% slippage).
`--min-label-return` defaults to the same value, so long and short heads are
trained only on moves large enough to clear the assumed round-trip cost. Smaller
future moves remain negative examples for both directions instead of teaching the
model to chase noise.
This is an assumed signal-level screen, not a portfolio backtest: signals can
overlap and actual fees, fills, exits, and capital constraints differ. Promotion
is not evidence of statistically significant or realized profitability. No
existing model is automatically rolled back or trading configuration changed.

## Bounded strategy discovery and regularization

The hourly night-research runner now stores `strategy_experiments` in its existing
report event. It searches 18 Spot-only variants: reversion (RSI 35/45 with a
bounce), breakout (volume multiplier 1/1.5), and trend (3-bar return 0.1%/0.3%),
each with 3/6/12-bar holding periods. These experiments do not change live pair
selection, executor strategies, stakes, or risk limits.

Each pair uses the first 70% of candles for selection; only that winner is checked
on the last 30%. Entry and exit use subsequent candle opens, with one position
per pair and no overlapping positions. Costs default to 0.3% round-trip; the
holdout must also remain positive at double costs and in both halves, have at
least 10 trades, and drawdown <=5%. Passing means candidate for paper research,
never permission for live trading. Reports retain all selection trials and the
winner's holdout metrics. Gap-containing histories are rejected. OHLC simulation
cannot account for order book depth, exact fills, and intrabar drawdown; current
short histories and repeatedly reused holdouts need longer forward paper
validation before any deployment decision.

The long logistic head now searches L2 values 0/0.01/0.1 using validation log loss.
The chosen weights, L2, and search metrics are saved in the artifact. Test data
never selects the regularization. Changing the target-return threshold does not
relax exclusion of data seen by the incumbent.

## Historical archive experiments

Bybit Spot history can be downloaded locally without duplicating it in the live
Supabase database:

```sh
PYTHONPATH=src .venv/bin/python scripts/download_market_archive.py --pair BTC/USDT --pair ETH/USDT --days 90 --interval 5
PYTHONPATH=src .venv/bin/python scripts/train_archive_model.py --pair BTC/USDT --pair ETH/USDT --timeframe 5m --max-candles 26000 --epochs 50
```

Downloads paginate backward in batches of 1000, save atomically after each page,
reuse cached complete ranges, exclude unclosed candles, and report missing
candles. History availability depends on a symbol's listing and Bybit's retained
data. Training refuses gaps and writes an offline model with chronological
70/15/15 splits and purged label boundaries to `.local/archive/models`. Artifacts
record the actual train/validation/test boundaries and never publish `model.active`.
The feature builder computes EMA prefixes once and only uses bounded windows for
other features, preserving the same values without quadratic history processing.
For production use, archive experiments still need forward paper validation and
comparison against the current champion; changing universe membership can create
survivorship bias. The scheduled live trainer continues using its existing data
source; archive experiments are a separate explicit command.

## Short Shadow Outcome Checklist

Short research remains shadow-only. Live Spot execution must not open margin,
futures or borrowed-asset shorts.

Implementation checklist:

- `trade_decisions.reasons` records `short_shadow_signal`, `short_emerging_momentum`
  and `ml_short_probability` for every evaluated pair.
- `scripts/evaluate_short_shadow.py` reads those decisions, waits until at least
  12 later 5m candles exist, computes virtual short outcomes at 3/6/12 candles,
  max favorable excursion and max adverse excursion, then writes
  `research.short_shadow_outcomes` to `system_events`.
- The analyzer uses existing Supabase tables only; no schema migration is needed.
- A useful short candidate should improve `probability_ge_0_5.mean_return_12`
  and `signaled.mean_return_12` after costs before any threshold is tightened.
- Live-short remains blocked until a separate derivatives plan exists.

Manual verification:

```sh
set -a; source .env; set +a
PYTHONPATH=src .venv/bin/python scripts/evaluate_short_shadow.py --lookback-hours 24 --limit 500
```

Review checklist:

- [x] Version 2 excludes unclosed candles and counts missing first or intermediate
  5m candles as `gaps`, separately from `pending`.
- [x] Gross returns remain available; `net_return_3/6/12`, `net_win_rate` and
  `mean_net_return_12` subtract an assumed round-trip cost (default 0.003).
  Override with `--round-trip-cost`. Borrowing and funding costs are not modeled.
- [ ] Compare net results over different days and pairs with a baseline.
- [ ] Tune short features and thresholds on validation and evaluate on untouched test data.
- [ ] Confirm improvement with forward paper observations before promotion.

- `candidate_count` is nonzero.
- `pending` is low enough that most candidates have 12 future candles.
- `signaled.count` and `probability_ge_0_5.count` are large enough to matter.
- `mean_return_12` is positive after repeated runs, not just one sample.
  Use `mean_net_return_12` for evaluation after assumed costs.
- `mean_max_adverse` is acceptable relative to the expected take-profit/stop.


## Complete information boundaries

New artifacts record `fit_information_end` (train plus validation used for L2 selection)
and `evaluation_information_end` (test used for acceptance). Promotion compares only
examples strictly later than all known candidate/incumbent boundaries. Changing
labels cannot bypass the cutoff. Legacy artifacts without complete boundaries also
use their publication timestamp conservatively; invalid boundaries reject promotion.
The draft research protocol is `config/research-protocol-v1.json`; it does not change
runtime or risk settings until explicitly integrated and frozen.


## Trade-outcome Spot-long labels

`trade_labels.py` generates `spot-long-trade-net-v2` labels with the shared offline
simulator. Positive means net PnL > 0 after configured costs; refused execution is
not a negative example. Complete horizons only; label availability is after the
exit candle closes. Independent hypothetical trades can overlap and are not
portfolio returns. The offline training script evaluates selected test signals
again with one shared wallet and writes artifacts with `live_eligible=false`.
No short target is simulated and short-head fields are excluded from its artifact.

```sh
PYTHONPATH=src .venv/bin/python scripts/train_trade_outcome_model.py --pair BTC/USDT --pair ETH/USDT --max-candles 5000 --epochs 30
```

These experiments are development replays, not independent walk-forward proof or
permission to replace the active model. The full historical trade-label audit,
MFE/MAE, regression targets and extended features remain planned.


## Development label audit and validation-only search

The audit independently recomputes selected historical outcomes on the first 70%
of development history and saves per-pair class/exit/month counts plus checksum.
The bounded search pre-records 18 rule/exit variants, evaluates the next 15% with
one wallet and stress costs, and never evaluates the outer final 15%. Results
are for further research only; repeated validation reuse is not independent proof.

```sh
PYTHONPATH=src .venv/bin/python scripts/audit_trade_labels.py --pair BTC/USDT --pair ETH/USDT
PYTHONPATH=src .venv/bin/python scripts/search_validation_portfolio.py --pair BTC/USDT --pair ETH/USDT
```


## Stage 1 archive quality

Archive downloads support intervals 1/5/15/60, strict closed OHLCV validation,
fixed timezone-aware `--start/--end`, immutable range snapshots and checksums.
Use the staging directory; the previously frozen archive must stay unchanged.

```sh
PYTHONPATH=src .venv/bin/python scripts/download_market_archive.py --pair BTC/USDT --interval 1 --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z --directory .local/archive-stage1
PYTHONPATH=src .venv/bin/python scripts/verify_archive_source.py
```

Quality checks include exact comparison of minute→5m→hour aggregation against
Bybit. Current online instrument metadata is a timestamped snapshot and cannot
be used as historical membership/rules. Long-history coverage and point-in-time
universe remain incomplete. Sources: [Kline API](https://bybit-exchange.github.io/docs/v5/market/kline),
[online instrument specifications](https://bybit-exchange.github.io/docs/v5/market/instrument),
[server error codes](https://bybit-exchange.github.io/docs/v5/error).


## Streaming long-range archive

Long ranges use `.local/archive-stage1/history.sqlite`, decimal TEXT columns and
page transactions. Range manifests checksum canonical ordered JSON lines of rows,
not the mutable SQLite file. Incomplete/changed ranges are rejected by the reader.
`download_long_archive.py` resumes cached pages and enforces a 2 GiB disk reserve.
`verify_long_archive.py` compares three dates per pair with Bybit and records
previous-day liquidity membership within the fixed basket. This does not recover
delisted pairs or historical instrument filters and is not a whole-market universe.

```sh
PYTHONPATH=src .venv/bin/python scripts/download_long_archive.py --pair BTC/USDT --start 2025-10-01T00:00:00Z --end 2026-10-01T00:00:00Z
PYTHONPATH=src .venv/bin/python scripts/verify_long_archive.py
```

Stage-1 data is not part of frozen protocol v1 and is not automatically passed to
training or the live executor.


Stage-1 completion evidence (7 October 2026): ten fixed pairs have 105120 closed
5m candles each over 2025-10-01 through 2026-10-01 UTC, no gaps (1051200 total).
SQLite occupies ~83.42 MiB; observed live loader HWM ~31.13 MiB. Range checksums
and three source dates per pair were verified. 3650 previous-day membership
records remain scoped to the survivor basket, with historical filters unknown.
The stage is still open for full historical universe/instrument-rule evidence.


## Partial historical instrument evidence

`instrument_history.py` models dated official global Spot events with source
checksums and announced/effective timestamps. `build_instrument_history.py`
imports reviewed facts from captured announcement HTML; unknown steps and absent
rule changes remain unknown. EU and derivatives are rejected. Original publication
metadata does not prove a historical revision snapshot; execution certification
stays false. Date-only publication is conservatively bounded by the next day.

Delisted history is available in `.local/archive-stage1/delisted.sqlite`. Missing
terminal candles are explicit; `continuous_segments` exposes valid subranges
without inventing data. Progress files are now keyed by DB stem. The official
source inventory contains candidates for review, never automatically inferred
listing/rule facts. None of this data alters live trading or frozen protocol v1.

```sh
PYTHONPATH=src .venv/bin/python scripts/build_instrument_history.py
PYTHONPATH=src .venv/bin/python scripts/inventory_historical_sources.py
```


## Source review queue and venue isolation

`review_historical_sources.py` captures metadata/body/checksum for each discovered
URL and distinguishes Spot candidates, unknown body/market, derivatives and EU.
A global `/en/` URL does not prove the announcement concerns Bybit global:
content mentioning Bybit EU is excluded. Sources remain pending event review
until exact fields and effective times have been curated.

The reviewed April 1, 2026 notice adds AVAX/LINK tick changes (0.001 after the
effective time) to the partial registry. Previous tick values are not backdated
to an unproven baseline. The 89-source linkmap inventory lacks May–September 2026
publication coverage; complete annual rule/membership reconstruction is still open.

```sh
PYTHONPATH=src .venv/bin/python scripts/review_historical_sources.py
```


## Calendar source coverage extension

The linkmap gap was supplemented by paginated official category indexes.
`inventory_announcement_categories.py` records page IDs/date boundaries and stops
after crossing the study start, with checkpoint resume and repeated-page checks.
The combined 140 candidates now span all 12 study months. This is calendar
coverage, not proof of complete historic rule changes or page revisions.

Reviewed DOT tick changes (June 26) and four September Spot delistings extend the
partial instrument registry to 34 events. Pre-change tick values are not backdated
to unknown baseline periods. Historical quantity steps and exhaustive universe
coverage remain open; stage 1 is not complete.

```sh
PYTHONPATH=src .venv/bin/python scripts/inventory_announcement_categories.py
PYTHONPATH=src .venv/bin/python scripts/review_historical_sources.py
```


## Execution feedback for training

The live-feedback reader audits execution-backed FIFO records grouped by exit
order and joins decisions by exact order ID. `realized_pnl` is already net; fees
are informational and are never subtracted again. Missing context is explicit.
Actual orders now retain their own idempotency keys and as-of features. The new
30-minute feedback service writes a local report only, without sending messages.

The production training CLI injects the feedback reader. Candidate cost estimates
use only executions completed by the train label boundary; validation/test do
not calibrate fees. With enough prior orders, the floor is observed median fee
drag plus 0.1% assumed slippage. Feedback failure makes the run a candidate only.
Fee/horizon patterns are hypotheses for paper comparison, never automatic changes
to hard stops, stakes or the live gate.

```sh
set -a; source .env; set +a
PYTHONPATH=src .venv/bin/python scripts/analyze_live_feedback.py
bash deploy/install_local_live_feedback.sh
```


Проверка расширенного годового архива выполняется отдельно от frozen v1:

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_historical_universe.py
PYTHONPATH=src .venv/bin/python scripts/verify_long_archive.py \
  --database .local/archive-stage1/historical-universe-20251001.sqlite \
  --output .local/state/historical-universe-year-quality.json \
  --reuse-report .local/state/long-archive-quality.json
```

Первая команда воспроизводит отбор top20 только из prior-day evidence и датированного baseline. Вторая проверяет полные диапазоны/manifest SHA и прямые source samples; reuse допустим только при точном совпадении logical SHA. Недоступные источники исключены явно. Начальный состав — частичный исторический baseline, не полный состав биржи.

С 2026-10-08 00:00 UTC reserved final period нельзя использовать для подбора параметров frozen исследования. Операционный live feedback продолжает собираться; обучение по его новым outcomes делает этот период непригодным в качестве независимого финального теста такой модели.


Cost calibration в training CLI проходит через `ObservedFeedbackReader`: комиссия сделки доступна только после фактического наблюдения verified версии в `.local/state/feedback-memory.sqlite`. Поздние accounting corrections не попадают в старые train windows, даже если сама сделка закрылась раньше. При отсутствии памяти ретроспективный журнал не используется для восстановления старых fee assumptions. Current accounting health также проверяется.


Проверить реальные пробелы execution rules для исторической корзины:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_historical_execution_rules.py
```

Отчёт `.local/state/historical-execution-coverage.json` проверяет source/semantic SHA и разделяет last documented numeric values, известную недоступность и полную историческую сертификацию. Последняя остаётся false даже при наличии всех чисел: полный change/revision history не доказан. Current instrument snapshots в `trade_decisions.features.instrument_snapshot` относятся только к моменту чтения, не к прошлым свечам.

`collect_live_experiences.py` запускать после `analyze_live_feedback.py` (таймер выполняет именно такой порядок). Для обучения допускается только свежий, не старше пяти минут, independently reconciled accounting snapshot. Cutoff source отличается от времени наблюдения label; позднее полное закрытие не делает старое partial window зрелым.

Динамические поля лимитов сохраняются раздельно и без допущения о постоянстве: [Bybit Instruments Info](https://bybit-exchange.github.io/docs/v5/market/instrument).


Для позиций с маленьким непродаваемым остатком добавлен отдельный экспериментальный dataset `.local/state/cash-recovery-dataset.json`, target `spot-long-real-cash-recovery-dust-zero-v1`. Это cash recovery с residual inventory at zero, не fully-closed net PnL. Residual basis вычитается один раз из net closing PnL; actual inventory остаётся на бирже. Cap residual basis=1% full acquisition cost; свежие публичные instrument/quote данные определяют, подходит ли остаток для market sell. Material/sellable remainder не становится отрицательной меткой.

```bash
# После свежего analyze_live_feedback.py и загрузки обычного .env:
PYTHONPATH=src .venv/bin/python scripts/collect_cash_recovery.py
```

Таймер выполняет шаг автоматически после independent audit и ordinary fully-closed collector. Both collectors сопоставляют closing basis/PnL и original features с конкретным verified audit, не только его health flag. Experimental memory хранит first observation и отдельные версии исправлений; повторный запуск не создаёт новые покупки.

Cash-recovery target и input candle state должны проверяться отдельно от fixed-future-return и closed-only модельного контракта. Current four legacy intrabar примера — development data, недостаточные для fit/promotion. Автоматическое обучение/допуск такого кандидата не включены; protocol достаточной выборки и отдельное будущее paper окно ещё нужно зафиксировать.


Для реальных cash-recovery примеров заморожен `config/live-cash-recovery-protocol-v1.json` + SHA-256. Он определяет input contract, minimum sample/diversity, fixed future windows и 24h embargo. Четыре уже просмотренные покупки закреплены training-only по identity, включая будущие исправления. Independent test не выбирает L2/threshold/windows.

```bash
PYTHONPATH=src .venv/bin/python scripts/check_live_learning_readiness.py
```

Результат `.local/state/live-learning-readiness.json` формируется по таймеру после collectors. Отдельные as-of snapshots предотвращают перенос поздних исправлений в старый train cutoff; duplicate buy identities/несовместимые input states блокируются. Test/paper labels не входят в readiness statistics. Fresh timestamp не компенсирует truncation, source binding mismatch или missing public observations.

Instrument/quote collector использует два общих публичных Spot GET, а не исключает пары после первых двадцати по алфавиту. Для каждой нужной пары сохранена projection evidence; missing identities не заполняются параметрами другой монеты. Old rows вне текущего audit lookback не считаются новой ошибкой source reconciliation.

Data readiness не даёт live допуска: automatic_training_allowed/live_promotion_allowed=false. Candidate paper harness и performance acceptance gates ещё требуется реализовать; обычные живые сделки не выдаются за независимые бумажные сделки кандидата.


Prospective cash shadow foundation подключён в executor, но inert без пригодного frozen candidate. После будущего завершения train/validation локальный artifact можно зарегистрировать:

```bash
PYTHONPATH=src .venv/bin/python scripts/register_cash_shadow_candidate.py --artifact /absolute/path/to/cash-candidate.json
PYTHONPATH=src .venv/bin/python scripts/report_cash_shadow.py
```

Registration сейчас отвергается из-за недостатка данных/неоконченных окон. Она фиксирует наблюдаемое время, protocol/artifact SHA и один неизменный candidate на protocol. Не публикует model.active.

Forecast записывается до actual Buy request, затем связывается с response order ID/orderLinkId. Его нельзя переписать после исхода или вставить с прошлой датой через обычный recorder. Observer errors не меняют baseline trade/risk decisions. Report `.local/state/cash-shadow-report.json` создаётся по таймеру; rewards закрыты до завершения окна.

Этот механизм сравнивает forecasts на фактически выполненных покупках baseline. Он не симулирует portfolio capital/fills/alternative opportunities и не создаёт paper execution evidence для readiness. Полный paper harness и performance acceptance gates ещё не реализованы; доходность/допуск модели не установлены.


Подготовлено изолированное ядро `paper_wallet.PaperWallet` с явно заданным `PaperConfig`. Оно не содержит exchange order API и не пишет реальные trades. Новая wallet DB получает immutable candidate/policy; реальная или обучающая SQLite DB не допускается в качестве paper ledger.

Интерфейс: `enqueue` → следующая свежая quote после actual enqueue+delay → `execute`; отдельно `mark` для всех held assets. Общий cash, FIFO, base acquisition fee/quote exit fee и residual ownership сохраняются. Missing liquidation marks блокируют новые входы; gross bid value не считается гарантированными proceeds. Fees/slippage и top-book fill остаются заявленными scenario assumptions.

`paper_market.observe_market` нормализует текущий публичный Spot стакан и explicit instrument filters: [Bybit Orderbook API](https://bybit-exchange.github.io/docs/v5/market/orderbook). Не подставляет неизвестные quantity/market limits.

Kernel протестирован, но operational worker/exit dispatcher, frozen paper policy и acceptance gates ещё не подключены. Paper wallet не создаётся автоматически при отсутствии пригодного candidate; текущий report сохраняет full_paper_execution_harness_implemented=false.


Бумажный dispatcher/worker реализован, operational запуск пока отключён. `config/paper-execution-policy-v1.json` — draft_execution_disabled. После будущего qualified candidate и до first eligible paper event policy нужно явно preregister с именованным fee/slippage scenario:

```bash
PYTHONPATH=src .venv/bin/python scripts/freeze_cash_paper_policy.py --cost-assumption-id named-simulation-scenario
PYTHONPATH=src .venv/bin/python scripts/run_cash_paper.py
bash deploy/install_local_cash_paper.sh
```

Сегодня freeze/install не проходят preconditions. Idle run пишет `.local/state/cash-paper-worker-report.json`, без создания wallet/запросов к рынку. Installer до проверки ничего не устанавливает. После допуска запускает отдельный virtual-only user timer с flock; API keys/real order client не используются.

Worker связывает forecast с atomic intent/source state, исполняет на следующей свежей quote и сохраняет исходный expiry. Отдельные exits используют hard stop, max hold и общий exit_signal с current validated market data. Последний день — exit-only. Политика/кандидат неизменны, interrupted write не разрешает новый scenario поверх прежнего теста.

Scope ограничен baseline-approved opportunity stream; это не independent market-wide strategy exploration. Paper dataset exporter и performance acceptance gates ещё нужны. Real cash outcomes, simulated fills и factual shadow cohort остаются разными источниками.


Бумажные результаты отдельно от реального обучения: `PYTHONPATH=src .venv/bin/python scripts/export_cash_paper.py` и `PYTHONPATH=src .venv/bin/python scripts/evaluate_cash_paper.py`. Экспорт читает три изолированных сценария (candidate/baseline/stress); отсутствие wallet не создаёт его. Критерии `config/paper-acceptance-policy-v1.json` зарегистрированы до наблюдения paper. Итог скрыт до завершения окна, simulated labels запрещены для реальной обучающей выборки, live promotion всегда false. Fast paper timer остаётся заблокирован до квалифицированного кандидата и frozen execution policy.


Manual cash candidate fit: `PYTHONPATH=src .venv/bin/python scripts/train_cash_candidate.py`. Команда не подключена к timer и не публикует модель. Требует завершённых квалифицированных train/validation; sealed test/paper не читает. Fit policy фиксирует100 epochs/lr0.08 и все3 preregistered L2, selection по validation log loss, без refit. Один сохранённый fit-report на протокол; повторный запуск восстанавливает только его artifact. Перед регистрацией проверяются исходный receipt и eligible snapshot hashes. Это cohort classifier на реально наблюдавшихся покупках, а не расчёт доходности гипотетического портфеля.


В `spot-long-trade-net-v2` численное поле `future_return` означает net_pnl/cost после модельных комиссий и slippage, согласованное с binary profit label. v1 хранил в этом поле gross price return; старые artifacts требуют отдельной совместимости и не переписываются. Independent development audit проверяет net arithmetic. Архивные проверки и manual cash fit сохраняют reserve памяти/диска для рабочего executor.


Cash collection report включает `collection_coverage`: canonical buy identities, eligible/excluded/awaiting/uncovered/unexplained categories. Unexplained omissions блокируют readiness. Versioned experience memory поддерживает verified withdrawals без удаления старой as-of истории; transient observation failures не отзывают пример. Candidate contract проверяет exact feature order и одинаковый threshold manifest/artifact.


Archive simulation допускает разные entry_fee/exit_fee; None означает прежнее общее fee. `stress_costs(2)` увеличивает обе effective fees и slippage. Числа остаются scenario assumptions. Validation search записывает immutable attempts в `.local/state/research-attempts.sqlite`; один и тот же study восстанавливает завершённые results, ошибки сохраняются, parameter budget связан с protocol/family. Старые reports остаются evidence ранее проведённого development, без backdated registration.


Validation-search budget identity включает execution config и SHA реализации стратегии/симулятора, а не только signal parameters. Cash fit artifact теперь содержит validation-only diagnostic baseline, calibration bins и exact cash recovery/cost sums по factual threshold cohorts. Эти sums не оценивают shared portfolio capital или неизвестные counterfactual fills и не меняют frozen selection rule.


Opt-in development study: `scripts/search_validation_portfolio.py --pair BTC/USDT --pair ETH/USDT --entry-conflict-study`. Проверяет18 paired обычных/no-exit-conflict вариантов (36 portfolios) при общих hold/stop/target. Shared exit indicator получает только прошлые≤120 закрытых свечей. Это исследование из наблюдавшихся live ошибок; прежний historical reserved final не заявляется независимым для новой гипотезы. Рабочий executor и frozen cash training protocol не меняются.


Experimental net diagnostics: `PYTHONPATH=src .venv/bin/python scripts/evaluate_archive_net_head.py` (checksummed separate protocol,3 ridge heads, train/validation only) и `scripts/evaluate_net_portfolio.py` (frozen chosen head/threshold0, shared-capital validation replay). Models use an experimental family/live_eligible=False; no auto registration or publication. Frozen dependency changes require a new fitted study, prior results are retained. Net regression errors and overlapping independent labels do not establish portfolio income.

`walk_forward.py` supplies calendar folds/purged availability and sealed test access; `walk_forward_selection.py` records one actually observed selection before eligible test opportunities. These kernels have no production registry. `closed_timeframes.py` emits complete closed15m/60m observations, and `causal_features.py` emits exact closed candle-v1 features without future targets. Neither changes the active model input state. Offline equity timestamps now reflect candle-close availability; daily block uncertainty excludes partial boundary days and requires at least14 full consecutive days.


Primary training source admission excludes individual malformed/gapped markets but requires at least80% source coverage; network/auth errors remain fatal. Read `artifact_dir/diagnostics/last-source-admission.json`; artifacts contain accepted pairs only. The training timer uses a separate model-training universe file throughout select/sync/fit. New model config declares `feature_lookback_candles` (CLI120, library default36); inference matches it exactly,legacy artifacts follow their original path.

The cache reader explicitly requests Bybit Spot and existing ingested_at metadata. Closed-only filters exclude a cached observation taken before its bar closed,even after wall time advances. Unknown metadata on immutable/legacy fixtures retains the previous temporal rule; this does not certify historical revision availability. Registry checks artifact training age as well as publication age,model family,feature order,metadata consistency and aware information cutoffs; research-only artifacts cannot become active models.


`evaluate_archive_net_tree.py` is a separate3-configuration development-only nonlinear experiment (depth2/3/4,min leaf80),not an active-model backend. `context_features.py` emits a distinct24-feature experimental schema with aligned BTC context and complete closed-hour data;no current model admission supports it. Feature quality audit does not train on outcomes or establish income.


New primary training runs keep original purged inputs in private content-addressed gzip files under `artifact_dir/input-snapshots`, together with copies/hashes of calculation dependencies and Python runtime metadata. These are candle examples, not executed buys. Source changes during fit abort publication; the model artifact is installed atomically. Probability diagnostics report train-only constant baseline log loss/Brier, grouped-tie Average Precision, balanced accuracy, calibration and fixed-threshold activity by split/pair, without changing model selection or the live threshold.

`PYTHONPATH=src .venv/bin/python scripts/audit_primary_training.py --artifact /absolute/path/to/model.json` verifies original inputs, normalization, information boundaries and both heads without refitting or publishing. An optional `--sha256` accepts the full checksum from a registry receipt. Legacy artifacts without original snapshots cannot be audited by rebuilding today's cache. Calculation dependencies must match the recorded version; archived source bundles are retained for review and never automatically executed.

Primary promotion also excludes the latest rejected candidate's evaluated period and carries a monotone `evaluation_history_end`; changing active/candidate evidence during comparison cancels promotion. Incompatible legacy/bounded feature contracts cannot be compared on the same input vectors. This screen remains separate from independent portfolio profitability qualification.

Closed cache observations require bar close <= observation <= snapshot cutoff. Causal EMA and closed-hour context retain late revision availability, and simulated entry decisions reject features observed after entry. Archive metadata without observation times retains a market-close assumption rather than claiming revision-certified history. Separate `spot-long-ohlc-excursion-bounds-v1` targets attach adverse/favorable price and holding-time bounds to simulated trade outcomes; opening exits exclude later bar extremes, intrabar exits expose uncertainty. These outcomes are not entry features or an already trained risk head.


Forward real-cash collection now also has `config/live-cash-recovery-closed-protocol-v1.json`: closed-only inputs with exact bounded120 calculation. Its SHA namespace is separate from the original legacy study. Current counters are legacy8/100 and compatible closed-only0/100, not one combined dataset. The readonly feedback timer updates both readiness and shadow reports. No candidate or paper wallet is activated.

Use `--protocol config/live-cash-recovery-closed-protocol-v1.json` with `check_live_learning_readiness.py`, `train_cash_candidate.py`, `register_cash_shadow_candidate.py` and `report_cash_shadow.py` for that study. Fitting remains manual and requires completed qualified train/validation plus an actually observed freeze. The environment's `CRYPTOFORGE_CASH_SHADOW_PROTOCOL` routes only prospective diagnostic observation; absent candidate is inert and observer errors do not change baseline trading decisions. Source contract/window metadata is preserved from original decisions; unknown old windows are not backfilled. Closed-study paper policy and acceptance criteria still need their own prospective registration.


Primary source admission also checks the last known closed candle is within15 minutes of its fit snapshot, recording per-pair close times; continuous stale history is excluded. Registry model age includes its evaluation-data boundary when present. Reject-entry diagnostics preserve exact observed features/probability/model/input bar in a separate first-snapshot namespace; these opportunities are never counted as executed buys.


Primary forecast-only diagnostics now have a separate private ledger selected by `CRYPTOFORGE_PRIMARY_FORECAST_LEDGER`. The existing candidate/short-shadow lookup also records the full long probability,original input bar/reference,explicit target/cost policy and train-only support diagnostic even when no real buy follows. First forecast per model/bar/contract is immutable; timezone aliases are canonicalized. This is an inventory-conditioned observation stream rather than a complete market universe.

`collect_primary_forecast_outcomes.py`/`cryptoforge-primary-forecast-outcomes.timer` read bounded Bybit Spot cached candles after the target close. Price endpoints receive actual-observation versions and remain separate from cash buys and simulated fills. Missing cached final values produce partial diagnostics; unknown original cost/label policy stays unknown. Storage stops at256MiB or below2048MiB free disk reserve without deleting evidence or changing the trade gate.

Actual original-input numerical audit can use `--allow-current-runtime-difference` to compare saved numbers while explicitly reporting changed source. It does not execute archived code or claim that the full historic runtime was reproduced. Classification log loss/Brier or a positive candle return is not evidence of realized portfolio income.


Paper commands also accept `--protocol` and isolate all three scenario wallets/worker ledgers/policies/results by the frozen protocol SHA. `prepare_cash_study_paper.py --protocol ...` creates disabled drafts; `freeze_paper_acceptance.py --protocol ...` preregisters that study's criteria before results. `freeze_cash_paper_policy.py --protocol ... --cost-assumption-id ...` still requires its qualified registered candidate. New-study virtual execution can be installed with `deploy/install_local_cash_study_paper.sh <protocol>` only after activation preconditions pass. It uses separate SHA-named units/locks and never replaces legacy units. Closed-study wallet/service is currently absent and acceptance remains sealed.

### Диагностика пропущенных базовых входов и риска

`report_primary_forecasts.py` публикует `baseline_opportunity_cohorts`: все сохранённые базовые сигналы и их фиксированное разделение по вероятности primary-модели 0.5. Низкая вероятность с последующим положительным ценовым результатом видна как потенциальная ошибка отбора. Это исход свечной цели после предполагаемых затрат; он не воспроизводит фактический ML gate, fills, общий капитал или реальную упущенную прибыль. По этим группам нельзя автоматически менять порог или выбирать модель.

`signal_cohorts` разделяет высоковероятные прогнозы по паре и training support. Отсутствующий либо ошибочный drift diagnostic остаётся `support:unknown`. Малые выборки и данные одного дня не подтверждают прибыльность.

`audit_trade_labels.py` независимо пересчитывает PnL, цену выхода, adverse/favorable excursion bounds и длительность удержания для development-only samples. Отчёт сохраняет dataset SHA и явно отмечает, что метки могут перекрываться и не являются исполненным портфелем. Арифметический аудит не заменяет ручной разбор, исторические правила исполнения или отдельную проверку ambiguous/target scenarios.

Для повторения source audit используйте `scripts/audit_intrabar_source.py --pair BTC/USDT --directory <minute-staging-directory> --sha256 <exact-file-SHA> --maximum-minutes 60 --output <report.json>`. SHA здесь относится к точным байтам `BTCUSDT-1.json`; canonical snapshot SHA из downloader manifest может отличаться из-за форматирования JSON. Команда не обращается к бирже, проверяет frozen development source и возвращает ненулевой код при расхождении. Resource guard сохраняется.

Архивная команда `train_archive_model.py` сохраняет original input snapshots и runtime source bundle для `audit_primary_training.py`. Default feature window120 задаётся явно (`--feature-lookback-candles`), input contract bounded-window-candle-v1; новые артефакты не утверждают совместимость с прежним неявным расчётом. Source hashes фиксируются до извлечения признаков и повторно проверяются после обучения. Это development diagnostic; `live_eligible=False`, автоматическая публикация запрещена.

Offline max drawdown отмечен как консервативная OHLC liquidation bound, а не точная траектория исполнения. Позиция, закрытая немедленно на open, больше не участвует в последующих экстремумах свечи; её поступления не финансируют другие pending entries того же opening batch.

Дополнительные research-only компоненты: `dual_market_context.py` (29-feature BTC/ETH extension), `turnover_features.py` (observed quote-turnover VWAP), `net_ablation.py` (train/inference masking) и `net_classifier.py` (net-profit classification). Они не меняют зарегистрированный candle-v1 input и не подключены к live gates. Class balancing использует только train counts; weighted score требует проверки калибровки на естественном распределении. Эти компоненты требуют отдельного frozen source-bound study до actual data experiments и не предоставляют допуск по прибыльности.

`entry_risk.py` создаёт исследовательские планы ATR по прошлым закрытым5m свечам; optional `simulate_portfolio(..., entry_risks=...)` хранит индивидуальные stop/target/hold для каждой позиции и проверяет availability до fill. В static mode numerical behavior сохраняется. `strategy_extensions.py` содержит отдельные support-bounce/compression-breakout kernels; их draft catalog ещё не является регистрацией исследования и не даёт право на test-подбор/live orders.

`exit_rules.py` задаёт общий порядок stop/target/timeout для observed price. Offline path применяет его к open, paper — к свежему bid без неразрешённого take-profit. Различия наблюдений и fills сохраняются явно.

Новая paper execution freeze сохраняет `implementation_hashes` и private source bundle. `paper_runtime.py` проверяет исходники worker/wallet/market/activation/exit rules и их зависимости; changed/missing source binding запрещает активацию прежнего исследования. Исходные старые receipts не дополняются сегодняшними hashes задним числом.

Offline `spread_fraction` — отдельный сценарий полного спреда вокруг OHLC reference: ask=reference×(1+spread/2),bid=reference×(1−spread/2), затем отдельно adverse slippage и entry/exit fees. Это не исторический bid/ask. При spread0 прежняя математика сохраняется.

`backtest_archive_portfolio.py --detailed-equity --max-candles 5000` экспортирует ограниченный cash/basis/open-position ledger вместе с close-equity. Нужны обычные resource/source guards; detailed capture не включается автоматически в каждый search trial.

Paper exporter запрещает выдавать будущие статусы заявок/события worker за более ранний баланс. Execution design проверяется до observed freeze; source manifest включает runner/export/evaluation scripts наряду с wallet иmath kernels.

`cryptoforge-atr-input-audit.timer` повторяет только отложенный входной аудит каждые30минут. Resource/worker contention даёт отдельный статус `deferred_by_resource_or_worker_guard`, сохраняя прежний numeric report. Corrupt frozen archives вызывают ошибку. Завершённый source-identical audit не пересчитывается; model fitting, strategy search, publication иorders не запускаются.

`spot_buy_math.py` — единая формула acquisition для explicit base/quote fee convention. Offline simulator использует quote fee, paper wallet — base fee при покупке; fractional net quantity и полныйbasis сохраняются в paper ledger. Unknown fee currency требует отдельной реализации. Эти conventions остаются сценариями; их сходство по коду не подтверждает исторический тариф.

Spot-long net heads отклоняют nonzero short-target labels. Они не выполняют автоматическую миграцию gross-price examples в net-trade target.

Fixed `backtest_archive_portfolio.py` replay теперь регистрирует source/config/data study до расчёта outcomes и расходует persistent family budget. Повтор сохраняет original JSON/result без пересчёта. Pending fixed replay timer проверяет observed source/command binding; source changes требуют пересмотра запроса, не автоматически запускают новые варианты. Historical reserved-final performance не заявляется.

`train_window.prepare_training_window` готовит research-only `[train_end-window, train_end)` по entry time, включая только метки, доступные до train_end. Весь переданный input проверяется на future/unordered/duplicate rows, даже вне выбранного окна. Optional exponential half-life weights зависят только от entry age, нормированы к mean1; effective sample size показывает потерю поддержки от weighting. `fit_net_regressor(..., sample_weights=...)` применяет веса к train means/stds, intercept и ridge objective; validation не переобучает нормализацию. Передача одних rows без weights сохраняет unweighted режим. Выбор окна/half-life требует отдельного preregistered budgeted validation study; процедура не изменяет frozen cash protocol и не разрешает live promotion.

`validation_threshold.select_validation_threshold` — research-only выбор из полного заранее объявленного probability threshold grid. Вход — validation portfolio summaries с одинаковыми study SHA/period/capital, а не доходности отдельных баров. Допуск требует положительных net и stress PnL, minimum trades и обеих drawdown в пределах declared limit. Ranking: stress return, затем net return, затем больший threshold для детерминированного tie. При отсутствии допустимых вариантов возвращается no candidate. Selector проверяет формат ссылок SHA, но не читает reports и не подтверждает их checksums: caller обязан проверить provenance и зарегистрировать каждую попытку до расчёта. Frozen cash threshold0.5 и live gates не меняются. Ablation head принимает explicit sample_weights для сопоставимого train-window исследования.

`validation_evidence.select_registered_validation_reports` читает существующий ResearchAttempts SQLite через `mode=ro`. Допускает только explicit `validation_threshold_selection` manifest и exact complete grid. Selection policy (period/minimum trades/drawdown) обязана совпадать с observed preregistration. Каждый JSON summary (≤1MiB) сравнивается с immutable completed ledger payload; вычисляется SHA256 исходных байтов. Execution timestamps должны следовать регистрации study/attempt и предшествовать completion. Backdated legacy reports не мигрируются. Это проверка целостности recorded evidence, не независимая проверка исполнения simulator или прибыльности.

`train_window_study.run_train_window_study` резервирует полный declared window/half-life grid в ResearchAttempts до fit. Train/validation snapshots, cutoff, ridge/target и implementation hashes входят в study identity. Повтор возвращает persisted JSON без обучения; изменение validation создаёт новый study, effective configuration budget сохраняется между studies. Результаты включают effective sample size и SHA выбранных train rows/weights. Автоматический winner не выбирается; метрики — prediction error counterfactual independent-entry labels, не совместный portfolio PnL. Archive provenance и resource guards обязан обеспечить вызывающий runner; сама процедура не запускает архив и не применяется к live trainer.

Primary forecast quality report содержит `signal_concentration`: распределения сигналов p≥0.5 по pair/UTC prediction day, largest fractions и отдельные количества signal pairs/days. Все observed endpoints не считаются независимыми сделками. Gate thresholds не меняются. Numeric net-head runner фиксирует dependency hashes до label construction и проверяет после fit/export; JSON reports используют atomic private writer.

`net_training_cohorts` требует explicit supported net target, проверяет seven-feature finite vectors, Spot-long labels и duplicate identities. Недоступные/unknown label availability rows исключаются без чтения их targets/features. По pair и UTC entry day сохраняются positive/negative/zero counts и concentration; это поддержка обучающих примеров, не независимые исполненные сделки. Window study сохраняет одинаковый validation cohort report для всех вариантов.

`net_training_snapshot` — отдельный private content-addressed gzip формат для исходных train/validation net examples. Price-target snapshot не принимается; outer test не сохраняется. Window study сохраняет original rows и original runtime source bundle до fitting. Наличие исходных real-cash targets само по себе не добавляет новых buy orders.

`train_window_audit.audit_train_window_study` проверяет manifest/input/runtime SHA, source compatibility, selected rows/weights, train-only weighted means/stds/intercept, ridge first-order equations и validation errors/cohorts. Он не решает normal equations, не обучает модель и не выполняет архивный код. Ledger authenticity эта процедура не подтверждает; для допуска требуется отдельная проверка immutable attempts. Нет автоматической публикации и доказательства доходности.

Для полной проверки window report передайте `ledger_path` в `audit_train_window_study`: `research_evidence.verify_registered_report` сравнивает manifest и полный unique result grid с completed immutable attempts через SQLite `mode=ro`. Численный аудит без ledger по-прежнему явно возвращает ledger_authenticity_verified=False. CLI `PYTHONPATH=src .venv/bin/python scripts/audit_train_windows.py --report REPORT.json --ledger LEDGER.sqlite` требует ledger и ограничивает JSON16MiB/совокупные uncompressed snapshots32MiB. Это только bounded verification; архивный label construction/fitting по-прежнему требует обычных research resource guards.

`paired_portfolio.compare_filtered_portfolios` сравнивает исходные baseline opportunities и их ML subset на одинаковой истории/капитале/лимитах. Ordinary и stress simulations выполняются для обеих сторон; optional reference_signals добавляет фиксированный reference model под теми же assumptions. New/duplicate/non-baseline filtered signals отклоняются. При per-signal entry_risks исходные frozen планы переиспользуются для retained entries всех arms; изменить stop/target/hold одновременно с фильтром нельзя.

Paired intervals используют разницу daily equity changes одних и тех же полных UTC дней общего wallet, сохраняя совместный учёт монет; partial boundary days исключаются. Bootstrap design включает explicit minimum_days/block_days/repetitions/seed. No-trade ML filter может избежать baseline losses, оставаясь zero-profit cash: такой результат не подтверждает доходность и не разрешает promotion.

`evaluate_net_portfolio.py` теперь регистрирует paired/bootstrap/source contract до simulations, считает stress baseline вместе со stress candidate и атомарно сохраняет report. Original completed attempts переиспользуются. Изменившийся source/budget contract не разрешает молча повторить frozen experiment: требуется новая observed protocol version и допустимый persistent budget. Existing all-bar baseline остаётся development diagnostic; его нельзя объявлять фактической торговой стратегией без отдельного сравнения.

Threshold validation summaries теперь требуют отдельный `stress_trade_count`. Declared minimum_trades применяется к ordinary и stress execution samples; stress profit на одном исполненном входе при большом ordinary sample не проходит activity gate. Missing stress counts не восстанавливаются из ordinary counts. Bootstrap seed допускает только integer, чтобы исключить нестабильные NaN/float seeds.

`evaluate_archive_train_windows.py` запускает fixed four-cell window study только после protocol checksum, resource/source/dataset guards. Frozen protocol `net-window-research-v1.json` задаёт windows2/4days × uniform/half-life1day, ridge0.01, tail2000bars/pair, aligned70%train/85%development boundaries. Caller archive/source/runtime/execution context входит в immutable study manifest. Git commit/dirty flag, Python version/implementation/machine и explicit no-randomness fit receipt не содержат environment values. Dirty working tree означает, что authoritative implementation identity задают source SHA, а не один commit.

`evaluate_window_portfolios.py` проверяет immutable source report SHA, original fitted study/ledger/numerical audit, execution assumptions и development archive digest. До simulations регистрируются все четыре фиксированные модели; entry threshold0 и stress multiplier2 не подбираются. Results — all-bar viewed-development comparison, без публикации и независимого final claim. Реальные запуски 11октября завершились; оба original JSON reports при повторе сохранены побайтно, fitting/simulations берутся из completed ledger attempts.

`ablation_study.run_registered_ablation` использует строго зафиксированный original window control, проверенный по ledger/input/runtime/numerical audit. Grid feature subsets резервируется до fitting; masked train/inference совпадают, result models/metrics/differences сохраняются immutable. Original control не переобучается и source study не заменяется. Automatic feature removal/promotion отсутствуют.

`evaluate_net_ablation.py` требует frozen protocol SHA, frozen CLI/dependency hashes и exact original report SHA. Protocol `net-feature-ablation-research-v1.json` задаёт7single-feature removals против previously viewed4-dayuniform control. Это descriptive development study, не blind validation.

`cryptoforge-feature-ablation.timer` повторяет только эту source-bound отложенную задачу каждые30минут. Observed retry request содержит exact coded command/protocol/self-source binding; JSON не используется как произвольная shell command. Resource floors1536MiB RAM/2048MiB disk сохраняются; source changes требуют review. Completed report проверяется против immutable ledger и повторно не обучается. Service140s/768MiB/nice10, publication/orders не запускает.

`ablation_audit.audit_ablation_study` проверяет original control/window ledger и source/input bundles, mask/feature names, fitted target/family/ridge, masked train-only means/stds/intercept, ridge stationarity и validation metrics/differences. Refitting/archived-code execution отсутствуют. Тест faulty recorded coefficient у удалённого признака показывает, что численный audit выявляет ошибку даже при неизменных predictions и совпадении ledger payload.

Actual ablation study11октября завершён (7/7fits), source/ledger/numerics verified. `evaluate_ablation_portfolios.py` сравнивает все7fixed models, baseline и frozen original unmasked control с одинаковыми ordinary/stress assumptions. Новый portfolio protocol frozen до7simulations; source report и control report SHA pinned. Все7вариантов в проверенном development-срезе сделали0trades/net0/stress0, как control; improved numeric RMSE не разрешил feature selection/promotion. Retry service теперь сохраняет completed report без fitting.

`evaluate_classifier_balance.py` регистрирует две fixed class_balanceFalse/True designs до fitting: train-only inverse-frequency weights, epochs100/lr0.05/L2=0.001, original4-dayuniform inputs, natural validation и threshold0.5. `ClassifierEntryScore` использует >= convention как diagnostics, включая equality; score не выдаётся за expected net return или calibrated probability. Source/report/data/runtime guards и ordinary/stress shared-wallet comparisons сохраняются.

Actual completed study11октября: unweighted Brier0.1128838/logloss0.3867386/0trades; balanced Brier0.2604986/logloss0.7181179/36trades/net−0.759012651USDT/stress−1.400583590 приcapital100. Constant-train-prevalence baseline Brier0.1113350/logloss0.3818423 лучше обоих classifiers. Balanced trades5positive/31negative,7price gains erased by costs. Model selection/publication отсутствуют.

`classifier_balance_audit` проверяет ledger/original input/runtime/source, train-only normalization/class weights/prevalence/identities/information cutoff и точный replay natural validation diagnostics. Он не refit и не подтверждает optimizer coefficient reproduction или независимую calibration. Это явно отмечено в report fields. Повтор CLI может deferred resource guard даже при completed report; original result остаётся сохранённым, это не successful cached execution.

`screen_completed_research.py` читает complete immutable result grids из ledger и проверяет экономические показатели каждой ordinary/stress filtered arm: minimum trades, strictly positive net PnL, PF и drawdown. Cash/PnL и trade/signal counts обязаны сходиться, unknown no-loss PF не превращается в infinity. Economic pass не выдаёт independent/live admission. Report SHA и gate protocol SHA сохранены; fitting/model selection отсутствуют.

Screen подключён как optional ExecStartPost к существующему read-only live feedback service при наличии трёх completed reports. Actual inventory13configs:0economicpasses,10no-trade configs и3loss configs; arms/варианты не суммируются как независимые сделки или единый доход. Feedback refresh успешно завершён, никаких orders/publication не добавлено.

`spot_sale` в shared cash-math module считает explicit quote-fee notional/proceeds/fee для уже округлённого количества. Offline simulator close, paper FIFO segments и paper conditional liquidation используют этот kernel. Venue rules/rounding/dust ownership остаются у callers; base/platform-token sell fees отклоняются, их конверсия не предполагается.

Sell proceeds используют notional*(1-fee), как прежний paper wallet. Это algebraically equivalent прежнему offline notional-minus-fee; крайние Decimal rounding differences возможны, поэтому источник реализации изменился. Старые source-bound studies/policies сохраняют original bundles/results и не получают новые hashes задним числом. Для нового execution study нужен новый observed source freeze. Primary price-model source dependencies не изменены; strict auditb08e9e31eb остаётсяexact.

`target_contracts` описывает три отдельные цели: fixed-future price return, counterfactual simulated net trade return и observed real cash recovery с residual-zero convention. Artifact target должен совпадать с требуемой задачей; root/config/event declarations не могут противоречить друг другу. Missing target допускается только в primary legacy-price context без cash provenance; такое fallback не является target migration.

ActiveModelRegistry теперь отвергает net/cash/unknown targets в primary active/candidate channels даже при совпадении pure-python-logistic family. Cash-specific workflow остаётся отдельным. Новые TrainedModel primary artifacts явно записывают fixed-future-return-v1 в root/config и не могут relabel иной target илиcash source. Caller config не мутируется. Старые artifacts/snapshots не переписываются.

Producer metadata source изменился: для oldb08e artifact current-source strict equality больше не заявляется. Explicit allow-current-runtime-difference audit подтвердил saved inputs/current numerical metrics, current_source_matches_fitted_source=False, без refit/publication/archived-code execution. Completed ablation retry timer отключён после7/7 completion: он больше не нужен и не пытается повторять старый source-bound fit. Основные training/feedback timers остаютсяenabled.

Entry gate diagnostics теперь содержат by_pair decisions/fallbacks/constraint categories и observed strategy flags. Numeric RSI/volume/momentum context не превращается в blocker keys; flags True/False не объявляются отдельными causal failure reasons. Unknown reject restrictions учитываются отдельно. Source windows остаютсяbounded, stale/future/truncated не выдаются за current complete evidence. Feedback timer использует расширенныйreport автоматически через существующийreport_entry_gates.py.

`ClosedFeatureStream` — append-only closed5m candle-v1 bounded-window calculator (36..1000bars, default120). Unavailable/partial/stale unfinished, duplicate/gapped/revised or wrong-market bars отклоняются до изменения состояния. Observation clock не идёт назад. Output различает earliest available_at и actual caller computed_at; late old revision влияет только пока находится внутри bounded window. История не растёт сверх lookback.

`audit_stream_features.py` сравнивает incremental vectors с bounded-window archive training examples и entry_signal на одинаковом bounded120input (declared emerging/reversion enabled). Fixed inputtail2000/first1400 BTC/ETH source/resource guards; current source fingerprints checked before/after. Actual2556featurevectors/2562bounded signals совпали. Это не full live baseline procedure qualification, не historical observation certification и неincome verification.

`FeatureMigrationStudy` создаёт actually observed immutable feature-comparison protocol: frozen primary price artifact, known closed bounded120 contract, trained pair basket, threshold0.5 иsame bounded120 ML-free control. Registry/source/model hashes, original runtime bundle иcompressed input windows сохраняются; source changes/unknown legacy reconstruction/model updates forbidden. Forecast namespace изолирован, timestamps post-freeze/fresh, signal bar close не раньшеfreeze. Initial fresh model36h rule applies atfreeze only для fixed research benchmark; live freshness policy не меняется.

`collect_feature_migration.py` read-only Bybit public500bar fetch per fixed pair,20s work budget; stores paired baseline/candidate signals through PrimaryForecastMemory and matured price endpoints. Already resolved endpoints не переписываются. Reports остаютсяprice diagnostics,counts real buys0,live promotionFalse. Project timer every5min,45s/256MiB/nice10. Active protocol700119966617653d6be5d011b009821ff35383ea91304c56bd02206d56c38c24:APT/NEAR, frozen041b candidate. V1/V2 receipts — preflight prototypes безнаблюдений, сохранены; v3 froze finalized collector beforefirst observations. Это не законченная migration admission и неcash execution study.

Simulator legacy liquidation math сохраняется, ноexit notional<declared min_notional теперьexplicitly flagged `exit_minimum_violations`/assumed_exit_not_certified_executable. Trade labels исключают такиеoutcomes какunresolved_exit_minimum безexample/net target. Portfolio diagnostics иdevelopment screen считают/отклоняют known violations. Historical min-notional certification иactual residual ownership modeling вoffline simulation остаютсяотдельной работой; отметкане являетсяисправлениемallfills.

Simulator: новый explicit `exit_minimum_policy=preserve_inventory` сохраняет unsellable quantity/basis/capital. Portfolio/economic diagnostics сверяют cash+open basis против realized net и не допускают unclosed inventory. `legacy_assumed` сохранён для старых сценариев, но не сертификат исполнения. Новые исследования требуют нового source/config freeze; прежние immutable результаты не пересчитываются задним числом. Проверка12октября:892tests passed.

12 октября: actual execution integrity. `unique_executions` защищает FIFO/inventory от duplicates, conflicting IDs, nonfinite economic fields; sync сохраняет исходное исполнение и отклоняет конфликт до публикации. `get_unified_wallet_coins_for` требует explicit coins/full coverage, сохраняет подтвержденные zeros. Readonly wallet23coins reconciled against local fills/transactions. Новый bounded `audit_execution_cache.py` сохраняет immutable input + original source/runtime, не отправляет orders/notices. Closed FIFO49segments net−1.305596403254432124223602484USDT;16segments≤−1%. Тесты903passed.
Strict label audit CLI сохраняет references для sample windows и manual_review_complete=False; actual run deferred по resource guard,20manualcases всё ещё открыты. Новые execution studies/policies должны freeze обновлённые dependencies, исторические receipts не переписывать.

Walk-forward12октября: strict Fold calendar validation и проверки дополнительных evaluation/previous-test/selection outcome cutoffs; восстановление receipt сверяет SQLite identity/interval и current observed clock. Data snapshot capture time отдельно от reward availability. Full913tests passed, final calendar-focused18passed; новые studies должны freeze обновлённые source hashes. Actual candidate4298b rejected fails_baseline_or_costs:400examples,30signals mean estimated aftercost−1.945684551%, accuracy75.75%<majority78.75%; old active contractunknown. Не cash profitability.

Validation threshold12октября требует явных ordinary/stress zero open inventory/exit-minimum violation counts; unknown legacy execution summaries исключаются даже при verified immutable report. Новая source/config/report registration обязательна, старые evidence не backfill. Paper full-risk summaries проверяются на integer coverage counts, consistent all-known, finite bounded drawdown/gaps и минимум по видимым marks. Tests930passed; source-bound acceptance policies требуют новой версии, future evidence gates остаются открыты.

13 октября: strict prospective price calibration (`report_migration_calibration.py`) сохраняет immutable original rows/source/runtime и сравнивает с train prevalence из frozen artifact;642endpoints,Brier.1302435<baseline.1339941,0signals≥.5. Это exploratory overlapping price targets, не net cash income и не preregistered selection. `capture_execution_market_sources.py` сохраняет full raw canonical instruments/orderbook responses и observed receipts; verifier повторяет normalization/source/runtime/freshness и не сертифицирует fills/fees/history. Actual527instrument snapshot +APT/NEAR receipts verified at originaltime. Tests940passed. Future execution qualification/source gaps/independent periods остаются открыты.

13 октября: InstrumentObservationMemory проверяет registry id/time/coverage против immutable full source и ограничивает source size. Новый account fee collector/replay (`capture_spot_account_fees.py`, fee_observation/evidence) получает explicit Spot fees readonly, сохраняет account-scoped original response/runtime и проверяет server/observed clocks/source hashes. APT/NEAR maker.001,taker.0018 observed13:31UTC; fill fee asset/history не подтверждены, настройки не меняются. Full950tests passed; actualarchiveaudit всё ещё resource-deferred, thresholds не понижены.

13 октября: новый independent paper_fill_audit включён в export_results и runtime source manifest: recorded quote/slippage/qty/fee accounting/FIFO fractions/net proceeds/segment allocation, source-clock/min/max/depth assumptions иremainingqty conservation. Source policies требуют новой версии. Full953tests passed. Actual strict archive audit BTC/ETH700candles/651labels/pair/20numeric samples each completed; original source windows retained, only timeout cases. Это declared default fee/min/step scenario иoverlapping labels, не исторические execution facts или cash portfolio returns; manual gaps/ambiguous/unclosed source cases остаются открыты.

13 октября: широкий strict source audit3500bars/BTCETH,20cases/pair,34timeout+6stop checked;17fee-erased gains. Original audit source/runtime pinned and unchanged, case windows replayed readonly by replay_label_audit.py with checksum/clock/ambiguity/market checks. Full957tests plus3finalfocused, actual40case replaypassed. Features/human/historical execution не сертифицированы; longarchive/ATR stilldeferred.

13 октября: coarse intrabar source must be available at as_of andvalid OHLCV; paper fill replay enforces frozenstake. Long label audit now fixed observed job0fd8a8a7... with original source/input/runtime, fifteen-minute systemd retry andoriginal1536/2048resourceguards; stops oncompletion/blockedfailure, no live changes. Actualinstalled status resource-deferred, completedFalse, timeractive. Full966tests passed. Actuallong/ATR/historicaledgecases/independentpaperremain open.

13 октября: registered extension study8280273c...support_bounce/compression_breakout ×fixed/ATR;4reserved configurations, sameoriginalresearchbudget100/family andcanonicalnamespace. Native baseline usesmatchedrisk/closed120context, sharedwallet ordinary/stress,cash-only0,pairedUTCbootstrap; notMLfilter, notindependent. Originalinput/source/runtime/ledger binding retained. Worker20minretryinstalled,firstactualresource-deferred,0/4results;completeimmutablegridverificationrequired beforecompleted. Longaudit andstudyretainoriginalsingleworker/reserves. Full973tests passed; cash/live model/risk settingsunchanged.

13 октября: buy_hold_context.py providesfixedstakepassivecontext,samecapital/stake/history,nextopenentry120,allinitialcosts reserved beforeterminalproceeds;fees/minimum/residualbasis explicit,stop-targetriskdifferent. Separately registeredstudy9e6e6008...,1reservedcontext,no backwardchange toextension8280273c...; passive20mintimerinstalled/firstresource-deferred0/1. Supervisorspermitonlyfixedsupportedscopesandimmutablecompletegrid,noliveadmission. Full976tests passed.

13 октября:captured6stop-case minute windows (30bars,6/6complete),originalsnapshot/runtime/input receiptSHA3bd26e7b...;dataingestiononly. Intrabar audit optionalinspect_unambiguous exposesfineropengapreference evenwithoutcoarseambiguity,defaultpolicyunchanged. New audit_stop_case_minutes source/firsttouch script resource-deferred,completedFalse;actualgap/sourcefindingsunavailable. Full979tests passed; existingOctober1minute source artifacts reusedratherthanclaimednew.

## Продолжение 14 октября 2026: очередь minute source audit

- Установлены scripts/run_stop_case_audit_job.py и cryptoforge-stop-case-audit.timer (enabled/active), каждые20минут. Job: .local/state/stop-case-audit-jobs/20261014/job.json. Заморожены ingestion pointer SHA и оригинальный runtime supervisor/auditor/reader/barrier/source-comparison. Изменение входов или кода блокирует задание; завершение требует полного уникального набора6cases и правильного source/runtime.
- Первая сервисная попытка14октября01:53UTC: deferred_resource_or_worker_guard, completed=false; около937MiB доступно, исходный минимум1536MiB сохранён. Три прежних исследования также deferred; численные результаты не объявлены завершёнными.
- Проверка:981passed/14.80s; bash -n обоих новых deploy scripts. Live promotion=false; рабочая модель и торговые настройки не изменялись.
- Остаётся actual minute comparison, исходные long/extension/passive outcomes, ручные source cases и независимые будущие периоды. Ни установленные таймеры, ни синтетические тесты не доказывают прибыль.


## Продолжение 14 октября: глобальная уникальность source-case replay

- Исправлен scripts/replay_label_audit.py: повторённые market groups, дубли signal times (включая разные UTC offsets), несовпадение group/sample/reference pair, naive timestamps и некорректные audited_samples теперь отвергаются до численной сверки.
- Actual read-only replay исходного source-bound отчёта f5a3de71164007f600791cc581c322f5955aa50ed8a6f28db6f72322f669941b:40уникальных случаев,34timeout и6stop. Receipt: .local/state/trade-label-wide-global-coverage-replay-20261014.json, сохранён текущий replay runtime. Original report не изменён; manual_review_completed=false и historical_execution_certified=false.
- Команда: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m scripts.replay_label_audit --report .local/state/trade-label-strict-wide-sourcebound-20261013.json.
- Полная проверка988passed/20.96s. Старый test fixture дополнен обязательным pair группы, как в реальных отчётах. Исправлен случайно дублированный текст исходного checklist; исторический раздел явно отделён от текущей готовности.
- RAM около938MiB: original resource floors сохранены. Actual minute/long/extension/passive results ещё pending; future paper и profitable admission не закрыты. Frozen computation dependencies и live настройки не изменялись.


## Продолжение 14 октября: разбор наблюдаемых убытков рабочего бота

- Реализованы execution_loss_review.py и CLI review_execution_losses.py: проверка unique FIFO segments, known fees/pnl/basis, exact recorded return; recent20cases содержат оригинальные source segments. Unknown fees не подменяются нулями; стратегия/независимость/no-fee counterfactual не сертифицируются. Output immutable, input SHA и runtime сохранены.
- Actual read-only cache audit14октября:63ordinary executions+12conversion events,49closed FIFO segments,14open lots,0unmatched sells,0incomplete fees; net−1.305596403254432124223602484USDT, open basis0.1137995937888198757763975155. Input SHA cc7fab4648c6663ee13ad67f41283c1cacd8b5305d0ea4e540fac45acb564309 совпал с прежним: fresh exchange sync не заявляется.
- Actual loss review49segments:28losses,16net returns≤−1%,6negative results with net+recorded-fee-equivalent≥0. Эквивалент fee для base currency не является независимым no-fee counterfactual; FIFO segments могут делить orders.
- Артефакты: .local/state/execution-cache-readonly-20261014.json; .local/state/execution-loss-review-cache-20261014.json. Повтор исходного12October receipt отдельно: .local/state/execution-loss-review-20261014.json.
- Проверки991passed/20.19s; live settings/model unchanged. RAM1333MiB<1536MiB: queued numerical research deferred. Открыты source strategy-attribution, fresh account reconciliation, execution qualification и independent future evidence; losses не используются для автоматической подгонки или публикации.


## Продолжение 14 октября: conflicting order context guard

- live_feedback.analyze_feedback больше не выбирает последнюю из конфликтующих записей approve_entry/approve_exit одного pair/order/action. Identical duplicates объединяются; конфликт остаётся missing context независимо от порядка и повторения записей. Финансовые outcomes сохраняются, attribution/cohorts не получают неизвестную стратегию. Report содержит conflicting_order_contexts и explicit policy.
- Actual cached execution replay через feedback:42exit-order groups из49FIFOsegments,27losing/15profitable, net−1.305596403254432124223602482USDT (Decimal grouping rounding отличается от segment sum на2e−27USDT), fees0.9025984852470321242236024844USDT.14short-hold groups,6fee-erased gains;5large bot-controlled spot exit orders. Conversion/external/partial groups не выдаются за независимые trades.
- Receipt .local/state/feedback-cache-replay-20261014.json содержит source input SHA и текущий runtime; original decisions отсутствуют в cache, exact attribution coverage=0, accounting_quality_verified=false. Receipt не записан в verified training memory. Source live feedback read, свежая wallet сверка и causal strategy attribution этим не закрыты.
- Полный набор994passed/29.14s. Frozen studies/primary migration computation sources не изменены; live risk/model/order settings сохранены. На старте1102MiB RAM: original1536MiB guard не снижен.


## Продолжение 14 октября: verified fee calibration и explicit wallet coverage

- candidate_cost_floor требует accounting_quality_verified is True, positive integer minimum_orders, finite0≤slippage<1 и finite0≤observed fee rate<1; unknown/malformed/NaN/Infinity/negative rates не калибруют кандидата. Fee floor остаётся prior-execution diagnostic, не live rule.
- scripts/analyze_live_feedback.py теперь запрашивает get_unified_wallet_coins_for для exact tracked base coins после unique-execution проверки. Empty tracked set не сертифицирует account; отсутствие coin coverage не подменяется нулём. Synthetic zero-wallet/full-close проверка прошла.
- Actual saved live-feedback.json14октября03:50:50UTC:40outcome orders,accounting_quality_verified=false,inventoryconsistent=false,9missing wallet coin records;candidate_cost_floor=None. Это снимок ДО исправленного следующего service run: corrected fresh-account reconciliation пока не заявляется. Feedback timer active; следующий обычный запуск применит новый запрос, existing memory не backfilled.
- Полная проверка1014passed/21.08s; git diff --check чистый. InitialRAM972MiB,final1070MiB ниже1536MiB: pending research jobs остаются resource-gated. Model/risk/order parameters не менялись.


## Продолжение 14 октября: actual current wallet source capture/replay

- Добавлены scripts/audit_cached_wallet.py и scripts/replay_wallet_audit.py. Read-only consistent SQLite snapshot с bounded executions/transactions, explicit tracked wallet request, immutable output, normalized adapter balances и original cached inputs, SHA/current runtime. Raw HTTP transport не заявляется сохранённым; API key заменён account scope hash и не выводится.
- Actual Bybit query14октября04:08:04UTC:23tracked coins,0missing balances,inventory_audit.consistent=true. Input SHA c76d178993cc810aa8d624ca2f85b208678b6ba3ab51742ec30272afb98be935, receipt .local/state/current-tracked-wallet-audit-20261014.json. source replay_matches=true для23coins без повторного API запроса.
- Команды: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/audit_cached_wallet.py --cache data/live-journal-821b0fc204930b57.sqlite --output .local/state/current-tracked-wallet-audit-20261014.json; затем scripts/replay_wallet_audit.py --report того же receipt.
- Full suite1015passed/21.60s; после добавления replay verifier focused1passed/0.14s, включая tampered result rejection. Existing output не перезаписывается и повторный wallet query при существующем output не выполняется.
- Actual corrected explicit wallet request подтверждён отдельно. Regular feedback service ещё не перезапускался послеfix: его accounting_quality_verified не подменён результатом standaloneaudit; cached history freshness/completeness неизвестна. Verified training memory не backfilled. RAM1152MiB<1536MiB: registered compute jobs pending, profitability/independent future gates открыты.


## Продолжение 14 октября: manual launches, RAM объяснение, passive result

- На вопрос о RAM проверен /proc/meminfo: начальный MemAvailable1182MiB учитывает reclaimable cache; требование1536MiB, swap не подменяет RAM reserve. Удалены10собственных completed pytest directories из /dev/shm,103854347filebytes; available поднялся до1319MiB,позднее1188/1061MiB. Пользовательские приложения не завершались, floor не снижен.
- Выполнены ручные systemd start для stop-case/extension/passive/long jobs. Итоговый receipt .local/state/research-resource-manual-launches-20261014.json содержит actual timestamps/statuses/ресурсы. Stop-case,extension,long deferred. Уточнение первоначальной промежуточной оценки: passive context completed,не deferred; результат вычислен03:42:44UTC и повторно source/ledger verified04:14:57/04:16:05UTC.
- Actual passive study9e6e60083d2736883c39db80d8b2e6877563ac9e9ee6b107b971deed49913917 завершён1/1. Fixed6USDT per BTC/ETH,capital100,development20Sep–1Oct:ordinary realizednet0.541497649134780USDT,stress0.504513888199200USDT;remainingbasis0,openpositions0,rejections0. Не deployed≈88USDT. Explicit different stop/target risk,noindependenthistoricalexecutioncertification. Это пассивный контекст,не квалифицированный ML кандидат и не live доход.
- Existing verifier подтвердил registered_results_verified=true,verified_configurations=1,ledger_modified=false. cryptoforge-passive-context.timer disabled послеcompleted. Остальные timers продолжают guarded attempts. Код/тесты в этом шаге не менялись; последняя fullsuite1015passed плюс focused wallet replay1passed остаётся актуальной.


## Продолжение 14 октября: user-authorized1024MiB execution profile и завершённая minute сверка

- Пользователь явно запросил запуск при1182–1319MiB. Создан отдельный config/research-resources-user-1024-20261014.json:RAMreserve1024 вместо1536; original protocol не изменён, worker768MiB/120s,disk2048MiB,flock и trading limits сохранены. Предыдущие запреты на снижение minimum больше не относятся к явно разрешённому отдельному профилю. Это не изменение условий старых результатов.
- audit_stop_case_minutes.py принимает --resource-protocol; supervisor фиксирует path/SHA profile и проверяет до запуска. Новый job .local/state/stop-case-audit-jobs/20261014-user-1024/job.json/current source runtime заменяет незавершённый старый job; oldreceipt сохранён. Старый stop-case timer disabled перед изменением frozenrunner; новый job выполнен сразу, retry не нужен.
- Actual completed14октября04:18:19UTC, .local/state/stop-case-minute-audit-user-1024-20261014.json, reportSHA28430ab5293e3965c4d312f1b97377ecae66e35646feb8740f7eb9dc442d8ec1.6/6minute/coarse OHLCVsource matches;6ordered_fine_barrier;0more-adverse fine references. Никаких найденных реальных gaps из synthetic tests не выводится. Realfill/historicalobservationcertification=false.
- Fullsuite1015passed/21.50s;gitdiffcheckclean. Source consistency6stop cases теперь закрыта; manual20cases/ambiguous/noncloseout/fullhistoricalexecution иindependentfuturepaper остаются открытыми. Other long/extension pending jobs пока привязаны к original1536profile; перенос требует отдельных зарегистрированных версий, нельзя редактировать их старые freezeSHA.


## Продолжение 14 октября: remaining jobs1024MiB, complete numerical outcomes

- По явному указанию пользователя перенос remaining studies на1024MiB выполнен отдельными source/profile freezes. Original1536protocol не изменён; worker768MiB/120s,supervisor896MiB/150s,disk2048MiB,flock иlive risk сохранены. Completedpassive/stop-case не пересчитаны. Старые long/extension registrations сохранены как superseded-before-results; SHA не backfilled.
- Новый long job9a1ed5c8747132cadc12073b0214713555ac549042d5e2c977d258e8232aa6a9 completed14октября04:21:55UTC. По18143candles BTC/ETH,18094executed independent overlapping labels/pair. BTC18044timeout/38stop/12target,positive12.93799%;ETH17935timeout/126stop/33target,positive18.42047%. Positive labels не portfolioincome.40sample windows replaypassed:28timeout/6stop/6target,original inputs/runtime. ReportSHA0d27c053e481550d70880ff0259b11caa22eeb1686610de730954c403d4fd070. Manualreview/historicalexecutioncertificationfalse.
- Новое extension studycd10cf88896be5f08a11b2e1a946e0b286f9fa8ecbccf816efecf163edd3d296 completed4/4,verified14октября04:22:22UTC. Sameoriginal canonical budgetaab93fbaa50821bc223be76aabe26d2aa8bb3b4410d130327d7e38519ec4a329,4additionalreservedattempts fornewsourceversion,не новая pool100.
- Supportbouncefixed86trades:ordinary−1.605473719190486433300USDT,stress−3.136365295598333173200. SupportbounceATR93/95trades:ordinary−1.781491428045615464914285714,stress−3.439049573731358426700000000. Compressionbreakoutfixed/ATR1trade each:ordinary−0.01669559613585,stress−0.03461949104340. Все4negativeaftercosts; profitableadmission0. ATR улучшения не показал. Baselinefixed−6.80276108374326390600/stress−13.62075407636757734400;ATR−7.687677026286600326748214282/stress−15.59029328921788367850000000. Smallerloss не означает income.
- Actual receipts/results: .local/state/long-label-audit-jobs/9a1ed5c8747132cadc12073b0214713555ac549042d5e2c977d258e8232aa6a9/; .local/state/strategy-extension-studies/cd10cf88896be5f08a11b2e1a946e0b286f9fa8ecbccf816efecf163edd3d296/. Existing evidence verifier registered_results_verified=true,ledger_modified=false. Обаtimerdisabledaftercompletion.
- Tests:12focusedpassed/1.46s;full1017passed/20.81s;gitdiffcheckclean. Новые tests фиксируют unchangedsearchbudgetidentity и запрет изменения stake через resourceprofile. Freeze source/fileSHA объявлены доoutcomes; loweringreserve не снижает statistical/admission критерии.
- Открыты: source gaps/ambiguous/partial/noncloseout cases, historicalfee/filter/depth qualification, compatiblecurrentmodelcontrol, independentwindowprocedures иfuturepaper. Старые reviewedarchive slices остаютсяdevelopment; workernegativeoutcomes не запускают live replacement.


## Продолжение 14 октября: actual ATR causal inputs, migration1093, verified feedback

- audit_atr_inputs.py принимает explicit resourceprofile, сохраняет original1400candle windows/pair и runtime; existing completed receipt с другой identity больше не перезаписывается. Actual1024MiB-profile audit .local/state/atr-entry-risk-input-audit-user-1024-20261014.json completed:99plans BTC+99ETH,0unavailable-at-next-open. Historicalobservationcertificationfalse,strategypayoff этим не установлен. Старый retry ATR timer disabled послеcompletion.
- Actual migration calibration1093price endpoints:positiveprevalence0.1655992681,frozentrainprior0.1777992278;Brier0.1363389670 vsbaseline0.1383249895,logloss0.4425189852 vs0.4493577318. Fixedthreshold0.5,signals0,pmax0.3848880246. Receipt .local/state/migration-calibration-strict-20261014.json c original input/runtime. Exploratory overlappingprice outcomes не independentcashtrades;parameterselectionfalse,liveprofitabilityfalse. Prospective sourcefreezev3 unchanged.
- Regular feedback послеexplicit-walletfix actual14октября04:20:51UTC(07:20МСК):accounting_quality_verified=true,inventoryconsistent=true,23coins,noerror. Сохранён исходный output .local/state/live-feedback-verified-wallet-20261014.json. Standalonewallettest иserviceverification теперь различаются; verified flag не поставлен вручную и memory не backfilled. Это устранение missingzerobalance blocker,не independentstrategyqualification.
- Fullsuite1017passed/24.14s; после добавления2regressions focused ATRsuite5passed/0.27s. Проверены explicitprofile forwarding иimmutable oldreceipt. Gitdiffcheckclean. Model/risk/threshold/orders unchanged.
- Открыты source-boundmanualedgecases,historicalexecutionmetadata,currentmodelcompatibleexecutioncontrol,independentcalendarprocedure иfuturepaper. Недостаточная активность prospectiveprice threshold остаётсянеуспехом incomeзадачи,не поводом снижать frozenпорог.


## Продолжение 14 октября: accounting health clock qualification

- LiveFeedbackReader теперь проверяет actual health observed_at по текущему observationclock: timezoneaware,неfuture,age≤3600s (два30minutefeedbackintervals),statusok,integeraccountingversion≥2,inventory_verifiedisTrue. Missing/malformed/stale/futurehealth не подтверждает accounting. Report содержит healthobserved/checkedat иmaximumageseconds; исходная healthquery сортируется поobserved_at.desc.
- Actual regularservice manually rerun14октября04:28UTC:success/exit0,accounting_quality_verified=true. Journalhealthobserved04:27:57.722622UTC,checked04:28:05.835707UTC,age≈8.11s. Current output сохранён .local/state/live-feedback-fresh-health-20261014.json. Verified source не подменён тестовымиданными; pastmemory не backfilled.
- Fullsuite1031passed/22.54s;after3additionalmalformedpayloadcases,focusedhealthsuite15passed/0.11s. Gitdiffcheckclean. Accountingsourceclockguard не меняет modelthreshold/risk/fills/realorders; fresh health не подтверждает стратегическую прибыль.
- Remaining actual obligations: source-qualified gaps/ambiguous/partial/feeasset/noncloseout cases; historicaluniverse/minimums/depth; compatiblemodelcontrol; independentselection/test иfuturepaper. Training/feedback не может публиковать кандидат по одномуhealthok или одномуBrierулучшению.


## Продолжение 14 октября:20real-source FIFO arithmetic cases

- Реализованы независимый fifo_case_audit.audit_segment и CLI scripts/audit_fifo_source_cases.py. Auditor не вызывает reconstruct_trades: originalexecIds из entry/exitreferences,market/time/qty,receivedbuyquantity послеbasefee,consumedsalequantity,allocatedbasis,quote/basefee-equivalent иnetpnl сверяются прямо с originalexecutioninputs. Unknownthirdtoken/extrafees не оцениваются безconversion source. Quantityallocation bounds иuniqueoriginalinputs обязательны.
- Actual source-bound .local/state/fifo-original-source-cases-20261014.json:20/20cases passed;20base-buy-fees/20partial acquisitionallocations;8partial saleallocations. Все20sale_sources=spot_execution,неconvertedbalanceevents. Сохранены reviewer/inputSHA,caseexecIds,sourcecategories иruntime. FloatingDecimal rounding tolerance1e−24 relative/absolute; fees не вычитаются из net повторно.
- Команда: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/audit_fifo_source_cases.py --review .local/state/execution-loss-review-cache-20261014.json --output .local/state/fifo-original-source-cases-20261014.json. Originalreview/sourceinputs не изменены.
- Fullsuite1040passed/18.02s,gitdiffcheckclean. Tamperedbasis/fee/pnl,duplicateinputs,thirdtokenunknown rejection tested. Live model/risk/orders не изменены.
- Это real-source arithmetic qualification partial/basebuy/quotesell cases,не syntheticdata; manual_review_complete=false,full_fifo_order_certified=false,historical_market_rules_certified=false. Общий20manuallabelcases checklist сgap/ambiguity/noncloseout остаётсяоткрытым,не подменяется20FIFOallocationcases.


## Продолжение 14 октября: full-source FIFO quantity/basis conservation

- Новый independent fifo_conservation_audit повторяет chronologicalsourcequeues без вызова productionreconstruct_trades,проверяет ожидаемый acquisition/saleexecpair иmatchedqty,применяет independent segmentarithmetic,remainingqty/cost/status после каждого полногоисточника. Duplicate/missing/extrarecords не допускаются. Externalinventory не превращается в bot-ownedprofit;conversion-backedsyntheticexecution отдельно сохраняетsourcekind вoriginalinputs.
- Actual .local/state/fifo-conservation-source-audit-20261014.json:49closedallocations,33remainingrecords (включаяzero/cancelled),14openlots,openbasis0.1137995937888198757763975155USDT;unmatchedsalequantity0. Sourceinputs fills+allrecords сохраненыimmutable сSHA/runtime. Independent replay сохранённыхinputs повторил все поля результата.
- Команда: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/audit_fifo_conservation.py --audit .local/state/execution-cache-readonly-20261014.json --output .local/state/fifo-conservation-source-audit-20261014.json. Auditorproductionledger использует как comparisontarget,не для восстановленияexpectedFIFOorder.
- Fullsuite1044passed/14.99s,gitdiffcheckclean. WrongFIFOallocation,missingresidual,extra/duplicateclosedprofit rejection tested. Real-sourcecase arithmetic иcompleteFIFOquantity/basis qualification теперь отдельно подтверждены;historicalfilter/marketexecution/cashprofitadmission остаютсяfalse.
- Remainingmanualgap/ambiguity/noncloseoutlabelcases,thirdtokenfeehistoricalconversion,universe/minimums/depth,currentmodelcontrol иindependentfuturepaper ещё не выполнены. Объявлять20allocationcases выполнением20manualarchivebarriercases нельзя. Model/risk/realorders unchanged.


## Продолжение 14 октября: formal extension economic rejection

- development_screen теперь исключает economicpass при missing open_positions_at_end/open_cost_basis_at_end/known_exit_minimum_violations. Unknown executioncoverage больше не подменяетсяzeroдлярешения оpass; oldreports не дополнены полями заднимчислом.
- Новый scripts/screen_extension_research.py проверяет actual registeredextension report иledger readonly,gateprotocol originalSHA иcurrentruntime. Outputimmutable,.local/state/extension-economic-screen-20261014.json:4screened,0economicpasses. Каждая из4configs провалила ordinary/stress minimumtrades,positivenet иprofitfactor; отсутствиеqualifyingincome формально сохранено. Sourcecd10cf study не изменён.
- Команда: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/screen_extension_research.py --report .local/state/strategy-extension-studies/cd10cf88896be5f08a11b2e1a946e0b286f9fa8ecbccf816efecf163edd3d296/results.json --output .local/state/extension-economic-screen-20261014.json. Default declaredgateprotocol net-classifier-balance-research-v1,оригинальныйledger,budget неизменны.
- Fullsuite1047passed/25.33s,gitdiffcheckclean. Missing executionfields regressioncases прошли; profitablemanualfixture с известнымиполями остаётсяdiagnosticpass безindependentadmission. Фактическиеextensionкандидаты не passed.
- Текущий checklist разделён: declaredfixed/ATRextensioncomparison завершён; дополнительныеfilters/currentmodel/newheads/independentwindows открыты. Общееfalseполеprofitableadmission не отмечаетсяdone какполучениеprofit. Live model/risk/orders unchanged.


## Продолжение 14 октября: actual cash training readiness preflight

- Реализован scripts/preflight_cash_training.py: readonlyavailableexperiences толькоtrain/validation cutoffs;sealedtest/paper rewards не загружаются. Frozenprotocolregistry проверяется; immutableoutput,originalcollectionrawsnapshot/trainvalidationsnapshots иruntime сохранены. Preflight не fit/register/publish.
- Actual sourcebound receipt .local/state/cash-training-preflight-sourcebound-20261014.json:collectionhealthytrue,fitreadyfalse.0eligibletrain/validationrows;8availablecases excludedincompatible_candle_input_state. Нельзя заднимчислом менять этиoriginalfeatures/metadata наclosedonly. Train minimum100buys/14days/6pairs/20positive/20negative;validation40buys/7days/4pairs/5positive/5negative не выполнены.
- Calendartrainend2026-11-06T21:59:16.427796UTC(7Nov00:59МСК),validationend20Nov21:59UTC(21Nov00:59МСК);окна ещё не завершены. Futuredeadlines не заменяютсяархивнымиразработочнымиданными. Sourcecollectionfix не устраняет incompatibilityexistingrows.
- Первыйdiagnostic receipt cash-training-preflight-20261014.json сохранённеизменным; после добавленияoriginalcollectionraw source snapshot новаяsourceversion отдельноcash-training-preflight-sourcebound-20261014.json.
- Fullsuite1049passed/13.91s;послеcollectionsnapshotaddition focused2passed/0.08s;gitdiffcheckclean. Testподтверждает отсутствиеsealed/paperreads иpreservationexistingoutput.
- Следующийоткрытыйшаг: futureclosed-contractoriginalbuyfeatures/достаточнаяeligibleвыборка, затемrealfit/validationselection/currentmodelcontrol.0eligible не означает отсутствие8cachedbuys и не исправляетсяфальшивойmetadata. Model/risk/ordersunchanged.


## Продолжение 14 октября: training collectors original-context conflicts

- Confirmedcashinputincompatibility:existing8rows legacy/inputstate не преобразуются вclosedonly; исходные признаки сохранены. Рабочий executor/migration frozenkernel не изменён для искусственного eligiblecount.
- Обнаружен и исправлен отдельный learning collectorbug: build_live_experiences иbuild_cash_recovery использовали последнийoriginalapproveentrycontext ордера,хотяfeedbackanalysis ужеисключалconflicts. Новый original_entry_context.unique_entry_contexts одинаковыеdecisions объединяет,conflictingfeatures оставляетunknown независимо отorder/repetition. Bothcollectors explicit conflicting_original_feature_context exclusion; oldmemoryversions не backfilled.
- Fullsuite1055passed/18.20s,gitdiffcheckclean.6new regressions:bothcollectors ×orderpermutation,identicalduplicatespreservation. Source/semanticchange относится к новойcollectionversion,старые runtime/source snapshots не переписаны.
- Actualregularfeedback manually rerun success/exit0. Новаяreadonlypreflight .local/state/cash-training-preflight-context-guard-20261014.json14октября04:47:30UTC:sourcehealthytrue,fitreadyfalse,0eligibleclosedinputcases,8incompatiblecandleinputstate. Guard не увеличил samples путёмmetadatarewrite. Originalcollectionraw/input/runtime сохранены.
- Remainingcontractmigration требует genuinefutureoriginalclosed features/control иindependentqualification,не переименования8legacyrows. Calendartrain/validation/paperwindows остаютсяfuture; profitablecandidate отсутствует,realorders/risk/activemodel unchanged.


## Продолжение 14 октября: actual primary candidate/registry/promotion replay

- Actualreadonly registry .local/state/primary-registry-readonly-audit-20261014.json:activelegacy09b486e979 event7Oct02:59:38UTC unchanged;candidatea252b48b49 event14Oct04:44:29UTC. Новыйartifact .local/models/pure-python-logistic-candle-v1-20261014-a252b48b49-bc67445df151.json fullSHAbc67445df151e02e91e754f6d0903e5fa08b25ada8cd2e068a04102e235b2826. Registryartifact совпал сlocalfile,referenceincumbentidentity точный. Никакихexternalwrites/publication.
- Actual exact_primary_inputs_and_metrics_verified/current_source_matches_fitted_source=true;train5180/validation1060/test1140;originalinput/runtime verified,normalizationtrainonly,fit/testcutoffs replayed;refittingfalse. Primary этоfixedfutureprice target,не realcashbuytarget.
- Promotion replay изoriginaltestsnapshot иstoredpromotionreference:420unseenexamples,3signals vsmin30;reasoninsufficient_signals,comparisonblocked incompatible_feature_calculation_contract. Candidateclosed_only/boundedwindow120 противincumbentnull/unknowncontract. Accuracy0.7619047619 vsmajority0.7547619048,3signalmean afterassumedcostfixedreturn0.0276287541;cost0.004598980126305915. Этот sparse descriptiveoutcome неincome/trades/independentadmission.
- Sourceboundreplay .local/state/primary-promotion-source-replay-20261014.json сохраняетregistrySHA,artifactaudit,promotion result иcurrentruntime. Freshprimaryfit calibratedpriorobservedfee floor,но cashpreflight0eligibleclosedbuys остаётсяотдельнымtargetgate. Поздниеtrainingruns могут породить новыеcandidateversions; этотreceipt относитсяточно кa252,не автоматически кfuturelatest.
- Код в этом шаге не менялся,примененыexistingauditor/promotionguards;fullsuite1055passed остаётся последней. Gitdiffcheckclean. Обновленыtopcurrentmodel facts,старые12Oct auditreceipts остаютсяисторией. Profitableadmission/currentmodelmigration/futurepaper remainopen.


## Продолжение 14 октября: real archive ambiguous sourcecases

- Новый find_archive_edge_cases.py выполнил streamingreadonly scan годовогоhistorical-universeSQLite. Fixedgeometry stop2%/target4% отbaropen;sourceonly,не strategysearch/fitting. SnapshotSQLiteBEGIN,canonicalquerystreamSHA,fullcount/timebounds,first20originalcaseOHLCVrefs,currentruntime и1024MiBprofile сохранены доminuteoutcomes.
- Actual .local/state/archive-edge-source-scan-20261014.json:2102400candles,56bothbarriersgeometries;0adjacentopeningdrops≥2%. Negativegapresult не означает отсутствиеothergaps/realstopgaptrades. Первые20cases выбраны вsorted symbol/timeпорядке,непоminuteperformance. Длябумажных/реальныхstrategyentries не сертифицированы.
- Новый audit_archive_ambiguous_minutes.py загрузил original1m windows первых20cases;actual20completed/20OHLCVsourceconsistencymatches. Receipt .local/state/archive-ambiguous-minute-source-audit-20261014.json,sourcecapsnapshots/runtime preserved.17ordered_fine_barrier,3unresolved_same_fine_bar_adverse_stop;firstbarrier16stop/4target. Для3cases точный порядокнеизвестен даже1m;неподменёноптимистичнымtarget.
- 9symbols inselected20:ADA/APEX/ATH/AVAX/CRV/DOGE/ENA/ETH/LDO. Coarsebarriergeometry сама по себе не actualstrategyentry:entryslippage/fees/qty/depth/minimums/netlabels отдельно не сертифицированы. Historicalobservationtimes не восстановлены:rawsources observednow,недоисторическойсделки.
- На первых2попытках1024MiBguard не был пройден приavailable≈999MiB. Послеудаления9своихcompletedtestdirs иростаavailable1106MiB guardпройден,scan/minuteinspectioncompleted. Floor не сниженниже1024.
- Fullsuite1058passed/22.08s;geometryexactbounds/adjacentsamemarket/quietbarnofalsecases regressiontests. Gitdiffcheckclean. Sourceambiguouscases теперь получены;manual20complete-tradelabel/fullhistoricalexecutiongate не объявляетсявыполненным поgeometryonly. Liveexecutionpolicy/threshold/model/orders unchanged.


## 14 октября: полные торговые метки для сложных архивных случаев

Реализован scripts/audit_edge_trade_labels.py. Для заранее выбранных 20 свечных случаев загружены исходные окна по 133 свечи: 120 свечей перед входом и полный горизонт удержания. Каждая свеча входа сверена с сохранённым источником. Конфигурация фиксирована: stake6USDT, fee0.001, slippage0.0005, stop0.02, target0.04, hold12, minimum5USDT, step0.000001, preserve_inventory. Это сценарные расходы и ограничения, а не подтверждённые исторические правила девяти монет.

Фактический отчёт .local/state/edge-complete-trade-label-audit-20261014.json:20/20 меток executed,20 выходов stop,19 неоднозначных stop/target,0 положительных net-меток. verify_trade независимо проверил цену/количество, комиссии, net PnL, бинарную метку, время доступности и границы риска. Полные исходные окна, параметры и runtime сохранены. Фактическое правило входа стратегии не проверялось: случаи выбраны по геометрии свечи, поэтому итог не является backtest прибыли стратегии. Состояние historical_execution_rules_certified=false и manual_review_complete=false сохранено.

Команда: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m scripts.audit_edge_trade_labels --scan .local/state/archive-edge-source-scan-20261014.json --output .local/state/edge-complete-trade-label-audit-20261014.json. Полный набор:1058passed/17.17s;git diff --check чистый. Дополнительные искусственные тесты не заменяют выполненный аудит реальных исходных окон. Рабочая модель, правила исполнения и реальные заявки не менялись.

Открыты ручное подтверждение полного набора edge cases, фактические gap/noncloseout случаи торговых меток, исторические фильтры и независимые будущие проверки. Минутный порядок касаний из предыдущего отчёта нельзя автоматически подставлять в эти метки: там границы отсчитывались от сырого открытия, здесь — от цены входа с проскальзыванием.


## 14 октября: календарь будущей walk-forward-оценки

Добавлены walk_forward_schedule.make_schedule и scripts/freeze_walk_forward_calendar.py. Фиксированы шесть окон train120/validation30/test30 дней, шаг30 дней, embargo1 день и максимальная длительность метки4 часа для этой offline-процедуры. Календарь не заменяет отдельные сроки closed cash study и не квалифицирует live TTL36h. Все просмотренные данные до observed_at считаются development; первый purge boundary должен быть позже этого времени.

Оригинальный календарь .local/state/walk-forward-calendars/7e08f025c4ef5697ee28063340879b5d3c4158146d52b2a33436682d4ede53f3/calendar.json сохранён до будущих test outcomes с runtime и parent-design SHA. Первый test_start16Oct2026 00:00UTC(03:00МСК), последний test_end14Apr2027 00:00UTC. Между test окнами пересечений нет; selection разрешён только в test_start..test_start+embargo, с проверкой всех cutoff выбранного артефакта. Сам выбор артефактов сейчас не выполнялся.

Предыдущая запись1cfdf0245bd63c4a90c248f9eca8b45364c5c4c53872b8fd0b1dce3955d8e2e9 сохранена как superseded до selections: добавлена явная проверка UTC offset. Обе записи имеют одинаковые даты; ни одна не содержит выбранных моделей или результатов. Final calendar flags:calendar_frozen_only=true,selection_procedure_preregistered=false,independent_results_completed=false. Не выдавать календарный файл за preregistration всей процедуры поиска.

Проверки1063passed/14.50s,git diff --check чистый. Пять новых tests проверяют6 окон, nonoverlap, reviewed-data purge, UTC и запрет снижения числа окон. Чеклист фиксации календаря закрыт; алгоритм выбора, source-qualified данные, независимая оценка и будущие paper сроки открыты. Рабочая модель и реальные заявки не менялись.


## 14 октября: зарегистрированные validation-правила для walk-forward

Добавлены walk_forward_validation_plan.validation_manifests и scripts/register_walk_forward_validation.py. Для каждого из6 folds объявлены два варианта net-классификатора (class_balance false/true;epochs100,learning_rate0.05,l2 0.001), каждый с полной сеткой thresholds0.3/0.5/0.7. Train label cutoff и effective validation start/end учитывают embargo. Параметры исполнения фиксированы, preserve_inventory включён. Выбор требует verified immutable validation reports, положительных обычного/стрессового net и выполненных требований активности/DD. Отсутствие подходящего варианта даёт no_candidate, а не принудительного победителя.

Корректная декларация .local/state/walk-forward-validation-plans/7e08f025c4ef5697ee28063340879b5d3c4158146d52b2a33436682d4ede53f3/plan-v2.json зарегистрировала12 studies и36 reserved trials в существующем canonical budget aab93fbaa50821bc223be76aabe26d2aa8bb3b4410d130327d7e38519ec4a329. Scope validation_threshold_selection поддерживается существующим readonly evidence verifier. Current source/runtime и selection-source fingerprints сохранены до вычислений. Actual fits/trials completed0;test rewards не читались. Calendar receipt не переписан.

Первая декларация plan.json имела ошибочное literal имя target spot-long-net-return-v2 вместо фактического spot-long-trade-net-v2. Ошибка исправлена до fit: значение теперь импортируется из trade_labels.TARGET_VERSION и проверяется регрессионным test. Оригинальные36 reserves помечены failed invalid_declaration_before_fit в ledger, исходный receipt сохранён. После исправления суммарный family budget usage72/100; бюджет не сброшен, новая pool не создана. Эти36 failed declarations не являются вычисленными отрицательными моделями.

Регистрация фиксирует правила выбора и search grid, а не весь execution pipeline: complete_execution_pipeline_preregistered=false. До независимого test остаются source/data binding, executable fitting/evaluation wrapper и full source qualification. Legacy current-model control остаётся unknown, metadata для него не реконструируется. Не объявлять эту регистрацию завершённой независимой оценкой.

Проверки:3 focused passed/0.12s;full1066passed/23.81s;git diff --check чистый. Проверены complete grids, actual target contract и purged boundaries. Live модель, риск и заявки не менялись.


## 15 октября: первый исполняемый walk-forward train/validation pipeline

Реализованы подготовка и проверка исходных данных (walk_forward_inputs.py, prepare_walk_forward_inputs.py, run_walk_forward_input_job.py), обучение/evaluation одного head (evaluate_walk_forward_head.py) и проверенный выбор между двумя head (select_walk_forward_validation.py). Входы первого fold содержат по43032 свечи BTC/ETH: годовой readonly SQLite плюс оригинальный публичный хвост до15Oct00:00UTC. Test-свечи с16Oct не читались. Full coverage, последовательность timestamps, рынок и OHLCV проверены; оригинальные чанки, public tail snapshots, design/runtime сохранены. Binding SHA616c83052b92e2aca4b62d8f063627bb8685b5aaab1653f9fb897ebe636fcabd.

Первоначально1024MiB guard откладывал запуск при≈830MiB. После роста доступной памяти worker запущен без снижения порога; на53-й секунде RSS≈219MiB (это отдельное наблюдение,не измеренный peak). Оба head последовательно обучены на68516 train examples. Нормализация и class weights рассчитаны только по train, train labels строго до train cutoff. Полные train/model snapshots и source dependencies сохранены до validation расчётов.

Обычная/стрессовая оценка шести исходно зарегистрированных thresholds выполнена. Unweighted0.3:6trades,+0.009276260200824922800USDT,stress−0.094909731382548940800;0.5 и0.7 не торговали. Balanced0.3:921trades,−16.553927523781318788150USDT,stress−32.988410569332534777600;0.5:329trades,−6.019329685417295908200,stress−11.890643878844461684800;0.7:9trades,+0.062900376439674922800,stress−0.095378766661308940800. Drawdown для balanced0.3≈16.60%,0.5≈6.08%. Малые положительные ordinary результаты не выдержали stress/activity gates.

Strict readonly evidence selector подтвердил обе полные immutable grids:eligible thresholds0/0,winner=null,no_candidate_cash_only=true. Report .local/state/walk-forward-execution/fold-0-selection-20261015.json; head directories fold-0-unweighted-20261015 иfold-0-balanced-20261015; binding .local/state/walk-forward-inputs/fold-0-20261015/binding.json. Нет публикации,не выбрана модель для live/paper, FoldSelections freeze не выполнялся до разрешённого календарного окна. Календарь не ускорялся. Новых конфигураций/бюджетов для этих запусков не резервировалось.

Plan-v2 progress-20261015.json из readonly ledger:6completed,30reserved;2actual head fits. Старые36invalid-declaration failed reserves сохранены, family usage72/100 не сброшен. Immutable plan-v2.json с исходным actual_fits_completed0 не переписан: актуальные итоги в новом progress receipt.

Важная граница: validation price bar, закрывающийся ровно на purge cutoff, исключён из equity/risk оценки; evaluation_information_end строго меньше cutoff. Проверены стресс/остатки/нарушения minimums, source gaps/duplicates/NaN, ranking и отсутствие принудительного победителя. Fullsuite1076passed/20.09s,git diff --check иbash -n новых deploy helpers чистые. Input job фактически completed, поэтому retry timer для него не устанавливался.

Полный independent test runner, последующие folds, source-qualified historical execution и future paper остаются открытыми. Статический collection/execution freeze не переписан как completed independent evaluation. Положительная прибыльная стратегия не подтверждена, primary active model/risk/orders не изменены.


## 15 октября: проверенный отказ от торговли для первого walk-forward fold

Добавлены `src/cryptoforge/walk_forward_cash_selection.py` и
`scripts/freeze_walk_forward_cash_selection.py`. Команда повторно проверяет
исходный plan SHA, обе головы, полную сетку candidates, report bytes/SHA,
registered ledger selection и строгую границу evaluation information.
Подмена победителя на cash-only, дубли/неполная сетка и future observations
отклоняются. Receipt явно описывает abstention, не содержит вымышленного
trained_at, прибыли или завершённой независимой оценки. Запись приватна,
атомарна и не заменяет существующее решение; recovery проверяет исходную
идентичность и observed clock. Исторический FoldSelections/model contract
и его source fingerprints не изменены.

Фактический повторный preflight15октября12:33UTC на сохранённых шести
отчётах: `waiting_selection_window`; receipt не создан. Разрешённое окно
16октября00:00UTC–17октября00:00UTC (03:00МСК), test_end15ноября00:00UTC.
Автоматический таймер для этой команды не установлен. До окна можно
проверять evidence, но нельзя выдавать будущую фиксацию за выполненную.
Команда для продолжения из корня проекта:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/freeze_walk_forward_cash_selection.py \
  --plan .local/state/walk-forward-validation-plans/7e08f025c4ef5697ee28063340879b5d3c4158146d52b2a33436682d4ede53f3/plan-v2.json \
  --evidence .local/state/walk-forward-execution/fold-0-selection-20261015.json \
  --receipt .local/state/walk-forward-execution/fold-0-cash-selection.json
```

Independent test runner, candidate/control comparison, последующие folds,
историческая execution qualification и future paper остаются открытыми.
Новых fits/configuration trials и изменений live модели/риска/заявок нет.

Проверки этого шага: full suite **1080 passed /15.41s**; после добавления проверки canonical manifest SHA — **17 focused passed /0.29s**, повторный реальный preflight12:34UTC подтвердил waiting_selection_window; `git diff --check` чистый.


## 15 октября: R5 — сохранность дневного лимита потерь

В `src/cryptoforge/live_risk.py:daily_equity_blockers` устранён silent reset:
раньше повреждённый JSON превращался в пустое состояние и текущая equity
становилась новой дневной базой. Теперь missing/truncated/non-object/invalid
state возвращает blocker новых входов и не перезаписывается. Бесконечности,
NaN, отрицательная база/equity, неположительный loss limit, будущая дата,
несовместимая timezone и naive clock отклоняются. Valid legacy state остаётся
совместимым, текущая дневная база не меняется. Смена дня определяется по UTC,
а не timezone аргумента now. Rollover использует приватный атомарный writer;
стабильный sidecar flock исключает конкурирующий read-modify-write, contention
возвращает blocker без ожидания. Missing baseline требует восстановления по
проверенному исходному состоянию; текущий баланс не назначается новой базой
автоматически. Для первого развёртывания baseline нужно provision отдельно.

Реальный файл risk state прочитан readonly: date2026-10-15,
start_equity14.80500013USDT; он не сбрасывался и не редактировался.
38focused tests passed, включая preserved loss, UTC alias, missing/corrupt/
NaN/future state, simulated atomic replace failure и competing lock. Ошибка
в test helper kwargs исправлена; повторный профильный запуск прошёл.
Источник live_risk не меняет frozen walk-forward learning/execution kernels;
старые study/selection receipts не переписывались. Orders, model publication,
перезапуск live executor и изменение установленных сервисов не выполнялись.
Код используется entry guard следующего обычного запуска; stricter blocker
при потере state является намеренным поведением. R1–R4, R5 host recovery/live
qualification и будущая независимая оценка остаются открытыми.

Итог проверки R5: полный набор **1102 passed /20.03s**; `git diff --check` чистый.


## 15 октября: R4 — резервные данные только для проверки выхода

Новый модуль `src/cryptoforge/exit_data_fallback.py` и opt-in флаг
`--exit-data-fallback` в launcher отделяют резервный источник от immutable
`supabase_executor.py` research kernel. До order-capable вызова основной
reader проверяется на достаточность/свежесть/рынок/закрытость/5m grid/continuity/
finite OHLCV. При data failure отдельный публичный Bybit client запрашивает
121bar, открытая свеча исключается, последние120closed повторно проверяются.
Любой fallback добавляет entry blocker: существующие stop/strategy exits
проверяются, новых buys нет. Источник отмечается в возвращённом решении.
Если оба источника недоступны/некорректны, явно возвращается
exit_data_unavailable/recovery без заявления о выполненном управлении позицией.

Повторяется только получение данных. Вызов run_once, который может отправить
ордер, никогда не повторяется при исключении; временные reader/blockers
восстанавливаются через finally. Frozen core/model/study SHA не переписаны.
24focused tests passed: реальные SupabaseLiveExecutor branches с fake clients,
primary exception/missing/stale, stop sell, запрет buy без иных blockers,
public outage/wrong market/gap/NaN/stale, healthy primary и unknown submission
outcome. Реальных ордеров/сетевых запросов/перезапусков не было.

Установленный service не менялся и новый флаг не включён. Это готовый к
проверке opt-in path, а не устранение всех runtime dependencies: startup
research selection/refresh, journaling после order и решение при полном
отсутствии данных ещё требуют R4/R15. Public closed5m fallback не является
непрерывным real-time stop или биржевым защитным ордером. R4 остаётся открыт.

Итог R4 local path: full suite **1113 passed /17.37s**, launcher `--help` проверен без исполнения цикла; `git diff --check` чистый.


## 15 октября: R4 — durable доставка записей решений

Добавлен `src/cryptoforge/decision_outbox.py`, launcher принимает opt-in
`--decision-outbox PATH`. Adapter перехватывает только trade_decisions upsert
с idempotency_key: exact rows/options сериализуются без NaN, SHA проверяется,
private isolated SQLite фиксирует pending до remote delivery. FULL synchronous
commit, connection cleanup, dedup identical requests, insertion-order flush и
stop-on-first-error проверены. Ошибка remote delivery оставляет original
request pending. Повторяется только Supabase upsert, API exchange недоступен
этому компоненту. Другие таблицы adapter не ставит в эту очередь.

Pending queue после startup flush либо после пары добавляет entry blocker
последующим проверкам; exits сохраняют доступность. Успешная отправка order с
последующим Supabase outage теперь может вернуть ExecutorDecision с original
response, имея local pending receipt. Проверка использует production _record,
реальный SupabaseLiveExecutor и fake exchange/public/remote clients: sell один,
запись pending одна, последующая доставка её не вызывает новый sell.
Проверены restart, exact original delivery, local disk failure до remote
write, corrupt payload, non-idempotent actions, unrelated DB и FIFO replay.

Ограничение: это decision-delivery outbox после exchange submit, не durable
order-intent ledger. Crash/disk failure между submit и local decision record
ещё требует independent order reconciliation и R15. При таком исключении
order-capable call не повторяется. Startup Supabase dependencies, полноценный
outage/recovery и rollout ещё не завершены. Installed service, модель и риск
не менялись; новый флаг не включён. Старый frozen executor kernel сохранён.

Итог R4 decision persistence: **1120 passed /19.39s**, launcher --help проверен без торгового цикла; git diff --check чистый.


## 15 октября: R4/R15 — журнал намерений до отправки market order

Добавлен `src/cryptoforge/order_submission_journal.py` и opt-in launcher flag
`--order-submission-journal PATH`. Private isolated SQLite фиксирует canonical
intent/SHA/link/symbol и prepared status в FULL synchronous transaction до
exchange call. BEGIN IMMEDIATE сериализует конкурирующую подготовку. Ошибка
local prepare не допускает send. Prepared/unknown попытка после timeout/crash
не отправляется повторно; после подтверждённого ACK возвращается exact cached
response без нового send. Link нельзя связать с другим intent. ACK проверяет
retCode/orderId и orderLinkId, если он присутствует; acknowledgment не fill.

Startup reconciliation читает только open/history: positive exact-link,
symbol/side/orderId observation фиксируется отдельно; конфликт блокирует,
отсутствие в ограниченных50history rows не считается неотправленным ордером.
После observed исходный link всё равно нельзя переслать. Unresolved attempt
блокирует действия по тому же symbol и новые buys по любому symbol; sell по
другому symbol допускается. Режим применяется только market submit, используемому
текущим executor; limit-order path этим adapter не квалифицирован.

Проверены commit-before-send, restart после timeout, отсутствие второго send,
изменённый intent, local disk error, crash после submit до ack commit,
положительная/пустая/конфликтующая reconciliation, unrelated-market exit и
неподтверждённый/mismatched response. Совместный production-executor test с
fake exchange, fallback reader и decision outbox подтверждает один sell,
acknowledged intent и pending decision при remote write outage.

Installed service не менялся, флаг не включён; real exchange/API/реальные
ордера не использовались. Для rollout нужна привязка path к account/host и
single-owner policy R1, operational crash/recovery и работа за пределами
bounded history R15. Нельзя удалять журнал для снятия unknown или автоматически
повторять неизвестную попытку. Frozen executor/model/study bytes не менялись.
Общий R4/R15 остаётся открыт.

Итог pre-submit journal: full suite **1132 passed /16.22s**, launcher --help без торгового цикла и git diff --check прошли.


## 15 октября: R1 — привязка журнала и local single-process ownership

Добавлен `src/cryptoforge/execution_ownership.py`. При opt-in
`--order-submission-journal` launcher получает lease до сетевых действий
run_cycle и держит её до выхода, включая exception path. Journal binding
фиксирует SHA API-key, endpoint, SHA machine-id и resolved path. Секретный
ключ/secret и raw machine-id в файлы не записываются. Private immutable
sidecars создаются atomic exclusive link. Existing unbound DB не принимается
автоматически; пропавшая bound DB, другой host/key/endpoint требуют recovery.

Общий local flock по credential/endpoint препятствует второму процессу даже
при выборе иного journal path. Persistent owner registry запрещает смену
journal path после restart: нельзя уйти от unresolved attempts в пустую DB.
В тестах проверены restart, identity mismatches, competing owner, new-path
bypass, missing/unbound DB и отдельный реально запущенный процесс с kill:
OS освобождает lock, а содержимое журнала не сбрасывается. Multiprocessing
использует spawn, чтобы не fork-ать многопоточный pytest процесс.

Граница: credential fingerprint не является verified exchange account UID.
Два API-key одного account не объединяются, distributed/multi-host lease не
реализована. Полный R1 runtime contract, key rotation/host transfer и rollout
остаются открытыми. Installed service без opt-in journal flag не изменён;
live order calls/remote account queries не выполнялись. Установленная модель,
численные risk limits и frozen studies не менялись.

Первый полный прогон нашёл устаревшее ожидание в тесте: новый owner registry
закономерно отклонял смену пути раньше проверки legacy adoption. Fixture
разделена по credentials, focused20passed; затем выполнен новый полный прогон.

Итог local ownership: **1140 passed /24.37s**, включая spawn-process kill/restart; launcher --help и git diff --check прошли.


## 15 октября: R2 — операторские controls перед order submit

Добавлены `execution_controls.py`, paused example config и runbook
`docs/EXECUTOR_CONTROLS.md`. Launcher принимает opt-in --execution-controls PATH.
ControlledOrderClient оборачивает market/limit submissions, внутри submission
journal: controls reread выполняется после intent commit и перед exchange call.
no_new_entry блокирует Buy, разрешает Sell с остальными guards; kill_switch
блокирует обе стороны. Kill не является автоматическим close/cancel.
Missing/unreadable/malformed JSON, duplicate fields, неверные bool/schema
блокируют обе стороны. Оба false снимают только operator blocker, не admission.

OrderControlBlocked фиксируется journal как known blocked before submit,
отдельно от unknown exchange outcome; этот link не пересылается. Проверены
mid-cycle toggles, guard после prepare, limit path, invalid states и настоящий
executor stop/fake exchange: pause не мешает sell, kill запрещает его. Код
старого frozen executor kernel/исторические source fingerprints не переписаны.

Installed service без нового флага, operational smoke и полный admission
не выполнялись; model/risk defaults не менялись. Открытые R2/R3/R4/R15
не закрыты локальной проверкой. Controls нужно обновлять атомарно; deleting
journal/ownership не является recovery. Семантика и ограничения в runbook.

Итог R2 controls: **1152 passed /23.01s**, launcher --help без торгового цикла и git diff --check прошли.


## 15 октября: R3 — повторная проверка текущих лимитов на submit path

Новый `submission_risk.py` и opt-in --submission-risk-guard в launcher
повторно проверяют current absolute CLI stake/position/daily-loss перед Buy.
Guard находится внутри JournaledOrderClient, перед Controls/exchange send.
QuoteCoin qty Buy валидируется отдельно от baseCoin qty Sell. Повторно читаются
account equity/USDT wallet и inventory; malformed/duplicate/missing/NaN данные
отклоняются. Daily baseline проверяется существующим R5 механизмом без reset.
Текущие dynamic equity capacity/material-position policy сохраняются.
Изменение holdings между покупками учитывается, startup snapshot недостаточен.

OrderControlBlocked сохраняет известный local отказ, не unknown submission.
Sell не зависит от entry-risk balance queries; limit path явно не поддержан,
чтобы base quantity не обходила quote stake cap. Tests проверяют изменившиеся
holdings, oversize/nonpositive/nonfinite qty, current daily loss, missing state,
API outage, incomplete inventory и production executor entry с fake clients:
при занятых capacity slots Buy не достигает exchange.

Ограничения R3 остаются явными: walletBalance не free/reserved-funds proof;
pending accepted orders, persistent peak drawdown, risk-per-trade/position
percent limits и full HardRiskConfig wiring не закрыты. Численные defaults
не изменялись, installed service без нового флага. Реальных сетевых запросов,
orders, публикации моделей и изменения frozen research kernels не было.

Итог R3 local submit guard: **1170 passed /21.17s**, в том числе18новых проверок; launcher --help и git diff --check прошли.


## 15 октября: R3 — резерв USDT и ожидающие Spot покупки

Новый `spot_reservations.py` подключён opt-in --spot-reservation-guard,
требует --submission-risk-guard. Wallet fields берутся из original coin rows;
неизвестные/empty/неfinite суммы не default0. Для ограниченного cash scope
borrowAmount/spotBorrow/totalOrderIM/totalPositionIM должны явно равняться0;
locked иbonus исключаются из USDTwallet. Для capacity используется меньшая
из conservative cash bound и отдельно прочитанного USDT wallet balance.

Open orders запрашиваются через existing private GET, categoryspot/openOnly0,
limit50,безsymbolfilter,с nextPageCursor до terminalpage. Loop,duplicates,
malformedcategory/cursor,API error/page ceiling20 не доказывают свободную
capacity и блокируют Buy. Pending Buy symbols объединяются с material held
symbols; pendingtarget блокирует новуюпокупку. LeavesValue не вычитается снова
из cash, поскольку knownlocked уже исключён. Sells не требуют этих запросов.

38focused passed, включая source-pagination params, locked/bonus, missing/
borrowed/NaN amounts, repeated/truncated cursors, duplicateorders, pending
capacity иsame-symbol/dedupheld. Реальных account/order calls не было.
ДокументацияBybit walletbalance/openorders проверена, ссылкивrunbook.

Открыто: REST snapshot latency/consistency, ACK-before-order-visibility и durable
local reservations; полная UTA buyingpower/otherproduct collateral не доказана.
Percent limits/peakdrawdown и operational rollout всё ещё открыты. Installed
service иriskdefaults не менялись, новый флаг не включён. Frozen research
kernels/study fingerprints сохранены.


## 15 октября: R3 — durable локальные резервы до видимости ACK

Предыдущий reservation шаг полностью проверен:1190passed/16.80s.
Добавлен --local-order-reservations, требует submission-risk-guard и bound
order-submission-journal. Buy-reserves читаются из сохранённых canonical
intent/SHA/status: prepared/unknown/acknowledged/observed учитываются после
restart, blocked/released_unfilled не занимают средства. Текущийpreparedlink
исключён: проверка не резервирует заявку против самойсебя. Risk guard считает
union materialheld/remotepending/localreserved symbols и conservative quote
cash после вычитания local reserves. Stale remote snapshots больше не являются
единственным локальным основанием для следующей покупки.

Reconcile рассматривает ACK/observed Buy, требует agreement с ранее known
exchange orderId и не снимает резерв по отсутствию rows. Только positive
terminalcancel/reject/deactivate с explicitzero cumExecQty/cumExecValue даёт
released_unfilled. Partial/filled/missingamounts остаются reserved. Старыйlink
не отправляется вновь послеrelease. Tests:60focusedpassed/0.50s, включаяrestart,
emptyhistory,current-intent exclusion,двепокупки/thirdblocked,quote depletion,
zero/partial/filled proof и conflictingknownorderID.

Открыто:source-qualified settlement послеfilled/closeout; local reserve сейчас
консервативно добавляется поверхremote locked bound и может блокировать лишнее.
Это не точная buyingpower/equity/profit accounting и не production-ready full
reservation lifecycle. Installed service/модель/численныеrisklimits не менялись,
API/order network calls не выполнялись. Frozenresearchcore/sourceSHA сохранены.

Итог remote/local reservations: full suite **1200 passed /18.76s**; CLI dependency rejection проверен до client/network initialization, git diff --check чистый.


## 15 октября: R3 — narrow proof освобождения резерва закрытого цикла

Добавлен `reservation_settlement.py` и opt-in --settle-closed-reservations,
требует local-order-reservations. Narrow collector получает через existing
private GET exactorderId history/executions, полные cursorpages, open symbol
orders и explicit finalbasewallet. КонтрактBybit проверен поofficialdocs,
ссылкивrunbook; actualnetwork/account calls не выполнялись в этой проверке.

Verifier ограничен одной retained Buy и knownlocal Sales: fullyFilled exact
orders, complete cumulative qty/value, unique trade execIDs, nonnegative
knownfees вbase/USDT, noextrafees, execution arithmetic, request quote/base
units, full chronological inventory consumption. Basebuyfee уменьшает received,
baseSellfee увеличивает consumed. Требуется explicitzero finalwallet/locked/
borrow иnoopenorders. Unknown/partial/multi-buy/thirdfee/dust cases retain reserve.
При proof сохраняются originalresponses,params,sourceSHA,observedclock и
released_closed; старыйlink не пересылается. Это reservation evidence,
profitability_established=False,не independent доходность.

Tests покрывают complete cycle/restart,noresubmit,partial/gaps/duplicates,
wrongids/market/links,fees,chronology,pending,remainingbalance,retentionmissing,
multiplefills иbaseSellfee. 18focusedpassed/0.10s. Сравнение Decimal scale в
новом тесте исправлено на численное: .999 и .9990 равны, форматне gate.
CLI dependency rejection происходит до client/network initialization.

Operational source qualification/latency/retention, partial/multi-lotFIFO,
thirdtokenfees иrollout остаются открытыми. Installed service,primary model,
riskdefaults иfrozenresearchkernels не менялись; реальныхordersнебыло.

Итог closed-cycle settlement: full suite **1218 passed /19.58s**; CLI dependency rejection до network и --help проверены, git diff --check чистый.


## 15 октября: R3 — terminal partial execution settlement

Narrow closed proof расширен доv2 с terminal_order_statuses. Допускаются
Filled иSpot PartiallyFilledCanceled с positive source executions; обычный
PartiallyFilled остаётся open иretainsreserve. Status semantics сверены по
Bybitofficialenum,ссылкавrunbook. Complete cumExecQty/cumExecValue должны
совпадать сuniqueoriginalfills. Buy сравнивает executedquotevalue сoriginal
quotebudget; Sell сравнивает executedbase сrequestedbase. Partial Sell leaves
не превышает remainder; FilledSell обязан исполнить originalrequest целиком.

Поддержаны partialBuy->closedreceivedinventory и partialCancelSell->ещёодна
terminalSale. Fees, chronology, zero wallet/noopenorders иsourceSHA остаются
обязательными. Cancelled/Rejected/Deactivated сявнымиzero fills сохраняют
отдельный shortcut; contradictory PartiallyFilledCanceled снулевымиtotals
больше не снимает reserve безexecutionproof. Старые v1 receipts не переписаны.

28focusedpassed/0.17s, включая productioncollector/fakeprivateAPI сterminal
partial sources. Unknownstatus,openpartial,zeroexecution,overbudget,badleaves,
missingfills,residualinventory не даютrelease. Реальныхaccount/ordercalls
не было;installedservice/riskdefaults/primarymodel/frozenresearchcore не менялись.
Actual-account partial/dust, multipleBuyFIFO,third-tokenfees иrollout открыты.

Итог terminal partial settlement: full suite **1229 passed /19.96s**, git diff --check чистый.


## 16 октября: фактический observed выбор первого walk-forward окна

UTCclock04:41:15 проверен отдельно. В04:41:22.290230UTC (07:41МСК) штатной
командой freeze_walk_forward_cash_selection повторно проверены plan-v2,
обе головы/6original complete registered reports, ledger, SHA и purge cutoff.
Впервые создан observed receipt внутри allowedselectionwindow16Oct00:00UTC–
17Oct00:00UTC: `.local/state/walk-forward-execution/fold-0-cash-selection.json`,
SHAe0d96b93c5925e840944689474f9fd24e93ce7842d040ec4252736dc8220cc98.
Policy no_candidate_cash_only, independentprofitabilityFalse,livepromotionFalse.
Это выбор исследовательского fold, не отключение/замена рабочего бота.

Добавлены walk_forward_cash_test.py иrun_walk_forward_cash_test.py. В
04:42:52.475205UTC зарегистрирован отдельный virtualidlecash component job:
`.local/state/walk-forward-execution/fold-0-cash-reference-job-20261016.json`,
SHA95d5b1af2eb7db0886a84ceabf5a110a3231da8ab5fb53c751c39e587d0348af.
Доeligible teststart зафиксированы initialcash100 изoriginalprotocol, original
plan/evidence/selection references+SHA, currentimplementation hashes иruntime.
Status повторно revalidates6grids/ledger/inputbytes иdeclaredcapital; source
drift/clock/late registration не допускаются. Job не является новой trading
configuration, budget/trials/fits не увеличивались.

25focusedpassed/0.27s. Actualstatus waiting_eligible_test_start. Пробныйactual
`evaluate`16октября04:43UTC отклонён ValueError cash test window has not ended;
файл fold-0-cash-reference-result-20261016.json отсутствует. Ранний отказ
ожидаемый guard, а не завершённый результат. Testcandles/rewards не читались.
Eligibleteststart17Oct00:00UTC (03:00МСК), testend15Nov00:00UTC (03:00МСК).
Послеокна virtualcash result может констатировать только0trades/0net/stress
при предположении idlevirtualcash безпроцентов/переводов/fees. Это не реальный
account income, не profitable model и не full candidate/control comparison.
Nativecontrol остаётся not_evaluated,currentmodelcontrol unknowncontract,
independentprocedurecompletedFalse. Автоматическийтаймер не создавался.

Открыто: full independent runner/controls/последующиеfolds, source qualification,
R1–R5/R9–R15 operational work. Liveorders/services/risk/model не менялись.
Команды продолжения:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/run_walk_forward_cash_test.py status --job .local/state/walk-forward-execution/fold-0-cash-reference-job-20261016.json
# evaluate допускается только после15Nov00:00UTC; output должен быть новым.
```

Итог16октября: **1240 passed /25.39s**, actualselection иjob SHA сохранены; prematureevaluation output отсутствует, git diff --check чистый.


## 16 октября: R3 — multi-buy FIFO cohort settlement

Добавлен verify_closed_cohort для нескольких local Buy одного symbol и
известных closing Sales. Каждый original terminal order, full fill totals,
fees и request units проверяет existing verifier. Quantity events сортируются
по execution time; FIFO queue запрещает продажу до available Buy и расход
неизвестного initial stock. Received base net fee/consumed base plus fee
должны полностью закрыться; explicit final zero wallet/no open orders обязательны.
Duplicate order/link/execIDs запрещены. Mixed Buy/Sell timestamp ties ambiguous
и сохраняют резерв; same-side execId tie объявлен quantity-only policy,
не actual venue/cost basis/profit qualification.

Collector группирует cohort, сохраняет общие original API responses/source SHA,
observed time и quantity FIFO allocations. Journal release_closed_cohort
проверяет expected intent SHA/current status внутри BEGIN IMMEDIATE и
исполнения ранее released proofs; все Buy обновляются в одной transaction.
Повторное использование sales для следующего cohort запрещено. Injected
failure на втором row откатывает первый row.

39 focused passed/0.37s: interleaved Buy/Sell, Sell across two lots,
negative inventory, ambiguous timestamps, duplicates, residual wallet,
source collection/restart, atomic failure и reused proof. Реальных API/orders
не было; installed service, model/risk defaults/frozen research core не менялись.
Entry policy не расширена: новая сверка не разрешает покупку same-symbol
при existing local reserve. Открыты actual-account multi-buy/dust/third-token
sources, full global coverage, snapshot latency и operational qualification.
Release/FIFO quantity proof не доказывает прибыльность или independent admission.

Итог multi-buy FIFO: full suite **1251 passed /23.05s**, git diff --check чистый; operational/actual-account qualification не закрыта.


## 16 октября: R3 — сохраняемый observed-equity drawdown

Новый portfolio_drawdown.py и explicit opt-in drawdown-state/threshold
подключены к startup и market Buy submit guard. State привязан к hash
credential/endpoint/host scope и threshold; peak, last equity и observation
проверяются до atomic update. Peak не уменьшается и не сбрасывается по дням.
Порог decline>=limit (finite>0<=.10) включает breach latch; последующая equity
recovery latch не снимает. Missing state никогда не становится новым peak.
Corrupt/duplicate/NaN/future/wrong-owner/threshold/clock-rollback/lock/write
failures блокируют Buy без перезаписи исходного состояния. Sell не зависит
от entry drawdown queries/state. Journal отличает known local block от unknown.

56 focused passed/0.32s: grow/restart/day rollover, exact boundary latch,
equity recovery, invalid state, atomic replace failure, nonblocking contention,
submission/journal integration и Sell при удалённом peak state. CLI требует
явных state/threshold, submission-risk-guard и bound journal до network init.
Actual peak state не создавался и installed service не менялся.

Ограничения: observed peak не continuous historical maximum, account equity
не cashflow-adjusted; реальные initial peak/source marks, transfer treatment,
operational recovery/full HardRiskConfig admission ещё открыты. Primary model,
riskdefaults/frozenresearchcore не менялись; реальных API/orders не было.

Итог observed drawdown: full suite **1267 passed /15.05s**, CLI dependency rejection до client/network init и git diff --check прошли.


## 16 октября: R3 — explicit fractional exposure/planned risk

Новый fractional_risk.py подключён через opt-in --fractional-risk-policy.
Immutable parsed policy требует explicit decimal position fraction<=.05,
planned stop-risk fraction<=.005 и roundtrip cost assumption; stop distance
берётся из текущего CLI executor. Before market Buy existing symbol USD value
включая dust + quote request сравниваются с current equity position budget;
quote×(stop+cost) — с planned risk budget. Exact boundaries разрешены,
oversize/nonfinite/unknown inputs отклоняются без auto resizing. Sell unaffected.
Remote/local reservation guards и bound journal обязательны для CLI path.
Policy original SHA сохраняется в risk snapshot, loaded values фиксированы
на цикл. Actual installed limits не менялись, разрешающая policy не создавалась.

30 focused passed/0.29s: exact budgets, oversize, dust, cost-only risk breach,
invalid bounds/NaN, required decimal costs, current-equity submit и Sell.
CLI dependency rejection проверен до credential/network initialization.
AGENTS.md прочитан; обязательный typesafe-ai skill загружен. Live docs index
доступен, building-guide Markdown/normal page tools вернули error; интеграция
не нужна: skill явно оставляет точные расчёты и execution в ordinary code.
TypeSafe dependencies/API inference calls не добавлялись.

Открыто: реальные cost/gap/stop исполнения, aggregate existing-position stop
risk и full HardRiskConfig/runtime admission. Planned loss не maximum possible
real loss. Installed service/primarymodel/frozenresearchkernels не менялись;
private API/order calls не выполнялись.

Итог fractional entry limits: full suite **1279 passed /16.88s**, CLI dependency rejection и git diff --check прошли.


## 16 октября: R4 — проверка всего launcher cycle при Supabase outage

Исправлен реальный startup abort: исключение NightResearchSelector раньше
не позволяло дойти до holdings/exits. Теперь сохраняются CLI fallback pairs,
include_held_pairs добавляет позиции, pair_source=night_research_unavailable,
новые entries явно заблокированы. Без research source флаги research-entry
не активируются. Frozen supabase_executor.py kernel не менялся.

Diagnostic risk snapshot перенесён после формирования outbox/control/
reconciliation blockers и заменён atomic private writer. В configured_protections
отдельно перечисляются включённые слои; scope не заявляет qualification.
OSError diagnostic write добавляет entry blocker, не обрывает exits.

19 focused passed/0.62s: новый full run_cycle harness использует production
executor/fallback/guards/journals и fake exchange/public/remote clients.
При research+Supabase outage и entry pause выполнен один fake stop Sell,
intent ACK сохранён, decision pending; повтор цикла не отправляет order снова.
Empty holdings не дают Buy; kill blocks Sell; diagnostic write failure не
прерывает exit. Return code1 честно сохраняется при unhealthy remote journal.
Private API/orders/services не запускались; installed flags, модель,
численные risk limits и frozen research kernels не менялись.

Обязательный TypeSafe skill/AGENTS прочитан; здесь точные rules/execution в
ordinary code, semantic inference не нужен. Sandbox обновлён: tests/tmpfiles
перенесены в разрешённый /tmp, без записей в /dev/shm и вне workspace roots.
Actual-account outages/private balances/marks, multi-host ownership,
source/operational admission ещё открыты. Fake-client cycle не live smoke.

Полный прогон этого шага: **1282 passed,1 failed /46.01s**. Единственный failed — public Bybit integration (`test_bybit_public_market_data_live`): DNS Temporary failure in name resolution в restricted network environment. Это не подтверждённая remote qualification; private API/real orders не вызывались. Повторный non-integration прогон выполняется отдельно, integration failure не скрывается.

Итог R4 launcher wiring: **1282 passed,1 deselected /41.43s** в повторном non-integration прогоне; ранее public integration failed DNS, поэтому complete live integration не заявляется. `git diff --check` чистый.


## 16 октября: R4 — account-wide entry outage без раннего abort exits

Новый entry_account_snapshot.py строго проверяет equity/USDT wallet и весь
inventory до sizing. Exception, NaN/nonfinite/negative values, None/empty/
missing USDT/duplicate coins не превращаются в healthy zero balances.
Launcher сохраняет account=None, positions/capacity=None, entry slots0 и
explicit Buy blocker; known pairs продолжают per-symbol exit branch.
Daily и peak state при unknown equity не обновляются. Diagnostic хранит
nullable fields/statusunknown; exit успех не превращает degraded cycle в0.
Return status также учитывает pair failures.

include_held_pairs больше не падает на invalid valuation/coin data: known
valid symbol с unknown value сохраняется для fresh per-symbol check; invalid
candidate quantity не обрывает другие пары. При отказе именно private
per-symbol quantity order не отправляется. Unknown account data не является
разрешением на вход или продажу без проверки количества.

16 initial focused passed/1.23s: balance/inventory exceptions, None inventory,
NaN equity/value, duplicate coin, no baseline reset, nullable diagnostics,
Buy blocked при healthy journal и private quantity outage без blind Sell.
Дополнительно проверен invalid candidate quantity с продолжением других pairs.
Private API/real orders/services не вызывались; installed flags/модель/численные
лимиты/frozen research kernels не менялись. TypeSafe skill прочитан, exact
rules остаются ordinary code без AI inference dependency.

Открыто: реальная discovery вне known pairs при inventory outage, private
exchange data quality/latency, full host/restart/outage qualification и rollout.
Полный сетевой integration в restricted environment не повторялся: прежний
DNS failure остаётся невыполненной remote qualification. Tests под /tmp.

Итог account-wide outage: **1292 passed,1 deselected /42.78s**, git diff --check чистый. Сетевой integration не запускался повторно, remote qualification остаётся открытой.


## 16 октября: R4 — восстановленный inventory используется для exit discovery

read_entry_account_snapshot возвращает copy точных validated coin rows,
использованных при sizing. Launcher дополняет ими material held pairs после
успешного account snapshot. Если ранний discovery wallet query упал, но
следующий запрос восстановился, позиция вне CLI fallback universe теперь
проверяется в том же цикле, без третьего wallet query. Уже включённые pairs
не дублируются, refresh вызывается только для newly recovered pairs.
Diagnostic сохраняет evaluation_pairs, неизвестные account rows по-прежнему
не дают entry permission и не маскируются нулевыми balances.

19 focused passed/0.54s: initial inventory exception→successful sizing rows→
outside-fallback HYPE position→one fake stop Sell; exactly2wallet calls;
повторяющиеся fallback/held rows не создают duplicate exit. Existing private
quantity/data checks, Buy blockers, journals и controls остаются обязательными.
Реальных API/orders/services не вызывалось; installed flags, model/risk defaults
и frozen research kernels не менялись. TypeSafe/AGENTS прочитаны; это exact
source reuse/rules, без semantic AI integration.

Открыто: полная недоступность inventory/private APIs, unknown historical
holdings, source latency и operational validation. Сетевой integration не
перезапускался из-за известного restricted-network DNS limitation; он не
считается успешным. Локальный regression suite выполняется отдельно.

Итог recovered-inventory wiring: **1294 passed,1 deselected /23.11s** (`-m not integration`); 19 профильных тестов прошли. Сетевой integration исключён из этого прогона; предыдущая ошибка DNS и реальная private API/операционная квалификация остаются открытыми. Реальные заявки не отправлялись, новые защитные флаги сервиса не включались.

## 16 октября: R4 — полный сбой источников цены не считается успешным циклом

- [x] При недоступности/невалидности primary и public candles fallback возвращает `recovery_required`, а launcher учитывает результат как failure даже при успешном journal reconciliation.
- [x] На executor сохраняется entry blocker до конца текущего цикла: следующая пара с рабочими свечами не может открыть Buy. Fresh cycle после восстановления не наследует transient blocker.
- [x] Existing stop Sell продолжает работать после восстановления свечей даже с сохранённым entry blocker. Отдельно проверено, что existing stop не вызывает ML registry ни с primary, ни с public fallback.
- [ ] Реальная private/public source qualification, длительность аварии/задержки и operational smoke остаются открытыми. Этот пункт не закрывает R4 целиком и не доказывает непрерывную защиту stops.

Изменены отдельный fallback wrapper и launcher; frozen executor/research kernels не менялись. Прогон использует fake clients; реальные заявки и rollout отсутствуют.

Проверка total-price-outage: **1299 passed,1 deselected /38.33s** (`-m not integration`), `git diff --check` чистый. Remote integration не запускался, предыдущая DNS/source qualification остаётся открытой.

## 16 октября: R5/R15 — проверенный перенос исходной daily baseline

- [x] Добавлен `daily_risk_recovery.py` и CLI `scripts/recover_daily_equity_state.py`: backup требует independently reviewed original state SHA, restore — retained backup SHA и тот же explicit account scope.
- [x] Исходные bytes сохраняются без пересчёта equity; только current UTC day, строгая finite/nonnegative schema и duplicate-field checks. Не принимаются future/outdated backup, неверный scope/clock/hash и неизвестные поля.
- [x] Общий с daily gate `.lock`, private atomic no-overwrite publication с fsync: существующий/повреждённый destination не заменяется. После loss3USDT при limit2USDT restored baseline продолжает блокировать Buy.
- [x] 56 focused tests passed /0.49s (recovery + daily state). Выполнен отдельный CLI process drill в двух `/tmp` каталогах; original SHA8893711e7a8bd53d376152134f54a45f54ec6b4abc9fced0ca39e1a8ae3d5ea0, backup SHA5d52ed799ac0f6ea74a720e331e59ad1b7a38cc56b7e609ce4b2bed4fed12d06. Receipt `.local/state/daily-risk-recovery-cli-drill-20261016.json` содержит implementation hashes и явный isolated scope.
- [ ] Scope проверяется как explicit assertion, не verified exchange UID. Реальное перемещение между хостами, восстановление production corruption, order/drawdown/ownership/outbox backup и actual-account qualification ещё открыты; весь R5/R15 не закрыт.

Runbook: [DAILY_RISK_RECOVERY.md](DAILY_RISK_RECOVERY.md). Действующий daily state, сервисы, journal и замороженные исследовательские kernels не менялись; API/ордера не вызывались. Инструмент всегда возвращает live_admission_granted=false.

Итог R5 daily baseline recovery: **1333 passed,1 deselected /37.50s** (`-m not integration`); `git diff --check` чистый. Сетевая integration/actual-account qualification не запускалась; прежняя DNS limitation остаётся открытой. Следующая работа: оставшиеся R1/R2 runtime contract/admission и operational R3–R5, затем R6–R11 без повторения существующих архивных receipts.

## 16 октября: R1/R2 — runtime-bound operator entry approval

- [x] Подготовлены opt-in `--entry-runtime-approval PATH` + `--entry-model-sha256 SHA`: exact canonical runtime fingerprint связывает credential/endpoint/host, CLI limits/flags, persistence/control paths, parsed policy SHA и явный source surface. Raw secrets не сериализуются; UID verification не заявляется.
- [x] Strict approval schema/real bool/unique fields, aware valid_from/until, duration<=24h, current time и exact fingerprint проверяются заново перед Market Buy. Initial source binding нельзя заменить новым approval в середине цикла; source/config/policy drift блокирует вход.
- [x] ML gate обязателен, active model pin исключает silent adoption другой модели. Submit требует original model input с тем же artifact SHA и symbol. Limit Buy outside contract запрещён; Sell не зависит от entry approval.
- [x] Проверена цепочка actual launcher/fake clients: journal prepare → risk queries → controls → approval → raw submit. Первичный regression поймал потерю inner wrapper при ControlledOrderClient(bybit); wiring исправлен на сохранение order_client. Revocation во время risk query теперь даёт 0 sends/status=blocked; valid synthetic approval даёт один fake acknowledged Buy. Missing approval сохраняет existing stop Sell.
- [x] 69 focused tests passed /1.72s (runtime approval, outage cycle, controls). Неполный CLI configuration отклоняется до credentials. Полный snapshot сохраняет контракт/его SHA отдельно от qualification claim.
- [ ] Full strategy/paper admission, actual capital/permissions/UID, environment/multi-host qualification и операторский rollout остаются открытыми. Это necessary local runtime binding, не автоматическое подтверждение этих evidence. Разрешающий production approval не создан; installed service не менялся.

Runbook: [EXECUTOR_RUNTIME_APPROVAL.md](EXECUTOR_RUNTIME_APPROVAL.md). Frozen executor/model/research kernels не менялись, только отдельные adapters/launcher/tests/docs. Все sends в проверках были fake, реальных заявок и API вызовов не было.

Итог runtime approval/model pin: **1376 passed,1 deselected /42.60s** (`-m not integration`), `git diff --check` чистый. Дополнительный regression проверяет expiry во время проверки контракта: время для TTL берётся после file IO. Сетевой integration не запускался; прежний DNS failure/remote qualification остаются открытыми. Общие R1/R2 не отмечены выполненными: следующий шаг — отдельный полный evidence-based strategy/paper/runtime admission, verified account scope и operational qualification без выдачи автоматических разрешений из development результатов.

## 16 октября: R1/R2 — authenticated account/key evidence adapter

Проверены existing paper acceptance/activation formats: они явно research-only,
с live_promotion_allowed=false. Их не превращали в разрешающие live evidence.
Следующая выполненная зависимость допуска — factual UID/permissions matching,
отдельно от полного strategy/paper admission.

- [x] Добавлен opt-in `--entry-account-policy PATH` (требует runtime approval): strict reviewed subaccount UID/parent/IP/freshness policy и authenticated GET `/v5/user/query-api`. Runtime contract связывает path/SHA и source adapter; старый permissive get_api_key_audit не используется как доказательство.
- [x] Проверяются key echo, explicit empty secret, exact UID/parent/isMaster, strict integer readOnly/uta/type, non-FIX bool, complete core permission lists и exact whitelist. Only SpotTrade; любые Wallet/derivatives/unknown nonempty grants запрещают Buy. Missing/NaN-like malformed fields и stale/future original server time не получают safe defaults.
- [x] Fresh query идёт после risk/controls и до final runtime TTL. Повторная смена Wallet→Withdraw после startup даёт 0 sends и journal blocked. Correct synthetic account/full fake launcher даёт один acknowledged Buy. Slow key query не продлевает approval, existing stop Sell не зависит от нового entry check.
- [x] 127 focused tests passed /2.21s (account verification/runtime approval/outage), затем добавлен отдельный slow-query TTL regression для полного набора. В диагностике только safe projection и SHA, без raw response/API key/secret/note; original permissions не меняются.
- [ ] Actual selected account/permissions/IP/latency qualification не запускалась. Existing credential lease сохраняет account_uid_verified=false; cross-key same-account и multi-host ownership открыты. Full evidence-based strategy/paper admission не реализован этим шагом; R1/R2 целиком не закрыты.

Runbook [EXECUTOR_ACCOUNT_VERIFICATION.md](EXECUTOR_ACCOUNT_VERIFICATION.md), API поля сверены по official Bybit key-info docs. Installed service/permissions/капитал/модель не менялись, production policy/approval не создавались, реальные API вызовы/ордера в этом шаге отсутствуют. Frozen research kernels сохранены.

Итог authenticated account/key adapter: **1446 passed,1 deselected /44.12s** (`-m not integration`), `git diff --check` чистый. Existing network integration не запускался; прежний DNS failure и actual-account/source/host qualification остаются открытыми. Следующий незакрытый механизм R1 — account-wide ownership для разных ключей одного UID без automatic journal adoption/reset; полный strategy/paper evidence admission также открыт.

## 16 октября: R1/R15 — UID lease для разных ключей одного счёта

- [x] Подготовлен opt-in `--account-ownership-guard`: общий UID+endpoint flock перед existing credential lease, private immutable UID registry и отдельный journal.account-owner sidecar. New bootstrap требует fresh strict authenticated account proof, existing credential-only/unbound journal автоматически не принимается.
- [x] Owner фиксирует key/host/UID/parent hashes, policy path/SHA, journal path/device/inode и исходную safe projection. После restart новая key/path/policy или replaced/missing journal не создают новый пустой namespace; inconsistent/partial sidecars требуют explicit recovery. Старый credential record не переписан и остаётся false в своей прежней UID assurance.
- [x] Active PID/lock inode/owner bytes/journal inode/credential scope проверяются до evaluation и raw submit; потеря lease запрещает новые Buy/Sell. После context escaped client не отправляет. Cache исходной UID binding позволяет тому же владельцу взять lease без нового key-info query; current entry permissions по-прежнему проверяются отдельно.
- [x] 144 focused tests passed /2.66s: real spawned process с другим key блокируется; kill/restart сохраняет original DB bytes. Actual launcher main не пускает второй key в cycle; full fake run_cycle с bound lease сохраняет existing stop Sell при query-api outage. Foreign UID/bootstrap failure не создаёт journal; raw upstream errors не раскрываются.
- [ ] Real account bootstrap, миграция production/legacy journal, смена key/IP и recovery ещё не квалифицированы. Защита требует одного canonical endpoint/shared local lock directory и cooperating режима. Endpoint aliases, legacy/off-mode executor, другой host и distributed fencing остаются открытыми; весь R1/R15 не закрыт.

Runbook: [EXECUTOR_ACCOUNT_OWNERSHIP.md](EXECUTOR_ACCOUNT_OWNERSHIP.md). Installed service не менялся, реальные API/orders не выполнялись, production ownership files не создавались/не менялись. Frozen model/executor/research kernels сохранены. Full strategy/paper admission остаётся обязательным отдельно.

Итог local cross-key account ownership: **1469 passed,1 deselected /27.06s** (`-m not integration`), `git diff --check` чистый. Network integration не запускался; previous DNS/actual-account/source/host qualification остаются открытыми. Следующая работа R1/R15 — reviewed migration/recovery legacy journal и отдельная multi-host/endpoint canonicalization процедура; R2 full independent strategy/paper/runtime admission также открыт. Никакой existing journal не принят автоматически и rollout не выполнялся.


## 17 октября: R1/R15 — reviewed миграция journal к UID

- [x] Prepare/reviewed-plan-SHA/apply реализованы для существующего согласованного
  credential-bound DELETE journal. DB bytes/inode, original owner records,
  unknown/ACK reservations сохраняются; atomic independent backup и exact
  partial resume проверены. Reserved/ancestor paths, symlink/hardlink backup,
  malformed intent, source/inode drift и UID/key API failures блокируются.
- [x] 65 профильных tests passed /3.91s; полный local suite:
  **1534 passed,1 deselected /28.56s** (`-m not integration`). Отдельные CLI
  процессы с fake client и UID lease restart прошли; receipt
  `.local/state/uid-journal-migration-cli-drill-20261017.json`.
- [ ] Production migration, key/host recovery, endpoint aliases, multi-host
  fencing и full strategy/paper admission открыты. Real API/orders/rollout нет;
  прежний network DNS failure не считается успешной qualification.

Процедура и ограничения: [EXECUTOR_UID_MIGRATION.md](EXECUTOR_UID_MIGRATION.md).
Детальные evidence/checklists: последний раздел
[основного плана](PROFITABLE_STRATEGY_RESEARCH_PLAN.md). Frozen research kernels,
production ownership files и installed service не менялись. Следующая работа:
незакрытые R1 canonical endpoint/host recovery и R2 evidence admission, затем
прежний порядок R3–R16 без повторения завершённых исследований.


## 17 октября: R1 — запрет endpoint alias namespace

- [x] Exact canonical mainnet endpoint проверяется до UID lease/migration и на
  active submit. Retained alternate registry того же UID блокирует bootstrap;
  hashes/owner records не переписаны. 67 новых fake endpoint tests passed.
- [x] Canonical migration CLI process drill сохраняет DB/reserves/owners;
  receipt `.local/state/uid-canonical-migration-cli-drill-20261017.json`.
- [ ] Alternate endpoints/regions, key/host recovery, old/off-mode writers и
  multi-host fencing открыты. Реальные API/orders/production migration нет.

Детали и ограничения: [ownership runbook](EXECUTOR_ACCOUNT_OWNERSHIP.md)
и последний раздел [основного плана](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).


## 18 октября: R2/R14 — source-bound paper evidence audit

- [x] Original protocol/candidate/policy registry lineage, pinned model
  probabilities и role decisions/intents/fills проверяются; три role exports
  и acceptance пересчитываются read-only. Sealed gate не читает rewards.
- [x] Cash/lot/flat/dust marks сверяются с original fills. Unknown historical
  liquidation valuations сохраняют paper_evidence_pass=false даже при
  conditional evaluator pass. Frozen producer/kernel не менялся.
- [x] 36 focused tests passed /26.42s. Actual CLI preflight закрытого protocol:
  sealed_until_paper_end, candidate_identity_verified=false, live_admission=false;
  `.local/state/strategy-evidence-sealed-20261018.json` (placeholder pin, 3metadata inputs).
- [ ] Actual independent/paper candidate, historical valuation sources и full
  live admission остаются открытыми. Entry adapter/rollout не выполнялись.

Процедура: [STRATEGY_EVIDENCE_AUDIT.md](STRATEGY_EVIDENCE_AUDIT.md).
Подробные проверки и ограничения — в [основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
Реальных API/orders/model publication нет; previous network failure не скрыт.


Итог18октября R1 endpoint + R2/R14 evidence: **1637 passed,1 deselected /139.53s**
(`-m not integration`, no cache provider, temp files под `/tmp`). Read-only
sealed CLI audit SHA d867f504836c128ee70d68714a8c0b340aeb9c6830aa17ddfef21083653b0efb;
retained receipt file SHA5ed8976977e0e8a3d30e62b562875932b74ff26a0e7d83ee65a3f83ba7b3a9b0.
Проверены текущие implementation/input SHA; сетевой integration не запускался.
Предыдущий DNS failure и actual account/source/host qualification открыты.
Следующий checklist: НОВЫЙ preregistered mark-source/ordering capture без
переписывания frozen study, независимый valuation replay и full entry admission
adapter с сохранением разрешённых exits. R1–R16 целиком не закрыты, profitable
candidate и разрешающий production approval не созданы.
