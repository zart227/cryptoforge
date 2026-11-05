# Capture v3: сегментированный журнал и исходные native rows

18 октября 2026, Europe/Moscow. `paper_capture_v3.py` — отдельный opt-in
адаптер существующего PaperWorker API для НОВОГО namespace. Он связывает
segmented events, original marks/fills/closed-segment row IDs и native state.
Это локальная реализация capture/source audit; full paper/economic/live
admission ещё отсутствует. Длинный study **BLOCKED** до следующих пунктов.

## Неизменяемая регистрация

`SegmentedCapturedPaperWallet.create` требует candidate SHA, исходный parent
study protocol SHA, роль `candidate`/`control`/`stress`, PaperConfig,
SegmentedLifecycle, SegmentPolicy и будущие start/end. Нельзя открыть legacy
root, добавить роль в существующий protocol или повысить его budgets.

1. В новой директории создаётся native wallet; исходная SQLite schema получает SHA.
2. Protocol связывает root/role/parent/candidate/config/cadence/resources,
   native schema, Decimal context и exact runtime SHA до outcomes.
3. Storage manifest ссылается на protocol SHA; genesis содержит пустой wallet.
4. Отдельная registration связывает protocol и storage manifest SHA до start.
   Это устраняет круговую зависимость checksums.
5. Original registration SHA сохраняется вне изменяемого namespace и нужен
   для каждого resume. Если setup не успел до start, root нельзя переиспользовать.

Само наличие parent/candidate SHA не проверяет admission этих документов.
Это обязанность будущего полного entry/runner adapter. Короткие synthetic
fixtures не являются квалифицированным min30days study и не меняют старые окна.

## События и восстановление

Durable `prepared` сохраняет before-state, input quotes/rules/raw responses,
original intent before execution, operation clock, poll slot и ресурсы.
Только после этого вызывается native mark/execute. `complete` связывает prepared
sequence, результат, after-state и exact original row IDs/payload SHA:

- `marks`: новые целочисленные IDs и hashes исходного JSON payload;
- `fills`: исходный intent_id и payload hash;
- `closed_segments`: новые исходные IDs и payload hashes.

Ни payload, ни row IDs не обрезаются и не перенумеровываются. Native error,
несохранённая completion или слишком большой результат оставляют prepared
и блокируют resume/новые операции. Результат не выдумывается по текущему wallet.
Storage recovery может дописать только уже зарегистрированный точный frame.
Если это complete и after-state совпал, resume безопасно продолжает следующий
шаг. Если это prepared, native outcome неизвестен: требуется review, без retry.

Проверены настоящие subprocess exits после native commit и во время частичной
complete-записи. Прежние frozen PaperWallet/PaperWorker и storage v1 исходники
не менялись. Это local process-death проверка; power-loss/host qualification нет.

## Ресурсы и завершение

`SegmentedLifecycle` сохраняет cadence/closeout/wall/memory правила прежнего
контракта; отдельная v3 schema расширяет только общий storage budget до
явного signed64 bound. V1/v2 по-прежнему ограничены64MiB. V3 total budget
резервирует весь event log,64MiB native wallet и metadata; free disk floor
должен покрывать весь budget. Никакого автоматического увеличения после outcomes.

Подсчёт bytes включает nested storage files, catalogue и manifest. Перед native
операцией проверяются общий/resource/event/segment budget, резерв prepared+
complete+terminal и приближение native wallet к64MiB. При исчерпании ресурсов
сохраняется terminal до следующей native записи. Больший, чем ожидается,
native результат всё ещё может оставить incomplete prepared; это не жёсткая
filesystem quota и не замер actual market capacity.

После entry cutoff новые Buy запрещены в enqueue и непосредственно перед fill;
разрешённый Sell сохраняется до end. Completed terminal допустим только после
end в original grace; early abort не раскрывает результаты раньше окна.
`finalize()` после original terminal закрывает log и публикует новый `sealed.json`.
Original seal SHA снаружи namespace обязателен для итогового аудита. Несохранённый
seal receipt можно создать после resume; частичный/существующий receipt нельзя
автоматически переписать.

## Read-only аудит

