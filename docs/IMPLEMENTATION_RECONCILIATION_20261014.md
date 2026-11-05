# Сверка реализации и чеклист продолжения

> **Архив с 5 ноября 2026.** Продолжение фиксируется в
> [CURRENT_PLAN.md](CURRENT_PLAN.md). Верхние абзацы этого файла описывают
> 14–28 октября и не учитывают восстановление 1–2 ноября.

R4/R15 и R7: [competing writers](FEEDER_COMPETING_WRITERS_20261028.md), [training status](MODEL_TRAINING_STATUS_20261028.md); full recovery и promotion не выполнены.

R4/R15: [selected_sync current observations](FEEDER_SELECTED_SYNC_OBSERVATION.md), historical effect остаётся unknown.

28 октября: [повторный FIFO-разбор cache](EXECUTION_CACHE_REVIEW_20261028.md); свежая история биржи не проверена.

R4/R15: [current feeder guard](FEEDER_GUARD_CURRENT_20261028.md), effect selected_sync unknown.

R6/R15: [bounded runtime inventory](FORECAST_RUNTIME_INVENTORY.md) и ограниченный host probe; timers active, общая writer-координация открыта.

R6/R15: [synthetic outcome ID/replay rehearsal](FORECAST_OUTCOME_ID_REHEARSAL.md); real event identity и fencing всех writers открыты.

R6/R15: [composite reader rehearsal](FORECAST_RETENTION_READER.md) проверен на полном snapshot; live wiring и global outcome ID открыты.

R6/R15: [split rehearsal](FORECAST_RETENTION_REHEARSAL.md) подтвердил все typed rows; будущие outcome ID и composite readers остаются открытыми.

R6/R15, 28 октября: [retention preflight](FORECAST_RETENTION_PREFLIGHT.md)
разделил snapshot на47700 candidates/279 protected, сохраняя учёт всех47722
versions; 34 tests. Физический split, readers, backup и cutover остаются открытыми.

Дата: 14 октября 2026, Europe/Moscow. Область проверки: текущий checkout,
локальные тесты, сохранённые исследовательские receipts и конфигурация user-systemd.
Это обновление плана, а не изменение исполнителя, модели, риска или сервисов.

## Forecast health — 28 октября 2026

- [x] Read-only capacity/maturity монитор:6new+25compat=31tests. Actual06:11:
  ledger полный,0 незакрытых mature forecast в36h,279 старше.
- [ ] Наличие исторических endpoints и безопасное возобновление записи не доказаны.
  [Evidence](FORECAST_MEMORY_HEALTH.md).

## Incomplete feeder inspection — 28 октября 2026

- [x] Read-only проверены registration/plan и source receipts;7new+32compat=39tests.
  Actual `selected_sync` остаётся unknown. В 06:08 SQL/REST/SQL binding120
  подтвердил одну identity/schema; BTC stale≈6ч23м, ETH fresh.
- [ ] Original row effects, безопасное восстановление, restart и host qualification.

[Метод и evidence](FEEDER_INCOMPLETE_INSPECTION.md).

## Diagnostic forecast snapshot — 28 октября 2026

- [x] Отдельный read-only-source snapshot и restore drill: 47979 forecast,
  47722 outcome versions, integrity и row digests совпали, orphan0.
- [x] 8new+17compat=25tests, включая WAL и concurrent writer.
- [ ] Original SQLite всё ещё полный; writer/reader cutover, rollback, retention,
  actual запись новых диагностических данных и off-host backup остаются открытыми.

[Контракт и evidence](FORECAST_MEMORY_SNAPSHOT.md).

## Bounded paired coordinator — 27 октября 2026

- [x] W8.2b.3a: отдельный coordinator, durable operations и explicit known-tick
  recovery без повтора worker/provider; настоящий process exit42 проверен.
- [x] 22new+36compat=58tests/365.04s, cumulative827; прежние601 Python files
  сохранены. Synthetic12ticks/fills4/0/4, source/reader и independent replay3/3.
- [ ] Unknown component/finalization/host recovery, long history/capacity,
  actual positive market и W9/economic/remaining gates ещё открыты.

[Runbook](PAIRED_CACHED_COORDINATOR.md), evidence
`.local/state/paired-cached-coordinator-work-20261027/verification.json`.

## Операционная диагностика покупок — 27 октября 2026

- [x] Local registry/исполнитель/cache и размеры forecast store проверены read-only;
  active `09b486e979` устарел, candidate `f8028fb44d` denied; 39 hold/0 rejects
  в отдельном окне 23:00–23:15 не являются объяснением всех hold.
- [x] Выявлен незавершённый feeder cycle после смены загрузки: три receipts есть,
  effect последней стадии unknown; local BTC устарел. Исходные данные сохранены.
- [ ] R4/R15 reconciliation/restart; R6/R15 сохранение и восстановление записи
  diagnostic store; R7/R12 compatible primary migration; R8 real-buy flow и
  W9/R14 independent future paper. Свежий account/risk snapshot не проверен.

[Доказательства и пределы](NO_BUY_DIAGNOSIS_20261027.md),
[актуальные проверки](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).

## Cached actual paper application v3 — 27 октября 2026

- [x] W8.2b.2b: новый pre-start parent, cached reader proof в actual input,
  prepared/completed worker result и result SHA ack. Heartbeats не создают
  opportunities, группы сохраняются в прежнем archive v2.
- [x]17new+39compat=56tests/124.44s, cumulative805. Прежние599Pythonfiles сохранены;
  61accepted source/test copies/77runtime keys. Unknown worker result/stale parent blocked.
- [x] Synthetic3roles/12applications/6opportunities/9heartbeats: source/reader
  audits3/3, independent controller/FIFO3/3, fills4/0/4;12retained reader proofs.
- [ ] W8.2b.3 новый coordinator/durable operations и W7b.3b unknown/parent/host
  recovery; bounded physical/source/delivery/native/capture history/capacity,
  actualpositive/current-model/R1–R16/VP/W9/host/review/economic gates.

[Runbook](CACHED_CASH_APPLICATION_V3.md), evidence
`.local/state/cached-cash-application-v3-work-20261027/verification.json`.
Public network/primary DB/model/risk/trading/fits/realorders0 этим этапом; actual paper
class работал только на synthetic quotes. Original sealed outcomes не открывались.

## Cached reader для original role offers — 27 октября 2026

- [x] W8.2b.2a: новый pre-start read-only reader связывает exact whole-poll
  source/index bytes с original role offer/cursor/batch. Backlog/stale/foreign
  offers blocked; cached view не подставляется в старый сигнал.
- [x]20new+18compat=38tests/10.14s, cumulative788. Прежние597Pythonfiles сохранены;
  19accepted copies/17runtime keys. Synthetic9packets/18cash decisions совпали
  с прежним reader,4positive synthetic decisions; actual worker/fills не проверялись.
- [ ] W8.2b.2b versioned cash-worker application с reader proof; далее coordinator/
  recovery и bounded physical/source/delivery/native/capture history/capacity.
  W7b.3b/actualpositive/current-model/R1–R16/VP/W9/economic открыты.

[Runbook](CACHED_REFERENCE_READER_V2.md), evidence
`.local/state/cached-reader-v2-work-20261027/verification.json`.
Public network/actual worker/primary DB/model/risk/trading/fits/orders0 этим шагом.
Original sealed outcomes не читались; старые app/runner не получили новый reader автоматически.

## Incremental cash source index — 27 октября 2026

- [x] W8.2b.1: отдельный pre-start source prefix index. Прежний SourceReplay
  проверяет только новые события; original first-seen и cached view сохраняются,
  полный независимый audit сверяет историю/state/versions/projection.
- [x]18new+100compat=118tests/17.99s, cumulative768. Прежние594Pythonfiles сохранены;
  19accepted copies/16runtime keys. Unknown commit/stale checkpoint blocked.
- [x] Synthetic6attempts/4polls/16events/12role packets matched, updates4/4/4/0/4/0
  соблюдают cooldown. Это input-only receipts, не actual worker result.
- [ ] W8.2b.2 versioned delivery/reader, bounded physical SHA/source/native/capture
  history, новый paired coordinator и W7b.3b unknown/parent/host recovery.
  Whole-file SHA ещё читается целиком; actualpositive/current-model/R1–R16/VP/W9/
  economic gates открыты. Старые runner/limits/registrations не менялись.

[Runbook](REFERENCE_PREFIX_V2.md), evidence
`.local/state/reference-prefix-v2-work-20261027/verification.json`.
Public network/actual worker/primary DB/model/risk/trading/fits/orders0; original
sealed outcomes не открывались, общий admission false.

## Индексированный cash application v2 — 27 октября 2026

- [x] W8.2a: новый сжатый архив точных исходных квитанций; проверка последней
  записи и текущей группы, полный post-end audit, explicit recovery одного
  completed шага без worker/provider/ack rerun. Истинный process exit42 проверен.
- [x]19new/97.65s +50compatibility cases в119.59s profile =69distinct;
  cumulative750. Ошибки прежней test fixture исключены, затем19new прошли все.
  Прежние591Pythonfiles сохранены;57accepted sources/59runtime keys.
- [x] Synthetic three-role replay3/3,12applications/6decisions/9heartbeats,
  fills4/0/4; receipt bytes/queue ack SHA сохранены. Actual market proof этим не получен.
- [ ] W8.2b source/delivery/native/capture и новый paired coordinator/long capacity;
  W7b.3b unknown/parent/host recovery, actualpositive/current-model/R1–R16/VP/W9/
  economic gates. Прежний single-use runner не получил v2 или resume автоматически.

