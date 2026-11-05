# Проверка идентичности счёта и прав ключа перед входом

Подготовленный opt-in флаг `--entry-account-policy PATH` требует режима
`--entry-runtime-approval` с его защитами и фиксированным SHA модели. В
действующий service этот флаг не добавлен. Политика с реальными UID/IP не создана.

Используется аутентифицированный GET `/v5/user/query-api` текущим ключом.
Названия и типы полей сверены с официальной документацией
[Get API Key Information](https://bybit-exchange.github.io/docs/v5/user/apikey-info).
Этот endpoint возвращает UID, parent UID, тип ключа, разрешения и привязанные IP.
Он доступен ключам master/sub account. Применяемая здесь политика намеренно
ограничена личным Unified Spot ключом субсчёта.

## Явная политика

Пример формата с **вымышленными** UID и тестовым IP:

```json
{
  "schema_version": "bybit-spot-account-policy-v1",
  "expected_uid": "101",
  "expected_parent_uid": "10",
  "expected_ips": ["192.0.2.1"],
  "maximum_response_age_seconds": 10
}
```

Операторский источник реальных ожидаемых UID и whitelist нужно проверить
независимо от самого ответа API. Скрипт не выбирает счёт и не переносит капитал.
UID задаются canonical positive decimal strings без ведущих нулей; parent
должен отличаться от child. IP — непустой набор отдельных адресов IPv4/IPv6
без wildcard/CIDR и duplicates. Политика не поддерживает широкие сетевые диапазоны.
Срок свежести задаётся явно, целым числом от 1 до 30 секунд.

Сначала проверяется политика и ответ при старте цикла. Затем непосредственно
перед каждым Market Buy выполняется новый authenticated запрос. Проверяются:

- `apiKey` соответствует текущему ключу; `secret` явно пустой.
- `userID` — integer и совпадает с expected UID; `parentUid` — ожидаемая
  строка, `isMaster=false`. При наличии ненулевого `userIDInt64` он должен
  совпасть с тем же UID.
- Строгие типы и значения `readOnly=0`, `uta=1`, `type=1`, `isFixApi=false`.
  Missing fields не превращаются в безопасные defaults.
- Явные core permission lists: только `Spot=["SpotTrade"]`, а Wallet,
  ContractTrade, Derivatives, Options — пустые. Любая другая непустая
  permission group, malformed list или duplicate permission запрещает вход.
  В частности, Wallet Withdraw/Transfer не допускаются этой политикой.
- Whitelist ответа точно соответствует проверенной политике. Это проверка
  конфигурации ключа; отдельного определения публичного egress IP здесь нет.
- Successful envelope и integer server timestamp; ответ не будущий и не старше
  заданного срока относительно UTC host clock, считанного после запроса.

Изменение policy bytes после загрузки запрещает вход; путь/SHA включены в
runtime fingerprint. Реальные ограничения IP/expiry или несовпадение часов
могут безопасно заблокировать запрос. Серверная timestamp не доказывает
атомарность нескольких независимых запросов или отсутствие следующей смены прав.

## Порядок и диагностика

Путь Buy: journal prepare → risk/reservation queries → operator controls →
fresh account/key check → final runtime approval/TTL → raw submit.
Медленный запрос UID не продлевает срок разрешения. Локальный отказ даёт
`blocked` в submission journal; неизвестность биржевого исполнения не создаётся.

Sell проходит прежние exit/quantity/order/control/journal guards и не читает
entry account policy/query-api. Неизвестные права или UID не становятся
приказом слепой продажи. Kill продолжает запрещать новые Sell; no-new-entry
оставляет разрешённые выходы.

Private risk snapshot содержит `entry_account_policy_sha256` и
`entry_account_observation`. Это projection с hash UID/parent UID/key/IP/
permissions, временем и флагами совпадения. Raw response, API key, secret и
note не сохраняются. Projection — факт одного ответа, не архивная сертификация.

## Проверено и осталось

- [x] Строгие типы, missing/foreign UID/key, parent/master, read-only/non-UTA,
  extra permission, wildcard/different IP и stale/future response regression.
- [x] Полный fake launcher cycle: правильный scope допускает одну fake Buy;
  Wallet Withdraw, добавленный после старта, запрещает submit/status=blocked.
- [x] Missing policy не обрывает existing stop Sell. Slow query после истечения
  runtime approval не получает прежний TTL; API outage не пишет sensitive error
  в journal или обычное сообщение launcher.
- [ ] Реальная проверка выбранного ключа/счёта/IP и source latency не выполнена.
- [x] Подготовлен отдельный [локальный UID lease](EXECUTOR_ACCOUNT_OWNERSHIP.md)
  для cooperating процессов с разными ключами и общим lock directory.
  Credential lease не переписан: его `account_uid_verified=false` сохраняется.
- [ ] Реальная миграция journal/смена ключа, endpoint aliases и другой хост
  требуют отдельной ownership/recovery квалификации.
- [ ] Full independent strategy/paper evidence, capital/risk review и rollout
  остаются открытыми. Наличие UID response не даёт live admission.

Существующий paper acceptance остаётся conditional research simulation с
`live_promotion_allowed=false`. Он не переименовывается в разрешение торговли
при успешной проверке UID или при наличии operator runtime approval.
