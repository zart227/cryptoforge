# Исходники valuation marks для нового paper-исследования

`paper_valuation_capture.py` добавляет отдельный opt-in адаптер
`CapturedPaperWallet` и независимый Decimal replay. Старые `PaperWallet`,
`PaperWorker`, runtime hashes, execution policies и frozen studies не меняются.
Наличие этого механизма не является результатом исследования или допуском.

## Предварительная регистрация

Адаптер создаётся только в **новом, отсутствующем** локальном namespace.
Он записывает candidate SHA, весь `PaperConfig`, будущие start/end, наблюдавшийся
registration clock, source/runtime SHA, Decimal context и event budget.
Старт обязан быть позже регистрации. Existing/legacy директорию, старую wallet
DB или прошлое окно он не принимает. Python API для нового согласованного study:

```python
from cryptoforge.paper_valuation_capture import CapturedPaperWallet
from cryptoforge.paper_lifecycle import PaperLifecycle

wallet = CapturedPaperWallet.create(
    new_namespace,
    candidate_sha=reviewed_artifact_sha,
    config=frozen_paper_config,
    start=future_start,
    end=future_end,
    max_events=10000,
    lifecycle=PaperLifecycle.from_payload(reviewed_lifecycle_payload),
)
protocol_pin = wallet.protocol_sha256
# Сохранить pin вне изменяемой директории исследования до начала окна.
```

При явном `lifecycle` создаётся schema `prospective-paper-valuation-v2`.
Все лимиты обязательны: cadence, operations/slot, оценка bytes/operation,
mark/endpoint gaps, доля известного времени, closeout/grace, wall time одной
операции, storage и минимальные свободные disk/memory. Это новые параметры
протокола, а не изменение боевых рисков или прежних frozen policies.
V1 без lifecycle не получает новый `lifecycle_evidence_pass`; добавить эти
поля в старый файл нельзя. Source drift требует новой preregistration.

Это интерфейс, не зарегистрированный текущий экономический эксперимент.
Нового qualified candidate и действующего трёхролевого paper-study пока нет.
Нужны прежние candidate/controls/acceptance/source/maturity/resource gates;
новый capture protocol не заменяет их и не создаёт дополнительный search budget.

Возобновление: `CapturedPaperWallet.resume(new_namespace,
expected_protocol_sha256=protocol_pin)`. Missing source files, runtime/config/
Decimal drift, иной pin, symlink/hardlink и WAL/sidecars не принимаются.
Нельзя удалять sidecars или переписывать исходники ради прохождения проверки.

## Запись и порядок событий

Перед каждым `mark`/`execute` сохраняется `prepared` с исходным wallet state,
quotes/rules и последовательным номером. После native операции сохраняются
`complete`, её результат и after-state. Hash chain и sequence сохраняют
порядок нескольких fills/marks даже при одном timestamp; сортировка заявок
по имени для восстановления порядка не используется.

При исключении producer либо невозможности записать completion остаётся
незавершённый `prepared`: новые операции/restart блокируются с требованием
review. Автоматического retry, resend, восстановления market sources и
backfill нет. Новое окно нельзя начать стиранием журнала или его budget.

Для v2 перед каждой capture-операцией проверяются исходная in-memory identity,
измеренные свободные memory/disk, storage reserve и число операций в frozen
poll-slot. Overrun фиксируется терминальным событием; restart не открывает
завершённый прогон. Превышение измеренного wall time операции записывается
после её completion и запрещает следующие операции; совершённый paper fill
при этом не теряется из replay.

После `end-closeout_seconds` запрещены новые Buy fills, включая pending
intents, созданные через прежний worker. Paper Sell разрешён до конца окна.
Полный runner ещё должен согласовать closeout lead с poll/delay/market latency;
один локальный guard не гарантирует своевременный выход при missing quotes.

V2 требует `wallet.terminate('completed')` после конца окна, в пределах frozen
grace. До конца разрешён только abort/зафиксированная аварийная остановка.
Ранняя остановка не открывает sealed результаты. Отсутствующий terminal,
abort, material remaining inventory и превышение wall budget не дают
`lifecycle_evidence_pass`. Малый остаток допустим только как доказанный
fresh-source nontradable dust; симулированное исполнение остаётся условным.

`capture.lock` сериализует **локальные** adapter operations. Это не multi-host
fencing и не защита от кода, напрямую открывающего native wallet DB. Обход
адаптера обнаруживается через before/after state, counters и конечную сверку
источников. Старый production worker не переводился на этот адаптер.

Существующий `PaperWorker` совместим с новым wallet adapter; проверка выполнена
на synthetic opportunities. Запуск real study, создание новых timers и
подключение к рабочему entry path остаются отдельными незавершёнными этапами.

## Первичные котировки

`observe_valuation_market(public_client, pair)` вызывает только два прежних
public Spot endpoints через существующий normalizer. Дополнительно сохраняет
**полный instrument response**, которого раньше не было в mark inputs;
orderbook response тоже удерживается целиком. Допустим только точный origin
`https://api.bybit.com`; private/order API не используется.

Проверка raw provenance повторяет нормализацию из сохранённых responses,
сверяет source SHA и совпадение нормализованных prices/depth/rules/clocks.
Одних нормализованных полей без обоих raw responses недостаточно для source
pass. Source presence не доказывает фактическое исполнение по displayed book.
Fees/slippage остаются явно frozen paper assumptions, не account-fee evidence.

