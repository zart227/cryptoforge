# Текущий W8.2a статус27октября

[Cash application v2](CASH_APPLICATION_V2.md) реализован отдельно: индексированный
архив точных исходных квитанций, bounded head checks, post-end полный аудит,
explicit recovery completed шага без повторного worker.19new+50compat=69distinct,
cumulative750; synthetic independent replay3/3. Старые v1 namespace и runner не
переводились в v2. Source/delivery/native/capture/long coordinator и общий admission
остаются открытыми. Ниже прежние датированные v1 scopes.

# Текущий recovery статус27октября

[Explicit known-result ack recovery](CASH_ACK_RECOVERY.md) реализован отдельно:
если original durable worker-result и полный source/worker proof сохранены,
недостающий ack/complete можно закончить без повторного tick. Unknown worker
completion/missingresult всё ещё blocked; whole-runner resume не реализован.
17new+33compat=50distinct/cumulative718. Ниже previous adapter scopes.

# Текущий статус27октября: short paired runner проверен actual

[Новый bounded runner](PAIRED_CASH_REHEARSAL.md) реализован и прошёл actual minute
10:40–10:41UTC:12ticks×3,6decisions/33heartbeats,0fills, independent replay3/3,
peak≈33MiB under512MiB cgroup cap. Actual negative run не проверил положительные
quote/fill/exit branches. Single-use20–120s профиль не multi-day daemon;
длительный runner/recovery/host/positive qualification остаются открытыми.
Ниже исходная приёмка W7b.2a/b и её ограничения.

# Cash-entry contracts и квитанции paper worker

