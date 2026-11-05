# CryptoForge - Implementation Plan

> **Архив с 5 ноября 2026.** Единственный актуальный план и чеклисты:
> [docs/CURRENT_PLAN.md](docs/CURRENT_PLAN.md). Галочки ниже не обновлять.
> Фазы 0–29 описывают прежний dry-run контур и не квалифицируют текущий
> Supabase executor с `--live`.

> **Прежняя пометка, сохранена как история.** Этот файл был основным планом
> реализации. Исследовательские и ноябрьские статусы в начале файла устарели
> относительно `docs/CURRENT_PLAN.md`.

Исследовательское направление ведётся в
[действующем research-плане](docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md), включая
дополнение VP. Полные VP-чеклисты находятся там и в связанной спецификации.
LLM-направление отдельно реализует другой агент; оно не входит в эту очередь.

## Other writers и обучение — 28 октября 2026

- [x] R4/R15: training sync20 пар,4 совпадают с incomplete selection;
  health согласуется, но авторство DB rows не доказано.
- [x] R7 partial: candidate253dc4fce7 не продвинут,2 signals/420;
  test probability metrics лучше baseline, не cash P&L. 24new+123compat=147tests.
- [ ] Полный writer inventory/recovery, compatible incumbent/control,
  current executor model и independent cost-aware evaluation.
  [Writers](docs/FEEDER_COMPETING_WRITERS_20261028.md), [model](docs/MODEL_TRAINING_STATUS_20261028.md).

## Selected sync effect и current data — 28 октября 2026

- [x] R4/R15: на тестовых клиентах проверены partial writes; local REST
  20 pairs,14 stale >1h; SQL/REST BTC stale≈14ч06м, ETH fresh.
  13new+110compat=123tests. [Evidence](docs/FEEDER_SELECTED_SYNC_OBSERVATION.md).
- [ ] Historical effect/competing writers, explicit recovery и actual
  continuous collection остаются открытыми.

## Повторный разбор локального кэша сделок — 28 октября 2026

- [x] Повторён source-bound FIFO:49 closed segments,28 losses,16 ≤−1%,
  6 случаев комиссии; snapshot идентичен14 октября, 8 тестов.
- [ ] Актуальные данные биржи/wallet и attribution, затем независимая
  оценка стратегий. [Evidence](docs/EXECUTION_CACHE_REVIEW_20261028.md).

## Feeder guard — 28 октября 2026

- [x] R4/R15: current service failed/timer active и read-only повторная
  проверка incomplete guard исходного цикла.
- [ ] Эффект selected_sync, explicit recovery и actual свежесть closed120.
  [Evidence](docs/FEEDER_GUARD_CURRENT_20261028.md).

## Forecast runtime inventory — 28 октября 2026

- [x] R6/R15: read-only unit/FD inventory, ограниченный host probe и health;
  active timers, исходная SQLite полная; 10new+68compat=78tests.
- [ ] Full host namespaces/writers, общий fencing и восстановление записи.
  [Evidence](docs/FORECAST_RUNTIME_INVENTORY.md).

## Forecast outcome ID rehearsal — 28 октября 2026

- [x] R6/R15: synthetic ID47723–47726 в изолированной копии, стабильный
  event replay, процессы и crash до/после commit; 13new+49compat=62tests.
- [ ] Real event identity, общий lease/fencing всех writers, live reader,
  recovery, независимый backup и cutover. [Evidence](docs/FORECAST_OUTCOME_ID_REHEARSAL.md).

## Forecast composite reader rehearsal — 28 октября 2026

- [x] R6/R15: изолированное чтение 5 API, полная сверка47979 forecasts и
  47700 as-of результатов, batch400, synthetic corrections; 49tests.
- [ ] Production wiring и concurrency, глобальная выдача ID, полный runtime
  inventory, backup и cutover. [Evidence](docs/FORECAST_RETENTION_READER.md).

## Forecast split rehearsal — 28 октября 2026

- [x] R6/R15: две изолированные SQLite, полное объединение typed rows и
  независимый SQL audit; 7new+34compat=41tests.
- [ ] Глобальные ID и порядок версий outcome, composite readers, writers,
  independent backup и безопасный cutover. [Evidence](docs/FORECAST_RETENTION_REHEARSAL.md).

## Forecast retention preflight — 28 октября 2026

- [x] R6/R15: read-only inventory snapshot, 47700 кандидатов с47722 версиями
  и279 защищённых unresolved; 9new+25compat=34tests.
- [ ] Подтвердить все readers/writers, архив и сохранение typed rows,
  concurrency, независимый backup, физический размер и безопасный cutover.

