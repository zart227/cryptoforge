# CryptoForge — единственный актуальный план

Дата сверки: **5 ноября 2026**. Это единственный файл, в котором отмечается
текущий прогресс. Исторические планы, дневники и evidence-отчёты сохраняются,
но их чекбоксы больше не являются очередью.

Последний проверенный runtime-срез executor — **5 ноября 2026, 15:34 МСК**
(пункт R1). Сверка остальных пунктов по-прежнему опирается на отчёты до
2 ноября. Прибыльный кандидат и рост реального дохода не доказаны.
Реальных заявок этот аудит не создаёт и sealed outcomes не открывает.

LLM-направление остаётся у другого агента и в эту очередь не входит.

## Что было не так в планах

Одновременно «текущими» считались корневой `IMPLEMENTATION_PLAN.md`,
исследовательский план, сверка от 14 октября, чек-лист от 1 ноября,
VP-спецификация, LLM-план, `FINAL_AUDIT.md` и промпт продолжения обучения.
Они расходятся.

Сделано, но в старых очередях всё ещё числится открытым:

- Сбор свечей возобновлён 1 ноября новой регистрацией feeder. Старый
  незавершённый цикл сохранён и не дописывался. Исторический эффект
  `selected_sync` по-прежнему неизвестен — это отдельный открытый пункт,
  а не «feeder всё ещё лежит».
- Запись прогнозов возобновлена 1 ноября на том же SQLite при лимите 512 МиБ.
  Повышение лимита не является запланированным versioned cutover.
- 2 ноября закрыты 31 недавний зрелый исход и 279 старых. На срезе 09:43 МСК
  зрелых незакрытых не было. Это ценовая диагностика, не денежные метки.
- История Bybit за зарегистрированный интервал сверена 2 ноября: 63 исполнения,
  12 конверсий, последнее исполнение CHIP 8 октября, остатки 23 активов сошлись.
  Локальный кэш до этой сверки нельзя было считать биржей; после неё пункт
  «биржа не проверена» устарел в границах этого интервала и ключа.
- Причины выходов: **25 из 30** ордеров бота. Формулировка «10 причин утрачены»
  устарела. Не найдены пять ордеров 29–30 сентября: NEAR `2314983928643283456`,
  0G `2315320374075943424`, QNT `2315327243498646016`, NIGHT `2315458141795740160`,
  NIGHT `2315473247120222720`. Их нельзя восстанавливать догадкой.

Отмечено выполненным шире, чем проверено:

- Фазы 0–29 и `FINAL_AUDIT.md` закрывают сентябрьский Freqtrade dry-run.
  Локальный Supabase executor установлен с `--live`. Галочки «реальные заявки
  невозможны» и «фаза 26/30 завершена» этот executor не квалифицируют.
- В `FINAL_AUDIT.md` одновременно указаны 121 тест и запрет реальной торговли.
  Сверка 14 октября зафиксировала 1057 non-integration тестов и установленный
  `--live`. Ни одно из этих чисел не является сегодняшним полным прогоном.
- Накопленные «753 / 827 разных cases» — срезы отдельных приёмок, не текущий suite.
- `INT-03` отмечен выполненным, но файла `docs/plans/CF-VP-2026-10-17.md` нет.
  Спецификация лежит в `docs/CryptoForge_VP_Research_Checklist_ActivePlan.md`.
- Локальные копии SQLite на том же диске названы backup. Они не закрывают
  независимый backup из R15. Crash после отправки ордера проверен fake exchange,
  не боевым отказом.
- В одном исследовательском плане абзац 1 ноября всё ещё говорит, что ledger
  заполнен на 256 МиБ и последний прогноз от 24 октября. Более поздние абзацы
  того же файла это опровергают.
- Правила раздела 0 в корневом плане записаны как пустые чекбоксы. Это запреты,
  а не незавершённые задачи.
- Ранние пункты W6b.3b и W8.2b.3 в датированных блоках остались пустыми после
  того, как следующие подпункты уже были закрыты.

## Уже сделано и заново не реализуется

- [x] Инфраструктура фаз 0–29 для исходного dry-run контура: данные Bybit Spot,
  scanner, regime, baseline, risk engine, журнал, метрики, outbox, мониторинг,
  backup/export tooling. Это не допуск текущего `--live` executor.
- [x] Исследовательский архив, симулятор, метки, общий wallet, costs и
  walk-forward календарь на 6 окон. Grid fixed/ATR: **0/4 economic passes**.
- [x] Paper producer v2, native archive, capture и независимый replay.
  Координатор, cached reader и cash application доведены до W8.2b.3a
  на synthetic и коротком отрицательном прогоне. Positive path и длинная
  ёмкость не проверены.
- [x] Основная база — локальный PostgreSQL/PostgREST.
- [x] Feeder снова пишет текущие свечи с 1 ноября; старый цикл `cycle-1b53f296681044a08dcb2d006e232e68` сохранён.
- [x] Диагностические forecasts и outcomes снова пишутся; очереди 31 и 279 закрыты 2 ноября.
- [x] Сверка биржи и FIFO за исходный интервал: 49 сегментов, не 49 ордеров;
  net **−1.3055964 USDT**.
- [x] Контекст новых решений пишется до отправки, в unit подключены submission
  journal и decision outbox. Первый штатный цикл 2 ноября в 10:40 МСК ордеров
  не отправлял.