```text
.venv/bin/python scripts/audit_paper_capture_v3.py \
  --root /absolute/new/capture \
  --expected-registration-sha256 ORIGINAL_REGISTRATION_SHA \
  --expected-seal-sha256 ORIGINAL_SEAL_SHA \
  --output /absolute/new/audit.json
```

CLI использует реальные UTC часы, без `--as-of`. До end читает только protocol
и registration; wallet/storage/receipt не открывает. Output должен быть новым
и находиться вне source root. Audit никогда не делает writer recovery.

После end audit принимает original seal/head/catalog pins и проверяет весь
event stream, native schema, row payload hashes, chronology, slots/resources,
causal prepared/complete, inventory/cash transitions, day-anchor и независимую
liquidation valuation. Day-anchor пересчитывается с последним known mark и
оригинальными UTC clock; состояние не копируется из producer summary.
После чтения fingerprints и metadata pins сверяются повторно.

`operation_trace_pass=true` означает только эту область source/operation replay.
Всегда `paper_evidence_pass=false`, `full_fifo_replay_pass=false`,
`coverage_evidence_pass=false`, `economic_profitability_established=false`,
`live_admission_granted=false`. Fill arithmetic/полный FIFO, независимые strategy
decisions и known-time coverage ещё не квалифицированы этим новым аудитором.

## Чек-лист

- [x] Новый v3 protocol/registration, роли/parent/runtime/schema/Decimal pins.
- [x] Segmented prepared/complete/terminal, source row IDs/hashes, exact recovery.
- [x] Budget/closeout/allowed Sell, no-retry, native schema/path drift guards.
- [x] End-window sealed CLI и read-only потоковый source/operation audit.
- [x] Локальные synthetic и actual subprocess-death проверки; source SHA
  и test receipts в `.local/state/paper-capture-v3-work-20261018/`.
- [x] Read-only размер двух original public inputs13октября: APT/USDT2225bytes,
  NEAR/USDT2227bytes для одного v3 mark input, с проверкой исходных SHA/runtime/
  normalization. Это quote+rules одной пары, без before/after wallet/event frames;
  не current freshness и не future budget qualification. Receipt:
  `.local/state/paper-capture-v3-work-20261018/archived-public-input-sizes.json`.
- [x] Отдельный [bounded native wallet archive](NATIVE_PAPER_ARCHIVE.md): immutable marks/fills/segments/intents,
  durable archive→checkpoint→active cleanup, original IDs/cash/FIFO/day anchors.
  Нужен versioned source format с global high-water counters и unified reader
  active+archive: текущая v3 проверяет count=max(row ID) и отвергает DELETE.
  Такой source-store реализован отдельно; очистка старого v3 root не разрешена.
- [x] Отдельный bounded worker archive: worker_events/seen_predictions/intent_links,
  atomic seen→intent linkage, pending exits и replay без aliases/потери истории.
- [x] [Capture v4 integration](PAPER_CAPTURE_V4.md): новый protocol/registration и causal events
  связывают indexed source archive/active checkpoints; sealed future-window gate.
- [x] [Streaming fill arithmetic/FIFO/valuation/known-time coverage](PAPER_STREAMING_REPLAY.md) реализован отдельно.
- [ ] Full worker strategy/opportunity/source decisions. Старый CoverageTimeline хранит mark clocks/intervals в списках;
  его и history-accumulating snapshot/auditors нельзя использовать на длинном run.
- [ ] Общий бюджет трёх ролей, реальные payload sizes/process RSS/full tick/
  network/queue/disk, host/power-loss и independent review.
- [ ] Qualified candidate, full runner/admission и НОВАЯ prospective registration
  по исходным экономическим/временным gates. До этого actual study не запускать.

Проверки v3:45focused tests passed /16.19s; итоговый общий **1809 passed, 1 deselected /438.15s**.
Последняя semantic проверка меняет сторону original intent и пересчитывает
segment/catalog/seal hashes: оригинальный Buy fill всё равно не принимается
как результат Sell intent. Корректность source trace не выводится только из SHA.

Подробный [следующий acceptance checklist](EVIDENCE_SEGMENTS.md#приёмка-следующей-интеграции-capture-v3)
и [актуальный основной план](PROFITABLE_STRATEGY_RESEARCH_PLAN.md).
