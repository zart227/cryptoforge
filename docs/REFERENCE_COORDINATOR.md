# W7b.1: ограниченный координатор source → delivery

Дата: 26 октября 2026. [Текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[source ledger](REFERENCE_SOURCE_LEDGER.md), [retained delivery](REFERENCE_DELIVERY.md).

Координатор создаёт **новый** собственный source/delivery namespace и выполняет
сбор по закрытым пятиминутным окнам. Исходные 563 Python-файла не переписываются.
Код: `src/cryptoforge/reference_coordinator.py`, CLI
`scripts/coordinate_reference_sources.py`, тесты `tests/test_reference_coordinator.py`.

## Приёмка

- [x] Создание source/queue до начала нового prospective окна, frozen runtime,
  модель и policies; отдельный явный diagnostic режим.
- [x] Poll только для нового 5m anchor; повтор в том же окне не делает GET,
  не создаёт новые forecasts и не обновляет original observation timestamps.
- [x] Mandatory BTC/ETH, rate-limit cooldown и original failures/skips сохраняются.
  Для каждого frozen model pair сохраняется forecast либо явный отказ по входам.
- [x] Bounded ingest, unresolved anchors блокируют delivery, все три роли получают
  одинаковые original source events и отдельные delivery IDs.
- [x] Перед каждой операцией durable prepared, после — completed с exact новыми
  source/queue descriptors. Одновременный stale writer блокируется.
- [x] Diagnostic input packet и его receipt сохраняются **до ack**. Offline audit
  сопоставляет их с original retained source replay, batch, role offer и ack.
- [x] Контроль текущего tail: возраст poll, missing tail slots, source backlog,
  freshness и cooldown; внутренние пропуски остаются в delivery audit.
- [x] Foreground run ограничен числом шагов и временем допуска следующего шага.
  Непрерывный systemd service этим CLI не устанавливается.
- [x] **31 новых +413 compatibility =444 разных tests passed /113.32s**;
  общий repository suite заново не запускался.
- [x] Actual public26октября: два соседних5m windows, по360closed rows,
  два original AVAX forecasts; повтор внутри первого окна без GET/новых events.
  Durable packets6, cursors2/2/2,48coordinator events; independent audit/recover.
- [ ] W7b.2: отдельные candidate/control/stress cash-entry contracts, полный
  actual strategy opportunity stream и применение к CapturedPaperWorkerV2.
- [ ] W7b.3/W8: recovery незавершённых component operations, host service,
  длительная capacity/recovery проверка и independent review.
- [ ] W6b.3b/R4: фактическое обновление reference rows основной локальной БД,
  REST→instance linkage и работа выбранного installed feeder.

## Режимы и смысл подтверждений

`create --start ... --end ...` регистрирует prospective **source-only** collector.
Он собирает исходные данные и пополняет delivery queue, но не выдаёт и не
подтверждает worker deliveries. Такой collector сам по себе не является новым
paper/economic study и не наследует admission прежних протоколов.

`create --diagnostic-input-consumers` без `--start` включает три встроенных
потребителя диагностических входов. Они сохраняют exact packet bytes и receipt
`diagnostic-reference-input-read-v1`, затем подтверждают его digest. Это чтение
входов, а не исполнение cash worker. Этот режим нельзя включить в prospective
namespace. Везде `worker_execution_qualified=false`,
`cash_entry_contract_available=false`,
`strategy_opportunity_completeness_verified=false`; paper/economic/live gates false.

Никаких `would_enter`, настоящих orders, обучения, публикации модели или
изменения primary PostgreSQL/PostgREST здесь нет. Price forecast не содержит
доказанного net payoff после fees/slippage и не заменяет entry policy.
Готовые paper v2 kernels сохраняют свои contracts; новый cash adapter — W7b.2.

## Команды

Новые output roots, внешние receipts сохраняются вне coordinator root.
Без ключей, `.env`, private API, endpoint override, fallback и `--as-of`.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/coordinate_reference_sources.py create \
  --output .local/state/NEW-coordinator --diagnostic-input-consumers \
  > .local/state/NEW-created.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/coordinate_reference_sources.py run \
  --reference-file .local/state/NEW-created.json --steps 2 --seconds 15 \
  > .local/state/NEW-run.jsonl

tail -n 1 .local/state/NEW-run.jsonl > .local/state/NEW-latest.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/coordinate_reference_sources.py audit \
  --reference-file .local/state/NEW-latest.json > .local/state/NEW-audit.json
```

Для нового frozen price model можно заранее добавить `--artifact-file FILE`
и дополнительные `--pair AVAX/USDT`. BTC/ETH остаются обязательными. Forecast
создаётся только для пар из original model artifact, без расширения trained scope.
Старые source/queue roots CLI не принимает и не усыновляет.

`step` выполняет один ограниченный проход без ожиданий. `run` выводит одну JSON
строку после каждого завершённого прохода; последняя содержит новый checkpoint.
Default: максимум360 шагов/1800s, интервал допуска≥5s; за проход≤2ingests и
≤1пакета на роль. Внутри прохода source poll≤75s, delivery ingest≤90s, bounded
replays≤60s; общий `--seconds` ограничивает начало следующего прохода, **не является
таймаутом остановки уже начатой операции**. Host full-tick latency ещё не измерена.

## Сбой и целостность

Prepared/completed records неизменяемы, имеют sequence/hash chain, canonical
JSON и original timestamps. Запись идёт через private same-directory temp,
fsync, rename и directory fsync. Временный файл, gap, неизвестный packet либо
незавершённая операция блокируют дальнейшую работу; cleanup не выполняется.

Если все операции завершены, а внешний checkpoint потерян, `recover` принимает
известный ancestor, проверяет цепочку, текущие exact component pins и полный
source/delivery/diagnostic receipt replay. Возвращается **новый** checkpoint:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/coordinate_reference_sources.py recover \
  --reference-file .local/state/NEW-created.json > .local/state/NEW-recovered.json
```

Если component commit состоялся, но coordinator completed не успел сохраниться,
старый component DB pin отвергается. Если остался только prepared, следующий
effect также запрещён. Этот coordinator **не восстанавливает неопределённую
component operation автоматически**. Recovery source poll/journal/worker/host —
отдельный открытый пункт; удалять journal или менять старые SHA нельзя.

Caps по умолчанию: journal≤2048events/16MiB, один record≤64KiB,
diagnostic packets≤192files/8MiB each/64MiB total. До начала effect резервируются
два максимальных journal records. На packet требуется полный max packet reserve;
непоместившийся packet не подтверждается. Floor свободного диска≥2048MiB плюс
резервы; source/queue дополнительно проверяют собственные caps и disk reserves.
Долговременная очистка, рост и одновременный RSS трёх настоящих workers — W8.


Actual replay сохранил35 initial missing5m slots: source namespace создан
08:56:27UTC, первый poll11:54:33UTC. Между двумя выполненными polls gaps нет;
current tail0 не отменяет initial gap. Continuous source completeness=false.

## Evidence

Work root `.local/state/reference-coordinator-work-20261026/` содержит baseline
563 Python files/6 документов, тестовые логи и последующую verification receipt.
Текущая реализация не читает sealed study outcomes. Frozen cash train cutoff
7ноября00:59:16МСК, validation21ноября00:59:16МСК, первый blind WF15ноября03:00МСК
остаются в силе. LLM-план по-прежнему выполняет другой агент.

Actual polls завершились11:54:35.757039UTC и11:55:33.335336UTC; forecasts созданы
до targets12:05/12:10UTC. Outcomes не читались. Сохранённый inference envelope
SHA2a7afd1e... соответствует прежнему diagnostic migration-v3`041b`; ни
candidatea252, ни активная модель не менялись. Source events6→12, distinct
versions360→363, forecasts1→2. Обе тройки имеют общий batch SHA внутри тройки.
Final receipt: `.local/state/reference-coordinator-work-20261026/verification.json`.
Accepted17source/test copies, `pytest-final.log`, actual JSONL/packet files,
full CLI audits и explicit ancestor recover receipts лежат рядом.