- [x] Кандидат `253dc4fce7` не продвинут: 2 сигнала на 420 примерах.
  Улучшение probability metrics не является cash P&L.
- [x] Документация VP встроена как отдельное направление. Семь гипотез не реализованы.
- [x] LLM: есть ограниченный diagnostics-отчёт L1a. Обучение через LLM не подключено.

## Единственный чеклист

`[x]` закрывает только названную проверку. Дата cutoff сама по себе ничего
не открывает. До наступления даты исходы закрытого окна не читать.

### A. Текущий executor и риск

- [x] **R1.** Новый read-only снимок после 2 ноября: unit, UID, флаги, account,
  позиции, капитал, модель, единственный владелец исполнения. Отдельно
  зафиксировать, чего снимок не видит.
  Проверка 5 ноября 2026, 15:34:50–15:34:57 МСК, user systemd этого хоста и
  read-only GET Bybit. Source HEAD `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`;
  рабочее дерево грязное, поэтому runtime pin — SHA-256 названных entry/decision
  файлов `07910733fd405f94876c89f94ae7be2af1e14b69beff47b6c002a0639ae71658`.
  Unit SHA-256 `9bfbb1349d6c510ddc73ea58d584ca21d5fbf48323fd4a467b252e71cee97ba4`.
  Receipt `.local/state/executor-snapshot-20261105/r1-report.json`
  (`9a7e195a868d5d39bc4a3e20a3c7da42c8eb304226eabd052bbd0b4e3c132a42`) и
  уточнение `.local/state/executor-snapshot-20261105/r1-review.json`
  (`db9682a7b8587db16198b6c9f3520feec60726d2321310661c76111289ee8288`).
  Установленный unit — `cryptoforge-supabase-executor.service` пользователя
  arthur, UID 1000; таймер enabled/waiting. Флаги включают `--live`,
  `--ml-mode gate`, stake 6, max positions 6, daily loss 2, stop 0.04.
  Счёт UID `590123682`, parent `174519639`, UTA, ключ read/write и шире Spot.
  UNIFIED equity `14.7845665` USD, USDT wallet `14.718604`; ответ вернул 15
  монет, открытых spot-позиций по порогу 1 USD нет, borrow и linear size нулевые.
  С 2 ноября 00:00 UTC spot-исполнений и unified transaction-log строк в этом
  окне нет. В цикле 15:34:24–15:34:43 МСК процесс записал 3 прогноза модели
  `pure-python-logistic-candle-v1-20261105-e75e43de34`
  (`3cb39171f560eaa43cbf69da2440cc272a07d893be4370a5c4fddd5ff283d4e4`);
  свежего `model.active` в окне 36 часов нет, gate для BEAM дал
  `ml_fallback=no_fresh_model`. Единственный user unit с флагом `--live` —
  этот executor. Локальный owner-файл привязан к journal и хосту,
  `account_uid_verified` ложен, flock между циклами не удерживается.
  Снимок не видит другие хосты и копии ключа, нулевые монеты, которые
  wallet-ответ опускает, FUND/inverse/option, историю до 2 ноября и
  resident-модель после выхода oneshot.
