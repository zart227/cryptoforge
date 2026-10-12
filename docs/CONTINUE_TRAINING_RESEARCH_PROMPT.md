# Промпт продолжения CryptoForge

Скопируй текст ниже в чат, открытый в проекте `/home/arthur/Projects/personal/CryptoForge`.

---

Продолжи работу над обучением и проверкой торгового бота CryptoForge. Главный документ — `docs/PROFITABLE_STRATEGY_RESEARCH_PLAN.md`, актуализация12октября2026, технические детали — `docs/FREQAI.md`. Цель: воспроизводимый поиск торговых ситуаций и обучение с проверкой результата после всех расходов; кандидат допускается только по доказательствам. Не обещай увеличение прибыли после каждого обучения.

Сначала прочитай актуальный раздел плана, применимые AGENTS.md/skills и текущие файлы. Не начинай реализацию заново. Git checkout сильно изменён, часть файлов менялась другим чатом: сохраняй чужую работу, не выполняй reset/cleanup/commit/push без соответствующего запроса. Последняя подтверждённая полная проверка в этом чате —880passed 11октября; сегодня это историческая отметка, а не новый запуск.

Что уже сделано и не надо повторно реализовывать:

- Архив Bybit Spot, dataset/source checksums, causal labels, purged chronological splits, simulator общего wallet с затратами, общий buy/sell/price-time core.
- Source-bound snapshots и original runtime bundles, immutable ResearchAttempts ledger, persistent configuration budgets, numerical audits, atomic private reports.
- Четыре train-window/recency variants, семь ablation variants и их portfolio comparisons, два balanced/unweighted classifiers. Все эти completed studies — ранее просмотренные development-данные.
- Economic screening13portfolio configs:0passes. Cash без сделок не назван заработком. Balanced classifier:36trades,net−0.759012651USDT/stress−1.400583590 приcapital100; без balancing0trades. Это simulation, не фактический доход аккаунта.
- Ablation безvolume_ratio немного улучшил RMSE, но все7portfolio variants сделали0trades. Признаки рабочей модели не удалялись.
- Явные price/net/cash target contracts; registry guards; новые primary artifacts объявляют fixed-future-return-v1. Cash/short labels нельзя выдавать за primary Spot-long price task.
- Append-only closed bounded120 feature stream и actual BTC/ETH parity audit:2556vectors/2562bounded signals совпали. Полная live execution parity не подтверждена.
- Readonly working-bot feedback, real execution/cash recovery memory, prospective forecast memory/outcomes, entry diagnostics поpair, ограничения freshness/source quality и paper harness.

Важные ограничения и состояние, которое нужно заново проверить:

- При последней сверке legacy cash training8buys:1positive/7negative; закрытый bounded120 study отделён и раньше имел0buys. Не смешивай их и не считай forecasts/simulated trades реальными покупками.
- Active legacy модель была устаревшей и имела неизвестный feature calculation contract. Новые closed bounded120 candidates не заменяли её: insufficient_signals и incompatible_feature_calculation_contract. Не восстанавливай неизвестный контракт по имени или догадке.
- Последний проверенный candidate041b283bc8/sha01d88cd66354268a92adb9663a428e27b720c9e745d94613e4f6b9f8a0517a20 прошёл original input/metrics/source audit;11novel signals на420examples недостаточны для допуска. Estimated fixed-candle returns не являются executed income.
- Статусы моделей/таймеров/числа сделок устаревают: прочитай свежие отчёты и журналы, не объявляй эти числа текущими без проверки.
- В ходе работы менялись kernels и primary producer metadata. Old frozen source fingerprints нельзя переписывать. Некоторые старые strict replay checks теперь должны отказать из-заsource drift; historical results/original bundles сохраняются. Source-difference audit возможен только с явным указанием ограничения, без автоматического исполнения archived code.
- Completed ablation retry timer отключён после7/7fits и portfolio completion. Основные training/feedback timers при последней проверке enabled. Не возобновляй завершённый поиск как новую попытку без причины.

Порядок оставшейся работы:

