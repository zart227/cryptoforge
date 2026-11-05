# Prospective capture v4: native archive и checkpoint

19 октября 2026, Europe/Moscow. Новый `paper_capture_v4.py` связывает causal
ledger с [native archive/projection](NATIVE_PAPER_ARCHIVE.md). Он применяется
только к отсутствующему собственному namespace. Старые v1/v2/v3 roots и frozen
producers не мигрируются и не очищаются. Actual study этим этапом не запущен.

## Регистрация и границы

`ArchivedCapturedPaperWallet.create` требует candidate SHA, parent study
protocol SHA, явную роль candidate/control/stress, PaperConfig, worker policy,
`SegmentedLifecycle`, `SegmentPolicy` и `NativeArchivePolicy`. Исходное start/end
и все budgets фиксируются до start.
Protocol SHA закрепляется отдельно в event и native manifests; registration
связывает их внешние SHA без циклического хеширования. Original registration
SHA нужно сохранить вне namespace. Runtime/native schema/Decimal context,
paths, config и политики проверяются повторно.

Capacity preflight проверяет исходную cadence, число events, оценочный event
budget, минимальную ёмкость native marks и сумму event/native/metadata budgets.
Это необходимое условие, а не измерение actual payloads или обещание вместить
все возможные сделки. Enqueue/cancel/compaction тоже расходуют operation slot
и пару prepared/complete events. Полный runner должен заранее учесть их в
frozen budget. Для всех трёх ролей остаётся отдельная общая квалификация.

## Порядок записи

Доступны `enqueue`, `execute`, `mark`, `cancel_pending` и `compact`. Каждый
вызов удерживает capture lease и общий native archive lease:

1. Проверяет original identity, предыдущее логическое состояние и checkpoint,
   исходное окно, Buy cutoff, rate, memory/disk/storage и terminal reserve.
2. Durable prepared содержит public inputs, before-state, generation,
   watermarks и hash-chain tips всех фиксированных archive shards.
3. Выполняет native operation ровно один раз с одним original clock.
   Archive-aware producer может сделать compaction внутри вызова.
4. Complete сохраняет result, исходные изменённые rows before/after, новое
   логическое состояние/checkpoint, completion clock и wall duration.

Логическое состояние включает 9 archive sources, отдельные cash/policy,
market filters и worker state. Для каждой группы записываются count и
domain-separated сумма SHA256 строк по модулю2^256. Identical retained anchors
учитываются один раз. Поэтому перенос row из active в archive не меняет
логическую историю. Это consistency commitment; он не доказывает FIFO,
правильность цены или прибыльность. Для этих свойств нужен independent replay.

Writer хранит только ограниченную active projection и небольшие accumulators.
При restart архив читается один раз потоком; дальше cache обрабатывает только
новые записи после сохранённых shard tips. Общая сериализованная active scan
ограничена frozen `maximum_batch_bytes` native policy (не более1MiB), каждая
row — `maximum_row_bytes`, таблицы — `maximum_active_rows`. Нехватка scan/frame
capacity блокирует run; бюджеты автоматически не увеличиваются. Complete,
не поместившийся после native commit, оставляет prepared с неизвестным исходом.

## Сбои и завершение

Resume сначала восстанавливает только exact pending event frame в event log.
Prepared без original complete запрещает native resume/retry/backfill, в том
числе при сбое во время compaction. Он требует отдельного review. Сохранённый
complete восстанавливается из exact frame bytes, после чего сверяются native
состояние и checkpoint; повторного native call нет. Изменения worker/direct
native writer вне ledger обнаруживаются перед следующей операцией или resume.

Требуется original terminal, записанный в исходных временных границах.
`finalize()` разрешён от end до end+исходного grace. Native seal делает одну
последнюю compaction; её generation увеличивается ровно на1, а логические
источники должны остаться прежними. Capture receipt связывает этот checkpoint,
native seal SHA и event head/catalog SHA. Его SHA тоже сохраняется снаружи.
Early abort не раскрывает outcomes до end. Сбой после native seal до capture
receipt не приводит к автоматическому adopt/перезаписи/синтезу завершения.

## Read-only аудит

```bash
.venv/bin/python scripts/audit_paper_capture_v4.py \
  --root /absolute/new-v4-study \
  --expected-registration-sha256 ORIGINAL_REGISTRATION_SHA256 \
  --expected-seal-sha256 ORIGINAL_FINAL_SEAL_SHA256 \
  --output /absolute/new-v4-audit.json
```

CLI использует реальный UTC; `--as-of` отсутствует. До original end читаются
только registration/protocol и возвращается `performance_hidden=true`.
После end нужны внешние original pins. Output должен быть новым и вне sources.
Reader не восстанавливает journals и не меняет исходные файлы.

Аудит потоково проверяет causal prepared/complete/terminal, исходные clocks,
operation/resource bounds, row-delta commitments и монотонные checkpoints.
Каждый изменённый shard tip сверяется с фактическим indexed archive prefix;
watermarks при compaction должны совпадать с original pre-operation row counters.
Есть узкие проверки enqueue/cancel/mark/fill identity/input/result linkage,
immutable rows и границ source groups. Затем полный source union читается один
раз потоком и сравнивается с terminal/final checkpoint. Проверки обнаруживают
подмену строк, в том числе при пересчитанных segment/catalog/seal hashes.