27 октября 2026. [Текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[source delivery](REFERENCE_DELIVERY.md), [coordinator](REFERENCE_COORDINATOR.md),
[frozen worker](PAPER_WORKER_CAPTURE_V2.md).

## Реализовано и проверено

- [x] W7b.2a: отдельный pre-start cash contract на новую пустую prospective queue,
  fixed pairs/window/cutoff, три разных strategy SHA и exact rational arithmetic.
  Source не содержит price artifact; price probability не становится `would_enter`.
- [x] Candidate — явно заданная исследовательская гипотеза `momentum_breakout_v1`:
  past return ≥ cost floor+buffer, закрытие выше прежних highs, volume/range guards.
  Это фильтр прошлого движения, не оценка будущего net return.
  Control — `cash_only`, **не legacy active model**. Stress имеет ту же гипотезу
  и параметры, кроме role/cost floor. Никакого default live strategy нет.
- [x] W7b.2b: по каждому полному poll сохраняются решения для всех fixed pairs,
  включая negative/source failure/expired/gap/cutoff skips. Только один whole poll
  в source batch; packet со второй poll/forecast/пропущенной парой отвергается.
- [x] Передача в фактический класс CapturedPaperWorkerV2 с проверкой frozen role,
  candidate/study/window/cutoff, assumed fee/slippage floor и исходного worker head.
  Retained inputs, реальный prepared event и completed worker result связаны SHA.
  Очередь подтверждается SHA durable worker-result, после его сохранения.
- [x] Пустые heartbeat ticks поддерживают worker cadence между source polls:
  pending fills/marks/exits продолжаются. Они не создают opportunities и не
  подтверждают несуществующий source batch. Реальные public providers передаются
  вызывающим runner; тестовые providers не объявляются рыночным evidence.
- [x] Exact external checkpoint, append-only bounded groups, fsync parent перед
  worker effects, original runtime/registration checks, read-only re-derivation
  решений и linkage audit. In-memory mutation и чужой worker tick блокируются.
- [x] Unknown operation, real process exit после worker commit и потерянный ack
  сохраняют incomplete group и блокируют автоматический повтор. Recovery ещё открыт.
- [x]33tests текущего кода passed /100.55s;249 compatibility cases прошли в
  предыдущем278case run. Его29cases прежней cash-ревизии исключены из приёмки.
  Итого282разных текущих cases; с предыдущими профилями —682distinct, не full suite.
  Прежние578Python files сохранены; новые2modules+CLI+test дают582.
- [x] Отдельная **синтетическая** проверка:3roles/12applications/6source opportunities/
  9heartbeats. Original capture audit и independent controller/FIFO replay прошли
  для всех ролей; fills4/0/4 в искусственном buy→stop→sell сценарии. Это не actual
  market study, не историческая прибыль и не qualified paper result.

## Использование

`cash_entry_contract.py` предоставляет `CashEntryRule`, `freeze_cash_contract`,
`load_cash_contract` и pure `evaluate_cash_packet`. Гипотезы и bounds задаются явно;
гиперпараметры не подбираются на sealed outcomes этим модулем.

Порядок для **нового** study:

1. Создать новый prospective ReferenceLedger без artifact и ReferenceDelivery
   до будущего start. `maximum_source_events_per_batch=len(fixed_pairs)+2`.
2. До start заморозить три cash rules, closeout и decision latency≤30s.
3. Зарегистрировать отдельные kernels с candidate SHA соответствующей cash rule
   и study SHA cash contract; config/cost assumptions и exits задаются отдельно.
   Legacy active09b486e979/candidatea252/migration041b этим не подменяются.
4. Создать CapturedPaperWorkerV2 и CashWorkerApplication каждой роли до start;
   заранее зарегистрировать independent replay. Сохранить все original references.
5. В окне source runner сохраняет новые public polls и ingests. Каждые worker5s
   вызвать `application.apply(queue, worker)`, в том числе при пустой queue.
   Сохранять возвращённый application checkpoint и queue reference после commit.
6. Завершить source/entry/endpoint/closeout по original contracts и отдельно
   провести source/worker/economic acceptance. Библиотека не запускает этот runner.

CLI `scripts/cash_reference_application.py`:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/cash_reference_application.py --help
```

`freeze-contract --root NEW --queue-reference FILE --rules FILE
--closeout-seconds N` записывает только новый owned research contract.
`inspect-contract --reference FILE` и `audit-application --reference FILE`
читают original pinned metadata/receipts. `.env`, ключи, production trades,
обучающие outcome stores и сеть этими командами не читаются.
Автоматического запуска, market-provider wiring или model publication у CLI нет.

## Bounds и остаток

Application policy:128groups/256MiB total/16MiB per group, scan15s, disk reserve
2GiB+group. History не удаляется. Это bounded rehearsal profile, **не достаточная
ёмкость многодневного study**; длительность/capacity регистрировать отдельно W8.
Два файла protocol/registration и original source/worker runtimes не переписываются.
После incomplete group нельзя очищать journal/worker state, усыновлять старые SHA
или повторять tick: сохранить исходные bytes и разбирать в W7b.3.

- [ ] W7b.2c: новый bounded paired runner/public provider+source polling+5s ticks,
  actual prospective rehearsal, monitors/checkpoint persistence/finalization.
- [ ] Проверить весь opportunity stream на выбранном deployment, pending/failed
  sources, role cadence и независимые source/worker replay по actual данным.
  Прежний diagnostic coordinator остаётся source-only/input-ack.
- [ ] Native/current-model/new-head/cash comparisons и полный preregistered
  selection protocol. Cash-only control не заменяет current-model comparison.
- [ ] W7b.3/W8 recovery/host/capacity/review, W9 future evidence/economic gates.

Evidence: `.local/state/cash-worker-application-work-20261027/verification.json`,
53accepted source/test copies, test IDs/logs, original synthetic captures/seals/
replay registrations и `synthetic-rehearsal-report.json`. Frozen original outcome
окна до7ноября/21ноября и first blind WF15ноября не открывались. Fit/model/risk/
trading services/real orders этим кодом не менялись. Profitability/paper/live=false.

## Сборщик на27октября

[Managed feeder](MANAGED_REFERENCE_FEEDER.md) при recheck10:15UTC active/waiting,
latest service success10:14:52UTC. Валидированы313retained completed success cycles,
0retained failures,302095396bytes и238prune receipts. Это сохранённая часть operational
истории с26октября22:22UTC, не доказательство непрерывности всех20h.
BTC120SQL/REST/SQL10:16:09UTC fresh(age69.866558s); primary instance/schema те же.
Продолжается bounded retention, не whole-host/outage qualification.

27октября10:50UTC separate public instrument/book probe BTC/ETH прошёл2/2 с
original raw payloads и normalization replay. Это acquisition-only; новые
opportunities/fills не создавались. [Provider receipt](PAIRED_CASH_REHEARSAL.md#дополнительный-actual-provider-probe27октября).
