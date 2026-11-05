# Потоковый cash/FIFO/valuation replay для capture v4

19 октября 2026, Europe/Moscow. `paper_streaming_replay.py` независимо
пересчитывает кошелёк по [v4 causal ledger](PAPER_CAPTURE_V4.md) и сверяет
исходные строки архива. Native producers и capture v1–v4 не менялись.
Actual future study этим этапом не запускается.

## Регистрация до наблюдений

Replay имеет отдельный immutable contract вне capture root. Его нужно
зарегистрировать после capture registration и **до original start**. Existing
законченный study нельзя приспособить к новому бюджету после просмотра outcomes.
Registration связывает external capture registration/protocol SHA, candidate,
role, исходное окно, runtime verifier/CLI и явный `ReplayPolicy`. Её SHA нужно
сохранить отдельно от источников. Это локальные trusted references, без внешней
подписи или независимого подтверждения времени.

API для будущего runner:

```python
from cryptoforge.paper_streaming_replay import ReplayPolicy, register_replay

receipt = register_replay(
    new_replay_root,
    capture_root=original_capture_root,
    expected_registration_sha256=original_capture_registration_sha,
    policy=reviewed_replay_policy,
)
```

Параметры policy задаются заранее, без автоматического увеличения:

- `maximum_scratch_bytes`:128KiB…1GiB, кратно4096; жёсткий SQLite page cap.
- `maximum_state_rows`: точный предел persistent keys, включая immutable stubs.
- `maximum_active_rows`:16…16384; суммарно open lots, cached filters и day anchors.
- `maximum_active_bytes`:64KiB…16MiB; минимум4×original maximum event frame.
- `maximum_wall_seconds`:1…86400; проверяется после source audit и между frames.
- `minimum_available_memory_bytes` и `minimum_free_disk_bytes`: положительные
  frozen floors; disk floor не меньше максимального scratch. Preregistration
  учитывает также сохранённый capture disk/memory budget.

Это верхние технические границы. Выбор значений требует реальных measurements;
данные синтетических tests не определяют production policy. Wall guard
кооперативный: уже выполняющийся source verifier не прерывается в точную
секунду, но превышение запрещает успешный результат. Host/cgroup/RSS и общий
бюджет трёх ролей остаются отдельной квалификацией.

## Ограниченное состояние и временный индекс

В Python хранятся только cash, open lots, ограниченный market cache, последние
два day anchors, latest mark/latest-known equity, counters и coverage scalars.
Вся история fills, segments или mark clocks в списках не собирается.

Для точных duplicate/old-state проверок создаётся новый private временный
SQLite index вне capture/replay roots. Mutable intent/lot/day rows сохраняются
с исходными значениями; immutable marks/fills/segments — только как key+SHA.
Поэтому проверка старого ID остаётся точной после удаления native active rows.
Индекс ограничен row budget и `max_page_count`; SELECT выполняется по primary
key. SQLite cache задан256KiB. Полный scratch не загружается в память.

Индекс disposable: `journal_mode=MEMORY`, `synchronous=OFF`, продолжения после
сбоя нет. При успехе или исключении он удаляется вместе с созданным приватным
каталогом. Эти настройки относятся только к новому scratch. Source DB/journals
не восстанавливаются и не удаляются; scratch внутри source roots запрещён.
Лимит сериализованного active state не равен process RSS.

## Независимый пересчёт

Сначала проходит v4 source/checkpoint audit. Затем второй bounded pass читает
original causal ledger и независимо строит expected result и **все** изменённые
native rows. Каждый before/after сверяется с indexed state и исходными source
commitments. Native `execute`, `mark`, `spot_acquisition`, `spot_sale` и старые
history-accumulating fill/snapshot auditors не вызываются.

Проверяются:

- Enqueue identity/clock/deduplication, pending/later quote, expiry/cancellation,
  native daily/position/shared-cash guards и причины rejection.
- Order rounding, stake, bid/ask, recorded rules/depth, adverse slippage,
  base entry fee/net quantity, quote exit fee/proceeds и Decimal operation order.
- FIFO по original ordering, basis/entry-fee allocation, все closed segments,
  cash, остатки и закрытые zero lots. Продажа без предшествующей покупки отвергается.
- Original raw market normalization/hashes, liquidation after fees/slippage,
  missing/stale sources, cached filters, UTC daily anchors и overnight carry.

При одинаковом `opened_at` replay сохраняет порядок original completed Buy
из causal ledger. Native SQL `ORDER BY opened_at,id` может расходиться с ним:
такой source-consistent case теперь отвергается, вместо ложного FIFO pass.
Негативный тест сначала воспроизвёл пропуск, затем прошёл после исправления.
Frozen native producer/исторические segments не менялись; causal FIFO
producer/full-worker qualification для будущего study остаётся обязательной.

