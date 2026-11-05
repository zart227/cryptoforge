# Отсутствие новых покупок: ограниченная диагностика 27 октября 2026

Обновление 28 октября: [снимок и отдельный restore drill](FORECAST_MEMORY_SNAPSHOT.md)
выполнены; исходная база остаётся заполненной, переключение записи не выполнено.

Срез 23:21 МСК (`20:21 UTC`) выполнен чтением локального PostgREST, local
SQLite, user-systemd и сохранённых отчётов. Это не полный аудит Bybit или
подтверждение будущего поведения. Снимок без секретов и методика сохранены в
`.local/state/paired-cached-coordinator-work-20261027/no-buys-readonly-evidence.json`
и `diagnose_no_buys.py`; сохраняемые отчёты имеют префикс `snapshot-` в том же каталоге.

- Локальный кэш `data/live-journal-821b0fc204930b57.sqlite` содержит 75 строк
  исполнений. Последний найденный Buy — CHIPUSDT 8 октября 17:10:24 МСК,
  Sell — CHIPUSDT 17:14:03 МСК. Это предел проверенного кэша, а не гарантия
  полноты истории биржи. Последние события уведомлений в local `system_events`
  относятся к тем же покупкам/продажам; их время формирования позже fill.
- Executor timer активен, unit запускается с `--live --ml-mode gate
  --ml-max-age-hours 36`. Сервис `oneshot` между циклами inactive/dead;
  последнее завершение при проверке 23:18:51 успешно. Это не свидетельство
  наличия сделки или гарантии защиты на всём order path.
- В актуальном registry local PostgREST последняя `model.active` —
  `pure-python-logistic-candle-v1-20261007-09b486e979`, обучена 7 октября
  05:59:38 МСК; возраст превышает 36 часов. Код gate отклоняет входной сигнал
  при отсутствии свежей модели с `ml_fallback=no_fresh_model`. Этот механизм
  не объясняет все решения `hold`.
- Снимок `.local/state/current-entry-gate-diagnostics.json` за 23:00–23:15
  27 октября: 39 `hold`, ни одного `reject_entry`; этот 15-минутный срез
  не наблюдал `no_fresh_model`. Отдельное повторное чтение local
  `trade_decisions` за 16:30:00–16:45:00 МСК дало 31 `hold` и 7
  `reject_entry`, каждый из семи содержит `ml_fallback=no_fresh_model`;
  38 rows, запрос не усечён. Это другое окно, не причина каждого `hold`.
  В журнале цикла, начавшегося в 23:23:11 МСК, отмечены `risk_state=checked`,
  `open_positions=0`, 2 entry slots и пустые `entry_blockers`; это наблюдение
  самого исполнителя, не независимая сверка всего аккаунта. Дополнительный
  снимок окна и безопасные поля журнала — `decision-window-evidence.json`.
- Последний локальный кандидат `f8028fb44d`, SHA `ca3553e730bf…`, обучен
  27 октября 22:21:38 МСК; registry хранит его как candidate. Его promotion
  срез содержит 580 новых примеров и 3 сигнала, причина отказа —
  `insufficient_signals`; accuracy 0,76379 ниже majority baseline 0,76552,
  средний условный return сигнала после принятой стоимости отрицательный.
  Это фиксированный price-target screen, не cash P&L. Test split целиком
  содержит 1140 примеров; он не тождественен 580 новым promotion-примерам.
- По glob верхнего уровня `.local/models/pure-python-logistic-candle-v1-*.json`,
  `trained_at >= 2026-10-08`, найдено 176 файлов: 164 с основной причиной
  `insufficient_signals`, 7 `fails_baseline_or_costs`, 4
  `incompatible_feature_calculation_contract`, 1 `insufficient_unseen_examples`.
  Отдельное поле `comparison_blocked_reason` содержится в 151 записи; оно
  пересекается с основными причинами и не суммируется с ними. Это локальные
  файлы, не обязательно полная история реестра.
- У active legacy-модели отсутствуют исходные `input_candle_state`,
  `feature_calculation_contract`, `feature_lookback_candles`; у нового
  кандидата указаны `closed_only`, `bounded-window-candle-v1`, 120. Неизвестный
  контракт нельзя восстанавливать догадкой. Код отсеивает уже использованные
  границы fit/evaluation; частые кандидаты могут иметь мало действительно
  новых сигналов, но изменение частоты не гарантирует достижение порога.
- `primary-forecast-memory.sqlite`: 268435456 байт при лимите 256 MiB,
  `quick_check=ok`, 47979 прогнозов и 47722 версий outcome; свободных страниц
  0, последнее сохранение прогноза 24 октября 08:41:48 МСК, исхода 08:26:37.
  Раздел имел около 6,77 GiB свободно при снятии. `record`/`record_outcome`
  сохраняют дисковый резерв и отклоняют запись при этом размере; это отдельный
  диагностический блокер, сам по себе не причина отсутствия сделок. Quick-check
  не является полноценной проверкой восстановления или источника каждой записи.
- Managed feeder после незавершённого цикла `cycle-1b53f296681044a08dcb2d006e232e68`
  стартовавшего 17:11:37 МСК блокирует новые циклы; в журнале между стартом и
  последующим 17:21 присутствует новая загрузка системы. BTC/ETH sync и select
  имеют три success receipt; результат selected_sync неизвестен. Исторический
  runtime pin совпадает. 23:21 latest BTC open 17:10 МСК, ETH обновлялся другим
  процессом и его latest open 23:20 МСК (ещё не закрытая свеча). Это не
  подтверждение freshness всех источников и не доказанная причина каждого hold.
- В export `cash-paper-results` на 23:15 все три роли `paper_not_started`;
  `paper_evidence_pass=false`. Synthetic worker/replay, фактические цены,
  старые buy labels и price-forecast outcomes не заменяют prospectively
  registered cash paper с квалифицированными исполнениями.

Исходный [актуальный checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist)
содержит конкретные действия по reconciliation feeder, восстановлению места,
совместимой миграции и независимой оценке. Не переобучать cash study до
исходных cutoffs, не менять active/gate/risk/units и не посылать ордера ради
создания выборки. Новые выводы должны учитывать competing writers/readers,
время наблюдения и неизвестные данные.
