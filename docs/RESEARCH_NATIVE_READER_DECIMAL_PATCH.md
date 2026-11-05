# Предложение: точный JSON parser для market candles

Статус: **review only, не применено**. Автор — инженерное изменение ассистента; это не budgeted LLM patch R16.

В `SupabaseMarketReader._get` текущий `json.loads` преобразует JSON дроби в binary64. Следующий `Decimal(str(value))` сохраняет уже округлённое число. Предложение добавляет `parse_float=Decimal`; импорт Decimal уже есть. URL/query/auth, фильтры, ordering/limit, clocks и стратегия не меняются.

[Патч](RESEARCH_NATIVE_READER_DECIMAL_V1.patch) рассчитан на текущие dirty main bytes `src/cryptoforge/supabase_executor.py`, SHA256 `b3a8530632498fc1291f1eecd2aae085b58fc6f4bc2a4b8c89c5bfcf4eb1910c`. Это не diff относительно старого committed base.

- [x] `git apply --check --whitespace=error-all` прошёл без применения к main.
- [x] AST сравнение допускает только добавленный keyword в единственном `json.loads` этого метода. Proposed module не импортировался и не исполнялся.
- [x] На50000original saved scalar lexemes native/exact values совпадают и до, и после; найденной реальной ошибки данных в этом срезе нет.
- [x] Counterexample: `12345678901234.123456789012` сейчас становится `12345678901234.123`, а предложенное чтение сохраняет точное десятичное значение. Integer/string/bool/null semantics проверены отдельно обычным JSON parser.
- [x] В M44 exact parser дал те же6786examples,91feature components и13late label windows. Это поддерживает parser primitive; patched production module end-to-end не запускался.
- [ ] Перед применением повторить source/hash/context check, согласовать с основной веткой и обновить reviewed runtime/source fingerprints. Старые fitted artifacts могут требовать отдельной проверки совместимости с новым source hash.
- [ ] После интеграции проверить actual local REST reader и новый approved training protocol. Старые данные/модели/журналы не переписывать.

Изменение не исправляет stale BR/ONDO, source lineage, размер HTTP body, coverage или недостаток исторических наблюдений. Улучшение метрик обучения, скорости и торгового результата не измерено.

[Python3.12 JSON contract](https://docs.python.org/3.12/library/json.html#json.load) поддерживает Decimal через parse_float. [Проверки патча](../.local/research-reader-decimal-patch-final-20261026/verification.json).

- [x] Final patch artifact: empty context-line prefix whitespace removed; default `git apply --check` still passes. Initial contextual patch/verification retained separately; original main bytes and one-keyword AST change unchanged.