- [ ] **R2.** Связать strategy, source, paper и independent admission с фактическим
  order path. Проверить kill switch и no-new-entry так, чтобы разрешённый выход
  сохранялся. Local approval это не заменяет.
  Продвижение 5 ноября 2026, 15:45 МСК: read-only карта установленного пути и
  тесты controls без изменения unit. Source HEAD `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`;
  runtime pin launcher/executor/controls
  `1a046b41cd1bfb08df7f63449a874c2a27998ba4bd3b6b207f3b109a93226e32` /
  `0ae3096e4b0daa63a9d72fd3219ca4265153334a7c88dcce0ac175c7003bf90a` /
  `a1c0da0239e37d50ac8091657341fbf201f24e31ae8f9dad6f6fa8d84147dfb1`. Receipt
  `.local/state/executor-order-path-20261105/r2-report.json`
  (`0bb98e4d60db0191ad6846d0ec1417e904cb7a18aed1ddc1f5e6a62870696e70`),
  pytest log `r2-pytest-execution-controls.txt` (**12 passed**, exit 0).
  **Доказано:** strategy = `SupabaseLiveExecutor` signals + ML gate; source =
  `SupabaseMarketReader`/feeder candles; paper и independent admission
  (runtime approval, account policy, sealed cash) в ExecStart **не подключены**.
  Цикл 12:39 UTC записал `configured_protections.execution_controls=false`,
  совпадает с unit. В коде `no_new_entry` блокирует только Buy, Sell при pause
  проходит; `kill_switch` блокирует обе стороны; exit path executor не использует
  entry_blockers, но без `ControlledOrderClient` операторский kill на боевом
  submit **не действует**.
  **Не закрыто:** живой order path с `--execution-controls`, наблюдение toggle
  на runtime, полная qualification strategy/paper/admission. Менять unit/флаги
  в этом проходе нельзя — нужен отдельный rollout с откатом.
  Дополнение 5 ноября 2026, 15:42 МСК: `deploy/install_local_supabase_executor.sh`
  тоже **не** генерирует `--execution-controls` и runtime-approval bundle —
  расхождения с боевым path нет. Receipt
  `.local/state/executor-order-path-20261105/r2-rollout-admission-audit.json`
  (`0b5963c3f92e629ef0ca28c89cd2ed22645e948b74e881ec1072ed35305a07bf`).
  Pytest `tests/test_execution_controls.py` +
  `tests/test_runtime_approval.py`: **60 passed**, exit 0. Independent admission
  (`sealed_cash_readiness`, paper producers) не входят в `windows_background_runner
  executor` argv.
  Rollout/rollback 5 ноября 2026, 15:43 МСК (unit **не** менялся): baseline-копии
  unit/timer в `.local/state/executor-rollout-20261105/rollback-baseline/`,
  готовый idle `executor-controls-v1-ready.json`, proposed diff только в receipt.
  Receipt `.local/state/executor-rollout-20261105/rollout-rollback-receipt.json`
  (`9175de5cd51cf239bfb779903d2abab0b1db64943df2ef752f6632f9c517d476`).
  Pytest exit+pause+kill: `test_actual_executor_stop_survives_entry_pause_but_respects_kill`
  **1 passed**. Live unit по-прежнему без `--execution-controls`.
  Перепроверка gate 5 ноября 2026, 15:54 МСК: live unit SHA и ExecStart line SHA
  совпадают с rollback receipt (`9bfbb134…`, `9250502a…`); baseline-копия не
  изменилась; `--execution-controls` **не** на unit. Receipt
  `.local/state/executor-rollout-20261105/r2-rollout-gate-recheck.json`
  (`b2aa721cec3b154a7827f6b1e283d39920808e25084ad05f2dbf40271ed1815a`), pytest
  **60 passed** (`r2-pytest-recheck-20261105.txt`, включает kill/pause test).
  **R2 закрыт только после:** явного одобрения rollout, применения unit с откатом,
  live наблюдения toggle; strategy/paper/admission binding — открыто.
  Углубление 5 ноября 2026, 15:55 МСК: admission binding vs
  `live-risk-snapshot.json` (`dcfe0738f25fdeeb53f58710143dbf5d2b1bc900012a48f95984c46c02d0f146`):
  runtime_approval bundle **не** собран; paper/sealed_cash **не** на launcher argv;
  controls idle (`6c3586eaf535d7cf0f933c176fced0a381e5ee477bff35e0de33a3eeaa78d7f2`).
  Receipt `.local/state/executor-r2-admission-binding-20261105/r2-admission-binding-report.json`
  (`6cb14ef8ad0a96545da314bddca0ed5d5fe3b8c390b9846d2564eb65acbfdca1`),
  pytest `test_sealed_cash_readiness` **14 passed**. `r2_admission_binding_qualified:
  false`.
  Углубление 5 ноября 2026, 15:56 МСК: kill/no-new-entry vs exit path — на live
  нет `ControlledOrderClient`; код при wiring: pause блокирует только Buy, kill
  обе стороны; executor exit не использует `entry_blockers`. Live qualification
  **не** выполнена. Receipt
  `.local/state/executor-r2-exit-controls-20261105/r2-exit-kill-qualification.json`
  (`5c92b56f94428bc847dbed904362666027202c5433fdcc1aff36ba9b89f504bb`), pytest `test_execution_controls` **12 passed**
  (`r2-pytest-exit-controls.txt`). `r2_kill_exit_qualified: false`.
  Синтез 5 ноября 2026, 15:57 МСК: единый статус R2 по 6 child receipts;
  matrix — live controls/admission/kill **не** квалифицированы; rollback готов.
  Receipt `.local/state/executor-r2-qualification-synthesis-20261105/r2-qualification-synthesis.json`
  (`6434babe6480c6ea53562afe7702898c6d2beddb95005864edaa0231d72f740c`), pytest
  synthesis **74 passed**. **`r2_closed: false`**; hard blocker — явное одобрение
  пользователя на unit rollout (без него unit не менять).
  Pre-apply gate 5 ноября 2026, 16:22 МСК: R3 `--submission-risk-guard` уже на unit
  (`f9e3e865…`); R2 добавит idle `--execution-controls` (SHA `6c3586ea…`) **без**
  снятия guard. Snapshot: `execution_controls=false`, `submission_risk_guard=true`.
  Receipt `.local/state/r2-execution-controls-preapply-gate-20261105/r2-execution-controls-preapply-gate-report.json`
  (`95ae467fccc4ec4d4d38bdb9c2eb2e39118686f69a21e799065efd197bb6db6f`), pytest
  execution_controls+launcher **17 passed**. Apply **не** выполнен — нужно отдельное
  «одобряю» на R2 controls.
  Apply 5 ноября 2026, 16:22 МСК (оператор: «одобряю»): добавлены
  `--execution-controls` + idle file (`6c3586ea…`); R3 guard сохранён. Unit
  `901e146c…`; receipt `r2-execution-controls-applied-receipt.json`
  (`29068738ee24aca3f827cbd8492289187e575353f33e47fc8e5bd0b550a32acf`), pytest **30 passed**.
  Post-apply 5 ноября 2026, 16:24 МСК: timer 16:24:04–16:24:17 MSK; snapshot
  `3087e1f4938ba4fb6d1cb6bd0021e7ef16b11b549212ac138821dacd973b495b` —
  `execution_controls=true`, `submission_risk_guard=true`. Receipt
  `.local/state/r2-execution-controls-postapply-observation-20261105/r2-execution-controls-postapply-observation-report.json`
  (`2d21eae122eedd200bdd943d56b382c9f8dfc73752910d472408d3f34eeefb3d`), pytest
  **30 passed**. Kill/admission live **не** квалифицированы; **R2 [x]** нет.
  Recheck 5 ноября 2026, 16:26 МСК (post-controls): ControlledOrderClient **ожидается**
  на live; admission bundle/runtime_approval **нет**; kill/pause toggle **не** наблюдались
  (controls idle). Receipt
  `.local/state/r2-post-controls-admission-kill-recheck-20261105/r2-post-controls-admission-kill-recheck-report.json`
  (`46e40bd05f00f00131332cecd27e9869afcffb361e809d6af4995faa298322dc`), pytest controls+runtime_approval+sealed_cash **74 passed**.
  `r2_kill_exit_operational_qualified: false`; `r2_admission_binding_qualified: false`.
  Toggle observation 5 ноября 2026, 16:29 МСК: `no_new_entry=true` в controls JSON (unit
  не менялся); цикл 16:28 MSK — snapshot blocker
  `operator no-new-entry active; buys paused`; откат idle SHA `6c3586ea…`. Receipt
  `.local/state/r2-controls-toggle-observation-20261105/r2-controls-toggle-observation-report.json`
  (`2d05b0d3d800fa15d502c747452d3a828934bba2e00ff345d5efa028b62bb026`), pytest **12 passed**.   Kill toggle / exit-under-pause **не** наблюдались;
  **R2 [x]** нет.
  Kill toggle 5 ноября 2026, 16:31 МСК: `kill_switch=true` в controls JSON; цикл
  16:30 MSK — snapshot blocker `operator kill switch active…`; откат idle `6c3586ea…`.
  Receipt `.local/state/r2-kill-toggle-observation-20261105/r2-kill-toggle-observation-report.json`
  (`341830db3b3472b611bd5cd0df2342e5ae2671d138a808526c03229a51c4c596`), pytest **12 passed**. Exit-under-pause/admission **не** закрыты; **R2 [x]** нет.
  Exit-under-pause code crosscheck 5 ноября 2026, 16:34 МСК: `control_blockers` блокирует
  только `Buy` при `no_new_entry`; `ControlledOrderClient` на submit; integration test
  `test_actual_executor_stop_survives_entry_pause_but_respects_kill` + pytest **12 passed**.
  Live Sell под pause **не** exercised. Receipt
  `.local/state/r2-exit-under-pause-codecross-20261105/r2-exit-under-pause-codecross-report.json`
  (`e2adafa2a6b8d668f6b6d3183dd5a88dc78556333847d340e43beed7af941c26`). **R2 [x]** нет.
  Admission binding post-toggles 5 ноября 2026, 16:37 МСК: snapshot `fb44ef14…` —
  `runtime_approval=false`; на unit **7** prerequisite-флагов bundle отсутствуют
  (`--exit-data-fallback`, reservations, drawdown/fractional, `--entry-runtime-approval`);
  paper/sealed_cash не на launcher argv. Pytest runtime_approval+sealed+controls **74 passed**.
  Receipt `.local/state/r2-admission-binding-post-toggles-20261105/r2-admission-binding-post-toggles-report.json`
  (`611b70e66aaed5d0bdbf00e71bd9479181e3f00f6200c00813969b3137fc0d0b`). `r2_admission_binding_qualified: false`; **R2 [x]** нет.
  Exit-under-pause live observation 5 ноября 2026, 16:40 МСК: `open_positions=0`,
  journal submit rows **0** — Sell под `no_new_entry` на live **не** наблюдался;
  toggle receipt `2d05b0d3…` без sell activity. Receipt
  `.local/state/r2-exit-under-pause-live-observation-20261105/r2-exit-under-pause-live-observation-report.json`
  (`630055c0befee09607032afc0bfa6a9e1101849d269e9563bb9963a99ab1113a`), pytest **2 passed**. **R2 [x]** нет.