[Контракт и evidence](docs/FORECAST_RETENTION_PREFLIGHT.md).

## Forecast health — 28 октября 2026

- [x] R6: независимая read-only оценка storage capacity и незакрытых endpoints;
  6new+25compat=31tests. Actual06:11: SQLite полная,0 recent/279 older unresolved;
  local REST содержит226/277 distinct endpoint,51 не найден.
- [ ] Проверить поздние endpoint/availability, подключить мониторинг и восстановить
  запись после согласованного cutover. [Evidence](docs/FORECAST_MEMORY_HEALTH.md).

## Incomplete feeder inspection — 28 октября 2026

- [x] R4/R15: read-only проверка original registration, receipt order и source
  observations;7new+32compat=39tests. Actual selected_sync остаётся unknown.
- [ ] Независимая сверка эффекта с SQL/REST/историей и recovery/restart/host.
  В 06:08 SQL/REST/SQL binding120 подтверждён: BTC stale≈6ч23м, ETH fresh.

[Метод и evidence](docs/FEEDER_INCOMPLETE_INSPECTION.md).

## Diagnostic forecast snapshot — 28 октября 2026

- [x] R6/R15: изолированный snapshot actual price diagnostic SQLite и отдельный
  restore drill; 47979 forecasts/47722 outcome versions, integrity и row digests
  совпали, orphan0. 8new+17compat=25tests; WAL/concurrent writer проверены.
- [ ] База остаётся полной: versioned writer/reader cutover, rollback, безопасный
  bounded retention, actual сбор новых записей и независимый backup не выполнены.

[Контракт и evidence](docs/FORECAST_MEMORY_SNAPSHOT.md).

## Bounded paired coordinator — 27 октября 2026

- [x] W8.2b.3a: отдельный preregistered coordinator с журналом prepared/completed,
  точными role refs, missed slots, сохранением cooldown и explicit recovery
  подтверждённого tick без повтора worker/provider; process exit42 проверен.
- [x] 22new+36compat=58tests/365.04s; cumulative827; прежние601 Python files
  сохранены. Synthetic12ticks, fills4/0/4, source/reader и независимый replay3/3.
- [ ] W8.2b.3/W7b.3b unknown source/worker/finalization/host recovery; physical
  history, actual positive и whole-host capacity, W9/R14 и economic gates.

[Runbook](docs/PAIRED_CACHED_COORDINATOR.md), evidence
`.local/state/paired-cached-coordinator-work-20261027/verification.json`.
Действующий торговый путь, модель, риск и сервисы не менялись.

## Операционная диагностика покупок — 27 октября 2026

- [x] Read-only сверены local executor/unit/registry и execution cache; последняя
  найденная покупка CHIP 8 октября17:10:24 МСК, active `09b486e979` старше36h.
- [x] 23:00–23:15 зафиксированы39 hold/0 rejects, а не объяснение всех отказов;
  candidate `f8028fb44d` denied, forecast store256MiB и feeder incomplete.
- [ ] R4/R15 доказать эффект незавершённой стадии feeder и восстановить сбор;
  R6/R15 сохранить записи и восстановить запись прогнозов с ограничением диска;
  R7/R12/R8 и W9/R14 — совместимая migration и независимая оценка с учётом
  закрытого real-buy gate. Аккаунт/риск в свежем snapshot не подтверждены.

[Диагностика и источники](docs/NO_BUY_DIAGNOSIS_20261027.md),
[конкретные критерии и зависимости](docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).

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

[Runbook](docs/CACHED_CASH_APPLICATION_V3.md), evidence
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

[Runbook](docs/CACHED_REFERENCE_READER_V2.md), evidence
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

[Runbook](docs/REFERENCE_PREFIX_V2.md), evidence
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

[Runbook](docs/CASH_APPLICATION_V2.md), evidence
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

[Runbook](docs/CASH_CAPACITY_PREFLIGHT.md), receipt
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

[Runbook](docs/CASH_ACK_RECOVERY.md), receipt
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

[Runbook](docs/PAIRED_CASH_REHEARSAL.md), receipt
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

[Runbook](docs/CASH_WORKER_APPLICATION.md). Receipt
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

[Runbook и пределы](docs/MANAGED_REFERENCE_FEEDER.md). Evidence
`.local/state/reference-feeder-operation-work-20261026/verification.json`.
Market candles/tickers/health/universe обновлены локально; заменены только
market-feeder service/timer. Модель/risk/trading units не менялись, real orders0,
sealed outcomes не читались, fit=false, economic/paper/live=false.
Ниже сохранены предыдущие датированные состояния до deployment.

