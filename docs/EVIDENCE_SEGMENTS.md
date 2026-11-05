# Сегментированный журнал исследовательских evidence

`evidence_segments.py` — отдельный storage-компонент для НОВОГО формата
paper-capture. Он реализует bounded files, общий event counter/hash chain,
rotation/recovery и read-only streaming verification. Старые capture v1/v2,
native wallets/workers, их лимиты и frozen studies не изменены.

**Статус:** компонент реализован и проверен локально; [capture v3](PAPER_CAPTURE_V3.md)
теперь подключает его к native mark/execute и исходным row IDs. Bounded native
source-row [archive engine](NATIVE_PAPER_ARCHIVE.md) теперь реализован отдельно;
[capture v4 integration](PAPER_CAPTURE_V4.md) реализована локально; полный paper runner ещё открыт. Прежний long-study
по-прежнему BLOCKED: структурная проверка сегментов не является cash/mark/FIFO/
coverage/economic replay. LLM-направление сюда не включается.

## Новый namespace и неизменяемые бюджеты

`SegmentPolicy` требует явных maximum_events, maximum_segments,
maximum_segment_events, maximum_segment_bytes, maximum_record_bytes и
maximum_total_bytes. Нет автоматического увеличения лимитов после результатов.
Файл сегмента ограничен64MiB, record —256KiB, число сегментов —4096,
каталог —8MiB. Общий event budget сохраняется через ротации и restart.
Создание нового лога не создаёт новых попыток в ResearchAttempts и не заменяет
регистрацию source protocol, ролей, экономических критериев и окна наблюдения.

```python
from cryptoforge.evidence_segments import SegmentPolicy, SegmentedEventLog

log = SegmentedEventLog.create(
    new_storage_namespace,
    source_protocol_sha256=original_protocol_sha,
    policy=SegmentPolicy(**reviewed_storage_limits),
)
manifest_pin = log.manifest_sha256
# Сохранить исходный pin за пределами изменяемой директории.
receipt = log.append('prepared', cleaned_capture_payload, expected_sequence=1)
```

Допускается только отсутствующая директория. Manifest связывает exact root,
source protocol SHA, storage policy и SHA реализации. Legacy root, alias,
symlink/hardlink, missing catalogue, WAL/SHM и изменённый manifest не принимаются.
Storage-компонент сам не удостоверяет, что source protocol допущен к запуску.
Цикл capture обязан до native operation дождаться durable prepared receipt.

Каждый frame содержит global sequence, kind, payload, previous SHA и собственный
SHA. Счётчик един для всех сегментов; новый файл его не обнуляет. Record размером
больше frozen limit отвергается до записи. Ротация происходит по числу событий
или фактическим bytes; sealed segment получает отдельный SHA в каталоге.
Inventory сегментов проверяется перед каждым обращением к каталогу: новый
посторонний файл блокирует append. При restart/seal весь committed prefix
активного сегмента читается и проверяется, включая середину, отдельно от
pending tail. Схема каталога проверяется до запросов к application tables.

## Аварийная запись и повтор

Каталог SQLite сначала фиксирует **точный следующий frame**, segment ordinal
и offset. После этого записывается/синхронизируется JSONL frame и только затем
двигается global head. Создание файла и его directory entry синхронизируются.

При открытии writer может завершить только известную pending-запись:

- если bytes ещё нет — дописать именно зарегистрированный frame;
- если записан его правильный prefix — дописать только недостающий suffix;
- если frame уже полный — завершить metadata commit;
- если tail отличается или есть лишние bytes — остановиться для review.

Truncate, автоматического удаления несовпавшего хвоста и подмены истории нет.
Повтор `append` с прежним sequence и теми же kind/payload возвращает duplicate
без дополнительного event. Иной payload на тот же sequence или sequence gap
отвергаются; original frame/hash chain проверяется и при duplicate retry.
Это идемпотентность storage; она не разрешает повторять неизвестную
native paper-операцию или exchange order.

SQLite сам восстанавливает собственный hot journal. Для оставшегося non-hot
rollback journal проверенного **active** каталога выполняется SQLite transaction
с recovery epoch; sidecars вручную не удаляются. Sealed catalogue с оставшимся
неустранимым sidecar требует review. Read-only verifier никогда не делает recovery.
Проверены реальные process-death сценарии на локальных synthetic источниках;
полная power-loss/filesystem/host qualification остаётся отдельной проверкой.

## Закрытие и потоковая проверка

```python
sealed = log.seal()
# Удерживать head и catalogue pins вместе с первоначальным manifest pin.
verified = log.audit(
    expected_head_sha256=sealed['head_sha256'],
    expected_catalog_sha256=sealed['catalog_sha256'],
)
```

После seal новые события запрещены. Audit принимает original manifest,
head и catalogue pins, проверяет все файлы/границы/размеры, sealed file SHA,
global sequence/hash chain и отсутствие source drift. Затем читает frames
через bounded `readline`, не собирая полную историю в list/dict.
`iter_events` — generator для будущего replay; его consumer обязан завершить
проверку всего потока, не публиковать частичный успех после первого yield.
Локальная lease исключает обычную одновременную запись во время verification.
Она не является multi-host fencing или внешним удостоверением времени.

