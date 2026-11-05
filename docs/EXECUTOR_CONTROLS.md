# Операторские переключатели Supabase executor

Подготовленный opt-in путь: `--execution-controls /absolute/path/controls.json`.
Установленный service пока не использует этот флаг. Пример с запретом новых
входов: [executor-controls.example.json](../config/executor-controls.example.json).

Схема `executor-controls-v1` требует настоящие JSON boolean:

- `no_new_entry=true`: запрет Buy; Sell для управления открытыми позициями
  допускается при прохождении остальных проверок.
- `kill_switch=true`: запрет всех новых Buy и Sell. Он не закрывает позиции
  и не отменяет уже принятые биржей orders. Для сохранения выходов используется
  no_new_entry, а не kill_switch.
- Оба false снимают только эти операторские запреты. Это не admission модели
  и не обход остальных risk/source/ownership blockers.
- Missing, unreadable, malformed JSON, неверная версия, duplicate fields,
  string/number вместо boolean запрещают обе стороны до восстановления файла.

Файл перечитывается перед каждым market/limit submit. При использовании
submission journal проверка находится после durable intent commit, но до
биржевого вызова. Локально отклонённый intent получает status=blocked;
неизвестность exchange outcome для него не создаётся. Повтор с тем же link
не отправляется: новый разрешённый сигнал должен иметь новый link.

Обновлять файл следует атомарно, например через существующий
`cryptoforge.atomic_reports.write_json_report`; частичная запись иначе
временно запретит submissions. Не удалять journal/ownership files для снятия
blocker. Операторские controls, order journal и decision outbox — отдельные файлы.

Control adapter защищает market/limit методы, вызываемые этим executor.
Он не управляет другими программами, открытыми вручную позициями, cancel API
или биржевыми защитными ордерами. Live smoke, startup outage, account UID,
общий admission и multi-host ownership остаются отдельными пунктами плана.

## Повторная проверка текущих лимитов перед покупкой

Opt-in `--submission-risk-guard` использует существующие `--stake-amount`,
`--max-open-positions`, `--max-daily-loss` без смены их значений. Daily loss
задан в USDT, а не процентах. Market Buy qty — quoteCoin сумма; Sell qty —
baseCoin количество, его этот entry guard не ограничивает размером stake.
Непосредственно перед Buy повторно читаются equity, USDT wallet balance,
inventory и daily-risk baseline. Local denial фиксируется как blocked при
использовании submission journal. Limit orders этот guard отклоняет как
неподдерживаемый контракт, а не пересчитывает их qty в quoteCoin.

Это ограниченный слой текущих абсолютных лимитов. Он не подтверждает
процентный HardRiskConfig, persistent peak drawdown, reserved funds/available
margin или отсутствие pending orders на других symbols. Порог material
position сохраняет существующие 1USD. API walletBalance не является отдельным
доказательством свободной покупательной способности. Rollout требует закрытия
соответствующих R1–R5/admission пунктов; установленный сервис пока без флага.

## Ограниченная проверка резервов Spot

Дополнительный `--spot-reservation-guard` требует `--submission-risk-guard`.
Поддерживается только явно non-borrowed USDT cash: `locked` и `bonus`
вычитаются из walletBalance, неизвестные поля не заменяются нулём. Ненулевые
borrowAmount/spotBorrow/totalOrderIM/totalPositionIM запрещают новый вход.
Это намеренно ограниченный контракт, не формула available margin для UTA.

Все страницы open Spot orders запрашиваются openOnly=0, без symbol filter.
Полный terminal cursor обязателен; missing/repeated cursor, duplicate orders,
API error или достижение ceiling20pages запрещают Buy. Pending Buy symbols
учитываются вместе с material holdings без двойного счёта одного symbol;
pending target symbol запрещает ещё одну покупку. Locked funds не вычитаются
повторно через leavesValue. Sell не зависит от этой entry-only проверки.