## Reference-aware feeder proposal — 26 октября 2026

- [x] [W6b.3b.1 runner](docs/REFERENCE_AWARE_FEEDER.md): independent BTC/ETH before ranking,
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

- [x] [Календарь до чтения cash outcomes](docs/SEALED_CASH_READINESS.md): незавершённые train/validation
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

- [x] [Source/delivery coordinator](docs/REFERENCE_COORDINATOR.md):5m polling/cooldown, durable
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

- [x] Append-only original source events и anchors, global first-seen/revisions/
  forecasts, bounded whole-operation chunks и independent offline source replay.
- [x] Три независимых durable cursor/pending/ack, stable redelivery, strict
  acknowledgement order/idempotency и explicit known-ancestor recovery.
- [x]39new+374compatibility=413 разных tests passed /27.98s. Проверены реальные
  process deaths до/после commit, source removal, tampering и storage/scratch caps.
- [ ] W7b — следующая реализация: periodic bounded coordinator, полный actual
  opportunity stream/cash policies и durable worker result receipts/full wiring.
- [ ] W6b.3b operational reference refresh/primary linkage; W8/W9 и общие
  W7/W6/W5/R1–R16/VP qualification остаются открытыми.

[Delivery runbook](docs/REFERENCE_DELIVERY.md). Прежние559 Python-файлов и804
historical checkbox/body сохранены. Ack — consumer receipt, не исполнение worker;
physical old source SQLite bytes не усыновляются под новым SHA.
Receipt: `.local/state/reference-delivery-work-20261023/verification.json`.
Primary DB/services/model/risk не менялись; paper/economic/live=false.
Датированные записи ниже сохраняют прежнюю область проверки.

## Общий reader W6b.3a — 23 октября 2026

- [x] Prospective reader contract, immutable shared source frame и closed120/
  precision28 feature interface для candidate/control/stress; original negative
  price forecasts и source/first-seen/forecast replay.
- [x] Inference envelope304141→2906bytes с сохранёнными original bytes/SHA и
  exact parameters. Actual360source rows,1AVAX forecast, three-role read;
  probability равна расчёту original migration-v3`041b` artifact.
- [x]48new+326compatibility=374 разных tests passed /38.85s; общий suite не запускался.
- [ ] W7 — следующая реализация: retained source history, durable common polling/
  role cursors/acks/restart и cash-decision policies. Reader не запускает workers
  и не преобразует price forecast в `would_enter`.
- [ ] W6b.3b actual working reference refresh/deployment/primary linkage;
  W8/W9 и общие W6/W5/R1–R16/VP qualification остаются открытыми.

[Reader runbook/evidence](docs/REFERENCE_SOURCE_READER.md).
Прежние556 Python-файлов и804 historical checkbox/body сохранены. Primary DB,
services/model/risk и старые protocols не менялись; paper/economic/live=false.
Receipt: `.local/state/reference-reader-work-20261023/verification.json`.
Датированные сводки ниже сохраняют прежний scope, текущая очередь приведена здесь.

## Продолжение W6b.1/W6b.2 — 23 октября 2026

- [x] Mandatory BTC/ETH research collector независимо от ranking, original raw
  HTTP/clock/query pins, immutable versions/first-seen и durable poll journal.
- [x] Source-bound original price forecast/replay mechanism с frozen artifact,
  negative forecasts, mandatory freshness и crash/tamper/resource guards.
- [x] 61new+265compatibility=326 разных tests passed /25.09s; actual public
  120BTC+120ETH ready в07:51UTC и offline audit. Actual forecasts=0.
- [ ] W6b.3: подключение reader к общему потоку/paired runner, actual compatible
  forecasts и проверка reference refresh рабочего контура. Primary SQL BTC
  при read07:08UTC остаётся stale≈32h; новый collector primary DB не обновляет.
- [ ] W7–W9 и общие W6/W5/R1–R16/VP gates остаются открытыми.

[W6b runbook/checklist/evidence](docs/REFERENCE_SOURCE_LEDGER.md).
Прежние552 Python-файла и804 historical checkbox/body сохранены. Primary DB,
services/model/risk не менялись; paper/economic/live admission=false.
Evidence: `.local/state/reference-sources-work-20261023/verification.json`.
Ниже датированные записи предыдущих этапов; их очередь уточнена текущим блоком.

## Продолжение W6a — 22 октября 2026

- [x] Read-only local instance/schema/migration и original candle observations,
  immutable pre-start contract, conservative known_at, revision/freshness guards
  и offline verifier реализованы отдельно от frozen paper components.
