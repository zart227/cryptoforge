# Архив нового paper-ядра: порядок исполнений и ограниченная активная проекция

20 октября 2026 года, Europe/Moscow. [Основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
Продолжение W5b после [нового ядра W5a](PAPER_PRODUCER_V2.md).
Компонент `native_paper_archive_v2.NativePaperArchiveV2` работает в новом owned
namespace. Прежние kernels, архивы, capture/verifier contracts и их receipts
не изменены. Основная БД приложения остаётся local PostgreSQL/PostgREST;
этот архив — отдельные SQLite files. API/SQL к основной БД он не вызывает.

## Предварительный контракт и создание

Сначала требуется новый `register_kernel(...)` из `paper_producer_v2` с явно
выбранным local backend. Затем, до original start:

```python
archive = NativePaperArchiveV2.create(
    new_archive_root,
    source_protocol_sha256=original_source_protocol_sha,
    kernel_root=original_kernel_root,
    expected_kernel_contract_sha256=original_kernel_contract_sha,
    expected_kernel_registration_sha256=original_kernel_registration_sha,
    policy=NativeArchivePolicy(...),
    market=public_market_provider,
)
```

Candidate, role, wallet config, worker policy, окно и cutoff берутся из kernel
contract. Альтернативные параметры не принимаются. Kernel/archive roots должны
быть отдельными; разрешены sibling roots будущего capture, вложение друг в друга
отвергается. Existing archive namespace не перезаписывается.

Manifest закрепляет обе kernel pins и полный публичный contract, source protocol
SHA, runtime hashes, schema hashes, Python/SQLite/Decimal environment и измеренные
resource floors. API key и содержимое `.env` в архив не попадают. После создания
всех файлов отдельный `ready.json` фиксирует завершение до start. У caller должны
сохраниться **два внешних SHA**: `archive.manifest_sha256` и `archive.ready_sha256`.
Late/partial setup без valid ready не принимается повторным запуском.

Возобновление требует `expected_manifest_sha256`, `expected_ready_sha256`,
public providers и actual clock. Sealed reader дополнительно требует
`expected_seal_sha256`. Он читает original kernel metadata offline и не вызывает
backend resolver, public/private API или producer execution. Изменение kernel
metadata обнаруживается также во время streamed чтения.

Дополнение21октября: [whole-worker capture v2](PAPER_WORKER_CAPTURE_V2.md)
с prospective registration этой schema реализован; paired runner ещё открыт. Clock injection применяется только в synthetic
fixtures. Этот API не регистрирует actual research или разрешение торговли.

## Сохраняемые источники

Новая версия явно объявляет **14 групп**, вместо12 прежнего capture:

- 10 immutable source groups: прежние marks/fills/closed_segments/intents/lots/
  day_anchors/worker_events/seen_predictions/intent_links и новая `wallet.fill_order`;
- 4 mutable auxiliary groups: `wallet.state`, `wallet.filters`, `worker.state`
  и `wallet.fill_counter` — строка `sqlite_sequence` для `fill_order`.

`fill_order(sequence, intent_id)` архивируется с original integer key и hash chain.
Counter является изменяемым состоянием и не вставляется под одним immutable key
с разными значениями. Его текущая строка сохраняется в active wallet, входит
в protected projection и доступна через `iter_auxiliary_rows('wallet.fill_counter')`.
Capture/replay обязаны включить эту группу в новый commitment; игнорирование
counter под видом прежнего schema недопустимо.

`iter_rows(source)` выдаёт union original archived и active rows, удаляя только
точные дубликаты. Числовые ключи сортируются численно через canonical index keys.
`wallet.fills` остаётся indexed по intent ID; причинный порядок задаёт отдельная
`wallet.fill_order`, а не порядок строк fills или timestamp ties.

## Очистка, causal anchors и аварии

Архивный commit и его проверка предшествуют cleanup. Удаление активных history
rows и обновление checkpoint выполняются одной attached-DB транзакцией SQLite
в DELETE/FULL режиме. Cash, open lots/basis/entry fee, pending intents/links,
последние day anchors, known/unknown marks и filters сохраняются.

В активной проекции остаются original entry fills открытых lots, causal latest
Buy для активной пары и последнее исполнение как global sequence anchor.
Их `fill_order` rows сохраняются вместе с fills. Последовательность и
`sqlite_sequence` не сбрасываются, даже когда все позиции закрыты. Latest Buy
выбирается по sequence; equal-clock reverse IDs не меняют контекст exit.

На resume сверяются checkpoint/archive/active high-water, точный тип и значение
counter, взаимные links fills/order/intents/lots и неотрицательный lot basis.
Потерянный anchor, ручной reset counter/checkpoint и несовпадающий payload sequence
дают отказ. Такой state не исправляется и не принимается как новая пустая база.

Recovery в этом adapter относится к **storage compaction**. SQLite rollback или
наличие последнего fill не доказывают исход неизвестной captured action/whole tick.
Будущий capture обязан отдельно журналировать prepared/complete и блокировать
resume/retry при unknown completion; этот шаг остаётся открытым.

## Пределы и исполнение

Прежние policy rules для shard/active/page/global-record/row/batch/total bytes и
memory/disk floors сохранены в отдельном versioned class. Новые source rows
учитываются общим record budget; rotation/restart его не сбрасывают.

Новая SQLite schema содержит закреплённые BEFORE INSERT/UPDATE guards для owned
producer tables. Они проверяют row count и безопасную верхнюю границу JSON row
bytes **внутри транзакции producer**. Слишком большой fill откатывается вместе
с cash/lot/fill_order/counter. Допустимые SQL text values — printable ASCII;
JSON payloads с Unicode заранее ASCII-escaped ядром. NUL/control/raw non-ASCII
identifiers и бинарные значения отвергаются. Guards входят в schema pin;
удалённый или изменённый guard блокирует resume.

Public inputs дополнительно проверяются до вызова ядра: bounded plain JSON,
depth/collection/row/batch bytes, отсутствие nonfinite/credential fields. Имена
торговых пар являются значениями; `TOKEN/USDT` не считается credential field.
Prediction byte budget учитывает также rows, отфильтрованные по archived seen IDs.

Archive worker принимает только original start/end/cutoff из kernel contract.
Native execute передаёт cutoff ядру, сохраняя actual clock check после SQLite
write lock. Buy на cutoff отменяется, Sell может закрывать имеющееся inventory.
Полнота источников и time coverage этим adapter не квалифицируются.

## Проверки и очередь

- [x] Отдельный v2 archive namespace, pre-start kernel binding, external
  manifest/ready pins, environment/schema/source inventory и offline sealed reader.
- [x] Explicit fill-order history и mutable counter source, causal retained
  projection и high-water guards при cleanup/restart.
- [x] Transactional SQL row/page limits и atomic rollback при oversized fill;
  bounded public inputs и общий prediction byte budget.
- [x] Итоговый профильный прогон: **83 passed /100.39s**, включая10 005 synthetic
  worker rows; write15.23s, sealed audit2.84s, Python peak197 919bytes,
  active worker49 152bytes. Receipt `measurement-10005.json` сохраняет точные числа.
- [x] Compatibility: **430 passed /339.50s**. Всего513 разных cases;
  новый общий suite не запускался. Exact commands/source/runtime pins и environment
  сохранены в `verification.json`, `final-source-pins.json`, `runtime-pins.json`.
- [x] W5b.2: новый whole-worker capture schema до общего start реализован21октября;
  см. [runbook и результаты](PAPER_WORKER_CAPTURE_V2.md).
  Связаны original kernel/archive manifest/ready pins, все14 групп и source
  checkpoints. UTC **после BEGIN IMMEDIATE** сохраняется без подмены его
  fixed-before-action timestamp при ожидании SQLite lock.
- [x] Capture v2 журналирует clocks внутри native action с её parent identity, сохраняя
  фактическую последовательность чтений; `filled_at` привязан к
  post-lock observation. Interrupted clock/write/action остаётся unknown;
  storage recovery не разрешает retry economics. Late action completion
  и original window/deadline проверены без изменения captured timestamps.
- [x] W5b.3: [independent replay v2](PAPER_WORKER_REPLAY_V2.md) реализован21октября: exact integer sizing,
  fixed512-place allocations, fill sequence/counter и новые clock/cutoff branches.
  Adversarial source-consistent rehash/omission и unknown-action guards проверены.
- [ ] Whole-worker resource plan с новым row payload/count и aggregate budget,
  W6/W7 local instance/schema/row provenance/shared polling/paired runner,
  W8 independent review/actual host capacity и W9 qualified candidate/actual study.

`audit()` подтверждает source integrity и активную проекцию этой версии. Его
`full_worker_or_host_qualified/paper_evidence_pass/economic_profitability_established/
live_admission_granted=false`. Проверка10k synthetic worker rows, когда выполнена,
измеряет bounded storage/Python heap, а не process RSS, сеть или30day трёхролевое
исследование. Реальная прибыльность и live admission требуют отдельных gates.

Receipts: `.local/state/native-paper-archive-v2-work-20261020/`.