- [ ] **R3.** Квалифицировать position, aggregate stop, daily loss, drawdown,
  costs и reservations на выбранном счёте. Missing data, dust, multi-buy,
  комиссия третьим токеном и внешний cashflow не обходят лимит.
  Read-only срез 5 ноября 2026, 15:45 МСК (R2 rollout по-прежнему без
  применения unit). HEAD `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`;
  pins `live_risk.py` / `submission_risk.py` / unit — в receipt. Receipt
  `.local/state/risk-qualification-20261105/r3-report.json`
  (`4a1fcfb9c37de34ecfc5c9551aa9022ae2eb3d1fe0787a0b9a3af0852b212a13`),
  pytest `test_live_risk` + `test_submission_risk` — **passed**, exit 0.
  **Наблюдено:** equity ~14.78 USDT, stake 6, daily loss cap 2 USDT в unit,
  `live-equity-risk.json` читается, blockers сейчас пустые; spot positions ≥1 USD
  = 0; **14 dust** остатков <1 USD; с 2 ноября transaction-log строк 0.
  **Не квалифицировано на live submit:** нет `--submission-risk-guard`,
  reservations, drawdown state; daily loss не вызывается перед Buy; aggregate
  stop только per-symbol 4% в executor; third-token fees и multi-buy FIFO не
  доказаны. `r3_closed: false`.
  Углубление 5 ноября 2026, 15:46 МСК: read-only dust vs сверка 2 ноября,
  frozen FIFO/fees, поведение `fee_quote` без live fee API. Receipt
  `.local/state/risk-qualification-20261105/r3-dust-fees-fifo-audit.json`
  (`eb437489f8ffac5bd7d2f6131cb76cf49781b057cd8650b0231e2ba271fc1158`),
  pytest `tests/test_live_trade_journal.py -k 'fee or third'` — **6 passed**,
  log `r3-pytest-journal-fees.txt`. Wallet-ответ **15** монет vs **23** tracked
  в `execution-reconciliation-20261102/verified/report.json`
  (`d9a1fd75704a109bc7c27353e28d297cc3f4a4f940ecb54859d4380f1083db66`):
  nine coins только в сверке (0G, BERA, CELO, ENA, ETH, INIT, NIGHT, QNT, ZRO) —
  вероятно нулевые/опущенные строки, не доказан off-exchange вывод. Frozen
  summary: 63 executions, **49 closed segments** (не 49 ордеров), 14 open lots,
  `incomplete_fees=0`. Multi-buy/reservations на unit не подключены. Третий
  токен комиссии: `fee_quote` возвращает None → live submit fail-closed **не**
  доказан. `data/live-journal-*.sqlite` на хосте в этом проходе не найден.
  Углубление 5 ноября 2026, 15:47 МСК: read-only GET `/v5/account/fee-rate`
  для 8 USDT-пар (unit + dust), replay `verify_fee_observation` на ETHUSDT.
  Receipt `.local/state/r3-fee-observation-20261105/r3-fee-observation-report.json`
  (`c9be997494067a4320dc3ab22aa680cf34c8cb24dd7c42e6ce3e61be6d4f59b3`), capture log `capture-stdout.json`, pytest fee_observation
  **8 passed**, live_risk+submission_risk rerun **21 passed**. Наблюдено maker
  0.001 / taker 0.0018 на всех парах; `live_promotion_allowed=false`,
  `fee_asset_known=false`. Установленный unit **без** `--submission-risk-guard`;
  `run_supabase_live_executor` **не** подключает fee receipts к sizing/submit.
  Тариф на live path **не** квалифицирован; third-token fill cost по-прежнему
  вне account-fee observation.
  Углубление 5 ноября 2026, 15:48 МСК: read-only `spot_reservations` + argv unit
  vs guard chain; live pending buys **0**, journal `buy_reservations` **{}**.
  Receipt `.local/state/r3-reservations-qualification-20261105/r3-reservations-report.json`
  (`453aa9cb62fad6aa9ca3f844a4f94d95b462e0e4359faa8524fdd53af2f334fc`), pytest
  spot_reservations + local_order_reservations + submission_risk — **49 passed**
  (`r3-pytest-reservations.txt`). Pins `spot_reservations.py`
  `e8eb9a59587da12fb08e9ea179df6c58eccf93c7339993e62523fd5b834a483e`,
  `submission_risk.py` `d43bf6196692403bdd09ed245139a4fea7965cb322b6ad2a980b99f8c077a1dc`.
  Journal на unit есть, но без `--submission-risk-guard` wrapper не блокирует
  multi-buy/daily loss at submit; `--spot-reservation-guard` и
  `--local-order-reservations` выключены; drawdown guard выключен.
  Углубление 5 ноября 2026, 15:49 МСК: read-only aggregate vs per-symbol stop.
  Unit: `--stop-loss-percent 0.04` в executor; **нет** `--drawdown-state` /
  `--max-portfolio-drawdown` / portfolio peak файла на хосте. Daily baseline —
  `live-equity-risk.json` (UTC day), не portfolio drawdown latch; daily loss
  at submit без `--submission-risk-guard` не enforced. Receipt
  `.local/state/r3-drawdown-aggregate-20261105/r3-drawdown-aggregate-report.json`
  (`749ea349d074b62c42a089a4dabe5981dc4bd585eebb905375fddd1158569d45`), pytest `test_portfolio_drawdown` **16 passed**
  (`r3-pytest-portfolio-drawdown.txt`). Pin `portfolio_drawdown.py`
  `eb4d63caa82d5dc2c3373054bc4008b7213861a5c1f0d4a4750451659404852d`.
  `aggregate_stop_qualified: false`.
  Углубление 5 ноября 2026, 15:50 МСК: read-only unified transaction-log
  (7-day windows с 2026-09-01 UTC до «сейчас»). Receipt
  `.local/state/r3-external-cashflow-20261105/r3-cashflow-report.json`
  (`71b07ef097b8a6bee3de9801e1011659d97a3f21ce7b5abba159be5884b6d8eb`).
  **С 2 ноября 00:00 UTC — 0 строк** (согласуется с r3-report). **До 2 ноября**
  в опрошенных окнах **151** строк: TRADE 126, CURRENCY_BUY/SELL по 12,
  **TRANSFER_IN 1** (+16.138 USDT, окно 21–28 сент.). DEPOSIT/WITHDRAW в
  агрегате **нет**; полнота истории **не** сертифицирована (ниже сентября и
  вне 7-day contract не опрошено). Live path **не** пересчитывает daily baseline
  по cashflow — bypass лимита **не** квалифицирован и **не** опровергнут на
  всех типах. `r3_closed: false`.
  Углубление 5 ноября 2026, 15:51 МСК: read-only цепочка submit на unit
  (`JournaledOrderClient` → Bybit, **без** `SubmissionRiskClient`). `fee_quote`
  не вызывается до submit; third-token/extraFees/missing execFee не блокируют
  Buy; post-submit FIFO помечает `incomplete_fees`, journal health **warning**,
  но `reconcile_journal` не паузит entries. Receipt
  `.local/state/r3-submit-fee-failclosed-20261105/r3-submit-fee-failclosed-report.json`
  (`c6771fccc973d7e35960c864bce42f299b92e58a9f74303cdb33ca179e5785e8`), pytest
  journal fee/extra **6 passed** (`r3-pytest-submit-fee-failclosed.txt`).
  `missing_data_fail_closed_at_submit: false`; `r3_third_token_live_qualified: false`.
  Синтез 5 ноября 2026, 15:52 МСК: единый статус R3 по 7 child receipts;
  unit guard flags **0**; matrix criteria — live submit guards **не** квалифицированы.
  Receipt `.local/state/r3-qualification-synthesis-20261105/r3-qualification-synthesis.json`
  (`bf6fb5fd5ac13732fc5d49891c2b504d66e2347c5e3df5544378f141e8de9725`), combined pytest **14 passed** (`r3-pytest-synthesis.txt`).
  **`r3_closed: false`** — закрытие блокируют отсутствие submission-risk/drawdown/
  reservations на unit и fail-closed fees на submit (rollout — отдельно от R2 controls).
  Углубление 5 ноября 2026, 15:58 МСК: R3 `--submission-risk-guard` **отдельно**
  от R2 `--execution-controls`; snapshot `c31b828e…` подтверждает
  `submission_risk_guard=false`, `entry_blockers=[]` не заменяет submit guard.
  Receipt `.local/state/r3-submission-guard-path-20261105/r3-submission-guard-path-report.json`
  (`b668ba5f31a209043c7463790c1b9406b1ed2a0109b6737fdf434dcfb2086f86`), pytest
  **21 passed** (`r3-pytest-guard-path.txt`).
  Углубление 5 ноября 2026, 15:59 МСК: drawdown peak readiness — на хосте **нет**
  `observed-portfolio-drawdown-v1` state; `live-equity-risk.json` только daily UTC
  baseline (`4140ac6b…`); `recover_daily_equity_state` **не** переносит peak/latch
  (docs/DAILY_RISK_RECOVERY.md). Unit без `--drawdown-state`. Receipt
  `.local/state/r3-drawdown-peak-readiness-20261105/r3-drawdown-peak-readiness-report.json`
  (`079f83d8d3b80d133550a34f84b724c861ac8194230da3a526ea15ecbc88c38a`), pytest daily_risk_recovery+portfolio_drawdown **50 passed**.
  `r3_drawdown_qualified: false`.
  Углубление 5 ноября 2026, 16:05 МСК: cashflow → daily baseline binding — executor
  **не** читает transaction-log для `live-equity-risk.json`; UTC rollover ставит
  `start_equity = current_equity`; приток в тот же UTC-день **не** поднимает baseline,
  но снижает `start_equity - current_equity` (обход лимита **не** квалифицирован и
  **не** опровергнут для всех типов). Receipt
  `.local/state/r3-cashflow-baseline-binding-20261105/r3-cashflow-baseline-binding-report.json`
  (`e58667d03b57276c71a0162e9c6c04d61ab5498bd6b59ced8cae157aaa3aa63d`), pytest
  daily_equity_state+daily_risk_recovery **56 passed**. `r3_cashflow_baseline_qualified:
  false`.
  Синтез v2 5 ноября 2026, 16:06 МСК: 10 child receipts (v1 + guard-path + drawdown
  peak + cashflow binding); unit baseline без guard flags. Receipt
  `.local/state/r3-qualification-synthesis-v2-20261105/r3-qualification-synthesis-v2.json`
  (`e055e76dd5335d859b87e81322e194b304f228e971212d9994e115f962f38d35`), pytest matrix **12 passed**
  (`r3-pytest-synthesis-v2.txt`). **`r3_closed: false`**.
  Plan checkpoint 5 ноября 2026, 16:01 МСК: read-only фазы R3 rollout
  (`--submission-risk-guard` отдельно от R2 `--execution-controls`; drawdown только
  с reviewed state, **без** auto peak). Rollback unit SHA `9bfbb134…`. Receipt
  `.local/state/r3-guard-rollout-plan-checkpoint-20261105/r3-guard-rollout-plan-checkpoint.json`
  (`4005c5fad7646c28a9bf26cf161672773c088c96c27473f672cc6a34b8a140e5`), pytest
  submission_risk+run_supabase_live_executor+execution_controls **35 passed**.
  Unit **не** менялся; apply блокирует явное одобрение оператора.
  Pre-apply gate 5 ноября 2026, 16:08 МСК: live user unit SHA **совпадает**
  с rollback (`9bfbb134…`); prerequisites (equity state, journals) на месте;
  snapshot `0969da548…` — `submission_risk_guard=false`. Receipt
  `.local/state/r3-phase-a-preapply-gate-20261105/r3-phase-a-preapply-gate-report.json`
  (`4e266795b3d60b160835c462e5bcc5fb71079804a79d532e742d630bcb13b9a2`), pytest submission_risk+live_risk **21 passed**.
  `phase_a_applied_on_live: false`; **R3 [x]** нет.
  Синтез v3 5 ноября 2026, 16:16 МСК: **12** child receipts (v2 + guard checkpoint +
  phase A preapply); live recheck — unit `9bfbb134…`, snapshot `a1406d765…`,
  guards false; preapply gate still valid. Receipt
  `.local/state/r3-qualification-synthesis-v3-20261105/r3-qualification-synthesis-v3.json`
  (`550c25399eb4b93414395b817919874815e485b55cb8044d8d9830e9ff447971`), pytest matrix
  **12 passed** (`r3-pytest-synthesis-v3.txt`).   **`r3_closed: false`**.
  Scope qualification 5 ноября 2026, 16:22 МСК: read-only границы **phase A**
  (`--submission-risk-guard` only) — daily loss/stake/capacity at submit в коде;
  third-token/fees/drawdown/reservations/controls **вне** phase A. Receipt
  `.local/state/r3-phase-a-scope-qualification-20261105/r3-phase-a-scope-qualification-report.json`
  (`a701575a1a2664a556a72d378ee8bcfdacb9b60cdbebe01e7b2c6212859c4d71`), pytest
  `test_submission_risk` **18 passed**; journal fee tests **6 passed** (fee slice).
  `phase_a_operational_qualified: false` (до apply).
  Apply 5 ноября 2026, 16:18 МСК (оператор: «одобряю»): на user unit добавлен
  **только** `--submission-risk-guard`; R2 `--execution-controls` **не** применён.
  Post-apply unit SHA `f9e3e865…`; rollback baseline файл **не** перезаписан
  (`9bfbb134…`). `daemon-reload` выполнен; executor **не** запускался (заявки не
  инициировались). Receipt
  `.local/state/r3-phase-a-applied-20261105/r3-phase-a-applied-receipt.json`
  (`31f34e7b2779afbb651c7e7db8ae567ebdb5209cddfee6f5d2090c20261dd77f`), pytest
  **21 passed**. Snapshot guard=true — после следующего цикла timer; **R3 [x]** нет.
  Post-apply observation 5 ноября 2026, 16:20 МСК: первый цикл timer **16:19:28–16:19:40**
  MSK (не ручной старт агента). Snapshot `ac1c56cc…` —
  `configured_protections.submission_risk_guard=true`, `execution_controls=false`.
  Receipt `.local/state/r3-phase-a-postapply-observation-20261105/r3-phase-a-postapply-observation-report.json`
  (`75313c6de167407d3d11f34d304aec938179ecf7be71679bde027c28547b2c88`), pytest **21 passed**. `phase_a_config_observed_on_live: true`;
  daily loss at submit **не** доказан; **R3 [x]** нет.
