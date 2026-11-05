# W7a: сохранение source history и доставка трём ролям

Дата: 23 октября 2026. [Единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[source ledger](REFERENCE_SOURCE_LEDGER.md), [предыдущий reader](REFERENCE_SOURCE_READER.md).

Реализована отдельная `ReferenceDelivery`: исходные source events сохраняются
один раз в append-only SQLite, затем candidate/control/stress читают одни и те же
пакеты с независимыми курсорами. Исходные manifest, raw responses, версии,
forecast IDs и hash chain сохраняют свою идентичность после новых source polls.
Это source-input delivery; реальные workers, cash decisions и торговля не запускаются.

Продолжение26октября: [координатор W7b.1](REFERENCE_COORDINATOR.md) реализован
отдельным runtime. Он автоматизирует source polling/delivery и сохраняет
диагностические input receipts; W7b.2 cash workers и W7b.3/W8 interrupted recovery
остаются открытыми. Ниже исходная приёмка W7a23октября.

## Приёмка и границы

- [x] W7a: retained original source-event prefix с original SHA/availability,
  raw failure/negative/skip outcomes и независимым offline replay.
- [x] Source rollback/divergence, missing rows, reorder и ложные forecasts
  выявляются; first-seen/version index восстанавливается из сохранённой истории.
- [x] Bounded ingest по целым операциям, без разрыва poll и скрытого пропуска
  forecasts; общий пакет имеет один SHA, delivery ID зависит от роли.
- [x] Durable role cursor/pending offer/ack, repeated offer без обновления ID/time,
  idempotent acknowledgement и явное восстановление после потерянной квитанции.
- [x] Тесты настоящего process death до commit и после commit, quota/rollback,
  journal guard, source removal, source/frame tampering и clocks.
- [x] 39 новых +374 compatibility =413 разных tests passed /27.98s;
  общий repository suite заново не запускался.
- [ ] W7b: automatic bounded polling/coordinator, source progress monitoring,
  все actual strategy opportunities, candidate/control/stress cash policies,
  durable worker application receipts и полное paired-worker wiring.
- [ ] W6b.3b/R4: фактический reference refresh рабочего feeder/primary DB,
  REST→instance/source linkage и deployment health.
- [ ] W8/W9: whole-worker/host RSS/throughput/disk/recovery/review, qualified
  candidate и новое future economic/paper study. Общие W7/W6/W5 открыты.

Код: `reference_delivery_source.py`, `reference_delivery.py`,
`scripts/deliver_reference_sources.py`, тесты `tests/test_reference_delivery.py`.
Предыдущие559 Python-файлов не изменены. LLM выполняет другой агент.

## Что именно сохраняется

Queue registration сохраняет exact original source manifest/registration/model
bytes и их pins. Ingest сначала проверяет текущий external source receipt и весь
source ledger. Затем копирует непрерывный префикс original events с прежними
sequence/previous/head SHA. Копия всего растущего SQLite-файла для каждого poll
не создаётся: хранение пропорционально объёму новых событий.

**Исходные физические SQLite bytes не сохраняются.** Старый `database_sha256`
остаётся частью исходного observation descriptor; он не объявляется SHA новой
БД и не заменяется её текущим hash. Новый retention contract подтверждает
семантический event prefix относительно исходных manifest/head anchors.
`source_sqlite_bytes_retained=false`. Старый `ReferenceMarketReader.open` остаётся
строгим; retained inputs читает новый `DeliveredReferenceReader`.

Большая история копируется ограниченными порциями. Пакет может ссылаться на
проверенный source head, который ещё не полностью скопирован. До сохранения
всего этого anchor он имеет `unresolved_source_attestations>0` и не выдаётся
ни одной роли. `retained_source_integrity_pass=false` до разрешения anchors;
проверка самой цепочки отдельна. Пропущенные source rows не подменяются пустотой.

Replay восстанавливает exact original closed120 windows, first-seen и revisions,
все исходные price forecasts и их features/probability/source links. Cadence
между сохранёнными polls фиксирована5m: отсутствующие slots отражаются явно,
venue cooldown pauses считаются отдельно. Это проверка сохранённого префикса;
непрерывное наблюдение будущего tail и все strategy opportunities ещё не доказаны.
`source_poll_completeness_verified=false` даже при нуле внутренних gaps.

## Доставка и подтверждения

У каждой роли cursor подтверждённых пакетов и максимум один pending delivery.
`next` выдаёт cursor+1; повтор возвращает прежние delivery ID и offered_at,
не добавляя event и не освежая source timestamps. Переход к следующему пакету
происходит только через `ack` с соответствующим role/delivery ID и digest receipt.
Wrong-role/out-of-order и conflicting repeated ack отвергаются.

**Ack означает регистрацию consumer receipt, не доказанное исполнение worker.**
Текущая реализация проверяет SHA и порядок, но не сертифицирует содержимое
торгового worker receipt. `worker_execution_qualified=false`. Полная привязка к
durable worker tick/result и cash policy остаётся W7b.

`DeliveredReferenceReader` возвращает closed120 `CandleRow`, features с precision28,
все source events пакета и original forecasts, включая отрицательные. Forecast
старого контекста сохраняется, но не считается текущим входом нового window.
Source available time не заменяется временем доставки. Failed/stale обязательная
пара или возраст последнего close>600s блокируют candle read; старые forecasts
сохраняются с `usable_price_input_now=false`. Cash `would_enter` не создаётся.

Одна роль может отставать, остальные сохраняют свои pending/cursors. Пакеты и
source events после ack не удаляются. Компакция/retention после завершения study
требуют отдельного protocol; невозможность дальнейшего append не обходится
ослаблением зарегистрированных caps.

## Команды

Создавать prospective queue нужно до start **нового пустого prospective source**.
Для read-only diagnostic существующего source явно используется `--diagnostic`;
такую очередь нельзя усыновить как зарегистрированное economic study.
Все output roots новые, descriptors сохраняются вне queue root.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py create \
  --source-reference-file .local/state/NEW-source-registration.json \
  --output .local/state/NEW-delivery > .local/state/NEW-queue.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py ingest \
  --reference-file .local/state/NEW-queue.json \
  --source-reference-file .local/state/NEW-latest-source.json \
  > .local/state/NEW-queue-after-ingest.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py next \
  --reference-file .local/state/NEW-queue-after-ingest.json --role candidate \
  > .local/state/NEW-candidate-offer.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py read \
  --reference-file .local/state/NEW-candidate-offer.json --role candidate \
  --delivery-id DELIVERY_ID > .local/state/NEW-candidate-input.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py ack \
  --reference-file .local/state/NEW-candidate-offer.json --role candidate \
  --delivery-id DELIVERY_ID --worker-receipt-sha256 RECEIPT_SHA256 \
  > .local/state/NEW-queue-after-ack.json
```

После каждого изменения coordinator обязан сохранить **новый** external queue
descriptor. Три роли имеют независимые cursors, но записью в SQLite владеет один
coordinator: конкурентный stale writer не усыновляет изменения другого процесса.
API: `ReferenceDelivery.create/open/ingest/next/read/acknowledge/audit/recover`,
`DeliveredReferenceReader.open(queue, role, delivery_id)`.
Никаких keys, private/order APIs, endpoint overrides или `--as-of` нет.

## Сбой и recovery

Source append + batch + queue event/state либо offer/ack + cursor фиксируются
одной SQLite transaction. Если commit состоялся, а external receipt потерян,
обычный `open` со старым database SHA отвергается. Явная read-only команда
`recover` проверяет известный старый head как ancestor и полностью воспроизводит
новую историю/проекции. Она выдаёт **новый checkpoint**, не объявляя прежние DB
bytes текущими. Unknown ancestor или изменённый prefix отвергаются.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py recover \
  --reference-file .local/state/KNOWN-queue-checkpoint.json \
  > .local/state/RECOVERED-queue-checkpoint.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/deliver_reference_sources.py audit \
  --reference-file .local/state/RECOVERED-queue-checkpoint.json
```

Process death **внутри незавершённой transaction** может оставить SQLite journal.
Он явно блокирует open/recover до отдельного host recovery; его нельзя удалять
или автоматически усыновлять. Проверка этого отказа выполнена, но actual host
recovery/cleanup ещё W8. Завершённый commit без выданной квитанции восстановлен
в тесте с настоящим `os._exit`, delivery ID при повторе сохранён.

Default caps: queue DB4GiB, scratch256MiB, events/source events100000,
batches10000, chunk≤256source events/4MiB, delivery≤8MiB, ingest≤90s,
replay≤60s. Disk reserve≥2048MiB + scratch +3(chunk+delivery).
Весь новый prefix проверяется scratch replay **до commit**. Переполнение основной
БД или scratch не продвигает архив/курсор. SHA считается streaming; full-host
RSS/capacity по этим caps не объявляется измеренной. Floor2048MiB не снижался.

## Evidence

Actual diagnostic23октября:

- Public source polls завершились16:52:01.826550UTC и16:55:44.652287UTC,
  каждый прочитал120AVAX+120BTC+120ETH closed rows. Distinct source versions360→363,
  original events6→12 после создания по одному AVAX price forecast на poll.
- Declared model — прежний migration-v3`041b` через неизменённый inference envelope
  SHA`2a7afd1e362d337b6dcef16ba9fee2cce15f98ab14e36311224ea2292fb000a2`.
  Probabilities0.14958024611222948 и0.14915049078091916 — price diagnostics,
  не cash decisions/доход. Targets17:05/17:10UTC, outcomes не читались.
- После второго poll старый physical source DB pin отвергается. Queue сохранила
  прежние source events, delivery IDs и offered_at; все три роли повторно
  прочитали старые inputs, затем новые. Shared batch SHA одинаков внутри каждой
  тройки, role delivery IDs различаются.
- Final replay:12source events/14queue events/2batches,0unresolved anchors,
  0внутренних missing slots; cursors candidate=control=stress=2.
  Consumer receipts подтверждают диагностическое чтение, не работу cash worker.
- Явный known-ancestor recovery выполнен с ранее сохранённого checkpoint;
  новый head полностью replayed, старые physical DB bytes не усыновлены.

`.local/state/reference-delivery-work-20261023/` содержит checkpoint559files,
accepted15 runtime/test copies, `pytest-acceptance.log`, actual source/queue/role
receipts, `verification.json` и `verify.py`. Фактическая сверка двух source
checkpoints и восстановленных role reads приведена в verification receipt.
Основная PostgreSQL/PostgREST БД, services/model/risk не менялись; ни новых fits,
ни реальных сделок, ни чтения sealed outcomes нет. Общие paper/economic/live gates=false.
