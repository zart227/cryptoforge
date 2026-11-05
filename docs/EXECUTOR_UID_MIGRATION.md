# Проверенный переход существующего журнала к UID ownership

`scripts/migrate_journal_uid.py` добавляет UID binding к существующему
credential-bound SQLite submission journal. Исходная база, её inode,
credential owner files, статусы заявок и резервы сохраняются. Это локальный
механизм R1/R15; он не выдаёт strategy/paper/live admission.

## Область применения

- [ ] Перед реальным переносом остановить все процессы, способные писать в
  журнал, включая legacy executor без UID guard. Выбрать согласованное окно
  обслуживания: перенос сам не обслуживает открытые позиции.
- [ ] Сохранить прежние key, endpoint, host, journal path и shared lock directory.
  Нужны обе исходные согласованные credential owner records. Unbound journal,
  смена ключа/хоста и восстановление потерянного журнала этим инструментом
  не поддерживаются.
- [ ] Поддерживается только exact `https://api.bybit.com`; alias/regional/testnet/
  demo/custom origins отклоняются до policy/locks/API. При retained account
  registry того же UID через прежний alias canonical bootstrap/migration
  блокируются. Не переименовывать и не удалять старые records ради обхода.
- [ ] Подготовить и отдельно проверить account policy по
  [account verification runbook](EXECUTOR_ACCOUNT_VERIFICATION.md).
  Prepare и apply выполняют только authenticated GET `/v5/user/query-api`;
  при отказе UID/permissions/IP/freshness перенос блокируется.
- [ ] База должна иметь исходную единственную таблицу `order_submissions`,
  режим DELETE и размер до 64 MiB; SQLite `-wal`, `-shm`, `-journal` не допускаются.
  Не удалять такие файлы вручную ради прохождения проверки. WAL-конвертация,
  восстановление повреждённой базы и расширенные схемы требуют другого review.
- [ ] Выбрать отдельные новые plan/backup paths вне lock directory. Они не
  должны пересекаться с входными и служебными путями или быть вложенными
  друг в друга. Symlink outputs и hardlink backup не допускаются.

Ниже — шаблон для выбранного окна обслуживания, а не выполненные production
команды. Credentials берутся существующим private client из environment;
не передавать их в аргументах и не включать в review artifacts.

## Подготовка и проверка

```bash
.venv/bin/python scripts/migrate_journal_uid.py prepare \
  --journal /absolute/original/orders.sqlite \
  --account-policy /absolute/reviewed/account-policy.json \
  --lock-directory /absolute/original/executor-ownership \
  --backup /absolute/review/original-orders-backup.sqlite \
  --plan /absolute/review/uid-migration-plan.json \
  --review-reference operator-review-reference
```

Prepare захватывает UID lock, затем credential lock. Он открывает SQLite
read-only, проверяет integrity/schema/каждый intent и сохраняет только plan.
UID owner files и backup на этой стадии не создаются. Существующий plan
никогда не перезаписывается.

- [ ] Проверить plan bytes и независимо получить их SHA256. Сверить resolved
  input/backup/lock paths, credential/host/UID/parent hashes и account policy SHA.
- [ ] Проверить journal device/inode, physical SHA, logical rows SHA, количество
  строк и распределение статусов. `prepared`/`unknown` не считаются неисполненными;
  ACK/observed не освобождаются. Факт миграции не подтверждает старые fills.
- [ ] Сверить `implementation_sha256`, включая CLI. Изменение этих исходников,
  любого исходного файла или journal inode делает plan неприменимым.
- [ ] Убедиться, что `live_admission_granted=false`, `orders_submitted=false`.
  Safe account observation не содержит raw key, secret, note или plaintext UID.

Поле `review_reference` — только ссылка на review. Инструмент проверяет
переданный SHA точных plan bytes; личность и независимость проверяющего
технически не удостоверяются.

## Применение

```bash
.venv/bin/python scripts/migrate_journal_uid.py apply \
  --plan /absolute/review/uid-migration-plan.json \
  --reviewed-plan-sha256 INDEPENDENTLY_REVIEWED_PLAN_SHA256
```

Apply заново проверяет inputs и свежую account identity под обоими locks.
Создаёт byte-identical независимый backup, затем immutable intent,
shared UID registry и `<journal>.account-owner.json`. Файлы публикуются
атомарно без overwrite, с mode0600 и fsync. Исходная база не переписывается,
её rows не reconcile/release; credential binding остаётся прежней.

- [ ] Сохранить result, reviewed plan, backup и migration intent вместе
  с hashes вне единственной копии рабочей машины.
- [ ] Сверить journal/backup SHA и сохранение исходных статусов/резервов.
- [ ] Проверить запуск того же владельца под UID lease в согласованной
  процедуре rollout. Другой key/host/path не должен получить новый namespace.
  Включение service и admission выполняются отдельным действием.

## Прерывание и конфликт

При прерывании повторить **тот же apply с тем же reviewed SHA**, сохраняя
inputs неизменными. Уже созданные outputs должны совпадать byte-for-byte;
оставшиеся дописываются из закреплённого intent. Fresh account query требуется
и при повторе. Новый prepare не заменяет начатую миграцию.

Любой конфликт, потеря исходной credential binding, замена journal inode,
изменение базы после review или неизвестная ownership lineage требуют
отдельного recovery review. Не удалять registry/intent и не заменять журнал
backup-копией: это не поддерживаемый rollback, inode binding будет нарушена.
Crash во время atomic publication может оставить temporary hardlink; если
backup имеет несколько links, инструмент блокируется до отдельной проверки.

Обычный UID lease по-прежнему не принимает частично записанные bindings.
После успешного переноса рабочие записи в журнал делают старый migration
plan неприменимым; повторный apply не является способом остановить или
откатить торговую историю.

## Выполненные локальные проверки и открытые пункты

- [x] Fake prepare/apply сохраняет DB bytes/inode, original owner records,
  `prepared`/`unknown`/ACK/observed reservations и поддерживает UID lease restart.
- [x] Прерывание перед каждым publication возобновляется только с тем же plan;
  conflicts, input/source drift, locks, malformed intent и API outage блокируются.
- [x] Отдельно проверены reserved/ancestor paths, SQLite sidecar collisions,
  замена inode при открытии DB, symlink outputs и hardlink backup.
- [ ] Production migration, реальные API/permissions/IP и сервисный rollout
  этим локальным прогоном не квалифицированы.
- [ ] Key rotation, restored/replaced journal, поддержка alternate endpoints, multi-host
  fencing и некооперирующие writers остаются открытыми. Нужны один canonical
  endpoint и общий local lock directory, как в
  [ownership runbook](EXECUTOR_ACCOUNT_OWNERSHIP.md).
