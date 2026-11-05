# Один локальный исполнитель на UID и endpoint

Подготовлен opt-in флаг `--account-ownership-guard`. Он требует
`--entry-account-policy` и связанный submission journal, а через account policy —
runtime approval и остальные защитные флаги. Установленный service не менялся.

Это дополнительный локальный слой R1/R15. Ключ блокировки определяется по
hash UID и endpoint, а не API-key fingerprint. Два процесса с разными ключами,
заявляющими тот же UID/endpoint, используют один неблокирующий flock в
`.local/state/executor-ownership/accounts`. Затем захватывается прежний
credential lease: порядок захвата всегда UID → credential.

UID guard и reviewed migration теперь допускают только точный
`client.base_url=https://api.bybit.com`. Другой регистр, явный порт, path/query,
`api.bytick.com`, региональный адрес, testnet/demo и custom proxy отвергаются
до policy IO, locks и authenticated request. Это ограничение подготовленного
режима, а не утверждение о недоступности этих API: официальный
[Bybit guide](https://bybit-exchange.github.io/docs/v5/guide) перечисляет оба
mainnet адреса и отдельные региональные endpoints.

Прежние hashes ключей и exact endpoint owner records не нормализуются и не
переписываются. Под UID lock проверяются другие retained account registries:
найденная прежняя привязка того же UID через иной endpoint/filename запрещает
bootstrap нового журнала. Нечитаемый/неизвестный registry также требует review;
scan ограничен1024records/64KiB на сторонний record. Переход с прежнего alias
требует отдельного восстановления; текущая migration не меняет endpoint.

## Первое создание

Для нового отсутствующего journal выполняется authenticated query-api через
существующий strict account verifier. UID/parent/key/permissions/IP/freshness
должны совпасть с явно выбранной policy. При unknown/mismatch journal и
account owner records не создаются. Внутренние ошибки private request не
выводятся вместе с raw key/response.

После создания credential-bound journal записываются два immutable private
account owner records: общий для UID/endpoint и `<journal>.account-owner.json`.
Они фиксируют credential/host/UID/parent hashes, endpoint, абсолютные пути,
policy SHA, device/inode journal и безопасную projection исходного подтверждения.
Записи публикуются без overwrite. Raw ключ, secret, note и plaintext UID в них
не сохраняются. Это локальные records, не подписанное биржей свидетельство.

Переход существующего credential-only/unbound journal автоматически запрещён.
У существующего service/journal нет автоматической миграции в новый режим.
Для существующего согласованного credential-bound журнала подготовлена
отдельная [процедура prepare/review/apply](EXECUTOR_UID_MIGRATION.md),
сохраняющая DB bytes/inode, статусы и резервы. Production migration не выполнялась.
Нельзя удалять owner records или выбирать новую пустую DB для снятия blocker:
сохраняющиеся UID/credential registries не допускают такую смену владельца.

## Повторный запуск и отправка

Повторный запуск допускается только с теми же key/host/endpoint, policy bytes,
путями и original journal device/inode. Нужны обе согласованные account records
и прежняя credential binding. Изменение ключа, IP policy или пути требует
отдельного reviewed recovery. Замена БД даже идентичной копией меняет inode и
останавливает режим; restore/host transfer не получает автоматического допуска.

Для того же проверенного владельца повторное получение key-info не является
условием захвата lease. Сохранённая UID binding подтверждает исходную привязку;
она **не** подтверждает текущие permissions. Их fresh проверка перед Buy
сохраняется. Поэтому временный query-api outage может запретить Buy, сохранив
разрешённый stop Sell с fresh per-symbol quantity/price/order checks.

Lease удерживается весь `run_cycle`. Перед каждой парой и raw Market/Limit
submission проверяются активность lease в этом PID, credential scope,
неизменность owner records, inode lock-файла и journal. После выхода из context,
замены/утраты state или смены credentials нельзя отправить новый Buy/Sell.
Kill/no-new-entry, runtime approval, risk guards и submission journal продолжают
работать; cached ACK не становится повторной отправкой.

Credential sidecar старого формата не переписывается и сохраняет
`account_uid_verified=false`. Новый account record/diagnostic использует
отдельное `account_uid_verified_at_binding=true`. Поля risk snapshot:
`account_ownership` и `configured_protections.verified_account_ownership`.
Они не являются live/strategy admission.

## Проверено локально

- [x] Разные ключи одного UID при одном exact canonical endpoint/shared local
  lock directory блокируются одновременно и после рестарта при
  попытке выбрать новый journal. Второй journal не создаётся.
- [x] Реальный отдельный процесс: UID lock contention, process kill, повторный
  запуск того же владельца без сброса original journal bytes.
- [x] Legacy journal, foreign UID, changed host/endpoint/policy, missing journal,
  partial sidecar write и замена journal inode требуют recovery.
- [x] Изменённые account/credential records, lock inode или credentials запрещают
  новые Buy/Sell; client после завершения lease тоже не отправляет заявки.
- [x] Фактический launcher `main` не допускает второй key к cycle; fake
  `run_cycle` с уже проверенной binding сохраняет stop Sell при query-api outage.
- [x] Canonical endpoint проверяется до bootstrap/migration и на active submit;
  синтаксические/domain aliases не создают новую namespace. Retained legacy
  alias owner запрещает canonical bootstrap без изменения original files.
- [ ] Real account bootstrap/restart, production journal migration/recovery,
  смена ключа/IP и disaster recovery ещё не квалифицированы.

## Границы

Нужны один canonical endpoint и общий локальный lock directory. Это защита
сотрудничающих процессов, включивших текущий режим. Отдельные
копии lock directory, другой хост, legacy executor без UID guard и сторонние
программы/ручные операции не получают распределённую блокировку. Не удалять и
не заменять lock-файлы работающего процесса.

Поддержка alternate endpoints/regions, multi-host fencing и operational
qualification миграции существующего журнала
остаются открытыми пунктами. Независимые strategy/paper evidence и проверка
реального account/runtime contract также обязательны; весь R1 этим не закрыт.
