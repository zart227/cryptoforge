# CryptoForge - дополнительный план исследований по видео VP Crypto

> **Спецификация, не статус.** С 5 ноября 2026 прогресс VP отмечается только в
> [CURRENT_PLAN.md](CURRENT_PLAN.md). `INT-03` ниже указывает путь
> `docs/plans/CF-VP-2026-10-17.md`; такого файла нет, текст спецификации — этот
> документ. VP-00…VP-09 не выполнены.

**Идентификатор:** `CF-VP-2026-10-17`  
**Версия:** `1.1` (цель интеграции уточнена пользователем)  
**Дата подготовки:** 18.10.2026  
**Источник гипотез:** пользовательская расшифровка выступления VP Crypto от 17.10.2026 (`vpcrypto 2026-10-17-15-57-27 1792227447317 (1).txt`) и предоставленное видео.  
**Репозиторий:** https://github.com/zart227/cryptoforge  
**Целевой активный план действующего агента:** `/home/arthur/Projects/personal/CryptoForge/docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md`. Именно в этот файл необходимо встроить новые чеклисты. Корневой `IMPLEMENTATION_PLAN.md` - дополнительный контекст проекта, но **не** целевой файл замены или место для новой полной копии плана.  
**Назначение:** дополнение к действующему плану, **не его замена**. Этот файл содержит только план и чеклисты, без промпта.

> **Правило выполнения.** Начинать с интеграции данного workstream в существующий master-план. Все пункты нового плана исходно `[ ]`. Зачёт уже выполненной функции допустим только после сравнения с актуальным кодом, проверки тестов и приложенного evidence. Запрещено автоматически присваивать выполнено на основании README или старого отчёта.