- [ ] **R4.** Проверить реальный restart, outage, unknown holdings и доставку
  выхода. Fake-client тесты не засчитываются. Длительный host drill feeder
  ещё не сделан.
- [ ] **R4, исторический хвост.** Эффект старого `selected_sync` остаётся
  unknown. Не возобновлять старый цикл, не ставить ему completion и не удалять
  сохранённый каталог. Полный inventory писателей строк БД не доказан.
- [ ] **R5.** Восстановить исходную daily/peak baseline на выбранном account/host
  без потери накопленного убытка.

### B. Данные, модель и разбор сделок

- [ ] **R6, устойчивость, не повторный запуск записи.** Подтвердить writers,
  fencing, late corrections и crash recovery до любого разрезания ledger.
  Независимый от этого диска backup и restore. Повышение лимита до 512 МиБ
  уже сделано и вторым решением не является.
- [ ] **R7.** Установить контракт фактически загруженной модели executor.
  Неизвестный legacy не угадывать. Сравнить candidate и совместимый control
  по net payoff после комиссий на непересекающихся окнах.
- [ ] **R8, ожидание.** Train cutoff **7 ноября 2026, 00:59:16 МСК**.
  Validation cutoff **21 ноября 2026, 00:59:16 МСК**. После cutoff проверить
  100 buy / 14 дней / 6 пар / ≥20 каждого класса для train и 40 / 7 / 4 / ≥5
  для validation. Не подменять выборку архивными, synthetic или ценовыми метками.