1. Проверь текущее состояние основного обучения, active/candidate artifacts, freshness, input/target contracts, source admission и причины недопуска. Разделяй отсутствие стратегии, no_fresh_model, dust/minimum constraints, нехватку наблюдений и отрицательный payoff.
2. Подготовь конкретный отдельный протокол feature-contract migration к closed bounded120. Для неизвестного legacy контракта нужна независимая prospective candidate/control проверка; нельзя просто присвоить старой модели новые metadata или убрать comparison guard. Реализуй выполнимые части и preflight без live замены.
3. Закрой execution/source gaps: point-in-time universe/rules/fees/spread/depth, partial/rejected fills, exit minimums, base/other sale fees, residual ownership и basis. Проверь вручную минимум20source-bound labels с gaps, ambiguous stop/target и fee/boundary cases. Unknown не заменяй сегодняшними правилами или оптимистичным fill.
4. Выполни только заранее зарегистрированные исследования стратегии: реальная baseline без ML, frozen current-model control, cash-only и явно заданный buy-and-hold context при одинаковом капитале/риске. ATR/filters/support-bounce/compression families допускаются после observed protocol/source freeze и budget reservation. Не выбирай новые параметры по старому test/paper.
5. Threshold выбирай на validation по shared-wallet net/stress payoff, minimum ordinary/stress trades и drawdown, с полной declared grid и immutable report verification. Уточни natural-distribution calibration на достаточных периодах. Не превращай class-weighted score в доказанную вероятность.
6. Реализуй и квалифицируй walk-forward процедуру целиком: calendar windows, nonoverlapping test, purge поlabel_end_time/availability, embargo, train-only preprocessing, all previous information cutoff, paired temporal block bootstrap общего wallet, budget/multiple-search accounting и concentration checks. Viewed development не становится blind test при новом названии файла.
7. После квалификации создай новую observed paper execution/source policy и проведи candidate/control forward stream с полными receipts, fills/rejections/exits/fees/net equity. Сверь replay того же будущего периода. Продли наблюдение при нехватке дней/сделок. Численные требования бери из соответствующего frozen protocol: общий30day/100trade paper и closed-cash14day/60trade acceptance нельзя смешивать.
8. Подготовь concrete reviewable admission/rollback/monitoring результат. Live замена требует выполненных gates и соответствующего разрешения; не публикуй неподтверждённую модель ради свежести или сбора100buys.

Как работать:

- Сохраняй действующие stake/positions/daily-loss/stop/TTL/ML gates. Не включай новые реальные ордера и не обходи quality/freshness/source guards для ускорения результатов.
- Перед actual research: RAM≥1536MiB,disk≥2048MiB, один offline worker, исходные wall/memory/flock limits. Не понижай floors. Deferred значит не выполнено; изучи другой независимый пункт, который можно сделать без этого запуска.
- До outcomes/fitting зафиксируй source/config/data hashes, параметры, дату наблюдаемого freeze, budget/grid и затем registration. Не расширяй старый frozen budget после просмотра результатов.
- Сохраняй immutable original inputs/runtime/results, Python/dependency/commit/dirty/seed/cutoff receipts; не создавай provenance задним числом. Seed=None допустим для явно deterministic fit.
- Разделяй implementation, actual development evidence, independent qualification и live admission. `[x]` ставь только за реально выполненную проверку. Не закрывай весь этап по unit tests или одному25-hour срезу.
- После изменения запускай уместные проверки; полный suite после существенного набора изменений, не повторяй его без причины. Для synthetic test files можно использовать `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp /dev/shm/cryptoforge-<unique>`. Это не обход actual research guards.
- Обновляй план и checklist после каждого проверенного результата: точные commands, source/protocol/study IDs, числа, риски/ограничения и следующий незавершённый пункт. Исторические записи не переписывай как текущие.
- Продолжай полезную работу по выполнимым пунктам, не заканчивай ход после каждого небольшого блока. Не расходуй лимит на повторные бессодержательные проверки, пустые рассуждения и искусственный перебор. Если требуются будущие данные/внешнее состояние, честно зафиксируй этот конкретный blocker, не имитируй completion; переходи к другой выполнимой работе.
- Не говори «всё выполнено» или «лимиты исчерпаны», если это не подтверждено. Не обещай автономное продолжение, которого реально не настроено.

В итоговом отчёте укажи: что реально закрыто, чем проверено, какие gates остаются и почему, какие файлы/протоколы созданы или изменены, менялись ли active model/live orders. Ссылка на актуальный план обязательна. Отсутствие прибыльного кандидата — допустимый научный результат, а не повод снять защиту.
