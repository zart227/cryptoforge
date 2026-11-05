# Новое ядро paper-исполнения: causal FIFO и строгий денежный лимит

20 октября 2026 года, Europe/Moscow. [Основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
Это реализация части W5. Новая версия opt-in, без подключения к рабочему
исполнителю, таймерам, модели или действующим evidence roots.

## Изменения

`paper_wallet_v2.PaperWalletV2` использует отдельную SQLite schema с таблицей
`fill_order(sequence INTEGER PRIMARY KEY AUTOINCREMENT, intent_id UNIQUE)`.
Номер добавляется в той же транзакции, что cash/lot/fill/intent transition.
Rollback не оставляет номера без сделки; повтор заполненного intent не списывает
деньги. FIFO и выдача fills идут по этому номеру. Одинаковые UTC timestamps и
лексикографический порядок intent IDs не определяют порядок исполнения.
`PaperWorkerV2` выбирает контекст последней покупки по `fill_sequence`.

`spot_buy_math_v2` выбирает максимальное доступное **целое число шагов** количества
через integer ratios. Base fee уменьшает полученное количество; quote fee входит
в денежный бюджет до округления. Cost обязан быть не больше stake и cash;
отрицательный cash запрещён. Floor sell quantity также не может превышать inventory.
Контекст Decimal вызывающего процесса не определяет число шагов или денежный итог.

Суммы, разности, proceeds и cash сохраняются как точные конечные десятичные числа.
Для частичной продажи доля cost/entry fee округляется вниз до512 decimal places;
**весь остаток остаётся в исходном lot**. Полное закрытие lot переносит весь его
остаток. Это новая фиксированная accounting policy; прежние allocations не
пересчитываются. Проверяется точное равенство в рациональной арифметике:

`cash + remaining_basis == initial_capital + sum(realized_net_pnl)`.

Для прочих промежуточных Decimal checks задан отдельный context precision2048.
Исходные числовые представления sizing/quotes/config ограничены128 digits и
absolute exponent128; внутренние суммы/allocations имеют отдельный cap4096.
Выход за пределы отвергается. Эти caps не являются измерением process RSS или
доказательством вместимости будущего30day journal.

## Buy cutoff и закрытие окна

Worker отменяет все pending Buy при наступлении entry cutoff **до** загрузки
котировок, затем повторяет проверку перед исполнением: market provider может
пересечь cutoff во время ожидания. Кошелёк получает cutoff отдельно и проверяет
свой execution clock **после BEGIN IMMEDIATE**, до любых денежных изменений.
Причина terminal rejection — `paper_entry_window_finished`. Sell остаётся разрешён
в пределах исходного окна; expiry, fresh-market, depth/minimum, stop/daily guards
и учёт dust продолжают действовать.

Сама граница окна остаётся аргументом из будущего frozen capture contract;
низкоуровневый wallet допускает отдельные synthetic tests без cutoff. Нельзя
выдавать вызовы kernel API за зарегистрированный полный study или live admission.

## Версии и предварительная регистрация

`paper_producer_v2.register_kernel(new_root, candidate_sha=..., study_protocol_sha256=...,
role=..., config=PaperConfig(...), worker_policy=..., backend_env=..., start=..., end=...,
closeout_seconds=...)` создаёт только `kernel-contract.json` и `registered.json`.
Оба SHA надо сохранить снаружи. Регистрация завершается до start; late/partial
freeze нельзя принять через `load_kernel`. Реальные запуски используют actual UTC;
clock injection предназначен для synthetic fixtures.

Contract связывает version/runtime hashes, candidate/study/role, config, окно,
cutoff и конкретные runtime/exit fields. Backend должен быть явно `local` через
существующий resolver: `http://127.0.0.1:54321` либо другой допустимый loopback.
Key и произвольные дополнительные поля worker policy не сохраняются. Reader
`load_kernel(...expected_contract_sha256=..., expected_registration_sha256=...)`
работает offline, без resolver, `.env`, API или БД. Это configuration binding;
backend instance/schema/migration/row provenance остаются W6.

Contract теперь связан с созданием wallet/worker через отдельный
[versioned native archive adapter](NATIVE_PAPER_ARCHIVE_V2.md). Архив закрепляет
обе contract pins, original config/окно и новые source groups. Whole-worker
[capture v2](PAPER_WORKER_CAPTURE_V2.md) и
[independent replay v2](PAPER_WORKER_REPLAY_V2.md) реализованы21октября; paired runner ещё открыт; kernel contract
сам по себе не разрешает исследование и не доказывает завершение W5.

Wallet/worker дополнительно сохраняют version/runtime/config/candidate/file identity
в своей state policy. Подмена policy, causal sequence, file path, symlink/hardlink,
потеря runtime state или смена кода отвергаются. Старый и новый wallet/worker не
принимают state друг друга. Frozen kernels и прежние receipts сохранены.

## Проверки и оставшийся W5

- [x] Отдельные versioned wallet/worker/math modules, без изменения frozen kernels.
- [x] Equal-clock reverse-ID FIFO, в том числе после restart, и causal latest Buy.
- [x] Regression stake6/price17/step1e-28: старый sizing тратит больше6;
  новый не превышает budget, cash неотрицателен, следующий Buy не использует капитал повторно.
- [x] Exact fee/base/quote sizing, maximal affordable quantity и независимость
  от caller precision/traps; strict cash/basis/PnL без epsilon на повторных exits.
- [x] Pending Buy cutoff: normal/failing/crossing market, execution guard,
  сохранение Sell closeout, rollback/duplicate atomicity.
- [x] Новый pre-start local kernel contract, external pins/offline reader,
  no-overwrite, late/partial/invalid/runtime/admission/link negatives.
- [x] Перенесены прежние wallet/worker behavior contracts, включая daily loss,
  stale/future quotes, instrument rewind, depth/minimum, dust, source expiry,
  stops/timeouts/shared exit/wall budget и несовместимость state.
- [x] **W5b.1 — новый native archive adapter:** отдельная schema, kernel binding,
  global fill sequence/high-water, protected counter и causal latest-Buy context
  при compaction/restart. [Проверки и границы](NATIVE_PAPER_ARCHIVE_V2.md).
  Всего14 explicit groups: добавлены immutable `fill_order` и mutable `fill_counter`.
- [x] W5b.2: новый capture schema и registration до общего start реализованы21октября.
  [Runbook и проверки](PAPER_WORKER_CAPTURE_V2.md). Связаны kernel contract,
  весь native schema/runtime/Python/dependency receipt, операции отмены и actual UTC **после SQLite lock**.
  Старый fixed-before-action timestamp не подтверждает этот post-lock guard.
  Partial action/tick и unknown completion по-прежнему блокируют resume.
- [x] W5b.3: [независимый replay v2](PAPER_WORKER_REPLAY_V2.md) реализован: exact integer sizing, fixed512-place
  allocation, fill sequence и новые clock/cutoff branches. Старый verifier остаётся
  неизменным и не должен принять старый перерасход/FIFO как корректный результат.
- [x] Проверены adversarial source-consistent rehash fixtures, bounded scratch, compaction,
  crash/late quote/overdue SQLite lock, full row deltas и final original sources.
- [ ] Далее W6/W7 polling/provenance/paired runner, W8 actual capacity/independent
  review и W9 qualified candidate/новое actual study минимум30days/economics gates.

Профильный прогон: **145 passed /18.00s**. Compatibility: **285 passed /363.18s**;
всего430 разных cases, новый общий suite не запускался. Точные команды, final
source/runtime pins и Python/SQLite environment — в `verification.json`.
Receipts: `.local/state/paper-producer-v2-work-20261020/`. Synthetic regression
fixtures и unit checks не доказывают прибыльность стратегии. Во всех kernel
contracts `full_worker_or_host_qualified/paper_evidence_pass/
economic_profitability_established/live_admission_granted=false`.
