# Привязка разрешения новых входов к runtime

Подготовлен opt-in режим `--entry-runtime-approval PATH` вместе с
`--entry-model-sha256 SHA256` и `--ml-mode gate`. Он добавляет обязательную
локальную проверку операторского разрешения перед Market Buy. Установленный
сервис не переведён на этот режим; разрешающий production файл не создан.

Это часть R1/R2: привязка разрешения к конкретной конфигурации, коду и модели.
Она не выдаёт независимый допуск стратегии, не подтверждает прибыльность,
permissions, exchange UID, paper results или операционную готовность.

Дополнительно подготовлен [entry-account-policy](EXECUTOR_ACCOUNT_VERIFICATION.md):
строгая проверка authenticated UID/subaccount/key permissions/whitelist при
старте и перед Buy. Её path/SHA включены в runtime contract. Опциональная
проверка сама не обновляет existing credential ownership lease. Дополнительно
подготовлен [account-ownership-guard](EXECUTOR_ACCOUNT_OWNERSHIP.md) для одного
UID/endpoint и общего локального lock directory; full multi-host ownership открыт.

## Что фиксируется

`supabase-executor-runtime-v1` содержит:

- SHA ключа, endpoint и SHA хоста из existing credential scope; raw API key
  и secret не попадают в контракт. `account_uid_verified=false` сохраняется.
- Численные CLI лимиты и их фактические единицы: stake/daily loss в USDT,
  stop/drawdown/dust — доли; ML threshold/age, количество позиций и timeout.
- Fallback pairs, режим research selection и flags входов/защит. Динамический
  результат selector не становится фиксированным историческим universe.
- Абсолютные пути journal, outbox, controls, daily/peak state, ownership
  registry, fractional policy и самого approval file.
- SHA первоначально загруженной fractional policy и явного набора файлов
  runtime, включая launcher, executor, model inference, risk, journals,
  ownership, selectors и market clients. Это явно перечисленная поверхность
  кода, а не полный transitive dependency/environment snapshot.
- SHA разрешённого активного model artifact. Имя версии модели не заменяет SHA.

Полный контракт и его SHA записываются в private atomic
`.local/state/live-risk-snapshot.json` как `runtime_approval_contract` и
`runtime_approval_sha256`. По ним можно проверить конкретный набор параметров.
Diagnostic `configured_protections.runtime_approval=true` означает подключение
проверки, а не состоявшийся допуск торговли.

Режим требует всех подготовленных entry protections:
`exit-data-fallback`, `submission-risk-guard`, `spot-reservation-guard`,
`local-order-reservations`, journal/outbox/controls paths, drawdown state с
явным threshold и fractional policy. Неполный набор CLI отклоняется до чтения
credentials. Значения действующего сервиса автоматически не меняются.

## Формат локального разрешения

Отказывающий пример структуры, не готовое разрешение:

```json
{
  "schema_version": "executor-runtime-approval-v1",
  "approved": false,
  "runtime_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "valid_from": "2026-10-16T00:00:00Z",
  "valid_until": "2026-10-16T23:59:00Z",
  "review_reference": "UNREVIEWED_EXAMPLE"
}
```

При `approved=true` необходимы точный SHA контракта, непустая review reference
и aware timestamps. Проверяется интервал `valid_from <= now < valid_until`,
длительность больше нуля и не более 24 часов. Строка/число вместо boolean,
duplicates, лишние поля, missing/corrupt file, unknown clock и несовпадение
fingerprint запрещают Buy. Файл следует обновлять атомарно, например через
`cryptoforge.atomic_reports.write_json_report`, с ограниченными правами записи.

Review reference — ссылка/идентификатор внешнего операторского решения,
а не проверенное этим кодом доказательство. JSON не является подписанным
аттестатом. До реального разрешения остаются независимая стратегия, paper,
актуальный account/runtime contract и операционные проверки R1–R5/R15.
Ни один исследовательский receipt автоматически не конвертируется в approval.

## Проверка перед отправкой

Порядок Market Buy: durable journal prepare, submission risk queries,
operator controls, optional account/key verification, runtime approval,
raw exchange submit. Разрешение заново
читается **после** запросов риск-данных. Отзыв в ходе этих запросов блокирует
send и даёт journal status `blocked`, а не неизвестный exchange outcome.
Cached ACK существующей заявки по-прежнему не отправляет новый ордер.

На начале цикла фиксируется контракт; перед Buy он вычисляется повторно.
Изменение source/configuration во время цикла запрещает вход даже при записи
нового approval: текущий процесс не должен автоматически принимать новый код
как уже загруженный. Изменение policy после её загрузки тоже блокирует вход.
Source SHA на диске не заменяет проверку чистого запуска/окружения при rollout.

Active model registry дополнительно обёрнут в pin: свежая `latest()` должна
вернуть именно ожидаемый SHA. Missing/mismatch/error не превращается в entry
fallback, поскольку поддерживается только ML gate mode. Перед submit
проверяется, что использованный `_last_model_input` относится к этому же
artifact и symbol. Новый опубликованный model artifact автоматически не
получает старое разрешение. Research candidate observations не являются
допуском их исполнения.

Sell проходит через прежние exit/quantity/order/control/journal проверки
без чтения entry approval. Missing/expired/revoked approval не становится
приказом закрыть или отменить позицию. Kill switch продолжает блокировать
новые Sell; no-new-entry сохраняет разрешённые exits.

## Выполнено и осталось

- [x] Unit/fake-client проверки изменения stake, threshold, model SHA,
  journal path, key/endpoint/source/policy, invalid/expired/future approval.
- [x] Полный fake `run_cycle`: pinned model → риск/резервы → один acknowledged
  Buy; отзыв approval во время risk query → ноль заявок, journal `blocked`.
- [x] Full outage cycle с отсутствующим approval сохраняет один разрешённый
  stop Sell. Неполный CLI configuration не доходит до credentials.
- [ ] Реальные account UID/permissions/capital/operator decision,
  независимые strategy/paper evidence, multi-host ownership, source/runtime
  environment qualification и включение сервиса ещё не подтверждены.