[Runbook](CASH_APPLICATION_V2.md), evidence
`.local/state/cash-application-v2-work-20261027/verification.json`.
Primary DB/model/risk/trading/fits/orders/public network не менялись этим этапом.
Original sealed outcomes не открывались; общий admission false.

## Count/resource capacity preflight — 27 октября 2026

- [x] W8.1 metadata-only preflight: original SHA-bound source/delivery/worker/app/
  replay caps, exact UTC poll/tick counts, quotas/segment/native/journal budgets.
- [x]13new+19compatibility=32distinct tests /38.28s; cumulative731cases.
  Actual trace896paths: no SQLite/outcome/groups/.env. Прежние588Python files сохранены.
- [x] Existing60s profile count pass; hypothetical30days518400ticks/role/8641polls/
  3144976journal records даёт26blockers/exit2. Execution/admission остаётся false.
- [ ] W8.2 versioned scalable long history/checkpoints/source/delivery/native
  quotas/retention/whole-host/review; W7b.3b unknowneffects/whole-runner recovery,
  W7b.2c.2 actualpositive и R1–R16/VP/W9/economic gates.

[Runbook](CASH_CAPACITY_PREFLIGHT.md), receipt
`.local/state/cash-capacity-preflight-work-20261027/verification.json`.
Новых fits/model/risk/trading/primary DB changes/orders нет, original sealed outcomes
не читались. Hypothetical horizon не является новой регистрацией или запущенным study.

## Known paper-result ack recovery — 27 октября 2026

- [x] W7b.3a: explicit recovery только durable completed worker-result/ack.
  Original source packet/offer, полный worker prefix/native/head и known queue
  ancestor проверяются; worker tick/provider/source poll не повторяются.
- [x] Default plan-only; explicit paper ack apply сохраняет original result и
  existing ack bytes, выдаёт новый application/queue checkpoint. Unknown states блокируются.
- [x]17new+33compatibility=50distinct, cumulative718. True process exit после
  queue commit и synthetic3failure points проверены; subsequent fills без duplicate intents.
- [ ] W7b.3b whole-runner/unknown worker effects/missing result/host restart;
  W8 long paired capacity/retention/review и W7b.2c.2 actualpositive/все economic gates.

[Runbook](CASH_ACK_RECOVERY.md), receipt
`.local/state/cash-ack-recovery-work-20261027/verification.json`.
Прежние585Python files сохранены. Это synthetic recovery qualification, не actual
production outage. Primary DB/model/risk/trading services/orders/fit не менялись,
original sealed outcomes не читались. Paper/economic/live=false.

## Actual bounded paired rehearsal — 27 октября 2026

- [x] W7b.2c.1: source/delivery/cash rules/3captured workers/5s ticks/endpoint/
  independent replay объединены в single-use20–120s runner с durable journal.
- [x]19new+33unchanged compatibility=52distinct cases; cumulative701.
  Прежние582Python files сохранены. Runtime103entries/59accepted source copies.
- [x] Actual prospective minute13:40–13:41МСК:240closed rows,12ticks×3,
  6negative/cash decisions,33heartbeats,44completed operations, ack1/1/1.
  Independent controller/FIFO/coverage3/3, actual fills0/0/0.
- [x] Transient service MemoryMax512MiB/AS384MiB/320s, measured cgroup peak≈33MiB,
  exit0/runtime81.467s. Whole-host/positive-load qualification этим не выдана.
- [ ] W7b.2c.2 actual positive/fill/exit branches и более длинный paired stream;
  W7b.3 interrupted recovery, W8 host/capacity/retention/review и R1–R16/VP/W9.

[Runbook](PAIRED_CASH_REHEARSAL.md), receipt
`.local/state/paired-cash-runner-work-20261027/verification.json`.
Source public BTC/ETH; primary DB/model/risk/trading units не менялись, real
orders/fit0. Original sealed outcomes не читались; paper/economic/live=false.
Это short negative-case paper run, не прибыльный кандидат и не persistent daemon.

## Cash contracts и actual worker receipts — 27 октября 2026

- [x] W7b.2a: pre-start three-role cash rules/strategy SHA, exact rational guards,
  cash-only control и separate stress floor. Price probability не становится entry.
- [x] W7b.2b: все fixed-pair decisions/negative/skip/failures, реальные frozen
  CapturedPaperWorkerV2 prepared/completed receipts, ack после durable result.
  Heartbeats обслуживают fills/exits между5m polls, без fake opportunities/acks.
- [x]33current tests +249compatibility =282distinct cases; по всем профилям682.
  Синтетический3role сценарий:12applications/6opportunities/9heartbeats,
  independent controller/FIFO replay3/3. Это не market study/доказательство дохода.
- [x]27октября feeder recheck:313retained successes/0failures/238prune receipts;
  BTC fresh120SQL/REST/SQL. Длительная whole-host/outage qualification ещё открыта.
- [ ] W7b.2c: actual bounded paired runner/public providers/cadence/monitoring/
  finalization и source-bound actual rehearsal. Diagnostic coordinator не paper runner.
- [ ] W7b.3/W8 recovery/capacity/review; actual current-model comparisons,
  R1–R16/VP/W9 и economic/paper/live admission остаются открытыми.

[Runbook](CASH_WORKER_APPLICATION.md). Receipt
`.local/state/cash-worker-application-work-20261027/verification.json`.
Прежние578Python files и804historicalcheckbox/body сохранены. LLM — другой агент.
Новых fits/primary model/risk/trading-unit changes/orders нет, original sealed
outcomes не читались. Ниже предыдущие датированные состояния.

## Рабочий reference feeder — 26 октября 2026

- [x] W6b.3b.2a: observed Docker api→PostgREST→PostgreSQL route и exact120
  closed UUID/value rows связаны SQL/REST/SQL; key/DB password не сохраняются.
- [x] W6b.3b.2b: установлен отдельный pinned managed runner на выбранный user
  market-feeder path UID1000. Первый настоящий service cycle завершился успешно;
  BTC/ETH sync+SQL probes идут перед ranking. Timer active/waiting, interval120s
  после завершения, MemoryMax768MiB/TasksMax64; child AS512MiB/75s/64KiB.
- [x] Operational retention ограничен384MiB/720cycles/24h; сохраняются два последних
  success и все failures. Unknown partial cycle блокирует автоматический повтор.
  Research evidence не очищается. Это реализация/test, не длительный host drill.
- [x]43new+108compatibility=151tests passed /4.19s; по четырём профилям26октября
  **564 разных cases**. Прежние572 Python files сохранены; полный suite не запускался.
- [x] W6b.3b.2c: автоматический timer cycle13:24UTC success, BTC/ETH probes fresh.
- [ ] W6b.3b.2d/R4/W8: длительные outages/recovery/retention/capacity проверки.
  Cash worker/host admission открыт.
- [ ] W7b.2 cash policies/all actual opportunities/CapturedPaperWorkerV2 results;
  W7b.3/W8 и остальные R1–R16/VP/W9 остаются открытыми.

[Runbook и пределы](MANAGED_REFERENCE_FEEDER.md). Evidence
`.local/state/reference-feeder-operation-work-20261026/verification.json`.
Market candles/tickers/health/universe обновлены локально; заменены только
market-feeder service/timer. Модель/risk/trading units не менялись, real orders0,
sealed outcomes не читались, fit=false, economic/paper/live=false.
Ниже сохранены предыдущие датированные состояния до deployment.

## Reference-aware feeder proposal — 26 октября 2026

- [x] [W6b.3b.1 runner](REFERENCE_AWARE_FEEDER.md): independent BTC/ETH before ranking,
  closed120 SQL probes, strict full sync result и общий venue cooldown10min.
- [x] Child caps512MiB address space/64KiB output/75s stage, bounded kill,
  local-only backend, private receipts и default plan-only mode.
- [x]17new+96compatibility=113tests passed /2.55s; actual proposal создан,
  primary write attempted=false. Три набора26октября:521 разных cases с учётом91повтора.
- [ ] W6b.3b.2/R4: actual installed path/ownership, local writes+probes,
  REST→instance linkage и repeated-cycle/restart/retention qualification.
- [ ] W7b.2 cash contracts/full opportunities/actual worker receipts;
  W7b.3/W8 recovery/host, W9 future evidence и остальные R1–R16/VP gates.

Evidence `.local/state/reference-aware-feeder-work-20261026/verification.json`.
Прежние569 Python-файлов сохранены. Primary DB/services/model/risk на этой
code-приёмке не менялись; установленный feeder продолжает прежний путь.

## Guarded cash preflight и local health — 26 октября 2026

- [x] [Календарь до чтения cash outcomes](SEALED_CASH_READINESS.md): незавершённые train/validation
  не вызывают payload loader; sealed-test/paper никогда не читаются этим путём.
  Explicit protocol/observed freeze, bounded read-only reader и immutable report.
- [x]14new+41compatibility=55 разных tests passed /0.92s. Actual closed-protocol
  preflight: inspected[],fit=false; openat trace не содержит memory.sqlite.
- [x] Current local SQL read: BTC close23октября14:05UTC/stale≈70h;
  ETH close26октября12UTC/fresh. Timer активен, последний oneshot успешен.
- [ ] W7b.2 cash policies/full actual opportunities/worker application receipts;
  R6 qualified counts/оконные cutoffs/collection health и W6b.3b actual refresh.

Evidence `.local/state/local-cash-readiness-work-20261026/verification.json`.
Прежние566 Python-файлов сохранены. Primary DB читалась read-only; services,
model/risk не менялись. New guard — opt-in, старые CLIs/schedulers не переписаны.

## Bounded coordinator W7b.1 — 26 октября 2026

- [x] [Source/delivery coordinator](REFERENCE_COORDINATOR.md):5m polling/cooldown, durable
  prepared/completed checkpoints, source tail/backlog monitoring и input receipts.