- [x]79new+186compatibility=265 distinct tests passed. Actual120BTC+120ETH rows
  и offline CLI verified; общий suite заново не запускался.
- [ ] W6b: mandatory reference sources/original forecasts/reader linkage.
  BTC stale≈14h23m, ETH fresh при read22октября13:33UTC; полный W6 не закрыт.
- [ ] W7/W8/W9, R1–R16 и VP qualification остаются по общему checklist.

[W6a runbook и evidence](docs/LOCAL_SOURCE_PROVENANCE.md).
Primary DB/services/model/risk не менялись; код и receipts прежних548files сохранены.

## Актуальная сверка чек-листов — 22 октября 2026

Единый текущий остаток и условия закрытия находятся в
[research checklist](docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Там разделены выполненный код, незавершённая интеграция, ожидание данных/дат
и постоянные требования. Старые пустые строки дневника не означают, что
готовый механизм надо реализовать повторно; исторические `[x]` не подтверждают
сегодняшний deployment.

- [x] Сверены 25 SHA implementation/tests W5a/W5b.1–W5b.3 и сохранённые
  результаты 21 октября:753 разных cases. Эта отметка относится к сверке docs;
  новые W6a tests приведены выше.
- [x] Completed long/minute audits, fixed/ATR4/4 (0passes), cached loss review,
  calendar/fold0 preparation отделены от ещё открытой квалификации результата.
- [ ] R1–R5: actual runtime/account/risk/exit qualification и проверка rollout.
- [ ] R6–R11: original entry data, candidate/control comparison, cash readiness,
  human20cases и historical execution/source qualification.
- [ ] W7b → W8 и W6b.3b operational: coordinator/cash policies/paired runner →
  whole-worker capacity/review. Kernel/archive/capture/replay заново не писать.
- [ ] R12/R13: полная независимая процедура и остальные folds; fold0 test
  заканчивается 15 ноября 03:00 МСК. Closed-cash train/validation cutoffs —
  7/21 ноября 00:59 МСК, это другое исследование.
- [ ] W9/R14: qualified candidate, новая preregistration, actual future
  paper30days/100closed trades и economic/replay review по общему плану.
- [ ] INT/VP-00…09, R15/R16 и Phase30/31: отдельные незавершённые gates,
  не закрываемые наличием подготовительных механизмов.

Основная БД — local PostgreSQL/PostgREST; authenticated read проверен 20 октября,
при предыдущей сверке docs. W6a22октября выполнил отдельное read-only SQL
наблюдение240rows, приведённое выше; сервисы/модель не менялись.
Подробные приёмочные условия и evidence — в указанном текущем checklist,
а не в повторяющихся исторических очередях ниже.

## Продолжение исследования — 21 октября 2026

- [x] W5b.2: capture v2 с original kernel/archive pins,14 groups, durable native
  clocks после SQLite lock и ограниченным actual endpoint без backfill.
  **637 разных cases прошли:** 123 passed /363.09s + 1 passed /26.08s после исправления tuple expectation только в тесте; compatibility 513 passed /620.65s. Общий suite заново не запускался.
- [x] W5b.3: independent controller/wallet replay новой schema реализован;
  exact financial rules, ordered native clocks, original-window valuation и scratch bounds.
  **753 разных cases прошли:** 115 passed /388.36s + overnight UTC 1 passed /13.43s; compatibility 637 passed /953.93s. Общий suite заново не запускался.
- [ ] W6/W7: local provenance/shared polling/paired runner; затем W8/W9
  capacity/review, qualified candidate и actual economic evidence.

Подробные чек-листы и границы: [capture v2](docs/PAPER_WORKER_CAPTURE_V2.md),
[independent replay v2](docs/PAPER_WORKER_REPLAY_V2.md).
W5 и paper/live admission целиком не закрыты.

## Исходная сверка — 14 октября 2026

Основной план сохраняет исходные фазы и исторические проверки. Текущая сводка,
выявленные ошибки и actionable checklist R1–R16 находятся в
[сверке реализации](docs/IMPLEMENTATION_RECONCILIATION_20261014.md).
Детальный research backlog — [исследовательский план](docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md).

- [x] На14октября локальный non-integration suite: 1057 passed, 1 deselected.
- [x] Подтверждены механизмы исследований и сохранённые source evidence в указанной области.
- [ ] Текущий end-to-end/live admission: runtime risk/outage wiring, model contract,
  independent profitability и forward paper не квалифицированы.

**Последняя проверка установки14октября:** локальный Supabase Spot executor был
установлен с `--live`; таймер присутствовал в расписании. Сверка22октября состояние
службы заново не проверяла. Поэтому старые утверждения «real trading disabled»
не описывают весь проект. Это фиксация состояния, а не новый допуск или изменение торговли.
Freqtrade dry-run проверки не переносятся автоматически на Supabase executor.

Исторические `[x]` фаз 0–29 подтверждают прежние проверки/механизмы, а не повторный
аудит текущего deployment. Открытые критерии актуальной квалификации перечислены
в R1–R16; Phase 30 и Phase 31 не завершены.

## 0. Non-negotiable rules

-   [ ] Exchange scope is **Bybit only**.
-   [ ] Current market scope is **Spot only**.
-   [ ] Current Supabase live executor must pass the dedicated runtime audit R1–R5;
    original Freqtrade dry-run checks do not certify it.
-   [ ] Controlled-live admission must be documented and verified for the actual
    executor; installed `--live` does not close this requirement.
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

-   [x] Every simulated position has defined risk protection.
-   [x] SL distance feeds position sizing.
-   [x] SL/TP logic is strategy-versioned.
-   [x] Test gap/fast-move behavior realistically within Freqtrade
    limitations.
-   [x] Test trailing/break-even logic if enabled.
-   [x] Do not overcomplicate baseline.
-   [x] Persist SL/TP context in journal.

### Definition of Done - Phase 11

-   [x] No simulated trade can open without valid risk definition.
-   [x] Position sizing and stop distance are consistent.
-   [x] SL/TP behavior is covered by tests.

------------------------------------------------------------------------

# PHASE 12 - End-to-end Bybit Spot dry-run

-   [x] Connect scanner -\> regime -\> strategy -\> risk -\> Freqtrade.
-   [x] Confirm only dry-run orders are created.
-   [x] Confirm no Futures endpoints/config.
-   [x] Confirm no leverage.
-   [x] Exercise at least one controlled simulated lifecycle if market
    conditions allow.
-   [x] Verify restart behavior.
-   [x] Verify no duplicate state after restart.
-   [x] Measure CPU/RAM/swap/disk during normal operation.

### Definition of Done - Phase 12

-   [x] End-to-end paper-trading pipeline works.
-   [x] Real-money execution remains impossible under active config.
-   [x] Runtime remains stable on current VPS.

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

-   [x] Define canonical trade record.
-   [x] Avoid duplicating Freqtrade data unnecessarily.
-   [x] Persist feature snapshot.
-   [x] Persist entry/exit reason.
-   [x] Compute MFE/MAE where reliable.
-   [x] Send durable events through outbox.
-   [x] Validate records against local trade state.

### Definition of Done - Phase 13

-   [x] A completed dry-run trade can be reconstructed from stored
    metadata.
-   [x] Trade context survives Supabase outage via outbox.

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

-   [x] Define formulas and assumptions.
-   [x] Avoid treating win rate as primary metric.
-   [x] Produce daily metrics.
-   [x] Produce strategy-version metrics.
-   [x] Produce regime-specific metrics.
-   [x] Test calculations against controlled samples.
-   [x] Persist summaries to Supabase.

### Definition of Done - Phase 14

-   [x] Metrics are reproducible from stored trades.
-   [x] Controlled test cases match expected calculations.

------------------------------------------------------------------------

# PHASE 15 - Backtesting framework

-   [x] Define historical-data download/cache process.
-   [x] Keep candles reproducible/disposable.
-   [x] Include fees.
-   [x] Use realistic execution assumptions.
-   [x] Check minimum order/precision.
-   [x] Prevent future leakage.
-   [x] Save summary results, not unlimited raw output.
-   [x] Limit resource usage.
-   [x] Run research at lower priority than trading.
-   [x] Document backtesting procedure.

### Definition of Done - Phase 15

-   [x] Baseline backtest is reproducible.
-   [x] Resource usage is bounded.
-   [x] Backtest does not interfere materially with trader runtime.

------------------------------------------------------------------------

# PHASE 16 - Strategy evaluation and lifecycle

Lifecycle:

`DRAFT -> BACKTESTED -> OUT_OF_SAMPLE_TESTED -> WALK_FORWARD_TESTED -> PAPER_TRADING -> CANDIDATE -> APPROVED`

Approval does **not** enable real money.

Checklist:

-   [x] Implement lifecycle metadata.
-   [x] Prevent invalid state transitions.
-   [x] Define evaluation criteria.
-   [x] Compare return and drawdown.
-   [x] Compare profit factor/expectancy.
-   [x] Compare Sharpe/Sortino.
-   [x] Require adequate trade count.
-   [x] Evaluate stability.
-   [x] Store evaluation evidence.
-   [x] Keep human approval boundary for real trading.

### Definition of Done - Phase 16

-   [x] Strategy state is traceable.
-   [x] A high-profit but unstable/overfit strategy is not automatically
    promoted.
-   [x] Autonomous promotion cannot bypass hard risk gates.

------------------------------------------------------------------------

# PHASE 17 - Champion / Challenger framework

-   [x] Register baseline as initial control/champion candidate.
-   [x] Define challenger metadata.
-   [x] Compare on equivalent datasets/windows.
-   [x] Compare out-of-sample.
-   [x] Compare walk-forward.
-   [x] Compare by market regime.
-   [x] Do not replace champion based solely on absolute historical
    profit.
-   [x] Record promotion/rejection reason.

### Definition of Done - Phase 17

-   [x] Every promotion/rejection is evidence-backed and auditable.
-   [x] Strategy history remains available.

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

-   [x] No massive parallel search.
-   [x] No thousands of concurrent backtests.
-   [x] Check free RAM/load/disk before research job.
-   [x] Use `nice`/`ionice` where appropriate.
-   [x] Defer research when trading resources are constrained.
-   [x] Persist experiment metadata/results.
-   [x] Avoid keeping large failed artifacts.
-   [x] Implement experiment IDs and reproducibility metadata.
-   [x] Implement day/night scheduling policy.
-   [x] Keep research disabled or low priority during trading hours.
-   [x] Candidate strategies are prepared for review/paper deployment,
    not uncontrolled live replacement.

### Definition of Done - Phase 18

-   [x] Lightweight experiment pipeline exists.
-   [x] It cannot starve the trading process.
-   [x] Heavy search is explicitly marked NOT ACTIVE on current VPS.
-   [x] Night research can produce candidate recommendations without
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

-   [x] Document future FreqAI architecture.
-   [x] Define chronological train/validation/test.
-   [x] Define walk-forward process.
-   [x] Define feature versioning.
-   [x] Define model versioning.
-   [x] Define artifact metadata/checksum.
-   [x] Define retraining triggers.
-   [x] Define anti-leakage checks.
-   [x] Define champion/challenger ML evaluation.
-   [x] Mark heavy continuous training as NOT ACTIVE until resources
    allow.
-   [x] Define retraining windows, initially night-only.
-   [x] Define shadow-mode validation before any live deployment.
-   [x] Define drift detection and automatic deactivation criteria.

### Definition of Done - Phase 19

-   [x] `docs/FREQAI.md` provides an implementable upgrade path.
-   [x] Current runtime does not waste resources pretending to run heavy
    ML.
-   [x] ML cannot autonomously increase live exposure.

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

-   [x] Implement health checks.
-   [x] Implement stale-market-data guard.
-   [x] Implement Supabase-offline indicator.
-   [x] Implement queue-growth warning.
-   [x] Implement disk warning.
-   [x] Implement risk-limit alerts.
-   [x] Define fail-safe no-new-entry states.
-   [x] Existing positions remain manageable during remote-backend
    outage.
-   [x] Document recovery procedures.

### Definition of Done - Phase 20

-   [x] Simulated failures produce safe behavior.
-   [x] Critical conditions are visible and documented.

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

-   [x] Add `.env.example` placeholders.
-   [x] Do not commit token/chat ID.
-   [x] Implement rate-conscious notifications.
-   [x] Avoid secret leakage.
-   [x] Test with mocks unless credentials are explicitly supplied.

### Definition of Done - Phase 21

-   [x] Notification subsystem is optional and cannot break trading
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

-   [x] Configure bounded log rotation/compression.
-   [x] Define disk thresholds.
-   [x] `<70%` normal.
-   [x] `70-80%` warning.
-   [x] `80-90%` clean only safe temp/reproducible data.
-   [x] `>90%` stop research and emit critical warning.
-   [x] Never auto-delete critical data.
-   [x] Test cleanup on safe synthetic data.

### Definition of Done - Phase 22

-   [x] Logs cannot grow without bound.
-   [x] Disk guard never deletes critical state.
-   [x] Research stops before filesystem exhaustion.

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

-   [x] Create backup command/script.
-   [x] Timestamp archive.
-   [x] Compress.
-   [x] Generate checksum.
-   [x] Verify archive after creation.
-   [x] Create restore command/script.
-   [x] Restore into controlled test location.
-   [x] Verify restored contents.
-   [x] Document `docs/BACKUP_RESTORE.md`.
-   [x] Do not include huge candle cache by default.

### Definition of Done - Phase 23

-   [x] A backup has been created and verified.
-   [x] A restore test has succeeded.

------------------------------------------------------------------------

# PHASE 24 - Migration to stronger VPS

Target workflow:

Old VPS: 1. stop research 2. gracefully stop trader 3. flush Supabase
queue 4. create compact export

New VPS: 1. clone repo 2. restore secrets securely 3. install runtime 4.
import critical state 5. reconnect Supabase 6. re-download reproducible
market data 7. start dry-run 8. verify health

Checklist:

-   [x] Create `docs/MIGRATION.md`.
-   [x] Create export/import tooling.
-   [x] Exclude bulk reproducible candles by default.
-   [x] Verify archive checksum.
-   [x] Document handling of IP-whitelisted Bybit keys for future real
    trading.
-   [x] Test export locally without destructive migration.

### Definition of Done - Phase 24

-   [x] Compact migration package can be produced.
-   [x] Migration procedure does not depend on copying the entire 20 GB
    disk.

------------------------------------------------------------------------

# PHASE 25 - Reboot/crash recovery

-   [x] Define startup order.
-   [x] Trader starts before research.
-   [x] Heavy research does not auto-start during constrained recovery.
-   [x] Test process crash.
-   [x] Test controlled service restart.
-   [x] Test server reboot only if safe for existing VPS services.
-   [x] Verify outbox recovery.
-   [x] Verify local state.
-   [x] Verify no duplicate trades/events.

### Definition of Done - Phase 25

-   [x] CryptoForge recovers safely without requiring manual database
    repair.
-   [x] Existing VPS services remain healthy.

------------------------------------------------------------------------

# PHASE 26 - Security audit

-   [x] Search working tree for secrets.
-   [x] Inspect Git status/history as appropriate for accidental
    secrets.
-   [x] Check `.env` permissions.
-   [x] Check listening ports.
-   [x] Check container exposure.
-   [x] Check admin/API exposure.
-   [x] Check logs for secrets.
-   [x] Check Supabase privileged key handling.
-   [x] Review RLS if applicable.
-   [x] Confirm Bybit withdrawal permission is never required.
-   [ ] Reconcile actual live executor and current admission evidence (R1–R5).
-   [x] Confirm Futures/leverage remain disabled.

### Definition of Done - Phase 26

-   [x] No known plaintext secret is committed/exposed.
-   [x] No unnecessary public administrative endpoint exists.

------------------------------------------------------------------------

# PHASE 27 - Quant audit

Explicitly inspect:

-   [x] Lookahead bias.
-   [x] Data leakage.
-   [x] Future candles.
-   [x] Incorrect indicator shifting.
-   [x] Unrealistic fills.
-   [x] Fees.
-   [x] Spread assumptions.
-   [x] Minimum order sizes.
-   [x] Precision.
-   [x] Selection bias.
-   [x] Hyperparameter overfitting.
-   [x] Insufficient trade count.
-   [x] Chronological split.
-   [x] Out-of-sample separation.
-   [x] Walk-forward methodology.

### Definition of Done - Phase 27

-   [x] Findings are documented.
-   [x] Blocking quant flaws are fixed before claiming strategy
    validity.

------------------------------------------------------------------------

# PHASE 28 - Resource audit

Measure actual:

-   [x] Trader RAM.
-   [x] Total CryptoForge RAM.
-   [x] Swap usage.
-   [x] Idle CPU.
-   [x] Scanner CPU.
-   [x] Light backtest CPU/RAM.
-   [x] Disk footprint.
-   [x] Outbox footprint.
-   [x] Log growth.
-   [x] Supabase sync behavior.

Record results in `FINAL_AUDIT.md`.

### Definition of Done - Phase 28

-   [x] Resource measurements are real, not estimates.
-   [x] Current VPS limitations are explicit.
-   [x] Upgrade triggers are documented.

------------------------------------------------------------------------

# PHASE 29 - Code-quality audit

Search for:

-   [x] `TODO`
-   [x] `FIXME`
-   [x] `pass`
-   [x] `NotImplemented`
-   [x] stubs/placeholders
-   [x] production mocks
-   [x] hardcoded secrets
-   [x] broad/empty exception handling
-   [x] disabled tests
-   [x] dead code
-   [x] unsafe defaults
-   [x] unbounded loops
-   [x] unbounded storage
-   [x] accidental `dry_run=false`

### Definition of Done - Phase 29

-   [x] Every relevant finding is fixed or explicitly documented as
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

-   [x] Bybit public data works.
-   [x] Market Scanner works.
-   [x] Market Regime works.
-   [x] Baseline strategy works.
-   [x] Independent Risk Engine works.
-   [x] Freqtrade dry-run works.
-   [x] Trade Journal works.
-   [x] Supabase sync works.
-   [x] Local outbox works through outage/recovery.
-   [x] Monitoring/fail-safe works.
-   [x] Backup and tested restore work.
-   [x] Migration export is ready.
-   [ ] Actual Supabase live execution is reconciled with runtime-specific gates (R1–R5).
-   [x] Futures are still disabled.
-   [x] Leverage is still disabled.
-   [x] Heavy FreqAI is honestly marked inactive if not running.
-   [ ] Current complete end-to-end audit closes R1–R16; historical FINAL_AUDIT
    and current reconciliation alone do not establish live readiness.

------------------------------------------------------------------------

# PHASE 31 - Controlled autonomous live trading pilot

This phase supports the revised long-term objective: autonomous daytime
trading and nighttime learning. It may begin only after Phase 30 is
complete and no blocking security, quant, risk, backup, restore,
monitoring or resource audit item remains open.

Status: **incomplete**. Checkboxes for primitives below retain their original
Freqtrade/design scope. Actual Supabase executor admission and operational
qualification require R1–R16; no blanket transfer of these checks is valid.

Live trading scope for the first pilot:

-   [x] Bybit only.
-   [x] Spot only.
-   [ ] Dedicated sub-account only.
-   [x] No withdrawal permission.
-   [x] No futures.
-   [x] No margin.
-   [x] No leverage.
-   [x] No martingale or martingale-like recovery logic.
-   [x] IP-whitelisted API key where feasible.
-   [x] Small capital allocation chosen explicitly by the user.

Pre-live checklist:

-   [ ] Confirm `.env` and VPS secrets are set with least privilege.
-   [x] Confirm `dry_run=false` is impossible without an explicit live
    config file and explicit operator command.
-   [x] Create separate live config; do not mutate dry-run config.
-   [x] Verify live config has Spot only.
-   [x] Verify live config has no leverage/futures/margin settings.
-   [x] Verify withdrawal permission is absent.
-   [ ] Verify kill switch.
-   [ ] Verify no-new-entry switch.
-   [ ] Verify daily loss guard. Runtime qualification: R3/R5.
-   [ ] Verify max drawdown guard.
-   [ ] Verify max position size. Runtime qualification: R3/R5.
-   [ ] Verify max simultaneous positions. Runtime qualification: R3/R5.
-   [x] Verify minimum order/precision handling.
-   [x] Verify monitoring alerts.
-   [ ] Verify backup/restore immediately before live start.
-   [ ] Verify current VPS resources are sufficient or migrate first.

Autonomous day mode:

-   [ ] Run only approved live strategies.
-   [x] Monitor strategy health.
-   [x] Pause strategy after configured abnormal loss/drift/error.
-   [x] Never edit live strategy code in place while positions are open.
-   [ ] Persist all decisions and trade context.
-   [x] Keep user-visible daily summary.

Autonomous night mode:

-   [x] Stop or avoid resource-heavy jobs if trading runtime is active
    and constrained.
-   [x] Run bounded backtests/research.
-   [x] Compare candidates against champion.
-   [x] Produce candidate recommendations.
-   [ ] Promote only through configured gates.
-   [ ] Deploy first to shadow/paper mode.

Objective:

-   [x] Optimize for risk-adjusted capital growth.
-   [x] Penalize drawdown, instability, illiquidity and excessive
    turnover.
-   [x] Reject strategies optimized only for maximum historical profit.
-   [x] Reject strategies that seek "fastest money" by violating risk
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

## 2026-10-14 — Reconcile plans against actual executor and evidence

Reason: root plan/README/final audit described September dry-run, while Linux
Supabase executor is installed with --live and research continued through October.
Impact: preserve historical phases; reopen misleading current/live checks;
record R1–R16 and distinguish code tests, source arithmetic, independent
profitability and operational admission. No executor/model/service/order changes.
Verification: 1057 passed, 1 deselected; saved input/runtime and minute snapshot
checks; installed timer/ExecStart read-only inspection. See dated reconciliation.

## 2026-10-18 — Correct research scope and link the VP supplement

Reason: user clarified that another agent owns the LLM plan. Its provisional
integration and continuation tasks were removed from this research queue.
The standalone LLM plan and implemented diagnostics remain available to that agent.
Impact: the existing research master preserves its phases/checklists and adds
the user-supplied VP specification with dependencies; no duplicate root checklist.
Verification: original804 research checkboxes retained, unique VP section and
documentation links checked; independent review and Git commit/PR remain open.
No research run, model publication, order or service change in this correction.
