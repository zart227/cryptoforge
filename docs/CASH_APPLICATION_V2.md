# Индексированный архив квитанций cash application v2

27 октября 2026. [Текущий чек-лист](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[исполнитель v1](CASH_WORKER_APPLICATION.md), [оценка вместимости](CASH_CAPACITY_PREFLIGHT.md).

## Реализованная часть W8.2a

- [x] Новый namespace и schema `indexed-cash-worker-application-v2`. Используется
  прежний `CapturedPaperWorkerV2` и неизменённая функция исполнения v1. Старые
  регистрации, файлы, лимиты и результаты не переводятся в новый формат.
- [x] Завершённая группа из пяти исходных файлов сохраняется в SQLite как
  сжатый поток с точными именами и длинами. До удаления собственной рабочей
  копии проверяются распаковка, совпадение всех байтов и повторное чтение
  committed записи. SHA `worker-result.json`, записанный в queue ack, сохраняется.
- [x] Обычный шаг читает последнюю архивную запись и не более одной текущей
  группы. Предел числа групп, физического размера БД, свободного диска, размера
  распаковки и времени проверки задан до начала окна. Это устраняет полный
  обход JSON-истории **этого слоя**, но не всех нижележащих компонентов.
- [x] После конца собственного окна полный потоковый аудит восстанавливает
  cash decisions, файлы, цепочку групп, worker prepared/completed и ack links.
  Повреждение старой записи обнаруживается именно этим аудитом. Проверка одной
  последней записи во время работы не является проверкой всей старой истории.
- [x] До original end read-only inspection читает только metadata/state head,
  не распаковывает payload и возвращает `performance_hidden=true`. Чтение
  отдельных групп до cutoff заблокировано.
- [x] Explicit recovery допускает только один доказанно завершённый шаг сверх
  известного внешнего checkpoint: до архивации, после commit перед удалением
  рабочей копии или после удаления при потере внешней квитанции. Исполнитель,
  market provider, source poll и queue acknowledgement не запускаются повторно.
- [x] Missing complete/result, неизвестный worker effect, изменённый native head,
  постороннее продвижение очереди этой роли, чужой ancestor, alias и занятый
  writer lease блокируют восстановление. Исходные window/expiry не продлеваются.

## Приёмка

- [x] 19 новых тестов прошли за 97.65s. Ещё 50 неизменённых compatibility cases
  исполнителя v1 и ack recovery прошли в отдельном профиле за 119.59s. В нём
  также были 19 ошибок прежней тестовой fixture: её segment budget не вмещал
  заявленный event budget. Они исправлены и все 19 новых cases затем прошли;
  ошибочные попытки не учитываются как успех. Production limits не ослаблялись.
- [x] Итого 69 разных текущих cases; накопленная проверенная выборка — 750,
  не полный повтор suite. Прежние 591 Python-файл сохранены; новые три дают 594.
  Сохранены 57 source/test copies и 59 runtime keys.
- [x] Настоящий `os._exit(42)` проверен в дочернем процессе в двух точках:
  committed archive перед удалением и удалённая копия перед внешним checkpoint.
  После explicit recovery один завершённый шаг сохранён без повторного worker.
- [x] Отдельная синтетическая репетиция: три роли, 12 applications, шесть
  source decisions, девять heartbeats. Независимые controller/FIFO проверки
  прошли 3/3; проверено 4/0/4 fills, включая синтетические покупки и выходы.
  Queue ack SHA совпадают с исходными распакованными worker receipts.

В этой репетиции raw группы занимали 208631/208178/208602 bytes по ролям,
сжатые payload — 43462/41274/43457, SQLite целиком — 73728/65536/73728.
Рабочих raw групп после завершения нет. Это измерение маленькой синтетической
выборки; коэффициент сжатия и вместимость 30 дней из него не выводятся.

Evidence: `.local/state/cash-application-v2-work-20261027/verification.json`,
`test-coverage.json`, `synthetic-rehearsal-report.json`, исходные SQLite/capture
roots, test logs и accepted source copies. Original sealed train/validation/test
outcomes не читались. Public requests, fits, реальные orders, изменения primary
PostgreSQL, модели, риска и trading services на этом этапе отсутствуют.

## Интерфейс и ограничения

Для нового будущего окна модуль предоставляет `SegmentedCashApplicationV2.create`;
он требует пустую prospective queue, исходный cash contract и ещё не начавший
работу frozen worker. Регистрация должна закончиться до original start.

Внешний checkpoint содержит шесть полей: `root`, `manifest_sha256`,
`registration_sha256`, `sequence`, `head_sha256`, `archive_head_sha256`.
Сохранять весь возвращённый объект; старую квитанцию не заменять новым SHA.
`open` с устаревшим checkpoint блокируется. `recover` — явная операция только
для завершённой группы после остановки выбранного runner; результат содержит
новые application и queue references. Никакого автоматического усыновления нет.

Read-only CLI:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/audit_cash_application_v2.py \
  --reference SAVED-V2-CHECKPOINT.json
```

Default policy: до 2000000 групп, SQLite до 512MiB, исходная группа до 2MiB,
head scan до 15s, полный аудит до 120s, свободный disk reserve минимум 2GiB.
Большой предел количества не доказывает достаточность байтов или скорости.
При исчерпании квоты шаг блокируется до queue offer/worker effect. Лимиты
конкретного worker/source/delivery/capture остаются самостоятельными.

## Следующие незавершённые проверки

- [x] W8.2b.1: [новый incremental source index](REFERENCE_PREFIX_V2.md)
  реализован отдельно; old SourceReplay валидирует новый suffix, first-seen
  сохраняется. Это ещё не wiring в cash/delivery/paired runner.
- [ ] W8.2b: source/delivery/native/capture history и их квоты, потоковый replay,
  полный расчёт диска и измерения под длительной нагрузкой. Прежний W8.1 CLI
  проверяет только прежний paired profile и не выдаёт admission новой схеме.
- [x] W8.2b.2b: [отдельный cached actual paper application v3](CACHED_CASH_APPLICATION_V3.md)
  связывает reader proof с actual worker input/result/ack и сохраняет их в новом
  дочернем v2 archive. Это не меняет прежние v2 schemas или их registrations.
- [ ] Новый pre-start paired coordinator и безопасное восстановление parent
  journal. Старый single-use runner v1 не получил v2 или resume автоматически.
- [ ] W7b.3b: неизвестные/незавершённые side effects и отсутствие durable result.
  Здесь блокируются; v1 ack helper не применяется к v2 без нового контракта.
- [ ] Actual positive/provider/fill/exit integration, whole-host/restart/capacity,
  независимый review и все economic/paper/live/current-model comparison gates.

`full_worker_or_host_qualified`, `paper_evidence_pass`,
`economic_profitability_established`, `live_admission_granted` остаются false.
