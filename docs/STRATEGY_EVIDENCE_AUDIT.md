# Проверка происхождения исследовательских paper-результатов

`scripts/audit_strategy_evidence.py` проверяет исходные локальные evidence
законченного cash-study. Он сверяет registrations и пересчитывает results,
сохраняя `live_admission_granted=false`. Существующие протоколы и модели
явно research-only; даже успешный экономический synthetic test не даёт
разрешения рабочему боту. Это отдельный механизм R2/R14, без entry adapter.

## Вход и команда

Нужны original protocol JSON + `.sha256`, original observed collection
registry и явно выбранный SHA model artifact. Для завершённого окна также
нужны исходные candidate/predictions, policies с freeze receipts/registries,
retained role export и acceptance report, а также шесть wallet/worker DB.
Файлы должны быть сохранены под первоначальными ожидаемыми путями.

```bash
.venv/bin/python scripts/audit_strategy_evidence.py \
  --protocol config/live-cash-recovery-closed-protocol-v1.json \
  --expected-artifact-sha256 REVIEWED_CANDIDATE_ARTIFACT_SHA256 \
  --state-root .local/state \
  --output /absolute/new/research-evidence-audit.json
```

`--output` необязателен; без него результат выводится в stdout. При сохранении
нужен новый отдельный путь: overwrite, symlink и пересечение с evidence paths
запрещены. Источники открываются read-only; инструмент не запрашивает рынок,
не запускает paper worker и не загружает сохранённый код для исполнения.
Ключи/API credentials не требуются.

CLI использует текущие UTC часы, без `--as-of`. До `paper.end_exclusive`
читаются только protocol/checksum и collection registry. Ответ
`sealed_until_paper_end` скрывает performance, не читает candidate/role DBs
и не подтверждает запрошенный artifact pin. Для текущего closed protocol
paper end — 15 января 2027, 21:59:16.427796 UTC; sealed-test end отдельно —
18 декабря 2026, 21:59:16.427796 UTC. Эти сроки не заменяются test clock.

## Проверки после завершения окна

- [x] Original protocol checksum/payload и фактически наблюдавшаяся collection
  registration; legacy protocol без такого registry не принимается задним числом.
- [x] Manifest/artifact SHA, feature/input/target/threshold contracts и исходная
  регистрация candidate до eligible test opportunities.
- [x] Execution/acceptance bytes сверяются с первоначальными SQLite freeze
  records; chronology проверяется отдельно. Paper runtime/source bundle должны
  совпадать с исходным policy freeze; drift требует нового исследования.
- [x] Candidate, baseline control и stress candidate экспортируются заново из
  исходных wallet/worker DB на retained export clock. Проверяются exact role
  policies/config, stress multiplier и соответствие полного retained export.
- [x] Предсказания сверяются с original shadow ledger и вероятностями pinned
  model. Кампании должны соответствовать разрешённой исходной opportunity.
- [x] Acceptance пересчитывается обычным evaluator на original policies;
  одно retained поле `paper_evidence_pass=true` доказательством не считается.
- [x] Cash и остатки lots пересчитываются из original fills для полного
  потока marks. Проверяются before/after одного fill с одинаковым timestamp,
  coverage inventory, known/unknown values и точное равенство cash для flat/
  recorded dust-zero marks. Завышенный капитал и material inventory,
  переименованная в dust, блокируют audit даже после пересоздания summaries.
- [x] В итог включаются hashes/inodes исходных файлов и verifier/runtime source
  hashes; изменение input/source во время audit запрещает частичный результат.
  JSON duplicate/nonfinite fields и SQLite sidecars не игнорируются.

Проверка ограничена завершёнными, неподвижными DELETE-mode SQLite файлами
до64MiB каждый. При WAL/SHM/journal, missing/corrupt источнике или drift
возвращается `strategy_evidence_blocked`, без инициализации нового источника.
Несколько fills с одним timestamp требуют original ordering review:
порядок по имени заявки не принимается за порядок фактического исполнения.
Не удалять sidecars ради прохождения проверки. Source files/DB следует
сохранять вместе с audit: один JSON не заменяет исходные evidence.

Native mark payload сохраняет рассчитанную equity, но не исходные mark
quotes/filters. Поэтому расчёт market value удерживаемой позиции полностью
не воспроизводится. `conditional_evaluation_pass` показывает пересчитанный
результат прежнего evaluator; итоговый `paper_evidence_pass` остаётся false,
если есть unreplayed liquidation marks. В `mark_cash_audits` видны coverage
и число таких marks; gate `historical_equity_valuation_source_qualification`
остаётся открытым. Новые исторические quotes не подставляются задним числом.

## Что остаётся открытым

- [x] Отдельное [сегментированное storage](EVIDENCE_SEGMENTS.md): глобальный
  counter/budget, bounded files, durable pending recovery и structural streaming
  audit реализованы локально. Это не подтверждает paper/economics и пока не
  заменяет исходные v1/v2 wallet/worker DB или общий cash/FIFO replay.
- [x] Отдельный opt-in capture/replay для НОВЫХ исследований реализован:
  [PAPER_VALUATION_CAPTURE.md](PAPER_VALUATION_CAPTURE.md). Raw quotes/rules,
  causal sequence, independent liquidation и sealed audit проверены локально.
  Frozen producer и исходные study этим не менялись; actual forward run не выполнен.
- [x] [Capture v4](PAPER_CAPTURE_V4.md) связывает НОВЫЙ native archive с
  prospective ledger/row deltas/checkpoints и end-window read-only CLI.
  [Streaming FIFO/valuation/coverage](PAPER_STREAMING_REPLAY.md) теперь реализован отдельно;
  полный worker/strategy replay остаётся открытым;
  старые frozen studies и source gaps этим не исправляются.
- [ ] Actual future cash-study: сейчас нет qualified candidate и завершённых
  независимых test/paper окон. Synthetic fixtures проверяют код, не доходность.
- [ ] Полный independent strategy evaluation, historical/source qualification
  и соответствующая live-eligible evidence policy остаются отдельными gates.
- [ ] Для НОВОГО preregistered study сохранять на каждом mark original
  bid/depth/filters/observed-at и причинный event sequence относительно fills.
  Проверить независимый liquidation replay с fees/slippage/rounding/dust,
  stale/missing quote coverage и chronology. Старые marks не дополнять
  современными или восстановленными задним числом котировками.
- [ ] Подключать будущий entry adapter только к явно live-eligible policy,
  exact model/runtime/account scope и независимым evidence. Проверить отзыв/
  drift непосредственно перед Buy, сохранение разрешённых exits и no resend
  существующего ACK; research-only auditor не использовать как grant.
- [ ] Проверка не воспроизводит каждый исторический market/risk/latency decision
  и не удостоверяет внешнюю неизменяемость локального SQLite registry.
  Подмена всей локальной истории вне сохранённых trusted references остаётся
  границей доверия; source SHA не является подписью независимой стороны.
- [ ] Actual account/runtime/operational qualification и операторский rollout.
  Audit не подключён к installed executor и не создаёт разрешающий approval.

Точное состояние выполнения и тесты — в
[основном плане](PROFITABLE_STRATEGY_RESEARCH_PLAN.md). Общий R2 этим механизмом
не закрыт; успешная сверка research evidence не меняет основной model artifact.
