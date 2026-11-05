# Local source provenance v1 — W6a

Дата: 22 октября 2026. Реализованы отдельный observer, immutable source contract,
диагностический capture, offline audit и сравнение двух наблюдавшихся revisions.
Общая W6 не закрыта: следующий W6b должен связать источники с actual upstream
forecasts/polling и устранить неполное обновление обязательных reference pairs.

## Что именно подтверждается

- Прямое чтение локального PostgreSQL17 через существующий Docker compose.
  Одна транзакция `REPEATABLE READ READ ONLY`, `ROLLBACK`, SQL timeout2s,
  lock timeout250ms, idle timeout5s, process wall<=15s и response<=4MiB.
- Cluster `system_identifier`, database OID/name/version, schema/table OID,
 18 column contracts, defaults, constraints, indexes, triggers/functions и RLS
  policies. SQL definitions сохраняются как SHA256, без их исходного текста.
- Retained migration metadata/source-hashes/verification/backup-restore
  verification связаны original file SHA, inventory и counts. Это проверка
  сохранённых receipts, не повторная миграция и не утверждение, что текущая
  изменяемая БД равна снимку20октября.
- До120 закрытых последовательных свечей Bybit Spot в одном query snapshot.
  Сохраняются original UUID, table OID, `xmin`, точный `row_to_json` текст,
  query SHA и runtime SHA до/после чтения. Числовые lexemes не проходят float
  roundtrip; исходные bytes и их hashes остаются доступными offline.
- `known_at` консервативно равен actual completion этого чтения.
  `created_at/ingested_at/updated_at` остаются source claims. Они не становятся
  доказательством исторической доступности после переноса БД.
- Два delivered reads можно сравнить на revision drift. Изменение source/schema,
  повторный UUID под другой свечой, смена UUID той же свечи, gaps/future times,
  duplicate JSON/IDs и malformed OHLCV не принимаются. Новая revision имеет новое
  время наблюдения; прежнее observation не редактируется.
- Query freshness явно пересчитывается. Для нового registered capture допустимы
  максимум2intervals после последнего candle close. Диагностический probe
  сохраняет stale evidence с `candle_freshness_pass=false`; такой probe нельзя
  усыновить как registered source или использовать для обхода freshness.

## Что не подтверждается

Это прямой SQL-source, **не идентификация отдельного REST endpoint**. Совпадение
API URL с kernel configuration не доказывает, что REST обслуживает этот cluster.
Будущий runner обязан использовать original observations этого reader либо
предъявить отдельное доказательство REST→instance linkage.

Компонент покрывает `public.market_candles`, не исходные predictions/forecasts
из других stores. Нет глобального first-seen ledger, доказательства полноты
polling/cursors/negative outcomes или новой трёхролевой registration. Сравнение
двух reads не восстанавливает пропущенные промежуточные revisions.
W6b/W7 и actual host qualification ещё нужны.

`source_poll_completeness_verified`, `historical_known_at_verified`,
`rest_instance_identity_verified`, `full_worker_or_host_qualified`,
`paper_evidence_pass`, `economic_profitability_established`,
`live_admission_granted` всегда `false`. Отдельный integrity pass не меняет эти gates.
Frozen kernel/archive/capture/replay v1/v2 и старые receipts не менялись.

## CLI

Диагностический probe читает только локальную БД и пишет новый private namespace:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/audit_local_source_provenance.py probe \
  --output .local/state/new-local-source-probe --pair BTC/USDT --limit 120
```

Сохранить возвращённые `observation_sha256` и `completion_sha256` отдельно.
`audit --root PATH --observation-sha256 SHA --completion-sha256 SHA` работает
offline и не читает credentials или БД. Частичные roots, link aliases,
подмена raw/derived facts и несовпадающие external pins отвергаются.
Пути primary database/transfer не допускаются как output.

`register` требует externally pinned probe, новый study SHA, pairs, future
`--start/--end`. Contract и отдельный registration SHA должны быть получены
до start; late/partial namespace не усыновляется. Это не запуск study.
`capture` требует обе original contract pins и текущую незавершённую window;
`audit` такого capture тоже требует эти pins. CLI не имеет `--as-of`.
Actual registration/capture study на этом этапе не запускались.

## Actual read и выявленный blocker

22октября13:33:27UTC прочитаны120BTC и120ETH свечей под окончательными runtime pins.
Оба observation offline verified, identity/schema/migration связаны.

- BTC: последний close **21октября23:10UTC**, age51807.334863s
  (14h23min), `candle_freshness_pass=false`.
- ETH: последний close **22октября13:30UTC**, age207.736015s,
  `candle_freshness_pass=true`.
- Read wall0.5670s/0.3618s. Это bounded read, не full-worker RSS/capacity measurement.
- Installed feeder конфигурация использует dynamic selection→selected config sync.
  В read-only universe snapshot13:29UTC BTC/ETH отсутствуют. Это поддерживает
  гипотезу, что reference pairs не обновляются независимо от ranking; causal
  diagnosis/service status ещё не доказаны. Службы и БД не изменялись.

Следующий W6b: mandatory benchmark coverage/freshness, original forecast linkage,
история наблюдений/revisions и reader adapter в новом shared source namespace.
Нельзя объявлять BTC-context пригодным только потому, что ETH и сама БД отвечают.

Receipts: `.local/state/local-source-provenance-work-20261022/`:
`accepted-actual-probe-receipts.json`, `source-freshness-diagnosis.json`,
`accepted-runtime-pins.json`, `accepted-sources/`, итоговый `verification.json`.
Предварительные probes до окончательных runtime pins сохранены как development,
не как final/registered study evidence.

## Проверки

- [x]79 новых tests passed /2.00s, включая actual subprocess byte/time limits,
  offline CLI, wrong instance/schema/RLS/query/runtime, revision/ID/known_at,
  stale diagnostics, prospective registration и запрет записи в primary DB paths.
- [x]186 compatibility tests passed /16.22s: backend/CLI, v2 producer/wallet/worker
  и independent exact replay math. Всего265 разных cases этого этапа.
- [x] Actual read-only240rows и offline CLI replay обоих окончательных observations.
- [ ] W6b complete upstream/forecasts/mandatory-source coverage и global revision ledger.
- [ ] W7 paired shared runner/polling completeness, W8 host/review, W9 economics/paper.

Официальные основания SQL: [PostgreSQL17 transaction modes](https://www.postgresql.org/docs/17/sql-set-transaction.html),
[control data functions](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-PG-CONTROL-DATA).
Основной [актуальный checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist).
