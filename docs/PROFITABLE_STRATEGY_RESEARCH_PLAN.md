# План поиска и проверки прибыльных торговых ситуаций

> **Архив с 5 ноября 2026.** Очередь и чеклисты ведутся только в
> [CURRENT_PLAN.md](CURRENT_PLAN.md). Этот файл — дневник решений.
> Раздел «27 октября: актуальные чек-листы» больше не является текущим
> статусом: часть его открытых пунктов закрыта 1–2 ноября, часть галочек
> уже тогда была только частичной.

Дата: 7 октября 2026 года. Проект: CryptoForge. Базовый commit после сверки с другим чатом: `da16f15`.

2 ноября: сверена работа другого бота с Bybit по R8 — новых исполнений с
8 октября в проверенном интервале нет, остатки 23 активов согласованы;
контекст 20/30 закрывающих ордеров найден, потеря контекста десяти объяснена
старой коллизией ключа. Повторно прошли 33+42 теста. [Сверка](EXECUTION_RECONCILIATION_20261102.md),
[чек-лист](PLAN_REMAINING_CHECKLIST_20261101.md).

2 ноября, R8: повторный read-only audit показал неизменный SHA исходных
исполнений локального кэша по сравнению с 14/28 октября:49 FIFO-сегментов,
суммарно −1,3055964 USDT. Актуальные сделки биржи не подтверждены.
[Очередь и evidence](PLAN_REMAINING_CHECKLIST_20261101.md).

2 ноября, 09:43 МСК: сверены результаты другого чата по R6 — закрыты прежние
31 недавний и 279 исторических endpoint; текущее read-only наблюдение показывает
0 зрелых незакрытых в последних 36 часах и 0 старых, 46 ещё не созрели.
Повторно прошли 42 связанных теста. Позднее получение исторических цен не
является исторической доступностью или денежной прибылью. [Чек-лист](PLAN_REMAINING_CHECKLIST_20261101.md),
[recent recovery](FORECAST_OUTCOME_RECOVERY_20261102.md),
[historical recovery](HISTORICAL_FORECAST_RECOVERY_20261102.md).

1 ноября, 19:12 МСК: диагностика отдельно показывает 39 новых прогнозов,
которые ещё не созрели; запись новых outcomes остаётся для последующей проверки.
31 связанный тест прошёл. [Чек-лист](PLAN_REMAINING_CHECKLIST_20261101.md).

1 ноября, 19:11 МСК: ручная диагностика forecast ledger получила явный
`--env-file`, чтобы учитывать рабочий лимит 512 МиБ; 30 связанных тестов
прошли. Новая запись forecast подтверждена, новый outcome ещё ожидает проверки.
[Текущая очередь](PLAN_REMAINING_CHECKLIST_20261101.md).

Актуализация 1 ноября 2026: выполнена повторная read-only проверка
диагностического хранилища прогнозов и 147 совместимых тестов. Хранилище
по-прежнему достигло лимита 256 МиБ, последний прогноз записан 24 октября;
восстановление записи и полный runtime inventory остаются открытыми. Подробная
очередь, результаты и ограничения: [сверка и чек-лист](PLAN_REMAINING_CHECKLIST_20261101.md).
Отдельный LLM-план ведётся другим агентом; основная БД — локальная.

1 ноября, 18:58 МСК: ограниченная проверка хоста выявила активные таймеры
executor и outcome при inactive службах, неполную видимость процессов и не
подтвердила безопасное переключение ledger. Feeder failed при активном timer;
повторяющиеся `ValueError` в журнале не устанавливают конкретную причину.

Актуализация 28 октября: **R4/R15 competing writers и R7 модель** — в
журнале обучения20 synced pairs, 4 совпадают с incomplete selection; health
согласуется по списку, но author строк не доказан. Кандидат253dc4fce7
не продвинут:2 signals/420, сравнение с incumbent несовместимо; positive
test probability metrics не cash P&L. 24new+123compat=147tests.
[Писатели](FEEDER_COMPETING_WRITERS_20261028.md), [модель](MODEL_TRAINING_STATUS_20261028.md).

Актуализация 28 октября: **R4/R15 selected_sync effect envelope** — current
REST по20 ранее выбранным парам:14 последних closed candles старше часа;
SQL/REST/SQL BTC stale≈14ч06м, ETH fresh. Historical effect unknown,
13new+110compat=123tests. [Evidence](FEEDER_SELECTED_SYNC_OBSERVATION.md).

Актуализация 28 октября: **повторный разбор кэша сделок** — 75 rows, input
идентичен14 октября; из49 закрытых FIFO-сегментов28 убыточны,16 ≤−1%,
6 с комиссией, перекрывшей неотрицательный результат. Это не проверка
актуальной истории биржи. [Evidence](EXECUTION_CACHE_REVIEW_20261028.md).

Актуализация 28 октября: **R4/R15 current feeder guard** — в13:30 МСК
service failed, timer active; read-only `_entries` подтверждает препятствие
незавершённого цикла, эффект selected_sync остаётся unknown.
[Evidence](FEEDER_GUARD_CURRENT_20261028.md).

Актуализация 28 октября: **R6/R15 runtime inventory** — в13:28 МСК оба
timer active, службы между запусками inactive; fuser не показал PID,
полная видимость хоста не доказана. SQLite всё ещё256MiB,279 unresolved.
10new+68compat=78tests. [Evidence](FORECAST_RUNTIME_INVENTORY.md).

Актуализация 28 октября: **R6/R15 synthetic outcome ID и replay** — четыре
процесса присвоили47723–47726 на отдельной копии; повтор первого после
других вернул47723. 13new+49compat=62tests. Реальные writers и cutover
не подключены. [Контракт и evidence](FORECAST_OUTCOME_ID_REHEARSAL.md).

Актуализация 28 октября: **R6/R15 composite reader rehearsal** — все47979
forecasts и47700 as-of results совпали с исходным читателем, batch400 и
rows100 совпали; 8new+41compat=49tests. Live wiring и global outcome ID
открыты. [Evidence](FORECAST_RETENTION_READER.md).

Актуализация 28 октября: **R6/R15 isolated split rehearsal**: 47700/47722
в archive и279/0 в active; integrity и все typed rows совпали, независимый
SQL audit подтверждён. 7new+34compat=41tests. Будущие outcome ID могут
конфликтовать; переключение не выполнено. [Evidence](FORECAST_RETENTION_REHEARSAL.md).

Актуализация 28 октября: **R6/R15 retention preflight** — на проверенном
snapshot 47700 старых forecasts с47722 versions и279 protected unresolved;
9new+25compat=34tests. Это оценка кандидатов, не перенос или восстановление
записи. [Условия и evidence](FORECAST_RETENTION_PREFLIGHT.md).

Актуализация 28 октября: **R6 forecast capacity/maturity health**;
в06:11 МСК SQLite заполнена,0 unresolved в последних36h и279 зрелых
прогнозов без outcome до этого окна. Возможность восстановить endpoints не
доказана. 6new+25compat=31tests; [health и границы](FORECAST_MEMORY_HEALTH.md).

Актуализация 28 октября: **R4/R15 read-only inspection incomplete feeder**;
BTC/ETH source receipts самосогласованы, `selected_sync` отсутствует и её эффект
unknown. 06:08 МСК SQL/REST/SQL совпал по120 closed candles на той же local DB:
BTC stale≈6ч23м, ETH fresh. 7new+32compat=39tests; recovery по-прежнему открыт.
[Сверка и ограничения](FEEDER_INCOMPLETE_INSPECTION.md).

Актуализация 28 октября: **R6/R15 snapshot и isolated restore drill выполнены**;
actual диагностическая SQLite сохранена без изменения источника:47979 forecast,
47722 версии outcome, integrity и row digests verified, orphan0. 8new+17compat=
25tests; источник всё ещё на лимите, writer cutover и восстановление записи не
выполнены. [Контракт и результаты](FORECAST_MEMORY_SNAPSHOT.md).

Актуализация плана: **27 октября 2026 — W8.2b.3a: bounded paired coordinator.**
[Runbook](PAIRED_CACHED_COORDINATOR.md): durable prepared/completed операции,
explicit recovery подтверждённого tick без повтора worker/provider, учёт пропусков
и сохранение API cooldown. 22new+36compat=58tests/365.04s, накопленно827 разных;
прежние601 Python files сохранены. Synthetic3roles/12ticks/fills4/0/4, source/reader
и independent replay3/3. Это синтетика, не доказательство доходности.
**Остаётся:** W8.2b.3 unknown source/worker/finalization/host recovery, bounded
physical/native/capture history, actual positive и whole-host capacity, R1–R16/VP/W9/
economic gates. [Текущий checklist](#current-checklist). DB local; LLM — другой агент.

**Операционная диагностика 27 октября, 23:21 МСК:** локальный active `09b486e979`
старше36h, новый candidate `f8028fb44d` не прошёл signal screen; в отдельном
15-минутном окне23:00–23:15 были39 hold и0 rejects; в окне16:30–16:45
локальная БД подтверждает31 hold и7 no_fresh_model rejects. Forecast SQLite
достиг256MiB; managed feeder остановлен защитой из-за незавершённого после
смены загрузки цикла, BTC не обновлялся с17:11. Это разные наблюдения, не единое
доказанное объяснение всех hold. [Источники, время и ограничения](NO_BUY_DIAGNOSIS_20261027.md).
Новые R1/R2/R4/R6–R8/W8/W9/R14/R15 ниже остаются открытыми.

**Рабочая база с20октября — локальный PostgreSQL/PostgREST.** Явный selector
`CRYPTOFORGE_BACKEND=local`; authenticated read через
`http://127.0.0.1:54321` подтверждён **20 октября**, повторён26октября с bounded120SQL/REST/SQL binding.
[Схема backend и миграция](DATABASE_BACKENDS.md).
Проверка20октября выполнила read-only запрос с limit=1, не повторяла миграцию и не изменяла БД.
Cloud copy не считается актуальным источником после новых local writes; fallback
не используется. Имена legacy Python-модулей `supabase_*` не означают cloud endpoint.
Owned paper/archive/evidence SQLite roots остаются отдельными файлами; переход
основной БД не переписывает их original protocol/runtime/source pins и не обновляет
автоматически старые runtime approvals. Новые проверки используют новые contracts.

- [x] Учесть local backend в текущей очереди и подтвердить read availability;
  receipt `.local/state/paper-worker-replay-local-work-20261020/local-backend-read-check.json`.
- [x] W6a: original local PostgreSQL identity/schema/migration и source-row
  observation contract реализованы и проверены actual22октября; [runbook](LOCAL_SOURCE_PROVENANCE.md).
- [x] W6b.1/W6b.2: отдельный mandatory BTC/ETH capture, original source versions/
  first-seen и source-bound forecast/replay mechanism; actual public240rows ready.
- [x] W6b.3a: общий closed120 reader/frame и original compatible price forecast
  проверены actual через три роли; [контракт и границы](REFERENCE_SOURCE_READER.md).
- [ ] W6b.3b: рабочий reference refresh/primary linkage и deployment health.
  Managed feeder уже обновляет primary reference rows и связывает local REST
  с SQL instance. Длительный restart/host gate открыт; worker wiring/полнота — W7b.
- [x] W7a: original event retention, ordered three-role delivery и explicit
  ancestor recovery; [контракт и приёмка](REFERENCE_DELIVERY.md).

- [x] **W6b.3b.1:** reference-aware feeder cycle/strict health gates
  реализованы; [proposal и113tests](REFERENCE_AWARE_FEEDER.md).
- [x] **W6b.3b.2a:** original local route+120closed rows SQL/REST/SQL binding.
- [x] **W6b.3b.2b:** UID1000 installed managed feeder, actual BTC/ETH sync/probes,
  first service success, bounded operational retention/tests и pinned units.
- [x] **W6b.3b.2c:** автоматический timer cycle13:24UTC success/BTC/ETH fresh.
- [x] **W6b.3b.2d.1:**27октября313retained successes/0failures и238prune receipts;
  bounded operational retention наблюдён, fresh BTC120SQL/REST/SQL подтверждён.
- [ ] **W6b.3b.2d/R4/W8:** длительный outage/restart/host capacity/full continuity.

<a id="current-checklist"></a>

## 27 октября: актуальные чек-листы и оставшаяся работа

С 5 ноября 2026 эта сводка историческая. Очередь — [CURRENT_PLAN.md](CURRENT_PLAN.md).
Исходные этапы и дневник ниже — история
решений. До сверки22октября в master было 969 checkbox:706 выполненных и 263 пустых.
Это число строк с повторами, а не число самостоятельных задач и не процент
готовности. Исходные 804 checkbox сохранены:582 `[x]`,222 `[ ]`.

`[x]` ниже закрывает только прямо названную реализацию или проверку.
`[ ]` с пометкой «частично» требует завершить указанный остаток; «ожидание» —
дождаться frozen cutoff и проверить объём данных; «условно» — выполнять только
после предшествующих gates. Постоянные правила и шаблоны отчётов не закрываются
один раз навсегда. **Прибыльный кандидат и улучшение реального дохода не доказаны.**

### Что уже сделано и повторно реализовывать не нужно

- [x] **Архив и development-симулятор:** годовая фиксированная корзина 20 пар,
  closed-candle/causal contracts, trade-outcome labels, общий wallet, costs,
  stop/target/timeout и deterministic accounting реализованы. Старые пустые
  «создать симулятор/метки» в разделе «Состояние на начало» описывают 7 октября.
  Историческая достоверность исполнения остаётся R9/R10 ниже.
- [x] **Длинная численная сверка и минутные cases:** новый разрешённый 1024MiB
  профиль завершил long audit,40 sampled replays и 6/6 stop minute checks14 октября.
  Старые resource-deferred1536MiB попытки не повторять как единственный текущий
  статус. SHA отчётов и original sources сохранены; manual review ещё открыт.
- [x] **Зарегистрированные development studies:** train-window4 варианта,
  ablation7, balanced/unweighted2 и fixed/ATR4/4 выполнены. Последний grid:
  **0/4 economic passes**. Отрицательный результат закрывает эксперимент,
  но не требование получить пригодного кандидата. Buy-and-hold context выполнен
  отдельно и не заменяет comparison с тем же риском.
- [x] **Разбор потерь рабочего бота:** receipt14 октября содержит 49 закрытых
  FIFO segments,28 убыточных,16 с net потерей не менее 1%,6 случаев, где
  fee-equivalent издержки съели неотрицательный результат. Это сохранённый cache,
  а не проверка последних сделок 22 октября и не независимые 49 trades.
- [x] **Исторические source-проверки:**20 counterfactual trade labels,
  20 minute geometries и FIFO conservation49allocations/33remaining/14lots
  существуют. Это разные проверки; ни одна не закрывает human/historical gate.
- [x] **Защитные механизмы R1–R5:** local ownership/UID migration, controls,
  risk/reservations/drawdown, daily recovery, exit fallback/outbox/submit journal
  и runtime/account adapters реализованы и локально проверены. Их operational
  qualification и установка на выбранном действующем пути остаются открытыми.
- [x] **W1–W4, W5a, W5b.1–W5b.3:** новый producer v2, native archive14groups,
  whole-worker capture и независимые controller/FIFO/math/clock/valuation replay
  реализованы. Перепроверены 25 implementation/test SHA. Сохранённый результат
  21 октября:753 разных cases; это не новый full-suite run22 октября.
- [x] **Walk-forward подготовка:** календарь 6folds, validation grid,
  train/validation первого fold и observed cash-only selection подготовлены/
  выполнены в заявленной области. В fold0 нет прошедшего кандидата; cash job
  подготовлен до test start. Исторические пустые checklist календаря не означают,
  что календарь нужно создавать заново. Independent outcomes ещё не оценены.
- [x] **Local backend:** переключение основной БД и проверка переноса описаны
  в DATABASE_BACKENDS.md; read availability проверена 20 октября. Это не W6
  provenance всех actual upstream rows. Cloud-copy и legacy имена модулей
  не являются указанием вернуться к облачной базе.

Основные receipts: `.local/state/{execution-loss-review,edge-complete-trade-label-audit,
fifo-conservation-source-audit,extension-economic-screen}-20261014.json`,
`long-label-audit-jobs/9a1ed5c8747132cadc12073b0214713555ac549042d5e2c977d258e8232aa6a9/`
и `.local/state/paper-worker-replay-v2-work-20261021/`.
Сверка 22 октября: `.local/state/plan-checklist-reconciliation-work-20261022/verification.json`.

### R1–R5: действующий бот и риск — частично, общий допуск открыт

- [ ] **R1:** заново зафиксировать фактический runtime/host/account UID,
  permissions/IP, капитал, модель и единственного владельца исполнения.
  Проверить необходимые production migration/key/host recovery; отдельно
  определить границы same-host lease и защиты от второго host.
- [ ] **R2:** связать полный strategy/source/independent/paper admission с actual
  order path; подготовленный local runtime approval его не заменяет. Проверить
  kill/no-new-entry на выбранной цепочке и сохранение разрешённых exits.
- [ ] **R3:** квалифицировать реальные position/aggregate-stop-risk/daily-loss/
  drawdown limits, costs/gaps и snapshot/reservation lifecycle. Missing data,
  partial/dust/multi-buy/third-token fees и внешние cashflows не должны обходить
  ограничения или освобождать резерв без доказательства.
- [ ] **R4:** проверить реальный outage/restart/recovery, unknown holdings,
  private quantity/price/order APIs, exit latency и durable delivery.
  Fake-client tests не доказывают непрерывную защиту настоящих stops.
- [ ] **R5:** проверить исходную daily/peak baseline и её восстановление на
  выбранном account/host без потери накопленного loss; local CLI drill выполнен,
  actual account/host recovery ещё не подтверждён.
- [ ] **R1–R5/R15:** проверить фактически установленные flags и выполнить
  operational rehearsals по конкретному deployment plan. Последняя запись
  установленного `--live` относится к 14 октября; текущая сверка trading units не читала
  и не меняла; отдельно проверялись market-feeder и временная paper-служба. Наличие opt-in кода не подтверждает его включение.

- [ ] **R1/R2 — актуальный operational snapshot:** при действующем local backend
  сопоставить executor unit/UID/flags, current account/positions/risk и model event
  с локальными executions и защитами. Зависит от доступного read-only account;
  результат — timestamped source-bound отчёт без секретов; проверка: нет новых
  orders/изменения флагов, отдельно обозначены missing/unknown и границы кэша.
- [x] **R4/R15 partial inspection:** защищённое read-only чтение incomplete
  cycle, original source observation integrity и порядок стадий; missing
  `selected_sync` классифицирован unknown. 7new+32compat=39tests; доступ к
  current DB и доказательство результата sync эта проверка не выполняет.
  [Доказательства и границы](FEEDER_INCOMPLETE_INSPECTION.md).
- [x] **R4/R6 — current local source binding:** 28 октября06:08 МСК
  SQL/REST/SQL binding по120 closed BTC и ETH подтвердил одну identity/schema;
  BTC stale≈6ч23м, ETH fresh. Из historic/current BTC windows общие41 row ID
  имеют новые версии; ETH windows не пересекаются. Это два среза без причинной
  атрибуции и не восстановление feeder.
- [x] **R4/R15 current guard observation:**13:30 МСК service failed/timer active;
  read-only проверка исходной lease/registration подтвердила incomplete guard.
  Прошлую причину ValueError и эффект sync это не доказывает.
  [Evidence](FEEDER_GUARD_CURRENT_20261028.md).
- [x] **R4/R15 selected_sync partial-effects/current snapshot:** ограничены
  возможные эффекты через тестовые клиенты; local REST по20 парам и
  независимый SQL/REST/SQL BTC/ETH. 13new+110compat=123tests;
  historical effect остаётся unknown. [Evidence](FEEDER_SELECTED_SYNC_OBSERVATION.md).
- [x] **R4/R15 competing writer observation:** учебная служба reported20
  синхронизированных пар, 4 совпали с incomplete selection, health имеет
  тот же список; executor тоже имеет write path. Доказательство автора
  каждой исторической строки и полный inventory не получены.
  [Evidence](FEEDER_COMPETING_WRITERS_20261028.md).
- [ ] **R4/R15 — неизвестный цикл feeder:** сохранить исходный каталог
  `cycle-1b53f296681044a08dcb2d006e232e68`, стадии и версии local rows;
  выяснить selected_sync effect через историю и сверку SQL/REST/primary rows.
  Зависимости: оригинальные receipts и доступная local DB. Результат — доказанная
  классификация каждой стадии и отдельная проверенная процедура recovery без
  повторения неизвестной операции; проверка fresh closed120 BTC/ETH, restart,
  durability и runtime pins. До доказательства не удалять incomplete cycle,
  не подделывать complete и не ослаблять guard.

### R6–R11: источники, реальные исходы и обучение — частично

- [x] **R6 guarded preflight:** до cutoff не открывать payload незавершённых
  train/validation; sealed-test/paper не читать этим readiness-путём.
  [Контракт и55tests](SEALED_CASH_READINESS.md). Counts пока не проверялись,
  а не равны нулю; actual trace подтвердил отсутствие открытия memory store.
- [x] **Local reference precheck26октября, до исправления:** BTC stale≈70h, ETH fresh;
  оба direct-SQL observations offline verified. Feeder timer active,
  последний oneshot success; current universe не содержит BTC/ETH.
  После нового feeder13:22UTC BTC/ETH fresh; длительный R4/W8 открыт.

- [ ] **R6, original features:** проверить fresh collector health и накопить
  future original closed bounded120 entry context без conflicts. Последний
  проверенный preflight14 октября:0 eligible,8 legacy incompatible; это не
  текущий счётчик 22 октября. Не переписывать старые 8rows и не считать архив
  реальными 100 покупками. Проверить raw instrument snapshot в новых actual
  order contexts без создания проверочной сделки.
- [ ] **R7, сравнение моделей:** выполнить execution-based candidate/control
  comparison с совместимыми frozen contracts. Legacy active09b486e979 имеет
  неизвестный контракт; candidatea252 и migration-v3 candidate041b не смешивать.
  Price endpoint/Brier/accuracy comparison не заменяет net income.
- [ ] **R8, ожидание/данные:** closed-cash train заканчивается
  **7 ноября 00:59:16 МСК**, validation — **21 ноября 00:59:16 МСК**.
  После cutoff проверить counts/days/pairs/classes frozen protocol и лишь
  затем fit/validation. Train требует 100buy/14days/6pairs/≥20 каждого класса;
  validation40buy/7days/4pairs/≥5 каждого класса. Дата сама по себе не даёт ready.
- [ ] **R9, ручной source registry:** свести минимум 20 полных source-bound
  cases с entry/known_at, fees/rounding/first-touch/residual basis и reviewer
  outcome. Представить gaps/ambiguity/partial/noncloseout либо явно оставить
  исключения. Готовые 20labels/geometries/FIFO использовать, не собирать заново.
- [ ] **R10, point-in-time execution:** завершить или явно ограничить область
  historical universe/listing/rules/steps/fees/fee assets/spread/depth/fill
  coverage. Current account fee observations не подтверждают прошлые тарифы;
  неизвестные partial fills и third-token conversion остаются unknown.
- [ ] **R11, частично:** versioned kernel/archive/capture/replay contracts уже
  созданы. Осталось source-bound qualification нового producer на полном
  local upstream/paired stream; original frozen manifests не переписывать.
- [x] **Повторная сверка локального execution cache, 28 октября:** 75 rows,
  hash как14 октября; повторено FIFO49/28 losses/16 ≤−1%/6 fee cases,
  8 совместимых тестов. Актуальная полнота биржи не подтверждена.
  [Evidence](EXECUTION_CACHE_REVIEW_20261028.md).
- [ ] **Успехи/ошибки рабочего бота, этап 8:** получить причинную strategy
  attribution и достаточно exact-context закрытий, проверить обновлённый
  cost-aware отбор и улучшение/ухудшение на независимом paired period.
  Loss review и training collectors есть; полезность переобучения для дохода,
  strategy-specific exits/churn/conflicts и полный цикл rollback ещё не доказаны.

- [x] **R6/R15 snapshot/restore drill:** создан новый изолированный SQLite
  snapshot actual price diagnostics и отдельный restore drill. Полная integrity,
  source transaction counts, все версии outcome и row digests проверены;
  отдельная read-only транзакция source в06:09 подтвердила те же schema/digests;
  8new+17compat=25tests, в том числе WAL и concurrent writer. Копии на том же
  разделе не заменяют независимый backup. [Evidence](FORECAST_MEMORY_SNAPSHOT.md).
- [x] **R6/R15 partial writer inventory:** source call sites и установленный
  outcome unit сопоставлены: executor record и outcome record не используют
  общий межпроцессный lease; report читает тот же выбранный ledger, feature
  migration имеет отдельный study store. Нормальный matured batch ограничен36h.
  Полный runtime inventory и восстановление пропущенных результатов ещё открыты.
- [x] **R6 price-diagnostic health:** отдельный read-only монитор ёмкости и
  незакрытых endpoint по36h/старше с учётом availability времени outcome;
  6new+25compat=31tests. Actual06:11: полный SQLite,0 unresolved в36h,
  279 старше. Он не подключён к service и не доказывает доступность endpoints.
  [Контракт и evidence](FORECAST_MEMORY_HEALTH.md).
- [x] **R6 bounded endpoint presence:** по сохранённому snapshot 279 старых
  прогнозов соответствуют277 различным endpoint/50 парам. Local REST 06:13
  содержит226 endpoint/226 прогнозов;51 endpoint не найден. Повторный capture
  сохранил12 requests/raw responses и прошёл offline replay. Это только presence
  сейчас, не OHLC validation и не historical known_at. [Evidence](FORECAST_MEMORY_HEALTH.md).
- [x] **R6 endpoint geometry preflight:** offline replay12 retained запросов/
  ответов подтвердил226/226 корректных OHLCV geometries;195 rows имеют stored
  updated_at не раньше закрытия,31 — раньше. Исторический known_at и финальность
  31 rows не подтверждены; результат outcome не записан. [Evidence](FORECAST_MEMORY_HEALTH.md).
- [x] **R6/R15 retention preflight:** классифицирован проверенный snapshot;
  старые результаты и все их версии учтены вместе, unresolved и недавние
  изменения защищены. 9new+25compat=34tests; 47700 candidates/279 protected.
  Это только inventory: доступность архива для readers и cutover не доказаны.
  [Контракт и evidence](FORECAST_RETENTION_PREFLIGHT.md).
- [x] **R6/R15 isolated split rehearsal:** две новые SQLite из pinned snapshot;
  47700/47722 archive,279/0 active; integrity и все typed rows подтверждены
  независимым SQL audit,7new+34compat=41tests. [Evidence](FORECAST_RETENTION_REHEARSAL.md).
- [x] **R6/R15 immutable composite reader rehearsal:** изолированный reader
  всех пяти read API; совпали47979 forecasts/47700 as-of results и batch400;
  synthetic late correction и conflict rejection проверены, 8new+41compat=49tests.
  [Evidence и ограничения](FORECAST_RETENTION_READER.md).
- [x] **R6/R15 synthetic outcome ID/replay rehearsal:** локальная SQLite
  сериализует cooperating writers, повтор event identity распознаётся даже
  после новой версии; четыре процесса, crash до/после commit и13new+49compat=
  62tests. Реальные writers и global fencing не доказаны.
  [Контракт и evidence](FORECAST_OUTCOME_ID_REHEARSAL.md).
- [x] **R6/R15 bounded runtime observation:** отдельный read-only inventory
  PID/FD и unit state, fail-closed при недостаточной видимости; выполнены
  ограниченные host probes и текущий health. 10new+68compat=78tests.
  [Evidence и пределы](FORECAST_RUNTIME_INVENTORY.md).
- [ ] **R6/R15 full host inventory:** полная видимость процессов/контейнеров,
  общий writer fencing и проверенная остановка таймеров перед переходом.
- [ ] **R6/R15 future outcome identity и composite readers:** устранить риск
  совпадения новых outcome ID между частями и сохранить глобальный порядок
  версий, реализовать и проверить объединённое чтение и late corrections.
- [ ] **R6/R15 — восстановить сбор диагностических forecast/outcome без потери:**
  зависимость — инвентаризация всех writers/readers, lock/async сценариев и бюджета
  свободного места. Спроектировать отдельный versioned storage/retention или иной
  проверяемый переход без удаления исходных записей, с copy/restore/reconciliation,
  atomic activation и откатом. Результат — архив с целостностью и сохранёнными ID,
  конкурентные readers/outcomes работают, новые прогнозы и результаты пишутся;
  проверки: bounded disk/reserve, параллельные процессы, crash/restart, integrity,
  counts/digests до/после и наблюдение actual цикла. Увеличение лимита само по
  себе не является решением; эта диагностика не создаёт real-buy labels.
- [x] **R7 partial current model observation:** journal candidate253dc4fce7
  не продвинут:2 signals/420; test1140 отдельно, log loss/Brier лучше
  baseline, incumbent сравнение заблокировано. Local registry event
  соответствует старой версии; loaded executor не доказан.
  [Evidence](MODEL_TRAINING_STATUS_20261028.md).
- [ ] **R7/R12 — migration/bootstrap совместимого primary price target:** сначала
  установить provenance active и кандидатского feature/target/fit/evaluation
  контрактов; неизвестный legacy не угадывать. Зарегистрировать независимое
  prospective окно, допустимый совместимый control и стабильный budget поиска;
  отдельно оценить количество unseen examples и signals после каждого cutoff,
  исходя из реальной частоты данных. Результат — reproducible parity и отчёт
  candidate/control с coverage, costs и uncertain/insufficient outcomes;
  проверка — исключение использованных интервалов, future mutation, разные contracts,
  disjoint windows и negative-control. Price screen не доказывает cash income.
- [ ] **R8 — зависимость накопления real-buy samples от закрытого gate:**
  мониторить поток реальных закрытий и причины no-entry по временным окнам;
  сравнить фактический темп с замороженными100/40 и class/pair/day требованиями.
  Зависимость — read-only источники и original closed-context записи. Результат —
  отдельный status `insufficient/blocked/ready` после своих cutoff, с причинами;
  проверка — не превращать historical, synthetic, price или hypothetical labels
  в real buys. Ожидание даты само по себе не открывает вход и не наполняет выборку.

### W6–W9 и R12–R14: исследовательская реализация и проверка результата

- [x] **W6a:** отдельный PostgreSQL observer/source contract, cluster/database/
  schema/RLS/migration pins, original UUID/xmin/raw row/query/runtime SHA и
  консервативный known_at actual query completion. Offline audit, revisions,
  gaps/future/stale guards проверены. Actual120BTC+120ETH;265tests этого этапа.
  [Детальные проверки и границы](LOCAL_SOURCE_PROVENANCE.md).
- [x] **W6b.1:** mandatory BTC/ETH collector независимо от dynamic universe,
  raw HTTP/query/clock SHA, closed120, failures/cooldown и durable poll journal.
  Actual23октября07:51UTC:120+120rows ready, offline integrity pass; primary DB
  и installed feeder не менялись. [Runbook/evidence](REFERENCE_SOURCE_LEDGER.md).
- [x] **W6b.2:** immutable versions/global first-seen внутри нового namespace,
  frozen artifact и оригинальный source-bound price forecast/replay mechanism.
  Отрицательные прогнозы сохраняются, stale/failed BTC блокирует ETH forecast,
  reread не обновляет возраст свечи. 61new+265compatibility=326tests passed.
- [x] **W6b.3a:** отдельный pre-start reader contract, immutable shared source
  frame и closed120/feature interface для candidate/control/stress; source first-seen,
  original forecast IDs/availability/negative probabilities и offline replay.
  Actual360rows/1AVAX forecast, одинаковый frame SHA и inputs трём ролям.
  Inference envelope304141→2906bytes, exact original probability equality;
  48new+326compatibility=374tests passed. [Runbook](REFERENCE_SOURCE_READER.md).
- [ ] **W6b.3b, частично:** installed reference refresh/primary REST linkage
  проверены26октября, BTC/ETH fresh после первого service cycle. Automatic repeat/
  длительные outage/restart/host проверки ещё открыты. Public IDs не подменяют SQL UUID.
- [x] **W7a:** original source-event prefix сохраняется с manifest/head anchors,
  negative/skip/failure/forecast IDs и global first-seen/revisions; после source
  append/new process старые inputs читает новый DeliveredReferenceReader.
  Три независимых cursor/pending/ack, no skipped/reordered batches, duplicate
  offer/ack idempotency и explicit lost-receipt ancestor recovery реализованы.
  39new+374compatibility=413tests passed. [Runbook](REFERENCE_DELIVERY.md).
- [x] **W7b.1:** bounded source/delivery coordinator,
  durable checkpoints, tail/cooldown/backlog monitoring и diagnostic input receipts;
  [runbook](REFERENCE_COORDINATOR.md).444tests passed; actual2polls/6packets,
  offline source/delivery/receipt replay и explicit completed-checkpoint recovery.
- [x] **W7b.2a:** отдельные pre-start cash hypotheses/role strategy SHA,
  exact candle/cost guards; cash-only control не заменяет legacy current model.
- [x] **W7b.2b:** полный fixed-pair decision stream на один poll/negative/skips,
  фактические CapturedPaperWorkerV2 prepared/completed result receipts, durable ack,
  heartbeats и readonly derivation/linkage audit. Synthetic replay3/3 прошёл.
- [x] **W7b.2c.1:** bounded single-use paired runner/public source/5s cadence/
  journal/finalization и actual minute проверены.240rows/12ticks×3/6decisions/
  33heartbeats/0fills; independent controller/FIFO/coverage3/3. Peak≈33MiB under512MiB.
- [x] **W7b.2c.2a:** separate actual public instrument+book acquisition BTC/ETH
  2/2,4GET/original normalization pass27октября10:50UTC; no new decisions/fills.
- [ ] **W7b.2c.2:** actual positive decisions/provider/fill/exit,
  более длинный preregistered paired stream и role-level failure/cadence monitoring.
  Этот short negative run не проверил positive path и не является long daemon.
- [x] **W7b.3a:** explicit recovery только known durable worker-result/ack;
  original source/worker prefix/native/head proof, no tick/provider rerun и новый
  checkpoint.17new tests/trueprocess-exit/synthetic3cases passed.
- [ ] **W7b.3b/W8:** missing result/unknown component side effects, whole-runner
  pending journal/lost checkpoint и host restart. Old component DB pin не усыновлять
  после commit без proof. Старый single-use runner не получил resume. Общая W7 открыта.
- [x] **W8.1:** metadata-only quota/count preflight, exact UTC source/tick slots,
  native/capture/app/journal/disk envelopes; no outcome read. Current short countpass,
  hypothetical30days26blockers,13new+19compat=32tests.
- [x] **W8.2a:** новый indexed lossless cash application v2: проверка последней
  записи вместо всей JSON-истории этого слоя, bounded decode, полный post-end
  audit и explicit recovery одного завершённого шага. 19new+50compat=69cases,
  synthetic independent replay3/3; [runbook и ограничения](CASH_APPLICATION_V2.md).
- [x] **W8.2b.1:** отдельный incremental cash source index: новые original events
  проверяются прежним SourceReplay, first-seen сохраняется, полный independent
  audit совпадает с projection.18new+100compat=118cases; synthetic12role packets
  matched, cooldown даёт0new events. [Runbook и ограничения](REFERENCE_PREFIX_V2.md).
- [x] **W8.2b.2a:** зарегистрированный cached reader связывает original role
  offer/batch/source prefix и точные event bytes с cached view; packets и cash
  decisions совпали с прежним reader.20new+18compat=38tests; synthetic9packets/
  18decisions, без actual worker. [Runbook](CACHED_REFERENCE_READER_V2.md).
- [x] **W8.2b.2b:** новый cached cash application v3 сохраняет reader proof
  внутри actual input/result/ack chain и выполняет frozen paper worker.
  17new+39compat=56tests; synthetic source/controller/FIFO audits3/3,
  fills4/0/4; [runbook и ограничения](CACHED_CASH_APPLICATION_V3.md).
- [x] **W8.2b.3a:** отдельный registered 20–300s paired coordinator, durable
  операции и explicit recovery сохранённого результата tick без повтора worker;
  22new+36compat=58tests, synthetic replay3/3/fills4/0/4.
  [Контракт, доказательства и границы](PAIRED_CACHED_COORDINATOR.md).
- [ ] **W8.2b.3/W7b.3b:** восстановление unknown source/prefix/queue/worker/
  finalization/replay и whole-host ещё не реализовано. Требуются fault drills и
  проверяемое восстановление без повторных внешних эффектов; до доказательства
  такой шаг блокируется. Старый runner не получил v3/resume автоматически.
- [ ] **W8.2 long-scope:** bounded physical source/delivery/native/capture history,
  квоты/replay и whole-host capacity. Physical SHA пока читает всю БД;
  original caps/registrations и type guards не ослаблять молча.
- [ ] **W8 — общая qualification:** positive-load whole-worker/host RSS,
  payload/queue/network, full-tick wall, длительные disk/retention/recovery и review.
  Actual short negative peak≈33MiB не является long/positive capacity; count estimates
  30days/poll5s также не заменяют measurements.
- [ ] **W5 — общая qualification:** после W6–W8 подтвердить producer + upstream
  + runner + host вместе. Математические исправления W5a/W5b уже сделаны;
  общий пункт остаётся открытым из-за интеграции и источников.
- [ ] **R12:** закончить полную preregistered selection/execution procedure,
  native/current-model/new-head/cash controls и остальные folds; bounded
  development studies, календарь и virtual cash job не закрывают эту процедуру.
- [ ] **R13, ожидание и реализация:** первый blind test заканчивается
  **15 ноября 00:00UTC = 03:00 МСК**. До cutoff outcomes не читать. После cutoff
  выполнить cash component и полную independent evaluation; затем остальные
  nonoverlapping windows, block bootstrap, count/PF/DD/stress/concentration
  и calibration по frozen protocol. Все 6 окон завершаются только
  **14 апреля 2027,03:00 МСК**;15 ноября заканчивается первое, а не вся процедура.
  Ноль сделок не доказывает доходность.
- [ ] **W8/W9/R14/R2 — migration не равна допуску:** после совместимого
  source-bound кандидата и контроля заранее зарегистрировать cost/fees/slippage/
  execution assumptions и shadow/paper; повторить независимый replay и adverse
  stress, затем оценить activity, net returns, uncertainty, risk и согласованность
  работающего order path. Зависимости — R7/R12, доступные данные, W6–W8 и gates;
  результат — evidence-bound decision PASS/REJECT/INSUFFICIENT, проверка —
  исходные timestamps и tests, ни один synthetic run не заменяет future paper.
  Модель и активные флаги не переключать без всех необходимых разрешений/gates.
- [ ] **W9/R14, условно:** после qualifying offline candidate и W6–W8 заранее
  зарегистрировать НОВОЕ candidate/control/stress study и вести actual future
  stream минимум 30 дней/100closed paper trades по общему плану, independent
  replay и economic review. Отдельный closed-cash14days/60trades protocol
  не сокращает этот срок. Старые historical quotes задним числом не добавлять.

### Ранние этапы 3–5: исследования, которые ещё не закончены

Эти пункты не исчезают из очереди после завершения инфраструктуры paper.
Прежние development эксперименты повторять нельзя без новой гипотезы,
зарегистрированной версии и сохранения общего бюджета поиска.

- [ ] **Этап 3, net/risk targets:** обучить и сопоставить обе net heads и risk
  objective на qualified данных; проверить availability/class/signal counts
  по периодам и парам. Смена имени target не является миграцией original данных.
- [ ] **Этап 3, признаки:** подтвердить point-in-time turnover/VWAP, BTC/ETH,
  multitimeframe/time/liquidity context и streaming parity всей применяемой
  схемы. Bounded120 parity проверена в своей области; live schema и польза
  расширенных признаков на независимых окнах ещё не подтверждены.
- [ ] **Этап 4, фильтры/параметры:** зарегистрировать дополнительный ограниченный
  filter grid, проверить соседние значения параметров и rule-only против ML
  при одинаковых capital/risk/costs. Доказать добавочную пользу ML, а не только
  уменьшение RMSE или меньший убыток. Разработка 18 вариантов и fixed/ATR4/4
  уже завершены, новый test нельзя выбирать по их лучшему прошлому результату.
- [ ] **Этап 5, payoff selector:** применить полный preregistered threshold grid
  к validation portfolio payoff/activity/ordinary+stress risk; отдельно
  оценивать вероятность прибыли, размер результата и решение о входе.
  Код selector готов; полезный прошедший кандидат не получен.
- [ ] **Этап 5, устойчивость обучения:** independent natural-distribution
  calibration, nonlinear/balancing/window/ablation stability и portfolio
  benefit на достаточных неперекрывающихся окнах. Уже выполненные descriptive
  diagnostics и отрицательные development studies не закрывают эту проверку.
- [ ] **Этапы 4–6, критерий результата:** получить кандидата, прошедшего
  заранее заданные activity/uncertainty/cost-stress/drawdown/concentration
  gates против compatible controls. При отсутствии преимущества сохранить
  REJECTED/INSUFFICIENT_EVIDENCE; это не основание ослаблять критерии.

### VP, эксплуатация и завершение всего плана

- [ ] **INT-01/09/10:** полная повторная сверка исходных документов,
  независимый reviewer и Git-фиксация с выделенным scope ещё не выполнены.
  INT-02…08 выполнены в области документации. Проверить источник видео/
  расшифровки: локальная спецификация есть, первоисточник пока не подтверждён.
- [ ] **VP-00…VP-09:** read-only baseline → causal preregistration → primitives
  →7 гипотез → execution/stress → economic screen → future paper → условный ML
  → QA/findings. Готовые общие simulator/capture/replay переиспользовать;
  они не являются реализацией семи VP-стратегий. Все фазы VP ещё открыты.
- [ ] **R15:** backup/restore/restart/outage, уведомления, account/host ownership
  и resource qualification на выбранном runtime. Backup самой local БД не
  заменяет совместное восстановление journals/risk/reservations/outboxes.
- [ ] **R16, Phase30/31:** финальная проверка всех соответствующих gates,
  dedicated limited account/permissions, explainable trades, day/night cycle,
  rollback и performance review против paper. Исторические `[x]` фаз 0–29
  не подтверждают текущий deployment или profitable autonomous trading.

Порядок: operational R1–R5 сохраняют приоритет; в текущей research-ветке
реализовать **W6b → W7 → W8**, одновременно закрывать доступные R6/R9/R10 и
готовить R7/R12 без раскрытия sealed outcomes. R8/R13 ждут своих разных
cutoffs и достаточной выборки; W9/R14 ждут квалифицированного кандидата.
VP зависит от INT и source/economic gates. **LLM-план исключён: другой агент.**

При продолжении менять эту сводку и соответствующий детальный пункт вместе:
ID, точная область, source/runtime SHA, команда/receipt/date, результат и
оставшееся условие. Исторические 804 строки не переписывать. Требования
этапа 8/раздела 12 («цикл улучшений»/«артефакты каждого эксперимента») считать
повторяемыми обязанностями, а не незапущенными разовыми задачами.

## CF-VP-2026-10-17 - Video-derived Strategy Research

Дополнительное направление: формализовать и проверить семь гипотез VP Crypto
в Bybit Spot long-only, с причинными данными и расходами. Подробная
[спецификация и acceptance checklist](CryptoForge_VP_Research_Checklist_ActivePlan.md),
[карта REUSE / EXTEND / NEW / BLOCKED](video_research/INTEGRATION_MAP.md).
Это дополнение к существующим этапам; основной исследовательский план — этот файл.

**Статус:** локальная интеграция документации подготовлена; INT-01 (полная
повторная сверка всех исходных документов), INT-09 (отдельный reviewer) и
INT-10 (commit/PR) остаются открытыми. Все исследовательские VP-00…VP-09
ещё открыты. Владелец этой очереди и документации — текущий агент; задачи
выполняются последовательно. Назначение других агентов не производилось.

Источник: предоставленная пользователем локальная спецификация версии1.1,
SHA256 `b13852096987cb877a2568a33e5e2fc299a31beb6a2fae507fe73982440adc1b`.
Fetch ранее выполнен, origin/main остался `8da4cb17`; эта спецификация не
выдаётся за новую версию, полученную с Git. Исходные bytes, dirty status и
base commit сохранены в `.local/state/vp-plan-integration-20261018/`.
Названные в спецификации видео/транскрипт пока не найдены среди доступных
вложений; source provenance исходных высказываний не подтверждена.

- [x] Сохранить checkpoint и встроить один раздел VP с detailed specification,
  dependency map и ссылками в прежние этапы; не переносить сюда LLM-задачи.
- [ ] Завершить INT: полная повторная сверка исходных документов, независимый
  review diff и дальнейшая Git-фиксация; локальные проверки не заменяют reviewer.
- [ ] **VP-00 — read-only аудит runtime, API и ресурсов.** После INT;
  текущие installed flags/ресурсы и отсутствие конфликтов проверить заново.
- [ ] **VP-01 — causal data и новый immutable preregistration.** После VP-00;
  source provenance, исторические rules/universe, closed 5m/15m/1h/1D,
  known_at, фиксированные splits/costs/budget до оценки результатов.
- [ ] **VP-02 — causal primitives и typed ResearchSignal.** После VP-01;
  EXTEND существующие closed-timeframe/support/risk функции, новые pivots,
  trendline и явно приблизительный POC; никаких изменений frozen kernels.
- [ ] **VP-03 — CF-VP-01…CF-VP-07 в research Strategy Lab.** После VP-02;
  приоритет CF-VP-01/02/04/05/07, CF-VP-03/06 зависят от качества данных.
- [ ] **VP-04 — shared-wallet execution и risk tests.** После VP-03;
  REUSE simulator/paper accounting, EXTEND limit TTL/partial/non-fill и
  event ordering. Касание OHLC не доказывает исполнение лимитки.
- [ ] **VP-05 — зарегистрированная экономическая проверка.** После VP-04;
  paired baseline/cash, ordinary/stress, все попытки в прежнем ledger,
  отрицательные и zero-trade результаты сохранять. Старые 0/4 extension
  passes не заменяют эксперимент VP и не становятся новым blind test.
- [ ] **VP-06 — prospective isolated shadow/paper.** После VP-05 и R2/R14
  source/mark qualification; НОВЫЙ frozen protocol до наблюдения outcomes.
- [ ] **VP-07 — условный research-only ML.** После достаточных зрелых меток
  и VP-06 evidence; допустим NOT_READY. Fit не меняет model.active.
- [ ] **VP-08 — QA/security/ресурсы/совместимость.** Проверки вести на каждом
  этапе, итоговый independent review обязателен; нет допуска к live.
- [ ] **VP-09 — findings, полный experiment registry и синхронизация.** После
  evidence/review; отсутствие прибыльного кандидата — допустимый итог.

Стратегии, каждая по собственной preregistration: **CF-VP-01** Fib0.382/0.5
с prior support и одним общим risk budget; **CF-VP-02** confirmed trendline
с закрытой1D свечой; **CF-VP-03** support + `approx_ohlcv_poc` либо отдельно
подтверждённый trade-derived POC; **CF-VP-04** range + wick-sweep price proxy;
**CF-VP-05** BTC as-of filter в paired on/off сравнении; **CF-VP-06** hammer
у заранее известной поддержки; **CF-VP-07** invalidation/TTL/no-chase.
Неоднозначные тикеры/цены и рекламная доходность из видео не становятся rules
исполнения. Стоп3% из примера не является универсальным risk default.

**Зависимости и возобновление:** operational R1–R5 сохраняют приоритет;
R6–R11 source quality, R12–R14 independent evaluation/paper и R15–R16
operational review не закрыты. Старые protocols/окна/бюджеты не менять.
Прежний **R2/R14** продолжается: локальный capture original mark quotes /
causal sequence и independent replay реализован (см. [runbook](PAPER_VALUATION_CAPTURE.md)).
Lifecycle v2/time-coverage/capture guards реализованы локально. Отдельный
[segmented storage-компонент](EVIDENCE_SEGMENTS.md) и [capture v3 adapter](PAPER_CAPTURE_V3.md)
тоже реализованы. Отдельный [native archive/projection engine](NATIVE_PAPER_ARCHIVE.md)
теперь реализован. [Capture v4](PAPER_CAPTURE_V4.md) связывает его с prospective ledger,
исходными row deltas/checkpoints и sealed CLI. [Streaming replay](PAPER_STREAMING_REPLAY.md)
независимо пересчитывает cash/FIFO/fill math/valuation/time coverage. Отдельный
[worker source journal](PAPER_WORKER_CAPTURE.md) теперь сохраняет full tick inputs,
clock/provider observations и atomic native actions. [Независимый worker replay](PAPER_WORKER_REPLAY.md)
теперь восстанавливает решения переданных batches и wallet/FIFO/coverage с новым
pre-start local backend contract. Отдельное [ядро producer v2](PAPER_PRODUCER_V2.md)
с causal FIFO/strict cash/cutoff реализовано. Новый [versioned archive](NATIVE_PAPER_ARCHIVE_V2.md)
с kernel binding/causal anchors тоже реализован. Whole-worker capture v2 и
[independent replay v2](PAPER_WORKER_REPLAY_V2.md) реализованы21октября;
повторять их как следующую задачу не нужно. W6a direct SQL provenance реализован;
остаток — W6b mandatory reference/forecast/source linkage,
W7 complete shared polling/paired runner, W8 host capacity/review и W9 study
по gates; см. [текущий чек-лист](#current-checklist). Старый v1/v2 long-study
preflight BLOCKED по вместимости: 1 036 804events > 10 000 даже для одной роли
без fills. Frozen study остаётся
неподтверждённым при missing historical quotes. VP допускает пока только
документацию/read-only подготовку; обучение/стратегии/таймеры не запускались.

Ниже сохранены исторические этапы и датированный журнал. При конфликте старой
«следующей задачи» с текущей сводкой использовать [сводку22октября](#current-checklist);
завершённые исследования и механизмы не запускать заново только из-за старого `[ ]`.

## Сверка реализации 14 октября: приоритеты и границы

Полная [сверка и checklist R1–R16](IMPLEMENTATION_RECONCILIATION_20261014.md)
дополняет этот исследовательский план. Новый запуск non-integration:
**1057 passed, 1 deselected**. Локальный executor установлен с `--live`;
его switch/risk/outage wiring требует R1–R5. Не считать исходный Freqtrade
pilot validator защитой другого executor. Код и сервисы этой сверкой не менялись.

- [x] Найден существующий `edge-complete-trade-label-audit-20261014.json`:
  20 полных counterfactual source labels. Проверены saved input/runtime SHA.
- [ ] Human review этих cases, actual strategy entry, historical rules/fees,
  gaps/noncloseout coverage: receipt явно не сертифицирует эти результаты.
- [ ] Следующая реализация: R1–R5, затем R6–R11; independent/paper R12–R16
  остаются обязательными. Ни completed losses, ни price endpoints не дают допуска.
- [x] R5 local state: убрать silent daily-loss reset при missing/corrupt JSON,
  проверить finite/nonnegative baseline, aware UTC day, atomic rollover и lock
  contention. Valid legacy baseline сохраняется; повреждённый state блокирует вход.
- [x] R5 local baseline transfer: reviewed source/backup SHA, same-UTC-day validation,
  explicit asserted account scope, private atomic no-overwrite restore и общий
  daily gate lock. Отдельный CLI process drill сохраняет original bytes и loss blocker;
  [runbook](DAILY_RISK_RECOVERY.md), actual-account/host migration не квалифицированы.
- [ ] R5 operational recovery/host transfer и R1–R4 runtime wiring: отдельные
  проверки ещё нужны; локальные тесты не подтверждают действующее исполнение.
- [x] R4 local exit-data fallback: отдельный opt-in launcher path, public closed
  candles validation, запрет buys при fallback, fake-client stop/exit regression,
  отказ при invalid резервных данных и запрет повторять order-capable call.
- [ ] R4 rollout/full outage: installed service пока без нового флага;
  startup/decision persistence при Supabase outage и полное recovery не проверены.
- [x] R4 launcher startup outage: исключение NightResearchSelector больше не
  завершает цикл до held-position branch; fallback pairs + explicit Buy blocker.
  Full fake-client run_cycle проверяет remote outage→public stop→one sell→
  durable journals, repeat без resend и соблюдение kill/no-entry switches.
- [x] Runtime diagnostic snapshot: atomic private запись после формирования
  outbox/control/reconciliation blockers, configured protection flags отдельно
  от qualification; diagnostic write failure блокирует Buy, не прерывает exits.
- [ ] R4 operational qualification: реальные outages/restarts, потеря private
  balance/inventory, exchange UID/multi-host, модель/quote/source failures и
  deployment/admission ещё открыты; fake-client cycle не live smoke.
- [x] R4 account-wide outage wiring: unknown balances/inventory/capacity не
  обрывают known-pair exit checks; Buy blocker+zero entry slots, nullable
  diagnostic fields, без daily/peak reset. Per-symbol quantity остаётся обязательной.
- [ ] R4 actual account qualification: обнаружение неизвестных outside-universe
  holdings при полном inventory outage не гарантировано; private quantity/
  price/order APIs и full outage recovery остаются обязательными.
- [x] R4 recovered-inventory wiring: exact validated sizing rows добавляют
  material holdings в текущий exit cycle после initial discovery failure;
  без третьего wallet query и duplicate attempts. Evaluation pairs отражены в snapshot.
- [x] R4 local decision persistence: durable SQLite outbox, сохранение original
  decision payload до remote delivery, replay только idempotent records,
  restart/recovery и single fake exit при remote outage проверены.
- [ ] R4/R15 operational rollout: новый `--decision-outbox` ещё не включён
  в installed service; pre-submit/crash uncertainty и startup outage остаются открытыми.
- [x] R4/R15 local pre-submit journal: intent commit перед market submit,
  no-resubmit при prepared/unknown, cached acknowledged response, exact-link
  positive reconciliation и отсутствие inference из пустой history проверены.
- [ ] Проверить account/host ownership, журнал на реальном crash/restart,
  reconciliation retention/pagination и operator recovery; installed service
  пока без `--order-submission-journal`, operational gate остаётся открытым.
- [x] R1 local ownership: immutable credential fingerprint/endpoint/host/path
  binding и общий local process lock для credential; отказ при смене пути,
  ключа/host, missing bound DB и unbound legacy DB. Отдельный process kill/restart
  test проверяет освобождение lease без сброса журналов.
- [x] R1 local cross-key UID ownership: shared UID+endpoint lock и immutable
  owner/journal binding, no legacy adoption/reset, raw submit lease check,
  actual process kill/restart и full fake launcher checks. Исходная UID binding
  не заменяет fresh entry permissions; [runbook](EXECUTOR_ACCOUNT_OWNERSHIP.md).
- [x] R1/R15 local reviewed journal migration: отдельный prepare/reviewed-SHA/apply
  для прежнего credential-bound журнала; DB bytes/inode, unknown/ACK reserves
  и credential records сохраняются. Независимый backup, exact partial resume,
  reserved path/link guards и отдельный fake CLI process drill проверены;
  [runbook](EXECUTOR_UID_MIGRATION.md).
- [ ] R1/R15 operational migration: production legacy journal, key/IP/host
  transfer, endpoint aliases и multi-host fencing ещё не квалифицированы.
- [x] R1 local canonical endpoint: UID guard/migration отвергают alternate origins
  до API/bootstrap; retained legacy alias registry запрещает новый namespace.
  Active endpoint drift блокирует отправку; разные UID сохраняют общий lockdir.
- [ ] Подтвердить реальный exchange account UID и multi-host single ownership;
  fingerprint API-key не заменяет UID и не объединяет разные ключи одного счёта.
- [x] R2 local operator switches: opt-in execution-controls JSON, строгие bool/
  version/duplicate-field guards, reread перед market/limit submit; no-new-entry
  сохраняет sells, kill блокирует новые Buy/Sell. Known local rejection
  записывается как blocked, не unknown; fake-executor stop/toggle checks passed.
- [x] R1/R2 local runtime-bound approval: exact code/config/credential/host/path
  fingerprint + pinned model SHA + expiring explicit operator approval before
  Market Buy, после risk queries и внутри journal. Full fake launcher Buy,
  mid-query revocation/status=blocked и existing stop Sell проверены;
  [runbook](EXECUTOR_RUNTIME_APPROVAL.md). Full admission/rollout ещё открыты.
- [x] R1/R2 local account evidence: authenticated query-api UID/subaccount/
  Spot-only permissions/exact IP matching перед Buy, original server freshness,
  runtime-bound explicit policy, safe diagnostic projection. Full fake cycle
  проверяет permission change после startup и сохранение stop Sell;
  [runbook](EXECUTOR_ACCOUNT_VERIFICATION.md). Actual scope/ownership открыт.
- [x] R2/R14 local paper evidence audit: original protocol/candidate/policy
  registrations, exact artifact pin, три role DB exports, model decisions/
  intents/fills и acceptance пересчитываются read-only. Sealed gate не читает
  rewards; cash/flat/dust marks сверяются с fills; [runbook](STRATEGY_EVIDENCE_AUDIT.md).
- [ ] Исторические liquidation marks без исходных quotes не квалифицированы:
  conditional economic pass не становится `paper_evidence_pass` при таком gap.
  Independent стратегия, будущие окна и actual live admission остаются открытыми.
- [ ] R2 admission/runtime rollout: полный admission contract ещё не подключён,
  installed service без execution-controls; operational kill/cancel/recovery
  и взаимодействие с R1/R3–R5 ещё требуют проверки.
- [x] R3 local submit-time checks: opt-in guard повторно проверяет market Buy
  quote stake, finite balance/inventory, current position capacity и absolute
  daily-equity loss непосредственно перед send; Sell не зависит от entry data.
- [ ] R3 full hard-risk policy: percent notional/risk-per-trade, persistent peak
  drawdown, reserved/available funds и outstanding orders не квалифицированы;
  installed service без submission-risk-guard, defaults не менялись.
- [x] R3 reservation mechanism: opt-in non-borrowed USDT cash bounds и complete
  open Spot order pagination; locked/bonus исключаются, pending Buy symbols
  занимают capacity, unknown/missing/cursor failures блокируют вход. Local tests passed.
- [ ] R3 live reservation qualification: latency/snapshot consistency,
  cross-product collateral и полный lifecycle settlement ещё не закрыты;
  implemented durable reserve не подтверждает полную buying power.
- [x] R3 local durable reservations: ACK/prepared/unknown/observed Buy сохраняют
  quote/position reserve после restart, текущий intent исключён из собственного
  резерва; empty remote history не освобождает средства. Zero-fill terminal
  reconciliation с exact acknowledged order ID допускает release.
- [ ] R3 full lifecycle settlement: partial/multi-lot buys после source-qualified
  accounting/closeout ещё не квалифицированы; conservative local reserves могут
  дублировать удалённый locked bound. Operational reservation gate открыт.
- [x] R3 narrow closed-cycle settlement: exact linked terminal orders/full fill
  totals/base-or-quote fees/chronology/zero final inventory, original source
  receipt и durable released_closed; partial/unknown/multi-buy cases не освобождаются.
- [ ] R3 settlement qualification: actual-account source validation, partial/dust/
  multiple-lot FIFO, third-token fees, full retention и snapshot latency ещё
  открыты. Narrow local tests не означают выполненный operational rollout.
- [x] R3 terminal partial settlement: Spot PartiallyFilledCanceled с positive
  complete fill totals, request quote/base bounds и несколькими closing sales
  проверен; proof-v2 хранит terminal statuses. Открытый partial и partial-status
  с нулевыми исполнениями не освобождают резерв автоматически.
- [ ] R3 remaining settlement: real-account partial/dust qualification, несколько
  покупок одного symbol/FIFO, third-token fees и operational rollout остаются открытыми.
- [x] R3 local multi-buy FIFO settlement: полный закрытый cohort по symbol,
  base-fee quantities, хронологические lots/allocations и запрет reuse execIDs;
  release всех Buy atomic, failed second update rolls back whole cohort.
- [ ] R3 cohort qualification: реальные multi-buy/dust/third-token sources,
  timestamp ambiguity и global account coverage ещё не квалифицированы;
  entry policy одного symbol не расширялась, service без opt-in rollout.
- [x] R3 observed drawdown mechanism: persistent peak/UTC observation/latch,
  owner/threshold binding, atomic updates/nonblocking lock, missing/corrupt
  state блокирует Buy без reset. Startup и submit checks, Sell bypass проверены.
- [ ] R3 drawdown qualification: реальный reviewed initial peak, continuous
  equity marks, external cashflow adjustments и operational recovery ещё не
  проверены. Threshold explicit/opt-in; installed service не менялся.
- [x] R3 fractional entry mechanism: explicit position-equity/planned-stop-risk
  fractions, existing symbol dust included, explicit roundtrip cost input,
  quote Buy checks before submit; boundary/invalid/current-equity tests passed.
- [ ] R3 fractional qualification: actual cost/gap/stop execution, aggregate
  portfolio stop risk, admission/runtime policy review ещё открыты. Механизм
  не подменяет полный HardRiskConfig admission и не меняет installed defaults.

- [x] R2/R14 local prospective valuation: отдельный новый namespace/protocol,
  raw market sources и causal event chain; независимый cash/FIFO/liquidation
  replay, same-clock fills, sealed read-only CLI и no-retry после incomplete
  completion. Совместимость с прежним worker проверена на synthetic inputs;
  [runbook](PAPER_VALUATION_CAPTURE.md). Frozen producers/studies не менялись.
- [ ] R2/R14 forward qualification: новая трёхролевая preregistration, lifecycle/
  termination/max-gap/ресурсные границы, actual prospective sources, economic
  acceptance и independent review ещё нужны. Full entry admission не подключён.

- [x] R2/R14 local lifecycle v2: typed frozen contract, capacity preflight,
  measured capture resource guards, Buy cutoff/Sell continuation и durable
  terminal. Exact time coverage с source expiry и completion clocks проверена.
- [x] R2/R14 standalone segmented storage: bounded files, global chain/budget,
  rotation, durable pending recovery, exact retries и read-only streaming
  structural verifier; [runbook](EVIDENCE_SEGMENTS.md). Это отдельный компонент.
- [x] R2/R14 capture v3 adapter: новый protocol/registration/role, segmented
  prepared/complete/terminal, native row hashes, sealed source/operation audit.
  Full FIFO/coverage/strategy admission этим не выдаётся.
- [x] R2/R14 отдельный native source-store: bounded indexed shards, durable
  archive/atomic cleanup/checkpoint, original IDs и archive-aware wallet/worker.
  Source integrity не является causal capture/economic admission.
- [x] R2/R14 capture v4: новый protocol/registration, все доступные wallet mutations,
  original row deltas, archive/checkpoint linkage и sealed read-only CLI;
  [runbook](PAPER_CAPTURE_V4.md). Это source trace, не полная экономическая проверка.
- [x] R2/R14 bounded streaming wallet replay: pre-start replay contract, hard scratch
  page/row budgets, independent cash/fees/FIFO/valuation/coverage;
  [runbook](PAPER_STREAMING_REPLAY.md). Full strategy/economic admission не выдаётся.
- [x] R2/R14 worker source capture: prospective tick/batch/clock/monotonic/provider
  и atomic wallet/worker action journal, negative-status/source linkage, unknown-tick
  restart guards и sealed read-only CLI; [runbook](PAPER_WORKER_CAPTURE.md).
  Source trace не подтверждает полноту upstream polling или worker economics.
- [x] R2/R14 independent delivered-worker replay: отдельный pre-start local backend
  contract, controller clocks/decisions/exits/report и wallet/FIFO/coverage нового schema;
  [runbook](PAPER_WORKER_REPLAY.md). Production PostgreSQL при replay не читается.
- [ ] R2/R14 long-study: qualified producer, provenance/полнота local polling,
  paired runner/три роли и actual resource/host qualification. V1/v2 всё ещё
  ограничены10 000events/64MiB source DB; min30days/poll5s требует1 036 804events.

## Текущий статус и порядок продолжения

**Квалифицированного прибыльного кандидата нет.** Рабочая модель в ходе исследований не заменялась. Реальные доходы не выводятся из accuracy, свечных прогнозов или сохранения cash без сделок.

Подтверждённо выполнено:

- [x] Архив, причинная разметка, общий портфельный simulator, учёт расходов и общий buy/sell/price-time core; полная квалификация исполнения ещё впереди.
- [x] Registered train-window comparison: 4 варианта; source/input/runtime snapshots, immutable ledger и numerical audit.
- [x] Registered ablation: 7 удалений признаков и 7 portfolio comparisons. Улучшение RMSE без volume_ratio не дало сделок или прибыли.
- [x] Registered class-balance comparison: 2 варианта. Balanced дал36сделок и убыток; unweighted не торговал.
- [x] Economic screen13completed portfolio configurations: 0passes, отдельные причины отказа, подключение к readonly feedback.
- [x] Версии целей и запрет смешивать price/net/cash в primary registry; новые primary artifacts явно объявляют price target.
- [x] Bounded120 streaming parity:2556feature vectors/2562signals на BTC/ETH совпали с batch; full live execution parity не доказана.
- [x] Main training/feedback timers при последней проверке enabled. Ablation retry timer выключен после завершения задания7/7.

Оставшаяся работа — в следующем порядке:

1. **Сверка и миграция основной модели.**
   - [x] Устранить conflicting original entry contexts в обоихlearningcollectors иповторитьactualcollection/preflight14октября04:47UTC:healthy,0eligibleclosedrows;legacy8 не backfilled.
   - [x] Выполнить actual cashfit preflight14октября:sourcehealthy,0eligibleclosed-contractrows,8incompatibleinputs;originalsnapshots/runtime иcalendarfailures сохранены. Fitready=false.
   - [x] Проверить candidatea252b48b49 14октября:exact originalinput/metric/source auditpassed,train5180/validation1060/test1140,localartifact совпал сregistry.
   - [x] Сверитьactualregistry14октября:active09b486e979legacy/unknown unchanged,candidatea252;storedpromotionreplay420unseen/3signals deniedinsufficient_signals иincompatiblefeaturecontract. Verifiedcandidate не означает разрешённуюпубликацию.
   - [x] Подготовить отдельный наблюдаемый протокол closed bounded120 с замороженным candidate и baseline без ML; неизвестный legacy контракт не реконструируется. Протокол v3 и prospective collector проверены; это подготовка миграции, не её квалификация.
   - [x] Реализовать и проверить сбор prospective candidate/baseline price comparison на одинаковых bounded120 данных; таймер активен, первые2price endpoints записаны12октября06:26UTC.
   - [ ] Накопить достаточную независимую выборку и выполнить candidate/control execution comparison; price endpoints не являются cash income или completed paper trades.
   - [ ] Критерий закрытия: воспроизводимый совместимый контракт и независимые доказательства допуска; изменение имени/metadata или ручное снятие no_fresh_model не считается решением.
2. **Квалификация источников и исполнения.**
   - [x] Проверить полные virtual trade labels для20 заранее выбранных сложных source cases:20 stop exits,19 ambiguous, independent arithmetic/risk replay passed. Сценарные фильтры не сертифицируют историческое исполнение или стратегию.
   - [x] Найтиactualambiguoussourcegeometry вгодовомархиве и сверитьfirst20original1m sources:2102400rows/56cases,20matches,17ordered/3stillambiguous. Geometry неactualstrategyfill;manualcomplete-tradelabelqualification отдельно открыта.
   - [x] Независимо проверить полный FIFOorder иqty/basis conservation source-cache14октября:49closed+33remainingrecords,14openlots,unmatched0;originalinputreplaypassed. Historicalexecution иindependentprofitqualification отдельно открыты.
   - [x] Независимо сверить20real-source FIFO allocations14октября:base-buy/quote-sellfees,basis/net иpartialallocationspassed. Полная FIFO/historicalfilter/manualedgecase квалификация этим не закрывается.
   - [x] Проверить actual source-health freshness regularfeedback14октября04:28UTC:journalage≈8s,accountingverifiedtrue;unknown/stale/futurehealth regressionguardspassed. Это текущая sourcequality,не independentprofitability.
   - [x] Проверить actual regular feedback послеexplicit-walletfix14октября04:20UTC:23coins,inventoryconsistent/accountingqualitytrue; сохранить originalserviceoutput. Отдельно ATR causalinputaudit198plans completed.
   - [x] Подтвердить standalone actual explicit-wallet reconciliation14октября04:08UTC:23coins,0missing,consistent=true,source replay passed. Regular feedback status и completeness historical cache отдельно не подтверждены.
   - [x] Подключить explicit tracked-coin wallet request к feedback и строгую numeric/accounting проверку fee calibration; synthetic tests выполнены. Actual explicit-wallet reconciliation и fresh-health feedback 14 октября проверены в отдельных receipts; future service runs проверять заново.
   - [x] Исключить conflicting exact-order decisions из strategy attribution; duplicate/order-independence regression tests и actual cache feedback replay42exit groups выполнены14октября. Исходные decision contexts отсутствуют: causal attribution остаётся открытой.
   - [x] Выполнить source-bound loss review реального cached FIFO14октября:49closed segments,28losses,16≤−1%,6fee-equivalent-erased; сохранить20recent cases и original input/runtime. Fresh exchange sync и strategy attribution не подтверждены.
   - [x] Повторно проверить global coverage source-bound replay40cases14октября: unique groups/pairs/times и exact counts;34timeout/6stop, actual original windows/runtime verified. Manual/historical execution qualification этим не закрывается.
   - [x] Установить отдельное source-bound задание сверки6stop cases: immutable job/input/runtime, retry20min, stop-on-completion/blocked; original job был deferred из-за RAM guard; отдельная user-authorized 1024MiB версия завершила 6/6 numerical cases 14 октября. Original freeze не переписан.
   - [x] Загрузить bounded original1m sources для всех6sampled stops:30closed candles,complete6/6,no gaps. Actual separate1024MiB-profile numerical audit14октября завершён:6/6source matches,6ordered stop touches,0more-adverse fine exits;real-fill qualification остаётся открытой.
   - [x] Реализовать и установить fixed long archive audit retry: original dataset/source/runtime freeze,1536MiB/2048MiB guards,15minute cadence иstop-on-completion/source-failure. Actual full long report получен14октября в новом1024MiBjob:18143candles/pair,40sample source replayspassed; historicalexecution qualification открыта.
   - [x] Выполнить strict archive numerical/source audit BTC/ETH:20samples/pair с оригинальными окнами; в этом срезе только timeout cases. Это не закрывает20manual/source cases с gaps/ambiguity/noncloseout.
   - [x] Проверить identity/time/coverage оригинальных instrument receipts и реализовать observed account fee source capture/replay. Actual APT/NEAR maker0.001/taker0.0018 подтверждены13октября по ответу текущего аккаунта; прошлые fees/fee assets не восстановлены.
   - [x] Сохранить13октября наблюдаемый снимок527Spot instrument rules и полные оригинальные instrument/orderbook responses APT/NEAR; проверить воспроизведение нормализации из saved inputs/runtime. Это observed snapshots, не historical execution qualification.
   - [ ] Дополнить point-in-time universe, instrument minimums/steps/ticks, комиссии/fee assets, spread/depth и источники partial fills; unknown оставить unknown.
   - [x] Проверить локальные FIFO partial/base-fee/quote-fee случаи, conflict/duplicate execution guards, basis и fresh explicit-wallet reconciliation23coins.
   - [ ] Завершить историческую/backtest/paper квалификацию exit minimums, округлений, partial fills и non-quote fee assets; third-token fee без source conversion остаётся unknown.
   - [ ] Закончить минимум20ручных проверок меток с реальными source references, включая gaps, ambiguous stop/target, комиссии и неполное закрытие.
   - [ ] Критерий закрытия: source-bound cases и объяснённые различия backtest/paper, без невозможных fills и удвоения fees.
3. **Зарегистрированные исследования стратегии и обучения.**
   - [x] Завершить actual complete fixed/ATR extension grid14октября:4/4 verified, все ordinary/stress net negative;noadmission. Уменьшение убытка относительно baseline не является прибылью.
   - [x] Реализовать и отдельно зарегистрировать fixed-stake buy-and-hold context ordinary/stress: same capital/stake/data slice, explicit different stop/target risk; reserve1context andretain original extension manifest. Actual1/1 context completed14октября:ordinary+0.541497649134780USDT/stress+0.504513888199200USDT; development context,не admission.
   - [x] Реализовать и зарегистрировать complete four-config extension study: support_bounce/compression_breakout ×fixed/ATR, risk-matched baseline безML, cash-only иpaired wallet diagnostics.Новая source/resource version completed4/4 14октября:все4negativeaftercosts,profitableadmission0; execution controls не являютсяML фильтром.
   - [x] Реализовать и выполнить bounded exploratory prospective calibration на642price endpoints: train-prevalence baseline заморожен в original artifact, Brier/log loss и fixed bins по pair/UTCday, original input/runtime snapshots. Это descriptive diagnostics, не registered parameter selection и не income.
   - [x] Подбор validation threshold исключает ordinary/stress unclosed inventory, exit-minimum violations и отсутствие этих execution summaries; verified immutable reports не получают отсутствующие поля задним числом.
   - [ ] Сравнить реальную baseline strategy без ML, frozen current-model control, новые heads и cash-only при одном капитале/риске; добавить buy-and-hold только как явно заданный контекст.
   - [x] Выполнить declared fixed/ATR extension study после source/protocol freeze и budget reservation:4/4completed,formal screen0/4passes. Просмотренный период остаётсяdevelopment.
   - [ ] Зарегистрировать и проверить дополнительные filters/newheads с current-model control; готовые отрицательные результаты не переименовывать в independenttest.
   - [ ] Подбирать threshold по validation portfolio payoff, activity и ordinary/stress risk, используя complete preregistered grid и проверенные immutable reports.
   - [ ] Проверить calibration на естественном распределении и более длинных/разных окнах; features удалять только после устойчивого эффекта, не по одному RMSE.
   - [ ] Критерий закрытия: положительные результаты после расходов/stress, достаточные trades/days/pairs и преимущество над control; no-trade не является заработком.
4. **Независимая оценка процедуры целиком.**
   - [x] Зарегистрировать validation-only grid/policy для6 folds:2 class-balance heads ×3 thresholds,12 studies/36 current reserved trials,original target/source/runtime; actual fits0. Failed original typo declaration retained; family budget72/100.
   - [x] Реализовать и выполнить source/data binding и train/validation pipeline первого fold15октября:2head fits на68516train examples,6verified trials,0eligible кандидатов. Test не оценивался.
   - [ ] Завершить full independent test runner и дальнейшие folds; actual cash-only selection первого fold выполнен16октября, но не заменяет независимую оценку.
   - [x] Реализовать отдельный cash-abstention freeze без фиктивной обученной модели: повторная проверка обеих complete grids/ledger/SHA, purged cutoff, actual clock, неизменяемая атомарная запись. Actual freeze16октября04:41:22UTC выполнен внутри разрешённого окна.
   - [x] Выполнить observed cash selection первого fold: receipt SHA e0d96b93c5925e840944689474f9fd24e93ce7842d040ec4252736dc8220cc98, policy no_candidate_cash_only; оба head/6trials повторно проверены, test rewards не читались.
   - [x] Подготовить prospective virtual cash-reference job16октября04:42:52UTC: code/runtime/input snapshots, clock gate, early evaluation rejected без создания результата. Это только idle-cash component, не full independent runner.
   - [ ] Дождаться test_end15ноября00:00UTC и выполнить cash component; отдельно завершить native/current-model controls и независимую оценку процедуры. Нулевой cash income не доказывает прибыльность стратегии.
   - [x] Проверить календарные guards для manually constructed folds, immutable selection recovery и все declared information cutoffs;18focused tests passed. Это проверка механизма, не завершённая независимая оценка.
   - [x] Зафиксировать отдельный календарь offline walk-forward:6 окон train120/validation30/test30,embargo1day,reviewed cutoff;futuretests16Oct2026–14Apr2027. Calendar freeze не preregistration всей процедуры.
   - [ ] До eligible test outcomes зафиксировать полную процедуру выбора и target/execution contracts для независимой оценки; календарь не заменяет source/model qualification.
   - [ ] Оценить всю процедуру поиска с train-only preprocessing, неперекрывающимися test windows и временным block bootstrap общего wallet.
   - [ ] Проверить требуемые окна/число сделок, PF/DD/stress/concentration и бюджет перебора по соответствующему frozen protocol; при нехватке данных продлить наблюдение.
   - [ ] Критерий закрытия: independent evidence; future windows невозможно заменить ретроспективными данными или просто отметкой в checklist.
5. **Forward paper и допуск.**
   - [x] Реализовать independent Decimal replay записанных paper fills/FIFO segments и включить его в export/source manifest; проверить цену, qty/fees/basis, доступность quote/filter и сохранение остатка. Actual future-period replay ещё не выполнен.
   - [x] Проверить согласованность retained/full mark quality summaries: integer counts, known coverage, finite drawdown/gaps и нижние границы по видимым marks. Synthetic tests проверяют механизм; длительное paper evidence остаётся открытым.
   - [ ] Создать новую execution source/policy version: старые source-bound fingerprints нельзя обновлять задним числом после изменений kernels/producer.
   - [ ] Выполнить preflight, source/clock/quantity/fee accounting checks; вести candidate/control wallets на одном потоке, записывать fills/rejections/exits/net equity.
   - [ ] Завершить сроки и число завершённых paper trades по конкретному протоколу. Общие30дней/100trades и closed cash study14дней/60trades — разные требования, их не смешивать.
   - [ ] Сверить replay того же future периода с paper и объяснить существенные расхождения.
   - [ ] Критерий закрытия: все admission checks пройдены, rollback/monitoring проверены и результат готов к отдельному review решения о live замене.

Для каждого оставшегося пункта сохранять: source/config/data SHA, protocol/study ID, observed timestamps, параметры/seed/runtime, команды проверок, фактические результаты, основания допуска/отказа. `[x]` означает выполненную проверку, а не написанный код, намерение, deferred status или прошедший synthetic test.

Промпт продолжения: [CONTINUE_TRAINING_RESEARCH_PROMPT.md](CONTINUE_TRAINING_RESEARCH_PROMPT.md).

Цель: построить воспроизводимый цикл «архив → гипотеза → симуляция сделки → обучение → проверка на новых периодах → бумажная торговля». Результат цикла — доказательства пригодности кандидата либо обоснованный отказ. Рост прибыли после каждого обучения не является критерием, который можно гарантировать.

Этот документ — план будущей реализации. Отмеченные пункты выполнены ранее; остальные требуют работы. Создание плана не запускает обучение, не публикует модель и не изменяет торговлю.

## 1. Состояние на начало

Этот раздел фиксирует исходный checklist 7 октября. Текущие выполненные работы и открытые критерии перечислены в разделе «Текущий статус и порядок продолжения» выше; исходные отметки не используются для определения готовности сейчас.

- [x] Загрузка Bybit Spot истории по страницам, сохранение и повторное использование локального архива: `src/cryptoforge/archive.py`, `scripts/download_market_archive.py`.
- [x] BTC/USDT и ETH/USDT: по 25 919 закрытых 5m свечей, всего 51 838; в manifest нет пропусков за запрошенные 90 дней.
- [x] Отдельное архивное обучение: `scripts/train_archive_model.py`; оно не публикует `model.active`.
- [x] Хронологические выборки с исключением меток, пересекающих границы.
- [x] Подбор L2 для long-модели на validation; test не выбирает L2.
- [x] Ограниченный поиск 18 вариантов трёх семейств в `strategy_search.py`.
- [x] Защита от безусловной публикации каждой новой модели.
- [x] В чате «Проверить работу обучающегося бота» добавлен short-shadow анализ через 3/6/12 свечей: `src/cryptoforge/short_shadow.py`, `scripts/evaluate_short_shadow.py`.
- [x] В `da16f15` добавлены gross/net результаты с предполагаемыми round-trip расходами 0,3%, net win rate, исключение незакрытых свечей и отдельный учёт пропусков.
- [x] Таймер `cryptoforge-short-shadow-outcomes.timer` активен; последний сервисный запуск `Result=success`, `ExecMainStatus=0` при сверке этого плана.
- [x] В другом чате последний полный запуск сообщил 269 прошедших тестов. В этом ходе составления плана полный набор повторно не запускался; это историческая отметка.
- [ ] Симулятор стопов, целей и общего портфеля с реалистичным исполнением.
- [ ] Метки, основанные на результате сделки, вместо изменения close через фиксированное время.
- [ ] Исторический состав торгового universe, более длинная история и дополнительные монеты.
- [ ] Последовательные проверки walk-forward и отдельный закрытый финальный период.
- [ ] Статистическая оценка устойчивости и учёт количества перебранных вариантов.
- [ ] Проверка кандидатов на будущих бумажных сделках.

Уже просмотренные тестовые периоды BTC/ETH нельзя объявлять нетронутым финальным тестом. Они доступны для разработки и предварительных проверок. Для окончательной оценки выделить ещё не анализировавшийся период или дождаться будущих данных.

### Сверка с другим чатом

Источник: [Проверить работу обучающегося бота](codex://threads/01a0edf9-6e74-7e90-a383-94e8e67720b1), последние завершённые сообщения; изменения дополнительно сверены с локальными файлами и Git.

Уже сделанные архив, short-shadow журнал, учёт предполагаемых расходов, проверку пропусков и таймер не реализовывать повторно. Следующие задачи этой ветки: сравнение net-результатов с baseline по разным дням/монетам, validation-подбор short-признаков и порогов, независимый test и forward paper. Это исследование виртуальных падений; оно не подтверждает прибыльность доступной Spot-long торговли и не учитывает заём/funding.

При исходной сверке обнаружен обход cutoff через `same_label_config`. В продолжении этапа 0 условие удалено; добавлено исключение всех известных train/validation/evaluation границ, а для старых артефактов — консервативная дата публикации. Регрессионные тесты добавлены. Полный этап 0 ещё требует фиксации dataset/runtime/resource параметров.

## 2. Правила выполнения

- Выполнять этапы по порядку. Следующий этап начинается после прохождения критериев предыдущего.
- В каждом этапе сохранить результат, конфигурацию, команды проверок и причину решения в журнале выполнения в конце документа.
- Первые эксперименты — Bybit Spot, только покупки за имеющийся капитал. Short-исследования отдельно, без смешивания с доходностью Spot.
- Сохранить текущие лимиты риска, размер позиции и правила выхода. Исследование не повышает их автоматически.
- Не подбирать параметры по test или paper-результатам и затем выдавать тот же период за независимую проверку.
- Любое исследование может завершиться «пригодного кандидата нет». Не снижать критерии ради обязательного победителя.
- До подключения новых библиотек оценить CPU, RAM, время и совместимость. Не обучать тяжёлые модели на торговом узле без проверки ресурсов.
- Численные пороги ниже — стартовые проектные предложения, а не универсальные нормы. Зафиксировать их до запуска поиска; изменение требует новой версии протокола и новых независимых данных.

## 3. Этап 0 — зафиксировать протокол и проверить текущую реализацию

VP: NEW protocol/source freeze — [VP-00/01](#cf-vp-2026-10-17---video-derived-strategy-research); прежние frozen studies не изменять.

**Статус: завершён для offline development.** Сбор новых архивов относится к этапу 1. Запуск тяжёлых исследований пока запрещается ресурсным gate; это не повод обходить его.

### Работы

- [x] Создать черновик `config/research-protocol-v1.json` с окнами, бюджетом поиска и предполагаемыми издержками; пока он не подключён к runner.
- [x] Создать versioned research-конфигурацию с universe, датами, таймфреймами, издержками, бюджетом поиска, капиталом и критериями допуска.
- [x] Сохранить снимок активной модели, checksum, версии признаков и фактических параметров исполнителя, не выводя секреты.
- [x] Проверить расхождения документации с systemd/runtime; например, описанный `shadow` не считать фактическим режимом без проверки.
- [x] Записать все ранее просмотренные периоды и использованные конфигурации.
- [x] Добавить в модель `fit_information_end`: последнюю дату данных, повлиявших на обучение, нормализацию, подбор L2, порога и стратегии.
- [x] Сравнивать кандидата с действующей моделью только после конца данных, использованных обеими при подборе. Одного `training_label_end` недостаточно, если L2 выбирался на validation.
- [x] Запретить обход этой границы при изменении целевой метки, параметров или семейства модели.
- [x] Проверить совместимость горизонта, целей, признаков и порога между архивным обучением и исполнителем.

### Проверки

- [x] Изменение целевой метки не делает старые обучающие данные «новыми».
- [x] Кандидат не становится основной моделью при недостатке независимых наблюдений или ошибке реестра.
- [x] Изменение будущих свечей не меняет уже рассчитанные прошлые признаки и сигналы.
- [x] Сбой исследовательского процесса не блокирует управление открытыми позициями.

**Готовность:** конфигурация и границы использования данных однозначны; защита покрыта тестами. Артефакт: `research-protocol-v1` и снимок исходного состояния.

## 4. Этап 1 — расширить и проверить архив

VP: REUSE archive/closed contracts, EXTEND point-in-time rules и closed1D coverage — [VP-01](#cf-vp-2026-10-17---video-derived-strategy-research). Unknown остаётся unknown.

**Статус: частично выполнен; механизм этапа 2 уже реализован. Qualified historical execution не закрыта; разрешены ограниченные development-проверки с явно описанными unknown, но не independent/live admission.** Годовой архив исторически выбранных 20 пар, формат и качество готовы. Полный исторический состав биржи и прежние instrument rules остаются открытыми; доступность внутри фиксированной корзины записана отдельно.

### Работы

- [x] Начать с 10–20 ликвидных Spot USDT монет, затем расширять только при достаточной истории и качестве данных.
- [x] Цель покрытия — 12–24 месяца, насколько позволяет история листинга и источник; для короткой истории явно уменьшить доступное число проверочных окон. Для исторически выбранных 20 пар получены и проверены полные 12 месяцев; 24 месяца не заявляются.
- [x] Хранить 5m как основную историю; получать 15m/1h напрямую либо агрегировать закрытые 5m свечи по строгим UTC-границам.
- [x] Поддержка 1m реализована и проверена на 6 sampled stops и 20 ambiguous source geometries. Для 3 геометрий порядок внутри одной минуты остаётся unknown; adverse stop сохранён.
- [ ] Сохранять историю доступности символов: листинг, делистинг, минимальная стоимость заказа, шаг цены/количества и известные изменения правил.
- [x] Сформировать machine-readable coverage audit по исторической корзине: численные значения отделены от полного подтверждения правил, known suspension блокирует доступность после observation time, unannounced dynamic limits отмечены как coverage gaps.
- [x] Добавить проверяемый частичный реестр официальных событий с source SHA-256, effective/announced timestamps и границами знания. Текущий реестр: 1617 фактов из 112 источников, включая исходные minimum-order значения для 527 USDT пар; полнота истории, quantity steps и максимальные market quantities не подтверждены.
- [x] Обработать 140 источников-кандидатов: проверить captured HTML, publication metadata, наличие текста и первичную market/venue классификацию; factual event review остальных источников остаётся открытым.
- [x] Дополнить linkmap официальными категориями; пройти их пагинацию до начала study period и получить публикации во всех 12 месяцах. Это не доказательство полноты событий или исторических версий страниц.
- [x] Сохранить 3650 причинных дневных записей наблюдаемой доступности/ликвидности внутри фиксированной корзины и датированные текущие instrument observations. Исторические правила и отсутствующие/делистнутые монеты не восстановлены.
- [ ] Формировать исторический universe только по данным, доступным в соответствующую дату. Не выбирать монеты по будущей доходности.
- [x] Построить и повторно проверить начальную корзину на 2025-10-01 по датированной официальной таблице и завершённому предыдущему дню: 527 кандидатов, 524 сохранённых ответов, 3 недоступных запроса исключены, 97 допустимых, top20. Полный динамический состав биржи остаётся открытым.
- [x] Если исторические листинги/спреды/правила недоступны, явно указывать ограничение; не заменять их сегодняшними значениями молча.
- [x] Добавить фиксированные `start/end`, отдельные manifest по диапазонам, SHA-256 и dataset ID. Текущий общий manifest повторный запуск перезаписывает.
- [x] Сохранить происхождение, интервал, покрытие, пропуски, дату загрузки и версию преобразований.
- [x] Проверить место на диске и время обработки небольшим пилотом; выбрать формат хранения после измерения. Не загружать весь архив в live Supabase по умолчанию.
- [x] Реализовать дозагрузку, ограничение запросов, backoff и восстановление после прерывания.

### Проверки

- [x] Временные метки уникальны, возрастают, выровнены по интервалу; свечи закрыты.
- [x] Цены положительны; `low <= open/close <= high`; объём и оборот неотрицательны.
- [x] Пропуски перечислены; не создавать искусственные цены и объёмы для маскировки отсутствующих данных.
- [x] Повторная загрузка не создаёт дубликаты; прерванная загрузка возобновляется.
- [x] Выборка OHLCV сверена с ответом Bybit для нескольких дат и символов.
- [x] Агрегация 1m→5m/5m→1h совпадает с эталоном в пределах заранее заданной точности.
- [x] Обучение не переносит горизонт метки через пропуск, отсутствие листинга или разрыв сегмента.

**Готовность:** пригодные диапазоны утверждены в dataset manifest; повреждённые сегменты исключены. Неполное покрытие видно в отчёте, а не трактуется как полная история.

## 5. Этап 2 — единый симулятор сделки и портфеля

VP: REUSE shared-wallet/cost/risk core; EXTEND staged limits/TTL/non-fill/order sequence — [VP-04](#cf-vp-2026-10-17---video-derived-strategy-research).

### Работы

- [x] Общий price/time exit core используется offline open и paper bid paths;stop/target/timeout precedence checked,undeclared paper target disabled.
- [ ] Полная общая entry/exit procedure и квалификация observation/fill differences между backtest и prospective paper.
- [x] Сигнал на закрытии свечи; исполнение не раньше следующего доступного момента с заданной задержкой.
- [x] Offline config отдельно задаёт entry/exit fees,spread scenario,slippage иentry delay. Spread0 сохраняет прежнюю математику;stress scale включаетspread. Historical bid/ask не выдумывается из OHLC.
- [ ] Проверить отдельные cost assumptions на qualified исторических/будущих execution observations.
- [ ] Использовать доступные сведения о фактических комиссиях; неизвестный исторический спред оценивать консервативно и проверять стрессом.
- [x] Поддержать стоп, take-profit, выход по времени; начать с простых правил и добавить trailing только после базовых проверок.
- [ ] Стоп/цель на одной свече: использовать 1m; при неразрешимой неоднозначности применять неблагоприятный исход и фиксировать его.
- [x] При гэпе через стоп учитывать доступную цену исполнения, а не гарантировать цену стопа.
- [ ] Моделировать капитал, резерв средств, общую занятость, ограничения позиции, округление, минимальный ордер и комиссии в разных активах.
- [x] Обрабатывать одновременные сигналы детерминированно, без выбора по будущему результату.
- [x] Не допускать перепродажи одного капитала нескольким монетам; считать портфельную equity, а не сумму независимых доходностей.
- [x] Simulator сохраняет trades/close equity и optional bounded detailed marks:cash,basis,realized PnL,open quantity/liquidation estimates. Available-at=bar close,OHLC drawdown bound явно отмечена.
- [x] Registered BTC/ETH2000 detailed portfolio replay completed;2000close marks/cash-basis identity checked,0errors. Scenario produced122trades/net−2.24362663 from100capital.
- [ ] Qualified historical/independent future execution andmark coverage;completed development replay не доказывает прибыльность.
- [x] Offline simulator ограничивает quantity по предыдущему закрытому bar volume; future entry volume не используется. Paper wallet отдельно проверяет displayed depth.
- [ ] Исторический стакан/partial-fill coverage; до него не заявлять точное моделирование исполнения.

### Обязательные тестовые сценарии

- [x] Только цель; только стоп; выход по времени; стоп и цель одновременно.
- [x] Simulator regression scenarios:gap-down open fill, invalid/gapped history rejection, zero/low prior volume rejection, delayed entry/no_future_bar.
- [ ] Исторические реальные отказы исполнения и независимая проверка их частоты/модели.
- [x] Simulator/paper tests проверяют insufficient cash, deterministic simultaneous signals, position limit/minimum order и paper dust FIFO basis/slot release.
- [ ] Исторические asset-fee/rule revisions и полное исполнение этих сценариев на qualified prospective stream.
- [x] Комиссии не начисляются дважды и не исчезают на отдельных путях выхода.
- [x] Контрольный пример вручную: баланс, комиссия, количество, PnL совпадают с расчётом.
- [x] Повышение издержек при одинаковой последовательности сделок не улучшает результат.
- [x] Повторный запуск с одинаковыми входами даёт идентичный журнал и метрики.

**Готовность:** тестовые сделки проходят; неизвестные особенности исполнения явно ограничивают выводы. Артефакт: версия simulator и эталонный набор сценариев.

## 6. Этап 3 — новые метки и признаки

VP: REUSE causal BTC/regime/multiframe contracts; NEW delayed pivots/trendline/approximate POC — [VP-02/03](#cf-vp-2026-10-17---video-derived-strategy-research), без замены действующей feature schema.

### Метки результата сделки

- [x] Для каждой допустимой точки входа определить цель, стоп и максимальное время удержания по информации на момент входа.
- [x] Реализована разметка тем же offline симулятором: причина/время выхода, net return v2 и отдельные OHLC lower/upper excursion bounds v1. Точная intrabar последовательность не выдумывается; historical execution certification и human review остаются отдельными открытыми проверками.
- [x] Experimental net-profit classifier,expected-net ridge и отдельные OHLC-risk labels реализованы с разными model families/targets; gross future-return target не принимается net heads.
- [ ] Обучить/сопоставить обе net heads и risk objective на qualified data; synthetic tests не подтверждают прибыльность.
- [x] Не считать отказ исполнения прибыльной/убыточной сделкой: отдельный статус.
- [x] Сохранить точный `label_end_time`; пересекающиеся сделки учитывать при разделении выборок и статистике.
- [x] Не выбирать лучшее будущее время выхода для каждой сделки задним числом.
- [x] Реализовать версии price/net/cash целей и compatibility guards; primary registry отвергает net/cash, Spot-long heads отвергают short labels, новые primary artifacts явно emit price target.
- [ ] Завершить фактическую миграцию целей/feature contracts на qualified original sources; переименование metadata не заменяет relabel и независимую проверку.

### Признаки

- [x] Реализованы returns12/36, ATR14/realized volatility12, range position и support/resistance distances в отдельном experimental24 schema; выполнен development context-net fit. Устойчивое улучшение и допуск schema к live ещё не подтверждены.
- [x] Относительный объём, EMA trend и RSI реализованы в candle/context schemas и проверены причинными тестами.
- [x] Experimental observed-turnover-vwap-v1 считает quote-turnover/base-volume window VWAP,с source interval и explicit observation availability; zero-volume/gaps/invalid turnover не заполняются HLC proxy.
- [ ] Point-in-time turnover source coverage и отдельное доказательство пользы VWAP/расширенных признаков.
- [x] Experimental context-v2 содержит выровненный по времени BTC return/volatility и relative return монеты; missing BTC и поздние revisions исключаются либо сохраняют actual availability.
- [x] Отдельный experimental-dual-market-context-v1(29features) содержит ETH return/relative return/volatility и past12-bar own-vs-BTC/ETH return correlations; unknown/undefined cases excluded.
- [ ] Квалификация dual-market признаков на независимых окнах и отдельная регистрация live schema.
- [x] Experimental context regime определяется past EMA gap / ATR с fixed thresholds±1; future segment returns не используются. Это причинный исследовательский признак, не qualified live regime policy.
- [x] Experimental context-v2 содержит циклические UTC hour/weekday features, только по market-close time; future BTC/hour prices не меняют прошлый вектор.
- [ ] Исторический spread/liquidity feature coverage и независимая проверка пользы временных признаков.
- [x] Experimental aggregation использует только complete closed15m/60m buckets и сохраняет actual cache revision availability; late data не backdated. Live feature registration и point-in-time historical certification ещё не выполнены.
- [x] Primary/logistic/net regression normalizers обучаются только на train; validation/test не refit preprocessing. Missing original/context data исключаются, не заполняются будущими значениями.
- [x] Research-only seven-feature ablation masking одинаково применяется на train/inference; validation не refit normalizer и не выполняет automatic feature selection.
- [x] Actual bounded source-bound ablation:7declared removals и7portfolio comparisons выполнены, original evidence/ledger/numerics проверены.
- [ ] Независимо подтвердить benefit ablation, выбрать признаки внутри train/validation без holdout подбора; любой будущий imputation требует отдельной проверки.

### Проверки

- [ ] Ручная проверка не менее 20 размеченных сделок, включая неоднозначные и граничные случаи.
- [x] Замена будущих данных не меняет прошлые признаки, но может менять соответствующие будущие метки.
- [ ] Проверка долей классов, числа сигналов и доступности признаков отдельно по периоду и монете.
- [x] Выполнить bounded BTC/ETH window cohorts и portfolio signal accounting: train/validation class counts по UTC дням и pair сохранены, label availability проверена. Расширенная point-in-time feature/source qualification остаётся открытой.
- [x] Получить train-распределения классов и причин выхода по BTC/ETH и календарным месяцам; расширенная проверка доступности признаков ещё впереди.
- [x] Прогноз «никогда не входить» явно виден как нулевая активность, а не победа по accuracy.
- [ ] Все этапы обработки повторяются при потоковом расчёте так же, как в архиве.

**Готовность:** dataset содержит причинные признаки и проверенные trade-outcome метки; версии и интервалы сохранены.

## 7. Этап 4 — ограниченный поиск стратегий

VP: REUSE support/compression как baseline, NEW CF-VP-01…07 — [VP-03/05](#cf-vp-2026-10-17---video-derived-strategy-research). Прежние результаты 0/4 и бюджеты сохранены.

- [x] Первый ограниченный validation-only проход 18 вариантов выполнен; все отклонены. Финальный test не использован. Общий этап и независимая оценка ещё не завершены.

### Работы

- [x] Trend/breakout/reversion реализованы и проверены ранее;separate support_bounce/compression_breakout kernels и draft hypotheses добавлены без изменения прежнего study.
- [x] Bounded development extension families зарегистрированы до расчёта; complete fixed/ATR grid 4/4 выполнен, economic screen 0/4 passes.
- [ ] Независимый final-period design и admission extension families; completed development не выдавать за independent search.
- [x] Для трёх реализованных development families записаны exact conditions/mechanism/regime/failures в source-bound strategy-hypothesis-catalog-v1.json. Catalog описательный,создан после прежних results; retrospective preregistration=False. Support bounce/compression/ATR extensions отдельно зарегистрированы позднее; development grid завершён 14 октября с 0 economic passes, independent qualification остаётся открытой.
- [x] Реализованы causal past-ATR risk plans с declared multipliers/bounds/hold и optional per-signal portfolio execution. Late/unmatched/missing risk plans отклоняются,static behavior preserved.
- [x] Registered bounded fixed/ATR extension grid выполнен и проверен: 4/4, все net negative.
- [ ] Дополнительный filter grid и независимая оценка; просмотренные development data не выдаются за blind validation.
- [x] Реализованные development families имеют frozen configuration/wall-time/resource budgets и persistent attempt ledger; разные runtime/cost contracts потребляют бюджет. Это не разрешение расширять тот же поиск после просмотренного test.
- [x] Для новых validation-search запусков сохранять успешные, убыточные и ошибочные попытки в immutable SQLite ledger; persistent per-family budget нельзя увеличить в той же версии протокола. Старые отчёты сохранены отдельно, новый ledger не выдаёт их за retrospectively registered attempts.
- [ ] Выбирать параметры только внутри train/validation. Итоговые test-периоды не ранжируют варианты.
- [ ] Проверять соседние значения параметров: узкий единичный пик — повод отклонить или продолжить исследование.
- [ ] Сравнить простую стратегию без ML с той же стратегией с ML-фильтром; ML должен показать добавочную пользу.
- [x] Реализовать paired shared-wallet comparison baseline/ML filter/optional frozen reference: одинаковые capital/history/risk plans, baseline subset guard, обычные и stress расходы для каждой стороны, paired full-UTC-day bootstrap. Actual strategy/current-model benefit и independent qualification остаются открытыми.
- [ ] Результаты привязать к общему портфельному капиталу и лимитам, а не неограниченным независимым сделкам.

**Готовность:** короткий список кандидатов и полный журнал попыток; отсутствие победителя — допустимый результат.

## 8. Этап 5 — обучение под прибыль и риск

VP: условный EXTEND research-only ML — [VP-07](#cf-vp-2026-10-17---video-derived-strategy-research), только после зрелых меток и отдельного evidence; LLM-направление здесь не ведётся.

- [x] Реализованы регуляризованный logistic classifier и отдельные experimental net ridge heads (7/24 features), с train-only normalization и development comparisons. Qualified profitable candidate ещё не получен.
- [ ] Сравнения: отсутствие сделок, стратегия без ML, текущая модель; buy-and-hold как контекст при сопоставимых датах/капитале.
- [x] Проверено одно bounded nonlinear family:experimental net tree depths2/3/4, development-only; результаты хуже constant baseline, live admission не выдан.
- [ ] Независимая оценка выбранной процедуры nonlinear learning при достаточных будущих данных.
- [ ] Разделить вероятность прибыли, величину результата и решение о входе. Порог подбирать по validation ожидаемой доходности с ограничением риска и активности.
- [x] Реализовать research-only selector полного declared threshold grid по validation portfolio summaries: одинаковые study/period/capital, положительные net и stress результаты, minimum trades, обычная и stress drawdown; test rows и неполная сетка отклоняются. Применение в зарегистрированном эксперименте и независимое подтверждение остаются открытыми.
- [x] Experimental net classifier поддерживает явно заданные train-only inverse-frequency weights; validation сохраняет естественное распределение,weighted scores не объявляются calibrated probabilities.
- [x] Preregistered bounded balanced/unweighted comparison выполнен на natural validation и ordinary/stress wallets; balanced ухудшил diagnostics и дал отрицательный PnL.
- [ ] Независимая natural-distribution calibration и проверка balancing benefit на достаточных окнах; sampling extensions только после этой проверки.
- [x] Primary artifacts и prospective diagnostics содержат log loss/Brier, calibration bins и grouped-tie average precision. Constant-train-rate baseline сохранён; эти метрики не разрешают publication без торговых gates.
- [ ] Независимое подтверждение calibration stability и positive portfolio payoff.
- [x] Сравнить заранее заданные train-окна2/4дня и uniform/half-life1день на общей bounded BTC/ETH validation: четыре зарегистрированных development варианта выполнены и проверены по original input/runtime snapshots; независимая квалификация не выполнена.
- [x] Registered development-only window study реализован и actual4-cell сравнение выполнено; full grid reserved before fit, fixed validation, SHA snapshots/weights/source, persistent budget и immutable cache. Independent qualification остаётся открытой.
- [x] Реализовать research-only подготовку ограниченного train-окна и recency weights: доступность меток до frozen train_end, отсутствие duplicates, target-independent веса и effective sample size; weighted ridge использует эти веса также в train-only нормализации.
- [x] Development ablation 7 вариантов и portfolio comparisons выполнены; устойчивое улучшение торговли не получено.
- [ ] Independent ablation stability; удалять признаки только после доказанного эффекта на payoff/риске.
- [x] Для completed bounded studies сохранены original runtime/input bundles, commit/dirty flag, Python/numeric runtime, параметры/cutoffs; deterministic fit seed=None явно описан, bootstrap seed frozen.
- [ ] Обеспечить такой provenance для всех будущих qualified studies, включая полный конец train/selection/evaluation информации.

**Готовность:** кандидат выбран без test-подбора; известны его торговые ограничения и отличие от простых baseline. Accuracy выше большинства сама по себе не обязательна для прибыльной стратегии с редкими входами; текущий фильтр accuracy пересмотреть только вместе с проверкой trade PnL, статистики и риска.

## 9. Этап 6 — walk-forward и устойчивость

VP: REUSE ledger/purge/paired metrics, NEW preregistered окна — [VP-05](#cf-vp-2026-10-17---video-derived-strategy-research). Просмотренные периоды не переименовывать в blind test.

### Протокол

- [ ] Предварительно выбрать календарные окна; пример для истории ≥12 месяцев: 120 дней train, 30 validation, 30 test, шаг 30 дней.
- [ ] Test-окна для итоговой метрики не перекрываются; train может расширяться/сдвигаться по выбранному заранее правилу.
- [ ] Purge по реальному времени завершения меток; временной зазор покрывает максимальный горизонт и задержку доступности данных.
- [ ] В каждом окне заново обучать preprocessing и модель; переносить только информацию, доступную к началу проверки.
- [ ] Оценивать выбранную процедуру поиска целиком, а не только удачный финальный набор параметров.
- [ ] Выделить закрытый финальный период до начала поиска. После просмотра считать его использованным; для новой настройки нужен новый период.
- [ ] Считать метрики по всем out-of-sample сделкам, монетам, режимам и календарным блокам.
- [ ] Bootstrap проводить по временным блокам с совместным учётом монет, чтобы сохранять зависимости. Не считать коррелированные сигналы независимыми.
- [ ] Учитывать множественный перебор: фиксированный бюджет, полный реестр попыток, независимая итоговая проверка; при большом поиске добавить заранее выбранную статистическую коррекцию.

### Предлагаемые критерии кандидата для paper

- [ ] Не менее 6 последовательных независимых test-окон при доступности истории; при меньшем числе — статус «недостаточно данных».
- [ ] Не менее 200 исполненных out-of-sample сделок суммарно; это нижний фильтр активности, не самостоятельное доказательство.
- [ ] Положительная net expectancy; нижняя граница заранее определённого 95% block-bootstrap интервала >0.
- [ ] Profit factor ≥1,2; если убытков нет, проверить малую выборку, а не трактовать бесконечное значение как доказательство.
- [ ] Положительный результат как минимум в 2/3 test-окон; худшее окно и режимы отражены отдельно.
- [ ] Максимальная портфельная просадка ≤5% при зафиксированном исследовательском капитале/размере позиции либо более строгом действующем лимите.
- [ ] При удвоении переменных издержек net expectancy остаётся >0; при задержке на дополнительную свечу нет недопустимой просадки.
- [ ] После удаления пяти самых прибыльных сделок результат не превращается в существенный убыток.
- [ ] Нет необъяснённой зависимости от одной монеты/одного месяца; если подход специально локален, область применения фиксируется до финального теста.
- [ ] Кандидат улучшает заранее выбранную основную портфельную метрику относительно baseline без ухудшения установленных ограничений риска.

**Готовность:** все условия пройдены на независимых данных. Иначе отклонить, сузить применимость с новой проверкой или собрать больше данных. Не повышать частоту сделок ради количества.

## 10. Этап 7 — воспроизведение и paper

VP: REUSE isolated harness, BLOCKED prospective qualification — [VP-06](#cf-vp-2026-10-17---video-derived-strategy-research) после R2/R14 mark-source evidence.

- [ ] Повторить финальный backtest из сохранённого dataset/config на чистом запуске; результат совпадает в заданном допуске.
- [ ] Для стратегий Freqtrade выполнить lookahead-analysis; собственные стратегии проверять тестами причинности и совпадения потокового/пакетного расчёта.
- [x] Отдельный Spot shadow/paper harness, guarded activation, wallets/export/independent fill auditor реализованы и локально проверены.
- [ ] Квалифицировать и запустить конкретную новую frozen candidate/control policy после preflight; наличие harness не закрывает future-period paper admission.
- [ ] Зафиксировать версию и запустить наблюдение минимум на 30 календарных дней и 100 завершённых paper-сделок. При редких сигналах продлить срок, не ослаблять условия.
- [ ] Записывать сигнал, доступные признаки, ожидаемые/фактические paper fills, задержки, комиссии, отказ, причину выхода и net PnL.
- [ ] Сверить историческое воспроизведение того же будущего периода с paper. Каждое существенное расхождение объяснить.
- [ ] При отсутствии реальных fills явно учитывать оптимизм paper-исполнения; shadow-сигнал не считать исполненной сделкой.
- [ ] На paper сохранить положительную expectancy после консервативных издержек, допустимую просадку и достаточную статистическую определённость; неопределённость означает продолжение наблюдения.
- [ ] Любая доработка по результатам paper создаёт новую версию с новым будущим периодом наблюдения.

**Готовность:** причинность, исполнение и будущая эффективность согласованы. Изменение действующей торговли — отдельное конкретное решение после проверки; этот план до него не повышает риск.

## 11. Этап 8 — цикл улучшений и остановки

- [ ] Регулярно обновлять архив и проверять его качество; частоту исследования выбирать по измеренному бюджету ресурсов.
- [ ] Переобучение запускать по расписанию или выявленному дрейфу, а не после каждого убытка.
- [ ] Использовать состояния: candidate → offline_passed → paper_running → paper_passed → approved; rejected/stale отдельно.
- [ ] Не переобучать действующую модель на месте; хранить действующую версию, кандидата и возможность отката.
- [ ] Новую версию сравнивать на периоде после всех данных, использованных обеими в подборе.
- [ ] Контролировать распределение признаков, вероятность, частоту входов, издержки и результаты по режимам.
- [ ] Пропавшие данные, несовместимые признаки или повреждённый артефакт не обходят проверку качества; обработка выходов продолжает работать.
- [ ] При превышении риска или деградации ограничить новые входы по действующей политике; не пытаться отыграть убыток повышением позиции.
- [ ] Если после нескольких заранее ограниченных циклов нет преимущества — сохранить вывод, остановить расширение перебора и пересмотреть гипотезу/данные.

**Готовность:** проверен полный сценарий от появления кандидата до отклонения/бумажного наблюдения и отката; нет требования «обязательно заработать больше прошлого раза».

## 12. Артефакты и отчёт эксперимента

VP: EXTEND provenance/findings — [VP-08/09](#cf-vp-2026-10-17---video-derived-strategy-research); independent QA/source/security gates обязательны, результаты пока отсутствуют.

Для каждого эксперимента сохранять:

- [ ] Experiment ID, UTC-даты, commit, seed, версии зависимостей и статус.
- [ ] Dataset manifest/checksum, состав universe и известные ограничения источника.
- [ ] Train/validation/test/paper границы и `fit_information_end`.
- [ ] Feature/target/simulator версии и параметры входа/выхода.
- [ ] Все варианты поиска, включая неудачные; причина выбора победителя.
- [ ] Журнал исполненных и отклонённых сделок, equity и использование капитала.
- [ ] Net PnL, expectancy, profit factor, drawdown, длительность, активность, издержки и доверительные интервалы.
- [ ] Разбивка по окнам/монетам/режимам, стресс и сравнение baseline.
- [ ] Пройденные/проваленные проверки, ограничения, решение и следующий шаг.

Исходные данные и крупные результаты хранить в игнорируемом архиве/хранилище; в Git — код, конфигурации без секретов и краткие результаты. При добавлении хранения в Postgres сначала спроектировать схему, политику доступа и миграции по навыкам проекта.

## 13. Порядок реализации и существующие команды

Первая очередь: этап 0 → проверка архивов → симулятор → метки → причинность. Вторая: расширение покрытия → ограниченный поиск → ML → walk-forward. Третья: независимый финальный тест → paper → управляемый цикл.

После каждого изменения запускать целевые тесты, затем полный набор перед завершением этапа:

```sh
.venv/bin/python -m pytest tests/test_archive.py tests/test_strategy_search.py tests/test_model_training.py -q
.venv/bin/python -m pytest -q
git diff --check
```

Существующие команды предварительных архивных экспериментов (не заменяют будущие portfolio/walk-forward проверки):

```sh
PYTHONPATH=src .venv/bin/python scripts/download_market_archive.py --pair BTC/USDT --pair ETH/USDT --days 90 --interval 5
PYTHONPATH=src .venv/bin/python scripts/train_archive_model.py --pair BTC/USDT --pair ETH/USDT --epochs 50 --horizon-candles 12
```

Текущий `--max-candles` по умолчанию ограничивает обучение примерно 26 000 свечами на монету. Для длинного архива явно задать нужное покрытие после проверки ресурсов. Параметры будущих CLI-команд не считать реализованными, пока не добавлены код и `--help`.

## 14. Журнал выполнения

### Сверка состояния, 7 октября 2026 года

- Проверены другой чат, commit `da16f15`, файлы short-shadow и локальные состояния timer/service.
- Отмечены выполненными архивные функции, shadow outcomes, предполагаемые издержки, исключение незакрытых свечей и пропусков.
- Проверки текущего документа: `git diff --check`, существование ссылок на рабочие файлы и парность Markdown code fences.
- Открытый риск: временной cutoff при смене разметки; конец validation-подбора также должен входить в `fit_information_end`.
- Следующий шаг: этап 0; затем общий симулятор сделки. Short-shadow ветку продолжать через baseline/net evaluation без повторного создания инфраструктуры.


Для завершённого этапа добавить запись:

```text
Этап / дата:
Commit / experiment ID / dataset ID:
Что сделано:
Проверки и результаты:
Артефакты:
Пройденные критерии:
Не пройденные критерии / ограничения:
Решение: перейти / исправить / собрать данные / отклонить
Следующий шаг:
```

## 15. Технические источники

- [Bybit Kline API](https://bybit-exchange.github.io/docs/v5/market/kline): исторические диапазоны, до 1000 свечей за запрос; незакрытая свеча требует исключения.
- [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): разделение временных данных и зазор между выборками. Purge по завершению торговых меток реализуется дополнительно.
- [Freqtrade backtesting](https://www.freqtrade.io/en/stable/backtesting/): допущения симуляции и учёт комиссий; проверить применимость к собственному исполнителю.
- [Freqtrade lookahead-analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/): проверка влияния будущих данных на индикаторы и сделки. Не заменяет проверку исполнения и прибыльности.

Пороговые значения, размеры окон и этапы этого плана — проектные решения CryptoForge, не рекомендации доходности из перечисленных источников.

### Продолжение этапа 0, 7 октября 2026 года

- Удалён обход временной границы при смене цели.
- Обучающий runner сохраняет `fit_information_end` по train+validation и `evaluation_information_end` по test. Архивный runner сохраняет те же поля.
- Сравнение исключает данные до максимальной известной границы кандидата/действующей модели, включая предыдущий период допуска. Старые модели дополнительно ограничены датой публикации. Некорректные/наивные даты отклоняются.
- Создан черновик протокола; даты финального теста, universe, капитал, реальные расходы и бюджет ресурсов ещё не зафиксированы.
- Следующий шаг: завершить фиксацию протокола и затем этап 2 — общий симулятор. Публикация модели/изменение торговли в этом ходе не выполнялись.

- Проверки этого продолжения: 272 теста прошли; `git diff --check` без ошибок; JSON протокола разобран успешно.

### Продолжение этапа 2, 7 октября 2026 года

- Добавлен `src/cryptoforge/trade_simulator.py`: общий offline Spot портфель, Decimal-баланс, вход после сигнала, стоп/цель/timeout, неблагоприятное разрешение двойного касания, гэпы, комиссии в quote, slippage, округление, минимальная стоимость, общий капитал и ограничение позиций.
- Добавлен `scripts/backtest_archive_portfolio.py`; он сохраняет журнал и equity локально, никогда не публикует модель/ордер. Поток сигналов пока берётся из текущих исследовательских правил; live/paper интеграция ещё не сделана.
- Ликвидность фильтруется по предыдущему закрытому объёму. Частичные fills, исторические индивидуальные instrument rules, комиссии в base/третьей валюте, отдельный bid/ask spread, 1m-разрешение неоднозначности, дневные risk guards и trailing остаются будущими задачами. Параметры симулятора — допущения, не снимок live-конфигурации.
- Просадка считается с консервативной оценкой одновременных lows, не как точный внутрисвечной путь. История должна иметь общую непрерывную сетку; выход в конце истории помечен `end_of_data`.
- 11 целевых сценариев прошли; полный актуальный набор — 289 passed; `git diff --check` без ошибок.
- Development replay BTC/ETH за имеющиеся 90 дней: стартовый капитал 100 USDT, stake 6 USDT, 1609 завершённых сделок, net PnL −27,5655 USDT, итог 72,4345 USDT; консервативная граница просадки ≈27,60%. Балансовое тождество проверено. Это не независимая оценка и не результат live-торговли.
- Результат: текущая простая trend-гипотеза не прошла; никакого допуска в торговлю.
- Этап 0 пока не закрыт: universe/dataset/final-test/resource параметры не заморожены. Прототип симулятора сделан на существующем development-архиве, без запуска поиска на финальном тесте.
- Следующий шаг: новые trade-outcome метки на этом модуле и проверки причинности; параллельно завершить фиксацию протокола перед подбором стратегий.

### Продолжение этапа 3, 7 октября 2026 года

- Добавлен `trade_labels.py`: `spot-long-trade-net-v1`, независимые контрфактические long-входы с причинными признаками, net-прибыльностью, trade-журналом и отказами отдельно. Конец метки — закрытие свечи выхода, поскольку симулятор использует её OHLC.
- Метки не складываются в портфельную прибыль. Готовая модель отдельно проверяется общим капиталом через `simulate_portfolio`; short-head в выходном артефакте исключён и помечен недоступным.
- Добавлен отдельный `scripts/train_trade_outcome_model.py`; исходная live-разметка и активная модель не менялись. Артефакты находятся в `.local/archive/trade-models`.
- Пробный development запуск: BTC/ETH, последние 5000 свечей на пару, 30 epochs, hold=12. Получены 9902 исполнимые метки, отказы=0; test=1486 наблюдений. На test classifier дал accuracy≈87,95%, но precision/recall=0. Портфель исполнил 4 сделки с net PnL −0,2383 USDT. Преимущество не обнаружено; допуска нет.
- Целевые тесты: 6 сценариев прошли — цель/стоп/неоднозначность, издержки, отказ, полный горизонт, причинность признаков, purge и пропуски.
- Осталось: ручная сверка ≥20 исторических меток, MFE/MAE, регрессия net PnL, сохранение dataset/checksum и распределений по монетам/периодам, расширенные признаки, frozen protocol и walk-forward. Этап 3 не закрыт целиком.
- Следующий шаг: диагностировать редкость положительных меток и отдельно проверять ограниченные стратегии/выходы на validation, не подбирать по этому test.

- Полная проверка этого продолжения: **295 passed**, `git diff --check` без ошибок.

### Аудит меток и ограниченная validation-проверка, 7 октября 2026 года

- Добавлен `scripts/audit_trade_labels.py`: анализ только первых 70% последних 5000 свечей каждой монеты; классы, выходы и распределение по месяцу. Dataset checksum и примеры сохраняются в `.local/state/trade-label-audit.json`.
- Независимым кодом повторно рассчитаны 20 стратифицированных исторических сделок BTC и 20 ETH: цена входа, округление количества, порядок достижения барьеров, время/причина выхода, net PnL и класс совпали. Это автоматизированная арифметическая сверка, **не ручная экспертиза 20 меток**; соответствующий пункт остаётся открытым. В этой истории нет достигнутых целей; случаи target/двойного касания дополнительно покрыты синтетическими тестами.
- Train-участок: по 3451 исполнимой метке. BTC positive rate≈16,23%, 3442 timeout/9 stop; ETH≈21,18%, 3432 timeout/19 stop. Фиксированная цель 4% редко достижима за 12 свечей в этой выборке. Это наблюдение по development/train, не утверждение о будущей доходности.
- Добавлен `scripts/search_validation_portfolio.py`: 18 заранее заданных вариантов трёх семейств, hold 12/24/48, stop/target 1%/2% либо 2%/4%. Диапазон validation строго 70–85%; outer test не оценивается. Перед вычислением результатов сохраняется protocol с сеткой, границами и checksum development-данных.
- Проверка единым капиталом, обычными и удвоенными издержками. Все 18 вариантов убыточны. Лучший по net PnL: breakout, hold=48, stop=1%, target=2%; 19 сделок, −0,2301 USDT, при двойных расходах −0,5636 USDT. Ни один не прошёл даже предварительный validation-фильтр.
- Результаты: `.local/state/validation-search.json`, спецификация: `.local/state/validation-search.protocol.json`. Выбранной стратегии и публикации модели нет.
- Добавлен регрессионный тест: изменение/повреждение цен в последних 15% истории не меняет validation-отчёт. И независимая сверка 20 синтетических сделок.
- Следующий шаг: зафиксировать отдельную ограниченную гипотезу выходов, привязанных к прошлой волатильности/ATR, и регрессию ожидаемого net PnL; дальше проверять walk-forward. Не расширять бесконечно подбор на этой же validation; её reuse фиксировать как использованную development-историю.

- Полная проверка: **297 passed**, `git diff --check` без ошибок.

### Возврат к ранним этапам: закрытие этапа 0, 7 октября 2026 года

- Зафиксирован `config/research-protocol-v1.json`, версия `research-v1.1`, статус `frozen_development_only`: BTC/ETH, SHA-256 обоих 90-дневных архивов, фактические диапазоны, 5m, предполагаемые издержки, капитал 100/stake 6/max positions 3 для offline и критерии. Это исследовательская конфигурация, не изменение live-риска.
- Весь архив и любая история до `frozen_at` считаются использованными development-данными, даже если старые журналы неполны. Конфигурации известных экспериментов сохранены в записях выше и их артефактах. Такая консервативная граница запрещает выдавать ранее использованные данные за финальный тест.
- Зарезервирован будущий период 2026-10-08 00:00 UTC — 2026-11-08 00:00 UTC (03:00 МСК). Он пока недоступен и не используется при подборе; это один итоговый будущий период, не замена 6 walk-forward окнам.
- Санитизированный снимок активной модели (версия/checksum/feature/config) и фактических параметров исполнителя сохранён в `.local/state/research-v1-runtime.json`, права 0600. Секреты/API-ключи не записаны.
- Runtime: live flag=true, gate=0.50, stake=6, max positions=6, max daily loss=2, stop=4%. Документация исправлена; настройки не менялись. Legacy contract модели совпал с 5m/horizon=3/candle-v1/threshold=0.50. Trade-outcome модель несовместима и остаётся отдельной offline-веткой.
- Измерение процесса снимка с полным чтением архивов: peak RSS≈654,09 МБ; пилот 1000 свечей/951 метка ≈0,274 сек. RSS не является отдельным измерением чистого worker. На момент измерения свободно ≈767,97 МБ RAM и ≈8037,97 МБ диска.
- Исправлен прежний нереалистичный memory budget: worker≤768 МБ, для запуска требуется available RAM≥1536 МБ, disk≥2048 МБ; один worker, nice≥10, wall≤120 сек, ограничение размера каждого выходного файла≤128 МБ. Суммарный размер новых файлов пока не ограничен отдельной квотой; проверка свободного диска обязательна.
- Offline CLI подключены к `prepare_research`: контроль frozen manifest/hash, памяти/диска, universe/source, временной границы, лимитов адресного пространства/размера файла/времени. При недостатке памяти запуск откладывается. Существующие live/nighly процессы не перенастраиваются.
- Проверки: frozen ranges, несовместимый target, отказ при ресурсах ниже бюджета; существующий exit успешно выполняется без обращения к неисправному ML-реестру. Причинность ранее проверена изменением будущих признаков и outer test.
- Следующий незавершённый этап — 1: качество и расширение архива, историческая доступность universe, 1m и сверка источника. К новым стратегиям/ML пока не переходить.

- Повторная проверка после подключения guards: **301 passed**, `git diff --check` без ошибок. Лимиты памяти/файла и эксклюзивный lock проверены с подменой системных лимитов, без воздействия на процесс торговли.

### Этап 1: качество и пилот расширения, 7 октября 2026 года

- Добавлен `archive_quality.py`: OHLCV/alignment/уникальность/закрытость, конечные положительные цены и неотрицательные объёмы; компактные диапазоны пропусков. Неполные aggregation buckets исключаются без выдуманных свечей.
- Клиент и ArchiveReader поддерживают 1m; CLI имеет фиксированные `--start/--end`. Источник сверён с официальным Bybit Kline API. Новые загрузки по умолчанию пишутся в `.local/archive-stage1`; frozen archive CLI менять запрещает.
- Для каждого диапазона создаются отдельный content-addressed snapshot и manifest с source, временем загрузки, requested boundaries, фактическим покрытием, gaps, dataset ID, SHA-256 и transformation version. Старые снимки/manifest не перезаписываются. Общий latest manifest оставлен как указатель последнего запуска, не как единственная история.
- Старые BTC/ETH архивы: по 25 919 свечей, качество valid. По три свечи на начале/середине/конце каждого архива точно совпали с новым ответом Bybit.
- Minute pilot BTC/ETH: 2026-10-01 00:00 UTC — 2026-10-02 00:00 UTC, по 1440 свечей без пропусков. Весь день: 1m→5m (288) и 5m→1h (24) точно совпал с прямым ответом Bybit по OHLCV/turnover. Это проверка данных, не реализация intrabar-stop разрешения в симуляторе.
- 10-парный 14-дневный пилот: BTC, ETH, SOL, XRP, DOGE, ADA, LINK, AVAX, LTC, DOT; 2026-09-17 — 2026-10-01 UTC. По 4032 свечи, всего 40 320, пропуски=0. Отчёт `.local/state/stage1-pilot-universe.json`; индивидуальные snapshots/manifest в stage1/snapshots.
- Онлайн instrument specs и turnover сохранены в `.local/state/archive-quality-source.json` с датой наблюдения. Исторические листинги/делистинги/спреды/изменения правил не доступны из этого снимка; текущий universe **не считается историческим point-in-time universe**. Этот пункт остаётся открытым.
- Во время DOGE-загрузки получен Bybit retCode 10016 (server error). Добавлены ограниченные повторы публичного GET с backoff; повторный запуск использовал сохранённые страницы. Тест подтверждает восстановление после прерывания без дублей и без перезаписи старого manifest.
- Проверки исходных архивов и API заняли ≈2,503 сек, процесс peak RSS≈654,09 МБ (полное чтение); свободный диск ≈8031 МБ. JSON допустим для текущего небольшого пилота; масштабирование до 12 месяцев ещё требует выбора/проверки формата и бюджета записи.
- Следующий шаг **в этом же этапе 1**: выбрать формат длительного хранения, расширить историю до доступного периода, отдельно решить point-in-time universe или явно ограничить исследование фиксированной исторически доступной корзиной. Длинная загрузка и новый протокол не считаются выполненными.

- Итоговые проверки этого продолжения: **310 passed**, `git diff --check` без ошибок. Frozen архивы не изменены; новая история отделена от протокола v1 и пока не допущена в обучение.

### Этап 1: потоковый годовой архив (в работе), 7 октября 2026 года

- Для длинного хранения выбран SQLite с decimal TEXT, ключом symbol/interval/time, WAL и атомарным commit каждой страницы. Проверка range checksum/качества и чтение ограниченного окна выполняются потоково. JSON оставлен только для предыдущих небольших снимков.
- `scripts/download_long_archive.py` загружает фиксированную корзину из 10 пар за 2025-10-01 — 2026-10-01 UTC в `.local/archive-stage1/history.sqlite`. Журнал прогресса обновляется после каждой пары; неудачные страницы можно дозагрузить.
- `sqlite_archive.py` сохраняет отдельные range manifest с canonical-row checksum; изменённый или неполный диапазон reader отвергает. DB является изменяемым cache, поэтому перед чтением обязателен логический checksum диапазона, а не hash всего SQLite-файла.
- Пилот измерения живого загрузчика по /proc: RSS 25 480 КиБ, HWM 31 872 КиБ; сохранено в `.local/state/sqlite-download-resource-sample.json`. Это показатель текущего процесса; старые getrusage high-water числа не считать размером чистого worker.
- Добавлен `archive_universe.py`: causal membership по полному предыдущему UTC-дню и turnover внутри фиксированной корзины. Изменение следующего дня не меняет прошлое membership. Исторические делистинги вне собранной корзины и старые instrument rules по-прежнему неизвестны; нельзя заявлять охват всего рынка.
- Подготовлен `scripts/verify_long_archive.py`: логический checksum, 3 даты прямой сверки Bybit на пару, дневная availability/liquidity history и существующие instrument observations. Финальное завершение загрузки/верификации ещё не отмечено.

### Этап 1: завершение годовой загрузки и сверки, 7 октября 2026 года

- Все 10 пар загружены полностью за 2025-10-01 00:00 UTC — 2026-10-01 00:00 UTC: по 105120 5m свечей, всего **1051200**, пропуски=0, failures={}.
- Загрузка заняла ≈936 сек; SQLite после закрытия WAL≈83,42 МиБ. Контроль памяти живого процесса: HWM≈31,13 МиБ, RSS≈24,88 МиБ. Лимит экспериментов 120 сек не применялся к отдельной resumable загрузке данных; обучение не запускалось.
- Все range checksum проверены; на каждой паре 3 даты × 3 свечи сверены с прямым API Bybit (90 свечей суммарно). Для уже проверенных диапазонов повторный API-запрос не делался при неизменном логическом checksum.
- Сохранено **3650** дневных записей membership: только предыдущий полный UTC-день и его turnover. Это causality внутри фиксированной survivor basket, не восстановление всего исторического состава биржи.
- Артефакты: `.local/archive-stage1/history.sqlite`, `manifests/`, `long-download-progress.json`, `.local/state/long-archive-quality.json`. Старые frozen v1 JSON архивы сверены по SHA-256 и не изменены.
- Проверки: **313 passed**, `git diff --check` без ошибок; precision/resume/checksum отказ и отсутствие future-volume leakage покрыты тестами.
- Открытые пункты этапа 1: исторические instrument rules/listings/delistings и полное историческое universe. Текущий API-снимок не подставляется задним числом. Пока отсутствуют источники такой истории, эти пункты не отмечаются выполненными и следующий этап не открывается.
- Следующий шаг в этапе 1: исследовать доступные источники истории листингов/правил; составить реестр дат и явно отделить подтверждённые факты от неизвестных. Годовой архив в trading/training не внедрён.

### Этап 1: официальные события и делистнутые пары, 7 октября 2026 года

- Добавлен `instrument_history.py`: отдельные effective/announced даты, источник и SHA-256; as-of состояние не включает ещё не опубликованные/не вступившие в силу события. Global Spot не смешивается с EU/derivatives. Минимальное количество отдельно от quantity step; неизвестные поля не заполняются сегодняшними значениями.
- `build_instrument_history.py` проверяет JSON source cache против captured HTML, сохраняет immutable content-addressed HTML и импортирует только вручную рассмотренные типы/поля. Для date-only midnight publication используется консервативная граница следующего дня. Историческая версия страницы не подтверждена: current-page publication metadata не считается полным архивом правок.
- **27 событий / 6 источников**: January 2025 минимальные API/non-API ордера и количество для 10 пар; 10 наблюдений наличия в официальной таблице; 6 делистингов AMI/BDXN/ONE/SIS/XEM/INSP с cutoff 2026-05-28 08:00 UTC; listing MONUSDT 2025-11-24 15:00 UTC. Источники: `.local/archive-stage1/sources/captured/`; реестр `.local/state/instrument-history.json`.
- Базовые API min order value=5 USDT в January 2025 таблице не переносились автоматически на весь последующий год и не изменяли конфигурацию торгового исполнителя. Quote non-API ограничения не используются вместо API. Quantity step/tick size для корзины остаются неизвестными, если нет соответствующего источника.
- Проверен API для всех 6 делистнутых пар: свечи до прекращения торгов доступны, несмотря на отсутствие таких пар в текущем online snapshot. Загружены последние 30 дней: 51837 свечей из ожидаемых 51840. AMI/BDXN/XEM имеют по одному пропуску в конце; ONE/SIS/INSP полные. Полные parent ranges с пропусками reader отвергает; 6 непрерывных subranges выделены с отдельными checksum и parent provenance, без заполнения разрывов.
- Артефакты: `.local/archive-stage1/delisted.sqlite`, `delisted-download-progress.json`, `.local/state/delisted-history-probe.json`, `.local/state/delisted-archive-quality.json`.
- Исправлена коллизия журналов разных SQLite DB: progress теперь называется по имени базы (`history-download-progress.json`, `delisted-download-progress.json`). Годовой журнал восстановлен из неизменяемых range manifest и сохранён отдельно; verifier использует именованный журнал. Старый общий указатель восстановлен для совместимости.
- Инвентаризация 7 официальных linkmap-страниц дала **89 уникальных кандидатов**; futures/Alpha/Convert исключены по явным признакам URL. URL title не считается событием: published/effective/market пока unknown, status=unreviewed, events_imported=0. `.local/state/historical-source-inventory.json`; полнота индекса не доказана.
- Проверки: **321 passed**, `git diff --check` без ошибок; no-backdating, future publication, delisting/relisting boundaries, market isolation, неизвестный quantity step, segment separation и checksum защита. Официальный реестр построен повторно с проверкой происхождения cache.
- Этап 1 по-прежнему открыт: разобрать источники-кандидаты за исследуемый год, расширить подтверждённую timeline и проверить покрытие исторических правил/universe. Частичный реестр всегда возвращает `can_certify_historical_execution=false`; ни модель, ни universe исполнителя не менялись. К этапу 2 не переходить.

Подтверждённые первичные источники:

- [Минимальные значения/количества, January 2025](https://announcements.bybit.com/en/article/update-on-minimum-single-order-value-and-quantity-for-spot-and-margin-trading-pairs-blt96f1cea87db75db9/).
- [Делистинг шести Spot-пар, May 2026](https://announcements.bybit.global/en/article/delisting-of-ami-bdxn-one-sis-xem-and-insp-bltdf4d2a49c410bf3f/).
- [Листинг MON на Spot](https://announcements.bybit.com/en/article/bybit-to-list-monad-mon-on-spot-blt92fd8d600e619238/).
- [Общие изменения maximum order size](https://announcements.bybit.com/en/article/changes-to-maximum-order-size-for-limit-and-market-orders-blt6ac479804a794c46/): численные пределы отдельных пар не импортированы.

### Этап 1: обработка 89 источников и два изменения tick size, 7 октября 2026 года

- Добавлены `announcement_sources.py`, `review_historical_sources.py`: captured source HTML/SHA, JSON-rich-text либо HTML body, публикационная дата, range classification и отдельная очередь событий. URL/title сами по себе событием не считаются; events_imported=0 до curated review.
- Обработаны все 89 URL. После проверки региона: 85 Spot-source candidates, 2 market/body unconfirmed, 1 non-Spot excluded, 1 Bybit EU excluded. Эти 85 записи не означают 85 подтверждённых event timeline.
- Обнаружено, что `/en/` на global announcement domain может содержать текст **Bybit EU**. Добавлена content-based venue проверка; regression test исключает такой notice из global Spot.
- В 2026-04-01 tick announcement вручную сверены effective time 10:00 UTC, заголовки таблицы и строки AVAXUSDT/LINKUSDT: after tick=0.001. Импортированы 2 rule-change события. Before tick=0.01 не переносится на начало исследуемого года, поскольку дата начала его действия неизвестна. Реестр теперь **29 событий / 7 первичных источников**.
- Среди прочих найденных minimum/tick notices большинство таблиц не затрагивают корзину; это не доказательство отсутствия иных изменений. Maximum quantity notice без рассмотренной численной таблицы не заполняет pair-specific пределы.
- Coverage audit по публикациям кандидатов: 2025-10=18, 2025-11=13, 2025-12=17, 2026-01=17, 2026-02=8, 2026-03=15, 2026-04=1. Linkmap не содержит May–September 2026 в этой выборке; полноту годовой истории объявлений считать недоказанной. Поздние источники, рассмотренные отдельно ранее, не устраняют этот пробел целиком.
- Артефакт `.local/state/historical-source-review.json` сохраняет classification, provenance, curated fields для двух событий и coverage gaps; `.local/state/instrument-history.json` обновлён. Оригинальные исторические версии страниц не подтверждены; current-page snapshot не подменяет point-in-time revision archive.
- Проверки: **323 passed**, `git diff --check` без ошибок. Реестр повторно собран с проверкой исходного HTML и table headers.
- Следующий шаг в **этапе 1**: получить источники за отсутствующие месяцы и разобрать конкретные effective dates/Spot sections оставшейся очереди. Полнота historic universe/rules по-прежнему не подтверждена, поэтому этап 2 не начинается. Торговля и модель не менялись.

Дополнительные первичные источники:

- [Tick size changes, April 1 2026](https://announcements.bybit.com/en/article/updates-on-tick-size-for-spot-pairs-apr-1-2026-10-00am-utc--bltdc47ad37a9df200a/).
- [Notice с Bybit EU в содержании](https://announcements.bybit.com/en/article/updates-on-tick-size-for-spot-pairs-blt9836f15aa75be922/): исключён из глобальной timeline.

### Этап 1: закрытие календарного пробела и новые события, 7 октября 2026 года

- Найден `articleInitEntity` официальных announcement category pages: пагинация действительно меняет objectID-списки и initialPage. Новая `inventory_announcement_categories.py` сохраняет HTML/SHA каждой страницы, total/items/date bounds, обнаруживает повтор страницы и ограничивает бюджет. Resume продолжает незавершённую категорию; completed categories не перечитываются без необходимости.
- Пройдены delistings=14, new_crypto=28, latest_bybit_news=16 и all=130 страниц до публикаций раньше 2025-10-01. Кандидатов стало **140** (89 linkmap + 51 новых). Все captured candidates проверены по actual article metadata/body; календарь покрывает все 12 месяцев study period. Это observed index coverage, а не доказанная exhaustiveness.
- Публикации: 2025-10=19, 11=13, 12=17; 2026-01=17, 02=8, 03=15, 04=11, 05=9, 06=11, 07=8, 08=8, 09=4. Прежний May–September gap устранён; смысловые/численные пробелы остаются.
- После content/venue классификации: 134 Spot candidates pending factual review, 4 unknown, 1 non-Spot excluded, 1 EU excluded. Curated events из review queue=7; весь общий реестр теперь **34 события / 9 источников**.
- Импортирован DOTUSDT tick_size=0.0001 с 2026-06-26 08:00 UTC. Старое before=0.001 не объявляется доказанной baseline на 2025-10-01. Новое effective time и numeric table вручную сверены с body; UTF rich-text и HTML-table поколения announcement pages обрабатываются отдельно.
- Импортированы 4 Spot delisting cutoff: NEONUSDT/SUNDOGUSDT/ICXUSDT/TACUSDT, 2026-09-24 08:00 UTC. Исключены даты закрытия deposits/Convert/withdrawals; используются только Spot trading dates.
- Артефакты: `.local/state/historical-category-inventory.json`, обновлённые historical-source-inventory/review, instrument-history; дополнительные sources под category-indexes и inventory-captured.
- Проверки: **326 passed**, `git diff --check` без ошибок. Тесты проверяют candidate filter (SPOTUSDT perpetual не является Spot), UTC study boundary/pagination и обе структуры таблиц. Повторная сборка registry прошла проверки source origin и headers.
- Этап 1 **ещё открыт**: factual review оставшейся очереди, baseline quantity/tick/order limits и полнота rule changes/universe. Календарные отметки сами по себе не закрывают эти пункты. Новые данные не передаются в live/training; параметры торговли не менялись.

Новые проверенные первичные источники:

- [DOT tick size, June 26 2026](https://announcements.bybit.com/en/article/updates-on-tick-size-for-spot-pairs-jun-26-2026-8-00am-utc--blt4f859a69f6600b94/).
- [Четыре Spot делистинга, September 24 2026](https://announcements.bybit.com/en/article/bybit-to-delist-4-token-s-on-sep-24-2026--art1a1071a0dd4e/).

## Дополнительная ветка по прямому запросу пользователя: обратная связь рабочего бота

Добавлена 7 октября 2026 года. Пользователь попросил анализировать успехи и ошибки рабочего бота, включая убытки около 1% после комиссий. Эта ветка ведётся параллельно сбору исторических доказательств; она не объявляет этап 1 завершённым и не запускает новые архивные стратегии.

- [x] Прочитать реальные closed/live FIFO записи и сопоставить решения по точному order ID.
- [x] Объединять FIFO сегменты по ордеру продажи, не суммировать проценты и не считать пыль отдельной успешной сделкой.
- [x] Использовать `realized_pnl` как net после комиссий; не вычитать `fee_amount` повторно.
- [x] Разделить признаки, причины, комиссии, удержание, отсутствующий контекст и гипотезы.
- [x] Сохранять контекст каждого фактического ордера отдельным idempotency key; повторные hold/reject той же свечи не перезаписывают его.
- [x] Сохранять точные 7 ML-признаков на момент входа/выхода и observation конфликта entry/exit. Поздний replay незакрытой свечи не считается исходными признаками.
- [x] Регулярный readonly feedback timer каждые 30 минут; первый запуск successful.
- [x] Требовать свежий verified accounting/inventory snapshot для реальных training labels; исключать закрытия после его cutoff и не переносить зрелость позиции назад.
- [x] Сохранять датированный raw instrument response в контексте новых решений; не восстанавливать им прошлые правила.
- [x] Проверить raw instrument snapshots в обычных live decisions: 15 решений проверены на 2026-10-08 03:17 UTC, датированные raw lotSizeFilter присутствуют в hold contexts.
- [ ] Подтвердить наличие raw instrument snapshot в новом реальном order context после обновления исполнителя; проверочный ордер для этого не создаётся.
- [x] Калибровать cost floor новых моделей по prior-completed train-period сделкам + assumed slippage, без test/validation leakage. Недоступность feedback запрещает promotion нового кандидата.
- [x] Первые когорты по exact-order entry flags и устойчивость после удаления двух крупнейших outcomes. Когорты по режимам и полноценная независимая проверка ещё впереди.
- [ ] Накопить достаточно новых exact-context закрытий для обучения на реальных outcome, не смешивая их с независимыми архивными метками.
- [x] Выявить структурное ограничение maturity из-за dust; добавить отдельный экспериментальный cash-recovery target с явным списанием residual basis, а не объявлять partial position полной сделкой.
- [x] Подтвердить closing evidence и исходные признаки каждого примера по конкретному verified audit; свежего health flag недостаточно.
- [x] Хранить версии экспериментальных примеров по buy order и фактическому first-observed time; повторный сбор и исправления не увеличивают число покупок.
- [x] Зафиксировать протокол сбора/достаточной выборки и независимые будущие окна до первого fit cash-recovery модели; отделить legacy intrabar inputs от closed-only inputs. Frozen JSON + SHA-256, original entry/label knowledge time, embargo и readiness checker подключены.
- [x] Добавить pre-trade shadow prediction ledger, observed candidate freeze и проверку причинной связи с фактическим ордером; прогнозы не восстанавливаются после outcomes.
- [x] Подготовить sealed factual-cohort report: reward statistics скрыты до конца окна, simulated portfolio income не заявляется.
- [x] Реализовать изолированное ядро paper wallet: durable intents, later fresh quote execution, общий cash, base/quote fees, FIFO, остатки, консервативный mark и risk gates. Проверки на synthetic inputs; operational wallet не создавался.
- [x] Подготовить нормализацию публичного Spot orderbook/актуальных instrument limits, без fallback для неизвестных правил; live read-only smoke выполнен.
- [x] Связать prospective forecasts с durable paper intents, свежим рынком, выходами и отдельным wallet; activation/freeze gates и guarded installer реализованы. Проверки на synthetic data, текущий operational запуск заблокирован.
- [x] Подготовить paper dataset exporter и заранее зарегистрированные performance/acceptance gates; virtual/factual outcomes не смешиваются. Проверены на synthetic inputs.
- [ ] Проверить полный operational lifecycle на квалифицированном кандидате. Бумажный execution policy пока draft_execution_disabled; candidate отсутствует.
- [ ] Проверить strategy-specific exits, предотвращение churn и entry/exit conflict на независимых paper периодах. Hard stop/защита капитала не ослабляются.
- [ ] Допустить изменение рабочего поведения только после зафиксированной проверки; текущие гипотезы автоматически не меняют риск или торговые правила.

### Проверка недавних сделок, cutoff 2026-10-07 18:38 UTC (21:38 МСК)

**Эта первоначальная оценка частично отменена последующей сверкой конвертаций.** Итоговые денежные результаты и PONS attribution ниже не использовать как проверенные training labels; исправленные значения находятся в записи о reconciliation v2.

- В доступном 14-дневном закрытом execution-журнале 28 FIFO-сегментов, сгруппированных в 22 ордера продажи. Общий closed net PnL +0,77650 USDT не включает открытый PnL, депозит/выводы и весь аккаунт.
- Сегодня: 11 закрытых продаж, 9 убыточных / 2 прибыльных; net PnL −0,30433 USDT; reported fees 0,23212 USDT. Восемь продаж имеют взвешенное удержание ≤5 минут; их net PnL −0,18945 USDT.
- PONS объединённая продажа: −1,9506%, −0,112399 USDT. В ней два разных purchase lots; нельзя приписывать весь outcome только последнему входу. MET: −0,7697% и −0,6601%; MON −0,6276%; ONDO −0,3597% при неизменной цене; APT небольшой gross rise не покрыл fees.
- Положительные примеры: PUMP +0,6661% net сегодня; более ранний INIT +11,6439% по закрытой продаже. Несколько победителей сами по себе не доказывают качество всей стратегии.
- Сегодня median fee drag≈0,35927%: одни фактические комиссии уже выше старого assumption 0,30% total. Смена live-fee/порогов не выполнялась; новые кандидаты могут использовать train-only эмпирический fee floor + 0,10% assumed slippage.
- Решения сохранены только для 19 approve событий в доступном interval. Старый per-pair/per-candle upsert мог терять order context; это исправлено для будущих записей, утраченным признакам не присваиваются выдуманные значения.
- `live_feedback.py`, `analyze_live_feedback.py`, timer installer, training reader hook реализованы; отчёт `.local/state/live-feedback.json` (0600). Внешние сообщения/публикации не отправляются.
- Проверки: **332 passed**, отдельные тесты net fee accounting, lot grouping, exact order attribution, будущих outcomes, train-only cost cutoff, сохранения действующей модели при ошибке feedback и non-overwrite decision context.

### Продолжение execution feedback: память, когорты и реальные метки

- Добавлена SQLite-память `feedback_memory.py`: текущее состояние и версии исправлений, idempotent по pair/exit order/payload SHA. First observed time сохраняется; старое окно обучения не видит позднее исправление PnL. `.local/state/feedback-memory.sqlite` (0600).
- Exact-context стоимость покрывает ≈22,17% журнала. Закрытый net PnL без двух крупнейших outcomes = −0,42863 USDT против общего +0,77650. В emerging-momentum exact-context когорте всего 6 exit orders; её positive total также исчезает без двух крупнейших outcomes. Это диагностика, не достаточная выборка для live-rule changes.
- Реальные ордера теперь записываются с `resolution=ignore-duplicates`: повторное сохранение того же order ID не меняет первый контекст. Сохраняется `feature_observed_at` после чтения market snapshot, до отправки ордера, отдельно от времени последующего журналирования.
- Добавлены `live_experience.py` и `collect_live_experiences.py`. Цель отдельная: `spot-long-real-execution-net-v1`; только полностью закрытые собственные buy lots, собственные exits, известные fees/net PnL, исходный feature vector и feature time ≤ execution. Partial closes/dust/ручные сделки/утраченные признаки не превращаются в независимые training examples. Label available time — observed snapshot, не задним числом close time.
- Первый сбор: **0 пригодных примеров**; 19 buy-order групп ещё имеют остатки/partial state, 6 не имеют исходного полного feature context. Это факт ограничения данных, а не причина подставлять reconstructed features.
- Live feedback timer обновлён: после отчёта выполняет collection реальных примеров. Для обучения отдельного real-outcome кандидата сначала требуется достаточная новая зрелая выборка и независимая проверка. Пока работает fee calibration train-only; риск/входы/выходы не адаптируются автоматически по малой выборке.
- Основной исторический этап 1 сохранён; explicit source/event queue продолжается отдельно.

### Reconciliation v2: обнаруженная ошибка basis и реальные результаты

- Проверка wallet PONS выявила mismatch: старый FIFO lot 12.37768 отсутствовал в Unified. Обычная execution history не содержала продажи этого лота. Transaction log показал `CURRENCY_SELL` / paired `CURRENCY_BUY` в 2026-10-07 02:48 UTC.
- Отдельный официальный small-balance conversion history подтвердил quote, fromAmount, actual received USDT и fee для каждого subrecord. Это не эвристическая sale-price подстановка: synthetic **accounting events** создаются только при независимом совпадении quote ID, coin, amount, времени debit и actual USDT credit. Exchange orders не создаются. Не-USDT/неизвестные fee/tax currencies и unmodeled movements приводят к отказу достоверной публикации.
- В batch conversion комиссия ≈2% от gross exchange value; actual net proceeds уже учитывают её. For synthetic Sell gross=net+fee/tax, fee вычитается ровно один раз; entry base fee учтён через received quantity.
- `conversion_journal.py`, transaction-log и small-balance-history GET pagination добавлены. Cache хранит source transactions/conversion records; verified events участвуют в FIFO до последующих покупок/продаж. Старые ошибочные derived segments помечаются cancelled вместе с новыми rows **одним REST upsert transaction**, исходные payload сохранены в local `superseded_trade_rows`.
- Reconciliation smoke: **47 exchange executions + 12 conversion accounting events**, 38 closed segments, 9 open lots, unmatched=0, incomplete fees=0. Wallet PONS=0.07408 согласуется с новым lot remainder, не 12.45176 старого учёта.
- **Исправлено PONS:** старый lot conversion −2.9853% / −0.14818112 USDT; новая Spot sale −4.8779% / −0.28971894 USDT. Прежние −1.9506% по объединённой ложной FIFO-sale были ошибкой accounting и не являются доказанным trading outcome.
- Executor log подтверждает stop_loss=True, entry 0.4146, price stop 0.398016; фактическая market fill 0.3958. Gross threshold 4% не гарантирует net-loss 4%: цена могла уйти дальше до polling/исполнения, затем добавляются fees. Stop controls не ослаблялись.
- Corrected cutoff 2026-10-07 19:37 UTC (22:37 МСК): собственные exits 11 (2 wins/9 losses), net −0.481003 USDT; внешние conversions 12, net −1.641128 USDT; closed total today −2.122130 USDT. Это realized close-date PnL, не дневной equity return и не весь аккаунт. Existing daily guard считает equity, а не просто этот sum.
- Reporting и calibration разделяют собственные Spot orders и внешние conversions. Converter fees 2% не настраивают обычный fee floor bot orders. Dataset extraction исключает external exits из собственных execution target labels.
- Learning memory хранит corrected versions/observed timestamps и исключает snapshots без accounting_quality_verified. `LiveFeedbackReader` требует healthy accounting_version≥2 для fee calibration; ошибочный/непроверенный журнал не допускает promotion кандидата.
- Тесты conversion accounting, unknown proceeds/fee currency, stale FIFO segment supersession и unmodeled transfers прошли; реальный источник сверён и canonical rows исправлены. Полный набор после этих изменений: 344 passed (ещё один memory guard test добавлен позднее, результат следующего полного запуска записать отдельно).

### Датированный исторический universe без отбора по сегодняшним победителям

- Из January 2025 официальной таблицы взяты **527** USDT пар, опубликованных до study start. Для каждой запрошен только завершённый предыдущий UTC-день 2025-09-30 (24×1h): полнота, turnover, range и source SHA сохранены. Текущий instrument list и future returns не используются.
- Исторический protocol задаёт min previous turnover=1000000 USDT, min day range=1%, top20 по previous-day turnover. Допуск не означает прогноз прибыли. `historical-universe-20251001.json` фиксирует decision as-of=2025-10-01 UTC и source evidence. История вне pool ещё не считается полной.
- Выбраны BTC, ETH, SOL, MNT, XRP, APEX, ORDER, DOGE, SUI, AVAX, ONDO, ADA, ENA, BNB, CRV, STRK, SQD, LINK, LDO, ATH. Загрузка их 12m в отдельную DB `historical-universe-20251001.sqlite` продолжается; 840960 уже проверенных строк скопированы, без изменения frozen v1.
- Параллельный factual source review: строгие Spot sections/UTC times/table headers дают proposals; 26 token listing quote ambiguities дополнительно подтверждены historical category=spot candles около объявленного старта. Semantic duplicates сохраняют source provenance без двойного счёта.
- Fact ledger содержит **555** уникальных фактов из 104 sources (331 rule changes, 169 delistings, 45 listings, 10 observations), conflicts=0; remaining source ambiguities=22. Это observed partial history, не доказательство полного numeric baseline.
- Внешний archive.org CDX-запрос исторических trading-rule snapshots вернул **HTTP 429**. Не выполнялись агрессивные повторные запросы/обход ограничения. Исходные правила без доказательств остаются unknown; прочая работа продолжается.


### 8 октября: годовой исторический архив, воспроизводимость отбора и текущие сделки

- Завершён отдельный `historical-universe-20251001.sqlite`: **20 × 105120 = 2102400** закрытых 5m свечей за 2025-10-01—2026-10-01 UTC, все диапазоны valid, пропусков нет. Файл ≈163,47 MiB. Frozen research-v1 автоматически не расширялся.
- `verify_long_archive.py` теперь принимает database/output/reuse-report. Logical SHA совпадают с manifest; для каждой пары проверены 3 даты × 3 свечи напрямую по Bybit. Для 8 совпадающих архивов повторно использованы ранее сверенные SHA; для 12 новых выполнены новые запросы. Сохранены **7300** причинных дневных записей; отчёт `historical-universe-year-quality.json`.
- Manifest и progress разделены по имени базы, чтобы загрузки разных корзин не перезаписывали указатели друг друга. Старые content manifests сохранены.
- `universe_evidence.py` и `verify_historical_universe.py` проверяют SHA сырых ответов, дату исходного baseline, точные границы предыдущего UTC-дня, completeness, оборот, range, eligibility и порядок top20. Replay совпал. 524 ответа сверены; BOB/CTAN/TON имеют ошибки API `Not supported symbols` и явно исключены. Это ограничение покрытия, не доказательство отсутствия этих инструментов в прошлом.
- Bybit иногда возвращает старые бары делистнутой пары вопреки query bounds. Такие сохранённые ответы доказывают только исключение из complete-prior-day набора, никогда не допускают пару в корзину. Добавлены проверки подмены SHA/metrics, неверного as-of и недопуска старого ответа.
- Повторный live feedback на **2026-10-08 02:25 UTC / 05:25 МСК**: accounting quality verified, остатки согласованы с кошельком. Сегодня один собственный выход MINA/USDT, **−2,62064% / −0,157212 USDT** net; reported fees ≈0,3556% round-trip. Вход за ≈32,5 минуты до выхода имел emerging momentum, RSI 80,16 и сохранённый конфликт entry/exit; выход отмечен trend-down, stop_loss=False. Это наблюдение, не доказательство универсальной неэффективности momentum.
- Отчёт теперь отдельно агрегирует только собственные Spot exits с явно сохранённым конфликтом входа/выхода и формирует гипотезу для paper-сравнения conflict filter. Отсутствующие старые признаки не объявляются отсутствием конфликта. Live правила и hard stops не изменены.
- Real-outcome collection: **0** полностью зрелых примеров; исключены 12 внешних entry/exit, 4 без исходных признаков и 11 ещё не полностью закрытых позиций. Частичные продажи и dust не выдаются за полную outcome-метку.
- На момент этой записи reserved final period уже начался: **2026-10-08 00:00 UTC / 03:00 МСК**. Новые рабочие сделки можно диагностировать операционно, но их outcomes/настроенные по ним параметры нельзя использовать для подбора стратегии, претендующей на независимый результат frozen final test. Архив исследования заканчивается 2026-10-01. Модель, обученная с данными reserved периода, потребует нового будущего независимого окна.
- Временные проверки модели усилены: only closed prospective inputs, метка доступна после закрытия future candle, публикация датируется завершением обучения; future-dated registry records не выбираются. Перед promotion повторно сверяется champion; это локальный optimistic guard, не distributed atomic CAS.
- Проверки: полный набор **353 passed**; после добавления агрегата conflicts отдельно **15 passed** (live-feedback и universe-evidence). Этап 1 остаётся частично открытым: неизвестные прежние numeric instrument rules, динамический полный universe, 22 неоднозначных публикации. Переход к следующим стратегиям пока не отмечен выполненным.


### Подключение observation memory к фактическому trainer

- Выявлен разрыв: SQLite-память защищала delayed corrections, но CLI trainer использовал напрямую ретроспективные строки `LiveFeedbackReader`. Закрытие сделки до train cutoff само по себе не означает, что её исправленная комиссия уже была известна.
- Добавлен `ObservedFeedbackReader`, подключён в production training CLI. Для cost calibration используются только verified версии, у которых одновременно close/information time и фактический observed time не позже train boundary. Текущее accounting health остаётся обязательным; retrospective source outcomes не подмешиваются в память. Если памяти нет, комиссия не backfill-ится задним числом. Evidence policy сохраняется в training metadata.
- Целевые проверки: изменение fee после cutoff видно только в более позднем окне; отсутствие памяти не заменяется текущим журналом; unhealthy source запрещает calibration. **26 passed** (feedback + model training).
- В отчёте на 2026-10-08 02:29 UTC два собственных выхода с сохранённым entry/exit conflict (FIL, MINA), оба убыточные: суммарно **−0,172988 USDT**. Это малая диагностическая выборка; основание для prospective paper hypothesis, не для немедленного удаления сигналов или ослабления exits. Feedback service Result=success, ExecMainStatus=0.


### Продолжение factual review: точные Spot timestamps и scope

- Проверена ранее неоднозначная October 2025 tick-size таблица: формулировка `by 10AM UTC on Oct 17, 2025` задаёт документированный крайний срок применения. В реестр внесено 21 USDT tick adjustment с conservative effective time=10:00 UTC; более раннее фактическое изменение не выдумывается. Среди пар ORDER/USDT и ATH/USDT.
- Шесть quantity/min-order публикаций имеют только пары MNT/BTC/ETH/SOL/fiat в явных таблицах. Они исключены из USDT scope, без переноса правил на USDT пары. Любая USDT строка, даже malformed, оставляет numeric scope review открытым.
- Pair-specific listing lines CC/USDT и MET/USDT теперь отделены от более поздних USDC listing times. Не используются deposit/reward timestamps.
- KDA/TOMI ISO-date + AM format, numbered Spot/Convert/Deposit sections, VANRY timeline и early TIME Spot Trading section разобраны отдельно. Подтверждены 4 delisting timestamps, без подмены срока Spot датами Convert/withdrawals или прежним запланированным TIME delisting.
- BTC/BRZ и USDT/BRZ исключены как non-USDT quote; LBTC On-Chain Earn notice не используется как доказательство Spot delisting.
- Fact ledger теперь **582** уникальных факта из 111 sources: 352 rule changes, 173 delistings, 47 listings, 10 availability observations; numeric conflicts=0. Остались 7 явно pending sources плюс 4 market/body-unconfirmed исходных публикации. Прежние численные значения 555/576 выше — исторические checkpoints, не текущая итоговая полнота.
- Отсутствующие historic quantity steps/ticks и изменения автоматически регулируемых параметров остаются unknown. Число фактов не заменяет проверку полного покрытия правил. Этап 1 не закрыт, новая модель по этому расширенному архиву не допущена в live.

- Финальная проверка этого продолжения: **361 passed**, `git diff --check` без замечаний. Live feedback timer активен; торговые лимиты и hard stops не изменены.


### Следующее продолжение 8 октября: numeric coverage и достоверность real labels

- Все 7 remaining pending публикаций разобраны по captured body: 2 AED-only источника исключены из USDT scope; PORT3/USDT suspension сохранена как observation на publication time (2025-11-22 23:47:45 UTC), без выдуманного начала suspension; 4 max-size публикации сохранены отдельно как source-backed numeric coverage gaps. Исходные 4 market/body-unconfirmed страницы остаются без подтверждённых событий. `pending_sources=0` означает завершение triage, а не восстановление всех правил.
- Источник January 2025 дополнительно проверен по headers, дате в body и полному совпадению parsed cache с captured HTML. Извлечены minimum quantity и разные API/non-API minimum amounts для **527** USDT пар. Minimum quantity не объявляется quantity step. В реестре **1617** фактов: 869 rule changes, 527 availability observations, 173 delistings, 47 listings, 1 suspension observation; 112 sources, numeric conflicts=0.
- Новый `instrument_coverage.py` / `audit_historical_execution_rules.py` проверяет semantic SHA каждого факта и исходные content SHA, включая источники coverage gaps. Временные сегменты начинаются только после BOTH effective и announced time, чтобы позднее объявление не меняло прежнее знание.
- Для 20 исторически выбранных пар получены **28** metadata segments за 2025-10-01—2026-10-01. Last documented minimum quantity/API value имеются на всём диапазоне; last documented tick значения — на **20,2957%** суммарного symbol-time. Quantity steps и максимальные market quantities — **0%**. Это доля присутствия последних документированных чисел, не доказательство их непрерывной фактической действительности. `certified_execution_segments=0`, live_eligible=False. Отчёт `.local/state/historical-execution-coverage.json`.
- Документированная автоматическая регулировка максимальных размеров с 2026-03-20 и отдельные market/limit/post-only поля запрещают предположение о неизменном лимите или универсальном 5×. Даты без времени остаются day-only source limitations; отсутствующие числа не заполняются текущими ответами API.
- В production executor context добавлена сохранённая копия raw `/v5/market/instruments-info` с observation time после чтения и до ордера. Не добавлены запросы и новые правила входа/выхода. Исходный response сохраняет отдельные dynamic limits, tick и precision, включая отсутствующие поля; повторный first-order context не перезаписывается. Cross-pair stale snapshot исключён, metadata другого symbol приводит к отказу до ордера. Реальный новый order с этими полями ещё нужно проверить; unit проверки пройдены.
- Real experience builder теперь fail-closed при отсутствии accounting_quality_verified. Collector использует независимый inventory audit не старше **5 минут**, сохраняет отдельные audit cutoff / фактический label observed time. Будущий final partial close не может превратить более ранний partial outcome в fully-closed label. Остатки/dust по-прежнему не объявляются полной сделкой.
- Live feedback service повторно выполнен успешно. Snapshot **2026-10-08 03:12 UTC / 06:12 МСК**: 3 собственных closed exit orders, 2 profitable / 1 losing; realized net **−0,087916 USDT**, reported fees **0,064512 USDT**. Это close-date realized PnL, не дневная equity. Independent inventory consistent=True.
- Real-outcome dataset: **0** eligible examples; 12 external entry/exit, 5 missing original feature context, 12 positions not fully closed. Подтверждённый source cutoff и accounting quality записаны в dataset. Новые сделки reserved final period анализируются операционно, не используются для подбора frozen final research.
- Основной этап 1 остаётся открытым по численной полноте прежних rules и полному dynamic universe. Отдельные источники/probes/reconciliation/coverage проверки завершены; новые архивные стратегии и live promotion на их основании не запускались.

- Финальная проверка этого продолжения: **378 passed**, `git diff --check` без замечаний. Public instrument поля сверены с официальной документацией [Bybit Instruments Info](https://bybit-exchange.github.io/docs/v5/market/instrument). Успешно проверена запись snapshot в обычных live hold decisions без инициирования ордеров; actual-order snapshot ещё требует естественной новой сделки.


### Продолжение: структурный dust и отдельная экспериментальная цель

- Live read-only аудит показал 12 buy-order групп с closed portions и открытыми остатками. У 4 из них (FIL/MINA/PONS/CRV) сохранены исходные 7 features. Нулевая fully-closed выборка объясняется в том числе остатками: ждать само по себе недостаточно; остаток не исчезает без операции. Операции по его продаже/конверсии ради меток не создавались.
- Добавлены `cash_recovery.py`, `collect_cash_recovery.py`, `experience_memory.py`; target **spot-long-real-cash-recovery-dust-zero-v1**. Это отдельная цель, не `spot-long-real-execution-net-v1` и не fixed-future-return. Она измеряет фактический возврат денег относительно полной buy basis, считая остаток нулём. Не является total equity/PnL всего аккаунта и не гарантирует будущую стоимость остатка.
- Один buy order → один пример из всех закрытий. Formula: `cash_recovery_net = closed_net_pnl - residual_cost`; `full_cost = closed_cost + residual_cost`. Closed net уже содержит fees; второй раз они не вычитаются. Actual residual inventory/ledger сохраняются; списание существует только в экспериментальной метке.
- Допуск: точный исходный feature vector, observation до entry execution, собственные acquisitions/exits, known finite net/fees, closing times не после verified source cutoff. Residual basis ≤ **1%** полной стоимости — заранее заданный cap, без подбора по прибыльности. Остаток должен быть нулевым либо не подходить для market sell по свежему (≤5 минут) raw Spot precision/min-notional и quote observation. Материальные или market-sellable остатки исключаются, не размечаются как проигрыш.
- Public observations: до 20 пар, GET only, timeout 5s/retries0, wall budget 45s (завершающий запрос может добавить время до своего timeout). Missing/error observations исключают соответствующие позиции. Current parameters относятся к моменту оценки cash recovery, не восстанавливают прежние правила entry/exit.
- `bind_examples_to_audit` проверяет сумму closing basis/PnL, число сегментов, close time и original feature time/vector/input state по конкретным entry details verified отчёта. Late correction между audit и collection не проходит только по healthy flag. Позднее исправление требует нового audit. Коллектор полной цели получил ту же проверку.
- Первые **4** qualified экспериментальных примера на 2026-10-08 04:12 UTC / 07:12 МСК: FIL −0.025714204800 USDT; MINA −0.157784176000; PONS +0.032826151158; CRV −0.012846800000. Это cash recovery при residual=0, не замена уже опубликованного realized PnL. У CRV closed portion +0.016034624564, residual basis 0.028881424564; разница показывает недостаточный возврат полной вложенной суммы.
- Память сохраняет actual observation time, first seen не сдвигается при неизменном примере. Поздняя correction/reversion создаёт новую версию только с новым knowledge time. При чтении на cutoff выбирается одна доступная версия на buy order. Backdated observations запрещены; correction/reversion тесты прошли.
- Сохранён input candle state. Все 4 текущих примера — **legacy_asof_snapshot**, не closed-only; unknown не заменяется guessed state. Добавление контракта состояния стало отдельной новой observed version: **8 stored versions / 4 distinct buy orders**, а не 8 обучающих покупок. Разные версии нельзя считать независимыми примерами или разносить по train/test.
- Existing timer расширен third step: independent audit → fully-closed collection → experimental cash recovery collection, каждые 30 минут. Successful smoke: Result=success, ExecMainStatus=0; `.local/state/cash-recovery-dataset.json` и `.local/state/live-experience-memory.sqlite` (0600). Полная цель по-прежнему **0** eligible examples; экспериментальная — **4**, labels 1 positive / 3 negative.
- Эти 4 примера уже просмотрены как development data. Их нельзя превращать в независимый test или использовать для настройки frozen historical final period, начавшегося 2026-10-08 UTC. Cash-recovery кандидат потребует отдельного prospective validation/paper protocol и совместимого input contract. Fit/promotion/live policy updates не запускаются по четырём примерам. Торговые лимиты, stops и existing real PnL не изменены.

- Финальная проверка этого продолжения: **392 passed**, `git diff --check` без замечаний. Source binding, unknown/future/stale instrument observations, material residuals, partial-fill grouping, correction/reversion и input-contract tests пройдены.


### Продолжение: frozen live-learning protocol и автоматическая готовность

- Созданы `config/live-cash-recovery-protocol-v1.json` и отдельный `.sha256`, статус frozen_collection_only. Изменение файла без совпадающего checksum отвергается; смена параметров/окон требует нового явного protocol version, не silent rolling cutoff. Fit/promotion flags остаются false. Это отдельное исследование real cash recovery, не frozen historical final test.
- Primary input contract=legacy_asof_snapshot, feature_version=candle-v1, target=spot-long-real-cash-recovery-dust-zero-v1, residual cost cap=1%. Closed-only/unknown inputs не смешиваются с этой выборкой. Budget: 3 pure-python-logistic L2 configurations (0.001/0.01/0.1), один threshold 0.50; самостоятельный поиск стратегий/порогов в этом протоколе не включён.
- Freeze **2026-10-08 05:14:44 UTC / 08:14:44 МСК**. Train entries: 8 октября—5 ноября; validation: 5—19 ноября; sealed test: 19 ноября—17 декабря; future paper: 17 декабря—14 января 2027. Точные UTC start/end в конфигурации. Окна не сдвигаются при неудачном результате/недостатке данных. После недостаточного окна нужен новый заранее заданный будущий протокол, прежнее окно сохраняет свой статус.
- Между окнами используется embargo **24 часа**: validation/test/paper entries не раньше start+24h, label knowledge не позже end−24h. Entry assignment использует первый фактический execution timestamp, а не collector time или latest correction time. Collector начал сохранять этот timestamp; его появление стало новой версией metadata (**12 versions / 4 buy orders**), не четырьмя дополнительными сделками.
- Minimum train: **100** разных buy orders, **14** entry dates, **6** pairs, минимум 20 positive / 20 negative labels. Validation: **40** buys, 7 dates, 4 pairs, минимум 5/5 labels. Sealed test и paper: по **60** buys, 14 dates, 4 pairs; их reward/label distributions не используются в readiness. Максимальная доля одной пары 35%, одного entry day 25%. Пороги — preregistered coverage guards, не доказательство прибыльности/статистической независимости.
- Все уже просмотренные 4 покупки закреплены hashed development identity keys: training-only, любые поздние correction versions сохраняют тот же запрет на независимые validation/test/paper. Source dataset SHA зафиксирован как origin reference; файл этого обновляемого отчёта успел смениться, поэтому raw dataset не восстанавливался задним числом. Отдельно сохранён immutable **as-of memory** baseline на freeze time, с 4 совпадающими identity keys и своим checksum в `.local/state/live-protocol-snapshots/`.
- `live_learning_protocol.py` / `check_live_learning_readiness.py` выбирают отдельно snapshots памяти на допустимый cutoff каждого split. В одной выборке может быть только одна версия buy order; пересечение identity между split snapshots блокирует fit, даже если correction поменяла entry time. Неверный target/features/input contract или поздняя label availability исключаются. Test/Paper outcome counts не показываются; readiness этих окон определяется только coverage/quality metadata.
- Candidate paper evidence требует собственный paper execution mode + candidate artifact identity. Живые outcomes действующего бота в эти counts не проходят. `paper_harness_implemented=False`, `profitability_established=False`, live_promotion_allowed=False сохраняются независимо от числа примеров. Финальные performance/acceptance критерии ещё открыты.
- Readiness требует verified source binding и accounting, свежесть ≤45 минут, отсутствие truncation/observation errors/coverage omissions. Найден и закрыт пробел: свежий timestamp сам по себе не делал усечённый collector достоверным.
- Вместо первого 20-парного alphabetical cap теперь **2 bulk public Spot GET** (instruments/tickers) с timeout=5s/retries0: все необходимые pairs получают projected raw instrument/ticker evidence. Quote/instrument identities уникальны; missing pair/error не заменяется чужими параметрами. Helpers tested на 25 парах с ровно двумя запросами. Archive/profit claims на весь рынок по-прежнему не допускаются.
- Old campaign evidence за пределами текущего 14-day verified audit scope исключается как coverage limitation, а не вечная current-correction mismatch. Ранее проверенные as-of версии остаются в памяти. Collector спрашивает instrument observations только для текущих source-covered групп, которым действительно требуется dust proof; старые архивные/материальные/unverified позиции не расходуют эти запросы.
- Timer chain: independent audit → fully closed dataset → experimental cash dataset → **readiness report**, каждые 30 минут. Новый шаг читает только локальную память/конфигурацию; модель не обучает, ордеров/внешних сообщений не создаёт. Успешный запуск на **2026-10-08 05:33 UTC / 08:33 МСК**: Result=success, ExecMainStatus=0.
- Актуальный readiness: train **4/100** buys, 2 entry dates, 4 pairs, labels 1 positive / 3 negative; остальные окна 0. Dataset binding verified, public observations 4/4, errors=0. Fit gate false из-за coverage minima и неоконченных окон. До дальнейшего fit требуется новая достаточная выборка; четыре development outcomes не превращаются в независимый результат модели.

- Финальная проверка этого продолжения: **408 passed**, `git diff --check` без замечаний. Проверены checksum freeze, first-known cutoffs/embargo, запрет development identity в holdout, cross-fold corrections, разные input contracts, концентрация, скрытие test labels, отсутствие fake paper evidence, truncation/coverage freshness, 25-парный bulk сбор и aging старого audit scope.


### Продолжение: prospective shadow foundation до первой пригодной модели

- Добавлены `prospective_shadow.py`, `register_cash_shadow_candidate.py`, `report_cash_shadow.py`. Это pre-trade forecast/factual-cohort foundation, **не полный paper execution harness**. Нет симулированных fills, капитал/переинвестирование/новые контрфактические входы не моделируются. Acceptance/performance gates и full paper engine остаются открытыми.
- `SupabaseLiveExecutor` на уже разрешённом собственным алгоритмом Buy вызывает observer **до отправки order request**, затем связывает durable prediction с response order ID. Параметры основного алгоритма не меняются: cash forecast никогда не разрешает/запрещает реальную сделку. Observer errors отражаются в reasons и не мешают записи уже отправленного ордера. Выходы/stop controls не зависят от observer.
- Пока `.local/state/cash-shadow-candidate.json` отсутствует, observer inert: не создаёт prediction ledger и не делает дополнительных network requests. Нельзя score replay старых FIL/MINA/PONS/CRV задним числом.
- Candidate registration требует завершённых qualified train/validation по тому же frozen protocol. Model family, selected L2, feature/target/input contract, finite 7 coefficients/standardizer и information cutoff проверяются. Actual selection/registration должна произойти после validation end и до первого eligible test entry (test start+24h embargo). Trained/fit information timestamps не могут быть будущими или включать test data.
- Manifest и artifact SHA проверяются перед использованием. SQLite хранит observed actual registration и неизменный manifest payload; timestamp в вручную созданном файле сам по себе не считается preregistration. Один frozen candidate на protocol SHA: переключение даже между двумя заранее зарегистрированными вариантами после просмотра test outcomes запрещено. Orphan registration после file-write failure может восстановить только тот же manifest/неизменный artifact.
- Prediction payload неизменен по candidate SHA/opportunity. Seven features known before prediction, probability/threshold finite; actual observation clock ограничивает claimed timestamp (≤5s capture tolerance), чтобы нельзя было вставить прогноз прошлой недели через обычный API. Retry не меняет существующий прогноз.
- Factual order binding idempotent, один candidate не может присвоить два forecast rows одному buy. Response `orderLinkId` обязан совпасть с pre-recorded request opportunity для causal link proof. Это подтверждает forecast-before-request независимо от небольшого server/client clock skew; при отсутствии такого proof поздний local timestamp относительно actual entry исключается.
- Cohort report связывает forecasts только с доступными exact-feature cash outcomes actual buy orders. Missing binding/outcome/несовместимые inputs/поздние labels исключаются. Sealed test и paper reward statistics закрыты до window end. После окончания доступны суммы baseline factual cash recovery и фактических групп would-enter/would-reject, а не утверждение о доходе гипотетического портфеля. Unresolved factual buys помечаются отдельно; profitability/live promotion остаются false.
- Timer расширен пятым readonly report step. Smoke **2026-10-08 08:55 UTC / 11:55 МСК**: service Result=success, ExecMainStatus=0; status=waiting_for_qualified_frozen_candidate, predictions=0; candidate/ledger отсутствуют. Новый кандидат не обучался/не регистрировался, показатели будущей модели не выдуманы.
- За время сбора появилась одна новая пригодная покупка: сейчас cash dataset **5** distinct buys, 13 stored versions; readiness train=5/100, 2 entry dates, 5 pairs, labels 1 positive / 4 negative. Это данные разработки, не подтверждение роста доходности.
- Проверки: **421 passed**, `git diff --check` без замечаний. Проверены inert отсутствующий candidate, immutable forecasts/selection, запрет retrospective timestamps и protocol switching, duplicate order binding, hidden holdout rewards, factual-only PnL, causal order link при clock skew и сохранение обычной сделки при observer failure.


### Продолжение: изолированное ядро бумажного исполнения

- Добавлены `paper_wallet.py` и `paper_market.py`. Это wallet/execution kernel для будущего paper worker, не запущенная новая стратегия. Entry/exit intent dispatcher, автоматические exits, paper execution policy freeze и performance/acceptance gates ещё нужно подключить. `full_paper_execution_harness_implemented=False`, `paper_worker_connected=False`; текущий `.local/state/cash-paper-wallet.sqlite` не создавался.
- Общий виртуальный USDT cash, Spot-only inventory и FIFO в отдельной SQLite. BUY списывает gross quote cost и уменьшает received base quantity на entry fee; SELL добавляет quote proceeds после exit fee. Cost basis уже несёт приобретённую base fee — второй quote debit не создаётся. Entry fees в base и quote equivalent отмечены раздельно. Несколько выходов/последующий buy через старую пыль сохраняют старый FIFO basis.
- Входы задаются durable intents с actual enqueue time; fill только на quote, полученной позже actual enqueue + delay, а не по более ранней цене из cache. Draft defaults: delay=1s, expiry=30s, quote age≤10s, filter age≤300s. Expired signal отклоняется, поздний исторический signal не backfill-ится. Retry заполненного intent не меняет cash.
- Draft risk defaults: max6 positions, max daily loss2 USDT, min exit buffer4%, residual precision budget1%, участие не более1% displayed top-book depth. Capital/stake/entry fee/exit fee/slippage/cost-assumption ID caller задаёт явно. Это ещё не frozen paper-policy fee calibration и не утверждение о текущем тарифе аккаунта. Перед operational paper запуском потребуется зафиксировать policy и actual/assumed cost evidence.
- BUY проверяет общий cash, position cap, свежий equity risk mark, minimum notional, quantity precision, maximum market quantity, видимую ликвидность и способность пройти exit minimum при резерве stop. Нет margin/short/auto-top-up. SELL без owned inventory не создаёт отрицательную позицию; untradeable remainder сохраняется.
- Пыль не удаляется: она может освободить active slot только по свежим quote/filter и маленькому remaining basis. Gross bid mark хранится отдельно от conservative liquidation estimate после fees/slippage/step/minimum/depth. Для неселлабельного остатка liquidation value=0, а ownership/basis остаются. Missing/stale/неопределённая liquidation data дают equity=None и запрещают новые paper BUY.
- Daily equity guard использует UTC day anchor, фиксируемый до первого входа. Overnight gap не стирается новым baseline: переносится предыдущая valid equity, а при отсутствии mark — предыдущий anchor. Не выдается точный midnight equity, если его не наблюдали.
- Кандидат и вся paper policy неизменны для ledger. Реальная execution/training DB отвергается до создания paper tables; изменение capital не перезапускает баланс существующего теста. Decimal quantities/basis остаются точными; SQLite float casts не определяют наличие инвентаря. Older/same-time rewritten instrument observations не заменяют более свежие правила.
- Public adapter использует только HTTPS global Bybit production GET: instruments-info(category=spot,symbol) и orderbook(category=spot,symbol,limit=1). Требует Trading USDT identity, обе стороны book, positive displayed sizes, explicit basePrecision/minOrderAmt/maxMarketOrderQty и plausible server timestamps. Другие venues/markets/unknown limits не превращаются в дефолтные числа. Quote/raw book и filter source hashes сохраняются. Источник формата: [официальный Bybit Orderbook API](https://bybit-exchange.github.io/docs/v5/market/orderbook).
- Live read-only smoke BTC/USDT **2026-10-08 09:49 UTC / 12:49 МСК** подтвердил bid/ask sizes и три обязательных instrument fields; update ID58012781. Виртуальные/реальные ордера и wallet для этого не создавались. Top-of-book + adverse slippage — явно симуляционное допущение, не обещание реально достижимого fill.
- Проверки: **448 passed**, `git diff --check` без замечаний. Отдельно проверены delayed/no-backfill fills, fee accounting, cash sharing, idempotency/restart, stale/future/crossed/wrong-market data, expired signal, daily loss/overnight gap, retained dust/released slots, precision/liquidity gates, DB isolation, rule rewind rejection, FIFO old residuals, cash+basis reconciliation и отсутствие short inventory.
- Readiness остаётся **5/100** train purchases; cash candidate не обучен/не зарегистрирован. Установленное shadow-report отражает kernel capability, но полный paper execution harness и доходность не объявляет готовыми.


### Продолжение: бумажный обработчик и guarded activation

- Добавлены `paper_worker.py`, `paper_activation.py`, `run_cash_paper.py`, `freeze_cash_paper_policy.py`, `install_local_cash_paper.sh`, draft `config/paper-execution-policy-v1.json`. Операционный запуск остаётся disabled: нет qualified frozen candidate, policy status=draft_execution_disabled. Full paper lifecycle/export/acceptance не объявлены выполненными.
- Worker принимает только forecasts выбранного candidate SHA в заранее заданном paper interval. Would-reject/expired/future/unobserved forecasts не превращаются в BUY. Один source opportunity обрабатывается один раз; intent и source link/seen marker пишутся общей транзакцией через ATTACH двух isolated SQLite DB, чтобы crash не породил новую покупку.
- Original prediction deadline сохраняется отдельно от enqueue time: задержка в очереди не продлевает signal life. Исполнение происходит только на quote после actual enqueue+delay; pending SELL исполняются раньше BUY. Fresh mark нужен для новых входов; market errors/недостаток liquidation evidence не создают идеальных fills.
- Выходы: hard stop=4% gross от последней simulated buy price, hold limit=3600s, shared `exit_signal` (тот же модуль, что у working executor). Current public 5m history проверяется на полноту/gaps/future timestamps и контракт candle state. Stale quotes не ставят новый exit decision. Unsellable dust сохраняется, не создаёт бесконечные forced fills.
- Последние 24h paper interval — closeout/exit-only: новые paper BUY не принимаются, позиции выводятся через обычные validated exit intents, не через фиктивное end-window execution. Неисполненные/неликвидные остатки остаются в оценке качества теста.
- Draft policy: explicit simulation capital100/stake6, entry/exit fee0.0018/slip0.0005 как **непроверенный scenario**, 6 slots/day loss2, poll5s/new intents≤6/tick budget20s. Это не заявление о текущем тарифе или обещание fill. Live promotion disabled. Source scope — **baseline-approved buy opportunity stream**, включая намерения до broker result; не новый независимый поиск всех рыночных входов.
- Policy freeze требует существующего observed frozen candidate, explicit named cost scenario и actual registration до first eligible paper event. SQLite сохраняет immutable policy bytes/SHA/candidate/protocol/observed time; receipt timestamp в файле сам по себе не считается proof. Policy/Candidate/Artifact изменения блокируют activation; restart не разрешает новый набор exit/cost правил поверх прежних результатов. Interrupted policy file write восстанавливает только исходную зарегистрированную policy, не новые параметры.
- Activation checker проверяет protocol checksum, observed candidate freeze до eligible test, target/features/input/L2/coefficient compatibility, policy receipt через registry и matching stop/reserve. До paper start, после paper end или при missing/unfrozen policy не создаются wallet и market connections. CLI errors имеют nonzero exit; idle waiting — нормальный status.
- Installer preflight выполняется **до** записи user systemd units. Fast paper timer с flock и poll5s может быть подготовлен только при valid candidate/policy и ещё не закончившемся interval. Текущий smoke ожидаемо отвергнут: waiting_for_qualified_candidate; units/timer не устанавливались. Existing real executor/risk параметры не менялись.
- Live-compatible dry run `run_cash_paper.py`: waiting_for_qualified_candidate, network_requests=0, wallet_initialized=False. `.local/state/cash-paper-wallet.sqlite` и `cash-paper-worker.sqlite` отсутствуют; no imaginary PnL report. Полный exporter/acceptance criteria ещё впереди, full_paper_execution_harness_implemented=False.
- Dataset обновился естественной торговлей до **6/100** distinct training buys, 2 entry dates, 5 pairs, labels1 positive/5 negative. Недостаточная выборка не обходится fake scores/fit/promotion.
- Проверки: **461 passed**, `git diff --check` без замечаний. Доказаны queue→later quote sequence, original expiry, shared/max-hold/hard-stop exits, dedup/restart, source errors, runtime policy immutability, last-day closeout, missing candidate no IO, actual freeze/candidate checks, receipt forgery/change rejection и отсутствие uncontrolled systemd activation.


### Продолжение: экспорт бумажных результатов и критерии оценки

- [x] Read-only exporter для трёх отдельных wallet: кандидат, baseline control и кандидат с удвоенными fees/slippage. Все используют один поток возможностей; общий капитал внутри каждого сценария. Simulated outcomes никогда не становятся real training examples.
- [x] Сверка cash/basis/FIFO и целых покупок с частичными выходами и оставшейся пылью. Минутное сжатие equity сохраняет точные full-stream drawdown, неизвестные marks, gaps и SHA; качество не вычисляется только по сглаженным точкам.
- [x] Критерии зарегистрированы actual-clock receipt **2026-10-08 11:57:06 UTC** в отдельной immutable registry: минимум60 покупок/14 дней/4 пары, net return>0, profit factor≥1.2, drawdown≤5%, ограничения концентрации, полное наблюдение equity, без незакрытых существенных позиций и ошибок исполнения.
- [x] Paired comparison требует одинаковых source opportunities, правил исполнения и дней equity; фиксированный circular block bootstrap (2 дня, 2000 повторов, lower5% bound>0). Stress scenario исполняется отдельно с fees/slippage×2 и должен сохранить net return>0. Это критерии исследования, без автоматического live promotion.
- [x] Export/evaluation команды подключены к read-only feedback timer; установленный service прошёл Result=success, ExecMainStatus=0. До окончания paper window итоговые performance gates скрыты. Текущий smoke: три paper_not_started, sealed_until_paper_end, waiting_for_qualified_candidate; wallet не создан.
- [ ] Получить достаточные будущие train/validation данные и квалифицировать frozen candidate; провести настоящий operational paper interval. Полный lifecycle не объявлен выполненным, доходность не установлена.
- Проверки: **475 passed**; git diff --check. Рабочая торговая модель и её риски не изменены.


### Продолжение 9 октября: восстановление зарегистрированных критериев

- [x] Acceptance registry возвращает точные первоначальные bytes/SHA/observed_at без новой регистрации. Отсутствующая registry при чтении не создаётся.
- [x] Freeze command восстанавливает отсутствующие policy/receipt после прерванной записи; изменённые параметры и несовпадающий receipt отклоняются. Позднее восстановление не меняет первоначальную дату и не разрешает поздний выбор критериев.
- [x] Проверены missing-file recovery, exact bytes, сохранение clock, отказ смены параметров; полный набор **477 passed**, git diff --check.
- Read-only отчёт на 9 октября: train **8/100** покупок, 2 даты входа, 7 пар; 1 положительный и 7 отрицательных исходов. Недостаточно дней/покупок/обоих классов, окно train ещё не завершилось. Новая модель не обучена и не опубликована. Feedback service Result=success, ExecMainStatus=0.
- [ ] Полный operational paper lifecycle и остальные исторические coverage checks остаются открытыми; восстановление регистрации не считается доказательством доходности.


### Продолжение 9 октября: одинаковые данные выхода для paper-сценариев

- [x] Кандидат, baseline и stress используют общий краткоживущий exit observation для каждой пары в одном tick. Отдельные последовательные candle requests раньше могли дать разные exit decisions и сделать сравнение зависимым от очереди ролей.
- [x] Успешный сигнал и ошибка запроса одинаково переиспользуются только в пределах quote age; snapshot age отсчитывается до запроса. Медленный запрос не получает новый срок свежести, clock rewind вызывает повторное наблюдение. Reasons копируются, роли не могут изменить их друг для друга.
- [x] Проверены shared signal/failure, независимые пары, истечение срока, медленный fetch, clock rewind и mutable reasons. **480 passed**; git diff --check.
- Smoke run остаётся waiting_for_qualified_candidate, wallet_initialized=False. Реальная торговля, frozen acceptance thresholds и обучающая выборка не изменены.
- [ ] Проверить общий путь на будущих operational paper-сделках. Synthetic tests не закрывают независимое наблюдение доходности.


### Продолжение 9 октября: потери сигналов в очереди

- [x] Completeness gate теперь видит rejected intents с expired_signal/source_prediction_expired даже при source status=queued. Ранее такая задержка могла исчезнуть из проверки missing opportunities. Проверка применяется к candidate, baseline и stress, включая exact worker error count.
- [x] Экспорт сохраняет execution counts по side/status и rejection reasons. Обычные portfolio risk/cash/precision отказы учитываются как результат стратегии; потеря сигнала по задержке блокирует успешное доказательство.
- [x] Проверены оба expiry reasons во всех ролях, expected risk rejection, exact error count и worker→expired intent→export без выдуманного fill. Полный suite до последнего export regression: **487 passed**; targeted suite с ним: **24 passed**. git diff --check.
- Свежий verified журнал на 9 октября 13:38 UTC: SAND exit 8 октября имел gross estimate+0.0090178 USDT, fee0.021594770619, net−0.012576970619 (~−0.2096%). CHIP net+0.003365662968 (~+0.05615%). Это диагностические отдельные exits с возможными остатками, не независимый портфельный результат и не доказательство прибыльного фильтра.
- [ ] Независимая operational paper проверка остаётся открытой. Критерии frozen policy и live trading rules не менялись; исправлена реализация проверки полноты.


### Продолжение 9 октября: manual offline обучение на собственных покупках

- [x] Добавлен `cash_training.py` / `train_cash_candidate.py`: только квалифицированные train/validation snapshots из versioned real-execution memory. Общая readiness-фильтрация переиспользуется; поздние метки, embargo, input state, duplicate buys и concentration не обходятся.
- [x] Три разрешённых L2=0.001/0.01/0.1, один threshold0.50; train-only normalization, без refit на validation, без short head. Дополнительный фиксированный fit policy:100 epochs/lr0.08, selection=min validation log loss, Brier как диагностика. Все попытки сохраняются, настройки доступны в checksummed `config/cash-training-fit-policy-v1.json`. Протокол train/validation/test и criteria не менялись.
- [x] SHA eligible snapshots, buy identities, fit-information-end и policy входят в artifact. Регистрация требует исходный полный fit-report, matching protocol и eligible snapshots; произвольный artifact без происхождения не принимается.
- [x] Один fit-report на протокол публикуется атомарно и эксклюзивно; повторный запуск восстанавливает только исходный artifact без нового fit/доступа к текущим labels. Изменённый artifact/receipt отклоняется. Actual fit completion до deadline обязателен.
- [x] Текущий smoke отказал **до fitting**: completed qualified train/validation required. Training artifacts, registry candidate и real orders не создавались. Проверены train-only normalizer, budget, holdout rejection, late labels, unhealthy/unfinished data, label/net mismatch, provenance changes и recovery.
- [ ] Реальный qualified fit/validation selection ещё не выполнен: текущей выборки недостаточно. Log loss/Brier не считаются доказательством net прибыли; необходимы будущие sealed test и isolated paper.


### Продолжение: границы paper и net-схема архивных целей

- [x] Старые sealed-test forecasts и forecasts вне paper interval не попадают в paper seen opportunities. Future timestamp внутри paper остаётся quality failure. Проверены оба случая; silent skip shared exit из-за wall budget теперь сохраняет error event.
- [x] Исправлена численная цель trade labels: `TrainingExample.future_return` теперь равен net_pnl/cost, а не gross exit_price/entry_price−1. Binary label уже был net; прежняя несогласованность опасна для регрессии ожидаемой прибыли. Schema target повышен до **spot-long-trade-net-v2**; старые saved artifacts не переписывались и не публиковались.
- [x] Independent audit arithmetic проверяет численный net target; regression покрывает price gain с net loss после fees. Synthetic suite **498 passed**, git diff --check.
- [ ] Actual development archive re-audit для v2: команда audit_trade_labels отказала до archive access из-за resource reserve. На момент проверки MemAvailable≈1390MB при минимуме1536MB; disk≈3547MB при минимуме2048MB. Resource guard не ослаблялся. Проверка остаётся открытой, synthetic tests не заменяют её.
- [x] Manual cash fit CLI также применяет существующий memory/disk reserve перед fitting; восстановление уже готового artifact не запускает новое обучение.
- [ ] Qualified real cash fit, independent sealed test и operational paper остаются впереди; автоматического включения модели нет.


### Продолжение: почему пока8/100 и как исправления отзывают примеры

- [x] Collection coverage считает canonical собственные покупки по identity, отдельно от закрывающих сегментов и количества версий. Текущий verified refresh:33 observed buy orders,8 eligible,13 missing original features,12 external exits,0 unexplained omissions. Это доступные canonical rows, не полный exchange-wide census. Старые признаки не восстанавливаются задним числом; число100 не достигается дублированием выходов.
- [x] Необъяснённое исчезновение covered buy из collection теперь блокирует healthy readiness. Незавершённая покупка и покупка вне bounded audit coverage показываются отдельно; исключение не превращается в отрицательную метку.
- [x] Versioned withdrawals: подтверждённые изменения origin/fees/features/cost могут отозвать ранее пригодный пример при verified untruncated binding. Latest as-of reader его исключает; прежний cutoff продолжает видеть прежнюю версию. Reinstatement — новая actual observed version. Transient quote errors/absence of coverage не удаляют историю.
- [x] Candidate contract теперь требует exact feature order, matching artifact/manifest threshold и live_eligible=False на обоих уровнях; trained_at не может предшествовать fit_information_end. Это предотвращает применимость правильных весов к переставленным признакам.
- [ ] Qualified training всё ещё требует100 buys,14 дат,6 пар,≥20 исходов обоих классов и завершённого train/validation окна. В текущем snapshot8 buys/2 даты/7 пар/1 positive/7 negative. Архивное обучение — отдельный источник/target, его данные не дописываются как реальные100 покупок.


### Продолжение: архивная проверка v2, отдельные fees и журнал поиска

- [x] Отложенный net-v2 audit выполнен после восстановления MemAvailable>1536MB: BTC/ETH по1400 development candles (30 сентября–5 октября),2702 executed independent label candidates,40 stratified arithmetic checks. Final reserved period не читался. Это independent arithmetic, не human review и не доказательство прибыльности.
- [x] Archive `SimulationConfig` поддерживает entry_fee/exit_fee отдельно; None сохраняет legacy symmetric fee. Entry cost/quantity, exit proceeds, low/close equity marks и independent audit используют соответствующую сторону. Stress helper умножает обе effective fees и slippage; explicit overrides не остаются случайно без stress. Default сценарий и live account tariff не менялись.
- [x] Persistent `ResearchAttempts` регистрирует study/grid до evaluation, хранит completed/failed/reserved attempts и actual observed timestamps; results immutable. Повторный study восстанавливает результаты без повторной оценки конфигураций; новые данные — новый study с видимым reuse параметров. Unique parameter budget сохраняется на protocol/family и не повышается незаметно. Foreign execution DB отвергается.
- [ ] Реальная историческая комиссия/спред, volume/depth fills, universe/rules coverage и ручная проверка остаются незавершёнными. Раздельные fee параметры — возможность симулятора, не подтверждение чисел на каждой исторической дате.


### Контрольная точка продолжения

- Verified service после coverage/withdrawal изменений: Result=success, ExecMainStatus=0,8 eligible current examples,17 stored versions,0 current withdrawals,0 unexplained omissions. Fit artifact/candidate/paper wallet отсутствуют;8/100 не повышено искусственно.
- Реальный ledger smoke:18 completed attempts (6 на trend/breakout/reversion), failed/reserved0; повтор восстановил результаты. Best development validation net−0.230100744821435357250 USDT, stress−0.563613936201029899200 USDT,19 trades, no_qualified_candidate. Outer/final test не оценивался.
- Version→protocol SHA binding не разрешает изменить checksum/бюджет под прежним номером версии ради сброса счётчиков. Старые pre-ledger reports сохранены; не утверждается, что они были заранее зарегистрированы в новом ledger.
- Из текущих8 labels1 positive/7 negative; нужны ещё92 unique eligible buys и покрытие дат/классов, не только число100. Future train end5 ноября, validation end19 ноября2026 (границы UTC из protocol). Automatic fitting/promotion остаются запрещены.

- Финальная проверка этой контрольной точки: **518 passed**, git diff --check без замечаний. Новые gates/ledger поддерживают дальнейшие этапы; оставшиеся чеклисты не закрыты по synthetic tests или убыточному development search.


### Продолжение: полный budget identity и cash validation diagnostics

- [x] Persistent per-family budget учитывает параметры стратегии вместе с base execution config и implementation hashes. Новый dataset с прежними параметрами не расходует дополнительный configuration slot, но новый fee/execution/implementation contract расходует. Старые manifests без hashes остаются legacy_unrecorded, не получают выдуманную версию исходников.
- [x] Search manifest связывает результат с SHA source стратегии и симулятора; изменение кода создаёт новый study, старые cache results не выдаются за результаты новой реализации. Проверены cost changes, data-only reuse, legacy/new implementation distinction и rollback при превышении бюджета.
- [ ] Actual archive smoke новой hash-схемы: guard отказал до регистрации/evaluation из-за памяти. Существующие18 completed results не изменены, новых попыток в operational ledger не появилось.
- [x] Cash candidate validation diagnostics: constant train-positive-rate baseline (log loss/Brier), пять calibration bins и exact Decimal cash/cost sums по factual all/accepted/rejected cohorts при frozen threshold. Отдельно указано, что это не counterfactual portfolio performance; диагностика не меняет min-validation-log-loss selection и не читает holdout.
- [x] Regression показывает2 accepted buys, positive fraction0.5, но cash net−0.4 при win+0.1/loss−0.5. Число удачных сделок не подменяет величину денежных результатов.
- [ ] Qualified production fit ещё не выполнен; текущие8/100 и незавершённые будущие окна не обходились. Live policy и торговая модель не менялись.


### Продолжение: archived entry/exit conflict hypothesis

- [x] Opt-in `--entry-conflict-study`:36 fixed configurations,18 paired baseline/no_exit_conflict comparisons по тем же family/hold/stop/target. Фильтр вызывает shared exit_signal только на предыдущих≤120 завершённых свечах до signal index включительно. Последующие свечи не влияют на вход. Live входы/exits не изменены.
- [x] Runner/RSI dependency hashes входят в manifest вместе с strategy/simulator hashes; изменение imported indicator инвалидирует cached study и расходует effective budget. Regression проверяет invalidated cache, causal filter и paired grid без outer-test access.
- [x] Actual development BTC/ETH5000 run:36 candidates, no_qualified_candidate. Filter улучшил net во всех18 matched comparisons этого одного validation period; лучший filter reversion/hold48/stop1%/target2% дал12 trades, net−0.029904006821365467150 USDT, stress−0.238864948918382810400. Улучшение относительно худшего baseline не равно положительной доходности или независимой статистической устойчивости.
- [x] Эта гипотеза не считается совместимой с прежним historical reserved final: при формулировке использованы текущие live outcomes после его начала. В `.scope-note.json` timing явно after_development_evaluation, без backdated preregistration; следующие manifests помечают provenance/compatibility непосредственно. Нужен новый независимый будущий interval, до просмотра результатов которого гипотеза будет frozen.
- [ ] Не переносить фильтр в live и не расширять frozen cash candidate protocol по этому development результату. Cash train остаётся8/100; qualified fit ещё не выполнен.

- Контрольная проверка: **529 passed**, git diff --check. Profitability/live promotion остаются false; архивный conflict-study result не включён в реальные training examples.


### Продолжение: различать снижение активности и улучшение сделки

- [x] Development search сохраняет activity diagnostics обычного и stress portfolio: generated signals, executed trades, rejection reasons, positive/negative/zero trades, total fees, net per executed trade и net per generated signal, profit factor и fee-erased price gains.
- [x] Refused executions не считаются отрицательными сделками. No-trade sample имеет expectancy/profit factor=None и не выдаётся за прибыльный вариант. Несогласованное signal→trade/rejection accounting вызывает отказ, а не скрытую потерю возможностей.
- [x] Diagnostics source SHA также входит в study identity. Existing ledger results не редактируются; новые поля доступны для новых studies, а прежние outcomes сохраняются в исходном виде.
- [x] Actual development archive activity comparison выполнено; независимое подтверждение эффективности фильтра ещё открыто. Aggregate net improvement само по себе не различает меньшее число сделок и лучшую expectancy; promotion остаётся запрещённым.


- Actual activity smoke:36 candidates, no_qualified_candidate; persistent effective budget30/100 на каждое family. Общий net улучшен18/18 comparisons, net per executed trade12/18. Best reversion filter:40 generated signals,12 trades (2 positive/10 negative),28 already_open rejections,fees0.143325551143982617150 USDT,7 fee-erased price gains,net per trade−0.0024920005684471222625,profit factor0.80359. Stress net per trade−0.019905412409865234200. Это development diagnostics, не независимый profit claim.
- Проверки: **532 passed**, git diff --check; live changes/promotion не выполнялись. Archive activity task закрыт отдельно; независимый будущий test/paper и достаточная real cash sample остаются открытыми.


### Продолжение: устойчивость по монетам/дням и cash baseline

- [x] Portfolio diagnostics группируют trades/net/fees по pair и UTC entry day как атрибуцию единого wallet, без суммирования независимых subportfolio returns. Добавлены концентрация количества сделок, cash-only baseline (idle cash/no interest), excess net над ним и net без двух лучших сделок. При≤2 trades последний показатель=None.
- [x] Проверка conservation по pair/day, единый wallet, отрицательное excess net и removal двух лучших исполнений. Общий suite **533 passed**, git diff --check.
- [x] Short development window best: BTC net−0.11688462391130333325, ETH+0.086980617089937866100 USDT;1 из3 entry days positive, net без двух лучших−0.152253886174838333250. Нельзя выбрать ETH по этому viewed window и объявить результат независимым.
- [ ] Independent multi-period/walk-forward validation ещё не выполнена. Более длинный development replay той же fixed grid — проверка зависимости от выбранного окна, не новый final test или источник real cash labels.

- Long development replay выполнен на frozen BTC/ETH90-day snapshots:36 configs,63 trades у best reversion/no_exit_conflict hold48/stop2%/target4%,net−0.09855259636413597000 USDT,stress−1.22471492256676776000,drawdown bound≈0.784%. No qualified candidate, outer_test_evaluated=False. Проверка одинаковой grid на другом development window не подтверждает независимую прибыльность.


### Продолжение: temporal walk-forward, старшие свечи и ожидаемый net

- [x] `walk_forward.py`: calendar120/30/30 days,step30,7 nonoverlapping test windows на365 днях. Labels purged по actual availability с embargo; duplicate groups/future features отвергаются. Test payloads доступны только по explicit include_test после test_end, а selection — после завершения validation.
- [x] `walk_forward_selection.py`: immutable future selections в отдельной SQLite, actual observed registration между validation end и first eligible test; один artifact на protocol/test interval. Retry/recovery возвращает только original bytes; timezone aliases нормализуются UTC и не дают второй selection. Это kernel, не проведённый семиоконный независимый эксперимент.
- [x] `closed_timeframes.py`:15m/60m only complete closed5m buckets, UTC alignment,OHLCV aggregation без gap filling. Missing/partial buckets помечены; future data не меняют past features. В active model эти новые inputs не подключены.
- [x] Offline equity теперь stamped на candle close availability. Trade timestamps остаются bar-open identifiers с явно указанной intrabar uncertainty; PnL/fees/labels не изменены. Старые saved reports не переписывались.
- [x] `equity_blocks.py`: daily changes одного shared wallet со всеми монетами, полные UTC calendar blocks, fixed circular2-day bootstrap/2000 repetitions/seed20261009/95%two-sided interval. Missing equity days/irregular grid не заполняются; boundary partial days исключаются. Long validation replay дал12 полных дней, status=insufficient_calendar_days, интервал=None. Это development diagnostics, не независимое confidence evidence.
- [x] `net_regression.py`: experimental ridge predicts net magnitude, train-only standardizer, explicit supported net target, chronology/finite/duplicate checks. Gross targets/mixed evaluation targets отвергаются. Отдельный model_family/live_eligible=False не проходит frozen cash candidate admission. Mathematical minimum2 examples не считается qualification.
- [x] Separate frozen net research protocolsv1.0/v1.1:3 fixed ridge values0.001/0.01/0.1, selection=min validation RMSE; source dependency fingerprints исправлены вv1.1 без изменения grid/ranges/criterion, prior reports retained.2700 purged train/572 validation labels, best ridge0.001:MAE0.0024101361761332814/RMSE0.0032307450722227145 vs train-mean baseline0.0024908103237559504/0.0033397022083384636. Prediction errors не означают выполненную торговую прибыль.
- [x] `causal_features.py` воспроизводит exact candle-v1 features без future labels, включая cumulative EMA state. Prefix/batch совпадают, known availability=open+5min, current unfinished candle не используется. Snapshot metadata closed_only; legacy live/cash input contract не подменён.
- [x] Separate frozen net portfolio diagnosticv1.0/v1.1 (одна configuration):model chosen в net study и threshold0 зафиксированы, feature/runtime dependencies проверяются перед replay. Historical source/weights/cost/ranges сверяются, исходные reports retained. On viewed validation candidate/stress generated0/trades0/net0; all-bar baseline572 signals/48 trades/net−0.930131502564015 USDT. No income obtained; zero-trade sample не считается profitable qualification. Independent evidence/live promotion=False.
- [ ] Actual qualified future fold selections/test evaluation, independent walk-forward≥6 windows, verified historic execution rules, richer-feature model fitting и live/paper profitability остаются открытыми. New kernels не заменяют будущие данные или реальные100 покупок.


### Продолжение: gate проверяет численную корректность и размерности

- [x] `predict_probability`/standardize/dot больше не обрезают features/weights/means/stds через zip при несовпадении размеров. Finite inputs/positive std, finite bias/score проверяются; NaN/Inf/overflow не превращаются в probability или entry approval.
- [x] Executor проверяет long/optional short probabilities как finite values в[0,1]. ML gate отвергает prediction_error; корректные forecasts и configured shadow/off semantics не менялись. Exit/risk/stake параметры не изменены.
- [x] Проверены extra feature dimensions, NaN inputs/bias/probability, Inf coefficients, zero std и numeric overflow;39 targeted tests passed. Богатые будущие features нельзя молча подать в старый7-feature model.
- [ ] Prototype net head/portfolio protocols привязаны к прежним runtime SHA и после изменения inference guards требуют новой явной fitted-study version для нового replay. Existing reports сохранены как результаты прежнего кода; новые safety checks не выданы за новый profit experiment.


### Продолжение: рабочее переобучение, данные кэша и согласованный EMA

- [x] Actual readonly registry probe:нет fresh usable active artifact при36h. Последний completed training cycle не promoted (insufficient_signals,0 selected signals); accuracy≈majority baseline. Свежесть/порог не ослаблялись ради новых сделок.
- [x] `_load_examples` исключает data-quality failures по pair с явными причинами,не заполняет пропуски. Требуется≥80% requested sources и прежний min_examples. Network/auth/reader failures fatal. Artifact/publication pairs содержат только реально admitted pairs; diagnostics пишутся атомарно отдельно от model files. Один плохой ряд больше не уничтожает весь запуск,неполное покрытие не скрывается.
- [x] Readonly real-source probe:20 requested/18 admitted,coverage0.9,6786 examples;WLFI/PEPE gaps в глубине cache history. На последних40 candles толькоSpot,duplicates0:смешение markets не выдано за доказанную причину этих gaps. Getter всё равно явно scoped exchange=bybit/market_type=spot.
- [x] Training universe теперь отдельный `model-training-universe.json` для select→sync→fit, чтобы частый feeder не подменял live-universe между шагами. Installed model training unit обновлён только по путям; model criteria/risk settings не изменены, manual forced promotion не выполнялась.
- [x] New model config фиксирует exact feature window. CLI default120; bounded training features совпадают с corresponding inference window (включая EMA initialization). Legacy artifacts без нового поля сохраняют прежний путь; library/test default36 описан явно. Main и short-shadow используют общий input resolver,недостаток полной истории не обрезается молча.
- [x] Existing cache ingested_at читается как cache_observed_at. Значения,сохранённые до bar close,не становятся closed-only inputs просто из-за времени. Единый guard применяется training/live model inputs,causal snapshots и higher-timeframe aggregation. Actual Supabase GET ETH passed,observation times present; schema/DDL не менялись. Metadata не выдаётся за полный historical point-in-time archive certificate.
- [x] Проверить следующий обычный training cycle с новым source report/feature-window contract:accepted20/20,coverage1.0;candidate не promoted,0 signals,accuracy=majority baseline. Qualified profitability не заявляется.


### Продолжение: nonlinear head и causal contextual schema

- [x] `net_tree.py`:bounded deterministic net regression tree, depths2/3/4,minimum_leaf80,до9 train-only thresholds на feature. Chronology/duplicate/finite/net-target checks; family experimental/live_eligible=False. Separate frozen `net-tree-research-v1` заранее ограничивает3 configurations,selection=min validation RMSE; source/data/ranges сохранены в ledger.
- [x] Actual2700 train/572 validation labels:depth2 RMSE0.003430709992594846,depth3 0.003619069817516272,depth4 0.003652469095076883 vs constant baseline0.0033397022083384636. Все3 хуже baseline; углубление не считается улучшением,live не подключён.
- [x] `context_features.py`:separate experimental-market-context-v2 schema24 dimensions:base7,returns12/36,ATR14,realized volatility12,range/support/resistance positions,alignedBTCreturn/volatility/relative strength,past EMA/ATR regime,fixed UTC time cycles,closed hourly return/range. Unknown/misaligned BTC/hour context исключается,не заполняется нулями; old7-feature inference rejects wrong dimension.
- [x] Feature quality audit на development train1400 BTC/ETH candles:1364 snapshots×24 features,excluded0,no labels read/no models fitted. Future BTC/hour prices и streaming prefix не меняют past feature values. Actual new model fitting/independent validation на этом schema ещё не проводились.
- [x] Ordinary production training cycle completed after feature-window/source admission changes:20/20 sources,coverage1.0,train5180/validation1060/test1140;candidate20261009-558d791485,no promotion (insufficient_signals). Long accuracy0.73509 equalsmajority baseline; свежесть/threshold не ослаблялись. Следующий цикл использует separate frozen-run universe path.
- Контроль: **583 passed**,git diff --check. Active model replacement не выполнялась,реальные100-buy/independent future-test/paper требования остаются.


### Продолжение 10 октября: bounded contextual net study

- [x] `context_regression.py`:24-feature explicit schema,train-only standardizer,net target/availability/duplicate checks,separate experimental family/live_eligible=False. Seven-feature model не получает новые coordinates silently.
- [x] Separate frozen context-net-research-v1:2700 purged train/572 validation labels,3 fixed ridges0.001/0.01/0.1,selection=min validation RMSE. All attempts recorded;test/final не читались,thresholds/trading rules не менялись.
- [x] Actual selected ridge0.1:MAE0.0024810411070974713,RMSE0.003303102211235887 vs constant baselineMAE0.0024908103237559504/RMSE0.0033397022083384636. Лучше constant baseline,но хуже7-feature ridgeRMSE0.0032307450722227145; richer schema не объявляется улучшением дохода или моделью для live.
- [ ] Independent multi-window comparison,prospective freeze/test/paper и actual source contract qualification для нового schema остаются впереди. Current real-cash dataset не дополнен архивными examples и требования100 buys не ослаблены.

- Контрольная точка: **585 passed**,git diff --check. Cash real-buy count остаётся8/100;новые archive labels не засчитаны как реальные сделки. Производственная публикация не форсировалась,параметры капитала/stop/daily-loss/ML threshold не изменены.


### Продолжение 10 октября: целостность будущего выбора и contextual evaluation

- [x] Исправлено недостижимое chmod в FoldSelections: успешная запись реестра теперь устанавливает 0600; проверка прав включена в regression test. Фактический prospective fold не создан, календарные требования не закрыты.
- [x] ContextRegressor использует проверяемый dot: 23/25 weights и NaN отвергаются вместо молчаливого zip truncation. Несовместимый feature_version артефакта отвергается при прогнозе.
- [x] Net evaluation contextual model сверяет feature_version каждого example с моделью: одинаковые 24 dimensions не считаются доказательством одинаковой схемы.
- [x] Readonly systemd status: последний обычный training cycle завершён SUCCESS, 20/20 admitted, 0 signals, no promotion; новый цикл вручную не запускался.
- [ ] Изменённые contextual/net runtime SHA требуют явного нового протокола/fit перед новым replay; прежний эксперимент сохранён как результат прежнего кода. Новая прибыль из этих исправлений не заявляется.
- Контроль: полный набор 589 passed; 14 targeted passed, git diff --check. Real-cash readiness на 2026-10-09T21:02:59Z остаётся 8/100 (1 positive, 7 negative), train ready=False.


### Продолжение 10 октября: полезность вероятностей и доступность данных

- [x] Primary artifacts сохраняют long/short probability diagnostics по train/validation/test и монете: fixed-threshold signals/min/max/mean, log loss/Brier против constant train-rate baseline, пять fixed calibration bins. Baseline обучен только на train; diagnostic metrics не меняют L2 selection/threshold/promotion и не доказывают прибыль. CLI печатает краткие probability_quality строки. Старые artifacts не переписаны.
- [x] Empty purged train/validation/test не допускаются к primary fit: пустая validation больше не выбирает L2 по фиктивному zero loss. Chronological splits самостоятельно сортируют входные examples; learning rate/epochs проверяются.
- [x] Primary promotion требует одинакового timeframe/input state/feature calculation/window контракта кандидата и incumbent. Legacy artifact без подтверждённого bounded-window контракта не используется для некорректного comparison; candidate сохраняется, automatic replacement блокируется с явной причиной.
- [x] known_closed требует bar_close <= cache_observed_at <= as_of: поздняя запись не используется в более раннем snapshot. Historical archive без observation metadata сохраняет market-close convention; это не сертификат point-in-time cache history.
- [x] Cumulative EMA FeatureSnapshot сохраняет maximum observation time всей использованной истории. Higher-timeframe candles сохраняют время поздних base revisions. Context snapshot учитывает own/BTC/hour observation dependencies, hour/time-cycle selection остаётся по market close, а не по поздней загрузке.
- [x] Experimental contextual fit/evaluation и net portfolio entry signals исключают features, недоступные к историческому entry decision. Revision между entry и exit не считается допустимым прогнозом: модель не получает прибыль от входа раньше наблюдения.
- [ ] Следующий обычный primary cycle должен сохранить новые probability diagnostics; он не форсировался. Ранее сохранённый результат с 0 signals не реконструируется из изменившегося cache как точный original snapshot.
- [ ] Старые source-bound studies после runtime изменений требуют новой явной fitted-study version; прошлые reports сохранены, archive research не засчитан как real-cash buys. Independent future folds/test/paper и historical quantity/max-market certification остаются открытыми.


### Продолжение: риск архивной сделки и воспроизводимость зависимостей

- [x] TradeLabel получил отдельный outcome-only risk target spot-long-ohlc-excursion-bounds-v1: lower/upper price excursion и holding-time bounds. Net target v2/feature vectors/exit rules не изменены. Intrabar exit extremes после выхода не выдаются за наблюдавшийся path; opening timeout/gap не используют later high/low той же свечи. Это price bounds без fees, не portfolio drawdown и не будущие entry features.
- [x] Regression cases: ambiguous stop, opening timeout с экстремумами после выхода, gap-stop с поздним восстановлением, future outcomes не меняют entry features. Audit CLI проверяет availability, ordered bounds и version, сохраняет private report отдельно от предыдущего net audit.
- [x] Net study source manifest централизован: включены candle observation guards, causal snapshots, optional higher-timeframe/context, risk labels и net evaluation, а не только direct head/normalizer. Frozen net portfolio replay требует весь соответствующий source contract; старый неполный manifest не считается current-compatible.
- [ ] Actual BTC/ETH train-only risk audit на2000 candles/pair сейчас deferred: prepare_research отказал по минимальному resource budget до чтения архива. Floors не снижались; новый report не создан и audit success не заявляется.
- [ ] Риск-head fitting/qualification, human review≥20 cases, независимый future walk-forward/test/paper остаются открытыми. Bounds kernel не считается обученной риск-моделью или доказательством дохода.


### Продолжение: отклонённые кандидаты и дисбаланс классов

- [x] Primary promotion исключает период evaluation последнего rejected candidate, а не только incumbent. Новый evaluation_history_end переносит максимальную границу дальше даже при более узком последующем dataset; legacy cutoff fallback=publication. При смене candidate evidence между comparison и publication automatic promotion отменяется. Проверка history time не допускает будущую информацию в registry. Это защита последовательных ordinary cycles, не замена independent multi-window portfolio qualification.
- [x] Probability diagnostics включают noninterpolated Average Precision с grouped ties, natural prevalence reference и balanced accuracy. Пустой/одноклассовый набор не получает фиктивную PR area/balanced accuracy; no-signals precision=None. Selection/thresholds не меняются.
- [x] NaN/Inf/negative cost, неверные promotion counts/threshold, duplicate/nonfinite outcomes не проходят quality screen. Симулятор требует integer positive hold/delay/position counts: fractional/boolean/NaN не создают молчаливое no-fill simulation.
- [ ] Полное independent walk-forward подтверждение, реальная risk-head fitting и qualified replacement основной модели остаются открытыми. Ни новых сделок, ни forced model promotion эти изменения не выполняют.


### Продолжение: original primary inputs и numerical audit

- [x] Новые primary runs сохраняют exact purged train/validation/test vectors/labels/timestamps в content-addressed gzip snapshot с full SHA256, size/count checks и0600; source_kind=historical_candle_primary_examples, counts_as_real_executed_buys=False. Это не original fully closed real-cash dataset.
- [x] Actual calculation source copies + Python version/machine сохраняются отдельно в runtime bundle до fit; содержимое проверяется против fingerprint. Bundle не исполняется автоматически. Source changes during fit abort publication, сохраняя input evidence. Это provenance используемых calculation dependencies, не полный образ ОС/всех upstream services.
- [x] audit_primary_training.py пересчитывает train-only normalization, labels/availability/purge boundaries, both-head metrics и probability diagnostics из exact inputs без refit/GET-market/publication. Tests используют synthetic fixture; success там не выдан за real production audit.
- [x] Actual latest production artifact20261009-558d791485 audit отказал:original primary input snapshot unavailable;do not reconstruct cache. Old artifact не переписан, новый снимок из сегодняшнего cache не выдан за его исходные данные.
- [x] Main model artifact и input/runtime snapshots записываются атомарно с0600 и content-address checks. Interrupted install не оставляет partial model. JSON rejects NaN/Inf; snapshot decompression bounded128MiB.
- [x] Nonfinite derived features/returns исключаются на уровне pair до fit;80% source floor не ослаблен. Empty/ragged/nonfinite/overflowing normalization rows и invalid label horizon/fit counts не дают молчаливой модели.
- [ ] Следующий ordinary primary cycle должен подтвердить real input/runtime snapshots и numerical audit. До его scheduled run ничего не forced; baseline accuracy/candidate0signals остаются последним actual свидетельством.
- [ ] Actual archive risk audit всё ещё blocked resources (MemAvailable≈1137MiB при floor1536MiB); historical qty_step/max-market и26 listing quote-pair pending notices не закрыты. Captured notices не содержат достаточного evidence пары; USDT reward/fiat links не превращены в listing facts.


### Продолжение: модельная идентичность и реальный input contract

- [x] Primary model version включает means/stds/feature ordering/threshold/L2, а не только weights/metrics. Equal standardized fits с разной normalization не получают один ID. Recheck сравнивает version+full artifact SHA+run ID, чтобы republication под тем же version не подменяла evidence.
- [x] Future decision contexts сохраняют фактическое feature window и bounded calculation contract для raw/ML inputs. ML overrides без original contract не получают raw-window backfill. Cash/fully-closed collectors сохраняют эти сведения только при наличии в original context; old8 examples остаются без выдуманного window certificate.
- [x] Input-contract corrections создают новую observation version; as-of прошлый snapshot остаётся прежним. Новые protocols могут потребовать exact feature_input_contract; unknown/36-vs120 windows отвергаются. Cash candidate admission также сверяет declared contract. Frozen legacy protocol JSON/SHA не изменены.
- [x] Prospective prediction ledger сохраняет original input contract immutable; factual cohort comparison требует совпадения при его наличии. Это поддержка будущего строгого protocol, не создание qualified candidate.
- [x] Для input-contract mismatch создан отдельный prospective closed-only collection protocol (exact bounded window120), actual observed freeze и изолированный namespace. Legacy8 buys не перенесены в новый100-buy counter. Training/validation/test/paper qualification остаются открытыми; старый study сохранён.
- [ ] Нужен qualified primary candidate/отдельный prospective research путь; текущий last active stale и new candidate0signals не исправляются отключением ML gate или снижением thresholds ради sample count.


### Продолжение: новый closed-only real-cash study

- [x] config/live-cash-recovery-closed-protocol-v1.json, SHA3c879a8f965059ec5a0bd978eaca0c449cbdadc426d92359a2df3f207d9e136f. Actual freeze observed2026-10-09T21:59:16.428987Z; frozen_at2026-10-09T21:59:16.427796Z. Closed-only/bounded120, original minima100/14days/6pairs/20positive/20negative, threshold0.50/3L2/cost-residual1%/24h embargo unchanged.
- [x] Future train ends2026-11-06T21:59:16.427796Z;validation endsNov20,test endsDec18,paper endsJan15 2027. Known8 buy hashes training-only anchors; current compatible count0/100. Legacy study remains8/100,1positive7negative. Counts are not merged.
- [x] CashStudyPaths assigns one canonical namespace per protocol SHA, including copied file aliases. New protocol has observed freeze registry; fake/backdated/unobserved protocols cannot fit/register. One version cannot be replaced by another payload, original receipt recovers original freeze time. No retrospective registration inferred from a hand-written timestamp.
- [x] Readiness/manual fit/registration/shadow report support explicit --protocol; legacy paths remain canonical for original SHA. New input-sensitive artifacts, fit markers and prediction ledgers are isolated. Protocol contents changing during fit/registration abort publication.
- [x] Installed readonly feedback unit and installer update both readiness/shadow reports. Reload only, no forced service start; no candidate training/paper timer created. New diagnostic observer selected through CRYPTOFORGE_CASH_SHADOW_PROTOCOL; absent candidate verified inert/no prediction DB created. Configuration errors surface during before-buy diagnostics and do not disable executor construction/exits.
- [ ] Real source contract capture on an eligible new buy,100 qualified closed-only buys, completed future validation/fit/shadow and independently frozen closed-study paper policy/acceptance remain open. Legacy paper policy is not valid evidence for this new protocol.
- [x] Original closed-study protocol/SHA/initial-memory snapshot/observed receipt и SQLite registry скопированы в private original-freeze-backup; hashes и чтение backup receipt проверены. First receipt predates optional embedded-snapshot recovery support: missing original file restores from backup, not current memory. New future freezes embed initial snapshot for exact crash recovery.


### Продолжение: упущенные возможности без фиктивных покупок

- [x] reject_entry сохраняет exact original feature vector/window/state/bar timestamp и full long probability/model version/artifact SHA, если реальный ML forecast был рассчитан. Ошибки features остаются диагностикой; missing model не получает выдуманную probability.
- [x] Rejected snapshots имеют отдельный idempotency namespace и ignore-duplicates: first snapshot per bar/model/input-contract не заменяется более поздней внутрисвечной картиной. Новый model/input-bar/window получает отдельный snapshot. Это ограниченная representative opportunity sampling, не полная tick history.
- [x] opportunity_only=True; cash/fully-closed collectors по-прежнему принимают только approve_entry, matched order и проверенные реальные executions. Rejected cases не увеличивают счётчик100 buys и не становятся negative labels автоматически.
- [ ] Post-outcome missed-opportunity analysis/independent paper replay нужны отдельно: будущая цена сама по себе не доказывает, что реальная сделка могла быть исполнена с прибылью.

- Контрольная точка текущего продолжения: **652 passed**, git diff --check, installer bash syntax checked; closed diagnostic observer verified inert, no candidate/prediction DB/training/paper created. Legacy8/100 and closed0/100 preserved separately.


### Продолжение: свежесть именно обучающих свечей

- [x] Primary source admission требует последнюю known-closed свечу не старше15 минут относительно actual fit snapshot. Непрерывная, но старая история не выдаётся за fresh20/20 coverage; stale pair исключается с причиной и last_closed_at_by_pair.80% coverage floor сохранён.
- [x] Registry оценивает возраст evaluation_information_end вместе с trained_at/publication, если граница сохранена. Повторное обучение/публикация старого рынка не делает его current model data.
- [x] Synthetic test clocks приведены к fake market history; проверка fee calibration cutoff/feedback failure по-прежнему действует. Для намеренно старой history test проверяет no model/publication.
- Контроль: **660 passed**, git diff --check. Ordinary readonly feedback cycle01:03MSK completed SUCCESS:legacy8/100,17versions,0withdrawals;closed0/100,exact contract matches. Paper still not started/acceptance sealed. Research audit deferred at MemAvailable≈1284MiB<1536MiB;free disk≈3661MiB, floors unchanged.


### Продолжение: actual primary cycle и forecast-only feedback

- [x] Ordinary07:41MSK run completed SUCCESS,20/20 sources/coverage1.0,original train5180/validation1060/test1140 gzip snapshot and runtime bundle present. Candidate20261010-b72a864519 has25 long test signals,precision0.4; log loss0.5727536225483906 vs constant0.5873574053141271,Brier0.19187936970754407 vs0.19770203971789013. Calibration improved relative to that baseline,not portfolio income. No promotion (feature contract mismatch).
- [x] Numerical audit verifies original inputs/normalization/both-head metrics from actual snapshot. Current-source difference is explicit; archived code was not executed and exact historical runtime identity is not falsely claimed. Default audit still requires source match,optional numerical-only mode reports drift.
- [x] Price-target signal diagnostics:25 signals mean gross return−0.008007367380602063,minus assumed cost−0.012605578149593613;10/25 positive target. Conservative prior-local-attempt cutoff00:35UTC gave22 signals/900 rows,mean-minus-cost−0.011458132461979105. Prior local cutoff is not claimed as exact registry reference. No source test-based fitting/threshold tuning.
- [x] Concentration/drift diagnostics:CAP18/25 signals,15 outside train feature support;largest price-target loss−10.287857287654571% at predicted probability0.78070. BAT4/STRK2 also negative average estimates; MINA1 positive is insufficient qualification. This is observed price-target behavior,not actual trade loss or justification for a live blacklist.
- [x] New primary artifacts store train-only feature min/max/normalization support. Prospective candidate forecasts annotate outside-training features/max standardized magnitude without clipping or changing entry gates. Older artifacts derive support only from validated original train snapshot; missing data stays unknown.
- [x] Forecast memory records prospective exact long/short/input/state/contract/model SHA/baseline signal before future endpoint,first model/bar snapshot immutable. UTC aliases don't duplicate samples; stale/already historical targets fail. Cache and disk limits256MiB/2048MiB reserve protect runtime; errors don't change buy gate.
- [x] Installed separate readonly primary-forecast-outcomes timer:400 forecasts/20 pairs/20s budget,30min intervals,45s systemd timeout/256MiB cap/flock. Actual first run SUCCESS:50 forecast rows,18 outcome versions;follow-up retained18 and added2,2 endpoints still not known closed. Missing/partial endpoints aren't negative labels; each forecast has exact counted outcome status.
- [x] Matured future candle labels are versioned by actual observation,late revisions don't backfill old as-of views. Old forecasts without original label/cost policy retain price-only outcomes,label=None/cost-estimate=None. These are primary_future_candle_return_diagnostic_v1,not executed cash,trade fills or paper PnL; real-buy counts remain separate.
- [ ] Independent prospective primary contract migration/bootstrap and portfolio paper comparison remain open. Forecast-only learning feedback does not authorize replacing stale incumbent,lowering gates or satisfying100 real buys with predictions.


### Продолжение: зрелые primary forecasts и original policy provenance

- [x] Primary forecast price collector/report работают в отдельном readonly timer,не затрагивая cash readiness. Streaming/as-of reader берёт последнюю outcome version,известную к cutoff; отчёт ограничен10000 endpoints и сообщает truncation. Classified price metrics и baseline-entry-signal cohort разделены; shared capital/actual fills не заявляются.
- [x] Existing forecast-only rows без label policy не получают implicit zero fee/zero threshold. Если original artifact найден и full SHA/family/feature/target/timeframe/horizon совпадают, его original cost/label policy может дополнить новую outcome version observed-now. Old as-of price-only records сохраняют label=None. Missing/changed original artifact оставляет policy unknown.
- [x] Per-forecast endpoint errors не исключают остальные valid rows этой пары; counts sum точно selected forecast count. Partial cached bars выводятся отдельной причиной,не отрицательным outcome. Actual next run:20 preserved+2 newly available,2 pending partial; later47 endpoints classified through original artifact provenance.
- [x] Actual47 observed endpoints,6 positive price targets,3 probability>=.5 signals with0 positive estimates,mean price return minus assumed cost−0.01252710012758091012495265217. Baseline entry signal was true on2 endpoints and on0 of those3 ML signals. No real transactions/cash rows added. Small single-day exploratory diagnostics,not independent income evidence.
- [ ] Independent primary bootstrap/contract transition and prospective portfolio trials remain required. Neither current drift diagnostics nor few future candle labels justify a ticker blacklist,threshold change or replacing the working model.


### Продолжение: неблагоприятное исполнение и цена немедленного стопа

- [x] Исправлен offline entry-stop edge case: при adverse entry fill stop выше фактического market open немедленный выход использует доступный open,а не более выгодную неисполняемую stop price. Default .05% slippage/2% stop behavior не менялось. Independent arithmetic audit использует тот же causal timing,но отдельный расчёт.
- [x] Regression scenario entry103/current market100/3% exit slippage получает exit97 в той же свече,stop_gap. Risk-label opening-exit bounds не используют subsequent high/low.
- [ ] Это исправление крайних stress assumptions не доказывает реальное исполнение/доход. Existing source-bound study results остаются результатами прежнего кода; новый replay требует новой явной study version и resource readiness.


### Продолжение: forward archive of actual Spot instrument observations

- [x] instrument_observation_memory stores public parsed-response canonical SHA, actual request/response/observation clocks, compressed original JSON and immutable receipt. Unique symbols/category/retCode checks. Earlier as-of query never sees future capture; old observation expires, missing symbol does not prove delisting.
- [x] Actual2026-10-10T06:31:20.086780Z capture:528 Spot symbols,nextPageCursor absent. Current numeric filters retained as observed; historical effective dates/change times not inferred. This does not retroactively fill2025 quantity/max-market gaps.
- [x] Separate readonly public instrument observation timer every30min,flock/30s timeout/128MiB cap/2048MiB disk reserve. No account keys/orders/fits. Observations between captures are not certified unchanged,can_certify_historical_execution=False.
- [ ] Exhaustive historical rule revisions,old market quantity baselines and exact historical execution certification remain open; forward collection can support later studies without inventing old rules.


### Продолжение: 1m ambiguity audit component

- [x] intrabar_audit validates complete closed1m path against coarse5m OHLC,market identity and actual observation availability. Ordered target-before-later-stop can be identified; missing minutes/mismatched prices/same-minute dual touch preserve adverse unresolved stop. Cached partial duplicates are excluded from both aggregation and barrier traversal.
- [x] Component returns explicit audit-only/no-real-fill-certification flags and actual information availability. Existing simulation/target labels/policies remain5m adverse assumptions; no new profitable result is inferred.
- [ ] Captured/checksummed historical1m dataset and actual manual/data audit are still required before a separate preregistered1m execution study. Kernel unit cases do not close full historical ambiguity handling or execution certification.


### Продолжение: paper namespace нового closed study

- [x] CashStudyPaths выделяет отдельные execution/acceptance policies,registries,three-role wallets/workers/results для full protocol SHA; копии одного protocol остаются одним namespace. Legacy filenames/receipts не переписаны.
- [x] New study disabled execution draft prepared. Separate acceptance criteria observed2026-10-10T06:40:07.576905Z before any new-study paper results; original60buys/14days/4pairs/positive net/PF1.2/DD5%/stress×2/paired-block evidence thresholds preserved. This is preregistration,not a passed paper result.
- [x] freeze/run/export/evaluate paper commands support --protocol. Actual new-study run iswaiting_for_qualified_candidate,wallet_initialized=False;export allrolespaper_not_started;acceptance sealed_until_paper_end/passFalse.
- [x] Separate installer uses protocol-SHA unit/lock names. Actual install attempt refused before writing units because candidate absent; no new-study paper service or wallet created.
- [ ] Qualified candidate,observed named execution-cost scenario,actual prospective paper stream and paper acceptance remain open. Shared legacy policy cannot qualify the new study.


### Контрольная точка09:44MSK: новый ordinary fit воспроизводится точно

- [x] Actual09:40MSK candidate20261010-256a347fd2 completed SUCCESS,20pairs,train5179/validation1060/test1142. Original inputs/runtime/train support captured; strict current-source numerical audit passedexact_primary_inputs_and_metrics_verified,current_source_matches=True.
- [x] Promotion now stores exact incumbent/candidate SHA+run IDs and prior consumed evaluation cutoff. Novel subset after04:40UTC has382 examples/4 signals;mean fixed-candle return minus assumed cost−0.02188361338725924,accuracy0.7120418848167539 vsmajority0.7225130890052356. Not promoted,insufficient_signals; separate feature-contract mismatch remains. Total25 test signals are not25 new independent observations.
- [x] Current test probability loss0.5611550925921962 vsconstant0.590072098081599,Brier0.18781002308516317 vs0.1977004247849548; this improved probability diagnostics but did not establish positive signal payoff or portfolio income.
- Контроль:**688 passed**,git diff --check. RAM≈1092MiB remains below1536MiB offline floor; no forced archive experiment/primary publication/real orders.

- Финальная контрольная точка этого блока: **688 passed**; additional primary audit/namespace/paper activation checks passed, all new installer shell syntax checked,git diff --check clean. Qualified live replacement/profitability remain unconfirmed;legacy8 real buys/newclosed0 real buys,price forecasts are not added to either counter.


### Продолжение: source-bound strategy hypothesis descriptions

- [x] Catalog содержитtrend(SMA8/24+return3+volume),breakout(previous20-high+volume),reversion(RSI14+recovery+volume),с exact declared sensitivities и expected failure modes. Source SHA binds descriptions to actual code; silent strategy edits require catalog review. No financial advantage claimed.
- [x] Future validation search manifest records catalog SHA. Prior reports aren't recast as preregistered; new effective source/runtime context consumes persistent family budget. No archive experiment launched while resource floor fails.
- [ ] Genuine profitable candidates,independent closed-final performance and support/compression/ATR extensions remain open. An understandable hypothesis is not qualification.

### Продолжение: полнота соседних параметров и регулярные paper reports

- [x] Development neighborhood diagnostics сообщает expected/tested/missing соседние configurations и neighborhood_complete. При пропущенном соседе либо единственном испытанном наборе isolated_positive_peak не подтверждается. Selection и thresholds не изменяются; positive neighbors не доказывают независимую прибыльность.
- [x] Installer и действующий readonly feedback service дополнены отдельными export/evaluate для closed study namespace. Unit reload выполнен без принудительного запуска collector или paper worker. Ручная проверка export: все три роли paper_not_started; acceptance sealed_until_paper_end, paper_evidence_pass=False, live_promotion_allowed=False.
- [x] Полный набор проверок: **694 passed**; installer bash syntax и git diff --check прошли.
- [ ] Проверка устойчивости на фактической полной сетке нового зарегистрированного исследования, независимая прибыль и квалифицированный кандидат остаются открытыми. Старые результаты не переоценены новым кодом.
- [x] Neighborhood coordinates сравниваются как Decimal: .01/0.010 не создают два разных варианта. Повторные configurations и nonfinite barriers отвергаются, чтобы дубликаты не завышали число проверенных соседей; шесть focused regression cases прошли.
- Последняя полная проверка после Decimal/duplicate guards: **696 passed**, git diff --check clean. Незавершённые этапы сохраняют [ ]; результаты price forecasts не подменяют реальные покупки и paper acceptance.

### Продолжение: prospective errors by pair and training support

- [x] Primary forecast quality report содержит signal cohorts по монете и within/outside/unknown training support. Missing/error drift diagnostics остаются unknown, а не считаются нормальным входом. Все cohort numbers exploratory, без model selection, cash-training rows или live promotion.
- [x] Actual snapshot2026-10-10T09:23:03Z:545 endpoints across three models. 256a model:326 endpoints/5 threshold signals, все CAP, mean price return minus assumed cost−0.01458915594;81051:90 endpoints/3signals, mean−0.01528029498;b72a:129 endpoints/9signals, всеMINA,mean−0.00289656155. Данные одного дня, не исполненные сделки и не independent profitability.
- [x] Полная проверка697 passed; subsequent unknown-drift correction checked focused report tests. Отдельные хорошие наблюдения не превращаются автоматически в разрешённую стратегию/blacklist.
- [ ] Независимые будущие когорты, исполненный portfolio payoff и квалификация сохраняются открытыми.

### Продолжение: baseline opportunities и независимая арифметика риска

- [x] Primary report теперь сравнивает все наблюдавшиеся baseline-entry opportunities с фиксированными группами probability≥0.5 и <0.5. Раньше baseline cohort был виден только при высоком ML probability. Current price endpoints не объявляются фактическим решением gate, missed trade income или causal portfolio benefit.
- [x] Snapshot09:25UTC:256a baseline15/6positive/mean−0.00085017;81051 baseline6/4positive/mean+0.01003043;b72a baseline5/2positive/mean+0.00108554. Все эти observed baseline opportunities имеют probability<0.5. Это исследовательский сигнал для будущего исследования false negatives, не основание менять threshold.
- [x] Latest ordinary candidate81051 original input/runtime audit прошёл strict exact_primary_inputs_and_metrics_verified,source_matches=True;train4921/validation1007/test1083. Никакого refit/publication.
- [x] После восстановления RAM≈2357MiB и disk≈3078MiB выполнен ограниченный development-only risk-label audit:BTC/ETH по1400bars и20 sampled labels; independently recomputed actual adverse/favorable bounds и holding duration. Numeric audit passed; никаких final candles, strategy search или реальных заказов.
- [x] Audit report явно помечает overlapping independent labels,counts_as_real_executed_buys=False,portfolio_profitability_established=False. Fault-injection tests отвергают ordered-but-wrong risk bounds и plausible-but-wrong duration.
- [ ] Human review, покрытие реальных target/ambiguous cases и независимое portfolio qualification остаются открытыми. В этом архивном срезе predominately timeout, поэтому арифметический pass не закрывает весь audit checklist.

### Продолжение: целостность mutable diagnostic reports

- [x] Readiness/shadow/paper-export/paper-acceptance/archive-label audit reports сериализуются до изменения destination, запрещают NaN/Infinity, пишут private temp0600+fsync и атомарно заменяют destination. Ошибка сериализации/replace сохраняет прежний полный отчёт и очищает temporary file.
- [x] Fault-injection tests проверяют сохранение previous report при invalid numeric payload и failed filesystem replace. Actual closed-study readiness/export/acceptance commands прошли:0 real qualifying buys,data_ready=False,all roles paper_not_started,acceptance sealed/passFalse.
- [ ] Надёжная запись отчёта не меняет требования к данным, не запускает paper worker и не доказывает прибыль.

### Продолжение: chronological intrabar audit

- [x] Минутный path сортируется по open_time до first-barrier traversal. Reversed complete input теперь даёт тот же target-before-stop, а не ошибочный stop из поздней минуты.
- [x] Coarse5m candle обязана быть known_closed at as_of; поздняя cache revision не видна ранее actual observation. Information availability учитывает обе coarse/fine observations.
- [x] Six intrabar regression cases passed, включая reversed minute order и late coarse revision. Компонент остаётся audit-only, без изменения торгового simulator/entry policy.
- [x] Actual small public Bybit1m capture2026-10-10T09:28:52Z:BTC2026-10-01T00:00..01:00UTC,60 complete minutes, immutable snapshot SHA fce1f36a4ce9cecd92897453365332e2cb9e31d04be9cb8c93ef597221c56b56. Separate staging path .local/archive-intrabar-audit-20261001; frozen5m data unchanged.
- [x] Actual source consistency audit:all12 aggregated5m OHLC and volume exactly matched frozenBTC development archive; report .local/state/intrabar-source-audit-20261001.json. This is a one-hour diagnostic,not full1m coverage or a newly profitable execution study; historical observation times and real fills not certified.
- Последняя полная проверка: **704 passed**,git diff --check clean. Ниже остаются невыполненными data sufficiency,prospective qualification и real portfolio income gates.

### Продолжение: воспроизводимая команда intrabar source audit

- [x] scripts/audit_intrabar_source.py применяет resource floors/worker lock/frozen coarse SHA, требует exact minute-file SHA, ограничивает size/count, отклоняет minute gaps/disorder/incomplete5m edges/missing coarse bars и повторно проверяет обе source SHA после расчёта. Sealed-final range не допускается.
- [x] Actual command повторила BTC60minutes→12matched5m bars,source_consistency_pass=True. Exact staging-file SHA f297ac30b36b001ad22516df397a482370272350f0610e53965d2cfb5a11afce отличается от canonical immutable-snapshot SHA fce1f36a... из-за JSON serialization; обе identities не смешиваются.
- [x] Six regression cases проверяют consistency,volume mismatch,missing/unaligned/reversed minutes и missing coarse. Размер audit slice не используется как количество прибыльных сделок.
- [ ] Полноценный исторический1m dataset,ambiguity cohorts и preregistered execution study остаются открытыми.
- [x] ETH second real slice captured2026-10-10T12:59:27Z:60minutes,canonical snapshot SHA4351a0baa2ba84171d8840bf2cb47be813c2ee821475b37d146b03ff1489edca,exact staging file SHA4997d2c670e2779e9c00bb45a78a38030f91c133ab43d2131c8e7ad09530b9e8. Repeatable CLI source audit matched12/12OHLC+volumes.
- [x] Полная проверка нового source-audit блока: **710 passed**; checksum recheck добавлен после этой проверки и actualETH CLI passed;git diff --check clean.
- [x] Latest ordinary primary9ed0451bdd trained2026-10-10T12:43:31Z:strict original-input/runtime audit passed,train5180/validation1060/test1140. Novel promotion900examples/34signals/mean fixed-candle return minus assumed cost−0.01311864448627437,accuracy0.77vsmajority0.77888889. Not promoted,fails_baseline_or_costs; feature-contract comparison still separately incompatible. Income not established.
- [x] Actual prospective report12:52UTC now1140 endpoints:81051 model685endpoints/42signals/19positive,meanpriceMinusCost−0.00602817603;othermodelmeans stillnegative. Additional endpoints не добавляются к real-buy100 threshold.

### Продолжение: реальные bot losses от1% и комиссия

- [x] Live feedback теперь содержит large_bot_losses:bot-controlled Spot exits с netreturn≤−1%,ограниченный worst-examples list,fee-drag/gross-before-reported-fees decomposition. External exits/conversions исключены; FIFO partial overlap и отсутствие causal attribution явно отмечены. Net PnL не уменьшается комиссиями повторно.
- [x] Actual accounting-verified source12:33UTC содержит5 таких exit orders. PONS−4.87786%(fees0.35153%),NEAR−4.64500%(0.27195%),MINA−2.62064%(0.35560%),NEAR−2.39500%(0.35601%),ETH−2.12759%(0.19797%). Все5 уже имели negative gross-before-reported-fees estimate; комиссии усилили убыток,а не создали его целиком. MINA entry-exit conflict observed,причинность не доказана.
- [x] Отдельный .local/state/large-bot-loss-diagnostics.json связан fullSHA с source и actual observed_at; past report не переписан. Unit test проверяет net−1%,fee.4%,gross−.6% и manual-exit exclusion.
- [ ] Объяснение причин убытков на независимых будущих примерах,полные исходные entry contexts и paper comparison улучшений остаются открытыми. Missing contexts не реконструируются по сегодняшним свечам.

### Продолжение: сверка основного чеклиста и actual implementation

- [x] Основные строки этапов2/3/5 уточнены: готовые feature/normalization/nonlinear/diagnostic/test components отмечены отдельно от независимой квалификации. Historical spread/rule coverage,ETH synchrony,VWAP,ablation,qualified future stream оставлены открытыми. Unit component не закрывает общий этап прибыли.
- [x] Analyze feedback и оба real-experience collectors теперь используют atomic private reports; quality/source-binding checks и eligibility thresholds сохранены.73 focused simulator/context/learning/feedback checks прошли.
- [x] Simulator settles immediate entry-open stop before measuring later candle lows,после всех simultaneous pending entries. Post-exit extremes больше не завышают maxDD для нулевого времени удержания; proceeds не финансируют другие одновременные opening entries.42 focused checks passed;drawdown_semantics явно OHLC-bound,not exact execution path.
- [x] Offline archive training CLI теперь сохраняет точные purged splits/train-only support,source hashes/runtime bundle и explicit bounded-window120 default contract. Hashes снимаются до feature calculation и проверяются после fit; no publication/live eligibility. Synthetic CLI→original snapshot→strict numerical audit roundtrip passed.
- [ ] Ни новый provenance,ни исправленная оценка риска не переоценивают старые frozen study results автоматически. Новая заявка на эксперимент требует новой source-bound version и учёта бюджета.

### Продолжение: operational collection blocker виден в readiness

- [x] Readonly report_entry_gates.py получает последние15minutes live decisions,отбрасывает future/outside-window rows,отмечает truncated window и actual ML fallback reasons. Ошибка optional query сохраняется как diagnostic_unavailable; причины не превращаются в разрешение входа.
- [x] Actual13:13:38UTC:61decisions,56hold/5reject_entry;all5rejects contain ml_fallback=no_fresh_model. Этим объясняется текущий наблюдаемый барьер притока новых реальных buys,не гарантируется отсутствие других причин либо future behavior.
- [x] Live feedback installer и currentunit обновляют gate report перед readiness,unit reload only. Readiness принимает его только при age0..300seconds;old/future/missing reports остаютсяunknown. Fit/promotion gates и actual trading policy не менялись; data readiness0closed buys remainsFalse.
- [x] CLI readiness отдельно показывает train failures/window requirements и collection_flow вместо одного misleading empty infrastructure blocked list. Three diagnostic regression cases passed.
- [ ] Допуск свежей рабочей модели требует положительных результатов/qualified execution evidence и разрешения feature-contract mismatch. Stale-model gate не отключается ради набора100 samples;prospective price observations не становятся real executed-buy labels.

### Проверенный предел завершения текущей квалификации

- Последняя полная suite: **716 passed**,последующий CLI diagnostics change проверен27focused tests;git diff --check clean. Live feedback/outcome timers active,последний feedback serviceResult=success,ExecMainStatus=0.
- Closed-study readiness actual0/100buys,0/14days,0/6pairs,0/20positive и0/20negative. Train window ends2026-11-06T21:59:16Z. Эти данные и календарное завершение нельзя заменить unit cases,архивными label counts либо hypothetical forecasts.
- Operational report содержит recent no_fresh_model rejections; existing candidates не разрешены по cost/baseline evidence. Collection gate и old contract incompatibility не обходятся ради роста счётчика.
- Весь план не объявлен выполненным: remaining implementation/evidence items сохраняют[ ],а future qualification/paper/live-income этапы зависят от independent future observations и реальных календарных окон.


### Продолжение: dual market context и наблюдаемый turnover VWAP

- [x] New29-feature dual-market schema не меняет existing24/candle7 vectors. Four tests:causal future invariance,late ETH availability,missing ETH и undefined correlation exclusion. Actual BTC/ETH development input audit produced1364vectors,0late market-close vectors;no fit/model selection. Historical input-observation times не сертифицированы.
- [x] Observed VWAP module использует quote turnover/base volume,actual caller-supplied observation cutoff и explicit source interval. Partial captured bars не становятся final позже автоматически. Four numeric/availability/gap/zero-volume cases passed. Source receipt authenticity отдельно не удостоверяется.
- [x] Net-return evaluation теперь отвергает duplicate samples и reversed/unavailable label intervals;такие строки не могут завысить evaluation count. Nine focused context/net tests passed.
- [ ] Признаки не допущены к primary inference;нет утверждения о положительной прибыли или qualified ablation. Для будущего fit требуется новая source-bound schema/study и budget accounting.
- Последняя полная suite: **725 passed**,git diff --check clean. Actual observed-turnover archive input audit был остановлен prepare_research resource guard до чтения архивов; нового numerical audit report/fit не создано. Unit component pass не подменяет эту невыполненную фактическую проверку.


### Продолжение: train-only ablation и profit-classifier procedure

- [x] AblatedNetRegressor сохраняет immutable removed indices и маскирует те же columns при inference. Removed NaN не скрывается,invalid/duplicate/all-feature masks отвергаются. Eight tests включают удаление единственного полезного признака,сохранение полезного признака и unchanged validation normalizer.
- [x] Experimental weighted net-profit classifier учится на net labels с explicit availability;weights derived only from original train class counts. Gross labels,future/reversed outcomes,duplicate rows отвергаются. Validation does not resample/refit. Four tests;constant-feature example показывает weighted .5 vsnatural .2 и worsening Brier,а не фиктивное улучшение.
- [ ] Эти kernels не запущены на actual archived/real data вне зарегистрированного budgeted study,не connected to primary registry/real orders. Probability calibration и profitable portfolio comparison остаются открытыми.
- [x] Profit-classifier report хранит original train identities/fit information end и явно сообщает overlap либо later temporal evaluation. Reused train diagnostics не выдаются за independent out-of-sample result. Five focused classifier tests passed after provenance guard.
- Последняя полная suite перед этим узким уточнением: **737 passed**;actual archive turnover audit по-прежнему deferred by resource floor. Новых primary fits/publication/orders из этих experimental kernels нет.
- Итоговая сводная проверка текущих новых компонентов: **738 passed**,git diff --check clean. Оба существующих live-feedback и forecast-outcome timers active. Available RAM1250580kB≈1221MiB ниже1536MiB offline floor; actual archive input experiment остаётся deferred. Остаточные qualification/data/calendar пункты не отмечены как выполненные.


### Продолжение: individual ex-ante ATR risk plans

- [x] EntryRiskPlan хранит pair/signal/available-at,stop,target,hold и отдельную research schema. ATR14 использует только declared past closed5m window;OHLC/continuity/availability/multiplier/bounds checked. Future price mutation не меняет plan.
- [x] Shared portfolio simulator optional entry_risks требует exact signal coverage и information available no later than fill. Each position stores own barriers/hold;fixed mode numerical trades/equity/maxDD unchanged. Per-signal plans preserved in result;diagnostics distinguishes fixed vsdynamic research risk.
- [x] Thirty-three focused simulator/ATR checks passed,including two positions with different barriers/hold and late/missing plans. Net research source manifest includes entry-risk dependency.
- [ ] Existing paper/live policy не изменена;new dynamic study requires frozen source/budget/target horizon accounting. No actual ATR strategy search launched and no return improvement claimed.

### Продолжение: новые family kernels и фактический storage limit

- [x] Separate support_bounce/compression_breakout kernels используют previous support/range/ATR/volume baselines,excluding current breakout bar from historical reference. Current bar должна быть known closed. Four causal/volume/late-observation tests passed;no live rule replacement.
- [x] Draft strategy-extensions catalog хранит exact conditions/mechanism/failure modes и full hashes of extension/risk/candle dependencies. Status explicitly not frozen experiment,actual data evaluations0;existing three-family catalog не переписан. Новый independent final period требуется до квалификации.
- [x] Disk exhaustion остановил запись extensions и два SQLite archive tests по реальному2GiB reserve. Нулевые partial files удалены/восстановлены;deleted only own completed pytest315 temp data plus regenerable pip download cache(1112files,398.7MB). Existing archive/receipt/model files preserved. Free root disk now≈1282MiB,stillbelow research floor.
- [x] Full suite после relocation only synthetic pytest temporary files to /dev/shm: **743 passed**. Runtime disk reserve в archive downloader не ослаблен. Four extension tests passed after code restoration;new full suite pending.
- [ ] Actual archived dynamic ATR/extension experiment и полноценное execution qualification не выполнены:disk/RAM readiness иregistered budgeted study остаются обязательными.
- [x] Full restored suite **748 passed**;symbol identity guard追加 checked infullsuite. Cleared only regenerable Chrome HTTP/code caches(~955MiB) after path validation,bringing rootfree≈2195MiB andRAM≈1653MiB. Runtime budgets unchanged;testRAM temp dirs cleaned after completion.
- [x] Deferred observed-turnover input audit resumed successfully:49BTC+49ETH windows from original checksummed minute snapshots. All98 have availability at actual late capture,0available at historical market close;no past decision admission/model fit. Report .local/state/observed-turnover-input-audit.json.
- [ ] Actual bounded ATR input audit был повторно остановлен prepare_research resource guard до чтения данных. Отметка о99cases была ошибочно записана командой после отказа и сразу исправлена:нового ATR audit report/результатов нет. Unit cases не заменяют actual source audit;runtime limits не снижены.
- Финальный контроль текущего implementation increment: **748 passed**,git diff --check clean,feedback/outcome timers active. Runtime guards для real data unchanged. ATR actual audit stillpending due fluctuating RAM;its erroneous completion entry corrected before delivery. New strategy families remain draft kernels without historical payoff evidence orlive admission.

### Продолжение: common exits и execution runtime freeze

- [x] Shared price_time_exit используется offline opening exits и paper bid stop/timeout. Stop→target→timeout precedence preserved;paper безdeclaredtarget не получает take-profit. OHLC intrabar uncertainty/fill models остаютсяявными отдельными observations.52focused tests passed.
- [x] Future execution policy freeze captures hashes ofworker/wallet/market/activation/exit rules/shared indicator/candle/public-client/hash dependencies иprivate original source bundle. Changed/missing hashes refuse activation;present bundlechecksum verified. Existing policy receipts не переписаны/неbackfilled.
- [x] Eighteen activation/worker/runtime checks passed before additional source-bundle checksum test;full suitepending. Disabled/unqualified study remainsdisabled;no paperwallet ororders created.
- [ ] Complete shared entry logic,intrabar historical execution qualification и prospective paper evidence остаютсяоткрытыми. Source freeze implementation не заменяет actual qualified candidate orcalendarwindows.

- Final verification ofcommon exit/runtime binding: **757 passed**,git diff --check clean. Source bundle corruption/changed source/missing manifest refuse activation. Existing disabled execution drafts/observed acceptance receipts не переписаны;paper staysunstarted.


### Продолжение: time-safe paper status и отдельный spread scenario

- [x] Paper intent status transitions(filled/rejected/expired/cancelled) обновляют actual observed_at. Export отказывается reconstruct earlier decision/worker state,включая future non-error events иrejections withoutfills.40 focused paper tests passed.
- [x] Offline scenario spread моделирует ask/bid proxies вокругOHLC reference отдельно от fees/slippage. Stop/target проверяются поbid proxy;zero spread math preserved,opening stopgap andindependent risk arithmetic checked.34 focused scenario/labels checks passed;historical quote reconstruction notclaimed.
- [x] Detailed close-equity export bounded5000bars иopt-in;cash+basis=capital+realizedPnl проверено,fees notdoublecounted.43 focused checks passed;running realized total avoids repeated fulltrade scans.
- [ ] Actual qualified replay,paper timeline/source migrations иhistorical execution evidence остаютсяоткрытыми. Existing frozen studies не переоцениваются сегодняшним кодом автоматически.
- [x] Future paper runtime freeze также binds results exporter иacceptance evaluator:measurement semantics не меняются молча после регистрации. Seven targeted source/activation checks passed afterdependencylist extension.
- [x] Shared execution-design validator вызывается до source capture/ledgerfreeze иприactivation. Stop/reserve mismatch,noninteger/nonpositive timing,poll>=expiry иwrong source/live scope отвергаются доimmutable receipt. Twelve targeted design/runtime/activation tests passed.
- Последняя полная suite beforedesign helper: **763 passed**;new full verificationpending. Existing observed acceptance receipts иdisabled execution drafts не переписаны.
- [x] Paper source freeze binds actual worker/export/evaluation runner files,not only imported kernels. Shared runtime source capture supports explicit trustedPath inputs without executing archived code;16 targeted runtime/snapshot/audit/activation checks passed. Duplicate preregistration design validation removed afterearly validation.
- Последняя полная suite beforethis source-list refinement: **768 passed**. Realportfolioqualified execution иfuture collection gates unchanged;no new source claimfrom old frozen receipts.

### Продолжение: автоматическое завершение отложенного ATR input audit

- [x] audit_atr_inputs.py работает только с frozen development sources иfixed tail2000/first1400/every14 input cases. Prepare_research budgets/lock сохранены;corrupt dataset не маскируется временной нехваткойресурсов. No strategy outcomes,fit,publication ororders.
- [x] Resource-deferred status пишется отдельно от original numeric report,не стирает завершённыйaudit. Completed report reused only after current source/protocol identity andfrozen dataset checks;original observed_at preserved. Three resource/corruption/cache tests passed.
- [x] Actual cryptoforge-atr-input-audit timerinstalled/enabled every30min,45s/256MiB/nice10/UMask0077. First runResult=success butstatusdeferred_by_resource_or_worker_guard,completed=False;actual numeric audit пока не выполнен. Это очередная автоматическаяпроверка условий,не completed research evidence.
- [x] Original pending ATR numeric input audit completed2026-10-11T03:52:46Z underoriginal resourceguards,99cases perBTC/ETH;100realbuy/papercalendar/profitability gates неизменны.
- Итоговая сводная проверка: **771 passed**,git diff --check clean. Live feedback,forecast outcomes иdeferred ATR input audit timers allactive. Actual RAM1457600kB≈1423MiB below1536MiB;source numeric ATR audit stilldeferred,notclaimed complete. Diskfree≈2457MiB above2048MiBfloor. Realcash/paper/calendar qualification остаётсяоткрытой.

### Продолжение: shared acquisition fee math

- [x] Spot acquisition helper явно задаёт base/quote fee currency. Quote fee резервируется до quantity rounding;base fee удерживается изgross qty,net fractional inventory иfull acquisition basis сохраняются. Unknown fee currencies отвергаются,не интерпретируются молча.
- [x] Offline quote-fee иpaper base-fee paths используютодин helper,с прежними explicit conventions;58focused math/simulator/wallet/runtime checks passed afterboth integrations. Independent arithmetic audit остаётсяотдельным расчётом.
- [x] Simulator reports explicit quote entry/exit convention;paper fill metadata retainsbase-buy/quote-sell. Source freeze includes sharedbuy dependency. Это устранение code divergence,не утверждение одинаковых fee conventions либоhistorical execution certification.
- [x] Deferred ATR audit cache identity includesresource/temporal guard иsource-hash implementation,помимоrisk/candle/archive/runner dependencies;policy/source changes requirefresh input audit.
- [ ] Offline base-fee residual liquidation model,historical fee-asset coverage иqualified execution comparisons remainopen. Paper dust/basis ownership не удаляется ради full-close label.
- [x] Spot-long net ridge/tree/classifier train andevaluation rejectnonzero short-target labels;price-short targets нельзя незаметно перенести вnet profit training. Twenty-three targeted net/context checks passed. Версии целей иsource binding по-прежнемуобязательны;это не automatic target migration.
- Последняя полная suite beforethese directional guards: **774 passed**;full verification pending.

- ActualATRinput audit completed2026-10-11T03:52:46.247141Z,auditidentity5be66ae7be974ec877dc0abc5e2817c8138c396d10a59b499ccf99010ee80a64. SystemdResult=success/ExecMainStatus0. 99past-window cases perBTC/ETH,0unavailable-at-next-open;no strategyoutcomes/fit/orders. Earlier deferred attempts remainhistorical notes,не выдаются за completed attempts.
- Current full suite: **777 passed**,git diff --check clean. Shared fee/math anddirectional target guards verified;qualified realincome remainsunconfirmed.

### Продолжение: registered detailed portfolio replay

- [x] Fixed CLI replay регистрируетsingle configuration/source/cost/dataset manifest before signals/outcomes,consumes same persistent family budget;failed evaluation recorded,completed replay reused without recalculation. Source hashes capturedbefore archive decoding andcheckedaftercalculation;finite sensitivity andfamily-specific defaults validated.
- [x] Canonical JSON conversion beforeledger record сохраняет одинаковые timestamp representations. Repeated cached call keeps original matching report bytes/observed_at. Seven targeted ledger/replay tests passed afterfix.
- [x] Actual BTC/ETH2000 detailed replay completed2026-10-11 viareviewed source-bound queue;initial protocol-ID mismatch/resource refusals remainearlier attemptnotes,not results. Registered studyb9558ef1eba3c6400f832526f32fed1c556308d9fafd17e2e8dfaac5b63082aa.
- [ ] Registered real-source detailed accounting replay/qualification остаётсяоткрытым;cash/paper/calendar requirements unchanged.

### Продолжение: one source-bound pending replay queue

- [x] Fixed BTC/ETH2000 detailed replay queued withactual observed sources/command,not an open-ended search. Source/command changes refuseautomatic evaluation;constant coded argv used. Three source-tamper/command-tamper/resource-defer tests passed.
- [x] Dedicated retrytimer every30min,45s/256MiB/nice10/UMask0077. Original v1 request retained;reviewed v2 request replaces pending sourcebinding aftercommand-hardening,not historicalresults. First v1 run onlyresource-deferred;no old result rewritten.
- [ ] Actual detailed replay completion must be read fromstatus/result;timer success alone не означает completedsimulation илиpositiveincome. No publication/realorders.

- Actual detailed replay statuscompleted withstudy b9558ef1eba3c6400f832526f32fed1c556308d9fafd17e2e8dfaac5b63082aa. 2000close equity marks,0cash/basis reconciliationerrors;summary={"trades": 122, "rejections": 312, "net_pnl": "-2.243626631319360", "final_cash": "97.756373368680640", "max_drawdown_conservative_bound": "0.0230003648509789926718260637", "live_eligible": false, "evaluation": "development_replay_not_independent_validation"}. Development scenario,not independent income/realfillcertification.

- Final suite ofshared acquisition/directional target/replay queue increments: **781 passed**,git diff --check clean. Four operational timers active. Registered detailed replay b955...completedwithnegative scenario return;no actualorders,model fit/publicationorqualified income claim.

### Продолжение 11 октября: происхождение validation-подбора порога

- [x] Добавить read-only проверку registered study/grid/result для threshold selection; checksum исходных JSON и совпадение immutable ledger payload.
- [x] Требовать observed preregistration до execution timestamps и неизменную selection policy по периоду, minimum trades и maximum drawdown.
- [x] Проверить подмену report, неполную сетку, backdated execution и изменение risk/activity policy; SQLite остаётся побайтно неизменным после проверки.
- [ ] Запустить зарегистрированное сравнение реальных validation portfolio результатов при достаточных ресурсах; новая процедура не меняет frozen cash threshold0.5.
- [ ] Независимо подтвердить качество выбранной процедуры на будущих test/paper данных. Evidence verification не является таким подтверждением.

### Продолжение 11 октября: registered окна и концентрация прогнозов

- [x] Подготовить зарегистрированную процедуру сравнения train windows/recency weights и проверить reservation-before-fit, immutable cache, snapshot changes, duplicate effective grids и отсутствие validation/train overlap.
- [x] Добавить forecast signal concentration по pair/UTC day; actual local report обновлён read-only из original prospective ledger без новых labels/fits/orders.
- В проверенном отчёте 3867 observed endpoints. Два положительных fixed-threshold candle diagnostics: 20 сигналов одной монеты/одного дня, mean price return minus assumed costs +0.00912034; 13 сигналов другой версии также одной монеты/одного дня, +0.00543115. Это не realized cash PnL и не независимое подтверждение переносимости.
- Последняя entry-gate диагностика as_of 2026-10-11T09:34:38Z: 44 hold за15минут, no_fresh_model rejections=0; предыдущую stale-model причину нельзя объявлять текущей без нового подтверждения. Legacy cash readiness остаётся8buys/1positive/7negative и не разрешает fit/promotion.
- [ ] Реальный архивный window comparison отложен: при проверке MemAvailable910748kB <1536MiB floor, disk2177MiB близок к2048MiB reserve. Ограничения не снижались.

### Продолжение 11 октября: net input support и численная воспроизводимость

- [x] Реализовать causal cohort diagnostics по pair/UTC day: class counts, zero targets, available support, concentration; unknown/future labels исключаются без чтения target values, duplicates и gross-price target contract отклоняются.
- [x] Сохранять original train/validation net rows в отдельном private content-addressed gzip snapshot; проверять SHA/size/split/target contract. Primary price snapshot не переименовывается в net evidence.
- [x] Registered window procedure сохраняет original runtime source bundle до fit и cohorts для каждой выбранной train выборки и общей validation.
- [x] Добавить аудит сохранённой weighted normalization/intercept/ridge stationarity и validation metrics без нового обучения; changed coefficients/preprocessing отклоняются.
- [ ] Actual source-bound cohort/window comparison при достаточных ресурсах, подтверждение общего portfolio payoff и независимый test/paper остаются незавершёнными. Новый численный аудит не подтверждает ledger authenticity или доходность.

- [x] Подключить optional read-only immutable ledger verification перед numerical window audit; при CLI ledger обязателен. Подмена модели в отчёте отклоняется до numerical replay, DB bytes не меняются.
- [x] Добавить bounded CLI и end-to-end проверку saved report → original ledger → original input/runtime snapshots → numerical model/metrics audit.
- Численный audit без ledger явно не подтверждает ledger authenticity; с ledger проверяется совпадение с recorded attempts. Оба режима не разрешают live promotion и не являются доказательством доходности.

Проверка этого продолжения: полный suite **823 passed**, `git diff --check` без ошибок. Реальный window training не запускался; последняя проверка ресурсов MemAvailable1209276kB (~1181MiB), disk2165MiB. Future qualification, реальные cost/rule observations и actual source-bound experiments остаются открытыми.

### Продолжение 11 октября: симметричное сравнение portfolio/ML

- [x] Ordinary и stress comparison для обеих сторон с общим начальным капиталом, лимитами и историей; optional frozen reference позволяет добавить сравнение с текущей моделью по тем же opportunities.
- [x] Проверить baseline subset, duplicate refusal и одинаковые ex-ante risk plans; фильтр меняет только допуск исходного входа.
- [x] Paired bootstrap по совпадающим полным UTC equity days, все pairs остаются в одном wallet. Incomplete-day coverage не заполняется.
- [x] Проверить zero incremental value одинаковых filters, deterministic full-day bootstrap, недостаток календарных дней, capacity и отсутствие fake profit при no-trade filter.
- [x] Подключить registered numeric portfolio runner: source fingerprint до подготовки, budget reservation до simulation, stress baseline, atomic report и cached immutable results; end-to-end orchestration проверена на synthetic data.
- [ ] Actual registered comparison по qualified source-bound strategy/current-model data. Изменения кода не переиспользуют old frozen admission или budget; существующие результаты не пересчитаны и не объявлены независимыми.

- [x] Усилить threshold support gate: explicit stress_trade_count и minimum activity для ordinary/stress execution отдельно; tiny stress sample не проходит независимо от большой суммы PnL.
- [x] Ограничить bootstrap seed целым числом; invalid float/NaN/bool/string seeds отклоняются до resampling.

Итог проверки этого продолжения: **836 passed**, `git diff --check` чистый. Guarded real archive comparison не запускался: MemAvailable1112992kB (~1087MiB) ниже1536MiB, disk2152MiB близок к2048MiB reserve. Original frozen protocols/reports/results не заменялись; новые comparison procedures не изменяли live orders или модели.

### Продолжение 11 октября: фактический bounded window и portfolio experiment

Ресурсы восстановились: MemAvailable3061008kB при исходной проверке выше1536MiB floor. Новые отдельные frozen protocols созданы до запуска; old studies/budgets/protocols не заменены. Inherited resource_readiness/measurements из parent protocol относятся к старому снимку; фактический запуск проверял текущие resources через prepare_research, без снижения лимитов.

- Window protocol SHA404d81e0b4ee730292d59a6405cc04b4cb346acbb465529558329a3685465ab6; study1135c72f15f5bd546f97ea5dd9426d35bbfd4d269c9ff69346aed40572e3eee8.
- Общая validation: 2026-10-05T01:10Z..2026-10-06T02:10Z,572examples (73positive/499negative). 2-daytrain1126examples (43positive/1083negative),4-daytrain2278 (290positive/1988negative). Это independent-entry counterfactual net targets, не реальные buys.
- RMSE2-dayuniform0.003670655;2-dayhalf-life1 0.003755126;4-dayuniform0.003320599;4-dayhalf-life1 0.003380983. Weighting ухудшил численную ошибку в этом development-срезе. Automatic winner selection/publication не выполнялись.
- Original inputs/runtime, selected rows/weights, cohort support, ridge numerics и ledger records успешно audited для всех4fits без refit/archived code execution.
- Portfolio protocol SHAa5173f7637eaab5d78fe625e3563930b75e72cd83d17f6888dfd073b41b4d5c8; studydd30f651470a5d275351405bc26e17c3b727b3f16fae37e3d73a3946900b39d5.
- 2-dayuniform:6trades,net−0.102619342USDT,stress−0.209010385. 2-dayhalf-life1:6trades,net−0.120697330,stress−0.227336546. Оба4-dayварианта:0trades/net0/stress0. Общий all-bar baseline48trades/net−0.952201606USDT приcapital100. Сохранениеcash не выдаётся за заработок.
- Full UTC bootstrap days=0 (оба граничных дня partial), status insufficient_calendar_days; confidence/profitability не заявлены. Никакие candidates не публиковались/активировались.
- [x] Оба source-bound development запуска выполнены, completed results сверены с immutable attempts.
- [x] Повтор обоих runners завершён, original output JSON побайтно идентичен, grid4/4 и persistent budgets сохранены.
- [x] В actual archive context сохранены commitda16f15ed968b8e66f8ab2c88f054a9c02d5ffcf,dirty flag,Python/runtime и параметры/cutoffs; seed=None с randomness_used_for_fit=False для deterministic ridge,bootstrap seed20261011 frozen отдельно.
- [ ] Более длинные окна/другая source-qualified universe/ablation и independent test/paper. Текущие результаты не разрешают смену рабочего бота и не подтверждают, что он начнёт зарабатывать.

Проверка этого продолжения: **838 passed**, `git diff --check` чистый. Frozen checksums сверены; budget usage ridge-net-training-window=4/4 и window-net-portfolio=4/4. Actual fitting/portfolio studies completed, original report repeat байты идентичны. Общий план не завершён: ablation/source qualification, длительные независимые окна и будущий paper требуют дальнейшей работы; profitable candidate не найден.

### Продолжение 11 октября: source-bound ablation и автоматический повтор

- [x] Реализовать зарегистрированную ablation procedure с exact previously frozen4-dayuniform control; original source report/ledger/runtime/inputs auditable, control не refit.
- [x] Проверить cache immutability, original positive-feature removal ухудшает synthetic error, irrelevant-feature removal сохраняет его, duplicate/reordered/invalid subsets не потребляют budget.
- [x] До actual fitting зафиксировать protocol net-feature-ablation-research-v1.0 SHAea7ffc8baae9c8bcd838bf6fcd52af79dc1ff8cf4a72532c249406fb7f02beb7:7individual feature removals, maxfamily7, no selection/publication.
- Actual initial запуск остановлен resource guard до registration/fitting: MemAvailable935964kB (<1536MiB). Новые значения результатов не придуманы, completed ablation пока нет.
- [x] Установить active project timer cryptoforge-feature-ablation.timer: каждые30минут повторяет только зафиксированный study при достаточных ресурсах. Request/source/command binding immutable; completed attempts не пересчитываются.
- [x] Проверить resource deferral без child launch и отказ при подмене записанной команды. Initial service Result=success/ExecMainStatus=0, status deferred_by_resource_guard.
- [ ] Завершение actual7fits и source-qualified portfolio verification эффектов признаков. Independent test/paper и изменение live feature schema остаются отдельно открытыми.

Проверка этого продолжения: **845 passed**, `git diff --check` чистый, installer bash syntax проверен. Timer active; на момент проверки следующий retry11октября17:20:24МСК. Budget usage нового ablation protocol={} (0/7): resource guard не выдавался за completed fitting. Численные ablation results пока отсутствуют; изменения live features/model/orders не выполнялись.

### Продолжение 11 октября: actual ablation completed и portfolio effect

Ресурсы позволили guarded запуск при MemAvailable2030128kB (~1982MiB). Старый deferred status не выдаётся за completion: actual fit completed2026-10-11T14:09:04Z, studya9749fa7b63d8836d4db3b7c1f808d4cb2498e629d02848a0ab4f14e00f74d59.

- [x] Завершить7declared feature-removal fits на original4-dayuniform train/validation; проверить original ledger/source/input/runtime evidence и численные параметры безrefit.
- ControlRMSE0.0033205985. Безvolume_ratio0.0032832306 (difference−0.0000373679), безema_gap0.0033117221 (−0.0000088764), безrange_120.0033859729 (+0.0000653744). Остальные изменения малы; viewed validation не доказывает устойчивости.
- [x] Новым frozen protocol SHA35f561d454f3f84115c3848e3755045c80818db16731b23ca08bb16e3b0dfec0 зарегистрировать7fixed portfolio variants доsimulations, включая frozen unmasked reference.
- Portfolio study35af57c5514ccfe4423ce84c929168595f950cebcdaa85fba504d41a8d2c3ea2 completed: все7моделей0trades/net0/stress0, reference0. All-bar baseline остаётся−0.952201606USDT. Доход не появился; automatic removal/promotion не выполнялись.
- [x] Source report/control report SHA, dataset/execution context и registered results verified. Paired intervals остаютсяinsufficient_calendar_days, full UTC days0.
- [x] Повтор ablation service даётoriginal_completed_ablation_preserved; completed fits не повторяются. Portfolio repeat проверяется отдельно; persistent budgets7/7.
- [ ] Independent feature-benefit qualification, actual profitable candidate и test/paper остаются открытыми. Checkbox общего удаления неустойчивых признаков не закрывается по одному descriptive срезу.

Итог проверки продолжения: **849 passed**, `git diff --check` чистый. Frozen protocol checksums и budget usage7/7 для обеих ablation families сверены. Portfolio repeat завершился с original output JSON побайтно идентичным; ни новые fits, ни повторные simulations не выполнялись. Profitable candidate и independent feature-benefit qualification не получены; полный план остаётся открытым.

### Продолжение 11 октября: actual balanced/unweighted net classifier comparison

- [x] До fitting зафиксировать отдельный frozen protocol SHA80a931705f6a21d890daceaee04c0ff0bb91408ad7347035ec91f458829dc239: exactly2class-balance designs, epochs100/lr0.05/L2=0.001, threshold0.5, natural validation, no selection/publication.
- Actual studydone3af7d237f37ce5e55b27327d9fb8aef451420651f134e18df0b2290893cc4f7a: both fits и paired ordinary/stress simulations completed подresource guards.
- Unweighted: Brier0.112883796,logloss0.386738582,0trades/net0/stress0. Balanced: Brier0.260498600,logloss0.718117896,36trades/net−0.759012651USDT/stress−1.400583590USDT приcapital100. 5wins/31losses;7gross price gains erased by costs.
- Constant-train-prevalence Brier0.111335007/logloss0.381842276 лучше обоих. Balancing увеличил activity, ухудшил diagnostics и не далpositiveincome в viewed development window.
- [x] Проверить original class support/weights/preprocessing/time/identities и natural validation replay через immutable ledger/source/input bundles безrefit. Optimizer coefficients reproduction=False явно сохранён; audited metrics не объявляются calibration established.
- [x] Unit checks для threshold equality, invalid probabilities, preserved readonly ledger и отказа при изменённом evaluation count.
- Repeat CLI попытка остановлена resource floor; exit1/report bytes identical. Это **не** successful cached repeat, хотя completed ledger results и original report сохранены.
- [ ] Independent balancing/calibration benefit, longer windows/current-model profitability и future test/paper remain open. Live thresholds/features/models/orders не менялись.

Итог продолжения: **855 passed**, `git diff --check` чистый. Frozen classifier protocol checksum verified, completed budget2/2 и immutable result records сверены. Actual class-balance comparison завершён; independent calibration/income qualification не получены. Original source/coefficients и active trading policy не заменялись.

### Продолжение 11 октября: rejection accounting и свежая primary диагностика

- [x] Реализовать descriptive economic screen завершённых immutable portfolio results: ordinary/stress trade floors, positive PnL, PF/DD, cash/PnL и trade/signal reconciliation.
- [x] Проверить no-trade/fee-loss rejection, inconsistent cash/count refusal и отдельный запрет independent/live admission даже при synthetic economic pass.
- [x] Применить screen к13configs трёх completed studies:0passes. 10configs не торговали,3loss configs; варианты не складываются в один income/independent sample.
- [x] Подключить readonly screening к existing feedback timer; service Result=success/ExecMainStatus=0, thresholds/models/orders не изменялись.
- Latest feedback as_of2026-10-11T17:59:39Z:legacy8buys/1positive/7negative. Recent50decisions48hold/2reject_entry,1ml_fallback=no_fresh_model; предыдущий status без stale rejection нельзя выдавать за нынешний.
- Primary training service последнего запуска success,20/20 source pairs accepted. Candidateb08e9e31eb:novel380examples/20signals,estimated fixed-candle mean net signal return+0.00350578; reason insufficient_signals и incompatible incumbent feature contract. Это не executed portfolio income и не разрешение publication.
- [x] Exact primary artifact audit52977c79d8685463302e9fd98cc1a1b67cbf99333b379d3ecec2510d4659f9be passed: original inputs train5180/validation1060/test1140, current sources match, no refit/archived runtime execution/publication.
- [ ] Qualified feature-contract migration/independent prospective evidence и successful profitable admission remain open; проверки не обходятся для получения новых buys.

Итог продолжения: **859 passed**, `git diff --check` чистый, feedback installer bash syntax проверен, actual readonly refresh и screening completed. Полный план и независимая прибыльность не объявлены завершёнными.

### Продолжение: общая quote-fee sale procedure

- [x] Выделить shared explicit quote-fee sale kernel и использовать его в simulator exits, paper wallet fill/FIFO net PnL/fee allocation и conditional liquidation marks.
- [x] Сохранять already-rounded sale quantity, учитывать комиссию один раз; не придумывать base/platform-token sale fee conversion.
- [x] Focused wallet/simulator/runtime checks62passed; полныйsuite863passed,git diff --check чистый.
- Execution source fingerprint изменился: old studies и disabled paper policies не получают backfilled runtime hashes. Historical results не пересчитаны; future execution требует новой observed policy/source version.
- [x] Повторный strict primary artifact auditb08e9e31eb/52977c79d868: source match=True, exact original input/metrics verified; publication/refit=False.
- [ ] Full shared execution qualification, non-quote sale fees, partial-fill/exit-minimum historical coverage и независимый paper остаются незавершёнными. Общая формула не доказывает income или одинаковые observations/fills.

### Продолжение: versioned target semantics и primary registry guard

- [x] Описать3target contracts без automatic relabel: price, simulated trade net, observed cash recovery/dust-zero.
- [x] Ограничить primary active/candidate registry price target; совпадения family/features недостаточно для допускаnet/cash. Root/config/event metadata conflicts, null/unknown target иcash provenance rejected.
- [x] Сохранить primary legacy-price reading без target metadata; отсутствие metadata не мигрирует данные вnet/cash и не восстанавливает missing feature contract.
- [x] Новые primary artifacts явно emit target version вroot/config; unsupported target/cash provenance нельзя передать producer, callerconfig unchanged.
- [x] Проверить compatibility и новые target fields; полныйsuite874passed,git diff --check чистый.
- Sourceproducer изменился после previous strictb08e audit. Explicit source-difference numericalaudit теперьsource_matches=False/saved numerics verified; original snapshots и artifacts не изменены, live model не заменён.
- Completed ablation timer disabled послеfinished7fits+portfolio verification; этоcleanup завершённого подзадания, не отмена основной работы. Main training иfeedback timers enabled.
- [ ] Actual target migration/relabel from qualified original sources, feature-contract migration и independent income qualification remain open. Изменениеимениtarget не заменяет эти этапы.

### Продолжение: причины no-buy по pair и проверка нового primary artifact

- [x] Добавить by-pair decisions/ML fallbacks/entry constraints и observed strategy flags; numeric context не считается причиной, duplicated reasons не увеличиваютcounts.
- [x] Проверить unknown rejection accounting, дедупликациюfallback и разделение observed flags/cause. Policy/thresholds не менялись.
- Actual15-minute sample2026-10-11T18:31:14Z..18:46:14Z:56decisions50hold/6rejects;4no_fresh_model (SENT2/W2) и2dust_budget (GRASS/HYPE). Unclassified rejects0. Это не утверждение о причине каждогоhold или гарантированном будущему sample growth.
- Последний primary training21:41:52МСК success,20/20 source pairs accepted. Candidate041b283bc8:420novel examples/11signals, fixed-candle estimated mean net signal return+0.00403151, insufficient_signals иincompatible incumbent feature contract; promoted=False.
- [x] Новый artifact01d88cd66354268a92adb9663a428e27b720c9e745d94613e4f6b9f8a0517a20 действительно emit explicit fixed-future-return-v1 вroot/config. Strict auditoriginal inputs/train5180/val1060/test1140/current source matches=True, no refit/publication/archivedruntimeexecution.
- [ ] Independent income qualification иfeature-contract migration остаютсянезавершёнными; сохраняютсяstale-model/dust protections иlive policy.

Проверка продолжения: **875 passed**, git diff --check чистый. Main training/feedback timers enabled; новые live orders, publication иослаблениеgates не выполнялись.

### Продолжение: append-stream и archive parity

- [x] Реализовать append-only closed bounded-window feature state безfuture labels; explicit width/feature/state contracts, retained history≤120default.
- [x] Проверить partial/unfinished cached bars, duplicates/gaps/wrong market, failed push state preservation, backwards observation clock иlate revision dropping out of bounded window.
- [x] Actual guarded input audit2026-10-11T19:37:48Z:BTC/ETH по1400bars,1278compared featurevectors и1281bounded strategy signals наpair, exact parity (2556/2562total).
- Source/dataset context сохранён вstream-feature-input-audit.json. Replaycomputed_at соответствует текущемуaudit clock, historical observation times certified=False; earliest available_at не выдаётся заactual historical processing time.
- [ ] Все live processing/execution stages parity иqualified point-in-time source coverage остаются открытыми. Bounded signals не объявляются full live baseline, current worker не переведён нановыйstream calculator.

Итог продолжения: **880 passed**, git diff --check чистый. Actual bounded stream/archive parity audit completed; no model fit/publication/orders. Полная live procedure parity иindependent profitability remain open.

### Реализация 12 октября: observed migration groundwork и exit minimum

- [x] Проверить свежие исходные модели черезsource/input/target guards иреализовать immutable prospective feature comparison registry; неизвестныйlegacy contract не восстановлен догадкой.
- [x] Реализоватьпроверки current source bundle/model/input contract, trained basket, fixed threshold/control, post-freeze source freshness, earliest signal barclose, isolatedforecastnamespace иoriginal input-window capture.
- [x] Frozen finalized migration protocol700119966617653d6be5d011b009821ff35383ea91304c56bd02206d56c38c24 actual2026-10-12T06:06:23Z:fixed041b price candidate иbounded120 ML-free control,APT/NEAR. Прототипыv1/v2 оставлены какpreflight receipts безobservations; онинепереписаны и неактивированы.
- [x] Активировать read-only5min collector timer с45s/256MiB/nice10, publicAPIonly/no brokerorders. First service06:11Z recorded2futureforecasts; next06:16Z ещё2,error0. Доfirst postfreezebar attempt06:08Z былнеуспешным:0forecasts,ValueError наобеихпарах. Не выдаётся заcompleted observation.
- [ ] Matured price evidence, independent paired evaluation иactual execution/paper incomequalification. Price endpoint collection неослабляетlive publication/freshness gates и неувеличиваетrealcashbuycounts.
- [x] Flag simulated exitsbelowdeclaredminimum вSimulationResult иportfolio diagnostics; exclude unresolved_exit_minimum изnettrainingexamples. Development economicscreen rejects knownviolations.
- [x] Проверить gapmin-exit case, unknownlabel exclusion иscreenrefusal; focused50tests passed.
- [ ] Strict offline residual quantity/basis/cash-preservation execution, historical min/rule coverage, partialfills/nonquoteassetsales иindependentpaperremainopen. Legacy simulationcash may includeassumedinvalidexit и неcertifiedphysicalrecovery.

### 12 октября: строгий exit minimum и незакрытый капитал

- [x] Добавлен явный `exit_minimum_policy=preserve_inventory`: продажа ниже заявленного минимума не создаёт proceeds или realized PnL; количество, basis и занятость капитала сохраняются. Mark liquidation value для такого остатка консервативно равен0, ownership не исчезает.
- [x] Проверены gap ниже минимума, невозможность финансировать следующую покупку непроданным остатком и восстановление возможности продажи при росте цены.
- [x] Portfolio diagnostics отдельно учитывает terminal open positions/basis; paired report различает realized net и final cash difference, помечает comparison с незакрытым inventory. Economic screen отклоняет unclosed inventory и известные minimum violations, сверяя cash+basis-capital=closed net.
- [x] Неполное закрытие исключено из completed trade labels. Старый `legacy_assumed` остаётся явно обозначенным для воспроизводимости прежних сценариев; новая квалификация требует явного строгого режима и нового source/config freeze.
- [ ] Исторические minimums/steps, fee assets кроме quote, depth/partial fills и20ручных source-bound cases ещё не квалифицированы. Синтетические тесты не закрывают этот пункт.

Migration v3 `700119966617653d6be5d011b009821ff35383ea91304c56bd02206d56c38c24`: сервис12октября06:26UTC success, errors={},2mature price endpoints и2новых forecasts в этом запуске. Active model и реальные ордера этим изменением не переключались.

Проверка этого набора: `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp /dev/shm/cryptoforge-final2-oct12` → **892 passed**,10.86s; `git diff --check` → чисто.

### 12 октября: реальный журнал, защита execution identity и проверка кошелька

- [x] `execution_identity.unique_executions`: идентичные повторы учитываются один раз; конфликт immutable economic fields, unknown side и NaN/Infinity отвергаются до FIFO. Journal restart больше не перезаписывает наблюдавшееся исполнение до проверки.
- [x] Inventory audit использует тот же deduplication, неизвестные комиссии не подтверждают остаток; duplicate/nonfinite wallet rows отвергаются.
- [x] Добавлен explicit tracked-coin wallet query20coins/batch и проверка полной coverage. Bybit default wallet API пропускает zero assets; проверено по https://bybit-exchange.github.io/docs/v5/account/wallet-balance. Реальный readonly запрос23coins: consistent=True, inconsistent=[]; сравнение с cached fills/transactions, не обещание полной текущей reconciliation всего аккаунта. Receipt `.local/state/explicit-wallet-inventory-audit-20261012.json`.
- [x] `scripts/audit_execution_cache.py`: bounded readonly SQLite snapshot, immutable content-address input, оригинальный source/runtime bundle и numerical FIFO replay; нет orders, notices или publication. Receipt `.local/state/execution-integrity-sourcebound-runtime-20261012.json`; inputSHA `cc7fab4648c6663ee13ad67f41283c1cacd8b5305d0ea4e540fac45acb564309`.
- [x] Реальные сохранённые данные:63ordinary executions+12conversion events,49closed FIFO segments,14open lots,0unmatched sells,0incomplete closed fees; closed net−1.305596403254432124223602484USDT,16segments≤−1%,remaining basis0.1137995937888198757763975155USDT. Segments одного order не являются независимыми сделками; это отрицательный aggregate, не сигнал гарантированного будущего loss по каждой паре.
- [x] Последний primary candidate4298b6be76, fullSHA `a01359a352734e680fe4de839fe5141389d620d7b179bc2e4a193c31dfac42e4`: exact input/metric/current-source verified; refitting/publication=False, split5180/1060/1140.
- [x] Migration v3 current source/runtime receipt валиден;14:46UTC12октября200classified endpoints,13positive labels,0signals≥.5; baseline23signals,0positive estimated returns,mean after assumedcost−.005364450986640257661371842643. Один день, две пары, endpoints overlapping; не portfolio/paper income и не independence qualification.
- [x] Label audit CLI теперь явно выбирает preserve_inventory по умолчанию и сохраняет source windows для каждой арифметически проверенной метки; manual_review_complete=False.
- [ ] Actual strict label audit BTC/ETH1000bars deferred: resource guard RAM1536MiB не пройден; output не создан.20ручных source-bound checks не закрыты. Пороги RAM/disk не понижались.

Проверки: full suite903passed/12.41s; focused source/runtime/label arithmetic4passed. После изменения FIFO/private API прежние source-bound execution policies требуют нового observed version; fingerprints не обновлялись задним числом. Prospective price collector продолжает работать.

### 12 октября, продолжение: leakage guards и actual promotion rejection

- [x] `walk_forward.validate_fold` применяется к генератору и к ручным Fold: timezone awareness, contiguous ordered boundaries, positive embargo и достаточные окна validation/test. Negative embargo/overlap/empty test не обходят purge.
- [x] `FoldSelections` ограничивает fit/evaluation/previous-test/selection information ends до test-start-minus-embargo. Capture timestamp data_snapshot_at не подменяет outcome cutoff. Recovery сверяет protocol/test interval columns с receipt, повторно проверяет artifact availability и запрещает future observed_at относительно текущих часов.
- [x] Regression tests: поздняя secondary evaluation при раннем fit, конфликт interval в SQLite, receipt до observed clock, manually constructed overlap/naive/negative/empty folds. Full suite913passed/10.97s; после добавления validation в календарный генератор focused18passed/0.14s. `git diff --check` чисто.
- [x] Audit CLI старые receipts не перезаписывает; default новый trade-label-strict-audit.json; input/source windows сохраняются отдельно.
- [ ] Actual strict BTC/ETH1000bars audit снова resource-deferred, output не создан; неизвестные20manual/source cases не отмечены выполненными. Future independent/paper gates остаются открытыми.
- [x] Реестр readonly receipt `.local/state/primary-registry-readonly-audit-20261012.json`: active09b486e979 опубликован7октября02:59UTC, source contract fields отсутствуют; latest4298b candidate12октября14:43UTC. Denied reason fails_baseline_or_costs,400unseen examples,accuracy.7575 против majority.7875,30signals mean estimated return after assumed costs−.01945684551019262; comparison_blocked_reason=incompatible_feature_calculation_contract. Это fixed-candle diagnostic, не cash income. Candidate actual local artifact explicit price target проверен ранее; отсутствующий target в event summary не заменяет artifact contract.

Эти изменения не обновляли legacy metadata, active model или frozen migrationv3 hashes. Migration service12октября15:13UTC success/errors={}; future observations продолжаются. Для новых source-bound walk-forward studies нужны новые source manifests; исторические selections не переписаны.

### 12 октября: completion evidence при threshold selection и risk summary

- [x] ValidationPortfolio теперь несёт четыре explicit ordinary/stress summary fields: open_positions_at_end, stress_open_positions_at_end, exit_minimum_violations, stress_exit_minimum_violations. Все должны быть known integer0 для участия threshold в ranking. Unknown summary или failures дают recorded execution_exclusions; bool/negative counts отвергаются.
- [x] Registered validation evidence передаёт оригинальные поля из immutable portfolio report. Отсутствие полей не трактуется как zero; report checksum verification не доказывает полноту execution summary. Legacy reports не переписаны и новые источники требуют нового registration.
- [x] Paper acceptance проверяет raw/known mark counts, boolean all-known coverage, finite[0,1]drawdown, finite max gap и соответствие видимым marks. Full-history summary не может уменьшить наблюдаемые drawdown/gaps. Это внутренний consistency check, не замена source/runtime/input verification всей истории.
- [x] Проверки: focused validation/evidence/paper48passed; full suite930passed/11.76s; git diff--check clean.
- [ ] Actual research при проверке RAM1337MiB<1536MiB,disk3052MiB≥2048MiB остаётся deferred. Значения floors не менялись. Full protocol studies,20manual/source cases, independent temporal evidence и forward paper по срокам ещё не завершены.

Migration service success/ExecMainStatus0; active model не менялась, реальных orders этими проверками не создавалось. Предыдущие paper acceptance/source fingerprints не обновлялись задним числом после изменения acceptance code.

### 13 октября: prospective calibration и оригинальные market sources

- [x] Добавлены `migration_calibration.py` и `report_migration_calibration.py`: verified migration freeze, original model/prevalence, fixed threshold0.5, unique endpoint identities, правильные price target/pair/forecast_id, original label policy и actual availability clocks. Unknown labels не становятся отрицательными. Dataset<=10000rows; immutable original input/source/runtime receipts; никаких fitting/parameter changes/publication.
- [x] Actual strict report `.local/state/migration-calibration-strict-20261013.json`:642endpoints,102positive labels (15.88785%), original training prevalence17.77992%. Brier0.13024350808279705 против constant train-prior0.13399411918942467; log loss0.4261480146185676 против0.43906602768876757. Вероятности.135607745.. .3848880246,0signals≥.5.
- [x] Cohorts APT/NEAR и UTC12/13октября, fixed five calibration bins;582forecasts<.2 (meanp.163573,positivefraction.135739),60forecasts.2–.4 (meanp.235285,positivefraction.383333). Endpoint labels overlapping; no independent admission, no profits or trades; evaluation design exploratory, не объявлен preregistered задним числом.
- [x] Public instrument observations13октября09:31:06UTC:527symbols, no further page, original canonical parsed source retained в`.local/archive-instruments`. Наблюдение текущего состояния не датирует прошлые изменения правил.
- [x] `capture_execution_market_sources.py`: bounded basket<=20,production public sources,2048MiB+2disk reserve, short request timeouts, source/runtime bundle, оригинальные full instruments-info/orderbook responses и receipts. APT/NEAR captured13октября09:31:51UTC,errors={}.
- [x] `execution_market_evidence.py`: bounded checksum references, source/runtime verification, strict observed clock/freshness, точное повторение quote/filter normalization и запрет объявлять displayed depth fill proof или current snapshot историческим правилом. Actual receipts verified at original observation time; report `.local/state/execution-market-source-verification-20261013.json` не подтверждает freshness на более поздний момент.
- [x] APTreceiptSHA `ee9433780d86f4edc80df262c68c6292df6a75cb11672554c0fa9a8cbb760e21`, NEAR `3b1e13084dc15e5421a0bc92abf938d248749bf05ad4018b75eec5f2ab2f6ee0`. Observed minimum5USDT,quantity step.01обе пары, displayed spread.0002APT/.002NEAR. Fees/partial fills/execution qualification=False; эти snapshot значения не backfill в year archive.
- [x] Focused calibration7tests, market evidence3tests; full suite940passed/11.51s; gitdiff--check clean. Migration service latest09:25UTC errors={},2newforecasts/2matureendpoints perrun.
- [ ] Actual offline archive qualification не запущена: initial RAM1275MiB<1536MiB.20manual source cases, long independent calibration periods, economic candidate qualification и forward paper остаются незавершёнными. Active model и real orders не переключались, migration source fingerprints не менялись.

### 13 октября: integrity instrument registry и наблюдаемые комиссии аккаунта

- [x] InstrumentObservationMemory.state_at сверяет receiptSHA с id, observed_at с SQL column, request/observation chronology, schema, запрет historical-certification flags, bounded source<=8MiB и исходные category/retCode/count/uniqueness/pagination. Старые timestamps/coverage нельзя заменить изменённым payload.
- [x] Actual readonly `.local/state/instrument-receipt-integrity-20261013.json`: APT/NEAR присутствуют в original public snapshot13октября13:19:57UTC, can_certify_historical_execution=False.
- [x] Добавлены `fee_observation.py`, `capture_spot_account_fees.py` и `fee_observation_evidence.py`: explicit Spot symbol/category, finite maker/taker fractions, actual request/response clocks, account-scoped receipt, immutable full original response/runtime/source bundle; replay проверяет current account fingerprint, server-time skew<=60s, нормализованные rates и bounded source hashes. Source endpoint документация: https://bybit-exchange.github.io/docs/v5/account/fee-rate. Secrets/header values не сохраняются в receipt; execution settings/orders не изменяются.
- [x] Actual current account fee capture APT13:31:54UTC/NEAR13:31:55UTC: maker0.001 (0.10%),taker0.0018 (0.18%), errors={}. Source+runtime replay at original observation time passed, `.local/state/account-fee-source-verification-20261013.json`.
- [x] APTfee receiptSHA `2d3c5a49d0132002ad471efa57b91b998a977fbaf0eeed5a36f0a3b8dba3a2c7`, NEAR `f48219f98676d508e33dfe9c7057db89cd863f2c69e8496c5cb902c3478617bc`. Fee currency, historical tariff schedule и actual fill cost остаются unknown/unverified; rates не импортированы автоматически в старые backtests, paper policies или live settings.
- [x] Focused instrument integrity4tests, fee normalization/replay8tests; full suite950passed/12.27s; gitdiff--check clean.
- [ ] Strict source label audit1000BTC/ETH deferred13октября: resource guard не пройден даже после удаления четырёх собственных завершённых pytest tmpfs directories (≈44MiB). Порог1536MiB сохранён; новый archive report не создан,20manual cases не закрыты. На старте RAM978MiB, позднее1465MiB перед cleanup; будущие independent/paper gates остаются открытыми.

Изменения instrument/fee collectors не заменили active model, не создали real orders и не изменили frozen prospective migration runtime. Migration service success/ExecMainStatus0. Для нового execution scenario rate snapshots должны быть явными observed inputs/policy sources; отсутствие fee asset или исторических данных не заменяется сегодняшним tariff.

### 13 октября: independent paper fill replay и выполненный строгий archive audit

- [x] Добавлен `paper_fill_audit.py`: independent Decimal formulas по recorded fills, без вызова spot_acquisition/spot_sale. Base-fee buy: netqty,grossqty,cost,basefee иquote equivalent; quote-fee sell: proceeds,qty,exitfee. Проверяются price against saved bid/ask+slippage, qty step/min/max/depth assumption, quote/filter availability иoriginal quote timestamp.
- [x] FIFO segments сверяются с исходными buy/sell fills: quantity/cost fraction, net proceeds, allocated entry/exit fees иполное распределение каждого sell. Export дополнительно проверяет remaining quantity conservation, сохраняя existing cash/basis checks. Runtime manifest включает new fill auditor; source fingerprints существующих policies не backfill.
- [x] Regression cases: coordinated-looking totals с изменённой fill price, unchanged cost basis с изменённым inventoryqty, изменённая segment fee при сохранённых cash/cost. Focused34passed; full953passed/19.30s; git diff--check clean.
- [x] После изменения доступных ресурсов **actual strict label audit прошёл** с original1536MiB/2048MiB guard и прочими worker limits: `scripts/audit_trade_labels.py --pair BTC/USDT --pair ETH/USDT --max-candles1000 --output .local/state/trade-label-strict-source-audit-20261013-paper-replay.json`. Ранее deferred entries остаются историческими; этот новый completed result их не переписывает.
- [x] BTC/ETH по700development candles,3октября15:50UTC–6октября02:05UTC,651independent candidate labels/pair,20sampled labels/pair; risk bounds иduration independently verified. Source window refs content-addressed; target spot-long-trade-net-v2, exit_minimum_policy preserve_inventory. BTCpositive65/651≈9.98464%,ETH58/651≈8.90937%, все observed exits timeout. Overlapping independent labels не являются portfolio trades/realbuy counts.
- [x] Dataset SHA BTC `43fc352eb09abcae64c2a7acc251816357b02f78e7ec0bef0b65ac529bfb3020`, ETH `520c0c541217df44ee1c67b267491c81c6fdf9bb7581613af4648c1063fdd9c5`. Report содержит original config fee.001/slippage.0005/stake6/min5/step.000001; это declared scenario, не historical venue rules или current account fee schedule.
- [ ] Manual/source checks gaps, ambiguous stop/target, partial/unclosed inventory иactual historical fees/filters ещё не выполнены в архиве; этот срез их не содержит. Future independent/paper evidence иqualified profitable candidate отсутствуют.

Торговые настройки/active model/real orders не менялись. Новый paper source code требует нового observed execution policy перед следующим actual paper study. Численные проверки не заменяют source qualification или полное replay будущего периода.

### 13 октября: широкий source audit и replay архивных окон

- [x] Strict development audit BTC/ETH по3500свечей,19сентября18:30UTC–1октября22:05UTC; по3451independent labels. BTC3442timeout/9stop,ETH3432timeout/19stop; positive rate16.22718%/21.18227%. Overlapping labels не являются simultaneous portfolio trades.
- [x] По20sample cases на пару:34timeout/6stop суммарно;11BTC+6ETH fee-erased price gains checked. Нет gaps,targets,ambiguous илиunclosed cases в этом срезе, соответствующие проверки остаются открыты.
- [x] Source-bound report trade-label-strict-wide-sourcebound-20261013.json сохраняет оригинальный runtime/dependency code bundle, timestamps и проверяет неизменность sources во время расчёта. Предыдущий wide diagnostic сохранён отдельно, не превращается задним числом в runtime-bound evidence.
- [x] Усилен independent verify_trade: точное label availability и ambiguity flag из original candle extremes, не только risk bounds.
- [x] Новый replay_label_audit.py читает только saved case windows/runtime, проверяет checksums/paired identity/market identity и повторяет arithmetic. Actual40cases passed; source reportSHA f5a3de71164007f600791cc581c322f5955aa50ed8a6f28db6f72322f669941b. Receipt trade-label-window-replay-market-20261013.json; original replay receipt retained. Feature preprocessing/human review/historical venue execution не сертифицированы.
- [x] Full957passed/13.40s; после market identity correction focused3passed,actual40case replay passed; gitdiff--check clean. Ошибочно перезаписанный при добавлении тестов файл восстановлен с сохранением прежних3tests, добавлены regression cases.
- [ ] Long25919bar audit resource-deferred: output не создан. ATR input audit13октября14:19UTC deferred_by_resource_or_worker_guard,completed=False; это не завершённое исследование стратегии. Floors/worker limits не менялись.
- [ ] Actual gap/ambiguous/unclosed source cases, historical fee/filter qualification, independent test иfuture paper остаются открытыми. Synthetic tests не заменяют отсутствующие архивные случаи.

Active model,live orders иrisk settings не менялись. Эти audited outcomes используют declared scenario fees/step/minimum, не подтверждают доход или исторические правила биржи.

### 13 октября: source clocks, stake budget и фоновое продолжение

- [x] Intrabar source comparison проверяет coarse candle availability/cache revision на as_of, aware clocks иvalid finite OHLCV до сопоставления1m/5m. Более поздний coarse revision не сертифицирует прошлую минутную историю.
- [x] Independent paper fill audit отклоняет Buy cost сверх frozen stake даже при согласованных quantity/fee/cash/basis; declared execution/risk settings не изменяются.
- [x] Новый run_long_label_audit_job.py: actual observed registration с protocol/data/source SHA иoriginal runtime bundle, fixed BTC/ETH25919bars/first70%development, no parameter search, no live admission. Successful process без report иpartial3500barreport не считаются completion; требуется full18143candles/pair и>=20source cases/pair. Completed artifact сохраняется, deferred не становитсяcompleted.
- [x] Установлены cryptoforge-long-label-audit.service/timer: retry period15min,worker original768MiB/120s guards via prepare_research, supervisor896MiB/150s,parent timeout135s,nice15,0077,NoNewPrivileges. Timer disables itself приcompleted илиblocked contract/source/audit failure; resource/worker deferral остаётсяpending.
- [x] Active frozen jobSHA 0fd8a8a7fd135e3782d3a71574c5bf3f56d4314a711c02cdea6afcbb3fdb686a; manifest/status в .local/state/long-label-audit-jobs/<SHA>/. Первоначальный f0c25596... сохранён отдельно иsuperseded before completion после добавления full-coverage guard; frozen hashes не backfill. Installed service14:46:05UTC success/exit0,actual status deferred_resource_or_worker_guard,completed=False,timeractive. Это подтверждение здорового deferral, не выполненного архивного исследования.
- [x] Regression tests: future coarse revision/invalid source, coordinated larger buy,changed job identity,successful process withoutreport,partial-report completion. Focused44paper/source и4job tests passed; full966passed/13.65s; gitdiff--check clean; shell installers bash-n passed.
- [ ] Длинный archive report, actual gaps/ambiguity/unclosed historical source cases, ATR/extension studies, independent calendar evaluation иforward paper qualification ещё не завершены. Future price/instrument observations продолжаются отдельными существующими timers.

Активная модель,real orders иstake/risk limits не менялись. Новое задание автономно продолжает только строго зафиксированный numerical archive audit; оно не реализует весь план автоматически ине квалифицирует доход. Paper source policy после изменения auditor требует новой версии.

### 13 октября: preregistered strategy extensions и ATR comparison

- [x] Добавлены strategy_extension_study.py иevaluate_strategy_extensions.py. До чтения outcomes зафиксированы2catalog families ×2risk methods (fixed/ATR), exact defaults/specs/ATR clamps, baseline closed120flags, initialcapital100/stake6/maxpositions3, fees.001/slippage.0005/strictpreserve_inventory, stress2, inputtail5000_first3500, bootstrap14days/2dayblocks/2000reps/seed20261013, source/data/catalog/runtime receipts. Viewed period остаётсяdevelopment.
- [x] Контроль risk-matched: fixed candidate vsfixed native baseline иATR candidate vsATR native baseline, ordinary/stress shared-wallet executions; cash-only0. Extension может вводить новые сигналы, поэтому subset/filter claims=False. Currentlegacy MLincumbent не реконструировался ине сравнивался; этот пункт исходного плана остаётся открытым. Buy-and-hold context ещё не добавлен.
- [x] ActualstudySHA 8280273c066be801e85e1d22b8f1d391c0d492c5888e593e4054e9e3fe133123; receipt .local/state/strategy-extension-studies/<SHA>/protocol.json.4configurations reserved в existing research-attempts.sqlite до расчётов. Budgetnamespace сохранён: original research-v1.1 canonical ID aab93fbaa50821bc223be76aabe26d2aa8bb3b4410d130327d7e38519ec4a329; max100/family не расширен. Первую несовместимую попытку rawSHA registration ledger отклонил иrolledback; новый budgetpool не создавался.
- [x] Complete result verifier extension_report_evidence.py сверяет original manifest ивесь uniquegrid с immutable completed ledger payloads, observed reservation/execution/finish chronology и original runtime source bundle, readonly. Modified/partial results отвергаются; passing verifier не даётindependent/live admission.
- [x] Installed cryptoforge-extension-study service/timer20minretry with originalresource/worker guard,896MiB supervisor/150s/135s childwait/nice15/0077. Existinglongaudit15min иextension20min разделяютoriginalsingle offline worker lock. Completeverifiedgrid отключаетtimer; source/contract/studyfailure тоже останавливаетloop. Processsuccess безresults не completion.
- [x] Actualfirstservice13октября15:06:42UTC success/exit0,statusdeferred_resource_or_worker_guard,completedFalse;timeractive,0/4actual results. Никакой gridwinner/profit ещё не получен. Longlabelaudit тожеpending подсвоимfrozenjob.
- [x] Tests:3studymechanism+2immutableevidence+2jobdeferral/success-without-results; full973passed/15.08s; bash-n installers иgitdiff--check clean. Native strategy/ATR/simulator files не изменялись, existinglongjobsource freeze не переписан.
- [ ] Actual evaluation полногоgrid, independent windows/current-model comparison, buy-and-hold context, calibration longperiods иfuturepaper qualification ещё не выполнены. Historicalfees/filters/minuteedgecases не сертифицированы. Fixed/ATRcomparison используетdeclared source-cost scenario, не подтверждённыеvenue fills.

Active model,live orders иrisk limits не менялись. Background retries выполняюттолько2зафиксированных offline заданий; не выполняютвесьпланавтоматически ине адаптируют параметрыпослеoutcomes.

### 13 октября: отдельный buy-and-hold context

- [x] Новый buy_hold_context.py: explicit next-open entryindex120 на томже tail5000/first3500development slice, oneinitialpurchase/pair,shared capital100/stake6/maxpositions3/quantity-step/minimum/volume assumptions; undeployedcapital остаётсяcash. Всепокупки резервируютсядо любых terminalsale proceeds, чтобыбудущаяпродажане финансироваладругойinitialentry.
- [x] Quote entry/exitfees иspread/slippage учтеныодинраз; below-minimumterminalinventory сохраняетquantity/basis,conditional liquidation value0,closednet отдельно. Stop/target не применяются,risk_matched=False,no live/independent admission. Это context,не новыйприбыльныйкандидатилиrisk-equivalent benchmark.
- [x] Registered passive studySHA9e6e60083d2736883c39db80d8b2e6877563ac9e9ee6b107b971deed49913917; originalmanifest/source/runtime/dataSHA иsingletrial reserved вexisting researchbudget. Оригинальный4-arm extension protocol8280273c...неизменён, BHне добавлен заднимчислом вего preregistration.
- [x] evaluate_buy_hold_context.py сохраняетoriginalinputs иimmutable ledgerresult ordinary/stress. Background supervisor допускаеттолько2explicit supported scopes ипроверяет fullregistered result grid; context используетreadonly generic ledger verifier.
- [x] Installed cryptoforge-passive-context service/timer20minretry,originalworkerresourceguards/singleoffline lock/896MiB supervisor150s/nice15/0077,stoponcompletion/blockedsourcefailure. Firstactual16:01:17UTC success/exit0,statusdeferred_resource_or_worker_guard,completedFalse;0/1context results.3backgroundtimers active,longauditpending,extensions0/4.
- [x] Regressiontests: two-sided fees/idlecapital,unsellable residualbasis иinitialcapitalreuse. Focused5worker/contexttests; full976passed/15.42s; bash-n andgitdiff--check clean.
- [ ] Actualpassive result/economic strategy comparisons,currentlegacy-model control,historicalexecution qualification/edgecases,independentwindows иfuturepaper stillopen. Нельзяделатьвыводдоходностипокодупроверкиилиdeferredstatus.

Сравнениеbuy-and-holdбудетиспользоватьdeclaredhistorycostscenario,не сегодняшниеaccountfee snapshots. Mainmodel,realorders иlive-risk settings не изменены.

### 13 октября: минутные источники для stop-случаев

- [x] Сверены existing artifacts другого этапа: .local/archive-intrabar-audit-20261001 содержитBTC/ETH1m sources за1октября00:00–01:00UTC. ExistingBTCaudit10октября:60fine candles/12coarse bars,price+volume matched,realfill/historical-observation certification=False. Не объявляется новым выполненным исследованием ине перезагружалось.
- [x] capture_stop_case_minutes.py выполняеттолькоpublicdataingestion: selection всех6stop samples из original40case report без выбора по1m outcomes, bounded<=40cases/2s timeout/no retries,2048MiB+2diskreserve,isolatedstaging; source-report/current-code checksums verified. Originalfrozen5m archive не изменён.
- [x] Actualingestion complete6/6:по5closed1m bars накаждыйstop,30bars total,no missingcandles/errors. Source canonical OHLCV snapshots/observed metadata/runtime retained. ReceiptSHA3bd26e7b0d373a2c7a59e58e3d431226ac15104993b4086a1e44809549e2a259; latest-ingestion pointer в .local/intrabar-stop-cases/f5a3de71164007f600791cc581c322f5955aa50ed8a6f28db6f72322f669941b/. Transport-byte integrity не заявляется: это canonical parsed OHLCV/raw-ohlcv-v1 source.
- [x] audit_barrier_order optionalinspect_unambiguous=True проверяетfinepath идляordinary coarse stop: finer open gap можетдаватьreferenceхуже coarse stopprice. Defaultexisting behavior сохранён; incomplete/source-mismatched target-only path сохраняетtargetfallback,ambiguouspath remains adverse stop. Никакихtradepolicy changes/guaranteedfills.
- [x] Новый audit_stop_case_minutes.py: completeoriginalstopset/hash/reference pairing,mutable/immutable source verification,exact5finebars,original5m source comparison,first-touch/rawprice diagnostic,postreadsourcehash and1e-20 noise tolerance. Исходный fee/spread scenario сохраняется; declaredspread долженбыть0дляrawprice comparison. Originalingestion reference/runtime сохраняетсяв completedreport.
- [ ] Actualnumeric1m/5m+firsttouch audit deferred13октября16:28:05UTC byoriginalresource/worker guard; .local/state/stop-case-minute-audit-20261013-status.json completed=False,mainreport не создан. На старте RAM920MiB<1536MiB. Sourceingestion выполняласькакboundeddatafetch,не как обход compute researchguard.
- [x] Focused18tests иfull979passed/15.14s; gitdiff--check clean. Synthetic unambiguous1m-gap case доказываетпроверкумеханизма,ноненаличиеgapвэтих6realarchivecases.
- [ ] Actual source-consistency outcomes/internal-gap findings,minute ambiguouscases/real partial fills/fees иhistorical execution qualification ещё не получены.3previousbackground researchtimers active butresource-deferred; этаminute audit пока отдельныйpending CLI,не автоматическивыполненныйjob.

Active model,real orders иrisk settings не менялись. Нельзяиспользоватьполученныеданныекакдоказательствопрошлойдоступностиминутныхбаровилиactualfillprice.

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

## Сверка планов и чеклистов, 14 октября 2026

Основной план и FINAL_AUDIT получили актуальную границу historical/current.
Research checklist разделён на завершённые mechanisms/development studies и
незавершённые historical/independent/forward gates. Этап 1 больше не запрещает
уже выполненный bounded development этап 2; qualified admission остаётся закрытым.
Полный runtime backlog и критерии закрытия: IMPLEMENTATION_RECONCILIATION_20261014.md.
Cash preflight 0 eligible, incompatible legacy contract и отсутствие independent
profitable candidate не исправляются отметкой checklist или сменой metadata.


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


## 17 октября: R1/R15 — reviewed миграция credential-bound журнала к UID

- [x] Добавлены `account_migration.py` и CLI `scripts/migrate_journal_uid.py`:
  prepare сохраняет manifest с physical/logical SHA, counts/statuses, paths,
  device/inode и implementation SHA, включая CLI. Apply требует independently
  reviewed plan SHA и заново проверяет source/account inputs под UID→credential locks.
- [x] Исходные SQLite bytes/inode, credential records и reservations сохраняются;
  prepared/unknown/ACK/observed не пересылаются, не reconcile и не release.
  Strict schema/integrity/row audit ограничен прежним DELETE journal до64MiB
  без SQLite sidecars; unbound/foreign/missing history автоматически не принимается.
- [x] Private atomic independent backup → immutable intent → UID registry →
  journal account binding. Exact partial resume не заменяет conflicting outputs;
  malformed intent, inode/source drift, reserved/ancestor paths, symlink outputs
  и hardlink backup блокируются. Safe projection не сохраняет raw key/secret/note.
- [x] 65 focused tests passed /3.91s, в том числе независимая повторная проверка.
  Review нашёл path collisions и mutable hardlink backup; оба дефекта исправлены
  и покрыты regression checks. Полный non-integration suite:
  **1534 passed,1 deselected /28.56s**.
- [x] Отдельные CLI prepare/apply процессы с fake read-only account client и
  следующий UID lease restart сохранили два original unknown/ACK rows и reserves.
  Receipt `.local/state/uid-journal-migration-cli-drill-20261017.json`:
  journal/backup SHAd223d8d54e451f4cdea32f198cac04f6e220e51f86950df8c5134424060b075d,
  plan SHA5ca341de944e60bca07364369a0d4fae422956c7b0e6a68a7705f9bc5cede97c.
  Все файлы drill находились в `/tmp`; real API requests=0, orders_submitted=false,
  live_admission_granted=false. Это simulated review, не production approval.
- [ ] Production migration и API/permissions/IP/host qualification не выполнялись.
  Key rotation, replaced/restored journal, endpoint aliases, multi-host fencing,
  некооперирующие writers и full strategy/paper/runtime admission открыты.
  Общие R1/R15 и весь план не отмечены выполненными.

Runbook: [EXECUTOR_UID_MIGRATION.md](EXECUTOR_UID_MIGRATION.md). Installed service,
production ownership/state, permissions, model и frozen research kernels не
менялись. Network integration не запускался; прежний DNS failure остаётся
невыполненной remote qualification. Следующие открытые пункты: R1 canonical
endpoint/host recovery procedure и R2 full evidence admission; operational
R3–R5 и R6–R16 сохраняют прежние отдельные критерии.


## 17 октября: R1 — canonical endpoint и старые alias registries

- [x] UID lease/migration ограничены exact `https://api.bybit.com` до policy IO,
  locks и API. Активный lease повторяет проверку перед Buy/Sell. Case/port/path/
  domain aliases не получают новый namespace; credential scope/hashes и owner
  records прежнего формата не нормализованы и не переписаны.
- [x] Под UID lock просмотрены retained account registries: same-UID alternate
  owner либо malformed/oversized record запрещает новый bootstrap. Два разных
  verified UID с отдельными fake keys продолжают использовать общий lockdir.
- [x] 67 новых endpoint tests passed /1.83s; initial ownership/migration/endpoint
  focused set154passed, затем добавлен distinct-UID regression. Existing
  ownership/migration/runtime-approval set136passed /5.22s.
- [x] Повторный isolated CLI process drill на canonical origin:
  `.local/state/uid-canonical-migration-cli-drill-20261017.json`, DB/backup
  SHA35cecdaf010343c32707461022d47ccd0a8b622ef62f29d891da99e2e0a6a333,
  reviewed plan SHAf7fe5d4dddcc896cfc0974603edae3f17d48795b518f91db26196a6ccc94d72b.
  Fake handlers only; original bytes/inode/reserves и restart сохранены.
- [ ] Поддержка regional/testnet/demo/custom origins, перенос retained alias
  binding, old/off-mode writers, отдельные lockdirs и multi-host fencing
  требуют отдельной процедуры. Existing credential-only history другого key
  не превращается в verified UID history. Общий R1 не закрыт.

Runbooks: [ownership](EXECUTOR_ACCOUNT_OWNERSHIP.md),
[migration](EXECUTOR_UID_MIGRATION.md). Реальные API/заявки/сервисы не вызывались;
production records и frozen research kernels не менялись. Historical CLI
receipt предыдущей версии сохранён; он не является проверкой новых source bytes.


## 18 октября: R2/R14 — original evidence и независимый пересчёт paper

- [x] Добавлены `strategy_evidence.py` и `scripts/audit_strategy_evidence.py`:
  original observed protocol/candidate/execution/acceptance registrations,
  exact model SHA/threshold/feature/input/target и source/runtime hashes.
  Проверка read-only, без API/private credentials и исполнения archived code.
- [x] После paper end три исходных wallet/worker пары экспортируются заново,
  retained roles/acceptance должны совпасть целиком. Проверяются original
  opportunities, probability по pinned model, role decisions→queued intents→
  fills/campaigns, causal clocks, duplicate acquisitions и natural rejections.
  Нельзя скрыть accepted losing opportunity как candidate_rejected или открыть
  trade по rejected signal и сохранить положительный report.
- [x] Полный raw marks cash/remaining-lot replay: flat/dust-zero equity,
  known/unknown coverage и material basis проверяются отдельно от summaries.
  Original pre-fill/post-fill marks с одним clock поддерживаются; несколько
  simultaneous fills без original ordering требуют review. Inflated equity,
  неверные cash/clock и fake dust блокируются даже после re-export summaries.
- [x] Existing mark format не хранит historical liquidation quotes/filters.
  Поэтому `conditional_evaluation_pass` сохраняет результат прежнего evaluator,
  а `paper_evidence_pass=false` при unreplayed valuation marks. Такой gap
  указан в mark_cash_audits/remaining_live_gates. Frozen producers не менялись;
  historical quotes/ordering не придуманы и не backfill.
- [x] До actual paper end читаются только protocol/checksum/collection registry;
  candidate/rewards DB не открываются. CLI не имеет --as-of; source files
  immutable, strict JSON/SQLite checks, no-overwrite output и path/link guards.
- [x] 36 focused tests passed /26.42s. Synthetic full original DB replay даёт
  conditional economic pass, но не live grant и не qualification неизвестных
  valuations. Missing/corrupt/drift/omission/collision cases проверены.
- [x] Реальный CLI preflight закрытого протокола18октября сохранил
  `.local/state/strategy-evidence-sealed-20261018.json`: sealed_until_paper_end,
  performance_hidden=true, candidate_identity_verified=false,
  live_admission_granted=false. Requested pin000…000 был placeholder, не
  выбранная модель. Прочитаны ровно3источника: protocol/checksum/collection DB.
- [ ] Actual candidate/independent test/paper, historical valuation sources,
  full strategy/live-eligible evidence policy и runtime/account/operational
  admission остаются открытыми. Audit не подключён к рабочему entry path;
  весь R2/R14 не закрыт. Paper end15января2027 21:59:16.427796UTC не ускоряется.

Runbook: [STRATEGY_EVIDENCE_AUDIT.md](STRATEGY_EVIDENCE_AUDIT.md). Installed
service/permissions/primary model/production state не менялись. Реальных
API/заявок не было; прежний network integration DNS failure остаётся открытым.
Следующая работа: qualification исходных mark quotes в НОВОМ preregistered
study без изменения frozen protocol, отдельный full evidence/live admission
adapter и прежние operational R1–R5/R15; R6–R16 сохраняют свои gates.


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

## 18 октября: исправление области работ и интеграция VP

По уточнению пользователя LLM-направление исключено из очереди этого чата:
ошибочно добавленные этапы и задачи продолжения удалены. Standalone LLM-план,
код диагностики и его тесты сохранены для другого агента. Исторический полный
прогон1659/1 остаётся фактом прежней проверки кода; в этой правке менялись docs.

Добавлен один раздел VP со ссылками в прежние этапы и integration map.
Исходный основной текст после сверки14октября и все **804 прежних checkbox**
сохранены в прежнем порядке/статусах; добавлены только поясняющие cross-references.
Source snapshot/commit/dirty status: `.local/state/vp-plan-integration-20261018/`.
Спецификация VP предоставлена пользователем локально, raw SHA записан выше.
Исследования VP не выполнялись; полная повторная сверка исходных docs,
independent reviewer и commit/PR пока открыты. Порядок продолжения R2/R14
зафиксирован в разделе VP; operational R1–R5 и temporal gates сохраняются.

## 18 октября: R2/R14 — prospective valuation capture и независимый replay

- [x] Добавлен отдельный `paper_valuation_capture.py`; новый отсутствующий
  namespace, registration до future start, expected protocol SHA, frozen
  candidate/config/runtime/Decimal context и bounded event journal. Legacy
  DB/root, missing sources, drift, symlink/hardlink/WAL не принимаются.
- [x] Public-only `observe_valuation_market` сохраняет целиком instrument и
  orderbook responses; проверяются original hashes и повторная нормализация.
  Нормализованные snapshots без raw sources не получают source evidence pass.
- [x] Перед producer operation commit prepared, после — completion/after-state.
  Seq/hash chain разрешают несколько marks/fills в один clock; native error
  или потеря completion блокируют retry/restart, без resend/backfill.
- [x] Независимый Decimal replay cash/FIFO/remaining basis и liquidation:
  fees/slippage/rounding/minimum/depth/dust; missing/stale sources остаются
  unknown. Проверяются native source rows, counts, hashes/inodes и отсутствие
  изменения DB во время replay. Actual fills/доходность не сертифицируются.
- [x] Sealed read-only `scripts/audit_paper_valuation.py`: текущие UTC часы,
  без --as-of; до end не открывает events/wallet DB. No-overwrite output вне
  source namespace. Всегда live_admission_granted=false и
  economic_profitability_established=false; mark/fill source coverage отдельно.
- [x] Добавлено34новых теста. Смежный прогон **112 passed /27.00s**;
  итоговый **1693 passed, 1 deselected /56.76s**. Проверены same-clock order,
  worker compatibility, forged/rehashed events, missing/stale/partial sources,
  no retry, resource/lease guards, sealed reads и CLI input protection.
- [x] SHA прежнего paper runtime совпали с checkpoint до реализации;
  PaperWallet/PaperWorker/market/runtime policies и closed study не менялись.
  Evidence: `.local/state/paper-valuation-work-20261018/verification.json`.
- [ ] Новый actual candidate/control/stress study ещё не зарегистрирован;
  lifecycle/termination/max-gap policy, budget/resource qualification, source
  collection и independent review остаются следующими задачами. Synthetic
  fixtures не являются prospective рыночными evidence или прибыльной моделью.
- [ ] Подключение full strategy entry admission, actual account/host/runtime
  rollout и весь R2/R14 остаются открытыми. Старые mark quotes не backfill.

Команды: `.venv/bin/python -m pytest tests/test_paper_valuation_capture.py
 tests/test_paper_wallet.py tests/test_paper_worker.py tests/test_paper_market.py
 tests/test_paper_observations.py tests/test_strategy_evidence.py -q -p no:cacheprovider`;
полный `.venv/bin/python -m pytest -q -m 'not integration' -p no:cacheprovider`
с basetemp под `/tmp`. Сетевые API/реальные ордера/новые таймеры/обучение не
запускались; LLM-план остаётся у другого агента. [Runbook](PAPER_VALUATION_CAPTURE.md).

## 18 октября: R2/R14 — frozen lifecycle v2 и causal time coverage

- [x] `paper_lifecycle.py`: обязательные typed limits, closeout/grace, cadence,
  mark/endpoint gaps, known-time threshold и resource/storage estimate.
  `capacity_requirements`/`plan` вычисляют бюджет до создания namespace;
  недостаточные event/byte budgets и неизвестные ресурсы блокируют freeze.
- [x] Новая capture schema v2 связывает lifecycle/config/runtime/Decimal и
  registration resources в protocol SHA. V1 не получает новый lifecycle pass;
  старый protocol/root нельзя обновить. In-memory mutation identity проверяется
  до producer operation; новые source changes требуют нового study.
- [x] Capture operations ограничены frozen poll-slot, storage/disk/memory и
  measured operation wall time. Превышение фиксирует terminal и блокирует
  следующие вызовы/restart. Неизвестный prepared outcome по-прежнему требует
  review, автоматического resubmit/backfill нет.
- [x] Entry cutoff блокирует pending/bypassed Buy непосредственно перед fill;
  разрешённый paper Sell остаётся доступен до end. Explicit completed terminal
  только после end в frozen grace. Early abort не открывает sealed outcomes.
- [x] Audit считает **время**, а не долю mark rows: availability от completion,
  срок годности ORIGINAL quote/rule receipts и invalidation на prepared.
  Same-timestamp duplicates не закрывают пропуск; mark cadence, leading/trailing
  endpoints и внутренние unknown gaps проверяются отдельно. Material remaining
  inventory, missing terminal, abort/wall failure не дают lifecycle pass.
- [x] Capacity evidence по прежним min30days/poll5s: одна роль без execution
  требует1 036 804events; cap10 000 недостаточен. Byte estimate4 246 806 528 при
  8192bytes/operation — непроверенное предположение, не фактический disk/RAM.
  `.local/state/paper-lifecycle-work-20261018/capacity-lower-bound.json`.
- [x] Добавлено33теста; focused lifecycle/capture **67passed /3.29s**,
  итоговый non-integration **1726passed,1deselected /84.44s**. Проверены late
  completion, stale source reuse, duplicate timestamps, truncated endpoints,
  resources/rate/wall abort, no-buy/allowed-sell, negative fee-inclusive
  closeout и forged terminal. Экономическая прибыль не объявляется.
- [x] Прежние native PaperWallet/PaperWorker/market/runtime SHA совпадают с
  checkpoint. Source hashes и результаты проверок сохранены в
  `.local/state/paper-lifecycle-work-20261018/verification.json`.
- [ ] Следующий R2/R14: новый сегментированный capture format для длинного
  study (bounded files, chained segments, global counter/rotation/restart,
  streaming source replay). Текущий long-study не запускать и не обходить cap.
  Standalone storage, capture v3, native archive и capture v4 реализованы
  последующими этапами; полный economic/coverage/worker replay ещё открыт.
- [ ] Полный worker polling/network/queue/worker-DB/RSS budget, shared roles,
  совместимость closeout lead с poll/delay, actual prospective protocol,
  qualified candidate/economics/independent review и entry admission открыты.

Команды: `.venv/bin/python -m pytest tests/test_paper_lifecycle.py
 tests/test_paper_valuation_capture.py -q -p no:cacheprovider` и полный
`.venv/bin/python -m pytest -q -m 'not integration' -p no:cacheprovider`;
basetemp под `/tmp`. Native frozen studies, модель, live risk/permissions/
таймеры не менялись. [Runbook](PAPER_VALUATION_CAPTURE.md). LLM — другой агент.

## 18 октября: R2/R14 — bounded segmented storage и streaming integrity

- [x] Отдельный `evidence_segments.py`: новый namespace, original manifest/
  protocol/runtime pins и typed immutable byte/count/segment/global budgets.
  Глобальные seq/hash chain не сбрасываются при ротации и restart.
- [x] Exact pending frame фиксируется в SQLite до записи JSONL; затем fsync
  и metadata commit. Recovery завершает только правильный original prefix,
  не truncate/rewrite. Exact retry не создаёт второго события; неизвестная
  native операция от этого не получает разрешения на повтор.
- [x] Реальные subprocess-death tests внутри frame write и незавершённого
  catalogue commit. SQLite сам восстанавливает hot journal; non-hot остаток
  active каталога завершается через SQLite transaction, без удаления sidecar.
- [x] Schema проверяется до application queries; manifest/inode/link/source
  guards, inventory перед append, весь active prefix при resume/seal и digest
  при retry. Sealed audit принимает external head/catalog pins, проверяет все
  сегменты и global ordering, читает bounded frames без полной истории в RAM.
- [x] Добавлено38тестов; быстрые **37passed,1deselected /13.58s**. Итоговая
  non-integration suite: **1764passed,1deselected /421.60s**. На10 005 маленьких
  synthetic events:21segment, запись/seal251.69s, audit1.246s, peak tracked
  Python allocations148 779bytes. Это не process RSS/full market capture.
- [x] Native frozen runtime и прежние `paper_valuation_capture.py`/
  `paper_lifecycle.py` SHA сохранены. Test log, source pins, measurement и
  verification: `.local/state/paper-segments-work-20261018/`.
- [x] Capture v3 adapter и bounded native wallet/worker source-row archive
  реализованы последующими этапами; затем выполнена capture v4 integration.
- [x] Streaming wallet cash/FIFO/valuation/coverage реализован19октября
  в [отдельном verifier](PAPER_STREAMING_REPLAY.md). В [runbook](EVIDENCE_SEGMENTS.md)
  уточнены приёмочные проверки source IDs, crash boundaries, day/FIFO anchors,
  sealed-window gate, shared-role budgets и реальных disk/RSS/wall measurements.
- [ ] Full runner, три роли, новый qualified candidate/protocol, future
  collection, независимая экономика/review/admission. Storage pass всегда
  оставляет paper/economic/live admission false. Existing v1/v2 long-study
  остаётся BLOCKED: cap10 000,64MiB native sources и history accumulation.

Команда: `.venv/bin/python -m pytest -q -m 'not integration' -p no:cacheprovider
--basetemp=/tmp/cryptoforge-segments-verified-20261018 --durations=5`.
Новый actual study, API/orders, fit/model publication, service/timer/risk changes
не выполнялись. LLM остаётся в другом агенте; все804 исходных checkbox сохранены.

## 18 октября: R2/R14 — capture v3 и source-row linkage

- [x] `paper_capture_v3.py`: новый schema/root, original registration до future
  start, candidate/parent study/role, runtime/native schema/Decimal identity.
  Protocol→storage manifest→registration связываются без круговой SHA-ссылки.
  V1/v2 и native frozen sources не меняются и не получают новый pass.
- [x] `SegmentedLifecycle` расширяет общий total byte budget только в v3;
  прежние cadence/cost/closeout/resource rules сохранены. Capacity30days/poll5s
  считает1 036 804events, но явно full_worker/native_archive_qualified=false.
  Nested log bytes, native64MiB limit и terminal reserve проверяются до операции.
- [x] Segmented durable prepared/complete/terminal: original mark/execute inputs,
  native intent before execution, full before/after state и original row IDs/
  payload hashes marks/fills/closed_segments. Recovery завершает только ранее
  сохранённый frame; неизвестный native outcome не resubmit и не backfill.
- [x] Sealed read-only CLI `scripts/audit_paper_capture_v3.py`: до end читает
  только protocol/registration, без --as-of. После end нужны external original
  seal/head/catalog pins; проверяются source rows, chronology, slots/resources,
  cash/inventory transitions, day-anchor и независимый liquidation mark.
  Выход всегда full_fifo_replay_pass/coverage_evidence_pass/paper_evidence_pass/
  economic_profitability_established/live_admission_granted=false.
- [x] 45 новых focused tests passed /16.19s; смежный capture/lifecycle110passed
  /7.67s до добавления последнего oversized-result case. Actual subprocess
  death после native commit и внутри partial complete, no-retry, missing schema,
  resource/native limits, reserve terminal, cutoff/allowed Sell, UTC day anchors,
  raw row rewrite, sealed reads и source/output aliases проверены.
- [x] Итоговый non-integration прогон v3: **1809 passed, 1 deselected /438.15s**. Final source pins,
  полный test log и verification receipt сохранены; git diff --check пройден.
- [x] Read-only размеры двух original public observations13октября: one-pair
  v3 mark input APT2225bytes/NEAR2227bytes; original source SHA/runtime/
  normalization verified. Wallet before/after/full frames/RSS/future capacity
  не измерены этим sample, свежего API запроса нет. Evidence:
  `.local/state/paper-capture-v3-work-20261018/archived-public-input-sizes.json`.
- [x] Bounded native wallet/worker source archive с durable archive/checkpoint/cleanup,
  original IDs и day/FIFO/pending-exit anchors реализован19октября, см. следующий этап.
- [x] Streaming fill arithmetic/FIFO/valuation/time coverage реализован19октября.
- [ ] Full worker strategy/opportunity/source decision replay.
  Старый CoverageTimeline хранит mark clocks/intervals в списках: не применять
  его на длинном run. Full worker/host/RSS/shared-role qualification открыты.
- [ ] Long-study всё ещё BLOCKED: native archive и capture v4 уже реализованы,
  но full economic/coverage/worker/admission gates не пройдены. Qualified candidate, новый actual
  protocol/future collection и independent review не созданы этим кодом.

[Runbook и checklist v3](PAPER_CAPTURE_V3.md). Checkpoint/source pins/test log:
`.local/state/paper-capture-v3-work-20261018/`. Рабочая модель, live настройки,
сервисы/таймеры и LLM-направление другого агента не менялись.

## 19 октября: R2/R14 — native archive и bounded active projection

- [x] Добавлен `native_paper_archive.py`: только новый owned root, original
  protocol/candidate/role/config/native schemas/runtime и явные budgets.
  Fixed hash shards с SQLite source/key index и per-shard row hash chain;
  global record budget сохраняется через compaction/restart.
- [x] Exact rows marks/fills/segments/terminal intents/zero lots/day anchors,
  worker events/seen predictions/intent links сначала durable archive и verify.
  Только затем attached DELETE-mode transaction очищает active wallet/worker
  и обновляет checkpoint/high-water. При archive failure active rows сохраняются.
- [x] Cash/policy/open lots/pending exits, latest/known marks, latest entry fills
  и day anchors сохраняются. Original integer IDs не сбрасываются. Archive index
  обнаруживает потерянный high-water даже после обнуления checkpoint metadata.
- [x] Archive-aware wallet/worker не исполняют повтор archived intent/prediction.
  Atomic seen→intent→link, reserve для exits и multi-lot close segments,
  bounded full prediction batch и SQL page/row/byte limits проверены.
- [x] Read-only external-seal source reader объединяет indexed archive + active
  projection, убирая только identical anchors. Missing/changed shard не значит
  unseen. Native snapshot явно projection-only, не полный export результатов.
- [x] 36focused cases passed /7.63s; actual subprocess death после archive commit,
  перед и после native cleanup/checkpoint commit; rollback half-link, source drift,
  shard-full, restart budgets, tamper, no-retry и reserved exit capacity проверены.
- [x] Итоговый полный non-integration: **1846 passed, 1 deselected /359.50s**,37новых cases.
  Synthetic10 005worker rows/4shards: запись/compaction/seal 9.97s, audit 1.729s, peak Python allocations 154845bytes, active worker file 32768bytes.
  Это не actual market capture, process RSS или full-worker/host qualification.
- [x] Capture v4 integration выполнена следующим этапом: новый prospective
  protocol/registration, causal events с archive/checkpoint references и end-window
  sealed CLI. V3 root не очищать: его count=max(ID) contract остаётся прежним.
- [x] Streaming FIFO/fill math/valuation/time-coverage replay реализован следующим этапом.
- [ ] Full worker strategy/opportunity/source replay, реальные payload/state/RSS/
  full-tick/shared-role measurements, host/power-loss,
  independent review, qualified candidate и future study/admission открыты.

Source-only pass всегда paper/economic/live admission=false. Generic source
seal не является завершением экономического окна. Actual study/fit/API/orders/
model publication/services/risk не запускались и не менялись этим этапом.
[Runbook и checklist](NATIVE_PAPER_ARCHIVE.md); checkpoint и final test log:
`.local/state/native-paper-archive-work-20261019/`. LLM ведёт другой агент.


## 19 октября: R2/R14 — capture v4 с native archive/checkpoint

- [x] Новый отсутствующий namespace, prospective protocol, parent study SHA,
  candidate/control/stress role и registration, связывающая оба manifests.
  Старые native producers, source-store и v1/v2/v3 код не менялись.
- [x] Mark/execute/enqueue/cancel/compaction проходят durable prepared→native→complete.
  Сохраняются original row deltas, logical source commitments, generation,
  watermarks и shard tips. Pure compaction не меняет логическую историю.
- [x] Bounded active scan и incremental archive accumulators; после restart
  archive читается один раз потоком, далее только новые rows. Автоматическая
  compaction/restart сохраняет original IDs и полный source union.
- [x] Actual process-death после native commit и на трёх границах compaction
  не разрешает повтор prepared. Partial stored-complete восстанавливается
  ровно из исходного frame. Сбой между native seal и capture receipt не adopt.
- [x] Original terminal/end/grace, early-abort hiding, Buy cutoff/allowed Sell,
  external source/event/seal pins, read-only CLI без --as-of и source overwrite.
- [x] 52 новых focused tests passed /46.05s: source/schema/alias drift,
  rate/resource/wall/event limits, unknown completion и rehashed false trace.
- [x] Intermediate shard tips проверяются по actual indexed archive prefixes,
  compaction watermarks — по original pre-operation counters. Две adversarial
  регрессии сначала воспроизвели пробел, затем прошли после исправления.
- [x] Synthetic42marks/86events/22segments после automatic compaction/restart:
  audit0.519s, peak Python allocations392032bytes. Receipt сохранён в папке этапа;
  actual market payloads, process RSS и full runner этим не квалифицированы.
- [x] Итоговый общий non-integration: **1898 passed, 1 deselected /536.74s**; final source SHA,
  native runtime comparison и log сохранены в `.local/state/paper-capture-v4-work-20261019/`.
- [x] Streaming cash/FIFO/fill arithmetic/valuation/known-time coverage replay
  с bounded state/scratch реализован следующим этапом; source commitment
  сам по себе не заменяет этот расчёт. Старые history-accumulating auditors не применять.
  [Подробная приёмка следующего replay](PAPER_CAPTURE_V4.md#приёмка-следующего-streaming-replay).
- [ ] Full worker tick/decision/source capture, shared candidate/control/stress
  runner и actual payload/RSS/queue/network/disk/host/power-loss qualification.
- [ ] Qualified candidate, independent review и НОВЫЙ actual prospective
  protocol/study/admission по исходным gates; min30days и бюджеты не ослаблять.

`source_checkpoint_trace_pass=true` не выдаёт paper/economic/live admission;
эти флаги false. Actual market/API/orders/fit/model publication/service/risk
changes этим этапом не выполнялись. LLM ведёт другой агент.
[Runbook и checklist](PAPER_CAPTURE_V4.md).


## 19 октября: R2/R14 — bounded independent streaming replay

- [x] Отдельный pre-start replay contract связывает original capture/role/window,
  verifier runtime и scratch/state/wall/memory/disk budgets. Closed study нельзя
  ретроспективно preregister для нового economic pass; старые protocols не менялись.
- [x] Fresh private SQLite index вне sources: hard page/row limits, indexed exact
  terminal IDs и immutable key+SHA stubs. Python хранит open lots, bounded filters,
  последние day anchors, latest mark и scalars; cleanup после успеха/ошибки.
- [x] Independent expected results и все before/after native rows: stake/order
  rounding, base/quote fees, cash/proceeds, FIFO allocation/segments/residuals,
  native daily/position/cash/rejection rules и raw liquidation/day-anchor sources.
  Native execute/mark/math и history-accumulating auditors для длинного stream не вызываются.
- [x] Constant-size coverage: prepared invalidation, original source expiry,
  completion availability, duplicate clocks и original endpoints/gaps/fraction.
  Material-zero assumptions, pending closeout и unverified final mark не квалифицируются.
- [x] 65 focused cases passed /36.83s. Source-consistent неверные fee/cash/lot/FIFO,
  unobserved same-clock Buy перед Sell, omitted losing fill, stale book, budgets,
  temporary cleanup, raw-source limits, midnight anchors и sealed CLI проверены.
- [x] Выявлен пропуск same-clock FIFO: native SQL сортирует lots по ID при равном
  opened_at. Replay теперь использует original Buy completion order и блокирует
  расходящиеся segments; red→green regression сохранён. Frozen producer не менялся.
- [x] Строгая purchase/stake/cash conservation: synthetic native Decimal case
  price17/step1e-28/capital6 дал overspend1e-27. Reader теперь отказывает,
  без расширения бюджета на epsilon и без исправления source rows; red→green сохранён.
- [x] Synthetic10 005mark core:10 009keys, scratch1 216 512bytes, active384bytes,
  peak Python allocations72 208bytes /9.124s. Это не actual capture/RSS/full-worker test.
- [x] Короткий paired replay со старым independent verifier:2fills/3marks/1segment,
  одинаковый cash99.844153885540; false dust label при согласованных source hashes
  отдельно отвергнут. Original synthetic sources и receipts сохранены.
- [x] Итоговый общий non-integration streaming replay: **1963 passed, 1 deselected /470.87s**.
  Final source SHA/log/receipts сохранены в `.local/state/paper-streaming-replay-work-20261019/`.
- [ ] **Следующий R2/R14:** full worker polling/opportunity/decision/source capture
  и paired candidate/control/stress runner. Квалифицировать causal FIFO producer
  при одинаковых timestamps и strict sizing/stake/cash conservation.
  Проверить source identity/deduplication,
  original market requests, exits/nonfills и crash boundaries всего tick.
- [ ] Actual payload/state/process RSS/full-tick/network/queue/disk/shared-role/
  host/power-loss qualification; независимый review и НОВАЯ prospective registration
  с qualified candidate по прежним минимумам30days/economics/admission.

`full_fifo_replay_pass` и local lifecycle/coverage подтверждают расчёт исходной
paper model, не доходность. `paper_evidence_pass/economic_profitability_established/
live_admission_granted=false`; full worker/account fee/host admission открыты.
Actual strategy study/fit/API/orders/model publication/services/risk не запускались
этим этапом. LLM ведёт другой агент. [Runbook](PAPER_STREAMING_REPLAY.md);
receipts `.local/state/paper-streaming-replay-work-20261019/`.

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
- [x] W5 implementation: новый producer, causal FIFO и strict sizing/cash,
  pending Buy cutoff реализованы в W5a/W5b. Общая producer qualification
  остаётся открытой до W6–W9; это отдельное условие ниже.
- [x] W5a: отдельное versioned kernel и local pre-start contract реализованы;
  [изменения и проверки](PAPER_PRODUCER_V2.md). Frozen producer/receipts сохранены.
- [x] W5b.1–W5b.3: новые archive/capture/replay components реализованы; causal
  sequence/counter, exact sizing/allocation и post-SQLite-lock clocks проверены.
  Полная actual producer qualification зависит от W6–W9.
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

## 22 октября: W6a — original local source identity и observed availability

- [x] Добавлены отдельные `local_source_observer.py`, `local_source_provenance.py`
  и CLI `audit_local_source_provenance.py`; frozen548 Python files не менялись.
- [x] Local PostgreSQL17 cluster/database/schema/table OIDs, columns/defaults,
  indexes/constraints/triggers/functions/RLS, retained migration/restore pins.
  Одна bounded `READ ONLY / REPEATABLE READ` transaction, rollback, no cloud fallback.
- [x] До120 consecutive closed rows: original UUID/xmin/raw bytes/query SHA,
  runtime до/после чтения, duplicate/future/gap/revision/ID-swap guards.
  known_at=this query completion; старые ingested/created times не backfill availability.
- [x] Pre-start source contract и external ready pins, private no-overwrite output,
  diagnostic/registered separation, offline audit и stale registered capture blocker.
- [x]79new tests passed /2.00s;186compatibility passed /16.22s.265 distinct,
  общий suite не перезапускался. Final source snapshots и actual receipt pins сохранены.
- [x] Actual22октября13:33:27UTC:120BTC+120ETH rows, identity/schema/migration
  integrity и offline CLI audit прошли. BTC last close21октября23:10UTC,
  age51807.334863s, freshness=false; ETH last close22октября13:30UTC,
  age207.736015s, freshness=true. Это240observed rows, не проверка всех таблиц.
- [x] Read-only installed feeder config использует dynamic selection и selected
  sync; snapshot universe13:29UTC не содержитBTC/ETH. Независимое обновление
  reference pairs не подтверждено; это гипотеза причины stale BTC, не causal proof.
- [ ] **W6b:** mandatory source coverage/freshness, original forecast provenance,
  global observation/revision history и reader linkage в новом shared namespace.
- [ ] W7 complete polling/paired runner, W8 actual whole-worker/host/review,
  W9 qualified candidate/new future study/economics и остальные R1–R16/VP gates.

Общая W6 не закрыта. REST→DB identity, historical known_at, source polling
completeness, host/paper/economic/live admission не выдаются. Probe не становится
registered study; actual study/fit/model publication/services/risk/primary DB
не менялись. LLM ведёт другой агент. [Runbook](LOCAL_SOURCE_PROVENANCE.md);
receipts `.local/state/local-source-provenance-work-20261022/verification.json`.

## 23 октября: W6b.1/W6b.2 — reference capture и source-bound price forecasts

- [x] Отдельные `reference_sources.py`, `reference_source_ledger.py`, CLI
  `capture_reference_sources.py`; прежние552 Python-файла сохранены без изменений.
- [x] Фиксированный public Bybit Spot GET, mandatory BTC/ETH независимо от ranking,
  closed contiguous120, raw bytes/status/query/server/actual clocks и SHA.
  Forming/future/gap/duplicate/invalid sources блокируются, failures сохраняются.
- [x] Immutable source/version IDs, first-seen без переписывания при reread,
  append-only SQLite/hash chain/external DB/head pins и crash/pending blocker.
- [x] Frozen compatible artifact, exact seven features/price probability и
  source-bound forecast IDs/availability; negative forecasts также сохраняются.
  Нет caller-supplied retrospective forecasts, повторного обучения или публикации.
- [x] Global mandatory freshness: failed BTC блокирует ETH, age последней closed
  candle и observation≤600s; недавнее чтение старой свечи не даёт свежесть.
- [x] Bounded transport: socket3s/killable worker5s/body64KiB, no redirect/keys/
  fallback/retries; venue rate errors дают cooldown≥10min и explicit remaining
  skips без дальнейших GET. SQLite cap1GiB,
  disk floor2048MiB, bounded audit/scratch/cleanup; whole-host qualification открыта.
- [x] **326 разных tests passed /25.09s** одним прогоном:61new+265compatibility.
  Проверены revisions/duplicates/failed polls/clock rollback/process death,
  first-seen/forecast tampering, quotas, lock, runtime drift и offline CLI.
  Общий repository suite заново не запускался.
- [x] Actual SQL read23октября07:08:07UTC:BTC last close21октября23:10UTC,
  age115087.881843s, stale; cluster/schema совпадают с accepted22октября.
  ETH primary SQL сегодня отдельно не перечитывался. Primary DB/services не менялись.
- [x] Отдельная restricted-network попытка07:40:10UTC:2URLError/0versions,
  original negative receipt сохранён. Разрешённый public GET нового namespace
  в07:40:29UTC:обаHTTP200,120BTC+120ETH. Ранние receipts и исходники сохранены.
  После исправления cooldown новый final namespace07:51:33UTC:обаHTTP200,
  latest close07:50UTC,age92.561/92.970s,240versions/4events/offline integrity=true.
  Actual forecasts=0, original_source_forecast_linkage_pass=false; это diagnostic.
- [ ] **W6b.3:** reader/actual compatible forecast/worker reference refresh и
  shared source integration. Новые venue IDs не заменяют прежние SQL UUID и
  не дописываются в старые frozen studies. Primary BTC staleness пока не устранена.
- [ ] W7 shared candidate/control/stress opportunity stream/cursors/restart;
  W8 full-worker resources/recovery/review; W9 qualified candidate/new future
  paper/economics. Общие W6/W5, R1–R16 и INT/VP admission остаются открытыми.

[Runbook и команды](REFERENCE_SOURCE_LEDGER.md); receipts, original source copies,
test log и verification: `.local/state/reference-sources-work-20261023/`.
source_poll_completeness/historical_known_at/full_worker_or_host/paper/economic/
live/real_executed_buys=false. Нет реальных сделок, изменения основной модели,
риска, сервисов, primary DB или чтения sealed будущих outcomes. LLM — другой агент.

## 23 октября: W6b.3a — shared source reader и компактный inference artifact

- [x] Добавлены `reference_source_reader.py`, CLI `read_reference_sources.py` и
  48тестов. Прежние556 Python-файлов сохранены, frozen source/worker contracts
  и вычислительные зависимости не переписывались.
- [x] Reader contract регистрируется до start нового пустого prospective source.
  Runtime/source initial pins, fixed pairs/model/window и три роли frozen;
  late/partial setup, source substitution и diagnostic adoption блокируются.
- [x] Immutable frame фиксирует audited source DB/head/queries/raw responses,
  original known_at и global first-seen/version links. Closed120 CandleRow и
  features precision28 читаются одинаково candidate/control/stress, без API GET
  и без обновления timestamps при повторном чтении. Budget4MiB/75s/disk2048MiB
  сохранён, incomplete output не имеет completion pin.
- [x] Original negative price forecasts доступны с original IDs/source/availability;
  current usability отдельно от сохранённого результата. Истёкший forecast не
  исчезает. `worker_prediction_batch_available=false`, cash `would_enter` не создаётся.
- [x] Inference envelope копирует параметры frozen model без fit/rounding и
  сохраняет exact original bytes/SHA отдельно. Original1MiB и source artifact64KiB
  caps сохранены. Unknown/ambiguous target/input/normalization не угадываются.
- [x] **374 разных tests passed /38.85s:**48new+326compatibility одним прогоном.
  Проверены shared roles/features, negative forecasts, stale/failed sources,
  global first-seen revisions, source/frame/parameter tampering, deadlines,
  runtime drift, consumer clock rollback, source append и offline CLI.
  Общий repository suite заново не запускался.
- [x] Из frozen migration-v3 protocol взят original artifact`041b`, SHA
  `01d88cd66354268a92adb9663a428e27b720c9e745d94613e4f6b9f8a0517a20`,
  304141bytes. Новый inference2906bytes, собственный SHA
  `2a7afd1e362d337b6dcef16ba9fee2cce15f98ab14e36311224ea2292fb000a2`.
  Exact parameters audit=true; original protocol/weights/candidatea252 не менялись.
- [x] Actual public23октября08:19:49UTC:120AVAX+120BTC+120ETH closed rows,
  все ready в момент observation, latest close08:15UTC. AVAX — явно выбранная
  исходная trained pair, BTC/ETH — mandatory references; outcomes не отбирались.
- [x] Actual original AVAX forecast08:20:19.991167UTC до target08:30UTC:
  long probability0.14484000970793767. Три роли прочитали один frame SHA и
  исходные120AVAX inputs/forecast. Probability точно совпала с вычислением
  original304KiB artifact на тех же inputs. Source/frame offline audit:
  360versions/6events/1forecast, source linkage=true/frame integrity=true.
  Это diagnostic, не новый economic study/сделка/доход. Outcome не читался.
- [x] Actual stale guard08:27:32UTC: тот же frame с close08:15UTC уже старше600s,
  чтение свечей блокируется, исходный forecast ID остаётся, usable=false.
  Новых GET или outcome reads нет; `actual-stale-read-rejection.json` сохранён.
- [ ] **W6b.3b/R4:** actual working reference refresh/deployment/primary linkage.
  Primary DB в этом этапе не читалась и не менялась. Последний SQL observation
  07:08UTC показал staleBTC≈32h; новый public source не исправляет primary rows.
- [ ] **W7 — следующая реализация:** retained immutable source history после
  append, bounded common polling и все negative/skip/failure opportunities,
  durable role cursor/ack/restart и cash-entry contracts/full worker wiring.
  Уже открытый reader удерживает frame до expiry; новый consumer или replay
  старого frame требует original pinned DB. Текущий изменённый DB SHA не
  усыновлять как прежний snapshot; это требует отдельного retention contract.
- [ ] W8 full-worker/host capacities/recovery/review, W9 qualified candidate/
  новая future paper/economics и общие W6/W5/R1–R16/VP gates остаются открытыми.

[Reader runbook и команды](REFERENCE_SOURCE_READER.md). Evidence, accepted source
copies и проверка: `.local/state/reference-reader-work-20261023/verification.json`.
source_poll_completeness/historical_known_at/full_worker_or_host/paper/economic/
live/real_executed_buys=false. Нет обучения, model publication, реальных orders,
изменения primary DB/services/risk или старых protocols. LLM — другой агент.

## 23 октября: W7a — retained source prefixes и ordered role delivery

- [x] Добавлены `reference_delivery_source.py`, `reference_delivery.py`, CLI
  `deliver_reference_sources.py` и39тестов. Прежние559 Python-файлов сохранены.
- [x] Новый separate prospective contract до start пустого source; diagnostic
  режим явный и не усыновляется как economic study. Source manifest/registration/
  artifact и runtime pins сохраняются; source substitution/rewind блокируются.
- [x] Original source-event prefix сохраняется с теми же sequence/raw bytes/
  previous/head SHA. Independent replay восстанавливает first-seen/revisions,
  mandatory response/failure/rate-skip/cooldown и original price forecasts.
  Старый SQLite file не копируется целиком и не получает новый SHA задним числом.
- [x] Whole-operation chunks≤256events/4MiB, source anchors обязательны до offer.
  Частичный archive не выдаёт unanchored prefix ролям; missing rows/reorder/
  conflicting anchors и rehashed false forecast выявляются offline.
- [x] Candidate/control/stress имеют отдельные durable cursor/pending/ack.
  Повтор offer сохраняет ID/time, wrong-role/out-of-order/conflicting ack
  отвергаются. Ack — digest consumer receipt, не доказательство worker execution.
- [x] Append source/batch/queue state и offer/ack/cursor atomic. Lost receipt
  после commit восстанавливается explicit known-ancestor replay с НОВЫМ
  checkpoint. Hot journal после незавершённой transaction не удаляется и явно
  блокирует recovery до отдельного W8 host recovery.
- [x] Default queue cap4GiB/scratch256MiB, disk floor2048MiB+reserves,
  ingest90s/replay60s и delivery≤8MiB. Scratch replay проверяет новый prefix
  до commit; quota failure не продвигает cursor/archive. RSS/capacity не сертифицируются.
- [x] **413 разных tests passed /27.98s:**39new+374compatibility одним прогоном.
  Настоящие process deaths до/после commit, lost receipt, atomic rollback,
  main/scratch storage caps, locks/stale writers, duplicate ack, source removal,
  revisions, missing/cooldown slots, tampering, clocks и CLI проверены.
  Общий repository suite заново не запускался.
- [x] Actual diagnostic public polls16:52:01UTC/16:55:44UTC:120AVAX+120BTC+120ETH
  на каждом poll, distinct versions360→363/source events6→12. Два original AVAX
  forecasts `041b` до targets17:05/17:10UTC, outcomes не читались.
- [x] После source append old physical DB pin отвергается, но retained history
  воспроизводится. Три роли повторно получили прежние source events/ID/time,
  затем новый packet. Final14queue events/12source events/2batches;
  candidate/control/stress cursors=2/2/2,0unresolved anchors/внутренних gaps.
  Consumer receipts означают diagnostic input reads, не actual worker execution.
- [x] Actual explicit ancestor recovery и отдельные offline queue/source CLI
  audits прошли. Старые frozen evidence, model parameters и candidatea252 не менялись.
- [ ] **W7b — следующая реализация:** bounded automatic coordinator/polling,
  source tail/progress, полный поток strategy opportunities, separate cash-entry
  policies и durable worker tick/result receipts/full paired execution wiring.
  Нынешние price forecasts не содержат `would_enter`; receipt SHA не квалифицирует trade.
- [ ] W6b.3b/R4 actual primary reference refresh/REST linkage/deployment health;
  W8 actual host resources/recovery/review; W9 qualified candidate и future
  economic/paper study. Общие W7/W6/W5/R1–R16/VP gates остаются открытыми.

[Delivery runbook/команды](REFERENCE_DELIVERY.md); receipts и original source copies:
`.local/state/reference-delivery-work-20261023/verification.json`.
source_sqlite_bytes_retained/worker_execution_qualified/source_poll_completeness/
historical_known_at/full_worker_or_host/paper/economic/live/real_executed_buys=false.
Primary PostgreSQL/PostgREST DB, services/model/risk и sealed outcomes не затрагивались.
LLM ведёт другой агент.


## 26 октября: W7b.1 — bounded source/delivery coordinator

- [x] Новый namespace с owned source/queue, pre-start registration и frozen
  runtime/policies/model; прежние563 Python-файла сохранены.
- [x] Автоматический5m polling, explicit rate cooldown/failure/forecast skips,
  bounded ingest и мониторинг missing source tail slots/backlog/freshness.
- [x] Durable prepared/completed journal; stale writer/checkpoint блокируется,
  explicit known-ancestor recover проверяет source/queue/input receipt replay.
- [x] Три diagnostic input consumers сохраняют exact packet/receipt до ack.
  Independent replay связывает original source events/batch/role offer/ack.
- [x]31new+413compatibility=444 разных tests passed /113.32s, общий suite не запускался.
  Настоящий process death после completed pass и внутри poll, no-refetch/restart,
  rehashed packet/source/offer/freshness, quotas/locks/backward clocks проверены.
- [x] Actual public26октября: polls11:54/11:55UTC по120BTC+120ETH+120AVAX;
  source events6→12, distinct versions360→363, forecasts1→2. Повтор в первом
  окне без HTTP/новых events, delivery cursors2/2/2, packets6, journal events48.
- [ ] **W7b.2 — следующая реализация:** отдельные cash-entry contracts для
  candidate/control/stress, все actual strategy opportunities и полное
  CapturedPaperWorkerV2 wiring/durable application/result receipt verification.
  `would_enter` из price probability не выводится. Квитанции выше — input reads.
- [ ] **W7b.3/W8:** recovery между component commit и coordinator completed,
  незаконченного poll/hot journal, installed bounded runner и capacity/review.
  Неопределённые operations сейчас явно блокируются, old DB pins не усыновляются.
- [ ] W6b.3b/R4 primary reference refresh/REST linkage/deployment health и
  остальные W8/W9/R1–R16/VP gates остаются открытыми.

[Runbook](REFERENCE_COORDINATOR.md). Evidence и accepted17source/test copies:
`.local/state/reference-coordinator-work-20261026/verification.json`.
Модель прежняя diagnostic migration-v3`041b`, не candidatea252/active model.
Targets двух original price forecasts12:05/12:10UTC, outcomes не читались.
Никаких новых fits, primary DB/service/risk changes или actual orders нет.
Historical804checkbox/body сохранены; LLM-план остаётся у другого агента.
Paper/economic/live/full-host/actual-worker qualification false.

Actual replay сохранил35 initial missing5m slots: source namespace создан
08:56:27UTC, первый poll11:54:33UTC. Между двумя выполненными polls gaps нет;
current tail0 не отменяет initial gap. Continuous source completeness=false.


## 26 октября: R6 / W7b.2 preflight — календарь до чтения cash payloads

- [x] `sealed_cash_readiness.py` и CLI `check_sealed_cash_readiness.py`:
  unfinished train/validation не вызывают loader; counts=null, не fabricated0.
  Sealed-test/paper никогда не открываются этим development preflight.
- [x] Explicit original protocol SHA/observed freeze, bounded read-only snapshot
  после cutoff, latest versions/withdrawals, byte/row/wall/alias/sidecar guards.
- [x]14new+41compatibility=55 разных tests passed /0.92s; общий suite не запускался.
- [x] Actual closed protocol: calendar-only, inspected[], fit=false. Openat trace
  подтвердил: experience memory не открывалась, original freeze registry читался.
- [x] Local probes26октября: BTC close23октября14:05UTC,age252020.491109s/stale;
  ETH close26октября12UTC,age372.296792s/fresh. Identity/schema/migration +offline
  replay проверены. Timer active/waiting; последний oneshot15:05МСК success.
  В наблюдавшемся universe20pairs нет BTC/ETH; причинность остаётся гипотезой.
- [ ] W7b.2 cash-entry policies/full actual opportunities/CapturedPaperWorkerV2
  result receipts; новый preflight не является работающим cash worker.
- [ ] R6 qualified sample/input compatibility/source health и завершение окон;
  W6b.3b/R4 actual primary reference refresh/REST linkage/operational qualification.
- [ ] W7b.3/W8 recovery/host/capacity/review, W9 future study и R1–R16/VP gates.

[Runbook](SEALED_CASH_READINESS.md). Evidence/accepted11source/test copies:
`.local/state/local-cash-readiness-work-20261026/verification.json`.
Прежние566 Python-файлов и804 historical checkbox/body сохранены. DB только
читалась; services/model/risk не менялись. Automatic fit/publication/live false.
Guard новый opt-in; старые CLIs/scheduler не переписаны и не объявлены qualified.


## 26 октября: W6b.3b.1 — reference-aware feeder runner и proposal

- [x] Новые `reference_aware_feeder.py`/`run_reference_aware_feeder.py`:
  независимые BTC/ETH sync до ranking,121latest candles для120closed SQL probes,
  freshness≤600s и одинаковая identity/schema. Ranking whitelist не расширяется.
- [x] Полный sync result обязателен; exit0 при failed pairs не означает успех.
  При обычном BTC failure ETH ещё пробуется, при venue rate limit общий10min
  cooldown блокирует дальнейшие запросы и следующий cycle.
- [x] Immutable selected-pair snapshot, runtime pins/single writer/new root,
  local-only/no fallback, bounds512MiB child address space/64KiB output/75s stage.
- [x]17new+96compatibility=113 разных tests passed /2.55s; actual plan-only
  proposal создан, primary write attempted=false, service installed=false.
  С учётом повторов трёх наборов26октября —521different cases, не full suite.
- [ ] **W6b.3b.2/R4:** actual installed path/ownership qualification и primary
  reference refresh; REST→instance linkage, repeated cycles/outage/recovery,
  host capacity и retention. Новый runner ещё не заменил installed feeder.
- [ ] W7b.2 cash-entry policies/полный opportunity stream/worker result receipts;
  W7b.3/W8 recovery/host/review, W9 future study и остальные R1–R16/VP gates.

[Runbook](REFERENCE_AWARE_FEEDER.md). Evidence/accepted11source/test copies:
`.local/state/reference-aware-feeder-work-20261026/verification.json`.
Прежние569 Python-файлов и804 historical checkbox/body сохранены. Primary DB,
services/model/risk на этой code-приёмке не менялись. Последний BTC SQL probe
остаётся stale≈70h. Apply-local/реальные orders/новые fits не выполнялись.

## 26 октября: W6b.3b.2 — actual local route и installed managed feeder

- [x] Exact composed Docker api/rest/db, readonly nginx route, SQL/REST/SQL
  closed120UUID/value binding; initial BTC stale≈70h сохранён отдельным evidence.
- [x] Actual one-off13:04UTC success и installed service13:22UTC success;
  BTC/ETH mandatory sync+probe перед ranking, original units backups сохранены.
- [x] Managed operational retention/caps/runtime/owner guards и151tests/4.19s;
  по четырём профилям564distinct. Прежние572files/804historicalcheckbox/body сохранены.
- [x] Automatic timer cycle13:24UTC success, fresh BTC/ETH probes.
- [ ] Длительный W6b.3b.2d/R4/W8 recovery/host; W7b.2 cash
  policies/all actual opportunities/CapturedPaperWorkerV2 results остаются открытыми.

[Runbook](MANAGED_REFERENCE_FEEDER.md), receipt
`.local/state/reference-feeder-operation-work-20261026/verification.json`.
Local market DB/feeder units изменены. Модель/risk/trading services не менялись,
orders0/fit=false/sealed outcomes не читались; profitability/paper/live=false.

## 27 октября: W7b.2a/b — cash hypotheses и actual worker application receipts

- [x] Отдельный prospective cash contract, role-specific strategy SHA, exact
  rational guards и hold-cash control; price forecasts не превращаются в entry.
- [x] All fixed-pair decisions/negative/skip/failures, real frozen worker prepared/
  completed receipts, ack по durable result SHA и no-opportunity heartbeat ticks.
- [x]33current+249compat=282distinct cases; по профилям682distinct. Synthetic
  3roles/12applications/6opportunities/9heartbeats, independent decision/FIFO replay3/3.
- [x] Feeder27октября313retained success/238prune receipts и BTCfresh120SQL/REST/SQL;
  это bounded retained history, не доказательство непрерывности всех20h.
- [ ] W7b.2c actual paired runner/provider/cadence/monitor/finalization/prospective
  source rehearsal, W7b.3/W8 recovery/host и остальные R1–R16/VP/W9 gates.

[Runbook](CASH_WORKER_APPLICATION.md), evidence
`.local/state/cash-worker-application-work-20261027/verification.json`.
Прежние578Python files/804historicalcheckbox/body сохранены. Synthetic fixture
не market study; model/risk/trading services не менялись, fit/orders0,
original sealed outcomes не читались; economic/paper/live=false.

## 27 октября: W7b.2c.1 — bounded paired runner и actual negative-case rehearsal

- [x] Новый single-use20–120s runner/public source/3roles/5s ticks/journal/
  endpoint/independent replay,19new+33compat=52distinct; cumulative701cases.
- [x] Actual10:40–10:41UTC:240rows/12ticks×3/6decisions/33heartbeats/44operations,
  acks1/1/1; controller/FIFO/coverage3/3. Actual fills0/0/0, strategy filters rejected.
- [x] Transient service exit0/runtime81.467s, measured cgrouppeak≈33MiB under512MiB,
  AS384MiB/timeout320s. После transient GC default unit properties не runtime limits.
- [ ] W7b.2c.2 actualpositive/provider/fill/exit и long paired stream, W7b.3 unknown
  partial recovery, W8 scalable capacity/host/review и R1–R16/VP/W9/economic gates.

[Runbook](PAIRED_CASH_REHEARSAL.md), receipt
`.local/state/paired-cash-runner-work-20261027/verification.json`.
Прежние582Python files/804historicalcheckbox/body сохранены. Local primary DB/model/
risk/trading units не менялись, original sealed outcomes не читались, fit/orders0;
не short-run income evidence и не multi-day qualification.

## 27 октября: W7b.3a — explicit known paper-result ack recovery

- [x] Known completed prefix+durable worker-result, full original source/worker
  stream/native/head proof и explicit queue ancestor recovery. No tick/provider rerun.
- [x] Plan-only default, missing ack/complete append с сохранёнными original result/
  existing ack bytes; subsequent heartbeat без duplicate entries.17new+33compat=50distinct,
  cumulative718. Synthetic3cases иtrueprocess-exit послеqueuecommit прошли.
- [x] Separate actual providerprobeBTC/ETH2/2/4publicGET/normalization27октября10:50UTC;
  signals/fills не создавались. Прежние585Pythonfiles/804historicalbody сохранены.
- [ ] W7b.3b missingresult/unknowneffects/whole-runner/host recovery, W8 scalable
  longcapacity/review иW7b.2c.2 actualpositive/все economic/current-model/R1–R16/VP/W9 gates.

[Runbook](CASH_ACK_RECOVERY.md), evidence
`.local/state/cash-ack-recovery-work-20261027/verification.json`.
Primary DB/model/risk/trading services не менялись, fit/realorders0, original sealed
outcomes не читались; recovery не продлевает original window или signal expiry.

## 27 октября: W8.1 — metadata-only count/resource preflight

- [x] Exact UTC source slots/ticks, SHA-bound source/queue/worker/native/app/replay
  caps, journal and disk envelopes. No SQLite/outcome/groups/.env: actualtrace896paths.
- [x]13new+19compat=32distinct tests/38.28s, cumulative731. Прежние588Pythonfiles
  и804historicalcheckbox/body сохранены. Existing60s countpass, admissionfalse.
- [x] Hypothetical30days518400ticks/role/8641polls/3144976journal records имеет26
  blockers, explicit require-capacity exit2. Это только расчёт, новый study не запущен.
- [ ] W8.2 scalable bounded history/checkpoints/longscope, W7b.3b unknown/runner
  recovery, actualpositive/current-model/R1–R16/VP/W9/economic/host/review gates.

[Runbook](CASH_CAPACITY_PREFLIGHT.md), evidence
`.local/state/cash-capacity-preflight-work-20261027/verification.json`.
Primary DB/model/risk/trading services не менялись, fit/realorders0, original sealed
outcomes не читались. Memory/RSS/performance не выводились из count estimates.

## 27 октября: W8.2a — индексированный архив cash application v2

- [x] Новый schema/namespace, gzip с точными исходными пятью файлами, проверка
  commit/readback перед удалением собственной рабочей копии. Worker receipt и
  queue ack SHA сохраняются. Старые v1 roots/runtime/ограничения не менялись.
- [x] Обычный шаг проверяет только последнюю запись и максимум одну текущую
  группу. Полный post-end audit проверяет всю цепочку; до end только metadata.
- [x] Explicit recovery одного completed шага, включая настоящий process exit42
  после archive commit и после удаления raw copy. Worker/provider/ack не повторяются;
  неизвестный результат и постороннее продвижение role queue блокируются.
- [x]19new tests/97.65s +50compatibility cases в119.59s profile =69distinct,
  cumulative750. Ошибки прежней test fixture исключены, затем19new прошли все.
  Прежние591Pythonfiles и804historicalcheckbox/body сохранены;57accepted/59runtime.
- [x] Synthetic3roles/12applications/6decisions/9heartbeats: independent replay3/3,
  fills4/0/4, исходные receipt bytes и ack SHA сохранены, active raw groups0.
- [ ] W8.2b source/delivery/native/capture и новый paired coordinator/long capacity;
  W7b.3b unknown/parent recovery, actualpositive/current-model/R1–R16/VP/W9/
  economic/host/review gates. Existing v1 runner не стал v2 или long daemon.

[Runbook](CASH_APPLICATION_V2.md), evidence
`.local/state/cash-application-v2-work-20261027/verification.json`.
Новых public requests/primary DB/model/risk/trading changes/fits/orders нет.
Original sealed outcomes не открывались, все общие admission flags false.

## 27 октября: W8.2b.1 — incremental cash source prefix index

- [x] Новый pre-start namespace, только cash source без price artifact. Прежний
  SourceReplay feed проверяет новые event suffix; original bytes/versions/global
  first-seen и cached view сохраняются одной transaction с external pins.
- [x] Полный независимый replay проверяет prefix/state/versions/projection; no-op
  не меняет observed time. Unknown commit/stale checkpoint/incomplete poll blocked.
- [x]18new+100compat=118tests/17.99s, cumulative768. Прежние594Pythonfiles и804
  historicalcheckbox/body сохранены;19accepted source/test copies/16runtime keys.
- [x] Synthetic6attempts/4completed polls/16events/12role packets matched.
  Updates4/4/4/0/4/0 соблюдают two rate-limit cooldowns. Trueprocess-exit42 после
  commit оставляет старый checkpoint blocked; recovery не выдумывается.
- [ ] W8.2b.2 versioned delivery/reader, bounded physical SHA/history/native/
  capture/long capacity и новый coordinator; W7b.3b recovery, actualpositive/
  current-model/R1–R16/VP/W9/host/review/economic gates.

[Runbook](REFERENCE_PREFIX_V2.md), evidence
`.local/state/reference-prefix-v2-work-20261027/verification.json`.
Это input-only parity, не worker execution или constant-time всего пути. Прежние
source/delivery/app/runner namespaces и limits не менялись. Public requests/worker/
primary DB/model/risk/trading changes/fits/orders0; original sealed outcomes не читались.

## 27 октября: W8.2b.2a — cached reader для original role offers

- [x] Новый pre-start reader contract связывает queue/prefix/source identities.
  Read-only pending-role packet, точные source event bytes и cached whole-poll
  view; backlog/stale/foreign/acknowledged offers blocked без retiming или skip.
- [x]20new+18compat=38tests/10.14s, cumulative788. Прежние597Pythonfiles и804
  historicalcheckbox/body сохранены;19accepted copies/17runtime keys.
- [x] Synthetic3polls/12source events/9packets/18cash decisions: exact original
  packet/cash parity,4positive synthetic decisions, reads не меняли queue/prefix.
  Это input-only proof, actual worker/fills/profitability не проверялись.
- [ ] W8.2b.2b versioned cash-worker application с reader proof; затем paired
  coordinator/recovery, bounded physical/native/capture history/capacity,
  W7b.3b/actualpositive/current-model/R1–R16/VP/W9/host/review/economic gates.

[Runbook](CACHED_REFERENCE_READER_V2.md), evidence
`.local/state/cached-reader-v2-work-20261027/verification.json`.
Прежние source/delivery/cash/runner/runtime/limits/type guards не менялись,
monkey-patching production пути не применялся. Public requests/actual worker/
primary DB/model/risk/trading changes/fits/orders0; original sealed outcomes не читались.

## 27 октября: W8.2b.2b — cached actual paper application v3

- [x] Новый pre-start parent contract: registered cached reader → original
  packet+reader proof в input → actual prepared/completed worker-result → SHA ack.
  Heartbeats не создают source opportunities/ack, группы сохраняются в archive v2.
- [x] Full post-end source/reader proof replay, original batch/result ack checks;
  metadata-only audit до end. Unknown worker result/changed identity/budgets blocked.
- [x]17new+39compat=56tests/124.44s, cumulative805. Прежние599Pythonfiles и804
  historicalcheckbox/body сохранены;61accepted copies/77runtime keys.
- [x] Synthetic3roles/12applications/6opportunities/9heartbeats: source/reader
  audits3/3, independent controller/FIFO3/3, fills4/0/4 и12retained reader proofs.
- [x] Trueprocess-exit42 после child archive commit оставляет stale parent blocked;
  readonly source failure до worker допускает retry того же offer без duplicate intents.
- [ ] W8.2b.3 new paired coordinator/durable operations/recovery и bounded physical/
  native/capture history/capacity; W7b.3b/actualpositive/current-model/R1–R16/VP/W9/
  host/review/economic gates. Старый runner и общий long admission не менялись.

[Runbook](CACHED_CASH_APPLICATION_V3.md), evidence
`.local/state/cached-cash-application-v3-work-20261027/verification.json`.
Это actual paper class на synthetic market, не live market evidence. Новых public
requests/primary DB/model/risk/trading changes/fits/orders нет; original sealed outcomes
не открывались. Прежние source/cash/worker/runtime/registration/type guards сохранены.

## 27 октября: read-only сверка отсутствия покупок и диагностики

Срез23:21–23:23 МСК: local registry подтверждает active `09b486e979` от
7 октября и candidate `f8028fb44d` от27 октября; candidate denied при3/580
новых сигналов. Отдельный 16:30–16:45 МСК срез содержит31 hold и7
`no_fresh_model` rejects;23:00–23:15 содержит39 hold и0 rejects. В журнале
позднего цикла риск проверен, open positions0, entry slots2 и blockers пусты;
это не независимый полный account audit. Last cached CHIP fills 8 октября
17:10:24/17:14:03 МСК. Диагностический SQLite заполнен до256MiB,
quick_check=ok. Feeder после смены загрузки заблокирован незавершённым циклом
17:11:37; последняя выбранная стадия остаётся unknown, BTC в local DB устарел.

[Подробности и воспроизводимые evidence](NO_BUY_DIAGNOSIS_20261027.md).
Текущий checklist содержит R1/R2 account/order path, R4/R15 feeder reconciliation,
R6/R15 диагностическое хранение, R7/R12 совместимый price migration, R8 поток
real-buy и W8/W9/R14 условное prospective paper. Это поставленные задачи, не
результаты их реализации. На этой проверке service flags, model, risk и order
path не менялись; запросы к local PostgREST были только GET.

## 27 октября: W8.2b.3a — bounded paired coordinator и известный результат

- [x] Новый отдельный coordinator journal сохраняет pre-start bindings, prepared/
  completed операции, точные role checkpoints, tick/missed counts и cooldown.
  Explicit recovery подтверждённого completed tick не повторяет worker/provider;
  true child process exit42 проверен. Unknown эффекты остаются blocked.
- [x] 22 новых и36 совместимых тестов:58 passed/365.04s; накопленно827 разных
  без повторного полного suite. Synthetic three-role12ticks, fills4/0/4,
  независимые controller/FIFO и source/reader audits3/3.
- [ ] Unknown component/finalization/host recovery, actual positive market,
  long physical history и full host/capacity остаются открыты; отсутствие
  подтверждённой прибыли не меняет ML gate или допуск.

[Runbook](PAIRED_CACHED_COORDINATOR.md); проверка и pins —
`.local/state/paired-cached-coordinator-work-20261027/verification.json`.
Старые601 Python files и original contracts сохранены; DB/model/risk/trading
settings не изменены, настоящие ордера и sealed outcomes не использованы.

## 28 октября: R6/R15 — сохранение diagnostic forecasts и restore drill

- [x] Отдельный bounded read-only-source snapshot и изолированное восстановление:
  47979 прогнозов,47722 версии outcome,0 orphan, full integrity `ok`, SHA
  исходного снимка и восстановленной копии совпадает; оба row digests совпадают.
  Actual источник DELETE journal; искусственный WAL и concurrent writer проверены.
- [x] 8 новых +17 совместимых тестов:25 passed; предыдущие результаты не
  переименованы в full-suite. Никакой реальный ордер или cash label не создан.
- [ ] Source остаётся полным: координация всех реальных writers/readers,
  versioned cutover/rollback и actual сбор новых forecast/outcome после
  восстановления ещё не выполнены. Same-disk копия не независимый backup.

[Runbook и evidence](FORECAST_MEMORY_SNAPSHOT.md); отчет
`.local/state/forecast-snapshot-work-20261028/restore-drill/restore-evidence.json`.

## 28 октября: R4/R15 — проверка незавершённого feeder cycle

- [x] Новый read-only inspection original registration/plan/receipt order и
  source self-consistency без повторения операций; 7new+32compat=39tests.
- [x] Actual исходный incomplete cycle: BTC/ETH source integrity pass,
  select reported success, `selected_sync` неизвестен. Текущий local REST
  06:06:59 МСК:120 closed BTC stale≈6ч22м,120 closed ETH≈2мин; в обоих
  выборках gaps0. Это не SQL/REST binding.
- [ ] Original row effects/конкурирующие writers, recovery, restart и actual
  source freshness ещё не доказаны; отсутствующие stdout нельзя пересоздать
  по SHA. Retry не авторизован.

[Метод и evidence](FEEDER_INCOMPLETE_INSPECTION.md).

## 28 октября: R4/R6 — current SQL/REST binding и два исходных среза

- [x] Local SQL/REST/SQL binding120 closed rows для BTC и ETH в06:08 МСК;
  обе пары используют исходные SQL identity/schema. BTC freshness=false,
  ETH freshness=true. У41 пересекающегося с17:11 BTC row ID изменились версии
  и raw SHA; у ETH окна не пересекаются.
- [ ] Эти два observation не являются полной историей revisions и не доказывают
  результат missing `selected_sync` или автора изменений. Recovery/непрерывность
  и restored fresh BTC остаются открыты.

[Evidence и границы](FEEDER_INCOMPLETE_INSPECTION.md); comparison
`.local/state/forecast-snapshot-work-20261028/historical-current-observation-comparison.json`.

## 28 октября: R6/R15 — сверка копии с исходной диагностической базой

- [x] В отдельной read-only source transaction в06:09 МСК проверены schema,
  counts и SHA всех типизированных строк прогнозов и версий исходов: они
  совпали с более ранним snapshot; `data_version` не изменился в процессе.
  Это сравнение двух срезов, не доказательство отсутствия промежуточных изменений.
- [ ] Независимый backup и безопасный переход записи/читателей не выполнены;
  исходная база остаётся на256MiB.

[Метод](FORECAST_MEMORY_SNAPSHOT.md); receipt
`.local/state/forecast-snapshot-work-20261028/source-snapshot-comparison.json`.

## 28 октября: R6/R15 — частичная инвентаризация writer и reader

- [x] Static call sites и installed unit: executor record использует настроенный
  ledger, outcome unit имеет отдельный flock, report читает тот же ledger;
  feature migration пишет в свой study store. Общий lock для двух writers
  не найден. Штатный matured batch ограничен последними36h.
- [ ] Проверить фактические живые процессы/отложенные операции и реализовать
  согласованный cutover с rollback. Отдельно выявить пропущенные за outage
  endpoints, позднее известное сохранять с реальным временем наблюдения;
  не выдавать его за исторически известный outcome.

[Источники](FORECAST_MEMORY_SNAPSHOT.md); receipt
`.local/state/forecast-snapshot-work-20261028/writer-reader-inventory.json`.

## 28 октября: R6 — диагностика capacity и пропущенных endpoint

- [x] Новый read-only health сообщает отдельно budget/disk blockers и количество
  незакрытых зрелых прогнозов в текущем36h окне и ранее; outcome из будущего
  не учитывается как уже известный. 6new+25compat=31tests.
- [x] Actual06:11 МСК: база256MiB blocked,0 recent unresolved и279 старых
  unresolved. Это price diagnostics, не реальные cash покупки.
- [ ] Проверить источники и возможность восстановления каждого позднего endpoint
  с честным временем наблюдения; подключение мониторинга, полный writer cutover
  и возобновление записи ещё не выполнены.

[Метод и evidence](FORECAST_MEMORY_HEALTH.md).

## 28 октября: R6 — наличие endpoint для старых price-прогнозов

- [x] Read-only local REST preflight 279 unresolved forecasts:277 distinct
  endpoint/50pairs,226 endpoint сейчас имеют rows (для226 forecast),51 endpoint
  не найден. Запросы выполнялись по исходному snapshot; outcome не записывался.
- [ ] Проверить точные OHLC/source/version и actual observation time, разрешить
  или отклонить поздние price outcomes по отдельно зарегистрированной процедуре;
  недостающие endpoint не угадывать и не записывать задним числом.

[Метод и evidence](FORECAST_MEMORY_HEALTH.md).

## 28 октября: R6 — геометрия и временные поля найденных endpoint

- [x] Read-only local capture и offline replay12 запросов/ответов:226 найденных
  rows имеют корректную конечную OHLCV geometry. У195 stored updated_at не
  раньше close time, у31 — раньше. Время в записи является source claim.
- [ ] Final candle для31 rows не подтверждена; даже у195 историческая
  доступность не доказана. Нужны исходные versions/independent source и
  корректное позднее время наблюдения до любого восстановления outcome.

[Метод и evidence](FORECAST_MEMORY_HEALTH.md).
