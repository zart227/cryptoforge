# Снимок диагностики прогнозов — 28 октября 2026

`src/cryptoforge/forecast_memory_snapshot.py` и
`scripts/snapshot_primary_forecast_memory.py` создают отдельный снимок SQLite
диагностических price-прогнозов. Исходный файл открывается `mode=ro`; SQLite
backup выполняется в одной читающей транзакции с фиксацией schema и числа строк.
Снимок проверяется полным `integrity_check`, подсчётом ссылок на отсутствующие
forecast ID и потоковыми SHA-256 по всем типизированным исходным значениям в
порядке первичных ключей. Сохраняются все версии результатов, включая поздние
исправления, и JSON без нормализации. Снимок и manifest — приватные файлы.

Команда требует новый каталог и заранее проверяет свободное место: резерв
2 GiB плюс две копии логического размера и 64 MiB. Максимум исходной базы —
1 GiB, срок проверки по умолчанию — 120 секунд; встроенный срок не заменяет
ограничение процесса при зависшем вводе-выводе. Неуспешный каталог сохраняется
для анализа, молчаливого возобновления/удаления нет. SHA файла копии и SHA
исходного файла могут различаться из-за заголовка SQLite; размер и число строк
источника зафиксированы в момент snapshot transaction. Для созданного 28 октября
снимка в отдельной последующей read-only транзакции исходной БД также рассчитаны
row digests и schema: они совпали с копией, а `data_version` между началом и
концом проверки не изменился. Это два ограниченных среза, не полная история
между ними. Сохраняйте SHA manifest отдельно для проверки его подлинности.

Пример для **нового** output-пути:

```bash
.venv/bin/python scripts/snapshot_primary_forecast_memory.py \
  --source .local/state/primary-forecast-memory.sqlite \
  --output .local/state/forecast-snapshot-NEW
```

28 октября 06:02 МСК создан снимок фактического хранилища:
`.local/state/forecast-snapshot-work-20261028/actual-snapshot/`.
Размер 268435456 байт; в транзакции и копии 47979 прогнозов и 47722 версий
outcome, отсутствующих исходных forecast ID — 0; `integrity_check=ok`.
Snapshot SHA `efa54c5109d22db411f8908bb11b35a3dcacdaeaf5b4bcf231fef6f7c89c8e07`.
Снимок дополнительно воспроизведён в отдельный новый файл
`restore-drill/restored.sqlite`: hash исходной копии, count, оба логических
row-digest и полная проверка целостности совпали. Отчёт испытания —
`restore-drill/restore-evidence.json` в том же work-каталоге. Существующий
`PrimaryForecastMemory` отдельно прочитал первые 10 прогнозов и 10 последних
версий их результатов из snapshot и восстановленной копии с одинаковыми данными;
receipt `existing-reader-drill.json`. В 06:09 МСК source-schema и потоковые
row digests двух таблиц исходного файла в отдельной транзакции совпали с более
ранним snapshot; receipt `source-snapshot-comparison.json`.

25 тестов, включая 8 новых: проверены исходные bytes/все версии, отказ на
недостатке места/лишней схеме/повторном output, существующий reader, WAL с
незаписанными страницами и конкурентный writer во время snapshot transaction.
Это тест на синтетических БД; actual source при snapshot был в DELETE journal
mode, без отдельного контролируемого одновременного writer drill.

Инвентаризация текущих call sites и установленных unit 28 октября: executor
записывает forecast синхронным `PrimaryForecastMemory.record` при настроенном
`CRYPTOFORGE_PRIMARY_FORECAST_LEDGER`; outcome unit читает matured batch и пишет
через `record_outcome`, затем `ExecStartPost` запускает отчёт. Unit защищён своим
`primary-forecast-outcomes.lock`, но executor этот lock не использует; общий
межпроцессный lease на оба writer не обнаружен. Код feature-migration использует
отдельную базу study. Это статическая выборка call sites, не полная инвентаризация
всех запущенных процессов/отложенных действий; receipt `writer-reader-inventory.json`.
`matured_batch` штатно рассматривает только последние 36 часов, поэтому результаты,
пропущенные за более длинный outage, сами этим сборщиком не восстанавливаются;
нельзя выдавать поздно полученный endpoint за наблюдение в прошлом.

Эти копии лежат на том же разделе, поэтому не защищают от отказа диска. Исходная
база остаётся на лимите 256 MiB, запись новых прогнозов не восстановлена;
redirect writers/readers, атомарная миграция, независимый backup, ограниченная
retention, проверка concurrent processes и работа после restart остаются
открытыми. Диагностика не является real-buy label и не даёт допуск к торговле.
