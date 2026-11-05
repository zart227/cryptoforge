# Обновление 2 ноября — причины выходов и сохранение контекста

> **Архивный промпт.** Не использовать как очередь. Актуальный план:
> [CURRENT_PLAN.md](CURRENT_PLAN.md). Блоки «актуальный вход 28 октября»
> ниже противоречат восстановлению 1–2 ноября.

Актуальное покрытие причин выходов **25/30**, проверено повторным чтением БД.
Пять исходных approve_exit найдены в logs/supabase-live-executor-task.log и
добавлены под отдельными order keys. PONS stop_loss=True подтверждён логом.
Ранее написанное «10 причин не восстановлены» устарело: осталось пять за
29–30 сентября. В штатный локальный service подключены decision outbox и
order submission journal; причины и свечи сохраняются ДО отправки, recovery
не пересылает ордера. Штатные циклы успешны;154tests passed, backup/restore
обоих SQLite проверен. Сигналы, суммы и модели не менялись.
См. [полный результат](EXIT_CONTEXT_RECOVERY_AND_DURABILITY_20261102.md).

# Актуальный вход 28 октября — competing writers и модель

Training service reported20 synced pairs,4 пересекаются с incomplete feeder;
current health совпадает списком, но историческая атрибуция DB rows неизвестна.
Candidate253dc4fce7 не продвинут:2 signals/420; test1140 отдельно, probability
metrics лучше baseline, сравнение incumbent blocked. Last local active event —
старая модель; loaded executor не доказан. 24new+123compat=147tests.
[Writers](FEEDER_COMPETING_WRITERS_20261028.md), [model](MODEL_TRAINING_STATUS_20261028.md).
Продолжить full writer inventory/recovery, compatible control и independent
cost-aware evidence; локальная БД, LLM — другой агент.

# Актуальный вход 28 октября — R4/R15 selected_sync effect

На synthetic clients проверены partial ticker/candle/health effects; current
local REST по20 сохранённым парам:14 закрытых свечей старше часа. Отдельно
SQL/REST/SQL BTC stale≈14ч06м, ETH fresh; historical effect неизвестен.
13new+110compat=123tests. Продолжить source versions, competing writers и
explicit recovery без повтора unknown stage: [evidence](FEEDER_SELECTED_SYNC_OBSERVATION.md).
Local PostgreSQL — основная БД; LLM — другой агент.

# Актуальный вход 28 октября — разбор доступного кэша сделок

Кэш75 записей идентичен14 октября; повторный FIFO:49 closed segments,28 losses,
16 ≤−1%,6 случаев комиссии, 8 тестов. Новая история биржи и wallet независимо
не проверены; собрать свежие данные и attribution без ложных cash labels.
[Evidence](EXECUTION_CACHE_REVIEW_20261028.md).

# Актуальный вход 28 октября — R4/R15 feeder guard

В13:30 МСК feeder service failed, timer active; read-only проверка исходного
guard подтверждает incomplete cycle, selected_sync по-прежнему unknown. Прошлый
ValueError не имеет текста в journal. Продолжить выяснение эффекта и проверяемый
recovery без обхода guard: [evidence](FEEDER_GUARD_CURRENT_20261028.md).

# Актуальный вход 28 октября — R6/R15 runtime inventory

В13:28 МСК оба writer timer active, службы между циклами inactive; fuser не
показал PID, но полная видимость процессов не подтверждена. Ledger всё ещё
256MiB/279 старых unresolved. Реализован bounded read-only inventory с fail-closed
статусом; 10new+68compat=78tests. Продолжить host/container inventory, общий
fencing всех writers и real event identity: [evidence](FORECAST_RUNTIME_INVENTORY.md).
Локальная БД остаётся основной; LLM реализует другой агент.

# Актуальный вход 28 октября — R6/R15 synthetic outcome ID и replay

На отдельной копии с pinned архивом четыре процесса выдали47723–47726; повтор
первого после новых исправлений вернул47723. Проверены SQLite crash и replay,
13new+49compat=62tests. Это synthetic протокол для cooperating writers, не
production и не реальный outcome. Продолжить real event identity, fencing
всех writers, reader/writer integration и recovery: [evidence](FORECAST_OUTCOME_ID_REHEARSAL.md).
Основная БД локальная; LLM выполняет другой агент.

# Актуальный вход 28 октября — R6/R15 composite reader rehearsal

Изолированный читатель пяти read API совпал на47979 forecasts/47700 as-of outcomes,
batch400 и rows100; synthetic late correction и конфликты проверены,49tests.
Это fixed snapshot, не live wiring. Далее global outcome identity/order, общий
writer lease, concurrency, полный runtime inventory и cutover; [evidence](FORECAST_RETENTION_READER.md).
LLM выполняет другой агент; основная БД локальная.

# Актуальный вход 28 октября — R6/R15 split rehearsal

Проверен isolated split: archive47700/47722, active279/0, все typed rows
объединения совпали с pinned snapshot, выполнен независимый SQL audit; 41 tests.
Новый active outcome может повторить ID архивной версии; простой union не решает
глобальный порядок. Продолжить с identity, composite readers, late corrections и
общим writer lease: [результаты и открытые условия](FORECAST_RETENTION_REHEARSAL.md).
Фактического cutover или восстановления сбора нет; LLM — другой агент.

# Актуальный вход 28 октября — R6/R15 retention preflight

Продолжить безопасное восстановление диагностического forecast ledger: read-only
inventory snapshot нашёл 47700 кандидатов с47722 версиями outcome и279 protected
unresolved. 9new+25compat=34tests; это не перенос и не разрешение на cutover.
Следующие шаги: [условия сохранения readers/writers и evidence](FORECAST_RETENTION_PREFLIGHT.md).
Исходные данные, службы, модель и risk controls не изменять без проверенного
контракта; local PostgreSQL остаётся основной БД. LLM — другой агент.

# Актуальный вход28октября — R6 forecast health

