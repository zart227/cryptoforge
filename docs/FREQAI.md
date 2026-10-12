# Future FreqAI Architecture

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