Replay независимо считает cash + net liquidation: quantity rounding,
минимальный ордер, maximum market quantity, displayed depth, fee/slippage,
nontradable inventory/dust. Отсутствующие/старые quotes/rules и нехватка depth
сохраняют неизвестную стоимость, а не превращаются в нулевой убыток.
FIFO cash/quantity/basis и native mark/fill payload сверяются с источниками.

## Аудит после конца окна

```bash
.venv/bin/python scripts/audit_paper_valuation.py \
  --root /absolute/new-study-namespace \
  --expected-protocol-sha256 REVIEWED_PROTOCOL_SHA256 \
  --output /absolute/new-report-outside-study.json
```

CLI использует текущие UTC часы, `--as-of` отсутствует. До `end` читает только
protocol/source code и возвращает `sealed_until_capture_end`; reward-bearing
wallet/event DB не открываются. После конца проверяет immutable sources
read-only, всю event chain, inventory/fill/mark replay и исходные raw responses.
Отчёт содержит head SHA и fingerprints файлов; их изменение во время replay
блокирует результат. Output должен быть новым и вне source namespace.

`mark_source_evidence_pass` относится только к полноте recorded mark sources
и воспроизводимости условной оценки. `fill_source_evidence_pass` отдельно
показывает raw provenance совершённых paper fills; отсутствие fills не pass.
`economic_profitability_established=false`, `live_admission_granted=false`
сохраняются всегда. Для v2 audit дополнительно проверяет frozen lifecycle:
**взвешенную по времени** coverage, mark cadence, крайние/внутренние gaps,
terminal и closing inventory. Mark доступен только после completion;
предыдущая оценка прекращает действовать при prepared operation. Срок
известности ограничен ORIGINAL quote/rule receipt, а не новым временем
повторного mark. Дубликаты одного timestamp не увеличивают известное время.
Независимые будущие результаты, активность, общий capital/risk и admission
остаются отдельными gates. Отчёт явно не квалифицирует хост или полный tick
worker: сеть, очередь сигналов, его отдельная DB и cgroup/RSS сюда не входят.

Журнал ограничен10000 событиями и64MiB, один event —256KiB. Место для двух
событий проверяется до producer operation. Это ресурсный предел механизма,
не доказательство пригодности длинного paper-run на конкретном хосте.
Hash chain и сохранённые pins не являются внешней подписью/нотариальным
timestamp: подмена всех локальных файлов вместе с trusted pins вне этой модели.

`PaperLifecycle.capacity_requirements()` показывает потребность до запуска;
`plan()` запрещает freeze, если event/storage budgets недостаточны. При
прежних30днях и poll5s **даже одна роль без сделок** требует1 036 804события
при лимите10 000. Это точный нижний предел event count. Оценка4 246 806 528bytes
при8192bytes/operation — непроверенное предположение о размере, не замер RAM
или disk. Evidence: `.local/state/paper-lifecycle-work-20261018/capacity-lower-bound.json`.
Текущая длинная постановка остаётся BLOCKED. Отдельное
[сегментированное storage](EVIDENCE_SEGMENTS.md) теперь реализовано, но ещё
нужно подключить его к capture v3 и ограничить рост native source DB/полного
replay. Старый v1/v2 cap не увеличен; срок paper/качество не сокращаются.

## Чек-лист R2/R14

- [x] Новый namespace/prospective freeze, code/config/Decimal binding и bounded ledger.
- [x] Original quotes/depth/rules/raw responses, причинный operation sequence.
- [x] Независимый cash/FIFO/liquidation replay, stale/missing coverage и source drift.
- [x] Same-clock fills/marks, restart, failed completion/no retry, opt-in worker compatibility.
- [x] Sealed read-only CLI и запрет перезаписать источники.
- [x] V2 lifecycle contract/future freeze, capacity preflight и runtime capture guards.
- [x] Time-weighted causal coverage, source expiry, cutoff, durable termination/closeout audit.
- [ ] Отдельный реальный preregistered candidate/control/stress study после всех gates.
- [x] Отдельный storage-компонент с bounded segments, общей chain, rotation/recovery и streaming verifier.
- [x] Отдельный [capture v3 adapter](PAPER_CAPTURE_V3.md): segmented source rows,
  original role/registration/terminal и sealed source/operation audit.
- [x] Отдельный [bounded native source engine](NATIVE_PAPER_ARCHIVE.md), с новым
  root/форматом; v1/v2/v3 DB не очищаются и не получают новый source pass.
- [x] [Capture v4 integration](PAPER_CAPTURE_V4.md): original row deltas и archive/checkpoint linkage.
- [x] [Bounded streaming wallet math/valuation/coverage](PAPER_STREAMING_REPLAY.md) реализован отдельно.
- [ ] Full worker/strategy/source capture и economic admission.
- [ ] Полная resource qualification/worker-runner wiring, shared roles и проверка closeout lead.
- [ ] Квалифицированный forward source stream, independent review и экономическая оценка.
- [ ] Full strategy/admission adapter и actual account/operational qualification.

Состояние и выполненные проверки обновляются в
[основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
