# Текущая проверка блокировки feeder — 28 октября

В 13:30 МСК локальный `cryptoforge-market-feeder.service` был в состоянии
`failed/exit-code`, а его timer оставался `active/waiting`; последняя отметка
срабатывания timer — 13:29:57 МСК. Последние строки journal показывают
`Managed reference feeder failed: ValueError` без текста причины. Поэтому
конкретную причину именно этого запуска по журналу установить нельзя.

Отдельная проверка read-only методами с исходными registration/runtime pins под
существующей lease подтвердила, что в тот же период `_entries()` возвращает
`incomplete operational cycle requires explicit investigation`. Этот guard
препятствует текущей подготовке очередного цикла. Проверка не вызывала `run`,
не выполняла `selected_sync`, не перезапускала службу и не меняла БД или циклы.

Повторная [проверка неполного цикла](FEEDER_INCOMPLETE_INSPECTION.md) в 13:30:32
подтвердила прежний incomplete cycle: первые три stage receipts сохранены,
следующая `selected_sync` без receipt; её эффект остаётся unknown. Исходные
files и pins не заменялись. Текущая SQL/REST freshness в этой проверке не
считывалась, успех прошлых стадий не означает актуальных свечей.

Evidence:

- Host status/journal `.local/state/forecast-runtime-audit-20261028/feeder-host-observation.json`,
  SHA-256 `4b4f9bed99e9f855c1b0e9d3a6ed25deb36814733c2f4736965c20eb9100fb6d`.
- Проверка guard `.local/state/forecast-runtime-audit-20261028/feeder-guard-check.json`,
  SHA-256 `4243a59f2e34b75cde670d3b57daa5b79f172f1f214170692070d454138b75ce`.
- Повторная проверка цикла `.local/state/forecast-runtime-audit-20261028/current-feeder-inspection.json`,
  SHA-256 `95774122dc756ac293fe0da25676a234247f2097eb5ea07b2734b3c9c2b79966`.

- [x] Повторно зафиксировать нынешнее препятствие без записи или повтора стадии.
- [ ] Доказать или надёжно ограничить эффект `selected_sync`, учесть независимых
  writers и закрепить исходные версии строк; разработать explicit recovery и
  проверить его на копии, включая crash/restart и неподтверждённые эффекты.
- [ ] Выполнить и проверить фактическое восстановление и свежесть mandatory
  closed120 BTC/ETH, когда выполнены соответствующие условия. Guard не обходить.
