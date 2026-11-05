# Карта интеграции CF-VP-2026-10-17

R4/R15 и R7: [competing writers](../FEEDER_COMPETING_WRITERS_20261028.md), [training status](../MODEL_TRAINING_STATUS_20261028.md); economic qualification открыта.

R4/R15: [selected_sync current observations](../FEEDER_SELECTED_SYNC_OBSERVATION.md), actual recovery открыт.

28 октября: [повторный разбор доступного cache](../EXECUTION_CACHE_REVIEW_20261028.md), не свежая история биржи.

R4/R15: [current feeder guard](../FEEDER_GUARD_CURRENT_20261028.md), actual recovery открыт.

R6/R15: [runtime inventory](../FORECAST_RUNTIME_INVENTORY.md), фактический cutover не выполнен.

R6/R15: [synthetic outcome ID/replay rehearsal](../FORECAST_OUTCOME_ID_REHEARSAL.md), реальный collector не изменён.

R6/R15: [composite read rehearsal](../FORECAST_RETENTION_READER.md), live wiring не выполнен.

R6/R15: [offline split rehearsal](../FORECAST_RETENTION_REHEARSAL.md), не runtime cutover.

R6/R15 28 октября: [retention preflight](../FORECAST_RETENTION_PREFLIGHT.md)
проверил кандидаты на snapshot; actual split и восстановление записи не выполнены.

