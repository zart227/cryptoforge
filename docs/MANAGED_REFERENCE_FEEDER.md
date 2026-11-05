# Установленный local reference feeder

26 октября 2026. [Текущий checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[исходный runner](REFERENCE_AWARE_FEEDER.md). Primary — local PostgreSQL17/PostgREST;
никакого cloud fallback или exchange-order API в этом пути нет.

## Что принято

- [x] UID1000, original service/timer SHA, отсутствие drop-ins и параллельного
  legacy feeder проверены до замены. Старые unit files сохранены; заменены только
  `cryptoforge-market-feeder.service` и `cryptoforge-market-feeder.timer` пользователя.
- [x] Docker Unix socket, pinned db/rest/api images, exclusive compose network,
  unique aliases и read-only exact nginx route проверены с двух сторон запроса.
 120closed BTC rows с original UUID/values совпали в SQL→REST→SQL. Тот же
  bounded check выполнен для ETH. SQL identity/schema одинаковы.
- [x] Разовый opt-in cycle13:04UTC и installed service cycles13:22/13:24UTC успешны.
  BTC/ETH mandatory refresh и closed120 SQL probes выполняются до ranking.
  После установки BTC fresh: age181.16427s при read13:23:01UTC.
- [x] Таймер `OnUnitInactiveSec=120s`, первый повтор автоматический.
  Служба MemoryMax768MiB/TasksMax64/TimeoutStartSec420/KillMode=control-group;
  child AS512MiB/stage75s/output64KiB. MemoryPeak не предоставлен systemd,
  whole-host RSS/capacity этим не измерены.
- [x] Новый managed namespace имеет external manifest/registration pins, runtime17files,
  собственный writer lock и streamed per-file inventories/completion receipts.
  Unknown incomplete cycle блокирует новый writer; partial effects не откатываются.
- [x] Operational retention384MiB/720cycles/24h, cycle cap96MiB, free reserve2GiB+
  cycle cap. Только terminal successful operational cycles могут удаляться;
  сохраняются последние два success и все failures. Research evidence не удаляется.
- [x]151tests passed /4.19s:43new+108compatibility. Четыре профиля26октября
  дают564distinct cases,199повторных runs; полный repository suite не запускался.
  Прежние572Python files сохранены. Старые source/model/runtime pins не переписаны.
- [ ] Длительные outages/restart/cooldown/retention и whole-host qualification R4/W8.
- [ ] W7b.2 actual cash policies/opportunity stream/CapturedPaperWorkerV2 results,
  W7b.3 component recovery, W9 future evidence и economic/paper/live admission.

## Регистрация, запуск и проверка

Установленный namespace:
`.local/state/managed-reference-feeder-v2-20261026/`.
External reference находится в
`.local/state/reference-feeder-operation-work-20261026/deployment-registration.json`.
`manifest_sha256=433719df7d566e6d5a18d9aa726f3be4fdaaaea4303da382b3590380565a1f7d`,
`registration_sha256=81584b15df7376f058c1df6b1e0b484b9c7adca9746389e771ab271756d4dbe2`.

Read-only `scripts/manage_reference_feeder.py status --root ROOT
--manifest-sha256 SHA --registration-sha256 SHA` проверяет original registration,
runtime и все retained completed files. Во время активного writer lease status
может быть занят; это не основание убивать writer или чистить pending state.
`systemctl --user status cryptoforge-market-feeder.{service,timer}` показывает
фактическое состояние. Ближайший запуск отсчитывается от завершения oneshot.

Для нового namespace CLI `register` читает local route/rows и сохраняет contract;
`propose-service` создаёт reviewable unit files без установки. `run` — write-capable:
обновляет market candles/tickers/health и dynamic universe. Аргументы/root/pins
обязательны. BTC/ETH не добавляются в торговый whitelist самим reference gate.

Не менять17pinned runtime files при действующей регистрации. Новую версию
регистрировать отдельно до установки, старую историю не переподписывать.
Неиспользованный v1 сохранён после исправления unit WorkingDirectory;
он не является установленным runtime и не должен усыновляться под текущий SHA.

## Сбои и границы восстановления

При rate limit исходный runner сохраняет shared cooldown10min и не продолжает
оставшиеся venue calls. Последующие попытки до expiry не должны делать запросы.
Перед заменой/ручным запуском остановить только market-feeder timer, дождаться
завершения oneshot и исключить параллельный legacy writer на этом host.
Новый lease не защищает от произвольного старого script или другого host.

Если процесс завершился до `complete.json`, не удалять pending или SQLite journal,
не повторять тот же cycle и не запускать legacy feeder для сокрытия результата.
Остановить таймер, сохранить bytes/units/logs, разобрать стадии и неизвестные cache
effects. Автоматическое adoption/repair не реализовано; это открытый recovery gate.
Market upserts между стадиями не составляют общую транзакцию.

Исходные unit backups лежат в operation work root как
`before-cryptoforge-market-feeder.service` и `.timer`. Возврат — явная scoped
операция после остановки writer и проверки cooldown/владения/текущих SHA;
само наличие backups не является проведённым outage drill.

## Evidence

`.local/state/reference-feeder-operation-work-20261026/` содержит baseline572,
original unit backups, redacted host topology, original route before/after,
one-off stage results, deployment19accepted source copies, unit syntax check,
installation receipt, snapshot двух completed cycles, test IDs и offline
`verify.py`/`verification.json`.

Две ошибки до deployment сохранены: нестабильный порядок nginx stdout/stderr
исправлен `-q -T`, а WorkingDirectory должен передаваться без argv-кавычек.
`-q` подавляет только non-error test diagnostics по
[официальной документации nginx](https://nginx.org/en/docs/switches.html);
exact full configuration comparison не ослаблен.

Technical local route pass относится к наблюдённой topology и конкретным120rows.
Он не доказывает historical known_at, непрерывную полноту polls или ликвидность.
Модель/risk/trading units не менялись; real orders0, fit=false, sealed outcomes
не читались. Full-worker/host, economic profitability, paper evidence и live admission=false.

## Recheck27октября

Read-only status10:15UTC валидировал313retained completed cycles, все success,
302095396bytes, latest10:14:52UTC; timer active/waiting. Сохранены238prune receipts
в текущей bounded истории. Oldest retained26октября22:22:39UTC: удалённые старые
successes не объявляются полностью сохранённой20h историей. BTC10:16:09UTC
120SQL/REST/SQLfresh(age69.866558s), instance/schema прежние. Snapshot latest cycle,
retention manifest и original REST/SQL observations сохранены в
`.local/state/cash-worker-application-work-20261027/`.
Это подтверждает работу retention на выбранном feeder, не whole-host/outage gate.
[Следующий cash adapter/worker этап](CASH_WORKER_APPLICATION.md).
