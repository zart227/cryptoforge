# Ограниченный native source archive для paper wallet/worker

19 октября 2026, Europe/Moscow. `native_paper_archive.py` реализует отдельный
НОВЫЙ формат состояния и архива. Это source-store с локально проверяемой
очисткой active projection. [Prospective capture v4](PAPER_CAPTURE_V4.md) теперь
связывает его с causal ledger; economic admission пока не подключён. V1/v2/v3, frozen native producers и старые studies не менялись.

## Формат и бюджеты

`NativePaperArchive.create` принимает отсутствующий nonsymlink root,
source protocol SHA, candidate SHA, role, PaperConfig, worker policy и явный
NativeArchivePolicy. Manifest связывает root/role/identities/config/runtime,
исходные SQLite schema SHA и budgets. Resume требует original manifest SHA,
не ремонтирует пропавшие native tables и не принимает legacy DB/root.

Число shards — фиксированная степень2 от1до64. Shard выбирается по SHA
source+original key; lookup использует SQLite index. Все записи shard имеют
порядковый номер и hash chain; native row хранится целиком, с исходным JSON
payload и ID. Каждый shard и active DB ограничены64MiB, active rows —4096,
row —256KiB, batch —1MiB/256rows. Это верхние технические границы;
конкретные frozen policy значения могут быть ниже и не увеличиваются после
outcomes. Общие record/byte/disk/memory budgets проверяются независимо.

`max_page_count` задаётся на writer connections, включая attached worker DB;
SQLite отклоняет рост сверх числа страниц ([SQLite PRAGMA](https://www.sqlite.org/pragma.html#pragma_max_page_count)).
Удалённые active rows освобождают страницы для повторного использования;
VACUUM и обещания немедленного уменьшения physical file size нет. Archives
никогда не удаляются ради продолжения run. Исчерпание budget требует остановки
и нового review, без reset счётчиков и попыток.

Архивируются исходные rows:

- wallet: marks, fills, closed_segments, terminal intents, закрытые zero lots
  и immutable day anchors;
- worker: worker_events, seen_predictions и intent_links.

Cash/policy, открытые lots, market cache, worker identity и pending intents
сохраняются в active projection. Unified reader добавляет их текущие source
rows к архиву без повторного учёта совпадающих anchors. Market-cache universe
и pending/open state остаются ограниченными policy; бесконечный basket не
поддерживается и не квалифицирован этим компонентом.

## Порядок compaction

1. Shared namespace lease останавливает cooperating native writers. Проверяются
   manifest/schema/identity, active bounds и global archive budgets.
2. Исходные native rows читаются bounded batches и фиксируются в индексированных
   archive shards. Повтор exact key+row идемпотентен; изменённый immutable row
   отвергается. Global record budget считается по persisted shard counters.
3. Источники проверяются повторно: их fingerprint, exact row hashes и protected
   projection не должны измениться. Ошибка archive оставляет active rows.
4. Wallet/worker/checkpoint объединяются через ATTACH в одну DELETE-mode SQLite
   transaction. Только rows с проверенной durable archive copy удаляются.
   Одновременно обновляются checkpoint generation и high-water IDs.
5. После commit проверяются anchors и protected cash/lot/day/pending state.

Условия atomic attached transaction включают disk-backed main DB и отсутствие
WAL ([SQLite ATTACH](https://www.sqlite.org/lang_attach.html)). Здесь используется
synchronous=FULL. Это основание реализации, а не power-loss qualification
конкретного host/filesystem. Hot journals восстанавливает SQLite; оставшиеся
non-hot journals завершаются SQLite transaction на проверенных участниках.
Sidecars вручную не удаляются.

Проверены actual subprocess exits после archive commit, перед projection commit
и после него. Resume не исполняет native operation повторно. Archive copies,
оставшиеся при незавершённой очистке, допустимы и сверяются с active rows.

## Anchors и повторная подача

Сохраняются latest mark и latest known-equity mark, последние два day anchors,
max-ID row marks/closed_segments/worker_events. Поэтому native integer IDs
продолжают расти после DELETE. High-water проверяется и по архивным индексам:
обнуление checkpoint не скрывает пропавший active anchor.

Retained fills включают entry fills открытых lots и последний Buy активной пары;
порядок latest fill учитывает UTC и исходное tie behavior. Pending intents и их
original links остаются доступными для exits. Перед новой записью резервируются
row slots; Buy не расходует весь pending capacity. Продажа нескольких lots
резервирует место для всех возможных FIFO segments.

ArchiveAwareWallet/Worker используют индекс для старых intent/prediction IDs.
Удалённая из active seen-history запись не становится unseen. Seen→intent→link
фиксируются одной attached transaction; ошибка не оставляет половину связи.
Incoming prediction batch ограничен по всему входу, включая archived duplicates.
Native snapshot явно `history_scope=bounded_active_projection_not_full_history`;
его нельзя выдавать за полный export результатов.

## Read-only reader и границы

`seal()` фиксирует source file SHA; original manifest и seal SHA удерживаются
снаружи namespace. `NativePaperArchive.reader` не делает recovery, проверяет
sealed files и читает unified rows через merge отсортированных cursors.
Хранится bounded число row heads, а не вся история. Смена источников во время
чтения блокирует итоговый pass. Изменённый/пропавший shard не считается
отсутствием prediction. Writer после seal не возобновляется.

У source-store **нет экономического end-window gate**. Seal этого компонента
не разрешает раскрывать prospective paper rewards и не заменяет terminal/full
capture. Public audit CLI для обхода temporal gates не добавлен. Source reader
вызывает новый capture v4 только по исходным gates; standalone source API
не является публичным prospective performance reader.

`native_source_integrity_pass=true` означает целостность archive+projection.
Всегда `paper_evidence_pass=false`, `economic_profitability_established=false`,
`live_admission_granted=false`. Нового qualified candidate/study, training,
реальных API/orders, model publication или service changes не было.

## Чек-лист

- [x] New namespace/manifest/native schemas/runtime и bounded indexed shards.
- [x] Persisted global record budget, byte/page/active-row limits и restart guards.
- [x] Durable archive→verify→atomic cleanup/checkpoint; no prune при ошибке.
- [x] High-water IDs, cash/FIFO/day anchors, pending exit context и exact dedupe.
- [x] Archive-aware wallet/worker, atomic seen→intent→link и bounded input batch.
- [x] Read-only external-pin reader, streaming union и duplicate/drift checks.
- [x] Local process-death/failure/tamper tests и synthetic10 005worker-row test.
- [x] [Capture v4](PAPER_CAPTURE_V4.md): новый prospective protocol/registration, causal events,
  archive/checkpoint references и end-window sealed CLI. V3 по-прежнему
  требует count=max(ID); его root нельзя чистить или обновлять этим форматом.
- [x] [Streaming FIFO/fill math/valuation/time coverage](PAPER_STREAMING_REPLAY.md) по paper model.
- [ ] Full worker strategy decisions/opportunity/source capture и paired roles.
- [ ] Actual market/state sizes, process RSS/full tick/queue/network/shared-role
  budgets, host/power-loss/independent review и actual future study/admission.

Receipts: `.local/state/native-paper-archive-work-20261019/`.
Текущая очередь — в [основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).


Итоговая проверка19октября: **1846 passed, 1 deselected /359.50s**,37новых cases.
Synthetic10 005worker rows в4shards: запись/compaction/seal 9.97s, audit 1.729s, peak Python allocations 154845bytes, active worker file 32768bytes.
Это source-store measurement; actual market payloads, process RSS и full
worker/host/economic qualification этим не подтверждаются.
