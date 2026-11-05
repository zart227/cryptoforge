# Независимый повтор решений worker с локальным backend

20 октября 2026 года, Europe/Moscow. Очередь:
[основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).

`paper_worker_replay.py` проверяет завершённый [worker source journal](PAPER_WORKER_CAPTURE.md)
без вызова исходного `PaperWorker.tick`, native `execute/mark` и providers.
Отдельный controller восстанавливает ожидаемую последовательность решений и I/O;
независимая арифметика кошелька повторно используется из
[streaming wallet verifier](PAPER_STREAMING_REPLAY.md) через новый adapter.
Старые kernels, contracts и SQLite evidence roots не переписываются.

## Локальная база и граница источников

Основная БД проекта теперь — локальные PostgreSQL17/PostgREST:
`CRYPTOFORGE_BACKEND=local`, API `http://127.0.0.1:54321`.
Authenticated read20октября подтверждён отдельным read-only probe с limit=1;
[backend runbook](DATABASE_BACKENDS.md) содержит сведения о выполненной миграции.
Этот этап не повторяет импорт, не меняет таблицы/credentials/services и не
считает старую cloud copy актуальной после новых local writes.

Новая replay registration требует явно загруженный `backend_env` через общий
`resolve_backend`. При выборе cloud либо отсутствии необходимых local credentials
регистрация отклоняется; fallback не выполняется. В contract попадают только
`name=local` и credential-free loopback `api_origin`. API key, пароль и содержимое
`.env` не сохраняются. Backend resolver и imported timestamp parser включены
в verifier runtime SHA вместе с capture/wallet verifier/CLI source files.

Это **configuration binding**, а не доказательство происхождения каждого
prediction из конкретного PostgreSQL volume/schema. Полнота upstream polling,
backend instance/migration snapshot/row provenance и связь трёх ролей остаются
открытыми. Frozen studies сохраняют исходные source/runtime pins; несовместимый
runtime не исправляется переписыванием original registrations или approvals.

Чтение sealed evidence не обращается к `.env`, local API, PostgreSQL либо cloud:
нужны только original journal/native archive и отдельный replay contract.
Owned SQLite evidence и private scratch не являются основной базой приложения.

## Регистрация до начала исследования

`register_worker_replay(new_root, capture_root=..., expected_registration_sha256=...,
policy=ReplayPolicy(...), backend_env=already_loaded_environment, clock=...)`
создаёт отдельный отсутствующий root с одной registration.json. Freeze выполняется
после исходной capture registration, но **до original start**. Contract связывает
capture registration/protocol/candidate/role/window, local backend configuration,
verifier runtime, measured resource floor и scratch/active/wall budgets.

Внешний registration SHA хранится вне обоих roots. Нельзя добавить новый verifier
к уже просмотренному closed study и объявить его заранее зарегистрированным.
Для actual study используются реальные UTC clocks; clock injection — synthetic
fixtures. Ни qualified candidate, ни actual30day study этот этап не создаёт.

Active byte budget должен покрывать восемь исходных bounded frame/projection
размеров. Combined free-disk reservation учитывает исходный capture и scratch.
Это проверка лимитов, не actual process RSS/host qualification.

## Независимый controller и учёт

Controller выдаёт следующий ожидаемый clock/provider request/native action.
Streaming reader обязан сопоставить с ним **следующую** исходную запись;
неожиданная, пропущенная или лишняя операция отвергается. Проверяются:

- candidate/opportunity identity, candidate scope, observation/future/expiry/
  cutoff, candidate rejection, duplicate handling и maximum-new-signals limit;
- UTC и monotonic clock order, market/exit request pair, original response или
  exception class, включая wall-budget skip branches;
- pending source deadlines, Sell-before-Buy ordering, price/time stop/timeout,
  closeout/shared exit, original inventory key и Sell identity;
- worker report, result statuses/errors, atomic intent/link/seen/event mutations;
- cash/fee/rounding/FIFO/fill/segments/liquidation/anchors и все source row deltas.

Исторические seen/link/intent IDs и immutable prediction identity проверяются
через bounded disposable SQLite index. Conflicting source row с тем же identity
между batches/restarts отвергается. Внутри одного batch одинаковые duplicate rows
сохраняют исходную duplicate behavior. Отрицательные opportunities не исчезают.