Семантика сверена15октября с официальными
[wallet balance](https://bybit-exchange.github.io/docs/v5/account/wallet-balance)
и [open orders](https://bybit-exchange.github.io/docs/v5/order/open-order).
REST snapshots не атомарны и могут запаздывать. ACK ещё не видимого ордера,
durable local reservations, other-product collateral и real-account validation
остаются открытыми пунктами R3. Установленный сервис не изменён.

## Локальный резерв до отражения ордера в REST

`--local-order-reservations` требует `--submission-risk-guard` и
`--order-submission-journal PATH`. Durable Buy intents со статусами
prepared/unknown/acknowledged/observed занимают quote capital и symbol slot.
Текущий intent исключается из собственного резерва. Restart, пустая bounded
history и отсутствие ордера в open-orders не снимают резерв. Локальный отказ
blocked резерв не занимает. Это закрывает локальную часть ACK visibility gap.

Automatic release допускается только при matching acknowledged order ID,
link/symbol/side, terminal cancel/reject/deactivate и явных нулевых cumExecQty
и cumExecValue. Partial/filled/unknown amounts сохраняют резерв. Сам по себе
ACK не fill и не evidence освобождения средств. Освобождение после исполнения
и последующего закрытия требует отдельного qualified accounting settlement.

Пока local reserve вычитается консервативно сверх remote cash bound и может
учесть уже locked средства повторно. Это safety bound, не точная equity или
бухгалтерия прибыли. Запускать как готовую production reservation policy до
lifecycle/settlement qualification нельзя; installed service без этих флагов.

## Ограниченный settlement полностью закрытого цикла

Opt-in `--settle-closed-reservations` требует `--local-order-reservations`.
Поддерживается одна зарезервированная Buy по symbol и известные локальные
Sell после неё. Collector читает exact orderId history и все execution pages,
потом open symbol orders и explicit final base-coin wallet. No-submit path:
он не создаёт/отменяет ордера. Источники сохраняются вместе с source SHA.

Verifier требует Filled orders, zero leavesQty, полное совпадение cumExecQty/
cumExecValue с unique fills, original link/symbol/side/orderId и request units.
Received buy base минус base fee должен точно совпасть с consumed sale base
плюс base fee; продажи не предшествуют последнему buy fill. Допускаются
только явно известные base/USDT fees, без extraFees. Финальный base wallet,
locked и borrow amounts должны явно равняться нулю; open orders отсутствуют.
После proof журнал получает released_closed; исходный link не пересылается.

Схема не закрывает partial/dust/multiple-buy FIFO, third-token fees и операции
вне этого локального цикла. Default execution history имеет ограниченный
период; пустые/неполные fills не снимают резерв. Raw response timestamps ещё
не квалифицируют полную snapshot atomicity/latency. Математический closeout
не является доказательством прибыльности или independent strategy admission.
API contract проверен по официальным
[executions](https://bybit-exchange.github.io/docs/v5/order/execution) и
[order history](https://bybit-exchange.github.io/docs/v5/order/order-list).
Actual-account validation и включение в service остаются открытыми.

## Завершённые частичные исполнения

Proof-v2 дополнительно допускает Spot `PartiallyFilledCanceled` с положительными
исполнениями, полностью совпадающими с cumulative totals. `PartiallyFilled`
остаётся открытым статусом и не даёт release. Для Buy проверяется executed
quote value относительно исходного quote budget; base qty не сравнивается с
quote amount. Для Sell executed base не превышает original base request;
leavesQty не должен превышать неисполненную часть. Filled Sell по-прежнему
требует полного original requested base qty.

Несколько terminal closing sales допускаются, только когда вместе полностью
потребляют полученный buy inventory с base fees, без reuse execIDs и при
нулевом final wallet. Неисполненная часть отменённого ордера не считается
полученной/проданной. Contradictory partial-canceled status с нулевыми fills
не попадает в zero-fill release shortcut. Источник terminal semantics:
[Bybit orderStatus](https://bybit-exchange.github.io/docs/v5/enum#orderstatus).
Actual-account source validation и несколько Buy/FIFO ещё не квалифицированы.

## Несколько локальных Buy одного symbol

Closed cohort verifier поддерживает несколько terminal Buy и closing Sell,
включая чередование Buy/Sell во времени. Каждый order проверяется прежним
exact-order verifier; received/consumed base учитывает fees. FIFO queue
распределяет Sell только на уже полученные local lots. Нельзя покрывать
раннюю продажу будущей покупкой или неизвестным initial inventory. Все lots
должны закрыться, final base wallet должен быть zero, open orders отсутствовать.

Mixed Buy/Sell в один timestamp не имеют доказанного порядка: такой cohort
сохраняет резервы. Same-side ties сортируются по execId детерминированно;
это не доказательство реального биржевого порядка и не cost-basis/profit claim.
Proof хранит quantity FIFO allocations и original responses/source SHA.

Все Buy резервы cohort снимаются одной transaction. Перед commit повторно
проверяются intent SHA/status, а исполнения из ранее released proofs нельзя
использовать повторно. Сбой любого update откатывает всю группу. Это не
разрешение дополнительных входов: existing one-symbol entry/reservation
policy не расширена. Actual-account multi-buy/dust/third-token qualification,
snapshot latency и rollout по-прежнему открыты.

## Сохраняемый максимум equity и просадка

Opt-in `--drawdown-state PATH --max-portfolio-drawdown FRACTION` требует
submission risk guard и bound order journal. Порог задаётся явно: конечное
число больше0 и не выше0.10; действующие численные лимиты автоматически не
меняются. Owner ID — SHA canonical credential_scope (key/endpoint/host),
а не подтверждённый exchange UID. State имеет схему
`observed-portfolio-drawdown-v1`, owner_id, maximum_drawdown, peak_equity,
last_equity, observed_at и boolean breach_latched. Peak/last/threshold —
decimal strings; observed_at — aware timestamp. Источник initial peak должен
быть проверен отдельно: guard не создаёт baseline по текущей equity.

Startup и каждый market Buy проверяют current account equity. Peak растёт,
но никогда не уменьшается при rollover/restart. Достижение порога включает
breach_latched; восстановление equity автоматически не разрешает торговлю.
Missing/invalid/duplicate fields, future time, другой owner/threshold,
неатомарная ошибка записи или lock contention дают Buy blocker. Peak updates
атомарны; Sell не зависит от доступности entry drawdown state.

Это максимум только наблюдавшихся при проверках значений. Пропущенные пики
между запусками не реконструируются. Показатель account-wide и не скорректирован
на deposits/withdrawals; он не является доходностью стратегии. Нужны reviewed
initial state, cashflow/source qualification и отдельная recovery процедура.
Installed service пока без новых флагов; автоматического latch reset нет.

## Процентные ограничения новой покупки

`--fractional-risk-policy PATH` требует remote Spot и local order reservation
guards. Policy JSON `fractional-entry-risk-v1` содержит только schema_version
и decimal strings maximum_position_fraction, maximum_planned_risk_fraction,
round_trip_cost_fraction. Position fraction должна быть>0 и<=0.05, planned
risk fraction>0 и<=0.005; costs явно>=0 и<1. Stop fraction берётся из того же
CLI stop-loss-percent, который получает executor. Unknown/missing costs не
заменяются нулём. Политика читается до сетевых действий цикла, SHA сохраняется
в risk snapshot; mid-cycle изменения файла не меняют уже загруженную policy.

Проверяется existing symbol USD value + requested quote notional относительно
current equity, включая остаток меньше material-position threshold. Planned
loss = quote notional × (stop fraction + roundtrip cost fraction). Точное
достижение порога допустимо; превышение отклоняет заявку без auto resize или
увеличения capital/stake. Market Buy проверяется непосредственно до send;
Sell не зависит от этих entry-only ограничений.

Расчёт не гарантирует фактический убыток при gaps/slippage/stop outage и не
доказывает качество заданной cost assumption. Aggregate risk существующих
позиций, real fee/stop/source qualification и полный admission остаются
открытыми. Никакая готовая разрешающая policy для installed service не создана.

## Общий баланс недоступен, отдельная позиция известна

Account-wide entry snapshot проверяет finite/nonnegative equity/USDT wallet,
unique valid coin names/values и explicit USDT row. Unknown snapshot означает
Buy blocker и entry slots0; equity/positions/capacity в диагностике остаются
null, а не вымышленными нулями. Daily и peak baseline не обновляются по таким
данным. Цикл продолжает known/fallback/доступные held pairs и возвращает
unhealthy status, даже если отдельный exit удался.

Known coin с неизвестной valuation можно проверить отдельно по свежему
per-symbol balance. Если сама quantity/инструмент/цена/open-order status
недоступны, автоматическая продажа вслепую не выполняется. При полном отказе
inventory нельзя обещать обнаружение ранее неизвестных outside-universe
позиций. Реальный private API outage/recovery и operational rollout открыты.

Если первый discovery query завершился ошибкой, а последующий validated
account sizing snapshot восстановился, material holdings из его точных coin
rows дополняют evaluation pairs в текущем цикле. Новый третий wallet query
не нужен. Уже добавленные пары не дублируются; market refresh запрашивается
только для вновь обнаруженных. Диагностика сохраняет evaluation_pairs.
Это recovery одного запроса, а не решение полного private API outage.

При полном отказе обоих candle sources exit fallback возвращает `recovery_required`: cycle exit code=1 даже при healthy reconciliation. Entry blocker сохраняется для следующих пар этого цикла; выходы при доступных данных продолжаются. Новый цикл начинает новую проверку источников. Это не подтверждение состоявшегося выхода или непрерывного stop coverage.

## Привязка к рассмотренному runtime

Подготовлен отдельный opt-in runtime approval и active model pin. Полный контракт/порядок wrappers/границы qualification описаны в [EXECUTOR_RUNTIME_APPROVAL.md](EXECUTOR_RUNTIME_APPROVAL.md). Проверка находится непосредственно перед raw Market Buy, после risk queries и controls; Sell не зависит от entry approval. Это один необходимый операторский gate, а не полный strategy/paper/live admission. Installed service не переведён на этот режим.