- [ ] **R8, разбор.** Пять причин выходов 29–30 сентября не найдены локально.
  Новые независимые носители можно проверить read-only. Не выдумывать причины
  и не считать 49 FIFO-сегментов отдельными сделками.
- [ ] **R9.** Свести не меньше 20 полных source-bound cases: entry, known_at,
  fees, rounding, first touch, residual basis, вывод reviewer. Готовые
  20 labels, 20 geometries и FIFO-сверку использовать, не собирать заново.
- [ ] **R10.** Ограничить или закрыть исторические listing, rules, steps, fees,
  spread, depth и fill coverage. Текущая комиссия счёта не доказывает прошлый тариф.
- [ ] **R11.** Source-bound qualification producer на полном local upstream.
  Старые frozen manifests не переписывать.

### C. Исследование и paper

- [ ] **Этап 3.** Net/risk heads на квалифицированных данных и point-in-time
  признаки, включая parity схемы за пределами bounded 120.
- [ ] **Этапы 4–6.** Новый ограниченный поиск только как новая зарегистрированная
  гипотеза. Правило и ML сравнивать на одном капитале и риске. Прошедшего
  кандидата нет; отсутствие преимущества фиксировать как REJECTED или
  INSUFFICIENT_EVIDENCE, не ослабляя пороги.
