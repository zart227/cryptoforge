# Metadata-only capacity preflight

27 октября 2026. [Единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[короткий paired runner](PAIRED_CASH_REHEARSAL.md), [ack recovery](CASH_ACK_RECOVERY.md).

## Принятая реализация W8.1

- [x] Original outer/source/delivery/worker/application/replay metadata связаны
  исходными manifest/registration/protocol SHA. Никакие source SQLite, captured
  outcomes, worker groups, `.env` или биржевые/private API не читаются.
- [x] Точные UTC microsecond bounds, end-exclusive source5m slots, role tick
  counts, source/queue/worker/native/application/coordinator event bounds.
  Требуемые counts предполагают полное выполнение всех planned polls/ticks;
  это не наблюдённая полнота данных или будущая прибыль.
- [x] Считаются source versions minimum при full closed coverage без revisions
  и отдельная upper envelope при изменении каждой строки. Required capture events
  используют original WorkerCapturePolicyV2.events_per_tick и segment capacities.
- [x] Проверяются original group limits и hard1024groups v1 schema, source/queue
  quotas, minimum native marks/reports, journal256records, runner20–120s/320s,
  allocated cap/scratch/disk reserve. Memory/RSS/network throughput не выводятся
  из counts; caps и старые approvals не увеличиваются.
- [x] `--require-capacity` даёт exit2 при нехватке counts/byte budgets. Даже pass
  означает только count capacity: `execution_ready=false`, economic/paper/live=false.
- [x]13new+19compatibility=32distinct tests passed /38.28s; cumulative731cases,
  не full suite. Прежние588Python files сохранены;61accepted files/runtime105entries.

## Actual metadata checks

Использована metadata уже завершённого minute rehearsal27октября10:40–10:41UTC.
Его исходные cash/source/capture файлы не менялись.

- [x] Исходное60s окно:12ticks/role,1source poll,240initial versions,
  4source events/88coordinator journal records — count/budget checks pass,
  execution_ready=false. Завершённое окно не разрешено запускать снова.
- [x] Hypothetical30days с тем же UTC offset:518400ticks/role,8641source polls,
  34564source events, minimum17520versions без revisions,3144976journal records.
  Верхняя version envelope2073840 при every-row revisions — не прогноз данных.
  Обнаружены26capacity blockers, require-capacity exit2. Это **не** новый study,
  никакие будущие outcomes не открывались и новый запуск не выполнялся.
- [x] Actual openat trace896paths не содержит source/outcome `.sqlite`,
  `sealed.json`, worker `groups/` или `.env`. Sandbox ptrace отказал, поэтому
  трасса выполнена отдельно с разрешённым tracing собственного read-only child.

## CLI

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/check_cash_capacity.py \
  --reference SAVED-PAIRED-REFERENCE.json --require-capacity --output NEW-REPORT.json
```

Оба `--requested-start`/`--requested-end` задают hypothetical capacity horizon
на основе того же frozen profile. Это не переподписывает original window и не
создаёт нового deployment. Default без require-capacity возвращает report
с blockers; с флагом exit2 позволяет остановить дальнейший shell/job pipeline.
Output обязан быть новым и находиться вне original evidence root.

## Остаток W8.2

- [x] W8.2a: отдельный [indexed cash application v2](CASH_APPLICATION_V2.md)
  сохраняет исходные байты и SHA; обычный шаг проверяет последнюю запись вместо
  всей истории этого слоя. Полный post-end audit и one-completed-step recovery
  реализованы. Старый preflight/runner не получил v2 admission автоматически.
- [x] W8.2b.1: [отдельный incremental source index](REFERENCE_PREFIX_V2.md)
  проверяет только новые events через прежний SourceReplay, сохраняет first-seen
  и проходит full independent audit. Whole-file SHA ещё читается целиком;
  versioned delivery/reader binding и общий long capacity не реализованы этим шагом.
- [x] W8.2b.2a: [cached original-offer reader](CACHED_REFERENCE_READER_V2.md)
  связывает current prefix/role offer и exact event bytes; packets/cash decisions
  совпадают. Actual cash-worker wiring W8.2b.2b ещё не реализован.
- [ ] Source/delivery/native/capture segmented capacity, quota/retention и native
  stream proof для multi-day scope. Research evidence не чистить как operational
  feeder successes. Одного повышения памяти или maxevents недостаточно.
- [ ] Новый pre-start whole-runner recovery contract и проверка полного unknown
  component lifecycle; W7b.3a helper закрывает только known result/ack.
- [ ] Actual positive entry/provider/fill/exit, simultaneous roles under load,
  storage/network/whole-host/restart measurements и independent review.
- [ ] Затем новый preregistered study/candidate/control comparison с original
  selection/economic gates. Short negative-case profile не получает long admission.

Evidence `.local/state/cash-capacity-preflight-work-20261027/verification.json`,
`actual-short.json`, `hypothetical-30days.json`, `metadata-openat.trace` и
`metadata-read-trace-verification.json`. Primary DB/model/risk/trading units/
source collectors не менялись, orders/fit0, original sealed outcomes не читались.