- [x]31new+413compatibility=444 разных tests passed /113.32s; actual два соседних
  windows, packets6/cursors2/2/2 и full offline source/delivery/receipt replay.
- [x] Completed-pass lost checkpoint восстанавливается только explicit known
  ancestor recovery. Неопределённая component operation блокирует дальнейшую работу.
- [ ] W7b.2: cash-entry policies/all actual opportunities, CapturedPaperWorkerV2
  wiring и durable application/result receipts. Input ack не является worker trade.
- [ ] W7b.3/W8: interrupted component/host recovery, installed runner/capacity/review.
- [ ] W6b.3b/R4 actual primary reference refresh/REST linkage, W9 и общие W7/W6/W5.

Receipt `.local/state/reference-coordinator-work-20261026/verification.json`.
Прежние563 Python-файла и804 historical checkbox/body сохранены. Primary DB,
services/model/risk не менялись. Sealed outcomes не читались; LLM — другой агент.
Ниже прежние датированные сводки; текущая очередь — W7b.2, затем W7b.3/W8.


Actual replay сохранил35 initial missing5m slots: source namespace создан
08:56:27UTC, первый poll11:54:33UTC. Между двумя выполненными polls gaps нет;
current tail0 не отменяет initial gap. Continuous source completeness=false.

## Retained source history и role delivery W7a — 23 октября 2026

- [x] [Source event retention и ordered role queue](REFERENCE_DELIVERY.md):
  оригинальные manifest/head/event bytes/negative failures, global first-seen,
  три durable cursor/pending/ack и bounded replay после изменения source DB.
- [x] Explicit ancestor recovery после потерянного receipt; unknown prefix,
  conflicting ack и hot journal блокируются. Old SQLite bytes не объявляются
  сохранёнными; новая семантическая история имеет отдельный contract.
- [x]413 разных tests passed /27.98s:39new+374compatibility; общий suite не запускался.
- [ ] W7b: periodic coordinator/full opportunities, cash-entry policies,
  actual paired workers и durable result receipts. Ack digest не доказывает trade.
- [ ] W6b.3b/R4 actual working reference refresh, W8/W9 и общие W7/W6/W5 gates.

Receipt `.local/state/reference-delivery-work-20261023/verification.json`.
Прежние559 Python-файлов/804 historical checkbox/body сохранены. Primary DB,
services/model/risk не менялись. LLM — другой агент.
Ниже прежние датированные сводки; текущая очередь — W7b.

## Общий reader W6b.3a — 23 октября 2026

- [x] [Prospective source reader/shared frame](REFERENCE_SOURCE_READER.md):
  immutable source inputs, closed120 и precision28 features, original price
  forecasts и first-seen/forecast replay, одинаковые inputs для трёх ролей.
- [x] Compact artifact304141→2906bytes, original model parameters сохранены.
  Actual360rows/1AVAX original forecast и same probability из original artifact.
  Это diagnostic migration-v3`041b`, не candidatea252, не active model.
- [x]374 разных tests passed /38.85s:48new+326compatibility; общий suite не запускался.
- [ ] W7 — следующая реализация: durable delivery/cursors/ack/restart/source
  history retention и cash policies. Worker `would_enter` из price probability
  не создаётся. NEW replay старого frame требует original pinned source DB.
- [ ] W6b.3b working reference refresh/primary linkage/deployment health,
  W8/W9 и общие W6/W5/R1–R16/VP gates остаются открытыми.

Прежние556 Python-файлов/804 historical checkbox/body сохранены, primary DB,
services/model/risk не менялись. Outcome нового forecast не читался.
Receipt `.local/state/reference-reader-work-20261023/verification.json`.
Текущая очередь уточняет более ранние датированные сводки ниже.

## Продолжение W6b.1/W6b.2 — 23 октября 2026

- [x] [Mandatory reference capture и source-bound forecasts](REFERENCE_SOURCE_LEDGER.md)
  реализованы в отдельном namespace: BTC/ETH не зависят от dynamic ranking,
  raw responses, immutable versions/first-seen, frozen model и offline replay.
- [x] 326 разных tests passed /25.09s:61new+265compatibility, общий suite не запускался.
  Actual public GET23октября07:51UTC:120BTC+120ETH ready, затем offline verified.
  Forecast linkage mechanism проверен synthetic tests; actual forecasts=0.
- [ ] W6b.3: shared reader/paired stream, actual compatible forecasts и рабочий
  reference refresh. Primary SQL BTC при read07:08UTC всё ещё stale≈32h;
  этот collector работает отдельно и его primary rows не обновляет.
- [ ] W7–W9, общий W6/W5 и R1–R16/INT/VP gates остаются открытыми.

Receipt `.local/state/reference-sources-work-20261023/verification.json`.
Прежние552 Python-файла и804 historical checkbox/body сохранены. Primary DB,
services/model/risk не менялись; экономическая пригодность не доказана.
Ниже исторические датированные сводки; текущий следующий шаг — W6b.3, затем W7.

## Продолжение W6a — 22 октября 2026

Отдельный [local source observer/contract/audit](LOCAL_SOURCE_PROVENANCE.md)
реализован:79new+186compatibility=265 different cases passed; общий suite
не перезапускался. Actual120BTC+120ETH rows сохранены и offline verified.
BTC stale≈14h23m, ETH fresh в13:33UTC. Retained migration pins не объявляются
историческим known_at или равенством current DB старому снимку.

- [x] W6a implementation и bounded actual SQL/source checks.
- [ ] W6b mandatory reference/forecast/reader linkage; W7–W9 и общий W6 открыты.

DB/services/model/risk не менялись. Frozen548codefiles/804historical checkbox
сохранены. Receipt: `.local/state/local-source-provenance-work-20261022/verification.json`.

## Текущая сверка — 22 октября 2026