Актуальная сводка 22 октября — [текущий checklist master-плана](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
Общие producer/archive/capture/replay v2 уже реализованы; это reuse для будущих
VP-работ, а не завершение VP-00…VP-09 или семи стратегий. Их статусы ниже
остаются открытыми. LLM-план в эту очередь не входит.

### Состояние интеграции на18октября2026

Спецификация включена в [действующий master](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#cf-vp-2026-10-17---video-derived-strategy-research)
как отдельное направление VP. [Карта интеграции](video_research/INTEGRATION_MAP.md)
фиксирует evidence и зависимости. INT-02…08 выполнены локально; INT-01 остаётся
частичным (повторно просмотрены активные разделы/контракты, не заявлена полная
повторная сверка всех исторических документов), INT-09 требует отдельного
reviewer, INT-10 — Git-фиксации. VP-00…VP-09 не завершены. LLM-направление
принадлежит другому агенту и сюда не интегрируется.

Raw SHA256 до status edits: `b13852096987cb877a2568a33e5e2fc299a31beb6a2fae507fe73982440adc1b`;
base commit `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`, ветка `main`, dirty checkout.
Оригинал и checkpoint: `.local/state/vp-plan-integration-20261018/`.
Видео/расшифровка, названные в источниках, отдельно не найдены; их содержимое
не проверено, экономические результаты отсутствуют.

## 0. Цель и границы

Создать в CryptoForge воспроизводимые исследовательские гипотезы, извлечённые из видео: покупки на коррекции к Fib/поддержке, POC, подтверждённый пробой трендовой, консолидация/реаккумуляция, price sweep, свечное подтверждение, влияние режима BTC и отмена недействительных сценариев. Превратить эти наблюдения в causal features -> сигналы -> backtests -> forward paper/shadow -> при достаточности доказательств исследовательские ML-кандидаты.

**Видео не содержит обученную модель, готовый алгоритм или проверенный журнал прибыльных сделок.** В нём трейдер обсуждает сценарии и называет некоторые уровни, которые в транскрипции могут быть неверными. Это исходные **гипотезы**, а не сигналы для немедленной торговли.

Границы:
- Только Bybit **Spot, long-only**. Фьючерсы, маржа, плечо, заёмные шорты и золото - вне этой работы.
- Только исследовательские компоненты, офлайн-бэктест, явно изолированные shadow/paper; **никаких новых реальных заявок**.
- Не изменять действующие `live`/`gate`/`shadow` настройки, API-ключи, разрешения, таймеры, лимиты риска, `model.active`, оркестрацию исполнения и существующие стратегии, которые уже управляют позициями.
- Предварительно регистрировать ограничения исследования. Никогда не переписывать старые frozen protocols, study manifests, attempts, исходные snapshots и результаты.
- При несовпадении документов и runtime доверять фактическому read-only аудиту, сообщать о расхождениях.
- Не нарушать работающие на VPS VPN/network и остальные службы.

### Основание из речи и границы интерпретации

| Гипотеза | Что утверждалось в видео | Что мы формализуем как *свою исследовательскую интерпретацию* |
|---|---|---|
| Fib/pullback | Коррекция к 0.382/0.5 и покупке у уровней | causal swing anchors, вход/ожидание и параметры риска |
| POC | Совпадение уровня с «POC базы» | честное `approx_ohlcv_poc` либо отдельный trade-derived POC, если есть достаточные исторические сделки |
| Trendline | Пробой с закреплением полноценной **дневной** свечи; в одном примере стоп около 3% | объективные линии из подтверждённых пивотов, критерий свечи, отдельное исследование 1D; 3% не универсальный стоп |
| Base/sweep | Диапазон, снятие крайних уровней и закрепление выше базы | wick-sweep только **ценовой proxy**; не заявлять факт ликвидаций/ордеров |
| BTC context | Рост BTC может способствовать росту альтов | paired тест BTC-filter включён/выключен, не предполагать причинность |
| Hammer | Бычий молот у поддержки | отдельный контролируемый свечной фильтр |
| Invalidation | Бычий клин не отработал, возможен слом и нисходящий канал | отмена сетапа, TTL лимиток, no-chase фильтр |

Некоторые названия/цены распознаны неоднозначно (`Stark`, `Тао`, `NIR`, `Arbitrub`, `YUNI`, `0.0.58`, `2.42`, «790 уровень»); **запрещено автоматически превращать их в тикеры/цены ордеров**. Рекламные заявления о +166%/+500% и многолетней доходности не являются нашим evidence.

> **Важный контекст текущей сессии:** пользователь указал точный путь к файлу, над которым Codex уже работает. Прежде чем редактировать его, агент должен увидеть свои незавершённые изменения и актуальный in-memory task board. Запрещено заменять этот файл шаблоном, выводом из GitHub или старой копией, а также помечать старые шаги повторно. Если файл пока существует только локально, это нормально: читать и изменять локальную рабочую версию, а не пытаться восстановить его из удалённого `main`.

## 1. Протокол интеграции с существующим планом (БЛОКИРУЮЩИЙ ШАГ)

Выполняется **перед** разработкой новых стратегий. Текущий `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` сохраняет роль рабочего источника прогресса для уже запущенного агента. Если репозиторий также использует корневой `IMPLEMENTATION_PLAN.md`, следует сохранить его собственную роль и иерархию; не подменять им указанный файл.

- [ ] `INT-01` Сначала полностью прочитать **фактически редактируемый агентом** `/home/arthur/Projects/personal/CryptoForge/docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` и зафиксировать его текущий этап, потом `IMPLEMENTATION_PLAN.md` (если существует), `README.md`, `FINAL_AUDIT.md`, `docs/FREQAI.md`, актуальное дерево кода, git status/HEAD и незавершённую работу агента. Если активный план иной, установить и задокументировать иерархию и источник истины.
- [x] `INT-02` Создать карту пересечений: existing tasks / sections -> `CF-VP` задачи, классификация `ALREADY_VERIFIED`, `PARTIALLY_IMPLEMENTED`, `NEW`, `BLOCKED`, `CONFLICT`. Не дублировать бизнес-логику и одинаковые чеклисты.
- [x] `INT-03` Сохранить этот файл в репозитории, рекомендуемый путь `docs/plans/CF-VP-2026-10-17.md`; путь можно согласовать с фактическими соглашениями проекта. Зафиксировать SHA исходного файла и commit, с которого произведена интеграция.
- [x] `INT-04` Вставить в **`/home/arthur/Projects/personal/CryptoForge/docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md`** раздел **`CF-VP-2026-10-17 - Video-derived Strategy Research`** с целью, областью, ссылкой на этот файл, **статусом**, блокирующими условиями и небольшими отслеживаемыми чеклистами фаз `VP-00` ... `VP-09`.
- [x] `INT-05` Добавить аккуратные ссылки на workstream в существующие релевантные разделы **этого же `PROFITABLE_STRATEGY_RESEARCH_PLAN.md`** (historical data, market regimes, strategy lab, risk, backtesting, ML, audits) **без перенумерации прежних фаз**, удаления строк и перезаписи `[x]`/`[ ]`.
- [x] `INT-06` Если в `PROFITABLE_STRATEGY_RESEARCH_PLAN.md` аналогичный workstream уже существует, **обновить его на месте**, сохранить историю выполнения; сделать idempotent merge по `CF-VP-2026-10-17`, не создавать дубль при повторном запуске промпта.
- [x] `INT-07` Указать блокеры от прежних работ по `PROFITABLE_STRATEGY_RESEARCH_PLAN.md` и приоритет; новый workstream - дополнительный, не отменяет текущую задачу и не разрешает обходить уже установленные релизные и risk gates.
- [x] `INT-08` Записать integration decision в существующий Decision Log/changelog и отдельный краткий `docs/video_research/INTEGRATION_MAP.md`: что добавлено, что переиспользуется, что отложено, какие исходные стадии продолжаются без изменений.
- [ ] `INT-09` Проверить `git diff` и ссылочную целостность: `PROFITABLE_STRATEGY_RESEARCH_PLAN.md` остался главным рабочим планом текущего агента, все старые пункты на месте, все новые ID уникальны; отдельный reviewer проверил diff. Не отмечать как завершённые фазы реализации, выполнена только интеграция.
- [ ] `INT-10` Логически зафиксировать изменение текущего рабочего плана и исследовательской документации в ветке/коммите/PR по обычному workflow проекта, **не** переписывая чужие незакоммиченные изменения. Сверить, что агент возобновляет работу по расширенному master-плану с прежней точки.

**Definition of Done:** единый действующий `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` с видимой новой веткой `CF-VP`, отдельный подробный checklist файл, таблица соответствий и review diff. При конфликтах в незакоммиченном файле сначала безопасное согласование изменений, без `git reset --hard`/force push.

## 2. Зависимости, защита от ложного прогресса

При интеграции проверить наличие и контракты компонентов, которые уже упоминались в проекте: `strategy_extensions.py` (support-bounce/compression-breakout), `closed_timeframes.py`, `causal_features.py`, `entry_risk.py`, `exit_rules.py`, `paper_wallet.py`, `research_evidence.py`, `walk_forward.py`, торговый журнал, experiment ledger, Bybit archive и Supabase. Это **кандидаты на повторное использование**, не предположение, что все функции работают.

По исторической документации `docs/FREQAI.md` был snapshot 07.10.2026 с executor `live`/`gate`, а сентябрьский `FINAL_AUDIT.md` описывал dry-run. Статус **сегодня** не подтверждён. До любой работы с реальным окружением запрещены write-actions и необоснованные запуски.

- [ ] Проверить соответствие API/инвариантов текущему git HEAD и незакоммиченным изменениям.
- [ ] Разделить то, что выполняется на локальной машине разработчика, на ресурсоёмкие процессы, которые нельзя запускать на слабом рабочем VPS.
- [ ] Описать запрет на изменение боевого исполнения в тестах и отдельным security test.
- [ ] Завести три статуса для исследований: `REJECTED`, `INSUFFICIENT_EVIDENCE`, `RESEARCH_CANDIDATE`. Статуса `LIVE_APPROVED` в этой ветке **нет**.

## 3. Реестр стратегических гипотез (каждая - отдельное исследование)

### `CF-VP-01` - Fibonacci pullback + prior support (P1)

- [ ] Определить swing low/high с причинной задержкой подтверждения; `known_at` ставить при подтверждении пивота, не на экстремальной свече задним числом.
- [ ] Вычислить зоны 0.382 и 0.5 для **восходящего** swing: `high - ratio*(high-low)`; ограничить их ранее известной поддержкой.
- [ ] Сравнить один лимитный вход и две лимитные ступени с **одинаковым** совокупным риском и капиталом; использовать причинный TTL и отмену.
- [ ] Зафиксировать stop/invalidation по предшествующему swing или независимому risk engine; stop вне контролируемых диапазонов = отказ от входа.
- [ ] Сравнить с существующим `support-bounce`, простым pullback и отсутствием торговли.
- [ ] Unit tests: delayed pivot, неполный swing, отменённый/неисполненный лимит, две частичные fill, один risk budget.

### `CF-VP-02` - Confirmed trendline breakout (P1)

- [ ] Построить детерминированную линию на базе >=2 **подтверждённых** пивотов, сохранять `line_version`, опоры и timestamps их доступности.
- [ ] Зафиксировать признак пробоя и тела свечи **до** прогона; опорный вариант = закрывшаяся свеча **1D**, альтернативные 1h/15m - отдельные гипотезы, не «цитаты автора».
- [ ] Не исполнять до появления подтверждённого close; моделировать next tradable quote/open и execution latency.
- [ ] Сравнить структурный/ATR stop; упомянутые автором ~3% нельзя использовать как универсальный дефолт.
- [ ] Target - ранее подтверждённый swing high или фиксированный R/R; сформулировать invalidation при возврате в диапазон.
- [ ] Сравнить с существующим `compression-breakout` и простым momentum baseline.
- [ ] Тестировать pivot changes, дневные границы UTC, ложные пробои, retrace/retest без future peeking.

### `CF-VP-03` - Prior support + POC (P2)

- [ ] Определить, действительно ли доступны исторические **trade prints** нужной полноты и времени; только тогда использовать точный trade-derived POC.
- [ ] При наличии лишь OHLCV создать и явно назвать **`approx_ohlcv_poc`**, задокументировать цену-бин, метод распределения свечного объёма, доступность данных и ошибку приближения.
- [ ] Считать профиль только внутри заранее известной базы, не выбирать диапазон по будущей успешной сделке.
- [ ] Сравнить `support_only` против `support_plus_approx_poc` на одинаковых сделках/кошельке.
- [ ] Проверить тестами shifted bars, gaps, пустой профиль, low volume, разные bin sizes и версионирование feature.

### `CF-VP-04` - Range/base breakout after wick sweep (P1)

- [ ] Определить ширину диапазона, число касаний, окна; границы фиксировать на известных закрытых свечах (`known_at`).
- [ ] Формализовать `sweep_low` как wick ниже прежней границы + close обратно в базу; это **price action proxy**, не фактическое снятие заявок/ликвидаций.
- [ ] Требовать причинный breakout close выше ранее известной верхней границы и документировать TTL.
- [ ] Stop не ниже неизвестного будущего low; использовать ближайший *известный* локальный минимум и hard risk gate.
- [ ] Сравнить с базовым range-breakout без sweep и no-trade; проверить ложные проколы и пробой вниз.

### `CF-VP-05` - BTC context for alt-long (P1)

- [ ] Получать независимый Bybit Spot BTC regime только из свечей, **закрывшихся к моменту решения альта**.
- [ ] Сравнить тот же поток исходных alt-сигналов без BTC-gate и с BTC-gate, одинаковые capital/stake/fees/pairs/periods.
- [ ] Учитывать пропущенные прибыльные сделки, opportunity cost и сокращение экспозиции, а не только число предотвращённых убытков.
- [ ] Не заявлять причинность «BTC вырос -> альты вырастут» без экономической проверки.
- [ ] Проверить синхронизацию свечей BTC/alt, пропуски BTC и midnight crossover.

### `CF-VP-06` - Bullish hammer at established support (P2)

- [ ] Формально и заранее определить геометрию тела и хвостов закрытой свечи, направление предшествующего движения и доступность support.
- [ ] Сравнить поддержку без свечного фильтра против поддержку+hammer; допускается результат «недостаточно сделок».
- [ ] Проверить одинаковое поведение на равных OHLCV, doji/нулевых range и gaps.

### `CF-VP-07` - Pattern invalidation / no-chase (P1)

- [ ] Формализовать `pattern_invalidated`, `range_reentry`, `trendline_failed`, `pending_limit_expired`; сохранять причину и `known_at`.
- [ ] Определить метрику перегрева после импульса (например, ATR-normalized distance или trailing return), не превращая +166%/+500% из видео в правила.
- [ ] Проверить как фильтр влияет на **net portfolio** и количество сделок; снижение минусов при нулевой выручке не считать торговым преимуществом.
- [ ] Проверить stale/failed BTC regime, разрыв данных и отмену лимитов без нового входа.

## 4. План исполнения с этапами, чеклистами и условиями завершения

### `VP-00` - Baseline/read-only аудит (после `INT`)

- [ ] Сохранить commit/working-tree состояние, текущие master sections, плановые блокеры, контракт исполнения и измеренные ограничения RAM/CPU/disk.
- [ ] Отметить расхождения между октябрьскими docs, сентябрьским аудитом и действующим runtime; никаких live write/stop/start.
- [ ] Собрать reuse/extend/new map + dependency diagram и оценку рисков/совместимости.
- [ ] Согласовать неймспейс `docs/video_research/` или фактическую структуру проекта, чтобы не ломать существующие layout/CI.
- [ ] Подготовить read-only audit report и оформить blockers.

**Готово, если:** документированы фактические контракты, конфликтов с работающей торговлей нет, все неопределённости помечены.

### `VP-01` - Causal data contract / preregistration

- [ ] Уточнить historical Bybit Spot universe, listing/delisting и ограничения исторических minQty/tickSize (UNKNOWN не выдавать за known).
- [ ] Разделить closed 5m, 15m, 1h, 1D данные и `bar_end`, `known_at`, `computed_at`, `feature_version`, `source_sha`; исключить forming candles.
- [ ] Проверить причинность anchor/pivot/line/POC/BTC features, reject missing/future/gapped/revised data.
- [ ] Создать **новый** immutable study protocol с фиксированными family ID, dataset+source hashes, UTC windows, coins, fees+spread+slippage scenarios, split/purge/embargo, max search budget, trade-count threshold, drawdown, evaluation rules.
- [ ] Записать preregistration в существующий immutable ledger **до оценки outcomes**; если целевое будущее окно уже просмотрено - пометить contaminated и назначить новое prospective window, а не «очистить» его словами.
- [ ] Ограничить ресурсы; не запускать тяжёлые модели/бэктесты на рабочем VPS при недостатке CPU/RAM.

**Готово, если:** sample/feature causality проверена тестами, протокол зарегистрирован и source bound.

### `VP-02` - Reusable primitives и risk-safe signal API

- [ ] Реализовать/переиспользовать причинный swing/trendline/base detector и закрытые multitimeframe slices.
- [ ] Реализовать POC proxy только с явным префиксом `approx_` и отдельным quality flag.
- [ ] Определить typed `ResearchSignal` (pair, side=long, as_of, known_at, strategy/version, inputs hashes, stop proposal, entry kind, expiry, invalidation reason, confidence *если оправдана*).
- [ ] Сделать отдельные pure/research-only функции без вызовов приватных Bybit endpoints и без доступа к действующему registry/orders.
- [ ] Unit и property-based tests: boundary timestamps, pivot delay, repeated input -> same signal, gaps, null, flat markets, changes in source hash.

**Готово, если:** признаки воспроизводимы, нет будущих данных и есть явный fail-closed контракт.

### `VP-03` - Реализация набора гипотез

- [ ] Создать минимальные исследования `CF-VP-01`, `CF-VP-02`, `CF-VP-04`, `CF-VP-05`, `CF-VP-07`; только заранее заданные варианты.
- [ ] Затем `CF-VP-03` и `CF-VP-06`, если качество исходных данных позволяет; иначе `BLOCKED` с измеренным ограничением.
- [ ] Встроить новые модули в Strategy Lab **только как research candidates**, не в production dispatcher.
- [ ] Каждый сигнал сериализует as-of context и причину signal/no-signal; для отказов тоже сохранять accounting reasons.
- [ ] Провести unit/integration/security проверки каждого ID и определить independent baseline.

**Готово, если:** каждую гипотезу можно независимо повторно воспроизвести по одинаковому input.

### `VP-04` - Execution simulation / risk testing

- [ ] Подключить единую модель shared-wallet из имеющегося проекта; не выдавать отдельные перекрывающиеся сигналы за исполнимые сделки.
- [ ] Моделировать капитал, simultaneous positions, 1/2 лимитки, TTL/cancel, partial/non-fill, min order/precision, комиссии, spread, slippage, gap и ambiguity OHLC path консервативно.
- [ ] При неизвестной позиции в очереди лимитного ордера не гарантировать fill лишь по касанию low/high; передать uncertainty/status `not_proven_filled`.
- [ ] Сохранять в каждой сделке entry/exit/stop, fees, realized costs, rejection, slippage assumptions и trace provenance.
- [ ] Запретить bypass существующего hard-risk engine; суммарный риск двух лимиток не выше одного утверждённого budget.
- [ ] Сравнить ordinary и стрессовые издержки, результаты с тем же capital и exposure.

**Готово, если:** тесты охватывают неисполненные лимитки, конфликт капитала, stop/target ambiguity, разрывы и ресурсные границы.

### `VP-05` - Registered backtests / economic screening

- [ ] Запустить только preregistered ограниченную сетку, в первую очередь одиночные правила, без подгонки после увиденных результатов.
- [ ] Контрольные группы: текущий champion/baseline при доступности; простейшие support/breakout и no-trade. Сопоставимая история, капитал, ликвидность и risk.
- [ ] Проводить time-ordered train/validation, walk-forward с purge; sealed independent future не раскрывать ради parameter selection.
- [ ] Сохранить все попытки, включая нулевые, отрицательные и незавершённые, immutable source/config/result SHA.
- [ ] Отчитаться по net PnL, expectancy, drawdown, PF, count, fill rate, risk, turnover, exposure, by pairs/months/regimes, fee stress и uncertainty по календарным блокам.
- [ ] Decision только `REJECTED`, `INSUFFICIENT_EVIDENCE`, `RESEARCH_CANDIDATE`. Не путать экономический passing с independent/live admission.

**Готово, если:** воспроизводимые результаты с доказанной provenance и сравнениями существуют; «сигнал работает» без экономической проверки недопустимо.

### `VP-06` - Forward shadow / isolated paper

- [ ] Для прошедших исследовательский отсев заранее заморозить future paper protocol, дату старта, horizon, KPI и termination criteria **до наблюдения результатов**.
- [ ] Развернуть/переиспользовать изолированный paper wallet namespace без ключей для реальных ордеров; изменения существующих trade/ML gates запрещены.
- [ ] Логировать полный поток сигналов (включая rejected/missed) и event timestamps, фактические snapshots и прогнозы до раскрытия outcome.
- [ ] Проверить, что paper fills - моделируемые, а factual live outcomes и hypothetical signal labels не смешаны.
- [ ] Сравнить paired control/challenger по одинаковым рыночным возможностям и общему капиталу с учётом расходов.
- [ ] Если ресурсные или доказательные preconditions не проходят - оставить `BLOCKED/INSUFFICIENT_EVIDENCE`, не активировать worker таймер без проверки.

**Готово, если:** candidate наблюдается только в shadow/paper и performance нельзя менять постфактум.

### `VP-07` - ML как вторичный эксперимент (условный)

- [ ] Отдельно зафиксировать: хватает ли разных дней, пар и зрелых неперекрывающихся меток; если нет - **отложить обучение**.
- [ ] Target - net return/успех исполненной либо корректно симулированной Spot-long сделки с допустимой label-availability, не будущая цена как замена PnL; задокументировать различие observed/simulated.
- [ ] Обучить simple baseline (логистическая регрессия/малое дерево), но только на train; tuning на validation, untouched test и walk-forward с embargo.
- [ ] Сравнить с rule-only, no-trade и действующим champion в paired shared-wallet; исследовать calibration, profit after costs и stability, а не только accuracy/Brier.
- [ ] Проверить изменения при cost stress, regime shifts, empty trades, label leakage, concentration по pair/day, concept drift.
- [ ] Любая модель имеет `research_only=true`/`live_eligible=false`; запись в `model.active` и изменение live threshold запрещены.

**Готово, если:** либо обоснованно зафиксировано `NOT_READY`, либо есть независимые экономические доказательства кандидата **без** изменения боевого потока.

### `VP-08` - QA, security, resource and compatibility audit

- [ ] Тест no-lookahead по synthetic future append: сигнал в `t` не меняется после добавления свечей `>t`.
- [ ] Тест closed-only 1D/1h/15m/5m и знания BTC state `known_at<=signal_at`.
- [ ] Тест invariant: реальная Bybit торговля/withdrawal/derivatives не вызывается исследовательским кодом; нет `model.active`, изменение live gates или risk config.
- [ ] Тест source integrity/replay/ledger uniqueness/idempotency и repeated integration не создаёт дубликатов master-плана.
- [ ] Тест изменённых/пропущенных исторических данных и исторически недоступных instrument rules.
- [ ] Прогнать доступные тесты в отдельной среде, измерить RAM/CPU/disk и проверить, что исследование не лишает приоритета runtime.
- [ ] Проверить, что секреты/ключи/живые заявки не попадают в outputs/logs/Git.

**Готово, если:** blocking checks зелёные либо отчёт честно содержит ограничения и не разрешает последующие шаги.

### `VP-09` - Результаты и возврат к единому плану

- [ ] Создать `docs/video_research/VIDEO_STRATEGY_FINDINGS.md` с методологией, source provenance, отрицательными findings и итогами по каждому `CF-VP-XX`.
- [ ] Создать machine-readable `docs/video_research/VIDEO_STRATEGY_EXPERIMENTS.json` либо совместимый registry отчётов, связанный с ledger/source/protocol hashes.
- [ ] Обновить `docs/video_research/INTEGRATION_MAP.md`: mapping нового/старого, состояние, blockers, revisited assumptions, SHA коммитов.
- [ ] Отметить `[x]` только проверенные пункты и приложить конкретные test commands/results; оставить `[ ]` при невозможности подтверждения.
- [ ] В основном рабочем `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` обновить checklist/зависимости/decision log и привести итог в унисон; не модифицировать unrelated статусы.
- [ ] Провести independent reviewer pass, зафиксировать воспроизводимый commit/PR и handoff следующему текущему этапу master-плана.

**Готово, если:** обе части плана синхронизированы, журнал доказательств читаем и никакой research candidate не перешёл в реальную торговлю.

## 5. Оркестрация и зависимости работ

| Роль | Работа | Артефакт | Условие старта |
|---|---|---|---|
| `Lead / Integration` | найти текущий master-план, idempotent merge, task board, конфликт-ревью | `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` + `INTEGRATION_MAP.md` | сразу, сначала **INT** |
| `A / Architecture & Safety` | read-only runtime/code audit и API reuse map | `AUDIT.md` | после безопасного входа |
| `B / Data & Timing` | closed-only bars, as-of pivots, profile proxies | feature code + tests | после согласования typed contracts |
| `C / Signals` | CF-VP-01...07 детекторы | signal code + tests | параллельно с B только при стабильном API |
| `D / Quant & Validation` | preregistration, execution shared-wallet, paired metrics | immutable protocol/ledger/report | после source freeze и baseline contracts |
| `E / ML & Paper` | optional forward paper и optional ML | research-only reports | только после квантового допуска |
| `F / QA Reviewer` | independent no-live/no-leakage/compatibility checks | audit + blockers | непрерывно, read-only review |

- [ ] У каждого subagent отдельная ограниченная зона владения файлами, worktree/ветка; не редактировать master-план параллельно.
- [ ] Lead объединяет изменения и синхронизирует preregistration до запуска search/eval.
- [ ] Любая потребность изменить frozen policy/contract требует **новой** версии study, отдельного decision log, не задним числом.
- [ ] Если субагенты недоступны, тот же task board выполнять последовательно без имитации параллельной работы.
- [ ] Ни один worker не запускает live orders и не меняет production timers.

## 6. Приоритет, blockers и условия остановки

**Первый deliverable:** интегрированный действующий `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md`, compatibility audit, preregistered study design; это важнее новых сигналов.

**Предпочтительная очередность:** `INT` -> `VP-00` -> `VP-01` -> `VP-02` -> `VP-03 (CF-VP-01/02/04/05/07)` -> `VP-04` -> `VP-05` -> `VP-06` -> `VP-07` -> `VP-08` -> `VP-09`. `CF-VP-03/06` могут быть deferred при плохих данных.

Остановить только **новый исследовательский этап**, если: конфликты незавершённых изменений master, нет безопасной read-only информации о runtime, data leakage, невозможна независимая регистрация, риск нарушить live executor, нехватка диска/памяти, не хватает maturity labels, нет исторического instrument evidence. При этом прежняя согласованная работа агента не должна автоматически отменяться.

**Никакого повышения допуска:** содержимое этого документа не даёт разрешения на инвестиционные сделки, live pilot, futures, leverage, увеличение ставок или изменение существующего ML gate.

## 7. Проверка объединения двух планов (обязательный QA-checklist)

- [x] `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` сохранён как действующий план агента; `IMPLEMENTATION_PLAN.md` не подменял его и не получал дублирующий независимый трек.
- [x] Все старые фазы/чекбоксы сохранены, их порядок и смысл неизменны.
- [x] Раздел `CF-VP-2026-10-17` есть **один раз** и ссылается на подробный файл.
- [x] Дублировавшиеся задачи сведены ссылкой `REUSE`/`EXTEND`, а не реализацией заново.
- [x] Невыполненное не стало `[x]`, выполненное не стало `[ ]` без доказанной причины.
- [x] Новый план не отодвинул текущие опасные production blockers и не активировал live.
- [ ] Работающий на другом плане агент знает, **какую прежнюю задачу продолжать** после интеграции.
- [x] Повторная интеграция не меняет master содержательно (idempotence).
- [ ] Git diff, tests, evidence и reviewer acceptance сохранены.

---

**Как использовать документ:** передать его текущему Codex-оркестратору вместе с отдельным файлом `CryptoForge_Codex_Merge_Prompt_ActivePlan.md`. Промпт содержит правила интеграции в *существующий* master-план; этот файл - подробный, проверяемый перечень работ.