Успешный результат содержит `storage_integrity_pass=true`, но всегда
`paper_evidence_pass=false`, `economic_profitability_established=false`,
`live_admission_granted=false`. Generic storage не знает end экономического
окна; future capture/runner обязан сохранить прежний sealed-window gate.
Hash chain не защищает от замены всех файлов вместе с внешними trusted pins.

## Подтверждённая локальная проверка

18октября: **1764passed,1deselected /421.60s** (`-m 'not integration'`).
Добавлено38тестов storage, включая actual process death, SQLite journal,
изменённую схему/середину active segment, повреждённый retry digest и лишний файл.
Публичный integration не запускался; его прежний DNS failure остаётся открытым.

Отдельный synthetic test сохранил10 005events в21segment, с fsync на durable
границах; запись/seal заняла251.69s, audit —1.246s, peak `tracemalloc` —148 779bytes.
Это маленькие искусственные records: не рыночные book payloads, не process RSS,
не full-worker tick и не прогноз производительности30-дневного study.
Measurement и source hashes: `.local/state/paper-segments-work-20261018/`.

## Что ещё нужно для длинного study

- [x] Typed new-namespace manifest и глобальный budget/counter.
- [x] Byte/count rotation, sealed hashes и cross-segment ordering.
- [x] Durable pending-frame recovery, exact retry и actual process-death tests.
- [x] Read-only bounded streaming storage verifier и external head/catalog pins.
- [x] Capture v3 adapter: preregistered segment manifests, original prepared/complete,
  terminal и роль/source identity, sealed future-window gate. Source/operation
  audit реализован; full FIFO/coverage/strategy admission не выдаётся.
- [x] Отдельный bounded native wallet/worker source storage: marks/fills/lots/segments,
  с сохранением последних anchors и исходных row IDs, без потери old evidence.
- [x] [Capture v4 integration](PAPER_CAPTURE_V4.md) связывает source archive/active checkpoint с
  prospective causal ledger; v3 roots не мигрируются и не очищаются.
- [x] [Отдельный streaming cash/FIFO/valuation/coverage replay](PAPER_STREAMING_REPLAY.md).
  Текущий v1/v2 verifier остаётся history-accumulating; на длинном run его не вызывать.
- [ ] Реальные quote/state size measurements и план достаточного disk/retention
  для трёх ролей. Размер synthetic records не является оценкой рыночных payloads.
- [ ] Actual protocol, qualified candidate, полное наблюдение, independent
  economics/review и admission. Старые ограничения не ослаблять ради старта.

### Приёмка следующей интеграции capture v3

Статусы ниже относятся к локальной реализации; actual study/admission открыты.

- [x] Новый schema/root и future registration: protocol фиксирует roles,
  lifecycle, source/runtime/Decimal, storage policy и общий budget. Отдельная
  исходная registration связывает protocol и созданный storage manifest до
  start; не создавать круговую зависимость их SHA и не наследовать v1/v2 pass.
- [x] Adapter сохраняет полные original inputs и durable prepared до native
  операции; complete связывает original source rows и before/after anchors.
  Завершённая storage pending-запись не разрешает повтор неизвестной операции.
  Unknown prepared outcome блокирует resume без resubmit/backfill.
- [x] Отдельный bounded source format для wallet `marks/fills/closed_segments/intents`
  и worker `worker_events/seen_predictions/intent_links`: original row IDs,
  counts, payload hashes, FIFO/cash/day anchors, pending intents и открытые lots.
  Удаление из НОВОЙ active DB допустимо только после durable verified archive
  и checkpoint; IDs нельзя перенумеровывать или переиспользовать после очистки.
  Существующий frozen PaperWallet/PaperWorker и их SQL не изменять.
- [x] Source-store crash tests между archive/active-state/checkpoint commits:
  ни пропавших rows, ни двойного учёта, ни пропуска losing fill/rejection.
  Проверить atomic seen-prediction→intent linkage, текущую семантику day-anchor
  и источник pending exits после restart — локальные source-store tests прошли.
  Capture v4 process-death/registration проверки выполнены локально;
  full-runner/host/power-loss qualification ещё открыта.
- [x] [Read-only wallet replay](PAPER_STREAMING_REPLAY.md) потребляет bounded stream и native row sources:
  cash/FIFO/basis/fees/slippage/rounding/minimum/depth/dust, raw market lineage,
  causal coverage/termination по original paper assumptions.
- [ ] Полный worker/opportunity/source replay и все original role decisions. Не вызывать старые
  `snapshot()`/fill auditor, собирающие всю историю, на длинном study.
  State/scratch/active-lot/pair bounds должны входить в frozen общий budget.
- [x] End-window gate проверяет только protocol/registration до end, не открывает
  rewards/event/source rows; generic storage seal не раскрывает paper outcomes.
  Ранний abort, no Buy после cutoff и разрешённый Sell проверены локально.
  Full late-completion/unknown-book/material inventory admission остаётся
  отдельной частью полного coverage/FIFO acceptance, ниже.
- [ ] Полный future-window acceptance: late completion, unknown liquidating
  book, remaining material inventory, complete coverage и role economics.
- [ ] Измерить реальные quote/state sizes, full polling/network/queue/write/replay
  wall time, process RSS и disk всех источников трёх ролей. Зарезервировать
  prepared/complete/terminal, catalogue journals и archive checkpoint до старта.
  Повторно выполнить capacity/resource qualification, затем preregistration и
  future collection; не уменьшать min30days/coverage и не ослаблять gates.

Актуальный прогресс — в [основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
