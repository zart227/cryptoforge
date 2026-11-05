# Перенос проверенной дневной базы equity

Инструмент `scripts/recover_daily_equity_state.py` сохраняет и восстанавливает
только исходную базу **текущего UTC дня**. Он не запрашивает баланс, не выбирает
новую базу по текущей equity и не отправляет заявки. После восстановления
дневной убыток продолжает считаться от исходного `start_equity`.

Это узкая часть R5/R15. Она не переносит order journal, ownership registry,
drawdown peak/latch, outbox, позиции или секреты. Перенос реального работающего
executor на другой хост и восстановление повреждённого state ещё требуют
проверки фактического счёта, полноты резервной копии и единственного исполнителя.
Generic `cryptoforge-backup` не включает этот state в default include paths.

## Подготовка источника

- [ ] Для реального переноса запретить новые входы на действующем пути исполнения
  и исключить одновременное управление с двух хостов. Сам инструмент не останавливает
  сервисы. Установка файла controls не включает его в сервис, запущенный без флага.
- [ ] Подтвердить счёт/endpoint независимо от содержимого backup. Явный
  `account_scope` — SHA256 согласованного идентификатора области счёта, а не API
  secret. Инструмент проверяет равенство переданного scope; он не верифицирует
  exchange UID. Fingerprint ключа не объединяет разные ключи одного счёта.
- [ ] Проверить, что исходный файл содержит последнюю согласованную исходную
  базу этого UTC дня. Его SHA256 нужно получить и проверить независимо от backup.
  Наличие корректного JSON само по себе не доказывает правильность baseline.
- [ ] Указать новый путь backup. Существующий backup не перезаписывается.

Пример с явно подставляемыми проверенными значениями:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/recover_daily_equity_state.py backup \
  --state /absolute/path/live-equity-risk.json \
  --output /absolute/path/new-daily-baseline-backup.json \
  --account-scope '<REVIEWED_ACCOUNT_SCOPE_SHA256>' \
  --reviewed-state-sha256 '<REVIEWED_ORIGINAL_STATE_SHA256>'
```

Сохранить выведенный `backup_sha256` отдельно от переносимого файла.
SHA проверяет неизменность относительно известного значения, не авторство
или подлинность произвольно предоставленной копии. В backup остаются точные
исходные bytes, их SHA и время захвата. Допускаются legacy поля `date` и
`start_equity`, а также явный `timezone="UTC"`. Duplicate keys, неизвестные
поля, нечисловая/неfinite/отрицательная база и другой день отклоняются.

## Восстановление

- [ ] Сверить scope и известный SHA backup на принимающей стороне.
- [ ] Проверить UTC день и часы. Yesterday/future backup и future captured_at
  отклоняются; локальная полночь не заменяет полночь UTC.
- [ ] Destination должен отсутствовать. Даже повреждённый существующий файл
  не заменяется инструментом. Сохранение/разбор повреждённого файла и выбор
  правильного источника — отдельная reviewed recovery процедура, без удаления
  state для снятия blocker.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/recover_daily_equity_state.py restore \
  --backup /absolute/path/new-daily-baseline-backup.json \
  --state /absolute/path/missing-live-equity-risk.json \
  --account-scope '<SAME_REVIEWED_ACCOUNT_SCOPE_SHA256>' \
  --expected-backup-sha256 '<INDEPENDENTLY_RETAINED_BACKUP_SHA256>'
```

Операции используют тот же неблокирующий `.lock`, что и daily risk gate.
Публикация атомарна и запрещает overwrite, файл имеет права `0600`.
Concurrent rollover/restore, ошибка записи или несовпадение SHA дают ненулевой
код возврата. После ошибки fsync результат нужно проверить: публикация могла
успеть завершиться, повторный restore не перезапишет её.

- [ ] Сверить `restored_state_sha256` с проверенным исходником.
- [ ] На изолированном runtime проверить, что уже достигнутый daily loss
  продолжает запрещать Buy, а разрешённые exits сохраняют свой отдельный путь.
- [ ] Не считать `status=completed` допуском торговли: инструмент всегда
  возвращает `live_admission_granted=false`. Снятие прочих blockers и реальное
  переключение хоста в этот инструмент не входят.

## Выполненные локальные проверки 16 октября

- [x] Round trip legacy/UTC state сохраняет bytes и baseline без подстановки
  текущей equity; equity97 при baseline100/limit2 всё ещё блокирует Buy.
- [x] Отказ для NaN/Infinity, duplicates, неверного SHA/scope/дня/clock,
  занятого lock, existing destination и injected failure перед публикацией.
- [x] CLI запущен отдельными процессами в двух изолированных каталогах:
  backup → restore → actual daily risk gate → повторный restore отклонён.
  Receipt: `.local/state/daily-risk-recovery-cli-drill-20261016.json`.
- [ ] Actual-account identity, перенос между физическими хостами, повреждённый
  production state и общий backup/restore executor пока не квалифицированы.