В отдельной scratch projection находятся только pending intents, с удалением
после terminal transition. Lookup по старому ID не сканирует всю историю.
Immutable wallet history и worker events сохраняют exact key+SHA без payload
повторного использования. Pending/helper/identity rows учитываются общим row cap.
Python хранит только текущий bounded batch, активные lots/filters/context,
quotes/pending/errors/results и скалярные счётчики. Hard page/row caps, active
bytes и runtime memory/disk/wall budgets проверяются; private temporary directory
очищается после успеха и ошибки. Source journals/seals никогда не исправляются.

Time coverage учитывает original source expiry и completion clocks. Native
mark/execute preparation инвалидирует valuation до completion; metadata-only
seen/event/compaction не создаёт новых marks и не обнуляет известное состояние
кошелька. Missing/material/dust/pending/final raw-source и original endpoint
проверки обязательны. Cash-only без сделок может пройти math/coverage и не является
заработком. Stop/timeout и costs вычисляются в обычном коде, без AI API calls.

## Чтение

```sh
.venv/bin/python scripts/audit_paper_worker_replay.py \
  --root /absolute/original-worker-capture \
  --expected-registration-sha256 ORIGINAL_CAPTURE_REGISTRATION_SHA \
  --expected-seal-sha256 ORIGINAL_CAPTURE_SEAL_SHA \
  --replay-root /absolute/original-worker-replay-registration \
  --expected-replay-registration-sha256 ORIGINAL_REPLAY_REGISTRATION_SHA \
  --scratch-parent /tmp \
  --output /absolute/new-worker-replay-report.json
```

CLI использует real UTC и не поддерживает `--as-of`. До original end читает
только capture protocol/registration; source outcomes и даже replay root не
открывает. После end проверяет оба original pins/runtime/source seals. Output
должен быть новым, nonsymlink и вне evidence roots. Ошибка не выдаёт partial pass.

## Значение флагов и чек-лист

`full_worker_decision_replay_pass=true` относится к **переданным batches**,
`full_fifo_replay_pass=true` — к независимому wallet math, а
`coverage_evidence_pass` — к исходному окну/source clocks/closeout checks.
`source_poll_completeness_verified`, `full_worker_or_host_qualified`,
`paper_evidence_pass`, `economic_profitability_established`,
`live_admission_granted` всегда false. Ни реальная комиссия аккаунта, ни
свежесть/полнота всей migrated БД, ни strategy economics этим не квалифицируются.

- [x] Текущий local backend/read availability учтён, без cloud fallback или БД writes.
- [x] W1: отдельный pre-start local replay contract, runtime/source/resource pins.
- [x] W2: hard scratch caps, indexed active/history identities и private cleanup.
- [x] W3: independent delivered-batch decisions/I/O/clocks/exits/report controller.
- [x] W4: независимый wallet/FIFO/valuation/coverage adapter нового worker schema.
- [x] Профильная verification: **47 passed /97.00s**; compatibility **162 passed /178.42s**.
  Всего209 cases в двух непересекающихся наборах; новый общий suite не запускался.
  Final source SHA, logs и source/checklist receipts сохранены.
- [ ] W5: новый producer с causal FIFO, strict sizing/cash conservation и pending Buy cutoff.
- [x] W5a: отдельное [ядро producer v2](PAPER_PRODUCER_V2.md) и pre-start local
  kernel contract реализованы. Прежний producer/verifier сохраняют исходную версию.
- [ ] W5b: bounded archive/capture и independent verifier для новой schema,
  exact512-place allocation, fill sequence и execution clock после SQLite lock.
- [x] W5b.1: [archive v2](NATIVE_PAPER_ARCHIVE_V2.md) соединён с kernel contract,
  сохраняет global order/counter при cleanup/restart. Новый captured replay ещё открыт.
- [ ] W6/W7: backend instance/schema/row provenance, complete paired polling и три роли.
- [ ] W8: actual payload/RSS/tick/network/queue/disk/shared-role/host и independent review.
- [ ] W9: qualified candidate, новая actual registration минимум30days и economics gates.

Известные same-clock FIFO/tiny overspend прежнего native producer сохранены:
этот verifier обязан отклонять неверный учёт, не добавляя epsilon к бюджету.
Исправления находятся в отдельном v2 kernel; его full captured replay ещё открыт.
Отдельные source-consistent forgery tests показывают, что source trace может
пройти при ложном exit response/monotonic branch, а controller replay отказывает.

Receipts: `.local/state/paper-worker-replay-local-work-20261020/`.
LLM-план остаётся у другого агента. Actual orders/fit/model publication/
trading services/risk этим этапом не запускались и не менялись.