- [ ] **R12.** Полная preregistered selection по всем fold, с native,
  current-model, new-head и cash controls.
- [ ] **R13, ожидание.** Первое слепое окно заканчивается **15 ноября 2026,
  03:00 МСК**. До этого его outcomes не читать. Шесть окон заканчиваются
  **14 апреля 2027, 03:00 МСК**. Ноль сделок не доказывает доходность.
- [ ] **W7b.2c.2.** Фактический positive path: решение, fill и exit на заранее
  зарегистрированном paired stream. Короткий прогон 27 октября дал 0 fills.
- [ ] **W7b.3b и W8.** Неизвестные side effects, восстановление всего runner
  после host restart, физическая история, квоты и измеренная ёмкость.
  Оценка «30 дней» из count preflight измерением не является.
- [ ] **W9 / R14, условно.** Только после прошедшего кандидата и пунктов W6–W8:
  новое заранее зарегистрированное paper-наблюдение, минимум 30 дней и
  100 закрытых paper-сделок, затем replay и economic review.

### D. VP

Подробные гипотезы остаются в
[VP-спецификации](CryptoForge_VP_Research_Checklist_ActivePlan.md).
Статус ведётся только здесь.

- [ ] **INT.** Повторная сверка исходных документов, независимый reviewer и
  отдельный commit. Первоисточник видео в репозитории не найден. Путь
  `docs/plans/` не создавать задним числом, чтобы закрыть старую галочку.
