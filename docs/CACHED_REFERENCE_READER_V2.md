# Cached source view и исходные role offers

27 октября 2026. [Текущий чек-лист](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[source index v2](REFERENCE_PREFIX_V2.md), [исходная delivery](REFERENCE_DELIVERY.md).

## Завершённая область W8.2b.2a

- [x] Отдельная pre-start регистрация связывает пустые original queue и cash-only
  prefix index по исходным manifest/registration SHA. Только один полный poll
  на batch; price-model artifact и незарегистрированный новый источник не принимаются.
- [x] Reader читает уже существующий pending offer конкретной роли. Проверяются
  cursor/batch/delivery ID, original source reference, точная граница префикса
  и соответствие байтов каждого события одновременно в queue и prefix index.
- [x] Cached view используется только для того самого source head. Отставший
  batch блокируется: нет пропуска очереди, подмены старыми/новыми данными или
  изменения original offered_at/known_at. Необходимый backlog recovery ещё открыт.
- [x] Полный original packet, включая negative/failure observations, flags и
  closed-candle readiness, совпадает с прежним `ReferenceDelivery.read`.
  Проверено равенство решений прежнего cash contract для всех трёх ролей.
- [x] Вызов reader не делает offer, ack, source poll, worker tick или запись
  в queue/prefix. Нужны уже выданный delivery ID и current prefix reference.
  Registration/runtime, byte/wall limits и same-host leases проверяются.
- [x] В cached read не вызывается `SourceReplay.feed`. Physical SHA, attachment
  через прежний queue open/audit и некоторые SQL counts остаются полными;
  constant-time и long-throughput всего пути этим не доказаны.

## Проверки

- [x] 20 новых + 18 source-index compatibility cases: **38 passed / 10.14s**.
  Накопленная выборка — 788 разных cases, не полный suite. Прежние 597 Python-файлов
  сохранены; добавлены module и tests, теперь 599. Сохранены 19 source/test copies
  и 17 runtime keys.
- [x] Stale/foreign prefix, чужой или уже acknowledged offer, backlog, изменение
  регистрации, alias, backward clock, busy queue/prefix lease, недостаток byte
  budget и исчерпание whole-read времени блокируются без изменения pending offer.
- [x] Отдельная synthetic rehearsal: три poll, 12 original source events,
  девять packets и 18 cash decisions; четыре положительных решения по frozen
  rule. Для каждого packet и каждого cash decision подтверждено точное равенство
  прежнему reader; read не менял queue/index bytes. Есть positive, negative и
  source rate-limit case.

Эти четыре положительных решения — синтетическая проверка маршрута входных
данных. Worker не исполнялся, fills и доходность не оценивались. Сохранённые
ack в rehearsal явно относятся к input parity, не к actual worker result.

## Использование и границы

`CachedReferenceReaderV2.create(root, queue, prefix, ...)` создаёт отдельный
contract до original start. Reference содержит `root`, `manifest_sha256`,
`registration_sha256`. `open` не меняет компоненты.

`read(queue, current_prefix_reference, role, delivery_id)` возвращает исходный
`packet`, его SHA и отдельные reader/prefix references. Packet не содержит
добавленных служебных полей; proof отделён от него. Полнота source history
проверяется отдельным независимым `ReferencePrefixV2.audit`.

Budget packet совпадает с original queue maximum_delivery_bytes, wall budget
по умолчанию 10s, допустим 1–30s. Это cooperative check, не внешний watchdog.
Leases защищают выбранный same-host путь и не заменяют контроль других writers.

## Что ещё не сделано

- [x] W8.2b.2b: отдельный [cached cash application v3](CACHED_CASH_APPLICATION_V3.md)
  сохраняет reader proof вместе с actual prepared/completed result и safe result
  SHA ack. Synthetic independent controller/FIFO/source audits3/3 прошли.
  Прежние приложения/paired runner не менялись, monkey-patching не применялся.
- [ ] Полный paired coordinator, backlog/unknown parent/component recovery и
  integration в native/capture/independent worker replay. Existing exact-type
  guards не ослаблены для нового произвольного адаптера.
- [ ] Bounded physical history/SHA/source/delivery/native/capture quotas,
  actual positive/provider/fill/exit и whole-host/restart/load measurements.
- [ ] Current-model, R1–R16/VP/W9, independent review и economic/paper/live gates.

Evidence `.local/state/cached-reader-v2-work-20261027/verification.json`,
`synthetic-rehearsal-report.json`, test logs, 19 accepted source/test copies.
Новых public requests, actual worker/orders, primary PostgreSQL writes, model/risk/
trading changes и fits нет. Original sealed outcomes не читались. Все общие
admission flags остаются false.
