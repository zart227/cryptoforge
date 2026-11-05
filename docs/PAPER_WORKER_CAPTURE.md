# Prospective source capture полного paper tick

Актуализация: 20 октября 2026 года, Europe/Moscow.

`paper_worker_capture.py` добавляет отдельный namespace для записи цикла
исходного `PaperWorker`. В отличие от wallet-only capture v4 здесь сохраняются
входные прогнозы, наблюдения часов, обращения к источникам, отрицательные
решения, атомарные worker/wallet mutations и итоговый отчёт. Старые протоколы,
wallet/worker/math kernels и evidence roots этим компонентом не меняются.

Это **source trace**, не полный independent decision replay и не доказательство
доходности. [Streaming wallet replay v1](PAPER_STREAMING_REPLAY.md) принимает
capture v4; его receipt нельзя автоматически применить к новому worker schema.
Отдельная [интеграция независимого delivered-worker replay](PAPER_WORKER_REPLAY.md)
теперь реализована с новым pre-start contract. Paired runner и полнота upstream
local source polling остаются обязательными.

## Регистрация и входные данные

`CapturedPaperWorker.create(...)` требует отсутствующий собственный root,
candidate SHA, parent study protocol SHA, явную роль candidate/control/stress,
`PaperConfig`, исходную enabled/frozen worker policy, original start/end,
`SegmentedLifecycle`, `SegmentPolicy`, `NativeArchivePolicy` и новый
`WorkerCapturePolicy`. Последний задаёт положительные пределы:

- число predictions, actions и clock calls на tick;
- число market и exit-indicator requests на tick.

Регистрация завершается **до original start**. Protocol связывает runtime SHA,
Decimal contract, бюджеты, окно, роль и parent; log/native manifests связываются
с protocol SHA, а registration — с обоими manifests. Внешний original registration
pin следует хранить вне evidence root. Новые протоколы не квалифицируют старые
закрытые studies и не восстанавливают отсутствующие historical quotes.

Каждый вызов
`tick(predictions, source_id=..., source_observed_at=..., expected_source_sha256=...)`
передаёт bounded list исходных JSON rows. SHA вычисляется по canonical bytes
**полного переданного списка**, включая rejected/out-of-scope/duplicate rows.
Неограниченные generators, неверные типы, conflicting duplicate identities,
устаревший/future batch, credentials, слишком большие/глубокие JSON отклоняются.
Identity источника — SHA(candidate + `|` + opportunity). Семантика самого
candidate и полнота upstream polling этим SHA не доказываются.

Одна worker tick разрешена на original poll slot. Для нового schema lifecycle
`maximum_operations_per_poll=1` означает **целый tick**; его внутренние операции
ограничены отдельными budgets. В original end разрешён один
`mark_endpoint(quotes, filters)`; далее original terminal и seal в исходном grace.

## Что сохраняется и как обрабатываются сбои

До любой мутации записывается durable tick preparation со всем input batch,
исходным logical state/checkpoint, slot и measured resources. Внутри tick:

1. Отдельно записывается compaction исходного native archive.
2. Исходный worker получает прогнозы после archive duplicate filter; первоначальный
   полный batch уже сохранён. Решения worker не переписываются новым алгоритмом.
3. Каждый market/indicator request получает prepared record **до callback** и
   complete record с request pair, clocks, duration, response либо exception class.
   Текст exception не сохраняется. Market responses требуют full raw public book
   и instrument response, точной normalization/hash и наблюдения внутри request.
4. Native `mark/execute/cancel_pending` и worker `enqueue/seen/event` обёрнуты
   отдельными prepared/complete записями. Они содержат input/result и точные
   row deltas, logical commitments и archive checkpoints. Atomic enqueue сохраняет
   intent/link/seen как одну исходную SQLite transaction.
5. Native action использует один фактически наблюдавшийся clock instant,
   записанный до неё. Вне action все worker wall-clock observations записываются
   отдельно. Внутренние monotonic observations для wall-budget branches тоже
   записываются. Исполняется идентичный frozen function code с единственным
   приватным I/O binding для monotonic clock; общий модуль `time` других workers
   не подменяется. Timestamps не сдвигаются искусственно для исправления FIFO.
6. Whole-tick complete связывает итоговый worker report с конечным native state.

При неизвестном исходе action/tick следующая мутация блокируется, даже если
исходный `PaperWorker` поймал Exception и попытался продолжить. Restart принимает
только genesis, полностью завершённый tick или original terminal. Complete
отдельного callback/action не означает завершения whole tick. Ни retry, ни
backfill, ни adoption промежуточного native commit не допускаются.

Storage recovery может закончить **только точную заранее сохранённую frame**.
Если это whole-tick complete, restart безопасно продолжает с этим original
receipt. Partial leaf complete оставляет tick незавершённой. Source seal без
финального capture receipt также не становится автоматически новым receipt.

