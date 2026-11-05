# Cached reader → фактический paper worker → архив квитанций

27 октября 2026. [Текущий чек-лист](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[reader v2](CACHED_REFERENCE_READER_V2.md), [receipt archive v2](CASH_APPLICATION_V2.md).

## Принятая область W8.2b.2b

- [x] Новый `cached-cash-worker-application-v3` регистрируется до original start.
  Parent contract связывает cash contract, actual frozen worker, original queue,
  зарегистрированный cached reader и отдельный дочерний archive v2.
- [x] Packet читается через новый reader. Прежний `queue.read` не вызывается,
  старые приложения/регистрации/type guards не меняются и не monkey-patchятся.
- [x] Reader/prefix references, packet SHA и parent manifest SHA записываются
  в исходный `input.json`. Actual worker-result связывает SHA именно этого
  input, настоящие prepared/completed frames и результат `worker.tick`.
  Queue ack по-прежнему подтверждает SHA фактического worker-result.
- [x] Пустой tick сохраняет отдельный heartbeat proof, выполняет pending fills,
  marks/exits и не создаёт opportunities или source acknowledgement.
- [x] Завершённые группы losslessly сохраняются прежним archive v2. До original
  end `audit` скрывает показатели. После конца окна полный аудит проверяет
  parent/reader proof, original batch/ack и packet view через полный SourceReplay.
- [x] Истёкшее окно, чужой worker/reader, изменённая регистрация, alias, backward
  clock, busy parent lease и storage limits блокируются. Unknown worker result
  сохраняет error group и не может автоматически повторяться.

## Приёмка

- [x] 17 новых + 39 неизменённых reader/archive compatibility cases:
  **56 passed / 124.44s**. Накопленная выборка — 805 разных cases; полный suite
  не повторялся. Прежние 599 Python-файлов сохранены, теперь 601.
  Сохранены 61 source/test copy и 77 runtime keys.
- [x] Настоящий process exit42 после archive commit, но до выдачи нового parent
  checkpoint: исходный checkpoint остаётся blocked, повторного worker execution
  нет. Parent/whole-runner recovery этим не реализован.
- [x] Отказ cached read до worker сохраняет первоначальный pending offer.
  С тем же offer и правильным prefix reference разрешён нормальный повтор,
  который создаёт intents один раз. Unknown worker effect к этому случаю
  не относится и остаётся blocked.
- [x] Отдельная synthetic rehearsal использует настоящий класс paper worker:
  три роли, 12 applications, шесть source opportunities и девять heartbeats.
  Все три source/reader proof audits и независимые controller/FIFO replay
  прошли; проверено 4/0/4 fills, включая синтетические покупки и выходы.
- [x] Reader proof сохранён во всех 12 исходных input files. Source ack трёх
  ролей совпадает с SHA actual worker-result, не SHA input-only packet.

Синтетические quotes и clocks проверяют механизм исполнения. Этот результат
не доказывает улучшение дохода, работу на реальном рынке или достаточность
ресурсов для длительного периода. Control остаётся `cash_only`, а не действующей
основной моделью.

## Использование

`CachedCashApplicationV3.create(root, cash_contract_reference, queue, worker,
reader, ...)` создаёт новый parent и дочерний archive до start.
`apply(queue, worker, current_prefix_reference)` — явная local paper операция.
Сохранять весь возвращённый parent reference: `root`, `manifest_sha256`,
`registration_sha256`, вложенный `application_reference` archive v2.
Также сохранять новый `queue_reference` из результата.

`open` — operational attachment с проверкой текущего archive head и reader proof.
`audit(queue)` до конца окна возвращает metadata без полного source/receipt
replay; после end проверяет полный сохранённый поток. Queue должна быть исходной,
с current внешним checkpoint после всех операций ролей.

Original source/prefix physical files изменяются при append. Старый физический
SHA не выдаётся за сохранённую копию поздней БД. Исторический packet view отдельно
воспроизводится из original retained queue source events. Новые worker/cash
receipts и их SHA сохраняются побайтно в дочернем archive.

## Оставшаяся работа

- [ ] W8.2b.3: общий заранее зарегистрированный coordinator, который сохраняет
  prepared/completed вокруг source poll, prefix update, queue ingest и каждого
  role tick; покрыть read failures до application group и parent/lost receipt.
- [ ] W7b.3b: unknown component/worker effects и whole-runner/host recovery.
  Нижележащий v2 helper не означает разрешение автоматически усыновить parent.
- [ ] Bounded physical source/delivery/index/native/capture history, новые
  count/byte/shard/replay budgets и measurements под нагрузкой. Старый W8.1
  preflight оценивает прежний профиль; новый long admission ещё не выдан.
- [ ] Actual positive/provider/fill/exit paired stream, current-model comparison,
  chosen-host restart/capacity, independent review и R1–R16/VP/W9/economic gates.

Evidence `.local/state/cached-cash-application-v3-work-20261027/verification.json`,
`test-coverage.json`, `synthetic-rehearsal-report.json`, capture/native/queue roots,
12 original reader proofs, worker seals и independent replay registrations.
Public network, primary PostgreSQL/model/risk/trading changes, fits и настоящие
orders отсутствуют. Original sealed outcomes не читались. Все общие
`full_worker_or_host_qualified`/paper/economic/live flags false.