- [ ] **VP-00…VP-09.** Baseline, preregistration, primitives, семь гипотез,
  execution stress, economic screen, future paper, условный research-only ML
  и QA. Общий симулятор переиспользовать. Статуса LIVE_APPROVED у этой ветки нет.

### E. Допуск

- [ ] **R15.** Совместное восстановление базы, risk, reservations, outbox и
  обоих журналов решений. Ownership, лимиты ресурсов и уведомления на
  выбранном runtime. Архив одного SQLite или одного tar на том же диске
  этот пункт не закрывает.
- [ ] **R16 и фазы 30–31.** Отдельный ограниченный счёт, объяснимые сделки,
  проверенные kill switch и guards, day/night цикл без голодания runtime,
  rollback и сравнение live с paper. Исторические галочки фаз 0–29 сюда
  не переносятся.

## Порядок

1. Сначала A: свежий read-only снимок executor и риска.
2. B и C вести без чтения sealed outcomes и без повторной реализации
   уже принятых механизмов.
3. 7, 15 и 21 ноября только снимать заранее заданные counts. Не подгонять
   протокол под оказавшийся объём.
4. D не обгоняет A и не меняет боевые флаги.
5. E закрывается последним. Пока R16 открыт, автономный live pilot не начат.

## Где лежит история

Эти файлы не обновлять новыми галочками:

- `IMPLEMENTATION_PLAN.md` — фазы и decision log
- `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md` — дневник исследования
- `docs/PLAN_REMAINING_CHECKLIST_20261101.md` — срез 1–2 ноября
- `docs/IMPLEMENTATION_RECONCILIATION_20261014.md` — сверка 14 октября
- `FINAL_AUDIT.md` — аудит 25 сентября
- `docs/CryptoForge_VP_Research_Checklist_ActivePlan.md` — текст гипотез VP
- `docs/LLM_ASSISTED_TRAINING_PLAN.md` — архив другого агента
- `docs/CONTINUE_TRAINING_RESEARCH_PROMPT.md` — старый промпт продолжения

Датированные evidence в `docs/*202610*` и `docs/*202611*` остаются
доказательствами конкретных срезов.

## Передача следующему агенту

- Когда: 5 ноября 2026, 16:37 МСК.
- Сделано в этом ходе: **R2 продвинут** (не закрыт). Read-only admission binding после controls/toggles:
  gap matrix (7 missing runtime-bundle flags), snapshot `fb44ef14…`, pytest **74 passed**. Receipt
  `.local/state/r2-admission-binding-post-toggles-20261105/r2-admission-binding-post-toggles-report.json`
  (`611b70e66aaed5d0bdbf00e71bd9479181e3f00f6200c00813969b3137fc0d0b`).
- Не закончено: **R2** — live exit-under-pause Sell; runtime-approval rollout (отдельный plan item);
  operational admission binding; **R2 [x]** нет. **R3** operational submit — **R3 [x]** нет.
- Выявленные проблемы:
  - **Открыта:** `--entry-runtime-approval` bundle не на unit (7 prerequisite flags missing).
  - **Открыта:** live Sell under `no_new_entry` не observed; admission не operational на live.
  - **Исправлена (документировано):** post-controls admission matrix vs parser gate — receipt `611b70e6…`.
  - **Исправлена (ранее):** controls toggles live; exit-under-pause код `e2adafa…`; R1 snapshot.
- Не трогать: unit argv без отдельного rollout-пункта; feeder `cycle-1b53f296681044a08dcb2d006e232e68`;
  sealed outcomes до cutoff; controls idle; заявки.
- Следующему взять: **R2** live exit-under-pause (наблюдение при natural exit) или **R3** daily loss at
  submit; R4 не начинать. Файл: `.local/state/live-risk-snapshot.json`, `tests/test_submission_risk.py`.
- Не считать доказанным: **R2 [x]**; admission binding operational; exit-under-pause live; **R3 [x]**; P&L.
