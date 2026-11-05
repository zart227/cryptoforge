# W6b.3a: общий reader исходных свечей и ценовых прогнозов

Дата: 23 октября 2026. [Текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[источник W6b.1/W6b.2](REFERENCE_SOURCE_LEDGER.md).

Продолжение23октября: [W7a retained source delivery](REFERENCE_DELIVERY.md)
сохраняет original event prefixes и читает их после source append отдельным
DeliveredReferenceReader. Старый ReferenceMarketReader ниже остаётся строгим
к physical source DB pin; его contract не переписывался. Worker integration
и cash policies ещё W7b, полный W7 не закрыт.

Добавлен opt-in `ReferenceMarketReader`: candidate/control/stress читают один
неизменяемый frame с одним внешним SHA. Он предоставляет closed bounded120
`CandleRow`, признаки с фиксированной Decimal precision28 и исходные price
forecasts. Такой прогноз не содержит `would_enter`. Reader не подменяет
cash-strategy admission вероятностью роста и не запускает worker или заявки.

## Выполнено и осталось

- [x] W6b.3a: отдельный pre-start reader contract для нового пустого prospective
  source namespace; поздняя регистрация и adoption diagnostic frame отвергаются.
- [x] Общий source frame, explicit external source/reader/frame/completion SHA,
  оригинальные HTTP bytes и времена, global first-seen/version provenance.
- [x] Совместимый closed5m/bounded120 интерфейс, признаки с pinned arithmetic,
  одинаковые inputs для трёх объявленных ролей; stale/failed обязательные sources
  блокируют чтение свечей. Повторное чтение не освежает timestamps.
- [x] Сохраняются исходные отрицательные/положительные price forecasts и явный
  `usable_price_input_now`; истёкший прогноз не исчезает из evidence и не
  преобразуется в разрешение входа. Offline source replay выявляет подмену.
- [x] Компактный inference envelope с exact исходными числовыми параметрами,
  исходным artifact SHA, сохранёнными raw original bytes и отдельным audit.
  Неизвестный/несогласованный model contract не исправляется предположением.
- [x] Actual source→forecast→frame→three-role reader diagnostic проверен;
  48new+326compatibility=374 разных tests passed /38.85s. Общий suite не запускался.
- [ ] W6b.3b/R4: выбранный рабочий feeder и reference refresh основной локальной
  БД, actual deployment/health, REST→instance/source linkage. Новый reader не
  обновляет PostgreSQL rows и не установлен как периодический сервис.
- [ ] W7: durable shared polling/cursors/acknowledgements, retained source history
  и completeness всех opportunities/negative/skip/failure outcomes, delivery в
  настоящие candidate/control/stress workers и отдельные cash-entry policies.
- [ ] W8/W9: full-worker capacity/recovery/review, qualified candidate и новое
  future economic/paper study. Общие W6/W5 остаются открытыми.

Код: `src/cryptoforge/reference_source_reader.py`, CLI
`scripts/read_reference_sources.py`, тесты `tests/test_reference_source_reader.py`.
Прежние556 Python-файлов сохранены без изменений. LLM — другой агент.

## Контракт и использование

Сначала W6b source должен создать новый пустой **prospective** ledger до его
start. Затем `register` фиксирует reader/runtime, source initial reference,
manifest/registration, пары, artifact SHA и то же source window. Регистрация
не запускает study. После start source делает оригинальные `poll`/`forecast`,
а `capture` берёт **последний** выданный source receipt и выдаёт новый immutable
frame. Reader contract передаётся явно; при его отсутствии frame diagnostic.
Output roots всегда новые, receipts хранятся вне этих roots.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/read_reference_sources.py register \
  --source-reference-file .local/state/NEW-source-registration.json \
  --output .local/state/NEW-reader-contract \
  > .local/state/NEW-reader-registration.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/read_reference_sources.py capture \
  --source-reference-file .local/state/NEW-latest-source-receipt.json \
  --reader-reference-file .local/state/NEW-reader-registration.json \
  --output .local/state/NEW-reader-frame \
  > .local/state/NEW-reader-frame-receipt.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/read_reference_sources.py audit \
  --frame-reference-file .local/state/NEW-reader-frame-receipt.json \
  --reader-reference-file .local/state/NEW-reader-registration.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/read_reference_sources.py inspect \
  --frame-reference-file .local/state/NEW-reader-frame-receipt.json \
  --reader-reference-file .local/state/NEW-reader-registration.json \
  --role candidate --pair AVAX/USDT
```

Команды не имеют `--as-of`, endpoint overrides, keys или private APIs. `inspect`
использует текущее фактическое время; старый frame не становится свежим от чтения.
Offline audit использует сохранённое время только для воспроизведения исходных
inputs и не выдаёт новый допуск. Нет automatic source polling или recovery.

В Python `ReferenceMarketReader.open(frame_reference, role=..., reader_reference=...)`
предоставляет `read_candles(pair, timeframe='5m', limit=120)`, `features(pair)`,
`original_forecasts()` и `status()`. Все дополнительные пары обязаны быть явно
включены в исходный fixed source contract. Features не зависят от Decimal context
вызывающего кода; timestamps и версии не переписываются. `source_status` относится
к оригинальному poll, текущая свежесть отражена `closed_candles_ready`.

Source ledger полностью проверяется перед capture и перед первым открытием frame.
Оригинальные forecasts берутся только после последнего complete poll; предыдущие
bars не выдаются как новые. First-seen берётся из audited global version index,
а `cache_observed_at` свечи остаётся временем оригинального HTTP observation.
Source SHA/head/query/rows/first-seen/forecast сверяются в offline replay.

Уже открытый reader сохраняет прежний frame после нового poll источника до
истечения его freshness. **Новый consumer/offline audit старого frame требует
именно прежний pinned source DB.** Если source DB уже дописана, old DB SHA не
подменяется новым. Retention/versioned source snapshots и постоянная передача
последовательности frames ещё относятся к W7; это текущая интеграционная граница.
В этой реализации нет durable role cursor/ack или доказательства полноты доставки.

## Компактный inference artifact

Сохранённый migration-v3 кандидат `041b` имеет оригинальный artifact304141bytes.
64KiB source artifact cap сохранён. `prepare-artifact` копирует точные веса,
bias/means/stds, feature names, pair scope, model version/trained_at и известные
input/fit/evaluation/target contracts в отдельный inference envelope.
Диагностика/search traces остаются в **исходном raw artifact**, который сохраняется
рядом с envelope. Никакой fit, rounding параметров, threshold selection или
публикации нет. Новый envelope имеет собственный SHA и не является прежним
artifact identity или новой active model.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/read_reference_sources.py prepare-artifact \
  --artifact-file ORIGINAL-model.json --output .local/state/NEW-inference \
  > .local/state/NEW-inference-receipt.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/read_reference_sources.py audit-artifact \
  --artifact-reference-file .local/state/NEW-inference-receipt.json
```

Исходник ограничен1MiB; envelope≤64KiB, source frame≤4MiB, capture≤75s и
свободный диск≥2048MiB+3frame budgets. Source ledger transport/SQLite floors не
снижаются. Неполная/поздняя регистрация или capture не имеют valid ready/completion
pin и не усыновляются; caller не должен удалять partial evidence для retry.
Full-worker RSS, throughput трёх workers, durable delivery и host recovery пока
не измерены. Несовпадение frozen runtime требует нового процесса/namespace.

## Actual diagnostic 23 октября

Из **protocol**, без чтения новых outcomes, взят exact artifact migration-v3
`pure-python-logistic-candle-v1-20261011-041b283bc8`:
original SHA `01d88cd66354268a92adb9663a428e27b720c9e745d94613e4f6b9f8a0517a20`.
Он не подменяет candidatea252 или legacy active09b. Original protocol/weights не
менялись. Declared diagnostic pair AVAX/USDT входит в исходные trained pairs;
BTC/ETH добавлены как mandatory references. Проверки их доходности не было.

- Original304141bytes → inference2906bytes; parameter identity audit=true.
  Envelope SHA `2a7afd1e362d337b6dcef16ba9fee2cce15f98ab14e36311224ea2292fb000a2`.
- Public GET завершён23октября08:19:49UTC:120AVAX+120BTC+120ETH closed candles,
  все ready в момент наблюдения, latest close08:15UTC. Работающая primary DB
  не читалась и не менялась; прежнее SQL наблюдение07:08UTC показало stale BTC≈32h.
- Original AVAX forecast создан08:20:19.991167UTC **до target08:30UTC**;
  long probability0.14484000970793767. Это вероятность price label, не доход,
  не `would_enter` и не результат исполнения. Outcome этого прогноза не читался.
- Source audit:360versions/6events/1forecast, original source linkage=true.
  Frame `09e6a689abb3352b3cf82cc93e66e8be522dd3baa665955572c41f9d98a22ed7`:
  frame integrity=true; три роли прочитали один и тот же forecast и120AVAX inputs.
- Вероятность дополнительно рассчитана из **оригинального304KiB artifact** на
  тех же features: exact Python float equality. Ограничение trained pair scope
  сохранено; прогноз для BTC/ETH этим artifact не создавался.
- В08:27:32UTC повторное actual чтение старого frame отвергнуто как stale:
  last close08:15UTC уже старше600s. Прогноз сохранён с прежним ID, usable=false;
  новых GET и чтения outcome не было. Receipt `actual-stale-read-rejection.json`.

Evidence: `.local/state/reference-reader-work-20261023/`:
`model-source-selection.json`, `actual-inference-{receipt,audit}.json`,
`actual-forecast-receipt.json`, `actual-source-audit.json`,
`actual-frame-{receipt,audit}.json`, `actual-three-role-reader.json`,
`accepted-sources/`, `accepted-source-pins.json`, `pytest-acceptance.log`,
`verification.json`, `verify.py`.

Все source_poll_completeness/historical_known_at/full_worker_or_host/paper/
economic/live/real_executed_buys gates=false. Это diagnostic, не зарегистрированное
economic study. Cash decisions/worker execution/delivery completeness, текущий
рабочий reference refresh, улучшение дохода и общий W6 не подтверждены.
