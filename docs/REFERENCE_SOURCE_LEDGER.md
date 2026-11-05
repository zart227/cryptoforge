# W6b: обязательные reference sources и журнал прогнозов

Дата: 23 октября 2026, Europe/Moscow. Текущий статус и общий остаток:
[research checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).

Продолжение23октября: [общий reader W6b.3a](REFERENCE_SOURCE_READER.md) реализован
и actual source→price forecast→three-role frame проверен. Ниже сохранены scope и
receipts исходного W6b.1/W6b.2; его0actual forecasts не является текущим общим счётчиком.

Реализован отдельный исследовательский источник Bybit Spot. BTC/USDT и ETH/USDT
всегда входят в фиксированную корзину; динамический ranking не может их удалить.
Этот источник не пишет в основную локальную PostgreSQL/PostgREST БД и не меняет
установленный feeder. Автоматический периодический запуск пока не установлен.
Новый SQLite namespace нельзя использовать как продолжение старого W6a SQL
contract: venue natural IDs и PostgreSQL UUID имеют разные области идентичности.

## Приёмочные проверки

- [x] W6b.1: независимый от ranking сбор обязательных BTC/ETH, исходные HTTP
  bytes/status/time/query SHA, closed contiguous120 и явные failures.
- [x] W6b.2: immutable source versions/global first-seen внутри нового namespace,
  новые source-bound price forecasts и независимый offline replay реализованы.
- [x] Actual diagnostic GET и offline audit: 120BTC+120ETH, оба ready в момент
  наблюдения. Это один контрольный poll; continuous coverage им не доказано.
- [x] 61 новых +265 compatibility =326 разных tests passed /25.09s.
- [x] W6b.3a: shared source frame/closed reader и actual compatible price forecast
  реализованы отдельно; [runbook](REFERENCE_SOURCE_READER.md),374профильныхtests.
- [ ] W6b.3b: actual primary reference refresh/deployment/source linkage;
  новый collector не обновляет рабочую БД. Полный paired runner/delivery — W7.
- [ ] W7: полная shared opportunity/negative/skip/failure delivery, cursors,
  restarts и candidate/control/stress; это шире данного reference poll journal.
- [ ] W8: full-worker/host RSS, whole-tick/network/queue/disk/retention/capacity
  measurement и независимый review. Фиксированные caps не заменяют измерения.
- [ ] W9/R14: qualified candidate и новое future economic/paper study.

Реализация: `src/cryptoforge/reference_sources.py`,
`src/cryptoforge/reference_source_ledger.py`, `scripts/capture_reference_sources.py`.
Тесты: `tests/test_reference_source_ledger.py`. Прежние552 Python-файла, включая
замороженные W6a/W5 components, в этом этапе сохранены без изменений.

## Что сохраняется и проверяется

Каждый original GET имеет фиксированный origin `https://api.bybit.com`,
`/v5/market/kline`, явный `category=spot`, `interval=5`, `limit=120` и end последней
закрытой свечи. Формирующаяся свеча, разрыв, дубликат, неправильный символ/рынок,
NaN/Infinity, неверные OHLCV или server/query clocks блокируют использование.
HTTP-ответ сохраняется как исходные bytes в base64 с SHA; при превышении64KiB
сохраняется ограниченный префикс с failure, пригодный source не объявляется.
Никаких ключей, private API, redirect или fallback endpoint нет.

Natural source ID содержит provider/path/category/pair/interval/open time.
Version SHA относится к исходным7строковым полям candle. Первое observed time
каждой версии остаётся в immutable index при повторном чтении; revisions получают
отдельные версии. `known_at` консервативно означает завершение фактического чтения,
а не историческое время доступности всех120 архивных свечей. Старые imported
timestamps и прошлые closed trades новыми observations не восстанавливаются.

Перед запросами durable `poll_prepared` резервирует полный фиксированный список.
По каждой паре сохраняется response/invalid/unavailable outcome; завершение poll
возможно только после всех пар. Повтор в том же5m anchor возвращает прежний receipt
без GET и без обновления observed time. HTTP403/429 или venue10006/10429 вводят
cooldown минимум10минут. Оставшиеся пары получают explicit skip с
`request_performed=false` без сетевых запросов; replay проверяет причину skip.
После обрыва pending poll блокирует продолжение; скрытых
retries, позднего adoption или удаления неполной попытки нет.

Forecast поддерживает только заранее замороженный pure-python-logistic artifact
с closed bounded120/5m/3bar price target и известными fit/evaluation information
bounds. Artifact нельзя добавить в уже начавшийся журнал. Вероятность вычисляет
сам код из исходных120 свечей, принять готовый ретроспективный forecast нельзя.
Сохраняются также отрицательные price forecasts, exact features, artifact SHA,
pair/bar forecast ID и ссылки/SHA всех mandatory response windows/versions.
Повтор forecast не перезаписывает оригинал. BTC здесь обязательная проверка
доступности reference source; семь признаков модели вычисляются из целевой пары.
Новый cross-market признак этим не добавлен.

Любой failed/invalid/stale обязательный источник блокирует forecast. Возраст
считается и от observation, и от фактического закрытия последней свечи: оба≤600s.
Повторное чтение старой свечи не обнуляет её возраст. Forecast должен появиться
до своего target information end; его завершение ограничено5s. Backwards clocks
и runtime/source drift не дают завершить новый допустимый poll/forecast.