Дополнительно проверяются purchase cost ≤ frozen stake/available cash и
finite nonnegative cash. Даже native Decimal rounding может нарушить это:
synthetic price17/step1e-28 дал cost6.000000000000000000000000001 при stake6.
Согласованный source trace здесь не достаточен; независимая проверка
отказывает. Budget не расширяется на epsilon, source numbers не исправляются.
Future producer sizing/conservation qualification остаётся открытой.


`replay_liquidation` используется как существующий независимый расчёт по
ограниченному open state; функция producer не вызывается. Значимая непродаваемая
позиция не считается известным временем только потому, что native conditional
mark присвоил ей нулевую ликвидационную стоимость.

## Временное покрытие

`StreamingCoverage` хранит постоянное число counters. Любой prepared завершает
прежнюю оценку; новый mark доступен с completion time. Срок действия определяется
**original** quote/rule receipts и исходным mark-gap policy. Повтор старой quote
и одинаковые timestamps не прибавляют время. Старые interval/mark-clock lists
не используются. Результат сопоставлен с short-study CoverageTimeline, включая
случайные causal sequences и unknown/duplicate events.

Lifecycle pass требует исходный completed terminal, time fraction/gaps/endpoints,
end coverage, проверенный final valuation source, отсутствие material inventory
и pending intents, raw fill sources и соблюдённый operation wall budget.
Early abort, normalized-only final dust mark и missing book не квалифицируются.
Минимальные30дней и общие strategy/role economics этим расчётом не отменяются.

## Read-only команда

```bash
.venv/bin/python scripts/audit_paper_streaming.py \
  --root /absolute/original-v4-study \
  --expected-registration-sha256 ORIGINAL_CAPTURE_REGISTRATION_SHA256 \
  --expected-seal-sha256 ORIGINAL_CAPTURE_SEAL_SHA256 \
  --replay-root /absolute/original-replay-registration \
  --expected-replay-registration-sha256 ORIGINAL_REPLAY_REGISTRATION_SHA256 \
  --scratch-parent /tmp \
  --output /absolute/new-streaming-audit.json
```

CLI использует реальный UTC, без `--as-of`. До original end читаются только
capture protocol/registration; даже replay metadata, rewards и source DB не
открываются. После end обязательны external original pins. Output должен быть
новым и вне обоих source roots. Ошибка возвращает blocked без частичного pass.

## Значение результатов

`full_fifo_replay_pass=true` подтверждает независимый пересчёт wallet transitions
в исходной paper execution model. `coverage_evidence_pass` отражает lifecycle
проверки **исходного** окна и источников. Cash-only без сделок может пройти
математическую проверку и не является заработком.

Всегда `paper_evidence_pass=false`, `economic_profitability_established=false`,
`live_admission_granted=false`, `full_worker_or_host_qualified=false`.
Реальные account fees/fills, full worker opportunity/decision stream, strategy
выбор, paired candidate/control/stress economics и operational admission этим
не сертифицируются. Нельзя выдать этот receipt за full strategy acceptance.

## Чек-лист

- [x] Отдельный pre-start replay contract, original capture/runtime/source pins.
- [x] Hard scratch page/row caps, bounded active cache, private cleanup и no source writes.
- [x] Independent cash/fees/rounding/FIFO/segments/residuals и old-ID checks.
- [x] Independent liquidation/raw sources/day anchors и material-zero unknown time.
- [x] Constant-size coverage с source expiry, completion clocks и endpoint checks.
- [x] Pending/abort/final-source/closeout checks и sealed read-only CLI.
- [x] 65 focused cases passed /36.83s, including self-consistent wrong native rows.
- [x] Synthetic10 005mark core replay:10 009indexed keys, scratch1 216 512bytes,
  active384bytes, Python allocation peak72 208bytes,9.124s. Это не capture/
  real-market/process-RSS/full-worker measurement.
- [x] Итоговый общий non-integration: **1963 passed, 1 deselected /470.87s**.
  Native runtime/capture v1–v4/source-store SHA сохранены; causal FIFO red→green verified.
- [x] Same-clock FIFO сравнивается с causal fill sequence, без сортировки intent IDs.
- [x] Отдельный full tick/source journal реализован: [worker runbook](PAPER_WORKER_CAPTURE.md).
- [x] Independent delivered-worker decisions + wallet/coverage replay нового schema:
  [отдельный local contract и reader](PAPER_WORKER_REPLAY.md); v4 receipts не переиспользуются.
- [ ] Полнота local source polling и paired role runner; отдельно квалифицировать causal FIFO при timestamp ties,
  строгую stake/cash conservation и pending Buy cutoff/closeout producer.
- [ ] Actual source/state/process RSS/wall/network/queue/disk/shared-role/host qualification.
- [ ] Qualified candidate, independent review, новый actual study и economic admission.

Receipts и исходные SHA: `.local/state/paper-streaming-replay-work-20261019/`.
Текущая очередь — в [основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
LLM-направление ведёт другой агент; model/services/risk этим этапом не менялись.