`source_checkpoint_trace_pass=true` означает только успешную сверку этого
журнала с native source archive. Всегда `paper_evidence_pass=false`,
`full_fifo_replay_pass=false`, `coverage_evidence_pass=false`,
`economic_profitability_established=false`, `live_admission_granted=false`.
Full cash/FIFO/fill arithmetic/valuation/coverage проверяется отдельным
[streaming replay](PAPER_STREAMING_REPLAY.md). Его pass не меняет flags source auditor.
Strategy decision replay здесь ещё не реализован. V4 не подключён к полному PaperWorker.tick; native
worker schema/state закреплены, но запуск worker вне capture не допускается.

## Чек-лист

- [x] New namespace, prospective protocol/registration, parent study/role и два manifests.
- [x] Durable ledger для всех доступных wallet mutations и explicit compaction.
- [x] Original row deltas, archive-invariant commitments и checkpoint linkage.
- [x] Bounded active scan, incremental archive summary, source union без history lists.
- [x] No retry при unknown outcome, exact stored-complete recovery и process-death tests.
- [x] Terminal/end-window gate, внешние seal pins и read-only CLI без clock override.
- [x] Read-only, drift/schema/alias/tamper/budget/cutoff/negative-trade regression cases.
- [x] [Streaming cash/FIFO/fill arithmetic/valuation/time-coverage replay](PAPER_STREAMING_REPLAY.md).
- [ ] Full worker polling/decision/source capture и paired candidate/control/stress runner.
- [ ] Actual payload/process RSS/full-tick/queue/network/shared-role/host/power-loss qualification.
- [ ] Qualified candidate, независимый review, новый future protocol/study и economic admission.

Checkpoints и результаты проверок: `.local/state/paper-capture-v4-work-20261019/`.
Текущая очередь — в [основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
LLM-направление выполняет другой агент.

Локальное измерение synthetic fixture:42marks/86events/22segments,
maximum frame4773bytes, event bytes345881, все sources567697bytes.
Read-only audit0.519s, peak Python allocations392032bytes. Это тестовые
public inputs и короткое искусственное окно; actual market sizes, process RSS,
full worker и трёхролевая host qualification этим не подтверждаются.
Receipt: `synthetic-integration-measurement.json` в указанной выше папке.

Итоговые проверки:52focused passed /46.05s; полный non-integration **1898 passed, 1 deselected /536.74s**.
Frozen native runtime/source archive/storage/v3 SHA сохранены.

## Приёмка следующего streaming replay

Первые девять пунктов выполнены в [отдельном streaming verifier](PAPER_STREAMING_REPLAY.md).
Source trace сам по себе их не подтверждает. Full worker/actual admission остаются открытыми.

- [x] Определить frozen replay state/scratch/row/byte/wall budgets до нового
  actual study. Не добавлять автоматически растущий SQLite scratch или списки
  всей истории. Если scratch нужен, он должен быть отдельным новым bounded
  временным файлом вне sources; reader не восстанавливает source journals.
- [x] Читать causal ledger и unified native sources bounded cursors; не вызывать
  прежние history-accumulating snapshot/fill/coverage auditors. Сохранить original
  ordering для одинаковых timestamps. Перестановка Buy/Sell не допускается.
- [x] Вести independently calculated cash, только текущие open lots, filters,
  последние day anchors/latest-known mark и bounded per-pair context. Проверять
  каждый before/after row; архивные zero lots не накапливать в Python state.
- [x] Проверять каждый fill независимо от native execution: order quantity,
  base/quote fees, stake/proceeds, Decimal rounding order, filters, spread/depth,
  slippage, FIFO basis/fees/segments, residual inventory и conservation.
  Сверить изменения cash/lots/segments с original source rows и commitments.
- [x] Пересчитать каждый liquidation mark по original quotes/rules/raw source
  hashes и native temporal scope. Missing/stale/unknown, material inventory и
  conditional dust-zero трактовать по исходным gates; current quotes не backfill.
- [x] Заменить CoverageTimeline lists на потоковые counters: prior known state,
  original source expiry, prepared/completion clocks, covered seconds, текущий
  и максимальный gap. Same timestamp не добавляет duration; повторное применение
  старой quote не продлевает её срок. Prepared прекращает прежнюю оценку.
- [x] Проверить full start/end endpoints, exact known-time fraction/gaps,
  Buy cutoff, разрешённые exits, closeout/material residual и original terminal.
  Abort, late completion или missing source не дают economic pass.
- [x] Добавить независимые отрицательные cases: altered fee/FIFO segment,
  omitted losing fill, repeated source ID, same-clock reorder, rehashed cash/
  inventory/dust forgery, stale reused book и shortened endpoint/coverage.
  Структурные SHA в этих cases должны быть пересчитаны, чтобы проверить семантику.
- [x] Сопоставить малые fixtures с независимыми расчётами и прежним проверенным
  short-study replay; провести длинный synthetic stream с bounded state и
  измерениями. Synthetic allocations не выдавать за actual process RSS.
- [ ] После этого отдельно реализовать full worker decision/source capture,
  paired candidate/control/stress runner и их общий resource preflight.
  Сохранить исходные economics, budgets, minimum30days и independent review;
  будущие наблюдения не начинать до всех gates.