## Ресурсы и ограничения

Для N poll slots и policy limits A/C/M/X верхняя граница journal events:

`N * (2 + C + 2*(A + M + X)) + 6`.

Шесть дополнительных events — genesis, final endpoint tick/action и terminal.
План проверяет вместимость log/native/total до создания root. Перед каждым tick
резервируется худшее число его frames плюс terminal space; final endpoint имеет
собственный меньший reserve. Memory/free disk/total storage проверяются по
измеренным значениям, с запасом для native journals и bounded batch. Budget
exhaustion до начала tick даёт original resource terminal без её native effects.
Action/clock/request/frame exhaustion внутри tick оставляет unknown outcome;
он не превращается в успешную tick.

В памяти остаются только текущий ограниченный batch, активная native projection,
текущий market map и скалярные счётчики/commitments. История ticks/clocks/decisions
не накапливается в Python. Предварительная проверка JSON также ограничивает depth,
размеры коллекций и worst-case escaped strings перед копированием.

**Long-study capacity ещё не квалифицирована.** Например, тестовая policy
A=24,C=64,M=4,X=4 даёт130 events/tick;30days/poll5s требуют67 392 006events
для одной роли, а не wallet-only1 036 804. Нельзя переносить короткие test budgets
в actual study, понижать coverage/срок или выдавать bytes estimate за measured
RSS/payload/disk qualification. Нужно измерить actual full tick, затем проверить
совместимость выбранных frame/file/native caps и трёх ролей до регистрации.

## Sealed read-only audit

```sh
.venv/bin/python scripts/audit_paper_worker_capture.py \
  --root /absolute/original-worker-root \
  --expected-registration-sha256 ORIGINAL_REGISTRATION_SHA \
  --expected-seal-sha256 ORIGINAL_SEAL_SHA \
  --output /absolute/new-worker-source-audit.json
```

CLI использует реальный UTC; `--as-of` не поддерживается. До original end
открываются только protocol/registration, а source/log/seal outcomes скрыты.
Output должен быть новым, nonsymlink и вне source root.
API clock injection предназначен для synthetic fixtures; actual registration/
audit используют default real UTC и требуют отдельной host qualification.

После end reader последовательно проверяет hash chain и вложенность tick/calls,
source batch identity, causal clocks/window/slot/budgets, negative prediction
status и Buy/source/deadline linkage, raw market sources и передачу именно этих
данных в wallet, atomic native deltas, archive prefixes/watermarks и final source
union. Worker report сверяется с original worker event и числом successful market
callbacks. Вспомогательная история в Python не растёт с длительностью study.

`worker_source_trace_pass=true` означает только описанную source linkage.
`source_poll_completeness_verified`, `full_worker_decision_replay_pass`,
`full_fifo_replay_pass`, `coverage_evidence_pass`, `full_worker_or_host_qualified`,
`paper_evidence_pass`, `economic_profitability_established`,
`live_admission_granted` остаются **false**. Supply pin не доказывает отсутствие
пропущенных upstream opportunities; нужен paired polling contract.

Native same-clock FIFO и tiny Decimal overspend, найденные предыдущим replay,
остаются открытыми producer qualification gates. Новый журнал их не исправляет
и не объявляет допустимыми. Pending Buy, который исходный worker пытается
исполнить после entry cutoff, блокирует capture до исполнения Buy; отдельный
preregistered producer/closeout fix ещё требуется.

## Чек-лист

- [x] Новый prospective role/parent/runtime/source contract и bounded input batches.
- [x] Whole tick / clock / provider / atomic native action capture.
- [x] Full raw market normalization/hash и causal request availability.
- [x] Retained negative/out-of-scope/duplicate opportunities, source/deadline linkage.
- [x] Unknown outcome blocks swallowed-error continuation, restart/retry/backfill.
- [x] Sealed streaming read-only source auditor и CLI с exclusive output.
- [x] 85 focused passed /129.22s; общий non-integration **2063 passed, 1 deselected /747.04s**.
  Final source SHA, subprocess/forgery/budget tests и checklist receipts сохранены.
- [x] Independent delivered-worker decisions + wallet/FIFO/coverage replay для нового schema:
  [новый local backend contract](PAPER_WORKER_REPLAY.md), без production DB access.
- [ ] Paired candidate/control/stress runner, shared polling/completeness contract.
- [ ] Causal FIFO, strict stake/cash sizing, pending Buy cutoff/closeout producer qualification.
- [ ] Actual full-tick payload/RSS/wall/disk/network/shared-role/host measurements.
- [ ] Qualified candidate, independent review и новый actual study ≥30days; economic admission.

## Проверки следующего этапа

W1–W4 реализованы отдельным local verifier для переданных batches; детали и
проверки — в [runbook](PAPER_WORKER_REPLAY.md). W5–W9 остаются открытыми;
ни source trace, ни delivered-batch replay не заменяют их qualification.

