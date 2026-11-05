# Проверка увеличения ёмкости forecast ledger, 1 ноября 2026

Для восстановления записи выбран рост бюджета существующего файла с 256 до
512 МиБ через `CRYPTOFORGE_PRIMARY_FORECAST_MAXIMUM_MB`. Файл, схема, ID и
читатели не переключаются. Минимальный резерв свободного диска остаётся 2048 МиБ.
Производственные writers и health CLI используют `PrimaryForecastMemory.from_env`;
переменную необходимо загрузить в окружение процесса. Конструктор без `from_env`
сохраняет прежний бюджет 256 МиБ для изолированных исследований.

Независимая проверка этого чата выполнена на копии свежего read-only snapshot:
`.local/state/forecast-capacity-recovery-20261101/snapshot/manifest.json`.
Он содержит 47 979 forecast и 47 722 outcome versions, integrity `ok`;
исходная база не изменялась snapshot-инструментом. Копия находится на том же
диске и не является независимой резервной копией.

На отдельной копии `rehearsal.sqlite` прежний бюджет блокирует запись. Бюджеты
512 и 1024 МиБ позволяют записать синтетический prospective forecast и его matured
outcome. SQL `EXCEPT` подтверждает сохранение всех исходных строк обеих таблиц,
включая ID, raw payload, digest и observed_at. Inode не меняется, итоговый
`integrity_check` возвращает `ok`; counts становятся 47 980 / 47 723.
Синтетические данные записаны только в rehearsal, не в рабочую базу.

Receipt: `.local/state/forecast-capacity-recovery-20261101/capacity-rehearsal.json`.
Воспроизводимый скрипт рядом: `verify_capacity.py` (требует нового target файла).
Проверки forecast memory, outcomes, health, snapshot и report: **40 passed**.

Эта проверка подтверждает запись без split/cutover. Реальную активность writer
нужно проверять отдельно по свежему времени и росту counts в рабочей базе.
Старые 279 unresolved прогнозов остаются за пределами 36-часового batch; увеличение
ёмкости не восстанавливает их исторические endpoint и времена доступности.

## Подтверждение рабочего цикла

1 ноября в 19:06 МСК независимая read-only health-проверка подтвердила
лимит 512 МиБ, отсутствие capacity blockers и 47 993 прогнозов вместо 47 979.
Последний прогноз — 19:06:04 МСК 1 ноября. Размер файла — 268 496 896 байт.
`production-health.json` содержит актуальный срез. SQL EXCEPT против snapshot
подтвердил сохранение всех исходных строк и outcome versions в рабочей базе,
`integrity_check=ok`: `production-preservation.json` рядом.

Проверка копии именно при 512 МиБ:
`capacity-rehearsal-512.json`, скрипт `verify_capacity_512.py`.
Новые рабочие outcome на момент проверки ещё не записаны: первые прогнозы
должны созреть. Старые 279 unresolved этим изменением не восстановлены.
