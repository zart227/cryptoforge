# Explicit recovery сохранённого paper result/ack

27 октября 2026. [Единый checklist](PROFITABLE_STRATEGY_RESEARCH_PLAN.md#current-checklist),
[cash applications](CASH_WORKER_APPLICATION.md), [bounded runner](PAIRED_CASH_REHEARSAL.md).

## Принятая область W7b.3a

- [x] Только один pending application group после известного externally pinned
  completed prefix. Original manifest/registration/runtime и все прежние файлы
  сохраняются. Нужен durable `worker-result.json`, не предположение о завершении.
- [x] Exact cash decisions rederived по original input time; packet сверяется с
  полным retained source prefix и первоначальным offer. Queue восстанавливается
  через существующий explicit known-ancestor replay, не подменой старого DB SHA.
- [x] Worker capture/native state должны соответствовать сохранённому result.
  Полный bounded stream frames проверяется от original manifest до original head;
  source batch/prepared tick/completed result связаны. Новых ticks/providers нет.
- [x] Default создаёт отдельный read-only proposal. Только explicit apply может
  записать недостающие ack/complete, сохраняя existing ack bytes. Original worker
  result, cash contract, input и previous runtime pins не переподписываются.
- [x] Cases: сбой до ack; ack committed, external receipt lost; local ack записан,
  complete не сохранён. После восстановления текущий application checkpoint
  проходит исходный CashWorkerApplication.audit. Следующий обычный heartbeat
  может продолжить обработку в том же original window без duplicate entries.
- [x] Missing result/unknown worker effect, changed input/ancestor/native/head,
  conflicting ack, advanced role, aliases и busy lease блокируются. Recovery
  root не может загрязнять source/worker/application/registered owner namespace.
- [x]17new tests passed /41.81s;33unchanged cash compatibility прошли в46case run
  /69.01s.13ранее прошедших recovery cases исключены из повторного подсчёта.
  Итого50distinct текущего этапа; cumulative718, не full repository suite.
- [x] True process exit42 после queue commit проверен на isolated synthetic stores.
  Отдельная synthetic rehearsal трёх failure points: plan сохранил original bytes,
  recovery не повторял worker, next heartbeat дал2pending fills без новых intents.
  Production outage/recovery этим не объявляется проверенным.

## Применение

Сначала остановить выбранный runner и сохранить original evidence. Same-host
application/capture leases не защищают от произвольного legacy writer/другого host.
Known reference — последний **completed** application checkpoint до pending group:
root,manifest_sha256,registration_sha256,sequence,head_sha256.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/recover_cash_ack.py \
  --known-reference ORIGINAL-CHECKPOINT.json --output NEW-PROPOSAL-ROOT
```

Этот default не меняет application/worker/queue bytes. Recovery proposal сохраняет
original file SHA, original worker head, source/queue ancestor и новый verified
current queue reference. Новый SHA не выдаётся за прежние физические bytes.

`--apply-paper-ack` — отдельный opt-in write-capable режим **только isolated
paper acknowledgement**. Он создаёт новый recovery root, prepared/completed
receipts, недостающие local ack/complete и возвращает новый application reference.
Сохранить оба новых references: application и current queue. Вызовы worker.tick,
market provider, source poll, exchange order, fit и `.env` не используются.

Original signal expiry/window/cutoff не продлеваются. После end восстановленная
квитанция не позволяет исполнять старый сигнал или переписать original clocks.
Повторное применение завершённой recovery отвергается. Если сама recovery
прервалась, сохранить её proposal/prepared и original files; новый explicit
разбор должен снова доказать состояние, не удалять ack/journals.

## Что остаётся открытым

- [ ] W7b.3b: worker committed, но durable worker-result отсутствует; incomplete
  native/action/storage state; неизвестные side effects и source component commit.
  Этот helper такие случаи сохраняет blocked, не реконструирует успех.
- [ ] Whole-runner interrupted journal и lost external checkpoint. Старый
  single-use PairedCashRehearsal **не получил resume**. Его pending parent operation
  нельзя считать completed только потому, что component ack восстановлен.
- [ ] Actual chosen-host crash/restart/recovery rehearsal, long paired stream,
  resource/retention/capacity и independent review W8.
- [ ] Actual positive strategy/provider/fill/exit integration и все economic/
  paper/live/current-model comparison gates.

Evidence `.local/state/cash-ack-recovery-work-20261027/verification.json`,
55accepted source/test copies/runtime59entries, original synthetic pending files,
recovery proposals/completions и subsequent heartbeat receipts. Прежние585Python
files и804historicalcheckbox/body сохранены. Primary DB/model/risk/trading services
не менялись, actual orders/fit0, original sealed outcomes не открывались.
