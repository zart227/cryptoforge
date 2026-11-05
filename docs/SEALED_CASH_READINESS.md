# R6 / W7b.2 preflight: календарь до чтения исходов

Дата: 26 октября 2026. [Текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[координатор](REFERENCE_COORDINATOR.md), [local source provenance](LOCAL_SOURCE_PROVENANCE.md).

Новый `sealed_cash_readiness.py` проверяет окончание каждого development окна
**до вызова loader**, а не только перед вычислением `data_ready_for_offline_fit`.
CLI `scripts/check_sealed_cash_readiness.py` требует явный frozen protocol path
и сохраняет результат в новом private output root. Старые566 Python-файлов,
protocols, модели, service/timer и runtime approvals не менялись.

## Приёмка

- [x] Незавершённые train/validation окна не вызывают loader исходов. Counts
  возвращаются `null`, что означает «не проверялись», а не ноль примеров.
- [x] На точном train cutoff можно прочитать только train; validation остаётся
  закрытым до собственного cutoff. Original embargo/cutoff rules сохраняются.
- [x] Sealed-test/paper payloads не открываются этим preflight даже после end:
  independent unblinding выполняется отдельным зарегистрированным процессом.
- [x] До открытия payloads CLI проверяет original checksum и observed prospective
  collection freeze. Forged/unobserved past protocol не открывает memory store.
- [x] После cutoff новый reader использует read-only snapshot, последние
  доступные versions/withdrawals, caps10000versions/16MiB/256KiB row/5s,
  metadata/payload consistency и явный отказ при sidecar/alias/concurrent change.
- [x]14new+41compatibility=55 разных tests passed /0.92s; общий suite не запускался.
- [x] Actual closed-protocol preflight26октября: calendar-only, inspected splits[],
  fit=false. `strace -e openat` подтвердил отсутствие открытия
  `live-experience-memory.sqlite`; читался original protocol freeze registry.
- [ ] W7b.2: cash-entry policies, полный actual opportunity stream и durable
  application/result receipts настоящих CapturedPaperWorkerV2.
- [ ] R6: достаточные qualified samples, завершённые train/validation windows,
  current collection health и проверка feature/input compatibility.
- [ ] R4/W6b.3b: устранение реального primary reference refresh gap и проверка
  выбранного installed feeder/REST→instance linkage.

## Применение

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/check_sealed_cash_readiness.py \
  --protocol config/live-cash-recovery-closed-protocol-v1.json \
  --output .local/state/NEW-sealed-cash-preflight > .local/state/NEW-preflight-receipt.json
```

Closed protocol: train end **6ноября21:59:16.427796UTC = 7ноября00:59:16МСК**;
validation end **20ноября21:59:16.427796UTC = 21ноября00:59:16МСК**.
Legacy protocol имеет другие даты и другой SHA. Поэтому implicit default,
`--as-of`, подмена окон и автоматическая регистрация protocol отсутствуют.

Preflight не сертифицирует source health: в CLI `source_health_qualified=false`.
Даже завершённое окно и достаточный raw count не дают fit/paper/live admission.
API сохраняет original readiness rules для уже открытых development snapshots;
автоматический fit/publication отсутствуют. Классы/доходность незавершённых окон
не вычисляются. Архивные свечи не считаются новыми реальными покупками.

Это новый opt-in путь, старые readiness/preflight CLIs и установленный scheduler
не переписаны. Гарантия отсутствия раннего чтения относится к этому пути;
она не объявляет все остальные процессы автоматически квалифицированными.

## Обновлённые факты о local source

Read-only probes26октября (120rows каждый, SQL READ ONLY/ROLLBACK):

- BTC: последний close **23октября14:05UTC**, observation12:05:20UTC,
  age252020.491109s, freshness=false.
- ETH: последний close **26октября12:00UTC**, observation12:06:12UTC,
  age372.296792s, freshness=true.
- У обоих identity/schema/migration bindings и offline source integrity проверены.
  REST→instance linkage и global historical known-at по-прежнему не доказаны.
- Installed market-feeder timer active/waiting, последний oneshot завершился
  успешно15:05:19МСК; inactive/dead после успешного oneshot — не доказательство сбоя.
- Installed unit вызывает dynamic selection→selected sync. В наблюдавшемся
  universe20pairs BTC/ETH отсутствуют. Это поддерживает гипотезу неполного
  независимого обновления benchmarks, но не доказывает причинность.

Свежесть BTC в public research collector не исправляет stale BTC в primary SQL.
При этой проверке primary БД только читалась; services/risk/model не менялись.
Новые сделки/прогнозные исходы и sealed-window rewards не читались.

Work root `.local/state/local-cash-readiness-work-20261026/`: checkpoint566files,
accepted11source/test copies, `pytest-accepted.log`, actual preflight/report SHA,
openat trace, BTC/ETH source receipts и offline verification. Первые sandbox
Docker/ptrace ограничения обойдены scoped read-only escalation, не обходом gate.
Итоговая квитанция — `verification.json` в этом root.
