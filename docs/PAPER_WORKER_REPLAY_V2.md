# Независимая проверка paper-worker v2

21 октября 2026 года, Europe/Moscow. [Основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
Этап W5b.3 после [capture v2](PAPER_WORKER_CAPTURE_V2.md). Существующие kernels,
archive/capture/replay contracts и receipts сохраняются. Этот verifier читает
original sealed files и создаёт только отдельный private scratch SQLite.
Рабочий PostgreSQL/PostgREST не читается и не изменяется; LLM-план ведёт другой агент.

## Контракт до original start

`paper_worker_replay_v2.register_worker_replay(...)` принимает original capture
root/registration SHA, отдельный новый replay root, typed `ReplayPolicyV2` и
явно выбранный local backend. Replay `source_backend` должен точно совпасть с
credential-free kernel identity: name и loopback API origin. Это configuration
binding; instance/schema/migration/known_at provenance остаётся W6.

Контракт закрепляет capture registration/protocol, обе kernel pins, native
manifest/ready, candidate/role/window, resource floors, все capture/verifier
runtime hashes и independent arithmetic contract: precision2048, integer-ratio
sizing,512-place basis allocation. Ключ API не сохраняется. Проверки actual UTC
до и после durable registration запрещают late/partial adoption. Existing root
не переиспользуется. Внешний replay registration SHA нужен при чтении.

```python
registered = register_worker_replay(
    new_replay_root,
    capture_root=original_capture_root,
    expected_registration_sha256=original_capture_registration_sha,
    policy=ReplayPolicyV2(...),
    backend_env=explicit_local_backend_env,
)
```

Применять эту регистрацию к уже наблюдавшимся actual outcomes нельзя. Clock
injection используется только для synthetic fixtures; реальные API/CLI используют
actual UTC. Старый replay/schema не принимает source v2, и наоборот.

## Три части независимого пересчёта

`paper_replay_math_v2.py` импортирует только стандартные contextlib/decimal/fractions.
Число доступных quantity steps выбирается целочисленным делением точных отношений.
Проверяются maximal affordable quantity, stake/cash bounds и явная base/quote fee.
Finite Decimal строится отдельным integer long-division алгоритмом, без вызовов
producer helpers. Partial basis/entry-fee allocation округляется вниз к512 знакам;
полная продажа lot забирает весь остаток. После каждой операции строго проверяется
`cash + remaining basis = original capital + allocated realized PnL`, без epsilon.
Private Decimal context защищает proof от precision/traps вызывающего кода.

`paper_wallet_replay_v2.py` пересчитывает 14 source groups, filters/day anchors,
cash, fees, lots, marks, fills и closed segments. Порядок FIFO задаётся causal
fill sequence, а не ID или timestamp. Каждый fill добавляет следующий original
fill_order и обновляет mutable counter. Начальные policy identities строятся из
original contract; финансовые методы producer не вызываются.

`paper_worker_replay_v2.py` отдельно формулирует следующую ожидаемую операцию
controller как coroutine: clocks, monotonic observations, market/exit requests,
enqueue/seen/cancel/execute/mark/event и итоговый report. Проверяются negative
predictions, immutable opportunity across batches, expiry, signal/position caps,
pending Buy cancellation, exits по времени/цене/shared indicator и wall branches.
Соответствующее native решение не используется как правильный ответ.

## Native clocks и атомарность

Подготовка действия не является его execution clock. Отдельные clock records
с action parent собираются в source order. Financial replay потребляет каждый
clock по смыслу операции: первый execute clock после write lock, второй reject
clock для observed_at, clock mark/cancel/enqueue/seen/event. Недостающий или
лишний clock отвергается, даже если narrow source trace принимает структурно
согласованный журнал. Дублирующий no-effect archive/active path может иметь
ноль или одно чтение времени; запись новой строки всегда требует original clock.

Результат, полный ordered row delta и source commitments сравниваются с
независимым состоянием после каждой операции. Compaction не меняет logical
history. Проверки охватывают cold replay после producer restart и сохранение
counter при tradable closeout с retained dust. History хранится в indexed scratch;
immutable fills/order/events сохраняют IDs и hashes без бесконечного payload cache.

## Original window и endpoint

Actual post-end endpoint не переименовывается в original end. Он получает
отдельные `final_equity_observed_at` и `final_valuation_after_window`.
`endpoint_observations_backfill_window=false`.

Последний mark, **доступный до end**, учитывается отдельно от endpoint. Coverage
не получает known seconds из будущего mark. Original-window dust/material
classification также не заменяется будущей ценой: падение цены после end не может
скрыть material inventory, которое не было закрыто в original window.
В output эти источники различаются через `last_in_window_equity` и его observed_at.
Даже known final endpoint не создаёт original-window valuation при её отсутствии.

## Ограничения ресурсов и чтение

Typed policy задаёт максимум scratch bytes/pages, indexed rows, active rows/bytes,
wall time и memory/free disk floors. Combined original capture/replay floors
проверяются при регистрации и чтении. Scratch создаётся в новом private temporary
namespace вне source/replay roots и удаляется при штатном завершении или перехваченном исключении. Source files
не исправляются, не копируются обратно и не переигрываются через native writer.
После process death прежний scratch не принимается; следующий запуск создаёт
новый индекс. Очистка orphan directories и actual disk capacity относятся к W8.

Source audit также проверяет бюджет между bounded records/rows, затем independent
pass проверяет его на каждом event. Для этого используются private function globals
и reader subclasses; process-global capture/storage bindings не меняются.
Отдельные bounded SQLite/file reads не становятся real-time preemption; превышение
бюджета после их возврата блокирует результат. Actual host/RSS/network/three-role
capacity остаётся W8.

CLI `scripts/audit_paper_worker_replay_v2.py` принимает original capture/replay
roots и external registration/seal pins, optional private scratch parent и новый
output вне evidence. `--as-of` отсутствует. До original end возвращается только
sealed status, без source outcomes/scratch. Output не перезаписывается.

## Что означает результат

`full_worker_decision_replay_pass` и `full_fifo_replay_pass` подтверждают доставленные
batches и финансовые переходы по registered rules. `coverage_evidence_pass` требует
отдельных lifecycle checks, original known-time coverage, raw sources, closeout и
whole-tick wall budgets. Zero-trade/cash-only trace может быть вычислительно
корректным; это не прибыльный кандидат.

Source poll completeness, backend instance provenance, host qualification,
paper/economic/live admission остаются false/открытыми. Неизвестные действия и
partial source seal нельзя принять для replay. Без нового actual preregistration,
полного upstream polling/paired runner и экономических gates study не запускается.

## Acceptance checklist

- [x] Отдельный pre-start local contract, original kernel/archive/capture pins,
  arithmetic/runtime binding и late/partial/no-overwrite guards.
- [x] Независимые integer sizing, quote/base fees, causal FIFO,512-place allocation,
  strict cash/basis/PnL и original14-group row deltas.
- [x] Ordered native clocks и отдельный controller, negative/source/exit/cutoff paths.
- [x] Source-consistent wrong fees/quantity/allocation и лишние/пропущенные native
  clocks отвергаются независимо от narrow source trace.
- [x] Итоговая проверка: **753 разных cases прошли:** 115 passed /388.36s + overnight UTC 1 passed /13.43s; compatibility 637 passed /953.93s. Общий suite заново не запускался.
  Проверены overnight UTC anchor carry, exact PnL, equal-clock reverse-ID FIFO,
  source-consistent math/clock forgeries, window lookahead и namespace isolation.
- [x] Прежние539source/test files и original804checkbox/body сохранены;
  final code/runtime/documentation pins и original synthetic sources оставлены в receipts.
- [ ] W6: local instance/schema/migration/known_at и original upstream row provenance.
- [ ] W7: full shared polling/negative/skip/failure delivery, paired candidate/control/stress runner.
- [ ] W8/W9: actual whole-worker capacity/review, qualified candidate и новое
  actual study минимум30days с economic gates.

Receipts: `.local/state/paper-worker-replay-v2-work-20261021/`.