- [x] **W1 — новый replay contract до original start:** локальный компонент реализован
  отдельно в [worker replay](PAPER_WORKER_REPLAY.md). Отдельный verifier root,
  original worker registration/role/parent/window, verifier runtime и scratch/
  active state/wall/memory/disk budgets. Для full controller qualification
  явно проверить runtime dependency closure, включая imported timestamp parser
  и clock bindings; source manifest не является host/runtime admission. Закрытый worker study нельзя
  ретроспективно превратить в preregistered independent evidence.
- [x] **W2 — bounded independent state:** локальный scratch/index/cleanup реализован. Fresh disposable indexed scratch вне
  evidence roots; exact original IDs для всех seen/intent/link/fill/mark/segment
  rows, page/row caps и cleanup. Не хранить весь prediction/clock/event history
  в Python; отдельно проверить большой набор rejected/zero-trade opportunities
  и conflicting source identity между batches/restarts, а не только внутри batch.
- [x] **W3 — independent delivered-batch controller:** локальный компонент реализован;
  полнота upstream источника ещё открыта. Из original batch, UTC/monotonic
  observations, market/error/indicator responses восстановить пропуски, negative
  statuses, duplicate decisions, signal limits, expiry/cutoff, stop/timeout/shared
  exits, ordering, worker events и final report. Не вызывать producer tick для
  доказательства его собственной корректности. Rehashed omitted/extra decisions,
  неверный source identity и неверная wall-budget branch должны отклоняться.
- [x] **W4 — wallet/FIFO/coverage нового schema:** отдельный adapter реализован.
  Связать каждый atomic worker
  enqueue с causally available signal, затем независимо пересчитать все native
  wallet deltas и time coverage. Whole-tick capture layout не совпадает с v4;
  новый adapter/version должен явно квалифицировать эту границу. Проверить
  losing fill omission, same-clock allocation, strict cash/stake, dust/material,
  pending/late completion, overnight anchors и final original raw sources.
- [ ] **W5 — producer qualification.** В новом preregistered namespace обеспечить
  actual causal FIFO и strict sizing/cash conservation, сохранив исходные
  frozen kernels/receipts; отдельно определить cancellation pending Buy перед
  closeout. Regression fixtures предыдущего replay и поздний Buy должны остаться
  отрицательными для прежнего producer и пройти для нового без epsilon waiver.
- [x] **W5a — новое ядро:** versioned wallet/worker/exact sizing и local pre-start
  kernel contract реализованы; FIFO/cash/cutoff regression fixtures проверены.
  [Границы и checklist новой версии](PAPER_PRODUCER_V2.md).
- [ ] **W5b — интеграция ядра:** новый bounded archive/capture schema и отдельный
  independent replay для fill sequence, exact allocations и post-SQLite-lock clock.
  Старые manifests/12-group commitments не принимают новую schema автоматически.
- [x] **W5b.1 — native archive v2:** kernel contract binding, causal fill-order
  history/counter/anchors, row guards и crash recovery реализованы отдельно.
  [Новый archive runbook](NATIVE_PAPER_ARCHIVE_V2.md). Capture/replay ещё открыты.
- [ ] **W6 — paired source completeness.** Freeze общий polling contract и
  baseline/control/stress definitions до outcomes. Один original upstream batch
  должен иметь external identity/sequence и explicit delivery/skip/failure
  records для каждой роли; нельзя считать только accepted candidate rows.
  После миграции связать его с local backend instance/schema/migration snapshot
  и original row IDs/known_at; loopback configuration binding сам по себе этого не доказывает.
  Shared raw market evidence должно сохранять original request/availability,
  а не получать новые fabricated observation timestamps при повторной доставке.
- [ ] **W7 — paired runner и остановки.** Зарегистрировать три отдельных source
  roots до общего start; shared parent pin и агрегированный budget обязательны.
  Проверить crash одной роли, недоставленный batch, duplicate poll, market timeout,
  late Buy, неполный exit и запрет читателю оценивать outcomes до общего end.
- [ ] **W8 — actual capacity и независимый review.** Измерить payload/state/process
  RSS/whole tick/network/queue/disk, shared-role contention и durability; сверить
  bounds с числом poll slots минимум30days. Превышение не разрешает сокращать
  окно, убирать отрицательные события или переносить control/stress расходы.
- [ ] **W9 — новый actual study.** Только после qualified candidate, источников,
  producer/replay/runner/resource checks и independent review. Полный immutable
  registry сохраняет все попытки и negative/zero-trade результаты; economic gates
  проверяются отдельно. Cash-only/math/source pass не означает заработка.

Receipts: `.local/state/paper-worker-capture-work-20261020/`.
Очередь и исследовательские gates — [основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
LLM-план принадлежит другому агенту. Actual API/orders/fit/model publication/
services/risk этим этапом не запускались и не менялись.