Дата: 18 октября 2026, Europe/Moscow. Это карта зависимости дополнительного
направления VP от существующей реализации. Прогресс ведётся в
[основном исследовательском плане](../PROFITABLE_STRATEGY_RESEARCH_PLAN.md#cf-vp-2026-10-17---video-derived-strategy-research);
полный acceptance contract — в
[предоставленной спецификации](../CryptoForge_VP_Research_Checklist_ActivePlan.md).
Корневой IMPLEMENTATION_PLAN.md остаётся контекстом проекта.

LLM-план выполняет другой агент. Его очередь исключена из этого master-плана
и prompt продолжения. Созданные диагностика, CLI, тесты и результаты сохранены.

Operational diagnostic update 28 октября: [forecast health](../FORECAST_MEMORY_HEALTH.md)
в06:11 выявил полный ledger и279 старых незакрытых price forecasts; это не
источник cash labels и не VP qualification. Безопасный cutover остаётся открытым.

Operational feeder update 28 октября: [read-only inspection](../FEEDER_INCOMPLETE_INSPECTION.md)
проверил original source receipts; selected_sync остаётся unknown. SQL/REST/SQL
binding120 в06:08 МСК подтвердил BTC stale и ETH fresh; recovery/source continuity
и VP qualification открыты.

Operational update 28 октября: [diagnostic forecast snapshot и restore drill](../FORECAST_MEMORY_SNAPSHOT.md)
выполнены; actual source остаётся полным. Восстановление writers/readers и
отдельный backup ещё не закрыты, price diagnostics не cash labels и не VP qualification.

Текущий W8.2b.3a status27октября: [bounded paired coordinator](../PAIRED_CACHED_COORDINATOR.md)
работает в отдельном registered paper namespace;22new+36compat=58tests,
cumulative827. Synthetic12ticks/fills4/0/4 и независимый replay3/3 не закрывают
actual market, unknown recovery, host capacity, INT/VP или economic gates.

Operational update 27 октября 23:21 МСК: [read-only диагностика](../NO_BUY_DIAGNOSIS_20261027.md)
показала устаревшую active primary model, заполненный forecast store и незавершённый
feeder cycle; current BTC freshness и real-buy collection не считать готовыми.
R4/R15, R6–R8/R12 и future paper остаются prerequisites VP, не VP qualification.
См. [действующий checklist](../PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).

Текущий W8.2b.2b status27октября: [cached actual paper application v3](../CACHED_CASH_APPLICATION_V3.md)
реализован отдельно.17new+39compat=56tests/cumulative805; reader proof внутри
actual input/result/ack chain. Synthetic source/controller/FIFO audits3/3,
fills4/0/4; это не actual live market qualification. Следующий W8.2b.3 coordinator/
recovery, physical history/W7b.3b/actualpositive/INT/VP/economic gates открыты.

Текущий W8.2b.2a status27октября: [cached original-offer reader](../CACHED_REFERENCE_READER_V2.md)
реализован отдельно.20new+18compat=38tests/cumulative788; synthetic9packets/
18cash decisions совпали с old reader. Это input-only proof, actual worker не
исполнялся. Backlog/stale/foreign offers blocked. Следующий W8.2b.2b actual cash
application wiring; coordinator/physical history/W7b.3b/actualpositive/INT/VP/economic открыты.

Текущий W8.2b.1 status27октября: [incremental source index](../REFERENCE_PREFIX_V2.md)
реализован отдельно.18new+100compat=118tests/cumulative768; original first-seen,
new-event replay и full independent audit. Synthetic12role packets matched,
cooldown создаёт0new events. Это input parity, не worker execution/long admission.
W8.2b.2 delivery/reader/physical history/native/capture/новый coordinator и
W7b.3b/actualpositive/INT/VP/economic gates остаются открытыми.

Текущий W8.2a status27октября: [indexed cash application v2](../CASH_APPLICATION_V2.md)
реализован. Exact receipt bytes/ack SHA, проверка последней записи, post-end полный
аудит и explicit one-completed-step recovery;19new+50compat=69distinct/cumulative750.
Synthetic controller/FIFO replay3/3, fills4/0/4; actual market qualification не получен.
W8.2b source/delivery/native/capture/новый coordinator, W7b.3b/actualpositive/INT/VP/
economic gates открыты. Старый runner не получил v2/resume автоматически.

Текущий capacity status27октября: [metadata preflight](../CASH_CAPACITY_PREFLIGHT.md)
W8.1 реализован:13new+19compat=32distinct/cumulative731. Current60s countpass,
30dayhypothesis26blockers, no SQLite/outcomes/.env read. Это не longscope admission.
W8.2 scalable history/checkpoints и W7b.3b/actualpositive/INT/VP/economic остаются открытыми.

Текущий recovery status27октября: [explicit known-result paper ack](../CASH_ACK_RECOVERY.md)
W7b.3a реализован:17new+33compat=50distinct, cumulative718. Full original source/
worker proof и durable result обязательны; tick/providers не повторяются.
Synthetic failure cases/trueprocess-exit проверены. Whole-runner/unknowneffect/
host recovery W7b.3b и W8/INT/VP/economic gates остаются открытыми.

Текущий runner status27октября: [bounded paired rehearsal](../PAIRED_CASH_REHEARSAL.md)
реализован:19new+33compat=52distinct, cumulative701. Actual240source rows,
12ticks×3/6decisions/33heartbeats/0fills, independent controller/FIFO/coverage3/3.
Peak≈33MiB under512MiB cap. Это short negative case; actualpositive/recovery/
long capacity/INT/VP/economic gates остаются открытыми. Primary model/risk/orders
не менялись. Ниже previous scope.

Текущий статус27октября: [cash-entry/worker application](../CASH_WORKER_APPLICATION.md)
W7b.2a/b реализованы: explicit role hypotheses, all fixed-pair decisions,
actual CapturedPaperWorkerV2 result receipts/ack и heartbeats.33current+249compat
=282distinct, cumulative682. Synthetic3role replay3/3 не закрывает INT/VP/economic.
W7b.2c actual paired runner/providers/source/cadence/finalization, W7b.3/W8 открыты.
Feederrecheck313retained successes/238prunes, BTCfresh120; historical continuity/
host/outage gates не выданы. LLM по-прежнему вне очереди. Ниже previous scope.

Текущий статус26октября: [managed reference feeder](../MANAGED_REFERENCE_FEEDER.md)
установлен UID1000 на market-feeder service/timer, первый cycle13:22UTC успешен.
Локальные market rows обновлены; exact120SQL/REST/SQL подтверждены, BTC fresh.
151tests/43new, четыре профиля564distinct. Automatic timer cycle13:24UTC подтверждён; длительные
outages/host и W7b.2 actualcashworkers ещё открыты; INT/VP admission не выдан.
Модель/risk/trading units не менялись. Ниже предыдущие состояния до установки.

Дополнение W6b.3b.1 26октября: [reference-aware feeder runner](../REFERENCE_AWARE_FEEDER.md)
реализован,113tests passed (17new+96compatibility). Actual proposal plan-only;
installed path/primary reference refresh ещё не изменены и не квалифицированы.
У всех трёх профилей26октября521distinct cases; INT/VP gates остаются открытыми.

Дополнение26октября: [guarded cash preflight](../SEALED_CASH_READINESS.md)
реализован,55tests passed (14new+41compatibility). До cutoff outcome memory не
открывается; original collection freeze проверяется. Local SQLBTC stale≈70h,
ETH fresh, timer active; full reference refresh/INT/VP qualification остаются открытыми.

Продолжение26октября: [bounded coordinator W7b.1](../REFERENCE_COORDINATOR.md)
реализован;444 разных tests passed (31new+413compatibility). Actual два соседних5m
windows/6durable input packets/cursors2/2/2 и независимый replay. Это source delivery,
не cash worker execution и не INT/VP qualification. Следующий W7b.2 — cash-entry
contracts/full actual opportunities/worker result receipts; W7b.3/W8 recovery/host.
Primary DB/services/model/risk и LLM-направление не менялись.


Actual replay сохранил35 initial missing5m slots: source namespace создан
08:56:27UTC, первый poll11:54:33UTC. Между двумя выполненными polls gaps нет;
current tail0 не отменяет initial gap. Continuous source completeness=false.

Сверка 23 октября: [единый актуальный checklist](../PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist)
отделяет завершённые общие механизмы от ещё открытых INT/VP/R1–R16.
Ниже сохранены область и evidence интеграции 18 октября; новая сверка не является
independent reviewer acceptance или завершением какой-либо VP-гипотезы.

W6b.1/W6b.2 реализованы отдельно от frozen paper path:
[mandatory BTC/ETH capture, source versions/first-seen и source-bound price forecasts](../REFERENCE_SOURCE_LEDGER.md).
326 разных tests passed (61new+265compatibility); actual public240rows ready
23октября07:51UTC, offline audit,0actual forecasts. Primary SQL BTC всё ещё stale
при проверке07:08UTC; primary DB/services/model/risk не менялись. Следующий W6b.3 —
shared reader/actual compatible forecasts/reference refresh, затем W7–W9.
Общие W6/W5 и INT/VP admission не закрыты; LLM остаётся вне этой очереди.

Продолжение23октября: [общий source reader W6b.3a](../REFERENCE_SOURCE_READER.md)
реализован и actual360rows/1AVAX price forecast/three-role frame проверен.
374 разных tests passed (48new+326compatibility). Compact inference2906bytes
сохраняет параметры original304141byte artifact migration-v3`041b`; доходность
не оценивалась и candidatea252 не менялся. Следующий W7 — durable delivery/
cursors/retained source history/cash policies. W6b.3b operational reference
refresh, W8/W9 и INT/VP gates остаются открытыми. Primary DB/services не менялись.

## Источник и checkpoint

Продолжение W7a23октября: [retained original source events и ordered role queue](../REFERENCE_DELIVERY.md)
реализованы,413 разных tests passed (39new+374compatibility). Old source DB SHA
не подменяется новым: independent replay использует original event/head anchors.
Три роли имеют cursor/pending/ack; ack пока подтверждает digest consumer receipt,
не cash worker execution. Следующий W7b — coordinator/full opportunities/cash
policies/worker result receipts. W6b.3b/W8/W9 и INT/VP qualification открыты.

- База: `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`, ветка `main` с существующими
  незакоммиченными изменениями. Они не сбрасывались и не переносились в commit.
- Источник VP: локальный файл пользователя версии1.1. Raw SHA256 до обновления
  статусов: `b13852096987cb877a2568a33e5e2fc299a31beb6a2fae507fe73982440adc1b`.
  Это не загруженная с Git новая версия. Ранее выполненные fetch оставили
  origin/main на той же базе; remote code не объединялся с checkout.
- Исходники документов, SHA, dirty status и прежняя активная задача сохранены
  в `.local/state/vp-plan-integration-20261018/`. Более ранний основной план
  до ошибочного включения LLM — в `.local/state/additional-plan-import-20261018/`.
- Спецификация ссылается на видео и расшифровку `vpcrypto … (1).txt`.
  Среди доступных файлов проекта и вложений они отдельно не найдены.
  Содержание первоисточника и цитаты не проверены; числа доходности не evidence.

## Статусы и ответственность

`REUSE` — использовать имеющийся механизм; `EXTEND` — добавить новый контракт
отдельно от frozen kernels; `NEW` — новая работа; `BLOCKED` — зависимость не
подтверждена. Отдельная оценка готовности: `ALREADY_VERIFIED` применима только
к указанной проверке, `PARTIALLY_IMPLEMENTED` не закрывает фазу VP.

Владелец master, спецификации и карты — текущий основной агент. Работа
последовательная, новые агенты/чаты не запускались, ownership другого
LLM-агента не менялся. Отдельный reviewer пока не назначен и acceptance не дал.

## INT: локальная интеграция

- **INT-01 — PARTIALLY_IMPLEMENTED.** Прочитана вся новая спецификация;
  повторно сверены активные разделы master, R1–R16, prompt продолжения,
  расхождения README/FINAL_AUDIT/FREQAI и API ниже. Полная повторная сверка
  всех исторических документов не заявлена; исходный checkbox открыт.
- **INT-02…08 — ALREADY_VERIFIED в области документации.** Один VP-раздел,
  cross-references в прежние этапы, source/dirty checkpoint, настоящая
  активная задача и карта повторного использования. Upsert раздела повторно
  даёт тот же текст; старые804 checkbox сохранены в том же порядке/статусах.
- **INT-09 — PARTIALLY_IMPLEMENTED.** Локальные diff/link/checklist проверки
  описаны ниже; независимый reviewer pass остаётся открытым.
- **INT-10 — BLOCKED для Git-фиксации.** Подготовлена рабочая документация,
  commit/PR не создавались. Checkout содержит большой общий набор прежних
  изменений; они не включаются в коммит документации без выделения его scope.

## Сопоставление фаз и существующего кода

- **VP-00 — EXTEND / BLOCKED by INT.** Прежняя сверка
  [R1–R16](../IMPLEMENTATION_RECONCILIATION_20261014.md) и октябрьские записи
  master — исходный контекст. Сентябрьский dry-run и snapshot live/gate от
  7 октября не подтверждают текущие flags/account/runtime. Свежий read-only
  runtime/resource audit и отдельный AUDIT.md ещё не выполнены.
- **VP-01 — REUSE + EXTEND / PARTIALLY_IMPLEMENTED; blocked by VP-00.**
  [closed_timeframes.py](../../src/cryptoforge/closed_timeframes.py),
  [causal_features.py](../../src/cryptoforge/causal_features.py),
  [research_protocol.py](../../src/cryptoforge/research_protocol.py),
  [research_attempts.py](../../src/cryptoforge/research_attempts.py).
  Готовые closed15m/1h и availability tests не подтверждают новую1D VP-схему,
  delayed pivots или full historical instrument rules. Нужны source audit,
  отдельные frozen windows/config/source SHA и budget до outcomes.
- **VP-02 — EXTEND + NEW / PARTIALLY_IMPLEMENTED; blocked by VP-01.**
  Предыдущие causal/closed APIs — база. Existing
  [support/compression](../../src/cryptoforge/strategy_extensions.py)
  не реализуют Fib, confirmed trendline, POC, hammer и typed ResearchSignal
  из VP. Эти новые контракты не добавлены в production feature schema.
- **VP-03 — NEW / BLOCKED by VP-02.** Семь hypothesis IDs перечислены ниже.
  Research Lab использует отдельную регистрацию; существующий dispatcher и
  frozen extension study не расширяются постфактум.
- **VP-04 — REUSE + EXTEND / PARTIALLY_IMPLEMENTED; blocked by VP-03.**
  [trade_simulator.py](../../src/cryptoforge/trade_simulator.py),
  [paired_portfolio.py](../../src/cryptoforge/paired_portfolio.py),
  [paper_wallet.py](../../src/cryptoforge/paper_wallet.py),
  [entry_risk.py](../../src/cryptoforge/entry_risk.py),
  [exit_rules.py](../../src/cryptoforge/exit_rules.py).
  Shared cash, costs и stop/target core переиспользовать; staged limits,
  TTL, queue uncertainty, partial/non-fill и единый риск двух ступеней
  требуют отдельной реализации и проверки. Исторические правила неизвестны
  там, где нет источников; касание OHLC не означает доказанный fill.
- **VP-05 — REUSE + NEW / PARTIALLY_IMPLEMENTED; blocked by VP-04.**
  ResearchAttempts, [research_evidence.py](../../src/cryptoforge/research_evidence.py),
  [walk_forward.py](../../src/cryptoforge/walk_forward.py) и paired portfolio
  дают механизм, но VP-study не зарегистрирован и не оценивался. Старый
  development extension grid4/4 с0passes — результат прежнего исследования.
  Его нельзя перезапускать под новым именем ради нового бюджета/blind test.
- **VP-06 — REUSE + EXTEND / BLOCKED by VP-05 и R2/R14.**
  Paper wallet/worker/acceptance и
  [original evidence audit](../STRATEGY_EVIDENCE_AUDIT.md) существуют.
  Полная новая forward qualification требует заранее сохранённых original
  mark quotes/filters/fees и причинного ordering относительно fills. Старые
  missing historical liquidation quotes не восстанавливать задним числом.
- **VP-07 — условный EXTEND / BLOCKED by VP-06 и maturity.** Existing
  lightweight trainers — техническая база. Достаточность зрелых VP-labels
  не установлена; fit/selection/publication не запускались. Допустим итог
  NOT_READY; вероятность/accuracy не заменяет paired net portfolio payoff.
- **VP-08 — EXTEND + NEW / BLOCKED для итогового acceptance.** Старые
  causal tests переиспользовать; новые1D/pivots/limits/BTC boundaries,
  no-real-orders invariants и независимый security/resource review ещё нужны.
- **VP-09 — NEW / BLOCKED by evidence и review.** Findings и machine-readable
  experiment registry не созданы: экономических экспериментов VP пока нет.
  Нельзя заменять их этой картой интеграции или фиктивным статусом success.

## Семь гипотез: что переиспользовать и чего ещё нет

- **CF-VP-01 — EXTEND / NEW:** support_bounce как baseline; причинные
  подтверждённые Fib anchors, ступени/TTL/общий риск и тесты ещё нужны.
- **CF-VP-02 — NEW:** compression_breakout как baseline; линия по>=2
  подтверждённым pivots и closed1D вход не реализованы. Lower frames —
  отдельные preregistered alternatives, не подмена дневной гипотезы.
- **CF-VP-03 — NEW / BLOCKED по source quality:** полный trade-print coverage
  не подтверждён. OHLCV proxy допустим только как `approx_ohlcv_poc`,
  causal base selection и ablation против support-only ещё нужны.
- **CF-VP-04 — EXTEND / NEW:** prior-range/compression baseline; wick-sweep
  proxy, known range boundaries, breakout TTL и их incremental-value test.
- **CF-VP-05 — REUSE + EXTEND:** causal BTC context уже есть в экспериментальных
  schemas; paired filter-on/off на том же alt opportunity stream и capital
  ещё нужен. Opportunity cost учитывать, причинность BTC→alt не заявлять.
- **CF-VP-06 — NEW:** preregistered hammer geometry/support и paired ablation;
  thin/zero sample допускает INSUFFICIENT_EVIDENCE.
- **CF-VP-07 — EXTEND / NEW:** существующие risk/exits как ограничения;
  причинные invalidation/no-chase/expired-limit reasons и portfolio effect
  ещё не реализованы. Нулевая активность не подтверждает улучшение.

## Порядок продолжения и блокеры

Прежняя активная задача — **R2/R14: новый preregistered capture original mark
quotes и event sequence, independent liquidation replay, затем full entry
evidence adapter по gates**. Она сохраняется; ошибочное продолжение LLM снято.
Operational R1–R5 сохраняют приоритет. Full source/economic/forward/operational
gates R6–R16 остаются открытыми; наличие локальных fake tests их не закрывает.

Продолжение18октября: локальный [capture/replay механизм](../PAPER_VALUATION_CAPTURE.md)
для нового namespace реализован и проверен в составе1693passed/1deselected.
Lifecycle v2/time-coverage/capture guards теперь проверены в1726passed/1deselected.
Standalone [segmented storage](../EVIDENCE_SEGMENTS.md) и bounded structural
verifier реализованы; проверка кода **1764 passed, 1 deselected /421.60s**. VP-06 остаётся
BLOCKED: новый [capture v3 adapter](../PAPER_CAPTURE_V3.md) реализован локально
(45 новых тестов, итог **1809 passed, 1 deselected /438.15s**),
и отдельный [native archive/projection engine](../NATIVE_PAPER_ARCHIVE.md)
тоже проверен19октября: **1846 passed, 1 deselected /359.50s**,37новых cases.
[Capture v4](../PAPER_CAPTURE_V4.md) теперь интегрирован локально
(52новых cases; итоговый общий **1898 passed, 1 deselected /536.74s**).
[Independent streaming wallet replay](../PAPER_STREAMING_REPLAY.md) реализован локально
(65новых cases; итоговый общий **1963 passed, 1 deselected /470.87s**). Прежний v1/v2 cap10 000 против минимальных
1 036 804events сохраняется. Whole-worker source capture, delivered-worker
replay и новое ядро/archive/capture/replay v2 реализованы20–21октября; см.
[independent replay v2](../PAPER_WORKER_REPLAY_V2.md). Следующий R2/R14 шаг —
**W6a local identity/schema/migration/observed rows** реализован22октября;
[runbook](../LOCAL_SOURCE_PROVENANCE.md). W6b.1/W6b.2 reference capture/forecast
mechanism реализованы23октября; следующий W6b.3 shared reader/actual refresh,
затем W7 complete
shared polling/paired runner, W8 whole-worker resources/review и W9 новая
prospective registration/economic study по gates. Готовые storage/capture/
lifecycle/replay компоненты не реализовывать заново. VP-06 по-прежнему не закрыт.

Порядок VP: INT → VP-00 → VP-01 → VP-02 → VP-03 → VP-04 → VP-05 → VP-06
→ условный VP-07 → итоговый VP-08 → VP-09. QA VP-08 ведётся с первых изменений.
CF-VP-03/06 можно отложить по источникам/выборке. Пока допустима документация
и read-only подготовка, новые search/fit/paper jobs не стартуют.

Frozen protocols, просмотренные окна, reserved/completed attempts и старые
negative outcomes сохранены. Ни цены из видео, ни advertised166%/500%, ни
пример stop3% не дают допуска или новых defaults. Изменений live/gate,
model.active, рисков, ключей, сервисов, Supabase или реальных заявок нет.

## Проверки интеграции и границы доказательств

- Snapshot comparison: все804 исходных checkbox master сохранены в порядке
  и статусах. Исторический основной текст сохранён; добавлены cross-references.
- Новый VP-раздел один; десять стадий VP и семь hypothesis IDs доступны из
  master. LLM-очередь и команды продолжать её удалены из связанных документов.
- Локальные Markdown links и anchors проверяются вместе с `git diff --check`.
  Повторный upsert VP-раздела не меняет его содержимое.
- SHA трёх файлов LLM diagnostics и сохранённого отчёта не меняются.
  Существующие source snapshots/ledger/крупные данные не редактировались.
- Полный прогон1659passed/1deselected /65.99s — прежняя проверка кода18октября,
  не новый запуск в этой правке docs. Предыдущий integration DNS failure
  остаётся открытым. Независимый reviewer acceptance отсутствует.

Машинный отчёт локальных проверок после правки:
`.local/state/vp-plan-integration-20261018/verification.json`.
Проверка: `.venv/bin/python /tmp/verify_cryptoforge_plan_scope.py` — passed,
31 новый локальный Markdown link/anchor; `git diff --check` — passed.
Для diagnostics report сверён canonical payload SHA, отдельно от SHA JSON-файла;
три файла реализации совпали с сохранёнными SHA. Code suite не перезапускался.
