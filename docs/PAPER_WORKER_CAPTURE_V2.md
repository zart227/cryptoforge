# Журнал полного paper-worker v2: исходные данные и фактическое время

21 октября 2026 года, Europe/Moscow. [Основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
Этап W5b.2 после [ядра v2](PAPER_PRODUCER_V2.md) и
[архива v2](NATIVE_PAPER_ARCHIVE_V2.md). Старые capture/replay contracts,
исходники и receipts не изменены. Основная БД остаётся local PostgreSQL/PostgREST;
этот компонент пишет только в новый owned SQLite/evidence namespace.

## Предварительная регистрация

`paper_worker_capture_v2.CapturedPaperWorkerV2.create(...)` получает отдельный
original kernel root и обе внешние kernel pins. Candidate, role, config, policy,
start/end и cutoff берутся из него. Их нельзя заменить параметрами capture.
Lifecycle closeout должен совпадать с original kernel cutoff. Kernel и capture
roots должны быть отдельными, без вложения друг в друга.

```python
capture = CapturedPaperWorkerV2.create(
    new_capture_root,
    kernel_root=original_kernel_root,
    expected_kernel_contract_sha256=original_kernel_contract_sha,
    expected_kernel_registration_sha256=original_kernel_registration_sha,
    lifecycle=original_lifecycle,
    storage_policy=original_segment_policy,
    native_policy=original_native_v2_policy,
    capture_policy=original_worker_capture_v2_policy,
    market=public_market_provider,
)
original_registration_sha = capture.registration_sha256
```

Сначала создаются protocol, новый native archive, event log и genesis. Registration
закрепляет source protocol, storage manifest, native manifest **и ready SHA**.
Время проверяется до и после durable registration; при опоздании последний
registration удаляется и partial root не переиспользуется. Внешний SHA сохраняется
до original start. Runtime hashes включают новое ядро, архив, state adapter,
capture, audit CLI и зависимости; Python/SQLite/Decimal environment закреплён.
Ни API key, ни `.env` в evidence не записываются.

`resume(...)` требует original external registration SHA и провайдеры. Только
завершённый whole tick, genesis или terminal допускают продолжение. Partial action,
clock/provider receipt или неизвестный исход tick блокируют resume до открытия
native writer. Recovery event frame восстанавливает только заранее durable bytes.
Он не доказывает отсутствующее завершение экономического действия. Durable whole
completion, чей frame оборвался при записи, может быть восстановлен без повторного
выполнения tick.

## Четырнадцать групп и источник времени

Новый `paper_capture_state_v2.py` имеет собственный commitment domain и все
14 groups, включая immutable `wallet.fill_order` и mutable `wallet.fill_counter`.
Состояние включает logical row counts/checksums, checkpoint generation, integer
watermarks и fixed-shard tips. Active scan ограничен row/batch budgets, а архив
после restart читается streaming; затем учитываются только новые records.
Compaction не изменяет logical source history. Запись fill должна добавить order
с original intent ID и одновременно изменить counter на следующий sequence.

Каждый native action сначала получает durable `prepared` record. Каждое значение
UTC, передаваемое producer, **сначала записывается durable clock record** с
`action_prepared_seq`; controller clock имеет явный `null` parent. После native
operation в completion сохраняются ordered `native_clocks`, raw result и row delta.
Auditor сверяет их с отдельными clock records. Completion нельзя выдать после
ошибки clock/action/receipt, даже если worker перехватил Exception.

У wallet execute первый clock вызывается внутри исходного `BEGIN IMMEDIATE`,
после получения SQLite write lock. Он определяет cutoff/expiry/fill time.
Prepared time не подменяет этот clock. При reject ядро может прочитать UTC второй
раз для `observed_at`; обе записи сохраняются и сверяются. Mark и worker mutators
сохраняют их собственный порядок чтений; этот capture не объявляет все часы
post-lock. Внутренний порядок замороженного ядра не переписывается.

Controller выполняется через исходный `PaperWorkerV2.tick`, включая identity,
path и arithmetic checks. Для его `_tick` создаётся private globals binding
monotonic provider; process-global модуль time не меняется. Archive-aware native
mutators сохраняют guards, bounded projection и compaction. Raw prediction batch,
включая negative и уже встречавшиеся predictions, сохраняется **до** archive
filtering; count/bytes каждого prediction проверяются заранее.

Отдельный `paper_worker_events_v2.py` сохраняет прежний append/recovery transaction
и задаёт новую scoped payload policy: pair-map keys разрешены только в mark maps
и controller error maps; credential keys в их дочерних payload остаются запрещены.
Frozen segmented storage не изменён, новый policy hash входит в capture protocol.

Public market result содержит original raw book/instrument evidence. В журнале
сохраняются preparations, responses или класс ошибки, без её message. Provider
observed_at должен принадлежать интервалу запроса. Имена пар, включая TOKEN/USDT,
проверяются как идентификаторы; credential keys внутри provider payload запрещены.

## Бюджеты и завершение

`WorkerCapturePolicyV2` задаёт независимые caps для predictions, actions, всех
controller/native UTC+monotonic clocks, market и exit requests. Превышение любого
cap останавливает tick и запрещает последующие effects. Политика другого capture
или archive version не принимается.

`events_per_tick = 2 + C + 2 * (A + M + X)`. Для whole-window event budget:
`poll_slots * events_per_tick + 7` — genesis, endpoint tick/action/**clock** и terminal.
Для A24/C64/M4/X4 и 30days/poll5s это **67 392 007 events**. Это верхняя граница
числа records по заданным caps, а не измерение RSS/payload/network или доказательство
достаточного native total storage. End-to-end capacity и actual three-role runner
остаются W8. Caps и ресурсные floors не уменьшаются ради запуска.

Каждый tick проверяет event/storage/resource reserve до effects. Endpoint mark
имеет собственный reserve для пяти records. Его actual preparation/observation
допускается от original end до end + min(endpoint gap, finalization grace),
а completion — до end + finalization grace. Обе границы закреплены в protocol
до start. Фактический observed_at возвращается отдельно; post-end mark не
переименовывается в end и не backfill original coverage/equity. Обычный tick,
чья causal clock/completion вышла за original end, остаётся незавершённым и не
перезапускается. Wall budget failure сохраняет terminal reason; source audit
возвращает `operation_wall_budget_pass=false`.

После original end и terminal выполняется logical-neutral native compaction,
native seal и event seal. `sealed.json` связывает external registration, protocol,
source seal, final checkpoint, event head/catalog и sequence. Частичный seal не
переиспользуется. Ни runtime, ни missing quotes не backfill.

## Read-only аудит и границы

CLI `scripts/audit_paper_worker_capture_v2.py` принимает original root, registration
SHA, seal SHA и необязательный **новый** output вне source root. Он использует
actual UTC; `--as-of` отсутствует. До original end возвращается только sealed status,
без native reads/results. Повторная запись существующего output запрещена.

После end auditor проверяет causal parents, clock budget/order, raw prediction и
market identity, negative decisions/source deadlines, permitted atomic deltas,
fill sequence/counter, checkpoints, archive prefixes и final source union.
Чтение sealed source не изменяет original bytes.

`worker_source_trace_pass` означает source/native linkage. Он не проверяет заново
всю финансовую математику или все ветви controller. Independent wallet/controller
[replay v2](PAPER_WORKER_REPLAY_V2.md) реализован21октября в отдельном компоненте. Ни source audit, ни synthetic tests не закрывают
source poll completeness, independent decisions, coverage, host qualification,
paper/economic или live admission. Соответствующие flags остаются false.

## Проверки и receipts

- [x] Новые namespace/registration, external kernel+native ready pins и 14 groups.
- [x] Отдельные durable clocks внутри native action и исходный v2 controller wrapper.
- [x] Итоговая проверка: **637 разных cases прошли:** 123 passed /363.09s + 1 passed /26.08s после исправления tuple expectation только в тесте; compatibility 513 passed /620.65s. Общий suite заново не запускался.
  Process deaths, actual write-lock wait, distinct reject clocks, source-consistent
  rehash, endpoint timing и capture/compaction/resume counter linkage проверены.
- [x] W5b.3: [независимый replay v2](PAPER_WORKER_REPLAY_V2.md) новой схемы и actual clock sequence реализован21октября.
- [ ] W6/W7: upstream local DB instance/schema/migration/known_at provenance,
  shared polling/negative/skip/failure delivery и paired runner.
- [ ] W8/W9: whole-worker capacity/review, qualified candidate и actual study
  минимум30days с economic gates.

Receipts: `.local/state/paper-worker-capture-v2-work-20261021/`.
