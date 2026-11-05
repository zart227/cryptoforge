# Текущая capacity проверка27октября

[Metadata-only preflight](CASH_CAPACITY_PREFLIGHT.md) проверяет original quotas и
hypothetical horizons без SQLite/outcomes. Current60s counts fit,30days даёт26
blockers; short runner не стал долгим daemon.13new+19compat=32distinct,
cumulative731cases. Следующий W8.2 — scalable journal/checkpoints/longscope;
recovery/positive/host иeconomic qualification остаются открытыми.
Ниже предыдущие actual runner/provider results и точные границы.

# Текущий recovery scope27октября

[Component known-result ack recovery](CASH_ACK_RECOVERY.md) готов; original runner
остаётся single-use. Он не усыновляет pending parent operation автоматически.
Результат minute и последующий provider-only probe сохранены без изменения.
Ниже original runner acceptance и открытые positive/long/host gates.

# Bounded paired cash rehearsal

27 октября 2026. [Единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[cash contracts/application receipts](CASH_WORKER_APPLICATION.md).

## Реализовано

- [x] W7b.2c.1: один prospective runner объединяет отдельный source ledger,
  one-poll delivery, cash contracts,3frozen kernels/captures/applications и3
  заранее зарегистрированных independent replays. Стратегии/fees/exits задаются
  явно до start. Primary — local backend metadata, actual source — public BTC/ETH.
- [x] 5m source polling и5s worker slots, heartbeats между polls, journal
  prepared/completed вокруг каждой операции, external component descriptors,
  endpoint/terminal/seal и independent replay после конца собственного окна.
- [x] Single-use namespace: started/incomplete/terminal root не запускается снова.
  Unknown operation не усыновляется. Scope20–120s, attach до start, lead≤60s,
  whole run≤320s, journal≤256records. Это короткая репетиция, не multi-day daemon.
- [x] Bounded public instrument/book GET only BTC/ETH Spot; no auth/order paths,
  no redirects, body64KiB, killable child1s/output128KiB. HTTP403/429 и
  retCode10006/10429 дают10min pause в provider. Candles используют отдельный
  existing bounded reference client/ledger cooldown. Глобальный другой host
  или произвольный другой client этим limiter не покрываются.
- [x] Original cash/worker/runtime files сохранены. Низкий ресурсный профиль
  требует≥128MiB available и2GiB+768MiB free disk. Policy caps ограничивают
  новый rehearsal; success/capacity долгого окна из них не следуют.
- [x]19new tests passed /23.97s;33cash compatibility cases прошли в51case run
  /60.09s,18cases старой runner revision исключены. Итого52distinct для текущего
  этапа, cumulative701с предыдущими профилями; полный suite не запускался.

## Actual27октября

Original registration завершена до будущего окна
**10:40:26.340391–10:41:26.340391UTC =13:40:26–13:41:26МСК**.
Запуск выполнен в отдельной transient user service
`cryptoforge-paper-rehearsal-20261027-1040.service` без постоянного timer.
Существующие trading units и market-feeder не заменялись.

- [x] Source240original closed rows, BTC/ETH ready,4events/0priceforecasts.
- [x] Candidate/control/stress выполнили12ticks каждая,0missed whole-runner slots;
  6source decisions и33empty heartbeats,44completed journal operations.
  Source delivery acknowledged1/1/1 по durable worker-result receipts.
- [x] Все3 independent controller/FIFO/coverage replay checks прошли.
  **Actual fills0/0/0**: momentum/cost-buffer guard отверг candidate/stress входы,
  control сохранил cash. Это полезный negative-case run, не прибыльный эксперимент.
- [x] MemoryMax512MiB/TasksMax64/Timeout320s/KillModecontrol-group были проверены
  на активной service. Child AS384MiB унаследован subprocesses; whole cgroup cap
  относится ко всем процессам службы. Измеренный sample MemoryPeak34648064bytes
  (≈33.04MiB), systemd сообщил33.0M, swap peak0B, runtime81.467s.
  `/usr/bin/time` largest-process maxRSS33080KiB — другая метрика, не whole-host.
- [x] После exit0 transient service выгружена менеджером. `systemctl show` после
  этого вернул default infinity/no fragment: это **не** фактический runtime cap.
  При проверке использовать сохранённый live sample и systemd-run completion log.

Actual namespace и receipts:
`.local/state/paired-cash-runner-work-20261027/actual-prospective/`,
`actual-reference.json`, `actual-registration.json`, `actual-run.stdout/.stderr`,
`actual-resource-samples.jsonl`, `actual-process-resources.txt` и
`verification.json`.59accepted source/test copies, runtime103entries (часть
значений дублируется между source/capture/replay dependencies).

## CLI и продолжение

`scripts/rehearse_paired_cash.py register --root NEW --spec FILE` регистрирует
offline resource-limited components; spec содержит future start/end, rules,
трёх role configs, worker_policy и closeout_seconds. Только эта команда читает
backend selector из `.env`; секреты не сохраняются в manifests/stdout.
`inspect --reference FILE` — read-only observation. `run --reference FILE` —
explicit public-read/local-paper-write режим, никаких real exchange orders.
Сохранённый reference требует только root/manifest/registration SHA.

Для нового actual run нужны новая регистрация/namespace и отдельный resource
boundary: не повторять завершённое окно, не менять original clocks и не ослаблять
rules ради получения сделки. Неполный root сохранять для W7b.3 investigation.
Журнал содержит precise operation и последнее завершённое component state.

- [ ] W7b.2c.2: actual positive decisions/instrument+book/fill/exit branches,
  более длинный preregistered paired stream и role-level failure/cadence monitoring.
  Public quote provider в actual negative run не вызывался; его positive flow
  проверен синтетически, не фактической рыночной сделкой.
- [ ] W7b.3: versioned interrupted-operation/lost-checkpoint recovery, host restart,
  unknown partial effects и наблюдение на chosen deployment. Single-use refusal
  не является автоматическим восстановлением.
- [ ] W8: длительные window/capacity/retention/network/whole-host checks и review.
  Текущие JSON application groups и full retained-prefix replay рассчитаны на
  bounded rehearsal; не объявлять их пригодными для30days/всех20pairs.
- [ ] Current-model/native/new-head/cash comparisons, R1–R16/VP/W9 и все
  economic/paper/live gates. Original sealed windows не открывались, fits0.

Primary model/risk/real trading/order path этим этапом не менялись. Public data и
новые paper files записаны; основная PostgreSQL не изменялась этим runner.

## Дополнительный actual provider probe27октября

- [x] W7b.2c.2a:10:50:37–10:50:39UTC выполнены отдельные instrument+book GET
  BTC/ETH через тот же bounded provider.4public GET/2full raw snapshots,
  source hashes и original normalization replay2/2. Decision/entry/fill не создавались.
- [ ] Actual positive strategy/provider/fill/exit integration остаётся открытой:
  acquisition probe не заменяет trade. Original minute10:40 всё ещё negative-only.

Evidence `.local/state/paired-cash-runner-work-20261027/provider-probe-verification.json`.
