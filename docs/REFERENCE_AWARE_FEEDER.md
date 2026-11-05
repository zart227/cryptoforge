# Текущий статус26октября: runner установлен

[Managed feeder runbook](MANAGED_REFERENCE_FEEDER.md):13:04UTC один opt-in local
cycle,13:22UTC первый cycle через новую службу прошли. Primary BTC/ETH обновлены;
SQL/REST/SQL binding120closed rows проверен после установки. Служба и таймер
заменены с original backup/owner/pins checks. Automatic cycle13:24UTC подтверждён; full
outage/host qualification открыт. Ниже сохранена исходная code-приёмка:
её «plan-only»/«installed unchanged» относятся к предыдущему этапу, не к текущему.

# W6b.3b.1: reference-aware feeder cycle

Дата: 26 октября 2026. [Текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[local health и safe readiness](SEALED_CASH_READINESS.md),
[отдельный research coordinator](REFERENCE_COORDINATOR.md).

Новый `reference_aware_feeder.py` и CLI `run_reference_aware_feeder.py`
устраняют в новом opt-in пути зависимость reference refresh от рейтинга пар.
Предыдущие569 Python-файлов, установленная служба и её таймер сохранены.

## Приёмка реализации

- [x] До ranking отдельно запускаются BTC sync и ETH sync. Обычный сбой одной
  пары не подавляет попытку другой. Rate limit останавливает дальнейшие запросы
  и сохраняет общий cooldown10min между циклами.
- [x] На каждую reference pair передаётся candle-limit121: последний ответ может
  включать одну открытую свечу. Затем direct SQL observer проверяет ровно120
  закрытых последовательных свечей5m, freshness≤600s и одинаковую DB identity/schema.
- [x] Dynamic selection начинается только после двух успешных sync/probe.
  BTC/ETH не добавляются в торговый whitelist этим условием: ranking прежний.
- [x] Selected sync читает неизменяемую копию выбранных pairs из собственного
  output root. Частичный успех старого CLI с exit0/`failed=...` считается ошибкой;
  совпадение полного набора `synced_pairs` обязательно.
- [x] Только local backend, без fallback. Новый default — plan-only, без чтения
  `.env`, ключей, network/DB access. Write-capable цикл требует `--apply-local`.
- [x] Single writer lease, runtime checks до/после child, отказ от повторного
  использования output root, private stage receipts с SHA вывода без его текста.
- [x] Child address space≤512MiB через prlimit; output≤64KiB, stage wall≤75s,
  process-group termination, disk floor2048MiB+16MiB. SQL observer имеет свои
  read-only/time/bytes caps. Это лимиты, не замер whole-host RSS/capacity.
- [x]17new+96compatibility=113 разных tests passed /2.55s.
- [x] Actual plan-only CLI26октября создал commands/runtime proposal; primary
  write attempted=false, service installation=false.
- [ ] W6b.3b.2/R4: квалифицировать и заменить действующий installed feeder path,
  проверить настоящий local sync/probe, REST→instance linkage, повторные cycles,
  outage/restart, ownership/retention и host/recovery. Эти tests не равны deployment.

## Проверяемый запуск

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_reference_aware_feeder.py \
  --output .local/state/NEW-reference-feeder-plan
```

Plan-only сохраняет `plan.json` с точными argv и runtime SHA и `result.json`.
В нём четыре стадии: reference_btc → reference_eth → select → selected_sync.
Каждый настоящий цикл требует нового output root. Скрипт не устанавливает
периодический запуск и не переписывает старый installer.

`--apply-local` — отдельный write-capable режим: существующий sync пишет
market candles/tickers/health в локальную БД; selector обновляет файл universe.
Опцию не использовали при этой приёмке. До operational запуска остаются
ownership/installed-path checks и исключение одновременного старого feeder.
Новый lease защищает новый runner, не произвольные старые scripts/другой host.
Полный execution/model/risk admission не выдаётся этим исправлением collector.

Незавершённый цикл не возобновляется автоматически: stage receipts сохраняются,
повтор с тем же root отвергается. Market upserts разных стадий не составляют одну
транзакцию и не откатываются после последующего сбоя. После rate limit отдельный
mutable operational cooldown state сохраняется под `.local/state/`; это не
append-only research source ledger. Долгий retention/recovery ещё W8/R4.

## Evidence и текущий остаток

`.local/state/reference-aware-feeder-work-20261026/` содержит checkpoint569files,
accepted11source/test copies, `pytest-final-accepted.log`, actual proposal,
`test-coverage.json`, offline `verify.py` и `verification.json`.
Три профильные проверки26октября:444 +55 +113 cases;91 повторяются между первым
и третьим набором. Итого **521 разных cases**, не612 и не full repository suite.

Последний primary SQL probe перед этим proposal: BTC close23октября14:05UTC,
stale≈70h; ETH fresh. Эта code-приёмка primary rows и service не меняла, поэтому
не объявляет BTC исправленным. Cash contracts/worker receipts W7b.2, W7b.3/W8,
W9 и economic/paper/live qualification остаются открытыми. Новых fits/real orders нет.

## Продолжение27октября

Managed feeder продолжает installed path:313retained success/238prune receipts,
BTC fresh120SQL/REST/SQL при read10:16UTC. Это bounded retained history, не весь
период с установки. [Текущий runbook](MANAGED_REFERENCE_FEEDER.md),
[cash-entry/application receipts и следующий runner](CASH_WORKER_APPLICATION.md).