Актуальные статусы по всем R1–R16, W6–W9, исходным этапам и VP сведены в
[текущем checklist master-плана](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Ниже сохранены исходная сверка 14 октября и дневник продолжений; их «следующая
задача» не отменяет более новое завершение реализации.

- [x] Перепроверены 25 tested source/test SHA producer/archive/capture/replay v2,
  сохранённые pytest summaries21 октября и source/runtime references выбранных
  receipts14–21 октября. Проверка документации 22 октября не является новым code run.
- [x] Исправлена устаревшая очередь whole-worker capture/replay и разделены
  completed negative/development studies, готовые защитные механизмы и actual
  qualification. Исходные 804 checkbox/body сохранены как история.
- [ ] R1–R5 operational; R6–R11 data/human/source; R12–R14 independent/paper;
  R15–R16 deployment review: остаток каждого общего gate приведён в сводке;
  выполненные локальные механизмы повторять не требуется.

Предыдущая сверка docs не обращалась к account/primary DB/systemd. W6a read
22октября приведён выше. Основная БД local,
last authenticated read20 октября. Исторические упоминания remote Supabase/RLS
ниже не являются текущей задачей повторить облачную миграцию. Последняя
профильная code-проверка приведена далее с датой 21 октября.
Receipt: `.local/state/plan-checklist-reconciliation-work-20261022/verification.json`.

Последняя профильная проверка21октября2026: **753 разных cases прошли:** 115 passed /388.36s + overnight UTC 1 passed /13.43s; compatibility 637 passed /953.93s. Общий suite заново не запускался.
W5a/W5b.1–W5b.3 и W6a реализованы; следующий W6b — mandatory sources/forecasts, затем W7 paired runner.
Последний полный2063passed/1deselected — предыдущий этап.
Поправка области работ: LLM-план выполняет другой агент; его очереди здесь нет.
Текущий backend20октября — local PostgreSQL/PostgREST; authenticated read
через loopback подтверждён. См. [backend runbook](DATABASE_BACKENDS.md).
Исторические упоминания Supabase ниже не являются текущим выбором облачной БД.
Этот этап не мигрирует таблицы/credentials и не обновляет original frozen approvals.
Дополнение VP и его зависимости находятся в [действующем research-плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
R1 canonical endpoint и R2/R14 original paper audit проверены локально; current
service rollout/полный live admission открыты. Исходная сверка14октября ниже
сохранена как историческая; датированные дополнения имеют более новый scope.

## Как читать статусы

`[x]` — конкретный механизм/проверка выполнены в указанной области.
`[ ]` — результат отсутствует, неполон либо требует проверки на действующем пути.
Прохождение unit tests не закрывает independent evaluation, paper или live admission.
Старые VPS smoke checks относятся к 25 сентября; они не подтверждают состояние Linux executor сегодня.
Отрицательный законченный эксперимент считается выполненным исследованием, но не готовой стратегией.

## Что проверено в этой сверке

- [x] Прочитаны основной план, FINAL_AUDIT, исследовательский план, FREQAI,
  prompt продолжения и runbooks двух путей исполнения.
- [x] Проверены код Supabase Spot executor, live risk, collectors, архивные
  source-case scripts и существующие тесты; выполнен поиск TODO/FIXME,
  NotImplemented, broad exceptions и live configuration.
- [x] Новый запуск: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -m 'not integration'`
  — **1057 passed, 1 deselected, 33.38 s**. Историческая запись 1058 passed
  не заменяет этот результат; integration не запускался.
- [x] У шести receipts 14 октября проверены 69 ссылок на input/runtime bytes
  (для gzip SHA относится к распакованным bytes), отсутствующих файлов нет.
  Дополнительно проверены все 20 canonical minute snapshot SHA из minute_capture.
  Mutable `path` архива отличается от canonical `snapshot_path`; это не повреждение SHA.
- [x] Проверена установленная служба: `cryptoforge-supabase-executor.timer`
  присутствует в расписании, ExecStart содержит `--live`, последний Result=success.
  Inactive у oneshot между запусками не означает отключённые торги.
- [ ] Удалённая Supabase схема/RLS, текущие права ключа, остатки/новые orders,
  VPS/VPN, Telegram delivery и disaster recovery сегодня не перепроверены.
  Наличие документа или локального теста не является новой remote verification.

## Реализовано и проверено в ограниченной области

- **Архив и причинность:** Bybit Spot ingestion, closed-candle contracts,
  purged splits, checksums, immutable snapshots и source/runtime bundles.
  Годовая корзина и source audit существуют; полнота исторического universe/rules не доказана.
- **Симуляция и бухгалтерия:** shared wallet, fees/slippage, entry volume bounds,
  exit minimum preservation, отдельный paper wallet и независимый Decimal fill replay.
  FIFO source audit: 49 closed allocations, 33 remaining records, 14 open lots,
  unmatched sale quantity=0. Это арифметика предоставленного cache, не доказательство полной истории счёта.
- **Защита исследований:** attempt ledger, frozen budgets, source identity,
  target/feature compatibility, chronological selection guards и resource deferral.
  Completed/deferred/blocked различаются; повторный запуск не создаёт новый бюджет.
- **Исследования:** train windows 4 варианта, ablation 7 вариантов,
  balanced/unweighted 2 варианта; fixed/ATR extensions 4/4 завершены.
  Extension economic screen: **0/4 passes**, independent admission=false.
  Buy-and-hold development context завершён отдельно; положительный context
  не является прибыльным кандидатом с сопоставимым stop risk.
- **Source cases:** long BTC/ETH numerical audit и 40 sampled replays;
  minute check 6 stops; 20 minute ambiguous source geometries.
  Новый edge-complete-trade-label receipt содержит 20 counterfactual labels,
  но manual_review_complete=false, historical_execution_rules_certified=false,
  actual_strategy_entry_verified=false. Общий manual gate остаётся открытым.
- **Обучение и обратная связь:** собственные lightweight price/net heads,
  registry, primary artifact audit, prospective forecasts и migration collector,
  real-source reconciliation и конфликтующие original entry contexts guards.
  Heavy FreqAI integration по-прежнему не реализована как активный runtime.

## Неполно, неверно или требует переделки

### P0 — действующий executor не эквивалентен старому live pilot

Старые plan/README/FINAL_AUDIT утверждали dry-run only либо bootstrap.
На сверке14октября Linux Supabase executor был установлен с `--live`;
отдельный Freqtrade config validator не являлся его admission gate.
После сверки подготовлены opt-in controls, risk/drawdown, runtime approval,
UID ownership и exit recovery wiring; датированные проверки приведены ниже.
Installed service на эти новые flags не переводился. Полный strategy/paper
admission, включая квалифицированные independent evidence, не подключён;
наличие кода нельзя отмечать как operational qualification действующего режима.

- [ ] **R1.** Зафиксировать отдельный runtime contract Supabase executor:
  текущие капитал/лимиты/permissions/модель/хост и single-executor ownership;
  сверить явно с операторским решением. Новые defaults не менять молча.

  Обновление15октября: opt-in journal launcher обёрнут в execution_lease до
  сетевых действий цикла. Private immutable sidecar фиксирует credential SHA,
  endpoint, host SHA и resolved journal path; persistent owner registry
  запрещает выбрать новую пустую DB вместо старой. Общий credential/endpoint
  flock блокирует второй локальный процесс даже с другим journal path.
  Process-kill/restart test пройден, initial legacy DB adoption и missing bound
  DB требуют explicit recovery. Account UID не проверялся: новый API-key того
  же счёта не объединяется с прежним. Multi-host ownership/операторский runtime
  contract и включение установленного сервиса ещё открыты; весь R1 не закрыт.

  Обновление18октября: local UID ownership/reviewed migration и exact canonical
  mainnet endpoint guards проверены, включая сохранение retained alias lineage.
  Actual account/host/permissions и операторский rollout остаются отдельными
  открытыми gates; credential fingerprint не подменяет реальную проверку UID.
- [ ] **R2.** Подключить kill/no-new-entry и admission к фактическому entry/order
  пути; определить отдельно поведение exits/cancel и проверить shadow/fake client.
  При закрытом entry gate новых buy не должно быть; разрешённое управление
  существующей позицией должно продолжаться. Live smoke — отдельная процедура.

  Обновление15октября: подготовлен opt-in `--execution-controls PATH`,
  ControlledOrderClient стоит непосредственно перед exchange market/limit
  methods, внутри JournaledOrderClient. JSON reread выполняется после intent
  commit: изменение switch в середине цикла учитывается. no_new_entry запрещает
  Buy, допускает Sell; kill_switch запрещает все новые Buy/Sell без автоматического
  закрытия/отмены старых orders. Missing/invalid controls блокируют обе стороны.
  Blocked before submit фиксируется как blocked, не exchange unknown.
  Полный admission/операционный rollout ещё открыты; installed service не менялся.

  Обновление18октября: отдельный read-only original paper evidence auditor
  пересчитывает registry/model/role/acceptance и cash marks. Existing reports
  без historical mark quotes не дают квалификацию liquidation values; actual
  future study остаётся sealed. Auditor не является entry adapter и не
  выдаёт live grant; полный R2 по-прежнему открыт.
- [ ] **R3.** Сопоставить hard risk engine с фактическими executor limits:
  max drawdown, notional/risk-per-trade, daily loss units и позиции.
  `--max-daily-loss 2` здесь означает **2 USDT**, а не 2%; stake=6 и
  cap=6 из installer не доказывают соблюдение исходных 0.5%/5%/2 positions.
  Закрытие: каждый обязательный gate вызывается до submit, adversarial tests
  запрещают обход; документирована выбранная политика.

  Обновление15октября: opt-in `--submission-risk-guard` повторяет текущие
  absolute CLI limits на submit path. Market Buy qty трактуется как quoteCoin
  согласно private client; oversize/nonfinite/zero qty отвергается. Перед send
  заново читаются equity/USDT wallet/inventory, считаются current material
  positions/equity capacity и проверяется UTC daily baseline. Unknown/error
  блокирует Buy, Sell не зависит от entry-risk queries. Journal отличает
  такой known local block от unknown exchange outcome. Проверен actual
  executor Buy path с fake client. Это не полный HardRiskConfig admission:
  walletBalance не доказывает free/reserved buying power, pending orders,
  persistent peak DD и percent limits ещё открыты. Installed service не менялся.

  Дополнение15октября: opt-in `--spot-reservation-guard` (требует submission
  risk guard) использует строгие original USDT wallet fields. Locked/bonus
  исключаются; borrow/spotBorrow/positionIM/orderIM должны быть явно нулевыми,
  missing/empty/malformed не заменяются нулём. Open Spot orders читаются без
  symbol filter, openOnly=0,limit50 с полным nextPageCursor до terminal page;
  duplicates/loop/page ceiling считаются unknown. Pending Buy symbols входят
  в union с material holdings; target pending Buy запрещает duplicate entry.
  Snapshot latency, ACK visibility gap и durable local reservation ещё открыты.

  Следующее дополнение15октября: opt-in --local-order-reservations требует
  submission risk guard и bound submission journal. Journal-backed quote и
  symbol reserves сохраняют ACK, даже если remote REST пока пуст. Текущий
  prepared intent исключён из собственного reserve; next Buy проверяет union
  held/remote/local symbols и уменьшенный conservative cash bound. Reconcile
  теперь рассматривает ACK/observed Buy, но release допускается только при
  exact-link/symbol/side/acknowledged-orderId terminal zero-fill proof. Filled
  и partial orders не освобождаются автоматически. Lifecycle settlement после
  закрытия и устранение double-conservative bounds ещё открыты; rollout нет.

  Дополнение15октября: --settle-closed-reservations подготовлен для narrow
  single-buy/known-sales scope. Аутентифицированный read-only collector
  получает exact orderId history/executions с complete pagination и final
  explicit base wallet row; verifier проверяет cumulative totals, qty/value,
  base/quote fee movements, chronological full consumption и zero inventory.
  Original responses/source SHA сохраняются в released_closed receipt.
  Partial/unknown/third-fee/multiple-buy cases retain reserve. Tests используют
  fake API, actual account/retention/latency qualification и rollout открыты.

  Следующее дополнение15октября: proof-v2 допускает terminal Spot
  PartiallyFilledCanceled с positive cumulative execution proof. Для Sell
  executed base не превышает requested base и remaining leaves не превышает
  неисполненную часть; для Buy сравнивается quote value, не base qty с quote
  request. Несколько closing sales покрывают весь received base с fees.
  Open PartiallyFilled, unknown statuses, gaps и residual inventory сохраняют
  резерв; contradictory PartiallyFilledCanceled с zero executions больше не
  проходит zero-fill release. Actual partial/dust/multi-buy qualification открыта.

  Обновление16октября: local cohort verifier поддерживает несколько Buy и
  interleaved closing Sell. Existing verified_order проверяет каждый exact
  source order, FIFO queue запрещает использовать будущую/внешнюю inventory,
  повторение order/link/exec и остаток. Mixed Buy/Sell с одинаковым timestamp
  считается ambiguous, не получает guessed ordering. Original source receipt
  общий для cohort; release в одной SQLite transaction проверяет исходные
  intent SHA/status и запрещает executions из ранее released proofs.
  Injected failure на втором update откатывает оба. Actual account/FIFO scope
  и rollout открыты; локальная entry policy не менялась.

  Дополнение16октября: opt-in --drawdown-state PATH + explicit
  --max-portfolio-drawdown FRACTION подготовлены для bound journal/risk guard.
  Observed peak никогда не уменьшается и не сбрасывается сменой дня;
  decline>=threshold latches Buy blocker. Equity recovery latch не снимает.
  Missing/corrupt/future/wrong-owner/wrong-threshold state, lock/write errors
  запрещают Buy без инициализации новой peak baseline. Sell не требует state.
  Startup и submit проверяют текущую account equity; это observed, не continuous
  peak. External transfers/account-wide mark/source qualification и реальная
  baseline/recovery остаются открытыми. Installed service без флагов.

  Дополнение16октября: --fractional-risk-policy PATH подготовлен как opt-in
  слой market Buy. Explicit decimal limits<=5% position и<=0.5% planned risk,
  current CLI stop distance и explicit roundtrip cost участвуют в точном
  расчёте. Existing symbol USD value включая dust учитывается в exposure.
  Требуются remote/local reservation guards и bound journal; Sell unaffected.
  Policy SHA сохраняется в risk snapshot. Численные installed defaults не
  менялись; реальные costs/gaps/stops, aggregate portfolio risk и admission
  qualification ещё открыты.

### P0 — доступность exits и сохранность risk state

`SupabaseLiveExecutor.run_once` читает Supabase candles до проверки holdings;
при missing/stale candles возвращает reject_entry до exit branch.
При падении reader exit branch не достигается. Outbox другого пути не устраняет
эту зависимость; будущие stops нельзя считать независимыми от Supabase.
`daily_equity_blockers` заменяет повреждённый JSON на пустой state и принимает
текущую equity как новую базу; запись не атомарна. Это может сбросить уже
накопленный daily loss, а не безопасно запретить новый вход.

- [ ] **R4.** Отделить управление holdings/exits от entry data/ML/Supabase availability:
  определить аварийный источник цены и поведение при unknown/stale данных.
  Закрытие: outage/stale/missing/model-error regression проверяет, что
  управление открытой позицией не теряется и новые buys заблокированы.

  Обновление15октября: подготовлен отдельный `exit_data_fallback.py`,
  подключаемый к launcher флагом `--exit-data-fallback`. При primary data
  outage/missing/stale используется проверенная последовательность закрытых
  public Bybit5m candles; новые buys запрещены, existing stop/exit branch
  проверяется. 24focused tests passed, включая реальный executor с fake clients,
  invalid fallback и отсутствие повторной отправки при неизвестном outcome.
  Флаг в установленный сервис не добавлен. Startup dependencies, journal/
  decision persistence при Supabase outage, emergency quote latency и полный
  outage/recovery scope ещё открыты; весь R4 не закрыт.

  Дополнение16октября: launcher обрабатывает exception ночного selector,
  сохраняет fallback/held pairs и добавляет entry blocker вместо раннего abort.
  Full run_cycle с fake private/public/Supabase clients проверил исследование+
  remote outage→public closed candles→один stop sell→ACK journal/pending
  decision. Repeat не пересылает order; kill блокирует, no-entry допускает Sell.
  Diagnostic snapshot теперь atomic/private и пишется после всех startup
  blockers, содержит configured protections без qualification claim. Ошибка
  записи diagnostic блокирует Buy, но не ранний abort exits. Private-account
  outage, real source/host recovery и operational smoke ещё открыты.

  Дополнение16октября: read_entry_account_snapshot строго валидирует account
  balances/inventory. Exception/NaN/missing/duplicate rows переводят entry
  context в unknown, slots0 и Buy blocker; launcher продолжает known pairs.
  Daily/peak state при unknown equity не переписываются, diagnostic equity/
  positions/capacity nullable. Invalid coin valuation сохраняет известный
  symbol для fresh per-symbol check; invalid candidate balance не обрывает
  другие пары. При private position quantity outage Sell не отправляется.
  Cycle с unknown account data не объявляется healthy даже при successful exit.
  Реальная discovery outside known pairs и private-source qualification открыты.

  Следующее дополнение16октября: read_entry_account_snapshot сохраняет
  точные validated coin rows вместе с capacity. Если initial held-pair query
  упал, но sizing query восстановился, его material holdings дополняют pairs
  в этом же цикле; refresh выполняется только для новых pairs. Extra wallet
  query нет; duplicates не создают повторные exits. Snapshot хранит actual
  evaluation_pairs. Full fake-client cycle доказал outside-fallback discovery
  и один stop Sell после recovery. Полный inventory outage/source qualification
  и operational smoke всё ещё открыты.

  Дополнение15октября: `decision_outbox.py` и opt-in `--decision-outbox PATH`
  сохраняют exact trade_decisions request в isolated private SQLite до remote
  upsert, с FULL synchronous commit. Restart flush повторяет только idempotent
  records, не orders; локальный payload SHA проверяется, FIFO delivery
  останавливается на первой remote ошибке. Pending queue блокирует следующие
  entries, exits не блокируются этим признаком. Actual executor/fake exchange
  test подтвердил один sell при remote decision outage и сохранённый результат.
  Installed service не изменён. Это не pre-submit order-intent journal и не
  решение crash-after-submit-before-local-record; общий R4/R15 открыт.

  Следующее дополнение15октября: подготовлен opt-in pre-submit journal
  (`--order-submission-journal PATH`). Market-order intent фиксируется FULL
  synchronous SQLite transaction до обращения к exchange; prepared/unknown
  никогда не отправляются повторно, даже после restart. Exact matching
  orderLinkId/symbol/side/orderId в open/history допускает positive observation;
  пустая bounded history не снимает неизвестность. Unresolved symbol блокирует
  повторное действие, любой unresolved attempt блокирует buys; exits других
  symbols разрешены. Cached acknowledgment не объявляется исполненным fill.
  Local crash/failure/fake exchange integration проверены; account ownership,
  реальный host recovery и rollout ещё открыты.
- [ ] **R5.** Сохранять daily baseline атомарно и валидировать finite/nonnegative
  значения, дату и timezone; повреждение/утрата ожидаемого same-day state
  должно блокировать entries до recovery, а не обнулять loss allowance.
  Проверить crash/truncated/invalid/NaN state и перенос между hosts.

  Обновление15октября: локальный механизм исправлен и проверен. Повреждённый,
  отсутствующий, future-dated или incompatible-timezone state возвращает entry
  blocker без замены baseline. Legacy valid UTC state читается без сброса;
  rollover только по UTC, с атомарной записью и неблокирующим sidecar flock.
  38 focused tests прошли, включая simulated replace failure/lock contention.
  Отдельный live outage/recovery и перенос same-day baseline между hosts ещё
  не проверены; поэтому общий R5 остаётся открытым.

### P1 — основная модель и пригодность cash данных

По receipt 04:54 UTC candidate a252b48b49 воспроизводится; active legacy
09b486e979 имеет неизвестный контракт. Promotion replay: 420 unseen examples,
3 signals при minimum 30, incompatible feature contract. Это price target,
не cash strategy admission. Новые timer runs могут изменить candidate registry.
Cash preflight 04:47 UTC: source healthy, **0 eligible**, 8 несовместимых rows.
Миграционный протокол v3 frozen на другом candidate 041b; подменять его a252 нельзя.

- [ ] **R6.** Собрать genuine future original closed bounded120 buy features;
  существующие 8 legacy rows не переписывать. Сверить collector/producer contract.
- [ ] **R7.** Завершить independent candidate/control execution comparison
  в отдельно зарегистрированном protocol; price endpoint comparison оставить
  descriptive. Не реконструировать legacy feature contract по имени.
- [ ] **R8.** Выполнить cash fit только после original train/validation readiness.
  Train заканчивается **7 ноября 2026, 00:59 МСК**, validation —
  **21 ноября 2026, 00:59 МСК**; нужны также counts/days/pairs/classes из frozen protocol.
  Дата сама по себе не закрывает gate, sealed outcomes не читать раньше cutoffs.

### P1 — историческое исполнение и ручной source audit

- [ ] **R9.** Свести минимум 20 ручных полных trade-label cases в один registry:
  source identity, actual/counterfactual entry, available-at, qty/fee/rounding,
  first-touch bounds, residual basis и reviewer outcome. Использовать уже
  полученные edge/FIFO/minute artifacts; не скачивать/реализовывать их заново.
  Gaps/ambiguity/noncloseout и неполные fills должны быть представлены либо
  явно оставлены незакрытыми. 20 geometry cases и 20 FIFO allocations — разные проверки.
- [ ] **R10.** Дополнить point-in-time universe/filters/fees/fee assets,
  partial/rejected fills, spread/depth. Текущие maker/taker observations
  APT/NEAR не являются historical тарифом. Third-token conversion без source
  остаётся unknown; определить ограниченную qualified область и исключения.
- [ ] **R11.** Новый source/policy version для изменённых kernels/paper producer;
  не backfill старые fingerprints. Перед очередным paper проверить original
  runtime replay и clock/quote/filter coverage; старые guards с source drift
  должны отказать либо использовать явно архивный проверенный scope.

### P2 — независимая стратегия, paper и операционная квалификация

- [ ] **R12.** Зарегистрировать процедуру, календарные train/selection/test
  windows, purge/embargo, бюджет, controls и сведения о просмотренных периодах.
  Сравнить baseline, frozen compatible model, new heads и cash-only на общем
  wallet/risk; buy-and-hold оставить отдельным контекстом.

  Обновление16октября: первый observed no-candidate/cash-only выбор реально
  зафиксирован04:41:22UTC после повторной проверки6registered validation
  reports. Calendar window соблюдён; test outcomes не читались. В04:42:52UTC
  подготовлен source-bound virtual cash reference job до eligible test start
  17октября00:00UTC. Early evaluation rejected, output не создан. Cash-only
  component не заменяет native/control execution или full independent search;
  общий R12/R13 открыт, test_end15ноября00:00UTC.
- [ ] **R13.** Выполнить независимую оценку процедуры целиком: nonoverlapping
  windows, time block bootstrap, PF/DD/stress/activity/concentration и
  calibration на естественном распределении. Development проигрыши не
  становятся holdout при переименовании; отсутствие trades не заработок.
- [ ] **R14.** После прохождения offline gates вести candidate/control paper
  wallets на одном будущем потоке, сохранять fills/rejections/exits/equity;
  выполнить independent replay и объяснить расхождения. Общий protocol
  30 дней/100 trades и closed cash protocol 14 дней/60 trades не смешивать.
- [ ] **R15.** Повторить backup/restore, outage/recovery, уведомления, restart,
  risk switches и single-host ownership именно на выбранном runtime.
  VPS измерения 25 сентября не переносить на Linux desktop или новый executor.

  Обновление17октября: local reviewed UID migration существующего
  credential-bound journal реализована и проверена в isolated CLI processes.
  Prepare фиксирует original input/source SHA; apply требует reviewed plan SHA,
  fresh UID proof и оба locks. Original DB bytes/inode/statuses/reserves не
  меняются; независимый backup, exact partial resume и reserved path/link
  guards проверены. Production migration, key/host recovery, endpoint aliases
  и multi-host fencing открыты; R15 целиком не закрыт.
- [ ] **R16.** Закрыть Phase 31 только отдельным review evidence после R1–R15;
  текущие реальные execution records не заменяют profitable qualification.

## Сверка фаз основного плана

- **0–2:** исторический VPS/bootstrap/preparation закрыт в старой области;
  текущая topology/host/resource qualification требует R1/R15.
- **3–4:** Freqtrade dry-run smoke и public-data механизмы реализованы;
  Freqtrade и Linux Supabase executor — разные runtime.
- **5–6:** schema/outbox/sync код и тесты существуют; current remote RLS/schema
  не перепроверены, live executor availability требует R4.
- **7–11:** scanner/regime/baseline/risk/position primitives реализованы;
  корректная wiring действующего live пути и historical fills — R2–R5/R9–R10.
- **12–14:** старый dry-run E2E и journal/metrics реализованы;
  cache FIFO/reconciliation проверены; полнота attribution/history остаётся открытой.
- **15–18:** research/lifecycle/challenger/lab механизмы и development studies
  реализованы; qualified profitable candidate, controls и independent evidence отсутствуют.
- **19:** архитектура heavy FreqAI есть, own lightweight trainers есть;
  нельзя отмечать heavy FreqAI активной по наличию собственного logistic trainer.
- **20–25:** monitoring/notifications/disk/backup/migration/recovery tooling есть;
  текущие operational rehearsals — R15, safety wiring — R2–R5.
- **26–29:** старые audit tasks не являются непрерывной гарантией безопасности;
  новые runtime findings и ограничения внесены в R1–R15. Broad catch сам по
  себе не ошибка: проверять fallback, failure recording и отсутствие secret leakage.
- **30:** исторический final audit сохранён; текущая end-to-end квалификация открыта.
- **31:** отдельные primitives и реальный executor существуют; совокупный DoD не закрыт.

## Порядок следующей реализации

1. R1–R5: фактический runtime contract и защитные пути. Подготовить/проверить
   изменения локально; установка новой live версии — отдельное конкретное действие.
2. Параллельно по времени наблюдения, без расширения исследования: R6–R8;
   R9–R11 можно закрывать имеющимися sources и bounded qualification.
3. Только затем R12–R14. Отрицательные completed studies сохранить и не повторять
   под новым budget pool без новой гипотезы и preregistration.
4. R15–R16 закрывают operational/live review; profitable candidate сейчас отсутствует.

Источники: IMPLEMENTATION_PLAN.md; docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md;
код и tests текущего checkout; .local/state/{edge-complete-trade-label-audit,
cash-training-preflight-context-guard,primary-promotion-source-replay,
extension-economic-screen,fifo-conservation-source-audit,
archive-ambiguous-minute-source-audit}-20261014.json.
Локальные ignored artifacts должны сохраняться отдельно от Git с original SHA;
одна ссылка в Markdown не является резервной копией evidence.

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

## 18 октября: R2/R14 — новый opt-in capture valuation sources

- [x] Отдельный [capture/replay механизм](PAPER_VALUATION_CAPTURE.md): новый
  namespace/future freeze, raw quote/filter responses, причинный sequence,
  independent liquidation replay и sealed read-only CLI. Frozen runtime SHA
  прежних producers совпали с checkpoint, старые study не менялись.
- [x] Добавлено34теста; полный non-integration suite1693passed/1deselected,
  56.76s. Native worker compatibility проверена на synthetic opportunities.
- [ ] Actual новый трёхролевый study, lifecycle/coverage/resource contract,
  наблюдение исходников, independent economics/review и full entry admission
  не завершены. Capture не выдаёт ни прибыльность, ни live grant; R2/R14 открыт.

## 18 октября: R2/R14 — lifecycle v2 и вместимость long-study

- [x] Новый typed frozen lifecycle, measured capture guards, cutoff/termination
  и независимая time-weighted coverage реализованы локально. Old v1 не получает
  lifecycle admission; native frozen runtime SHA сохранены.
- [x] 33 новых теста, 1726passed/1deselected /84.44s. Прогон с комиссиями может
  пройти проверки корректности источников и завершения, оставаясь убыточным;
  economic_profitability_established/live_admission_granted всегда false.
- [x] Сегментированное хранилище/capture v3/v4 и independent streaming wallet
  audit реализованы последующими этапами. Min30days/poll5s даже без fills
  требуют1 036 804events против прежнего cap10 000; full worker/study ещё BLOCKED;
  full worker/resource/shared-role qualification и actual paper ещё открыты.

Подробности: [PAPER_VALUATION_CAPTURE.md](PAPER_VALUATION_CAPTURE.md).

## 18 октября: R2/R14 — standalone segmented evidence storage

- [x] Новый bounded storage с общими seq/byte budgets, rotation, durable pending
  recovery, exact retry и read-only streaming structural verification.
  Проверены process death, catalogue schema/source corruption и restart.
- [x] 38 новых тестов, **1764passed,1deselected /421.60s**. Synthetic10 005events/
  21segment проходят structural audit с peak148 779bytes tracked Python
  allocations. Это не full worker RSS или экономическая квалификация.
- [x] Capture v3/v4, bounded native wallet/worker source archive и streaming
  wallet cash/FIFO/valuation/coverage replay реализованы последующими этапами.
- [ ] Реальные full worker/shared-role/resource measurements.
  Существующий long-study остаётся BLOCKED; полного source/economic pass нет.

Native runtime, capture/lifecycle v1/v2, модель и сервисы не менялись.
[Runbook и следующий acceptance checklist](EVIDENCE_SEGMENTS.md).

## 18 октября: R2/R14 — opt-in capture v3 adapter

- [x] Новый protocol/role/parent/schema/runtime/Decimal registration, segmented
  native mark/execute capture, source row IDs/hashes и durable terminal.
- [x] Сохранение exact pending frame после сбоя не повторяет неизвестную native
  операцию. Actual subprocess-death tests и 45focused checks passed /16.19s.
- [x] Sealed read-only source/operation audit пересчитывает marks/day/cash/
  inventory; не выдаёт full FIFO/coverage/paper/economic/live admission.
- [x] Итоговый полный прогон v3: **1809 passed, 1 deselected /438.15s**; actual study не запускался.
- [x] Bounded native archive и streaming wallet FIFO/valuation/coverage реализованы19октября.
- [ ] Full worker/strategy/source replay и RSS/shared-role qualification.

Native frozen sources/storage v1, модель/сервисы сохранены.
[Runbook](PAPER_CAPTURE_V3.md), текущая очередь — в основном плане.

## 19 октября: R2/R14 — native archive/projection engine

- [x] New-root indexed source shards, immutable native rows, global budgets,
  byte/page/active bounds и original high-water IDs.
- [x] Archive→verify→attached atomic cleanup/checkpoint, archive-aware wallet/
  worker dedupe, cash/day/FIFO/pending context и source-only sealed reader.
- [x] 36focused cases passed /7.63s, actual subprocess-death boundaries,
  archive-full/source drift/rollback/tamper/exit-reserve checks.
- [x] Итоговый полный прогон: **1846 passed, 1 deselected /359.50s**,37новых cases;10 005-row synthetic stress прошёл.
- [x] Capture v4 integration реализована следующим этапом.
- [x] Independent streaming wallet FIFO/valuation/coverage реализован следующим этапом.
- [ ] Full worker/strategy/source replay, actual shared-role/host/RSS/power-loss
  qualification и admission открыты.

V3/frozen native producers и installed service/model/risk не менялись.
[Runbook](NATIVE_PAPER_ARCHIVE.md). Old roots не очищаются и не мигрируются.


## 19 октября: R2/R14 — capture v4 archive/checkpoint integration

- [x] Prospective registration/roles/two manifests; durable wallet mutation ledger,
  original row deltas и bounded archive-invariant source/checkpoint commitments.
- [x] Actual process deaths: unknown prepared blocks retry, stored complete recovers
  exactly; original source/log schemas и old runtime сохранены.
- [x] Terminal/end-window read-only CLI, external pins, source drift и rehashed
  false trace checks;52focused cases passed /46.05s.
- [x] Итоговый общий non-integration capture v4: **1898 passed, 1 deselected /536.74s**.
- [x] Streaming cash/FIFO/valuation/time coverage реализован следующим этапом.
- [ ] Full worker/opportunity/source capture, shared roles/host/RSS/resource qualification
  и actual future study/admission.

[Runbook и checklist](PAPER_CAPTURE_V4.md). Actual study, model, services/risk
не менялись; LLM реализует другой агент.


## 19 октября: R2/R14 — bounded independent streaming replay

- [x] Original pre-start contract/runtime, hard scratch page/row budget,
  bounded active cache и private disposable index вне immutable source roots.
- [x] Independent expected cash/fees/FIFO/fills/segments/liquidation/anchors/row deltas;
  constant-size time coverage, original expiry/completion/endpoints/closeout checks.
- [x] 65focused passed /36.83s;10 005marks synthetic core bounded-state test,
  independent short legacy crosscheck и source-consistent false dust rejection.
- [x] Итоговый общий non-integration streaming replay: **1963 passed, 1 deselected /470.87s**.
  Final source SHA/log/receipts сохранены в `.local/state/paper-streaming-replay-work-20261019/`.
- [ ] Full worker opportunity/decision/source capture, paired roles и actual
  source/RSS/full-tick/network/queue/disk/shared-role/host qualification/admission.

[Runbook и checklist](PAPER_STREAMING_REPLAY.md). Actual study/fit/model/services/risk
не менялись; LLM выполняет другой агент. Old source/runtime SHA сохранены.

## 20 октября: R2/R14 — prospective whole-worker source journal

- [x] Отдельный pre-start protocol/registration/role/runtime contract над native
  archive и segmented log. Старые study roots и frozen wallet/worker/math не менялись.
- [x] Полный переданный prediction batch с SHA/source observation, bounded JSON,
  original opportunity identity, negative/out-of-scope/duplicate rows.
- [x] Durable whole tick и вложенные original UTC/monotonic observations,
  public market/indicator prepared/complete responses/failures и atomic native
  enqueue/link/seen/event/mark/execute/cancel/compaction deltas/checkpoints.
- [x] Exact raw market normalization/hash, causal availability, original Buy/source/
  expiry и negative-status linkage, worker report и final native source union.
- [x] Неизвестная action/tick блокирует следующие effects и resume, даже если
  исходный worker проглотил Exception. Actual subprocess deaths и exact stored
  whole-tick completion recovery проверены; leaf complete не усыновляет whole tick.
- [x] 85 focused passed /129.22s: negative decisions, market/exit errors, swallowed
  failures, rehashed forgeries, clocks, budgets, process deaths,13ticks bounded
  projection/restart, sealed CLI и unchanged read-only sources.
- [x] Итоговый общий non-integration worker capture: **2063 passed, 1 deselected /747.04s**.
  Final source SHA/log/receipts: `.local/state/paper-worker-capture-work-20261020/`.
- [x] Pre-start independent delivered-worker decisions + native wallet/FIFO/coverage
  replay нового schema реализован отдельно: [local worker verifier](PAPER_WORKER_REPLAY.md).
  V4 receipt не переносится на новый journal; actual study admission остаётся открытым.
- [ ] Следующий R2/R14: qualified producer, backend instance/schema/source provenance,
  paired candidate/control/stress runner и immutable shared polling/completeness
  contract, включая skips/nonfills/negative outcomes.
- [ ] Квалифицировать producer: same-clock FIFO, строгая stake/cash conservation,
  pending Buy cutoff/closeout. Capture блокирует поздний Buy до исполнения;
  первоначальные native producer defects не объявляются исправленными.
- [ ] Actual payload/RSS/wall/network/queue/disk/three-role/host qualification,
  independent review и новая prospective registration с qualified candidate.
  Тестовая policy130events/tick требует67 392 006events на30days/poll5s/одну роль;
  старые wallet-only budgets не подходят. Минимум30days и economics gates сохраняются.

`worker_source_trace_pass=true` подтверждает source linkage. Полнота upstream
polling, независимые worker decisions/FIFO/coverage, economic/paper/live и host
qualification остаются false. Actual study/API/orders/fit/model publication/
services/risk этим этапом не запускались и не менялись. LLM ведёт другой агент.
[Runbook и acceptance checklist](PAPER_WORKER_CAPTURE.md);
receipts `.local/state/paper-worker-capture-work-20261020/`.

## 20 октября: локальный backend и independent delivered-worker replay

- [x] Учтён переход на local PostgreSQL/PostgREST: authenticated loopback read
  подтверждён; существующая миграция/selector/credentials не менялись. Legacy
  `supabase_*` имена кода не означают cloud endpoint. Paper SQLite roots отдельны.
- [x] W1: новый pre-start replay contract связывает original capture/candidate/
  role/window/runtime/resources и явную local configuration, без cloud fallback
  или сохранения credentials. Backend resolver и timestamp parser pinned.
- [x] W2: fresh hard-bounded scratch, indexed historical seen/intent/link/prediction
  identities, active pending projection, immutable history key+SHA и cleanup.
- [x] W3: отдельный controller восстанавливает delivered-batch decisions,
  UTC/monotonic branches, requests/errors, expiry/limits/order/exits и report,
  без вызова native worker/wallet/providеrs или рабочей PostgreSQL.
- [x] W4: independent wallet/FIFO/cash/fees/row deltas/valuation/time coverage
  связаны с atomic worker actions нового schema; source trace сам по себе pass не даёт.
- [x] 47 новых tests passed /97.00s: source-consistent false exit/
  monotonic responses отвергнуты после source trace pass; strict native overspend
  отвергнут без epsilon. Проверены negative/duplicate/conflicting opportunities,
  stop/timeout/closeout/expiry/position/signal limits, offline reader, sealed CLI,
  resource/index/page caps/cleanup и13ticks bounded negative history.
- [x] 162 compatibility tests passed /178.42s: existing backend selector/CLI,
  worker source capture и streaming wallet replay. Всего209 профильных cases;
  прежние source files/runtime сохранены. Новый общий suite не запускался.
- [ ] W5: новый producer, causal FIFO и strict sizing/cash, pending Buy cutoff.
- [x] W5a: отдельное [ядро producer v2](PAPER_PRODUCER_V2.md) и local pre-start
  kernel contract реализованы; прежние kernels/state/receipts сохранены.
- [ ] W5b: новый bounded archive/capture/replay для fill sequence/high-water,
  exact allocation policy и cutoff clock после SQLite lock; полный W5 открыт.
- [ ] W6/W7: actual backend instance/schema/migration/row known_at provenance,
  complete upstream polling, paired candidate/control/stress runner и registration.
- [ ] W8/W9: actual RSS/payload/tick/network/queue/disk/three-role/host qualification,
  independent review, qualified candidate и НОВОЕ actual study минимум30days.

Decision/math pass относится только к delivered batches и registered paper model.
`source_poll_completeness_verified/full_worker_or_host_qualified/paper_evidence_pass/
economic_profitability_established/live_admission_granted=false`.
Ни actual fee/strategy profitability, ни все migrated rows не сертифицированы.
Actual orders/fit/model publication/trading services/risk этим этапом не запускались
и не менялись. LLM остаётся у другого агента. [Runbook](PAPER_WORKER_REPLAY.md);
receipts `.local/state/paper-worker-replay-local-work-20261020/`.

## 20 октября: новое ядро paper producer v2 (W5a)

- [x] Отдельные `paper_wallet_v2.py`, `paper_worker_v2.py`, `spot_buy_math_v2.py`
  и kernel contract реализованы без изменения прежних producer/capture/replay.
  Основная БД остаётся local PostgreSQL/PostgREST; cloud fallback не добавлялся.
- [x] Durable fill sequence в одной транзакции с cash/lot/fill/intent;
  causal FIFO и latest-Buy context при equal UTC clocks и после restart.
  Частичный allocation округляется вниз до512places, весь остаток basis/entry fee
  остаётся в lot. Полное закрытие переносит весь остаток, отрицательные остатки не допускаются.
- [x] Exact integer-step sizing/base-or-quote fee, cost<=stake/cash, cash>=0,
  floor sell quantity<=inventory. Внешний Decimal precision/traps не меняет результат.
  Cash + residual basis == initial capital + realized net PnL проверено точно,
  без epsilon, на повторных Buy/Sell и dust cycles.
- [x] Pending Buy отменяется до market request и повторно после provider delay;
  wallet проверяет cutoff после BEGIN IMMEDIATE. Тест с реальной конкуренцией за
  SQLite write lock подтверждает отказ позднему Buy, Sell closeout сохраняется.
- [x] Новый pre-start kernel contract: candidate/study/role/window/runtime/config,
  local credential-free backend identity, отдельные external contract/registration SHA,
  offline reader, no overwrite и запрет late/partial/admission adoption.
  Contract пока не связан с archive/capture/runner и не запускает study.
- [x] **145 новых passed /18.00s**, **285 compatibility passed /363.18s**:
  всего430 разных cases. Проверены frozen wallet/worker/math, backend selector/CLI,
  native archive, worker source capture, independent worker и streaming wallet replay.
  Общий suite заново не запускался; прежние2063passed/1deselected — исторический результат.
- [x] Сохранены523 прежних code/test files и804 исходных checkbox/body без изменения;
  comparative synthetic receipts сохраняют old defects и new corrections отдельно.
- [x] W5b.1: отдельный native archive v2 с kernel binding,14 groups и causal
  high-water/projection реализован; см. NATIVE_PAPER_ARCHIVE_V2.md.
- [x] W5b.2: новый whole-worker capture, pre-start pins,14 groups и actual native
  clocks реализованы; итоговый результат21октября и PAPER_WORKER_CAPTURE_V2.md ниже.
- [x] W5b.3: independent replay новой schema реализован21октября:
  exact sizing/512-place allocation, fill sequence/counter, native clocks,
  original-window valuation и resource/scratch bounds. См. PAPER_WORKER_REPLAY_V2.md.
  Старые manifests/verifiers не изменены.
- [ ] W6/W7: instance/schema/migration/row known_at provenance локального upstream,
  complete shared polling и paired candidate/control/stress runner.
- [ ] W8/W9: actual RSS/payload/tick/network/queue/disk/three-role capacity,
  independent review, qualified candidate и новое actual study минимум30days/economics gates.

W5 целиком остаётся открытым. Это isolated kernel implementation и synthetic
regressions, а не source-complete paper qualification или доход. Все admission/
economic/host flags=false. Actual orders/fit/model publication/trading services/
primary DB/risk этим этапом не запускались и не менялись; LLM ведёт другой агент.
[Runbook и точные границы](PAPER_PRODUCER_V2.md);
receipts `.local/state/paper-producer-v2-work-20261020/`.

## 20 октября: native archive v2 и causal sequence (W5b.1)

- [x] Отдельный `native_paper_archive_v2.py` соединяет source storage с original
  local kernel contract: обе kernel pins, candidate/role/config/window, runtime/
  Python/SQLite/Decimal environment, schema и resource floors закреплены до start.
  После durable setup требуется отдельный внешний ready SHA; late/partial root не принимается.
- [x] Явные14 groups: новая immutable `wallet.fill_order` и mutable
  `wallet.fill_counter` добавлены отдельно от прежних12-group contracts.
  Protected projection сохраняет global high-water/counter, open-lot entry fills
  и causal latest Buy. После полного closeout active fill остаётся единственным anchor,
  original history выдаётся streaming union без потери исходных IDs.
- [x] Equal-clock reverse-ID FIFO и exact cash/basis/PnL сохранены через cleanup/
  restart. Отказ при missing/reset/wrong-type counter, потерянном order/fill,
  payload sequence mismatch, negative lot basis и reset checkpoint; state не чинится.
- [x] SQL guards новой schema ограничивают row count/byte representation внутри
  producer transaction: oversize fill откатывает cash/lot/fill_order/counter целиком.
  Public JSON/depth/credential/byte checks и batch cap учитывают filtered predictions.
- [x] Реальные process-death drills на трёх compaction boundaries прошли для
  marks/history и fill sequence. Новая запись после restart продолжает global counter;
  archive failures/page/record limits не удаляют незаархивированные active rows.
- [x] **83 новых passed /100.39s**. Synthetic10 005worker rows: write15.23s,
  sealed audit2.84s, Python peak197919bytes, active worker49152bytes. Это bounded
  storage/Python heap, не process RSS/network/трёхролевой30day qualification.
- [x] **430 compatibility passed /339.50s**: прежние wallet/worker/math/backend/
  native archive/worker capture/streaming+worker replay и v2 kernel. Всего513
  разных cases этого этапа; новый общий suite не запускался.
- [x] Прежние530code/test files и original804checkbox/body сохранены.
  Новая schema с transaction guards не принимается frozen archive/capture.
- [x] W5b.2: новый whole-worker capture и pre-start registration, kernel/archive
  manifest/ready pins,14 groups, checkpoints и actual native clocks реализованы.
  Parent trace сохраняет post-lock execution time; unknown action/tick блокирует
  retry/resume. Endpoint использует original tolerance без timestamp backfill.
  Проверки21октября и PAPER_WORKER_CAPTURE_V2.md ниже.
- [x] W5b.3: independent controller/wallet replay реализован21октября; exact sizing,
  512-place allocation, fill order/counter, ordered native clocks/cutoff, bounded
  scratch/source, source-consistent forgeries и original-window valuation проверены.
  [Подробности](PAPER_WORKER_REPLAY_V2.md).
- [ ] W6/W7: local instance/schema/migration/known_at provenance, full shared
  polling/negative/skip/failure delivery и paired candidate/control/stress runner.
- [ ] W8/W9: whole-worker payload/RSS/wall/network/queue/disk/three-role capacity,
  independent review, qualified candidate и новое actual study минимум30days/economics gates.

W5 целиком открыт. `native_source_integrity_pass` подтверждает storage/active
projection; full worker/host/paper/economic/live admission flags=false. Actual API/
orders/fit/model publication/trading services/primary DB/risk этим этапом не менялись.
LLM ведёт другой агент. [Подробности и acceptance checklist](NATIVE_PAPER_ARCHIVE_V2.md);
receipts `.local/state/native-paper-archive-v2-work-20261020/`.

## 21 октября: whole-worker capture v2 и actual clocks (W5b.2)

**637 разных cases прошли:** 123 passed /363.09s + 1 passed /26.08s после исправления tuple expectation только в тесте; compatibility 513 passed /620.65s. Общий suite заново не запускался.

- [x] Отдельный capture contract связывает original local kernel, обе kernel pins,
  native manifest/ready, storage manifest, runtime/environment, role/config/window
  и resource floors до start. Late/partial registration не принимается.
- [x] Новый state commitment включает все14 groups, immutable fill_order и mutable
  fill_counter. Native row deltas связаны с original action, checkpoint и archive tips.
- [x] Actual native clocks записываются durable с action parent до передачи ядру;
  execute читает время после BEGIN IMMEDIATE. Cutoff/expiry/fill и второй clock reject
  не подменяются prepared time. Исходный v2 tick сохраняет identity/arithmetic checks.
- [x] Проверен реальный SQLite write-lock wait через cutoff без списания cash;
  process death при clock append и после fill commit блокирует partial tick/retry.
- [x] Endpoint имеет pre-start observation/completion deadlines; actual post-end
  timestamp сохраняется отдельно и не backfill original window/coverage/equity.
  Advancing-clock и отдельный короткий observation gap проверены.
- [x] Scoped pair-map payload policy разрешает TOKEN/USDT как identifier и сохраняет
  credential guard внутри payload. Frozen segmented storage и прежние verifiers не менялись.
- [x] Итоговый профильный и compatibility receipts сохранены; final source/runtime
  hashes и environment закреплены. Прежние533files и804historical checkbox/body сохранены.
  Append transaction нового scoped payload policy совпадает с frozen storage по AST.
- [x] W5b.3: independent wallet/controller replay новой версии реализован21октября;
  exact sizing/512-place allocation, fill order/counter, ordered clocks, cutoff/expiry,
  original-window/endpoint separation, source-consistent forgeries и bounds проверены.
  [Runbook и итоговые проверки](PAPER_WORKER_REPLAY_V2.md).
- [ ] W6/W7: local instance/schema/migration/known_at provenance, complete shared
  polling/negative/skip/failure delivery и paired candidate/control/stress runner.
- [ ] W8/W9: whole-worker payload/RSS/wall/network/queue/disk/three-role capacity,
  independent review, qualified candidate и новое actual study минимум30days/economics gates.

W5 целиком открыт. Source/native linkage не закрывает независимую математику,
controller/polling completeness, coverage или host/paper/economic/live admission;
все соответствующие flags=false. Actual API/orders/fit/model publication/services/
primary DB/risk не менялись. LLM ведёт другой агент.
[Runbook и acceptance checklist](PAPER_WORKER_CAPTURE_V2.md);
receipts `.local/state/paper-worker-capture-v2-work-20261021/`.

## 21 октября: независимый replay v2 и original-window valuation (W5b.3)

**753 разных cases прошли:** 115 passed /388.36s + overnight UTC 1 passed /13.43s; compatibility 637 passed /953.93s. Общий suite заново не запускался.

- [x] Новый pre-start local replay contract связывает original capture, обе kernel
  pins, native manifest/ready, role/window, arithmetic/runtime и combined resource floors.
  Backend должен точно совпасть с kernel configuration; credentials не сохраняются.
- [x] Отдельный rational oracle без producer imports: maximal affordable sizing,
  явные fees, causal fill sequence/counter,512-place allocation и exact
  cash + basis = capital + realized PnL, без epsilon.
- [x] Независимый controller пересчитывает expected clocks/providers/actions,
  source negatives, pending Buy cancellation, cutoff/expiry/exit/report branches.
  Native leaf clocks потребляются отдельно от prepared time и controller clocks.
- [x] Source-consistent ошибки quantity/fees/allocation, лишний/пропущенный native
  clock, false shared indicator и mono branch отвергаются новым verifier.
  Equal-clock reverse-ID FIFO проверен отдельно по original native row deltas.
- [x] Original-window mark отделён от actual post-end endpoint. Будущая цена
  не скрывает material inventory и не добавляет coverage/valuation задним числом.
  Kernel/capture/replay roots защищены от записи scratch/output/new replay.
- [x] Source pass проверяет бюджет между bounded frames/rows через private bindings;
  global capture/storage methods не меняются. Scratch имеет hard row/page/byte caps
  и удаляется при ошибке; исходные financial methods producer не вызываются.
- [x] Итоговый профильный прогон и compatibility пройдены; exact source/runtime
  pins/environment сохранены. Прежние539files и804historical checkbox/body сохранены.
- [ ] **Следующий W6:** local backend instance/schema/migration snapshot,
  original source IDs/known_at и provenance actual upstream rows.
- [ ] **W7:** full shared polling/negative/skip/failure delivery и paired
  candidate/control/stress runner с original preregistration.
- [ ] W8/W9: whole-worker payload/RSS/wall/network/queue/disk/three-role capacity,
  independent review, qualified candidate и новое actual study минимум30days/economics gates.

W5 целиком ещё не квалифицирован. Delivered-batch decision/math replay не закрывает
upstream completeness, actual host или paper/economic/live admission; эти flags=false.
Working model/services/primary DB/risk и frozen evidence не менялись. LLM ведёт
другой агент. [Runbook и acceptance checklist](PAPER_WORKER_REPLAY_V2.md);
receipts `.local/state/paper-worker-replay-v2-work-20261021/`.
