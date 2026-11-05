# Пошаговый source replay index для cash research

27 октября 2026. [Текущий чек-лист](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[исходный ledger](REFERENCE_SOURCE_LEDGER.md), [прежняя delivery](REFERENCE_DELIVERY.md),
[cash archive v2](CASH_APPLICATION_V2.md).

## Завершённая часть W8.2b.1

- [x] Отдельный новый namespace `incremental-reference-prefix-v2` регистрируется
  до original start на пустом prospective source без price-model artifact.
  Сохраняются исходные source manifest/registration и runtime pins.
- [x] Прежний `SourceReplay.feed` остаётся точным валидатором. В обычном update
  он получает только новые оригинальные события после сохранённого source head.
  Полный старый префикс семантически заново не разбирается для каждой роли.
- [x] Исходные event bytes, versions, global first-seen, replay state и последний
  closed input view сохраняются одним SQLite transaction. Новое чтение и повтор
  того же source reference не меняют known_at, sequence или физические bytes.
- [x] Внешние manifest/registration/database/state SHA обязательны. Неизвестный
  commit и устаревший checkpoint блокируются. Лимиты новых событий, snapshot,
  БД, времени и свободного диска проверяются до/внутри bounded update.
- [x] Полный независимый replay сравнивает всю сохранённую цепочку, snapshot,
  source view и обе projection tables. Нового физического SHA недостаточно,
  чтобы выдать повреждённую projection за семантически правильную.
- [x] Незавершённый source poll, чужой namespace, выход за original window,
  backward clock, alias, busy lease и превышение квот не принимаются.
  Неизвестное состояние не «доделывается» автоматически.

**Это частичный шаг к W8.2b.** Проверки физического SHA всё ещё читают обе БД
целиком; компонент не обеспечивает постоянную стоимость шага при любой длине
истории. Он не меняет прежние SourceLedger/ReferenceDelivery или paired runner,
не выдаёт forecasts, не выполняет worker и не закрывает host/capacity admission.

## Проверки

- [x] 18 новых + 100 неизменённых source/delivery compatibility cases:
  **118 passed / 17.99s**. Накопленная проверенная выборка — 768 разных cases;
  полный suite заново не запускался. Прежние 594 Python-файла сохранены,
  теперь 597; сохранены 19 source/test copies и 16 runtime keys.
- [x] Настоящий process exit42 после commit до внешнего checkpoint оставляет
  прежний reference заблокированным. Файлы сохраняются; recovery такого случая
  ещё не реализован и остаётся W7b.3b.
- [x] В отдельной синтетической репетиции было шесть попыток poll: четыре
  завершённых poll, два BTC rate-limit ответа и две паузы по original cooldown.
  В индекс поступило `[4,4,4,0,4,0]` новых событий, всего 16, каждое один раз.
  Повторное чтение во время паузы не создало новые события или свежий known_at.
- [x] Все 12 source packets, доставленных candidate/control/stress, совпали
  с cached view и прежним полным replay. Полный аудит нового индекса прошёл.
  Это input-only acknowledgements, **не** actual worker-result receipts.
- [x] Index SQLite в этой выборке — 737280 bytes, исходная source SQLite —
  151552. Индекс дублирует данные и требует отдельного disk budget; экономия
  места или throughput долгого окна из этой репетиции не следуют.

Первый rehearsal ошибочно ожидал новый poll во время cooldown и остановился на
assertion. Его namespace/script сохранены; следующая версия проверяет соблюдение
паузы. Ограничение API не обходилось и collector clocks не переписывались.

## Интерфейс

`ReferencePrefixV2.create` принимает новый root, исходный пустой prospective
source reference и typed policy. `ingest` принимает новый current source reference;
`view` возвращает сохранённый closed input view и оба references. Внешний
checkpoint состоит из `root`, `manifest_sha256`, `registration_sha256`,
`database_sha256`, `head_sha256`. Сохранять все поля, не усыновлять неизвестный
новый физический pin после сбоя.

Default policy: БД до 512MiB, максимум 64 новых события за update, snapshot до
1MiB, update до 30s, полный аудит до 120s, свободный disk reserve минимум 2GiB.
Время ограничивается проверками внутри кода; прерывание зависшего I/O и общий
process/host boundary требуют нового runner и остаются отдельной задачей.
Никакой research retention или удаления исходных событий здесь нет.

Read-only audit CLI использует новый scratch вне namespace:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/audit_reference_prefix_v2.py \
  --reference SAVED-PREFIX-CHECKPOINT.json --scratch-parent EXISTING-SCRATCH-DIRECTORY
```

## Оставшиеся условия

- [x] W8.2b.2a: [отдельный cached reader](CACHED_REFERENCE_READER_V2.md)
  связывает view с original pending offers/cursors/batch и exact source bytes.
  Packets/cash decisions равны прежнему reader; stale/backlog blocked.
- [ ] W8.2b.2b: versioned actual cash-worker application с reader proof и safe
  actual result ack. Прежние app/runner не получили новый reader автоматически;
  `type(queue)` guards не ослаблять для незарегистрированного адаптера.
- [ ] Segmented source/index history, bounded physical SHA/replay, byte/record/
  shard/capture limits и измерения для длинного окна. Число групп само по себе
  не доказывает способность сохранить или воспроизвести все данные.
- [ ] Новый paired coordinator, interrupted parent/component recovery и chosen
  host restart; actual positive/provider/fill/exit и независимый review.
- [ ] Все original selection, current-model, economic/paper/live/VP/W9 gates.

Evidence `.local/state/reference-prefix-v2-work-20261027/verification.json`,
`test-coverage.json`, `synthetic-rehearsal-report.json`, оба rehearsal namespaces,
CLI receipts и accepted sources. Public network, actual worker, PostgreSQL writes,
model/risk/trading changes, fits и реальные orders отсутствуют. Original sealed
outcomes не читались. Все общие admission flags false.