Offline audit проверяет внешний manifest/registration/database/head SHA,
hash chain, original raw responses, ordered mandatory polls/cooldown, source
versions/first-seen, features/probabilities/forecast IDs и immutable projections.
Rehashed missing response, ложная вероятность или изменённый first-seen выявляются
также семантическим replay, а не только несовпадением внешнего database SHA.
Аудит после конца окна допустим; новое наблюдение после конца окна запрещено.

## Границы ресурсов и восстановления

Один HTTP worker имеет socket timeout3s и принудительный parent deadline5s,
stdout≤128KiB; body≤64KiB. Fixed pairs≤20 включая BTC/ETH; poll≤75s.
Default ledger: events≤100000, versions≤50000, forecasts≤50000,
SQLite≤1GiB, event≤256KiB, свободный диск≥2048MiB плюс запас текущих events.
Floors не снижались. SQLite max_page_count, append-only triggers, exclusive lock,
atomic events/version/forecast transaction и streaming SHA ограничивают storage.
Offline scratch replay имеет database cap, wall budget60s и cleanup.

Полный worker RSS, длительное накопление, quota exhaustion, host crash recovery,
периодический scheduler и доставка трём ролям ещё не квалифицированы. После crash
не подбирать новый receipt по изменённой БД автоматически: сохранить namespace
и externally pinned receipts для разбора. Старый receipt после нового append
намеренно не разрешает открыть изменённую БД; нужен выданный новым append receipt.
Нельзя удалять lock/journal, ослаблять caps или переписывать старый manifest ради
продолжения. Новый запуск требует отдельного prospective namespace/contract.

## Команды

Из корня проекта, без `.env` и API keys. Output root должен быть новым;
receipts сохраняются **рядом, вне root**, который имеет фиксированный inventory.
Следующие пути примеры, не существующие accepted receipts для перезаписи.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/capture_reference_sources.py probe \
  --output .local/state/reference-probe-NEW \
  > .local/state/reference-probe-NEW.receipt.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/capture_reference_sources.py audit \
  --reference-file .local/state/reference-probe-NEW.receipt.json
```

Для настоящего будущего source study сначала выполнить `create --output NEWROOT
--start FUTURE_UTC --end END_UTC [--artifact-file FROZEN_ARTIFACT] [--pair SOL/USDT]`,
сохранить исходный receipt вне root **до start**, затем `poll --reference-file`
с последним receipt. `forecast --reference-file ... --pair ETH/USDT` допустим
только при заранее frozen compatible artifact и готовых sources. Новый receipt
после append сохранять отдельно, атомарно доставлять будущему coordinator и
проверять exact external pins. CLI не имеет `--as-of` и не меняет registry.
Эта документация не регистрирует study и не устанавливает сервис.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_reference_source_ledger.py tests/test_local_source_provenance.py \
  tests/test_backend.py tests/test_database_backend_cli.py \
  tests/test_paper_producer_v2.py tests/test_paper_wallet_v2.py \
  tests/test_paper_worker_v2.py tests/test_paper_replay_math_v2.py
```

## Фактические observations и receipts 23 октября

Read-only W6a SQL probe в07:08:07UTC вновь обнаружил stale BTC в основной БД:
последнее закрытие21октября23:10UTC, age115087.881843s (около32часов).
Cluster identifier и schema не изменились относительно accepted22октября.
ETH в основной БД сегодня отдельно не перечитывался. Installed feeder/services
в этом этапе не менялись; проблема рабочего источника остаётся открытой.

Final restricted-sandbox probe в07:51:29UTC сохранил два URLError,
0versions и оба unavailable. Этот отрицательный receipt сохранён отдельно.
После разрешённого read-only network access новый diagnostic namespace получил
оба HTTP200: BTC known_at07:51:32.561587UTC, ETH07:51:32.970180UTC.
Оба latest close23октября07:50UTC (10:50МСК), age92.561/92.970s,240versions,
4events,0forecasts. Offline CLI replay: source_trace_integrity_pass=true,
original_source_forecast_linkage_pass=false, scope=diagnostic.

Evidence root: `.local/state/reference-sources-work-20261023/`:

- `current-btc-probe/`, `current-source-drift.json` — actual SQL observation;
- `accepted-sandbox-reference-receipt.json` — final sandbox failure попытка;
- `accepted-public-reference-receipt.json`, `accepted-public-reference-audit.json`
  — public GET и offline replay;
- `accepted-final-sources/`, `accepted-final-source-pins.json` — final runtime/test copies;
- `pytest-cooldown-final.log`, `verification.json`, `verify.py` — проверки и SHA.

Ранние actual-reference/public receipts07:40UTC и их исходники в `accepted-sources/`
сохранены как pre-cooldown development evidence. После исправления runtime они
не объявляются receipts final collector и не усыновлены новым namespace.

Флаги source_poll_completeness/historical_known_at/full_worker_or_host/paper/
economic/live/real_executed_buys остаются false. Actual forecast выбранной модели,
полнота будущих polls и денежная полезность здесь не подтверждены. Нет новых
orders, обучения/публикации модели, изменения риска, primary DB или сервисов.

Контракт HTTP проверен по [Bybit Kline](https://bybit-exchange.github.io/docs/v5/market/kline)
и [Bybit rate limits](https://bybit-exchange.github.io/docs/v5/rate-limit).