[Метод и evidence](FORECAST_MEMORY_HEALTH.md),
[основной checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Read-only storage/maturity монитор:6new+25compat=31tests. Actual06:11 SQLite
полная,0 unresolved в36h,279 старше. Из277 distinct endpoint local REST сейчас
содержит226,51 отсутствует; историческая доступность/OHLC не проверены. Это не cash labels. Проверить источники и честную позднюю availability,
согласовать все writers/readers и восстановить запись без потери версий. Feeder
selected_sync unknown, BTC stale; другие preregistered gates открыты. DB local,
LLM отдельно; модель/gate/risk/торговые units не менять.

# Актуальный вход28октября — R4/R15 feeder inspection

[Метод и evidence](FEEDER_INCOMPLETE_INSPECTION.md),
[текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Read-only inspector проверил original registration/plan, порядок и BTC/ETH
source receipts; `selected_sync` остаётся unknown. 7new+32compat=39tests.
SQL/REST/SQL binding120 в06:08: BTC stale≈6ч23м, ETH fresh; исторический
selected_sync остаётся unknown.
Осталось доказать original row effects с учётом concurrent writers и реализовать
безопасное recovery/restart, не удалять incomplete и не подделывать completion.
R6 diagnostic store всё ещё заполнен, несмотря на snapshot/restore drill.
Модель/gate/risk/торговые units не менять; DB local, LLM — другой агент.

# Актуальный вход28октября — R6/R15 diagnostic snapshot

[Runbook](FORECAST_MEMORY_SNAPSHOT.md),
[актуальный checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Snapshot actual price diagnostics и отдельный restore drill прошли:47979 прогнозов,
47722 версий исходов, orphan0; integrity и row digests совпали. 8new+17compat=
25tests; synthetic WAL/concurrent writer проверены. Копии на одном разделе, а
исходная SQLite всё ещё заполнена. Продолжить inventory реальных writers/readers,
versioned cutover/rollback/retention и доказательство новой записи без потери
версий; не удалять/не менять источник вслепую. Price diagnostics не cash labels.
Feeder unknown cycle, compatible model migration, paper/host/economic gates и
sealed cutoffs остаются открыты. DB local, LLM — другой агент.

# Актуальный вход27октября — W8.2b.3a bounded coordinator

[Runbook](PAIRED_CACHED_COORDINATOR.md); единая очередь —
[актуальный checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Новый отдельный coordinator 20–300s фиксирует prepared/completed source/prefix/
queue/tick/finalization/replay, checkpoints, actual worker slot и market cooldown.
Explicit recovery доказанного tick не повторяет worker/provider; настоящий
process-exit42 проверен. Unknown source/prefix/queue/worker/finalization/replay
и host recovery остаются blocked. 22new+36compat=58tests/365.04s; накопленно827;
прежние601 Python files сохранены. Synthetic3roles/12ticks/fills4/0/4,
source/reader и independent controller/FIFO audits3/3; не actual profitability.

Продолжить R4/R15 feeder unknown-stage reconciliation, R6/R15 безопасное
хранение forecast, R7/R12 совместимый кандидат и R8 real-buy flow. Для W8.2
нужны bounded physical history, unknown/restart/host recovery и actual capacity;
W9/R14 future paper и economic admission остаются открыты. Primary DB local,
LLM отдельно. Не снимать gate, не публиковать модель и не читать исходные
sealed outcomes до cutoff. Evidence
`.local/state/paired-cached-coordinator-work-20261027/verification.json`.

# Актуальный вход27октября — операционная диагностика и открытые задачи

Сначала читать [актуальный checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist)
и [срез причин отсутствия покупок](NO_BUY_DIAGNOSIS_20261027.md). Executor timer
active с gate36h; active `09b486e979` устарел; candidate `f8028fb44d` denied
(3signals/580unseen). Срез23:00–23:15 содержит39 hold/0rejects и не объясняет
каждый hold. Local forecast store256MiB заполнен, BTC feeder блокирован
incomplete cycle после смены загрузки. Не удалять исходные данные/cycle, не
угадывать неизвестный contract и не менять live flags/model/risk.

Операционно продолжить R4/R15 stage reconciliation и BTC fresh closed120;
R6/R15 inventory всех readers/writers, bounded migration/recovery forecast store;
R7/R12 preregistered compatible price migration/control/unseen; R8 отслеживание
real-buy data flow с учётом закрытого entry gate; W8/W9/R14 original future paper
после независимых gates. Зависимости, измеримые результаты и проверки — в master.
Отдельно cash labels не заменять synthetic/historical/price forecasts. Cutoff сам
по себе не создаёт выборку. Snapshot balances/risk без нового account read неизвестен.

# Актуальный вход27октября — W8.2b.2b cached cash application v3 готов

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[runbook](CACHED_CASH_APPLICATION_V3.md). AGENTS.md/TypeSafe обязательны; DB local
PostgreSQL/PostgREST, LLM — другой агент. Historical804/body и старые source/model/
runtime/registration pins сохранять; менять current summary + dated append.

Новый cached_cash_application_v3.py и17tests: pre-start parent contract связывает
cash contract, actual CapturedPaperWorkerV2, original queue и registered cached reader.
Reader proof/packet SHA/parent pin входят в input.json; actual worker-result.input SHA
связывает proof с real prepared/completed tick. Queue ack подтверждает result SHA.
Heartbeats выполняют pending fills/marks/exits без source decisions/ack; v2 archive
сохраняет точные bytes. Full post-end audit сверяет parent/reader proof, original
queue batch/ack и full retained SourceReplay. До end audit скрывает показатели.

17new+39compat=56tests/124.44s, cumulative805;599oldPythonfiles сохранены, теперь601.
61accepted copies/77runtime keys. Synthetic3roles/12applications/6opportunities/
9heartbeats: source/reader audits3/3, independent controller/FIFO3/3, fills4/0/4.
Trueprocess-exit42 после child archive commit блокирует stale parent без rerun.
Unknown worker result blocked; source read failure до worker допускает retry того
же pending offer. Evidence .local/state/cached-cash-application-v3-work-20261027/verification.json.

Следующий W8.2b.3 — НОВЫЙ preregistered paired coordinator: durable prepared/completed
вокруг source poll/prefix ingest/queue ingest/каждого role tick/endpoint/replay,
current external state refs, failure/read-before-group visibility и explicit recovery.
Старый PairedCashRehearsal single-use20–120s не менять и не считать v3 daemon.
Parent/whole-runner unknown commit recovery ещё не реализован; v2 helper не даёт
автоматического разрешения усыновить новый parent. W7b.3b unknown/native/action/storage/
source/parent/host recovery, bounded physical/source/delivery/index/native/capture
history/квоты/replay/whole-host capacity остаются открытыми. Physical SHA и старый
queue ingest всё ещё полные; W8.1 preflight оценивает прежний profile, не новый admission.

Actualpositive/publicprovider/fill/exit иlong stream/current-model/R1–R16/VP/W9/
review/economic gates открыты. Control cash_only не заменяет основную модель.
Original sealed cutoffs7ноября/21ноября00:59:16МСК; первый WF15ноября03МСК,
все6folds14апреля2027. Outcomes заранее не читать, research evidence не удалять.
Actual paper class в rehearsal работал только на synthetic market; publicrequests/
fit/model/risk/trading/realorders/primaryDBchanges0, все общие admissionflagsfalse.
Ниже прежние датированные scopes.

# Актуальный вход27октября — W8.2b.2a cached reader готов

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[runbook](CACHED_REFERENCE_READER_V2.md). AGENTS.md/TypeSafe обязательны.
Primary local PostgreSQL/PostgREST, LLM — другой агент. Historical804/body сохранять,
менять current summary + dated append. Старые source/model/runtime/registration pins не переписывать.

Новый cached_reference_reader_v2.py и20tests: pre-start контракт связывает
original queue/prefix/source identities, read только original pending role offer.
Packet source interval должен быть тем же whole poll, что cached view; exact source
bytes сверяются в обоих SQLite. Backlog/stale/foreign/acknowledged offers blocked.
Нет offer/ack/poll/worker effects; SourceReplay.feed внутри cached read не вызывается.
Physical SHA/queue attachment/full counts ещё линейные. Actual queue/cash app/runner
остались прежними; monkey-patching/type guard relaxation не применялись.

20new+18compat=38tests/10.14s, cumulative788;597oldPythonfiles сохранены, теперь599.
19accepted copies/17runtime keys. Synthetic3polls/12events/9packets/18cash decisions
совпали с old reader byte-for-byte,4positive synthetic decisions; worker/fills0.
Evidence .local/state/cached-reader-v2-work-20261027/verification.json.

Следующий W8.2b.2b — НОВЫЙ versioned cash-worker application, который явно использует
зарегистрированный cached reader и сохраняет его proof с actual prepared/completed
worker result. Original cash rule/queue/capture identity и safe ack сохранить.
Затем новый paired coordinator/recovery и bounded physical/source/delivery/native/
capture history/квоты/host/replay. W7b.3b unknown/parent/host recovery, actualpositive/
provider/fill/exit/long stream, current-model/R1–R16/VP/W9/review/economic открыты.
W8.2a compressed app v2 и W8.2b.1 source index готовы отдельно. Старый paired runner
single-use20–120s не стал новым долгим daemon.

Original sealed cutoffs7ноября/21ноября00:59:16МСК; первый WF15ноября03МСК,
все6folds14апреля2027. Outcomes заранее не читать, research evidence не удалять.
Publicrequests/actualworker/fit/model/risk/trading/orders/primaryDBchanges0 этим шагом,
общий paper/economic/live=false. Ниже прежние датированные scopes.

# Актуальный вход27октября — W8.2b.1 source prefix index готов

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[runbook](REFERENCE_PREFIX_V2.md). AGENTS.md/TypeSafe обязательны; primary local
PostgreSQL/PostgREST, LLM — другой агент. Старые source/model/runtime/registration
pins и804historicalcheckbox/body сохранять. Менять current summary + dated append.

Новые reference_prefix_v2.py, audit_reference_prefix_v2.py и18tests реализуют
отдельный pre-start cash-only SourceReplay index. Updates семантически проверяют
новые original events и сохраняют first-seen, state и cached view одной transaction.
Physical database SHA пока читается целиком; это не constant-time или long admission.
Explicit known checkpoint обязателен; unknown commit/stale pin/incomplete poll blocked.
Полный independent replay сверяет prefix/state/versions/projection. Recovery неизвестного
commit не реализован и остаётся W7b.3b. Actual source/delivery/runner не заменялись.

18new+100compat=118tests/17.99s, cumulative768;594oldPythonfiles сохранены, теперь597.
19accepted sources/16runtime keys. Synthetic6attempts/4polls/16events/12role packets
matched, feed4/4/4/0/4/0: original API cooldown соблюдён, no new observations on reuse.
Первый rehearsal с неверным ожиданием6new polls сохранён; версияv2 корректна.
Trueprocess-exit42 послеcommit блокирует старый checkpoint без автоматического усыновления.
Evidence .local/state/reference-prefix-v2-work-20261027/verification.json.

Следующий W8.2b.2 — versioned delivery/reader binding с original offers/role cursors/
ack/cash/worker contracts; не ослаблять old type(queue) guards. Затем bounded physical
source/index/native/capture history/квоты/replay/host и новый preregistered paired
coordinator/recovery. W8.2a cash archive v2 готов отдельно, existing PairedCashRehearsal
остаётся single-use20–120s без автоматического v2/resume. W7b.3b unknown/parent/host,
actualpositive/fill/exit, current-model/R1–R16/VP/W9/review/economic ещё открыты.
Original sealed cutoffs7ноября/21ноября00:59:16МСК; первый WF15ноября03МСК,
все6folds14апреля2027. Outcomes раньше времени не читать. Publicrequests/actualworker/
fit/model/risk/trading/orders/primaryDBchanges0 этим этапом; общий admissionfalse.
Ниже прежние датированные scopes, не текущая очередь.

# Актуальный вход27октября — W8.2a cash application v2 готов

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[новый runbook](CASH_APPLICATION_V2.md). AGENTS.md/TypeSafe обязательны.
DB local PostgreSQL/PostgREST; LLM-план выполняет другой агент.

Новые cash_application_v2.py, scripts/audit_cash_application_v2.py и19tests:
indexed-lossless-gzip-v2 сохраняет точные исходные пять файлов/receipt/ack SHA.
Normal step читает последнюю запись и максимум одну текущую группу; full post-end
stream audit обязателен, до end inspection metadata-only. Explicit recover только
одного fully completed шага, без повторных tick/provider/sourcepoll/ack.
Missing complete/result, unknown native/head и чужое role queue advance blocked.
Настоящий process exit42 после commit и после удаления raw copy проверен.

19new/97.65s +50compatibility cases в119.59s profile =69distinct/cumulative750.
19старых fixture failures не counted; затем19new прошли все. Прежние591Pythonfiles
сохранены, теперь594;57accepted copies/59runtime keys. Synthetic3roles/12applications/
6decisions/9heartbeats: controller/FIFO replay3/3, fills4/0/4, raw groups0.
Evidence .local/state/cash-application-v2-work-20261027/verification.json.

Следующий W8.2b: source/delivery/native/capture history и bounded replay/квоты/
диск, новый pre-start paired coordinator и recovery. Big group count сам по себе
не доказывает byte/throughput capacity. Старый W8.1 preflight оценивает прежний
profile, не даёт v2 admission. Старый single-use paired runner не получил v2/resume.
W7b.3b missing-result/unknown/parent/host recovery и actualpositive/long stream/
current-model/R1–R16/VP/W9/review/economic остаются открытыми.

Original sealed cutoffs7ноября/21ноября00:59:16МСК; первый WF15ноября03МСК,
все6folds14апреля2027. Outcomes раньше времени не читать. Research evidence не
удалять как operational feeder successes. Старые source/model/runtime/registration
pins и804historicalcheckbox/body сохранять. Никаких publicrequests/fit/model/risk/
trading/orders/primaryDB changes этим этапом; общий paper/economic/live=false.
Ниже прежние датированные статусы, не текущая очередь.

# Актуальный вход27октября — metadata capacity preflight готов

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[capacity runbook](CASH_CAPACITY_PREFLIGHT.md). AGENTS.md/TypeSafe обязательны;
DB local PostgreSQL/PostgREST, LLM — другой агент.

W8.1 реализован: cash_capacity_preflight.py, scripts/check_cash_capacity.py,
13new+19compat=32distinct tests/38.28s, cumulative731cases. SHA-bound metadata only,
exact UTC microseconds/end-exclusive5m poll slots, role ticks/source versions/
source+queue/capture/native/app/journal limits и disk/scratch envelope. --require-capacity
returns2 on blockers. Execution_ready и paper/economic/live всегдаfalse; pass не
даёт existing expired window launch или нового admission. Не выводить RSS из counts.

Actual existing60s metadata:12ticks/role/1poll/4source events/88journal rows — countpass.
Hypothetical30days с original UTCoffset:518400ticks/role,8641polls,34564source events,
minimum17520versions(no revisions),3144976journal records;26blockers. Original v1
app hardlimit1024groups, current frozen profile14groups; old caps не повышались.
Source/native/capture/journal capacities тоже недостаточны. Actual openat896paths
не содержит.sqlite/sealed/groups/.env, reports не открывали outcomes. Evidence
`.local/state/cash-capacity-preflight-work-20261027/verification.json`,61accepted
sources/runtime105entries и current/30dayJSON/trace рядом. Прежние588Pythonfiles
сохранены, теперь591; old source/runtime/model/registration pins не переписывать.

Следующий coding W8.2 — versioned scalable application journal/checkpoints,
bounded long-prefix replay и source/delivery/native/capture quotas/retention для
longscope, с новым pre-start coordinator/recovery contract. W7b.3b whole-runner/
unknown effects/missingresult recovery открыт: W7b.3a закрывает только durable
knownresult/ack. Short PairedCashRehearsal остаётсяsingleuse20–120s, не multi-daydaemon.
Research evidence не удалять как mutable operationalfeeder successes.

Actual short minute27октября13:40–13:41МСК:240rows/12ticks×3/6negative-cash decisions/
33heartbeats/0fills, independentcontroller/FIFO/coverage3/3, cgroupMemoryPeak≈33MiB
under512MiB cap. Actual instrument/bookprobeBTCETH2/2 passed(no fills). Actual
positive/fill/exit иlongpaired comparison, R1–R16/VP/W9/review/economic ещё открыты.
Closedcash cutoffs7ноября/21ноября00:59:16МСК; WF15ноября03МСК, outcomes заранее не
открывать. Fit/model/risk/trading/realorders0, economic/paper/live=false.
Historical804checkbox582x/222empty/body сохранять, current+datedappend обновлять.
Далее previous scopes, не текущая очередь.

# Актуальный вход27октября — known-result ack recovery готов

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[recovery runbook](CASH_ACK_RECOVERY.md). AGENTS.md/TypeSafe обязательны;
primary local PostgreSQL/PostgREST, LLM — другой агент.

W7b.3a: cash_ack_recovery.py +scripts/recover_cash_ack.py.17new+33unchanged
compatibility=50distinct, cumulative718cases. Known completed application prefix
и ровно один pending group, durable worker-result обязательны. Original cash
rules/packet/offer/source-prefix и полный worker frame/native/head proof,
explicit existing ReferenceDelivery known-ancestor recovery. Default writesonly
new read-only proposal; --apply-paper-ack добавляет только missing ack/complete,
не повторяет tick/provider/source poll. Existing ack/result/input/runtime pins
сохраняются. Новый application/current queue checkpoint сохранить отдельно.

Synthetic3cases beforeack/afterqueuecommit/beforelocalcomplete и true processexit42
после queue commit прошли. План сохраняет source bytes, recovery не повторяетworker,
последующий heartbeat исполняет2pending fills без новых intents. Baseline **585Python files сохранён**, теперь588;55accepted sources,
runtime59entries. Evidence `.local/state/cash-ack-recovery-work-20261027/verification.json`.

Следующий W7b.3b — missingworker-result/unknown native/action/storage or source
commit, whole-runner pending operation/lost checkpoint и chosen-host restart.
Старый PairedCashRehearsal single-use: **resume ему не добавлен**, component recovery
не закрывает parent journal и не продлевает original window/expiry. W8 scalable
long history/capacity/retention/review тоже открыт. Нельзя усыновлять новые DB SHA
как старые bytes, удалять pending или переигрывать неизвестную операцию.

W7b.2c.1 actual minute13:40–13:41МСК завершён:240rows/12ticks×3/6negative-cash
pairs/33heartbeats/0fills, independent controller/FIFO/coverage3/3, memorypeak≈33MiB
under512MiB cgroup. Separate actual instrument+book probe10:50UTC BTC/ETH2/2 прошёл,
4publicGET/rawnormalization pass; trades не создавались. W7b.2c.2 actualpositive/
fill/exit и longpaired stream остаются открытыми. Rules не ослаблять ради fills.
R1–R16/VP/W9/current-model comparison/economic gates открыты. Cutoffs7ноября/
21ноября00:59:16МСК иWF15ноября03МСК, outcomes заранее не открывать.
Fit/model/risk/trading/realorders0. Historical804checkbox582x/222empty/body сохранять,
current summary/checklist иdatedappend обновлять. Далее previous dated scopes.

# Актуальный вход27октября — short paired actual rehearsal завершён

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[runner runbook](PAIRED_CASH_REHEARSAL.md). AGENTS.md/TypeSafe обязательны,
primary local PostgreSQL/PostgREST; LLM — другой агент.

W7b.2a/b иW7b.2c.1 реализованы. Новый paired_cash_rehearsal.py,
scripts/rehearse_paired_cash.py,19tests;33cash compatibility passed. Текущий
набор52distinct, cumulative701с предыдущими профилями; не full repository suite.
Short20–120s single-use runner: public source polling, one-poll delivery,
3cash applications/workers,5s ticks/heartbeats, durable prepared/completed journal,
endpoint/seal/independent replay. Никаких попыток усыновить interrupted root.

Actual27октября10:40:26–10:41:26UTC завершён exit0:240BTC/ETH rows,
12ticks/role,0missed whole slots,6source decisions/33heartbeats,44ops,acks1/1/1.
Independent controller/FIFO/coverage replay3/3. **Actual fills0/0/0**: правила
momentum+cost buffer отвергли candidate/stress, control cash-only. Positive public
quote/fill/exit path не exercised этим run; synthetic buy/stop/sell3role proof
предыдущего этапа сохранён. Не ослаблять правила или повторять window ради fills.

Transient service cgroupMemoryMax512MiB, addressspace384MiB/child, timeout320s;
measured peak34648064bytes≈33MiB, swap0, runtime81.467s. После exit transient unit
GC: later systemctl defaultinfinity не runtime cap, брать live resource sample.
Evidence `.local/state/paired-cash-runner-work-20261027/verification.json`,
59accepted sources/runtime103entries, actual-spec/reference/registration,
actual-prospective originalsource/capture/application/journal/seals/replays рядом.
Прежние582Python files сохранены, теперь585. Эти runtime pins не переписывать.

Следующий остаток: W7b.2c.2 actual positive/provider/fill/exit и более длинный
preregistered paired stream; W7b.3 unknownpartial/lostcheckpoint/host recovery;
W8 bounded scalable history/retention/capacity/review. Текущие app JSON groups/
full source-prefix replay и short runner не объявлять multi-day daemon. Current
model/native/new-head/cash comparisons и остальные R1–R16/VP/W9 тоже открыты.
Не терять future cutoffs7ноября/21ноября00:59:16МСК, WF15ноября03МСК. Outcomes
заранее не открывать; fits/model/risk/realorders0, profitability/paper/live=false.
Historical804checkbox582x/222empty/body сохранять; current+datedappend обновлять.
Ниже предыдущие входы относятся к состояниям до этого actual run.

# Актуальный вход27октября — cash rules/application receipts готовы

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[runbook cash adapters](CASH_WORKER_APPLICATION.md). AGENTS.md/TypeSafe обязательны,
DB local PostgreSQL/PostgREST; LLM — другой агент.

W7b.2a/b реализованы отдельно от frozen worker/source: cash_entry_contract.py,
cash_worker_application.py, CLIcash_reference_application.py и33tests.
Hypothesis momentum-breakout использует closed candles/exact fractions и explicit
cost floor; cash-only control не legacy active model. Stress same rule/higher
cost floor, фактический fee/slippage config проверяется отдельно. Price forecasts
не потребляются, strategy SHA отдельные, это не доказательство прибыльного сигнала.

Все pairs одного полного poll получают decision/negative/skip/failure. Требуется
новая пустая prospective queue без priceartifact, batch events=len(pairs)+2.
Cash contracts→kernels→capture→application регистрируются до будущего start.
Реальный класс CapturedPaperWorkerV2 вызывается, сохраняются исходный prepared tick
и completed result; queue ack по SHAworker-result после durable write. Heartbeat
каждые5s нужен для pending fills/marks/exits между5m source polls; он не создаёт
source opportunity/ack. External checkpoint после каждого commit сохранять явно.
Unknown incomplete/lost ack/true process death блокирует retry, recovery ещё W7b.3.

Следующий W7b.2c — actual bounded paired runner/public provider/source polling/
5s role cadence, monitor/checkpoint persistence и endpoint/finalization. Старый
ReferenceCoordinator source-only/diagnostic-input-read; он не стал paper runner.
Default128groups/256MiB/scan15s — только bounded rehearsal, не multi-day study.
Native/current-model/new-head/cash comparisons ещё открыты. Original runtime/
source/model pins не переписывать, выполненные прошлые tests не повторять без причины.

33current+249compat=282distinct, по всем профилям682. Совместимость взята из278case
run;29cases прежней cash-ревизии исключены. Synthetic3role rehearsal12applications/
6opportunities/9heartbeats, independent worker/FIFO replay3/3, fills4/0/4. Он полностью
искусственный и не market/economic evidence. Accepted53source/test copies и receipt
`.local/state/cash-worker-application-work-20261027/verification.json`.
Прежние578Python files сохранены, теперь582. Historical804checkbox582x/222empty/body
сохранять; current checklist+datedappend обновлять. Sealed cash7ноября/21ноября и WF
15ноября03МСК заранее не открывать. Fit/model/risk/trading changes/orders0.

Actual feeder27октября10:15UTC:313retained successes/0retained failures/238prune
receipts; oldest retained26октября22:22UTC, не все20h continuity. BTC10:16UTC fresh,
120SQL/REST/SQLsameinstance. Feeder namespacev2 и installed17runtime files не менять
при работе с cash adapters. Далее предыдущие датированные входы.

# Актуальный вход26октября — managed reference feeder установлен

Продолжать [единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
AGENTS.md/TypeSafe обязательны; primary DB local, LLM — другой агент.

W6b.3b.2a/b выполнены: exact local Docker api/rest/db +SQL/REST/SQL120closed rows,
новый pinned managed runner установлен UID1000 в market-feeder service/timer.
Первый service cycle13:22UTC успешен; timer interval120s после завершения.
Child AS512MiB/75s/64KiB, service MemoryMax768MiB/TasksMax64; retained operational
cycles384MiB/720/24h, keep2latest success/allfailures, unknown pending blocks.
Automatic cycle13:24UTC и actual BTC/ETH freshness подтверждены. Полная outage/
restart/host-capacity qualification остаётся открытой, memory peak не измерен.
[Runbook](MANAGED_REFERENCE_FEEDER.md), evidence
`.local/state/reference-feeder-operation-work-20261026/verification.json`.
Registry `.local/state/managed-reference-feeder-v2-20261026`; original pins брать
из `deployment-registration.json`, не усыновлять unused v1 после runtime changes.

Следующий coding W7b.2: отдельные cash-entry policies/all actual opportunities и
actual CapturedPaperWorkerV2 application/results. Price forecast и input digest
не являются cash decision или trade. Начать с frozen contracts без их изменения;
новые adapters/strategies регистрировать отдельно до prospective start.
R6 cutoffs7ноября/21ноября00:59:16МСК; WF15ноября03МСК, outcomes заранее не читать.

151cases текущего профиля,43new; по четырём профилям564distinct. Прежние572Python
files сохранены. Local market DB writes и feeder units изменены; модель/risk/
trading units не менялись, fit=false/orders0/economic/paper/live=false.
Historical804checkbox582x/222empty/body сохранять, current+datedappend обновлять.
Ниже предыдущие входы описывают состояние до operational deployment.

# Актуальный вход26октября — reference-aware feeder proposal готов

Продолжать по [единому checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
AGENTS.md/TypeSafe обязательны, primary DB local PostgreSQL/PostgREST; LLM ведёт другой агент.

Сделаны W7b.1 coordinator, R6 safe calendar preflight и **W6b.3b.1 runner**:
[runbook](REFERENCE_AWARE_FEEDER.md), `reference_aware_feeder.py`,
`scripts/run_reference_aware_feeder.py`, `tests/test_reference_aware_feeder.py`.
Independent BTC/ETH sync before ranking, closed120 SQL probes, strict full-pair
sync health, immutable selected snapshot, venue cooldown10min, local-only,
child limits512MiB address space/64KiB output/75s stage. Обычный BTC failure
не подавляет ETH; rate limit останавливает оба до cooldown expiry.
17new+96compatibility=113tests passed /2.55s. Actual plan-only proposal сохранён,
`--apply-local` не выполнялся. Ни services, ни primary DB этой стадией не менялись.
Не объявлять BTC исправленным: installed feeder по-прежнему прежний, последний
SQL probe26октября BTCclose23октября14:05UTC/stale≈70h, ETH свежий.

Следующая operational задача **W6b.3b.2/R4**: квалифицировать chosen installed
path/ownership и реальный refresh, REST→instance linkage, repeated cycles,
restart/unknown partial writes, host/retention. Новый lease защищает только
новый runner на одном host, не старые процессы. Каждый run требует нового root;
не усыновлять partial stage receipts и не ослаблять original caps.
План и source/runtime pins для review:
`.local/state/reference-aware-feeder-work-20261026/actual-proposal/plan.json`.
Evidence/accepted11source/test copies:
`.local/state/reference-aware-feeder-work-20261026/verification.json`.

**W7b.2 также открыт:** отдельные cash-entry policies дляcandidate/control/stress,
все actual opportunities и durable CapturedPaperWorkerV2 application/result receipts.
Price forecasts/input-read acks не заменяют cash policy или worker execution.
R6 safe preflight до7ноября/21ноября00:59:16МСК не открывает unfinished payloads;
sealed-test/paper через этот путь не читать. WF first blind cutoff15ноября03МСК.
Никаких новых fits/admission/real orders из этих plumbing results.

Три профиля444/55/113 имеют91повтор: **521 разных tests**, не612/full suite.
Baseline до нового runner569 Python-файлов сохранён; теперь572. Исходные804checkbox
582x/222empty и historical body сохранять; current status/checklist и dated
append обновлять. Ниже подробные предыдущие scopes/receipts и оставшиеся gates.

## Предыдущий вход26октября: W7b.1 и guarded cash preflight

Продолжать W7b.2 cash-entry contracts/full actual opportunities/worker result receipts;
W7b.3/W8 recovery/host и W6b.3b primary reference refresh остаются открытыми.
AGENTS.md/TypeSafe обязательны; local PostgreSQL/PostgREST, LLM — другой агент.

Новое после W7b.1: [sealed cash preflight](SEALED_CASH_READINESS.md),
`sealed_cash_readiness.py`, `scripts/check_sealed_cash_readiness.py`,
`tests/test_sealed_cash_readiness.py`.14new+41compatibility=55tests passed /0.92s.
Actual frozen closed protocol calendar-only: inspected[],fit=false; openat trace
подтвердил отсутствие открытия `live-experience-memory.sqlite`. Source health
не сертифицируется. Все unfinished-window counts=null (не проверялись), не0.
Старые readiness CLIs не переписывались: до cutoff использовать новый guard.
Он никогда не открывает sealed-test/paper; после cutoffdevelopment только bounded
original snapshots. Путь protocol требуется явно, checksum/observed freeze проверяются.
Не подставлять legacy protocol с другими cutoffs. Counts/классы и fit до original
окон7ноября/21ноября00:59:16МСК не вычислять. First blind WF15ноября03МСК остаётся sealed.

Актуальный source recheck26октября: BTC close23октября14:05UTC/stale≈70h,
ETH close26октября12UTC/fresh. Local identity/schema/migration и offline source
receipts проверены. Feeder timer active/waiting, last oneshot success15:05МСК;
installed unit dynamic selection→selected sync, universe20pairs без BTC/ETH.
Это поддерживает reference refresh gap hypothesis, но не доказывает причинность.
Public research collector не исправляет primary SQL. DB читалась read-only,
сервисы/model/risk не менялись. Не заявлять старое BTC21октября как текущий last close.

Evidence/accepted11source/test copies:
`.local/state/local-cash-readiness-work-20261026/verification.json`.
Baseline566 Python-файлов сохранён; с новым guard теперь569. Исходные804 checkbox
и весь historical body сохранять, current summary/checklist и dated append обновлять.
W7b.1 прошёл444cases, guard55cases; эти два набора не пересекаются, не full repo suite.
Далее подробная история и ограничения source/delivery/worker contracts.

## Предыдущий вход26октября — после coordinator W7b.1

Прочитай AGENTS.md, обязательный TypeSafe skill, IMPLEMENTATION_PLAN.md,
[единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[coordinator runbook](REFERENCE_COORDINATOR.md), [delivery](REFERENCE_DELIVERY.md)
и предыдущие source/reader/kernel contracts. Рабочая БД — local PostgreSQL/PostgREST;
LLM-направление реализует другой агент, не включать его в этот план.

**W7b.1 реализован; следующий W7b.2 — cash-entry contracts/opportunities/worker wiring.**
Новые файлы `reference_coordinator.py`, `scripts/coordinate_reference_sources.py`,
`tests/test_reference_coordinator.py`. Bounded5m public source polling, original
price forecasts/explicit input skips, journal prepared/completed, source-tail
health, durable diagnostic packets/receipts/acks и completed-pass ancestor recover.
31new+413compatibility=444 разных tests passed /113.32s, не full repository suite.
Actual26октября два соседних окна11:54/11:55UTC:360closed rows/poll,
source events6→12/versions360→363/forecasts1→2, cursors2/2/2, packets6,
48coordinator records. Повтор первого окна без GET/новых events. Targets12:05/12:10UTC,
outcomes не читались, модель не переобучалась. Evidence/accepted17source/test copies:
`.local/state/reference-coordinator-work-20261026/verification.json`.


Actual replay сохранил35 initial missing5m slots: source namespace создан
08:56:27UTC, первый poll11:54:33UTC. Между двумя выполненными polls gaps нет;
current tail0 не отменяет initial gap. Continuous source completeness=false.

**Ограничения W7b.1:** встроенные consumers — диагностическое чтение inputs,
не cash worker execution. Prospective mode source-only и НЕ подтверждает workers;
diagnostic consumers нельзя включить с prospective start. Ни source polling
completeness всех strategy opportunities, ни profitability/host/live не доказаны.
`run --seconds` ограничивает допуск следующего прохода, не убивает начатую операцию.
После completed journal и потерянного внешнего receipt — explicit recover.
Commit component без coordinator completed/неизвестный pending/hot journal
не усыновлять: дальнейшие effects блокируются, recovery ещё W7b.3/W8.

W7b.2 начать с frozen PaperWorkerV2/CapturedPaperWorkerV2 и отдельных cash policy
contracts. Нельзя превратить existing price probability в `would_enter`, выдавать
input read digest за execution receipt или переписать старые runtime identities.
Новые adapters/policies регистрировать отдельно до нового prospective study.
Сохранять все negative/skip/failure opportunities, causal source/decision times,
role-specific candidate/control/stress identities и durable application results.

Новых исходных Python-файлов теперь566; baseline до W7b.1 был563 и не изменён.
Старые work roots/runtime/model/registration pins не переписывать. Исходные804
checkbox/body сохранять:582x/222empty. Обновлять current summary/checklist и dated
append, не менять historical statements. Primary DB/service/risk/model/order path
не менялись, их qualification остаётся открытой. Frozen cash cutoffs7ноября00:59:16МСК,
21ноября00:59:16МСК и first blind WF15ноября03МСК соблюдать; outcomes заранее не читать.
R1–R16/VP и W6b.3b operational reference refresh не потерять за paper plumbing.
Ниже сохранена предыдущая подробная история; её «следующий шаг» уже устарел.

## Исторический вход 23 октября — retained delivery W7a

Прочитай AGENTS.md и обязательный TypeSafe skill, IMPLEMENTATION_PLAN.md,
[единый текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
IMPLEMENTATION_RECONCILIATION_20261014.md, [delivery runbook](REFERENCE_DELIVERY.md),
[reader runbook](REFERENCE_SOURCE_READER.md),
[W6b runbook](REFERENCE_SOURCE_LEDGER.md)
и [W6a runbook](LOCAL_SOURCE_PROVENANCE.md).
Открытые R1–R16 и VP не терять из-за работы над paper plumbing.

**Следующий шаг — W7b coordinator/full opportunities/cash policies/worker wiring.**
W7a уже реализован: `reference_delivery_source.py`, `reference_delivery.py`,
`scripts/deliver_reference_sources.py`, `tests/test_reference_delivery.py`.
Append-only original source-event prefixes/head anchors, independent replay,
first-seen/revisions/failures/negative forecasts, ordered3role cursors/pending/ack,
whole-operation bounded chunks и explicit known-ancestor recovery.

**413 разных tests passed /27.98s**:39new+374compatibility, общий suite не запускался.
Actual diagnostic polls16:52:01/16:55:44UTC:360rows/poll, distinct versions360→363,
source events6→12, forecasts2. Source DB append изменил physical SHA, old pin
отвергнут. Retained inputs пережили append/new process: все3роли повторно прочитали
старые пакеты с теми жеID/time, затем новые; cursors2/2/2,14queue events/2batches,
0unresolved anchors/внутренних cadence gaps. Это input read receipts, НЕ cash worker
execution. Targets17:05/17:10UTC, outcomes не читались, модель не переобучалась.
Receipt: `.local/state/reference-delivery-work-20261023/verification.json`;
accepted15source/test copies и actual source/queue/role receipts рядом.

Не переписывать559предыдущих Python files или старые registration/runtime pins.
Source SQL bytes не копируются: original manifest/event/head SHA сохраняются,
старый DB SHA не подменяется новым. Retained inputs читает DeliveredReferenceReader.
Незавершённый source anchor не выдаётся ролям. После lost receipt разрешён только
explicit recover с known ancestor и полным replay; hot SQLite journal не удалять.
Single writer/coordinator обязан сохранять новые external descriptors после commit.
Capsqueue4GiB/scratch256MiB/chunk4MiB/delivery8MiB/ingest90s/replay60s/disk2048MiB+
reserves не ослаблять. Quota failure не должна продвигать archive/cursor.

**W7b:** automatic bounded coordinator/polling, monitoring текущего source tail,
полнота actual strategy opportunities/negative/skip/failure events, отдельные
candidate/control/stress cash-entry contracts и durable worker application/result
receipts. Ack сейчас проверяет только digest/order consumer receipt, не trade;
price forecast не превращать в `would_enter`. Начать с существующих frozen
consumer/worker contracts и сохранять их code/identity; новое wiring/strategy
contract отдельное prospective до нового study. Primary model/risk не менять.

**Завершённый W6b.3a reader, предыдущая проверка:**
`reference_source_reader.py`, `scripts/read_reference_sources.py`,
`tests/test_reference_source_reader.py`. Pre-start source/reader contract, immutable
frame с original source/forecast IDs и global first-seen, closed120 CandleRow и
features с precision28, три роли читают одинаковый frame SHA. Price forecasts не
превращаются в cash `would_enter`; admission требует отдельной strategy policy.

**374 разных tests passed /38.85s**:48new+326compatibility, общий suite не запускался.
Actual23октября08:19:49UTC:120AVAX+120BTC+120ETH ready, затем original AVAX forecast
08:20:19.991167UTC до target08:30UTC. Никакие outcomes этого прогноза не читались.
Offline source/frame replay и actual three-role read прошли. Compact inference
envelope304141→2906bytes сохраняет параметры frozen migration-v3`041b`, original
SHA01d88c...; exact probability equality с original artifact подтверждена.
Это отдельный diagnostic source artifact, не candidatea252 и не active model.
Actual probability0.14484000970793767 — price label diagnostic, не доход/сделка.
Evidence: `.local/state/reference-reader-work-20261023/verification.json`,
original protocol/model bytes и accepted12source/test copies рядом.

После этого этапа W7a реализовал retained history/role queue. Старый ReferenceMarketReader
остаётся strict к своему pinned DB; новый DeliveredReferenceReader читает retained
event prefixes после append. W7b должен связать delivery с actual coordinator/
cash policies/workers. Никаких реальных orders или silent adoption старых DB pins.

**W6b.3b остаётся открыт:** actual working reference refresh/primary linkage и
deployment health. Новый source/reader primary PostgreSQL rows не обновляет и
periodic service не устанавливает. Последний SQL read07:08UTC показал staleBTC≈32h;
после reader implementation primary DB не перечитывалась. Общие W6/W5 открыты.

**W6b.1/W6b.2 — предыдущий завершённый этап:**
`reference_sources.py`, `reference_source_ledger.py`,
`scripts/capture_reference_sources.py`, `tests/test_reference_source_ledger.py`.
Mandatory BTC/ETH не зависят от ranking; raw public Spot responses/actual clocks,
immutable source versions/first-seen, frozen price-model forecast IDs и source
replay сохранены в отдельном namespace. Негативные forecasts сохраняются, но это
price target, не cash-entry decision и не экономический допуск. Свежесть≤600s
считается от closed bar и observation; failed BTC блокирует ETH forecast.
Pending poll после crash нельзя автоматически повторить/усыновить.

Предыдущий этап:326 разных tests passed /25.09s:61new+265compatibility.
Actual public23октября07:51UTC:120BTC+120ETH ready, HTTP200,offline replay240versions/
4events,0forecasts. Source integrity=true; actual forecast linkage=false.
Evidence/accepted source copies: `.local/state/reference-sources-work-20261023/`.
Сохранена и первая sandbox network failure попытка:2URLError/0versions.
Primary SQL read07:08UTC:BTC close21октября23:10UTC,age115087.881843s,stale≈32h;
cluster/schema не изменились. ETH primary SQL сегодня отдельно не читался.

W6b.3a reader/explicit prospective contract и actual compatible forecast теперь
реализованы выше; повторно не писать. Public natural IDs не заменяют PostgreSQL
UUID. Полнота source polling/REST→instance linkage/host qualification открыта.
Не смешивать новое исследование с прежними manifest/pins/viewed windows.

W6a observer/contract/audit уже реализован:
`local_source_observer.py`, `local_source_provenance.py`,
`scripts/audit_local_source_provenance.py`, `tests/test_local_source_provenance.py`.
79 новых +186 compatibility =265 разных tests passed. Actual120BTC+120ETH rows
и отдельный offline CLI replay проверены; общий suite заново не запускался.
Accepted source/runtime snapshots и probes:
`.local/state/local-source-provenance-work-20261022/`.

W6a binds PostgreSQL cluster/database/schema/table/columns/defaults/indexes/
constraints/triggers/RLS, original UUID/xmin/raw row/query SHA и runtime до/после
чтения. Migration files привязаны hashes/inventory/restore receipts. Это direct
SQL source; REST→instance linkage и полнота всех actual sources не доказаны.
known_at консервативно actual query completion; imported timestamps остаются
source claims. Новый registered capture отвергает stale rows; diagnostic probe
нельзя усыновить как original registered study. Pre-start window/pins обязательны.

**Историческая диагностика22октября:**13:33UTC BTC last close21октября23:10UTC,
age51807s/freshness=false, ETH last close13:30UTC/freshness=true.
Installed feeder config делает dynamic selection→selected sync; в universe
snapshot13:29UTC BTC/ETH отсутствуют. Это гипотеза отсутствующего независимого
обновления reference pairs, не causal proof. Services не менялись.

Mandatory reference capture и source/forecast history mechanism готовы в
W6b.1/W6b.2 и reader W6b.3a; повторно не писать. W6b.3b — actual refresh.
Не использовать stale BTC-context или старые created/ingested times как
доказательство исторической доступности. Готовые W6a/W5a/W5b.1–W5b.3 не переписывать;
23октября сохранены552 прежних Python-файла, новые10 runtime/test copies pinned.
W7: complete shared polling, negatives/skips/failures/cursors/restarts и paired
candidate/control/stress delivery. W8: whole-worker RSS/payload/tick/network/
queue/disk/three-role capacity, crash cleanup и independent review. W9: qualified
candidate и НОВОЕ actual future study минимум30days/100closed trades по общему
плану; closed-cash14days/60trades protocol отдельный. Общие W5/W6 открыты.

Основная БД local PostgreSQL/PostgREST (`CRYPTOFORGE_BACKEND=local`). No cloud
fallback/повторной миграции. Owned paper/evidence SQLite roots отдельны.
Не менять старые protocol/runtime/source pins, approvals, budgets или viewed
windows. Любой новый contract отдельный, prospective, до actual study start.
Kernel/archive/capture/replay и W6a не выдают paper/economic/live admission.

Operational R1–R5 сохраняют приоритет: actual runtime/account/permissions/ownership,
controls/admission/risk/reservations/drawdown и exits/recovery ещё не квалифицированы.
Подготовленные opt-in flags не считаются включёнными без новой проверки deployment.
Не запускать executor/real orders/install scripts/model publication в read-only
preflight. Подготовка локального кода/tests допустима, primary model/risk сохраняются.

R6–R11: original closed bounded120 contexts, compatible candidate/control,
readiness, human20cases/historical execution coverage. Последний checked cash
preflight14октября:0eligible/8legacy incompatible; current counts нужно проверять
заново, старыеrows не backfill. Candidatea252 не подменяет migration-v3 candidate041b.
Train closed-cash ends7Nov00:59MSK, validation21Nov00:59MSK + counts gates.
R12/R13: full procedure/controls/folds; first blind test ends15Nov03:00MSK,
all6windows14Apr2027. Sealed outcomes раньше cutoff не читать.

Не повторять finished negative fixed/ATR4/4 (0passes), long/minute audits,
cached loss review, calendar/fold0 preparation. 20counterfactual labels,
20minute geometries и FIFO conservation есть; human/historical gates ещё открыты.
VP INT-01/09/10 и VP-00…09 не завершены. **LLM выполняет другой агент, не включать.**

При продолжении обновлять current checklist и подробный пункт одновременно:
ID/scope/receipt/date/command/sourceSHA/result/remaining gates. Исходные804checkbox
и исторический master body сохранять. Ниже прежний prompt/журнал для контекста;
старые «следующие шаги» и deferred counts не отменяют эту текущую очередь.

---

# Промпт продолжения CryptoForge

Скопируй текст ниже в чат, открытый в проекте `/home/arthur/Projects/personal/CryptoForge`.

---

Продолжи работу над обучением и проверкой торгового бота CryptoForge. Главный документ — `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md`, актуализация12октября2026, технические детали — `docs/FREQAI.md`. Цель: воспроизводимый поиск торговых ситуаций и обучение с проверкой результата после всех расходов; кандидат допускается только по доказательствам. Не обещай увеличение прибыли после каждого обучения.

Сначала прочитай актуальный раздел плана, применимые AGENTS.md/skills и текущие файлы. Не начинай реализацию заново. Git checkout сильно изменён, часть файлов менялась другим чатом: сохраняй чужую работу, не выполняй reset/cleanup/commit/push без соответствующего запроса. Последняя подтверждённая полная проверка в этом чате —880passed 11октября; сегодня это историческая отметка, а не новый запуск.

Что уже сделано и не надо повторно реализовывать:

- Архив Bybit Spot, dataset/source checksums, causal labels, purged chronological splits, simulator общего wallet с затратами, общий buy/sell/price-time core.
- Source-bound snapshots и original runtime bundles, immutable ResearchAttempts ledger, persistent configuration budgets, numerical audits, atomic private reports.
- Четыре train-window/recency variants, семь ablation variants и их portfolio comparisons, два balanced/unweighted classifiers. Все эти completed studies — ранее просмотренные development-данные.
- Economic screening13portfolio configs:0passes. Cash без сделок не назван заработком. Balanced classifier:36trades,net−0.759012651USDT/stress−1.400583590 приcapital100; без balancing0trades. Это simulation, не фактический доход аккаунта.
- Ablation безvolume_ratio немного улучшил RMSE, но все7portfolio variants сделали0trades. Признаки рабочей модели не удалялись.
- Явные price/net/cash target contracts; registry guards; новые primary artifacts объявляют fixed-future-return-v1. Cash/short labels нельзя выдавать за primary Spot-long price task.
- Append-only closed bounded120 feature stream и actual BTC/ETH parity audit:2556vectors/2562bounded signals совпали. Полная live execution parity не подтверждена.
- Readonly working-bot feedback, real execution/cash recovery memory, prospective forecast memory/outcomes, entry diagnostics поpair, ограничения freshness/source quality и paper harness.

Важные ограничения и состояние, которое нужно заново проверить:

- При последней сверке legacy cash training8buys:1positive/7negative; закрытый bounded120 study отделён и раньше имел0buys. Не смешивай их и не считай forecasts/simulated trades реальными покупками.
- Active legacy модель была устаревшей и имела неизвестный feature calculation contract. Новые closed bounded120 candidates не заменяли её: insufficient_signals и incompatible_feature_calculation_contract. Не восстанавливай неизвестный контракт по имени или догадке.
- Последний проверенный candidate041b283bc8/sha01d88cd66354268a92adb9663a428e27b720c9e745d94613e4f6b9f8a0517a20 прошёл original input/metrics/source audit;11novel signals на420examples недостаточны для допуска. Estimated fixed-candle returns не являются executed income.
- Статусы моделей/таймеров/числа сделок устаревают: прочитай свежие отчёты и журналы, не объявляй эти числа текущими без проверки.
- В ходе работы менялись kernels и primary producer metadata. Old frozen source fingerprints нельзя переписывать. Некоторые старые strict replay checks теперь должны отказать из-заsource drift; historical results/original bundles сохраняются. Source-difference audit возможен только с явным указанием ограничения, без автоматического исполнения archived code.
- Completed ablation retry timer отключён после7/7fits и portfolio completion. Основные training/feedback timers при последней проверке enabled. Не возобновляй завершённый поиск как новую попытку без причины.

Порядок оставшейся работы:

1. Проверь текущее состояние основного обучения, active/candidate artifacts, freshness, input/target contracts, source admission и причины недопуска. Разделяй отсутствие стратегии, no_fresh_model, dust/minimum constraints, нехватку наблюдений и отрицательный payoff.
2. Продолжи уже работающий prospective feature migration v3 (SHA700119966617653d6be5d011b009821ff35383ea91304c56bd02206d56c38c24, NEAR/APT, frozen041b candidate и baseline без ML). Сборщик и таймер реализованы; первые price outcomes появились12октября. Проверь новые receipts, не перезаписывай source-bound протокол. Price endpoints не являются доходом или execution qualification. Подготовь дальнейшее candidate/control исполнение только после соответствующих gates. Для неизвестного legacy контракта нужна независимая prospective candidate/control проверка; нельзя просто присвоить старой модели новые metadata или убрать comparison guard. Реализуй выполнимые части и preflight без live замены.
3. Закрой execution/source gaps: point-in-time universe/rules/fees/spread/depth, partial/rejected fills, exit minimums, base/other sale fees, residual ownership и basis. Проверь вручную минимум20source-bound labels с gaps, ambiguous stop/target и fee/boundary cases. Unknown не заменяй сегодняшними правилами или оптимистичным fill.
4. Выполни только заранее зарегистрированные исследования стратегии: реальная baseline без ML, frozen current-model control, cash-only и явно заданный buy-and-hold context при одинаковом капитале/риске. ATR/filters/support-bounce/compression families допускаются после observed protocol/source freeze и budget reservation. Не выбирай новые параметры по старому test/paper.
5. Threshold выбирай на validation по shared-wallet net/stress payoff, minimum ordinary/stress trades и drawdown, с полной declared grid и immutable report verification. Уточни natural-distribution calibration на достаточных периодах. Не превращай class-weighted score в доказанную вероятность.
6. Реализуй и квалифицируй walk-forward процедуру целиком: calendar windows, nonoverlapping test, purge поlabel_end_time/availability, embargo, train-only preprocessing, all previous information cutoff, paired temporal block bootstrap общего wallet, budget/multiple-search accounting и concentration checks. Viewed development не становится blind test при новом названии файла.
7. После квалификации создай новую observed paper execution/source policy и проведи candidate/control forward stream с полными receipts, fills/rejections/exits/fees/net equity. Сверь replay того же будущего периода. Продли наблюдение при нехватке дней/сделок. Численные требования бери из соответствующего frozen protocol: общий30day/100trade paper и closed-cash14day/60trade acceptance нельзя смешивать.
8. Подготовь concrete reviewable admission/rollback/monitoring результат. Live замена требует выполненных gates и соответствующего разрешения; не публикуй неподтверждённую модель ради свежести или сбора100buys.

Как работать:

- Сохраняй действующие stake/positions/daily-loss/stop/TTL/ML gates. Не включай новые реальные ордера и не обходи quality/freshness/source guards для ускорения результатов.
- Перед actual research: RAM≥1536MiB,disk≥2048MiB, один offline worker, исходные wall/memory/flock limits. Не понижай floors. Deferred значит не выполнено; изучи другой независимый пункт, который можно сделать без этого запуска.
- До outcomes/fitting зафиксируй source/config/data hashes, параметры, дату наблюдаемого freeze, budget/grid и затем registration. Не расширяй старый frozen budget после просмотра результатов.
- Сохраняй immutable original inputs/runtime/results, Python/dependency/commit/dirty/seed/cutoff receipts; не создавай provenance задним числом. Seed=None допустим для явно deterministic fit.
- Разделяй implementation, actual development evidence, independent qualification и live admission. `[x]` ставь только за реально выполненную проверку. Не закрывай весь этап по unit tests или одному25-hour срезу.
- После изменения запускай уместные проверки; полный suite после существенного набора изменений, не повторяй его без причины. Для synthetic test files можно использовать `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp /dev/shm/cryptoforge-<unique>`. Это не обход actual research guards.
- Обновляй план и checklist после каждого проверенного результата: точные commands, source/protocol/study IDs, числа, риски/ограничения и следующий незавершённый пункт. Исторические записи не переписывай как текущие.
- Продолжай полезную работу по выполнимым пунктам, не заканчивай ход после каждого небольшого блока. Не расходуй лимит на повторные бессодержательные проверки, пустые рассуждения и искусственный перебор. Если требуются будущие данные/внешнее состояние, честно зафиксируй этот конкретный blocker, не имитируй completion; переходи к другой выполнимой работе.
- Не говори «всё выполнено» или «лимиты исчерпаны», если это не подтверждено. Не обещай автономное продолжение, которого реально не настроено.

В итоговом отчёте укажи: что реально закрыто, чем проверено, какие gates остаются и почему, какие файлы/протоколы созданы или изменены, менялись ли active model/live orders. Ссылка на актуальный план обязательна. Отсутствие прибыльного кандидата — допустимый научный результат, а не повод снять защиту.

Текущий simulator поддерживает explicit preserve_inventory exit policy. Используй его в новом frozen execution scenario; legacy_assumed не сертифицирует исполнение. Open inventory/basis учитывается отдельно, cash difference не подменяет realized PnL. Исторические frozen reports не переписывать после изменений simulator/config.

Дополнение12октября:903fulltests passed; latest4298b candidate exact input/source audit verified. Реальный saved FIFO49closedsegments net−1.3055964USDT,16segments≤−1%; explicit-wallet23coinsconsistent. Новый audit_execution_cache сохраняет original input/runtime. Identity/inventory/private wallet code изменён: execution policies требуют нового source freeze, не backfill старых SHA. Migrationv3 остаётся active иcurrent-sourceverified:200price endpoints/1day/2pairs,0MLsignals,baseline23negative estimated opportunities; не доход. Labelaudit --exit-minimum-policy preserve_inventory поддерживает source references, ноactual1000barBTC/ETHrun resource-deferred;20manualreviewsнепройдены. Продолжить feasible code/source qualification и registered studies при достаточных ресурсах.

Последнее продолжение12октября:913fulltests+18finalcalendarfocused. Walk-forward guards теперь проверяют ручные Fold и secondary outcome cutoffs/recovery clock/SQLite identity; capture timestamp не outcome cutoff. Реестр readonly15:19UTC: oldactive09b486e979 unchanged, latest4298b rejected fails_baseline_or_costs (400unseen/30signals, estimatedaftercost−1.9457%,accuracy75.75%<majority78.75%; incompatible legacy contract). Не публиковать. Strictarchiveaudit1000BTC/ETH всё ещё resource-deferred; существующий audit receipt нельзя overwrite, выбирать новый output.

Последняя проверка12октября:930passed. Validation threshold требует four explicit ordinary/stress open inventory/exit-minimum counts==0; unknown reports исключаются без backfill. Paper acceptance проверяет consistency full/retained mark counts/drawdown/gaps. Эти source changes требуют новых registered manifests/paper policy versions. Actual RAM1337<1536MiB: research deferred, floors сохранять. Не повторять бессодержательные попытки запуска до изменения ресурсов; продолжать независимые реализационные пункты и исходную квалификацию.

13октября:940tests passed. Новый strict migration calibration report642endpoints,Brier.1302435vsfrozenprior.1339941,0signals≥.5; это exploratory no selection/income, не loweredthreshold. Original input/source/runtime snapshots сохранены. Instrument current snapshot527symbols и source-bound raw rule/top-of-book APT/NEAR captured; execution market verifier воспроизводит normalization с исходными response/time/checksums. Current snapshot не backfill в исторические rules; fills/fees/partialexecution всё ещё не qualified. InitialRAM1275<1536, actualofflinearchiveaudit не стартовал. Продолжить оставшиеся checklist источников/процедуры/независимой оценки, original frozen manifests не переписывать.

Последнее продолжение13октября:950tests passed. Instrument receipt read проверяет SQL identity/time/count/pagination и originalsource bounds. Account fees captured/replayed readonly APT/NEAR maker0.10%/taker0.18% at13:31UTC; original receipts и runtime сохранены, настройки не изменены. Unknown fill fee asset/historical tariffs не backfill. Strictsourcearchiveaudit1000BTC/ETH13октября снова resource-deferred, output не создан даже после cleanup собственных finished pytest tmpfsdirs.20manualcases/qualified candidate/futurepaper остаются открытыми.

Последнее продолжение13октября:953tests passed. Paper_fill_audit теперь independently replay recorded fill/segment math иqty conservation вexport/source manifest; старые paper policies не backfill, новый observed version обязателен. Actual strict archive source audit finallycompleted с исходным resourceguard:BTC/ETH700developmentbars,651labels/pair,20numeric source samples/pair, alltimeout. Receipt trade-label-strict-source-audit-20261013-paper-replay.json. Source windows preserved, manual_review_complete=False; gaps/ambiguity/unclosed/historicalfilterfee checks остаются открыты. Это важный выполненный numeric step, но не прибыльность илизавершение всего этапа.

Последнее13октября: full957tests +3finalfocused. Wide source audit/replay40cases completed (34timeout/6stop,17fee-erased gains), original runtime/input windows pinned. replay_label_audit.py has strict market identity. Long25919bars andATR actualruns deferred; gaps/ambiguity/unclosed source cases absent in current3500bar slice andremain open. Не отмечать весь manual/source этап закрытым; sourcebound wide report and replay-market receipt under .local/state.

Последнее13октября:966tests passed. Added intrabarcoarse availability andfrozenstake auditguards. Backgroundlong label auditinstalled: activejob0fd8a8a7fd135e3782d3a71574c5bf3f56d4314a711c02cdea6afcbb3fdb686a, fixedcode/data/runtime,15minretry,originalresourcefloors. FirststatusdeferredcompletedFalse; completion requiresfull18143bars/pair andsamplecoverage, not partialreport/processsuccess. Timerautodisables oncompletion/sourcefailure. Before touching dependencies, inspect currentjob status; source drift mustblockandneednewobserved job, nobackfill. Oldf0c...supersedednotcompleted. Это автоматизация толькоlong numeric audit, неwholeplan/livepublication.

Последнее13октября:973tests passed. Newregisteredstudy8280273c066be801e85e1d22b8f1d391c0d492c5888e593e4054e9e3fe133123:twoextensions×fixed/ATR,4attemptsreservedbeforeoutcomes, original100/family budget retained. Native baseline riskmatched,notMLsubset; legacyMLcontrol/BHcontext remainopen.20minextensionretryinstalled,currentstatusresource-deferred0/4. Completegrid+immutableledger+timing verification required,success/partialresultsnotcompletion. Checkbothbackgroundjobs before touchingdependencies; original sourcehashes no backfill. Actualprofitablecandidate/independentwindows/paperstillnotqualified.

Последнее13октября:976tests passed. SeparateBHcontextstudy9e6e60083d2736883c39db80d8b2e6877563ac9e9ee6b107b971deed49913917,1reserved,20minretryactive,firstresource-deferred0/1. Samecapital/stake/data,stop/targetriskdifferent;allinitialcosts reserved beforeterminalproceeds;unsellablebasis retained. Originalextension8280273c...unchanged. Threejobs pending(resourceguards),noactual income results. Checkstatuses first; donotmutate frozen sources/manifests; waitindependentcalendar/paper gates ratherthanmarkcompletion.

Последнее13октября:979tests passed. Sixsampledstopcases minute sources captured30bars complete6/6; receipt3bd26e7b0d373a2c7a59e58e3d431226ac15104993b4086a1e44809549e2a259 underintrabar-stop-cases/f5a3de.../receipts. New audit_stop_case_minutes.py --ingestion .../latest-ingestion.json --output .local/state/stop-case-minute-audit-20261013.json remainsresource-deferred (statuscompletedFalse). Mustrununderoriginalguards;donotclaimrealgapsorfillcertificationfromcapture/synthetictests. Optionalinspect_unambiguous=True supportsfinerreferenceaudit;nativeexitpolicyunchanged. ExistingOctober1hourBTC/ETHminute artifactsalreadyexist;originalBTCsource consistency passed10Oct,notnewwork.

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


## 18 октября: R2/R14 — segmented storage завершён отдельно от capture v3

- [x] `evidence_segments.py`: bounded segments/global budget, durable exact
  pending recovery/retry, original pins и read-only streaming structural audit.
  38 новых тестов; **1764passed,1deselected /421.60s**. Synthetic10 005events,
  21segment, audit1.246s и peak148 779bytes Python allocations; это не process RSS.
- [x] Native runtime и прежние capture/lifecycle SHA сохранены. Evidence:
  `.local/state/paper-segments-work-20261018/verification.json`.
- [x] Capture v3 adapter, bounded native wallet/worker source archive и capture v4
  реализованы последующими этапами.
- [x] Streaming wallet cash/FIFO/valuation/coverage реализован19октября;
  full worker/strategy economics остаются открытыми. Детальный acceptance checklist
  в EVIDENCE_SEGMENTS.md: original row IDs, crash commit boundaries, day/FIFO
  anchors, sealed-window gate и общий бюджет трёх ролей. Не реализовывать storage
  заново и не вызывать history-accumulating snapshot/auditor на длинном study.
- [ ] Long-study ещё BLOCKED, min30days/coverage не сокращать; затем реальные
  payload/RSS/full-tick measurements, full runner/roles, новый protocol/candidate,
  future data и independent review. Storage pass не paper/economic/live pass.

Frozen studies/services/model.active не менялись; LLM остаётся в другом агенте.

## 18 октября: R2/R14 — capture v3 реализован, следующий native archive

- [x] Новый capture v3 protocol/role/registration/runtime/native schema,
  segmented prepared/complete/terminal и original native row IDs/hashes.
  Sealed read-only source/operation audit и no-retry после unknown native
  outcome реализованы. 45focused tests passed /16.19s; полный **1809 passed, 1 deselected /438.15s**.
- [x] Bounded native wallet/worker archive реализован19октября, сохраняя original IDs,
  cash/FIFO/day anchors, atomic seen→intent linkage и pending exits. Нельзя
  удалять active source rows до durable verified archive/checkpoint.
- [x] Streaming fill arithmetic/FIFO/valuation/time coverage реализован19октября.
- [ ] Full worker/strategy/source replay:
  старые snapshot/fill auditor и CoverageTimeline накапливают историю в RAM.
  Full worker/host/RSS/трёхролевая resource qualification и admission открыты.

См. PAPER_CAPTURE_V3.md. Long-study не запускать до полного source/resource/
economic qualification. V1/v2/native frozen sources и LLM другого агента не менять.

## 19 октября: R2/R14 — source archive готов отдельно от capture v4

- [x] `native_paper_archive.py`: new-root indexed shards, original row IDs/hash
  chains, global budgets, bounded native projections и atomic cleanup/checkpoint.
  Archive-aware wallet/worker сохраняют cash/day/FIFO/pending-exit контекст,
  не считают archived predictions unseen и не повторяют terminal intents.
- [x] 36focused cases passed /7.63s; subprocess-death на трёх commit boundaries,
  source/metadata corruption, shard-full и rollback half-link проверены.
- [x] Итоговый полный прогон: **1846 passed, 1 deselected /359.50s**,37новых cases.
  Synthetic10 005rows/4shards: запись/compaction/seal 9.97s, audit 1.729s, peak Python allocations 154845bytes, active worker file 32768bytes; не actual market/RSS qualification.
- [x] **Capture v4 integration реализована следующим этапом:** новый prospective protocol/registration,
  causal prepared/complete и archive/checkpoint references, sealed end-window CLI.
  Не пытайся DELETE/migrate старые v3 roots: их contract count=max(ID) сохранён.
- [x] Streaming wallet FIFO/fill math/valuation/time coverage реализован следующим этапом.
- [ ] Full worker/strategy/source replay, actual market/state/process RSS/full-tick/
  shared-role/host qualification и admission.

Native source-only seal не разрешает раскрывать будущие paper outcomes и не
доказывает доходность. См. NATIVE_PAPER_ARCHIVE.md; source/test receipts:
`.local/state/native-paper-archive-work-20261019/`. LLM — другой агент.


## 19 октября: R2/R14 — capture v4 интегрирован

- [x] Новый prospective protocol/registration связывает native/event manifests,
  original role/config/runtime и parent study. Старые roots не мигрируются.
- [x] Все доступные wallet mutations и compaction записывают original deltas,
  bounded logical source commitments и checkpoints. Unknown prepared не retry;
  exact stored-complete восстанавливается без native resubmit.
- [x] Terminal/end/grace и read-only CLI без --as-of;52focused cases /46.05s,
  включая actual process-death и rehashed false source trace. Итоговый общий **1898 passed, 1 deselected /536.74s**.
- [x] Streaming cash/FIFO/fill arithmetic/valuation/known-time coverage replay
  реализован следующим этапом.
- [ ] Продолжай full worker/opportunity/decision/source capture и shared roles.
- [ ] Actual payload/state/process RSS/full tick/network/queue/disk/host и
  power-loss qualification, independent review, qualified candidate и future study.

См. PAPER_CAPTURE_V4.md. Source/checkpoint trace pass не paper/economic/live
admission; active model/services/risk и LLM другого агента не менять.
Receipts: `.local/state/paper-capture-v4-work-20261019/`.


## 19 октября: R2/R14 — independent streaming wallet replay

- [x] Отдельный replay registration до original start, frozen runtime/resources,
  private bounded scratch index и constant-size coverage. Старые sources не менять.
- [x] Independent cash/fees/FIFO/valuation/day anchors и полный native row transition,
  raw source expiry/completion/endpoints, pending/material/dust/final-source guards.
- [x] 65focused passed /36.83s; synthetic10 005marks, scratch1 216 512bytes,
  active384bytes/peak Python allocations72 208bytes; это не process RSS/full capture.
- [x] Short legacy independent replay matched2fills/3marks/1segment/cash;
  source-consistent false dust label rejected. Receipts и fixture sources сохранены.
- [x] Итоговый общий non-integration streaming replay: **1963 passed, 1 deselected /470.87s**.
  Final source SHA/log/receipts сохранены в `.local/state/paper-streaming-replay-work-20261019/`.
- [ ] Продолжай full worker opportunity/decision/source capture и paired roles,
  затем actual source/RSS/full tick/queue/network/disk/host/resource qualification,
  independent review/qualified candidate/новый actual future study по gates.

См. PAPER_STREAMING_REPLAY.md. Wallet math pass не strategy/economic/live pass.
Не выполнять LLM-план другого агента. Model/services/risk не менять.
Receipts: `.local/state/paper-streaming-replay-work-20261019/`.

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
- [x] W5a: отдельные v2 wallet/worker/math, local pre-start kernel contract;
  см. PAPER_PRODUCER_V2.md. Старые kernels и receipts сохранены.
- [x] W5b.1–W5b.3: bounded archive/capture/replay v2 реализованы; causal
  high-water/counter, exact allocation и post-SQLite-lock observation проверены.
  Actual producer qualification зависит от W6–W9.
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
- [x] W5b.2: whole-worker capture и pre-start pins/kernel/archive/14groups/actual
  native clocks реализованы21октября; см. PAPER_WORKER_CAPTURE_V2.md.
- [x] W5b.3: independent replay новой schema реализован21октября; exact sizing,
  512-place allocation, causal counter/clocks, original-window valuation, adversarial
  forgeries и bounds проверены. См. PAPER_WORKER_REPLAY_V2.md; frozen verifiers сохранены.
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
- [x] W5b.2: capture v2 реализован21октября; original kernel/archive/ready pins,
  14groups/checkpoints/native clock parents и post-lock guard проверены.
  Unknown action/tick не принимается через storage recovery. См. PAPER_WORKER_CAPTURE_V2.md.
- [x] W5b.3: independent replay v2 реализован21октября;14groups, sizing/FIFO,
  512-place allocation, native clock sequence/cutoff и original-window valuation
  проверены с adversarial source-consistent fixtures; см. PAPER_WORKER_REPLAY_V2.md.
- [ ] W6/W7: local instance/schema/migration/known_at provenance, full shared
  polling/negative/skip/failure delivery и paired candidate/control/stress runner.
- [ ] W8/W9: whole-worker payload/RSS/wall/network/queue/disk/three-role capacity,
  independent review, qualified candidate и новое actual study минимум30days/economics gates.

W5 целиком открыт. `native_source_integrity_pass` подтверждает storage/active
projection; full worker/host/paper/economic/live admission flags=false. Actual API/
orders/fit/model publication/trading services/primary DB/risk этим этапом не менялись.
LLM ведёт другой агент. [Подробности и acceptance checklist](NATIVE_PAPER_ARCHIVE_V2.md);
receipts `.local/state/native-paper-archive-v2-work-20261020/`.
