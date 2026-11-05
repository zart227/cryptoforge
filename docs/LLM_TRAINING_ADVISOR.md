# LLM training advisor: isolated first implementation

Branch: `arthur_dev/llm-training-advisor`. This is the offline diagnostics/proposal/fit prototype
of [the implementation plan](LLM_ASSISTED_TRAINING_PLAN.md), not a completed
research automation system. It adds only new files, with no production imports,
services, schedules, database writes or changes to the existing model trainer.


## Status reconciliation — 5 November 2026

The current branch completion plan is [LLM_TRAINING_ADVISOR_BRANCH_PLAN.md](LLM_TRAINING_ADVISOR_BRANCH_PLAN.md). The 5 November audit notes remain in [the plan](LLM_ASSISTED_TRAINING_PLAN.md#сверка-5-ноября-2026). Dated sections below stay as evidence of work already done. A historical `[x]` records a mechanism or a scoped run on its own date.

On 5 November the branch still points at `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`, with the same tree as `main` and the research files staged in this worktree. No commit, push, or merge was made. The 28 October full profile remains `2699 passed in 176.04s` in `.local/research-candidate-wire-real-20261028/profile-output.txt`. Repeating the 89-file next profile on 5 November produced `22 failed, 2482 passed, 19 skipped, 178 errors` because the live main `supabase_executor.py` no longer matches the reviewed pin `b3a8530632498fc1291f1eecd2aae085b58fc6f4bc2a4b8c89c5bfcf4eb1910c` (current SHA-256 `0ae3096e4b0daa63a9d72fd3219ca4265153334a7c88dcce0ac175c7003bf90a`). The 76 files that did not depend on that pin passed: `2303 passed, 19 skipped`. Logs are in `.local/research-plan-audit-20261105/`.

The default advisor model is still `nvidia/nemotron-3-super-120b-a12b:free`. The 28 October catalog snapshot does not contain it. The v2/v3 candidate `nvidia/nemotron-3.5-super-vl:free` has a zero catalog price and is not a qualified free endpoint. New completions stay refused until a native input-token bound exists. M64 still records `training_admitted=false` and `holdout_independence_attested=false`. Code preview execution stays disabled. The advisor prompt still forbids tools, trading, and budget changes.

The first remaining step is a local inventory of the exposure manifests already stored for M48, M52, and M64. It uses no external API, database write, training run, or provider call.

## Status reconciliation — 23 October 2026

The checklist that was current on 23 October is preserved below as history. The link that pointed at a 23 October heading is replaced by the 5 November section above. The paragraph that follows records what was true on 23 October.

The main checkout retains an archived plan and a separate L1a diagnostics contract;
a typed inter-process bridge now connects its evidence contract, while production still does not import this worktree's advisor automatically. Source,
provider, phase, arithmetic and local-export mechanisms are implemented, but real
historical-data admission, the current approved baseline and ML efficacy remain open.
All worktree additions remain staged, without a new commit/push/merge.

The checklist was reconciled against source/tests and existing evidence: 19 formerly
open items now mark only their implemented scope, 34 explicitly describe partial
completion. All 246 prior open entries map to 20 remaining groups; these are grouped
requirements, not equal-size tasks or a percentage-complete estimate. The documentation-only reconciliation used the 1491-test profile from 21 October. The subsequent bridge continuation on 22 October ran 1564 passed in 102.00s with 73 new tests; it rebuilt main research diagnostics read-only without provider, fit or budget mutations.

R01 source/report-contract reconciliation and model inventory are complete, with a stale-active finding recorded. R02 has temporal/source lineage and a native value-compatibility audit for available windows; data admission remains false. Current priorities are R02–R03 (approved
lineage/splits/baseline), R04 (full diagnostics), then R05–R08 (provider qualification,
full accounting, controlled experiments and equal-budget efficacy), followed by
R09 (independent final test/paper). Semantic research adds R10–R15: installed free
backend, genuine independent human gold, source coverage/lineage, real retrieval,
feature mapping and matched studies. Code experiments add R16–R19: real base/model
provenance, an explicit next numeric protocol (prototype cap remains 3/3), real-data
oracle/evaluator and runtime/stress/security qualification. R20 is optional expansion,
including wider Python/ML families and T4/T5; it does not block the parameter MVP.

Detailed dated sections below are evidence snapshots at their dates. A statement
that a capability was still missing then does not override the current R01–R20 list.
Preserved controls do not establish semantic label accuracy or trading benefit.

Operational storage update (20 October 2026)

The primary checkout now explicitly selects CRYPTOFORGE_BACKEND=local. Its PostgreSQL
17/PostgREST deployment uses loopback API http://127.0.0.1:54321 and PostgreSQL
127.0.0.1:55432. Primary docs/DATABASE_BACKENDS.md and backend.py describe selection;
the preserved migration verification matched 23 tables and 479884 rows at
2026-10-20T11:05:44.666579+00:00. That is migration evidence, not a new current-row
count after workers resumed. No database requests or credential reads were needed
for this session's storage-context receipt.

New research data must come through the selected primary local backend and an
approved immutable development-only export, with source/time/split/baseline binding.
Do not use the now-stale cloud copy as an automatic fallback. The isolated worktree
contains historical infrastructure clients; do not run its old Supabase-only paths
for fresh database access. Backend/deployment changes belong to the primary checkout
and are not reimplemented here. A bounded current PostgreSQL snapshot exporter was added on21 October; approved historical development lineage/splits/baseline remain open (R02/R03).

Existing API/fit/semantic/common SQLite budgets stay at their established paths,
with all history and quotas. Moving operational storage does not move/reset these
journals or relabel old export provenance. Offline advisor and code checks require
no database credentials. Worker namespaces receive neither the DB files/volume nor
host loopback/Unix sockets or .local/database secrets. config/llm-training.env.example
records these constraints without copying a key or loading a database connection.

## M69 — v3 existing accounting and audited wire, 28 October 2026

The separate [v3 audited adapter](LLM_CANDIDATE_WIRE_V3.md) now binds the M68 payload to the existing v5/API journals and quota, tested on synthetic fixtures. Strict input-token admission prevents new real completion; the main bot is not switched. Full profile: 2699 passed, plus two separate synthetic accounting integration tests; post-transfer offline checks passed.

## M68 — modern output limit, 28 October 2026

A [separate v3 payload preview](LLM_CANDIDATE_PAYLOAD_V3.md) uses `max_completion_tokens` and a wire-bound prospective identity. The preview itself does not access transport or journals; M69 adds a separate synthetic-tested integration, while input-token admission still refuses a new request. The final synthetic profile passed 2676 tests, and the preview was independently verified after transfer.

## M67 — retrospective coverage diagnosis, 28 October 2026

The M64 snapshot lacked three eligible pairs under its 80% gate; seven exclusions were stale at the original cutoff. The final synthetic profile passed 2669 tests; the transferred report was recomputed offline with original evidence and unchanged journals. [The remediation diagnostic](RESEARCH_SOURCE_REMEDIATION.md) records the exact historical timing boundary without treating it as a current database status, source fix or training admission.

## M66 — versioned candidate, 28 October 2026

A separate strict existing-journal v2 adapter now pins the M65 free candidate, with its own exchange/worker source identity. It is synthetic-tested and refuses uncached generation until a native input-token bound is verified. The earlier provider, old capture verification and the main bot remain unchanged. Full synthetic profile: 2650 passed. After transfer, an offline check verified the 2050 protected files, original journals and refusal without a native input limit. See [candidate v2](LLM_CANDIDATE_PROVIDER_V2.md).

## Implemented

- Closed-schema development prediction export → deterministic diagnostics.
- Aggregate and per-pair sample count, class balance, Brier/log loss, precision/recall
  at the experiment threshold, predicted positive rate and 10-bin calibration error.
  Diagnostics schema is now `training-diagnostics-v2`; old reports require a fresh export.
- Timezone-aware boundaries including label end times, duplicate detection,
  finite values, field allowlists and evidence IDs.
- Exactly one parameter proposal from a small fixed catalog. No executable code,
  risk settings, arbitrary paths or automatic model activation.
- OpenRouter adapter using the JobPilot API pattern without its application or
  third-party dependencies. A fixed free model is checked against the public
  catalog before each request; zero maximum prompt/completion price is requested.
  There is no retry, model substitution, free router or paid fallback.
- Local Ollama adapter. Cloud endpoints are refused until their free account
  entitlement can be established; an existing JobPilot Cloud setting is not proof.
- Explicit read-only JobPilot dotenv import of OpenRouter key and Ollama model/
  endpoint only. No secret file is copied and the global environment is untouched.
- Private receipt with diagnostics, validated proposal, model, price evidence,
  request/report hashes, usage when available and status. Output never overwrites
  an existing file. The legacy handler omits provider bodies on failure. The opt-in
  M55 worker retains bounded cleaned bodies and validation in private sidecar packs;
  see [audited provider](LLM_AUDITED_PROVIDER.md). Raw bodies and exception text are omitted.

Only an already approved development export should be supplied. Declaring a
partition `validation` does not prove its provenance; this implementation cannot
identify historical final-test contamination or certify input hashes against an
external evidence store. Prediction losses do not establish trading profitability.

## Development export

The input JSON has exactly these fields (timestamps must include a timezone):

```json
{
  "partition": "validation",
  "dataset_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "development_end": "2026-01-02T00:00:00Z",
  "rows": [
    {
      "pair": "BTC/USDT",
      "open_time": "2026-01-01T00:00:00Z",
      "label_end_time": "2026-01-01T00:15:00Z",
      "probability": 0.8,
      "label": 1
    }
  ]
}
```

The hashes and one row above are synthetic format examples, not evidence for any
real model. Real exports must carry the actual hashes from the approved pipeline.
Unknown fields, including free-text logs and artifact metadata, are refused.

## Run

Run from this worktree. Use its installed Python or the existing repository venv
with `PYTHONPATH=src` to ensure imports come from this checkout.

Diagnostics only, no network:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_research_cli \
  --input development-predictions.json --output diagnostics-receipt.json
```

Mock round trip, no network, using the proposal format below:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_research_cli \
  --input development-predictions.json --mock-response proposal.json \
  --output mock-receipt.json
```

A manually initiated free OpenRouter request using the existing JobPilot key:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_research_cli \
  --input development-predictions.json --provider openrouter \
  --jobpilot-env /home/arthur/Projects/personal/jobpilot-ai/.env \
  --output advisor-receipt.json
```

Alternatively set `CRYPTOFORGE_OPENROUTER_API_KEY` in the process environment;
see the secret-free `config/llm-training.env.example`.
There is no automatic dotenv discovery. Invalid responses and HTTP 429 fail the
run with a sanitized receipt, without retries or spending on another provider.
Each invocation can make at most one completion request. A private persistent
request journal (`.local/llm-training-api.sqlite`) now caches exact report/prompt/
model/catalog inputs and reserves a UTC daily quota, default 5, before contacting
the API. Failed and interrupted requests count and cannot automatically repeat.
`--request-ledger` selects the one stable journal; changing it loses the common
budget history and is not a legitimate quota reset. `--daily-max-requests` can
set 1–20 at first initialization; subsequent changes are rejected. This journal
does not monitor other applications using the same JobPilot account. Mock and
diagnostics-only calls do not consume API quota. Scheduling still awaits actual
data qualification and comparative evaluation.

Local Ollama (the model must already be installed; no automatic pull):

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_research_cli \
  --input development-predictions.json --provider ollama \
  --ollama-url http://127.0.0.1:11434 --model nemotron-3-nano:30b \
  --output local-advisor-receipt.json
```

Proposal format:

```json
{
  "schema_version": "llm-training-proposal-v1",
  "hypothesis_id": "check-l2",
  "evidence_ids": ["overall"],
  "rationale": "Check whether regularization stabilizes validation predictions.",
  "expected_effect": "Lower Brier score across development windows.",
  "falsification": "Reject if later development windows deteriorate.",
  "parameter": "l2",
  "value": 0.1
}
```

Allowed parameters: `l2` = 0/0.01/0.1/1; `threshold` = 0.55/0.6/0.65/0.7;
`lookback_candles` = 500/1000/2000. These ranges are an initial proposal catalog,
not approved trading settings or automatic trainer arguments.

## Bounded offline training workflow

The new `cryptoforge.llm_training_experiment_cli` reads development examples with
exactly `schema_version`, `target_version`, `feature_version`, `feature_names`,
`train`, `validation`. No `test` key is accepted. Use:

- `schema_version`: `llm-development-examples-v1`.
- `target_version`: `fixed-future-return-v1`.
- `feature_version`: `candle-v1`.
- `feature_names`: the seven names in `model_training.FEATURE_NAMES`, in order.
- Each row: `pair`, timezone-aware `open_time` and `label_end_time`, seven finite
  `features`, and binary integer `label`. Both training classes are required.

The entire training label interval must end before validation begins. Limits:
2–10000 rows per split, at most 1000 pairs, 100 epochs and 3.5 million feature-fit
operations. Each fit runs as a fixed Python subprocess with CPU ≤10 s, address
space ≤256 MiB, wall time ≤20 s, niceness +10, and only PATH/LANG/PYTHONPATH in its
environment. This is resource isolation for trusted numeric code; it is not a
sandbox for future LLM-generated patches.

The protocol binds the dataset and implementation hashes, epochs, learning rate,
fixed baseline and persistent attempt budget (default 12 per family). It cannot
be silently changed under the same version. The dataset is saved as a private
content-addressed snapshot, containing only train/validation. External source
provenance and the correctness of the exported labels still need qualification.

From this worktree, with a prepared `development-examples.json`:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_experiment_cli \
  --dataset development-examples.json --output protocol.json \
  freeze --version development-v1 --maximum 12 --epochs 50

PYTHONPATH=src python3 -m cryptoforge.llm_training_experiment_cli \
  --dataset development-examples.json --output baseline.json \
  run --protocol protocol.json --ledger .local/training-attempts.sqlite

PYTHONPATH=src python3 -m cryptoforge.llm_training_research_cli \
  --experiment-receipt baseline.json --output advice.json --provider openrouter \
  --jobpilot-env /home/arthur/Projects/personal/jobpilot-ai/.env

PYTHONPATH=src python3 -m cryptoforge.llm_training_experiment_cli \
  --dataset development-examples.json --output candidate.json \
  run --protocol protocol.json --ledger .local/training-attempts.sqlite \
  --advice-receipt advice.json
```

For an offline round trip replace provider/key flags with
`--mock-response proposal.json`. Every output is a new private receipt, never
an overwrite. Repeat an identical configuration with a new output path to read
its cached result (`cached=true`, `training_executed=false`), without fitting.

For this worker, the advisor receives only `l2` and `threshold` as executable
parameters. `lookback_candles` still exists in the broader diagnostic proposal
catalog, but is refused by this worker because changing candle history requires
rebuilding raw inputs. It must not silently mean a different number of training
rows. Threshold selection metrics are counts/class rates of overlapping labeled
observations, not trades or portfolio returns.

The exact validation report must already be recorded as a completed experiment
in the same protocol/ledger before it can justify another candidate. Rewording a
hypothesis or changing its ID cannot create a new effective configuration. A
nonblocking process lock prevents concurrent work on the same ledger. Crashes
leave persistent claims; failed/interrupted fits stay budgeted and require an
explicit investigation, not an automatic retry or deleted journal.

Artifacts use `offline-long-head-v1`, record conservative `fit_information_end`,
standardization, weights, configuration, environment, source/data hashes and
predictive metrics. `production_compatible=false`: they are never submitted to
the production registry.

## Historical implementation snapshot — 15 October 2026

- [x] Separate worktree, baseline `8da4cb17cbf1b6bfef390c57b31cb2148c5eb892`, branch
  `arthur_dev/llm-training-advisor`; only files owned by this implementation.
- [x] Diagnostics, proposal contracts, restricted JobPilot credential reader,
  free-only OpenRouter and local Ollama adapters.
- [x] Persistent API cache/quota/reservations with concurrency protection.
- [x] Frozen development protocol, private snapshots, source/data/environment receipt.
- [x] Existing `ResearchAttempts` integration, persistent budgets, deduplication,
  process lock, failure recording and crash-claim protection.
- [x] Offline long-head worker with resource caps and sanitized subprocess environment.
- [x] Full mock baseline → advice → candidate CLI test, including an actual numeric fit.
- [x] 138 tests passed at that iteration: 97 new advisor/experiment/request tests plus 41 existing
  model-training/snapshot/research-ledger/environment tests.
- [x] One authenticated free OpenRouter completion from the JobPilot key: 1512 tokens
  on synthetic diagnostics. It proposed `lookback_candles=2000`; the offline worker
  correctly refused unsupported candle rebuilding. Advisor catalogs were then
  restricted to the worker's supported parameters; this was checked with mocks.
  No second authenticated request was made.
- Remaining requirement → R02/R03: approved real development dataset, upstream lineage and aligned target contracts.
- Remaining requirement → R08/R09: real equal-budget comparison with/without LLM, untouched final test and paper.
- Remaining requirement → R02/R04/R07/R20: candle-history rebuilding, portfolio metrics and separately admitted new model families.
- Partial mechanisms implemented after this snapshot: common v5 admission, cancellation/cache and narrow arithmetic isolation. Remaining requirements → R06/R16–R19: full scheduling/recovery/accounting and real generated-patch validation; no generic Python runner.

Test command:

```sh
python -m pytest tests/test_llm_training_advisor.py \
  tests/test_llm_training_experiments.py tests/test_llm_research_requests.py \
  tests/test_llm_training_study.py \
  tests/test_model_training.py tests/test_training_snapshot.py \
  tests/test_research_attempts.py tests/test_research_environment.py -q
```

The existing main-checkout venv interpreter was used with imports from this
worktree's `src`. Tests do not certify another agent's uncommitted changes or
production behavior. Synthetic smoke receipts are under the private ignored
`.local/llm-advisor-smoke-20261015/`; their frozen protocol records an earlier source
revision and is intentionally rejected for fitting with later code changes.

## Next integration gate

Reconcile the actual development source and baseline with the main research plan.
Do not label historical test periods as untouched data, and do not infer trading
profitability from synthetic fit or a successful API response. The next study
must freeze its own current source/data/protocol before search begins. No shared
trainer, registry, executor, services or main implementation plan were changed.


## Equal-attempt development replay

`cryptoforge.llm_training_study` compares seeded random control configurations
with a frozen list of external suggestions through the same offline evaluator.
Each arm starts from a fresh baseline and executes the same number of unique
additional configurations. Replay v1 supports one to six suggestions, each
changing one of `l2`/`threshold`, with evidence IDs from overall or validation-pair diagnostics. Baseline-equivalent
or duplicate configurations are refused.

With a prepared development dataset and a JSON array of proposal objects:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_study \
  --dataset development-examples.json freeze --proposals proposals.json \
  --output replay-plan.json --version replay-v1 --seed 42 --epochs 50

PYTHONPATH=src python3 -m cryptoforge.llm_training_study \
  --dataset development-examples.json run --study replay-plan.json \
  --directory .local/new-training-replay
```

The output directory must be new. It retains `study.json`, two private attempt
ledgers, snapshots and `result.json`. The frozen study binds all suggestion text,
configuration order, seed, metric, evaluator protocol and relevant sources.
Changed plans cannot continue the same replay. Failed/interrupted runs retain
partial journals for investigation; this is not an automatic recovery service.

Reports include per-arm attempt count, numeric fit time and validation Brier
scores, without declaring a winner. They explicitly record `independent_evidence=false`,
`profitability_evaluated=false` and `suggestion_origin=external_unverified`.
The external suggestion list can be manual or mocked; replay alone does not
certify that it came from LLM. It also excludes the prior cost/time of preparing
suggestions, so it cannot establish total resource efficiency. No API calls are
made during replay. Threshold-only changes do not change predictive Brier score;
trading effects require a separate economic evaluator.

A real efficacy study still needs approved source data, provenance of LLM
suggestions, multiple predetermined external time windows, all preparation costs
and an untouched final test. These remain open in the main LLM plan checklist.


## Verified historical data export and first real run — 16 October 2026

A new trusted local exporter accepts a primary training snapshot reference:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_development_export \
  --reference source-reference.json --directory .local/new-development-export
```

It verifies the input checksum/counts, archived runtime source checksum, causal
feature contract, target, costs and horizon. It exports only train/validation
into private `development.json` and `provenance.json`, without relabeling,
truncating rows or executing archived source code. To verify the whole-file
checksum it reads the complete local archive; test values are never exported,
scored, sent to the advisor or passed to the numerical worker. Upstream candle
quality/source admission still requires its own audit.

A real historical snapshot was imported: 5180 training and 1060 validation rows,
20 pairs, 5m timeframe, three-candle horizon. The snapshot SHA starts
`21f474ac5de48d77`; the complete reference is retained privately. The accepted
feature list is unchanged; validation now correctly accepts one-character base
symbols such as `W/USDT`. The split limit is 10000 with the same operation and
subprocess resource caps. The first run used 25 epochs.

The existing JobPilot OpenRouter key was used for one free completion on real
development diagnostics: 4073 tokens, fixed Nemotron free model. It proposed
threshold 0.55 instead of 0.60. The candidate completed the registered fit, and
the original proposal, including references to pair evidence, was preserved.
The seeded random control chose the same configuration in a two-attempt-per-arm
historical replay. Baseline and candidate both selected zero validation
observations; Brier was 0.1896353925 and log loss 0.5703459259 for both.
There was no measured development improvement. Threshold changes do not alter
the fitted probabilities, and this run does not establish independent efficacy
or profitability.

Private receipts are in `.local/real-development-20261016/`, including
`export/provenance.json`, `baseline.json`, `advice.json`, `candidate.json`,
`replay/result.json` and `observation.json` with artifact hashes. No active model,
main checkout, service, risk setting or order execution was changed.

The current test command additionally includes `tests/test_llm_development_export.py`.
Earlier verification entries describe earlier iterations; source-bound protocols
and results must not be silently reused after an implementation hash changes.


## Verified suggestion origins and partial preparation costs

Replay schema v2 adds a verified local-journal mode. It reads the original
completed advisor receipts and the API request database in read-only mode,
checks request/response hashes, exact report linkage, provider/model identity,
proposal and saved zero OpenRouter pricing. These checks establish local audit
provenance; they are not an external provider signature or a billing audit.

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_training_study \
  --dataset development-examples.json freeze \
  --advice-receipts advice.json --request-journal .local/llm-training-api.sqlite \
  --output verified-plan.json --version verified-replay-v1 --seed 42 --epochs 25

PYTHONPATH=src python3 -m cryptoforge.llm_training_study \
  --dataset development-examples.json run --study verified-plan.json \
  --directory .local/new-verified-replay --advice-receipts advice.json \
  --request-journal .local/llm-training-api.sqlite
```

Execution rechecks the receipts and journal and requires the newly computed
baseline diagnostics to exactly match the report seen by the advisor. Different
training epochs cannot reuse an origin from another fitted baseline. Manual
proposal lists remain supported, explicitly as `external_unverified`. Schema-v1
archives retain their historical evidence, but are not silently accepted as v2.

A v2 replay on the real historical development export completed with
`suggestion_origin=verified_local_api_journal`. The originating receipt records
4073 tokens and 17.087807 seconds of preparation, reused without a new API call.
Both arms again ran two fresh attempts, with the same threshold candidate and no
measured improvement. Results are private under
`.local/real-development-20261016/verified-replay/`.

The result explicitly keeps `full_search_cost_accounted=false`. Receipt wall
time and provider-reported tokens exclude other preparation, failed searches,
baseline generation and local resource cost. Cached-receipt duration is only the
current CLI duration; it must not be presented as the original full search cost.
Current verification includes `tests/test_llm_advice_provenance.py`: **138 passed**
in the full profile, without additional provider requests.


## Planned TypeSafe extension — 16 October 2026

The main LLM plan now includes section 17 with a separately budgeted TypeSafe/Jev
track. Its first priorities are research-journal structuring, preliminary event
annotation, and an experiment comparing market-only, simple-text and TypeSafe
features under the same ML/evaluator. The generator proposes questions; Jev
supplies narrow typed judgments; the numerical trainer fits weights. Market
outcome labels, limits and execution remain deterministic.

This is planned work, not added runtime capability. Existing document evaluation
does not establish event/feature integration or SDK compatibility. Real TypeSafe
access and free pricing must be checked separately from OpenRouter; no paid
fallback is authorized by the plan update. Historical model knowledge leakage,
prospective evaluation, state/question/model versioning, annotation quality and
full question/API/fit costs now have explicit open checklists. The existing
138-test result remains historical; no implementation or test run was added in
this documentation-only iteration.


## Semantic research catalog: T0/T1 prototype

New modules `typesafe_judgment_contracts.py` and `semantic_research_catalog.py`
implement a local mock-only workflow. The catalog registers completed offline
experiment receipts and checks their artifact/validation evidence. Numerical
records are immutable. Annotations live in separate tables and cannot overwrite
metrics or change the training ledger.

`config/semantic-research-questions-v1.json` asks three independent questions:
mechanism classification, whether the stated conclusion is supported, and
whether the record has enough context. Choice includes unknown; Noul ambiguity
has an explicit abstain state. Score is supported and tested separately. The
starting policy is explicitly uncalibrated and research-only.

Normalized annotation schema v2 stores original question/criteria snapshots,
state/catalog/normalizer hashes, normalized answers and evaluation time. Cache
keys include question meanings, criteria, model fixture revision, schema and
normalizer implementation; changing questions or code cannot silently reuse an
old annotation. All outputs are labelled `origin=mock`, `api_calls=0`, and
`calibrated_policy=false`. Invalid/missing answers are errors, not false labels.

```sh
PYTHONPATH=src python3 -m cryptoforge.semantic_research_catalog \
  --receipt candidate.json --database .local/semantic-research/catalog.sqlite \
  --questions config/semantic-research-questions-v1.json \
  --mock-response semantic-fixture.json \
  --hypothesis 'Lower the decision threshold to select more observations.' \
  --conclusion 'Independent efficacy is not established.'
```

The fixture has one top-level `answers` mapping keyed by question ID. A Noul
answer has exactly `type` and `noul`; Choice has `type`, `choice`, `confidence`
and `probabilities`; Score has `type`, `score`, `confidence` and `probabilities`
with stringified level indices. Probabilities must sum to one. State consists of
a sanitized, explicitly supplied research description and closed-schema
numerical fields; it never automatically ingests raw logs.

A real development candidate was registered privately under
`.local/semantic-research-20261016/catalog.sqlite`. A mock annotation and repeat
cache lookup completed with no external calls. This validates the workflow,
not the semantic correctness of the assigned categories.

SDK inventory found `typesafe-sdk 0.7.1`; Choice/Noul/Score construction and the
system_one signature were checked offline, without instantiating a client.
The official model reference lists nonzero input pricing, while free entitlement
for this account is unverified. Live Jev is therefore not implemented or called.
No package upgrades or changes to shared document-evaluation code were made.

**152 tests passed**: 108 new research tests plus 44 existing numerical/document
evaluation tests. The profile adds `tests/test_semantic_research_catalog.py` and
`tests/test_document_eval.py`. Full live SDK mapping, gold-label annotation
quality, random holdout and semantic retrieval remain open in section 17 of the
main LLM plan.


## Annotation-quality evaluation harness

`semantic_annotation_benchmark.py` freezes an annotation benchmark separately
from the trading test. It requires at least two supplied groups and allocates
whole groups to calibration/annotation_holdout with a fixed seed. Equal state
hashes cannot be assigned to different groups. Group independence is supplied
by the dataset owner; the evaluator does not infer or certify it.

Gold JSON has exactly `schema_version=semantic-gold-v1`, `label_origin` equal to
`synthetic_fixture` or `human_reviewed`, and `examples`. Each example has SHA256
`record_id`, `group_id`, `state_sha256`, and a `labels` mapping containing every
question ID. Choice gold is an option key, Noul gold is yes/no, Score gold is a
numeric rubric level; null means explicitly insufficient evidence. The origin
field is a declaration, not independent proof of human review.

```sh
PYTHONPATH=src python3 -m cryptoforge.semantic_annotation_benchmark freeze \
  --gold private-gold.json --questions config/semantic-research-questions-v1.json \
  --seed 42 --output private-annotation-plan.json

PYTHONPATH=src python3 -m cryptoforge.semantic_annotation_benchmark public \
  --plan private-annotation-plan.json --partition annotation_holdout \
  --output prediction-manifest.json

PYTHONPATH=src python3 -m cryptoforge.semantic_annotation_benchmark score \
  --plan private-annotation-plan.json --partition annotation_holdout \
  --predictions mock-predictions.json --output annotation-evaluation.json
```

The private evaluator plan retains gold labels; never supply it to the proposer
or prediction producer. The public manifest includes only the selected partition
and no labels. Predictions are a mapping from selected record ID to the stored
normalized mock judgment. Missing, extra, wrong-state or wrong-policy predictions
are rejected. Current prediction-origin support is mock only; no live client is
constructed or called.

Metrics report coverage, abstention/errors, accepted-label selective accuracy,
valid-probability binary/multiclass Brier or Score MAE, scored counts and explicit
null denominators. Insufficient gold is not a negative label. Confidence is not
reported as accuracy. The harness does not select thresholds, certify supplied
clusters or establish financial efficacy. Human-reviewed samples and an actual
Jev quality study remain open.

**166 profile tests passed**, including 14 new evaluator tests, in the staging
copy prepared under the current restricted filesystem policy. New work consists
only of evaluator/tests and these documentation updates; no dependency, runtime
or main-checkout changes are required.


## Human-review task preparation and import

`semantic_review_package.py` prepares blank review tasks from verified completed
offline experiment receipts. Source manifests are JSON arrays with
`receipt_path`, `hypothesis` and `conclusion`. Paths can be absolute or relative
to the manifest. Descriptions must be explicitly supplied, approved research
text; the tool does not scrape arbitrary logs or invent labels.

```sh
PYTHONPATH=src python3 -m cryptoforge.semantic_review_package prepare \
  --manifest review-sources.json --questions config/semantic-research-questions-v1.json \
  --directory .local/new-review-tasks

PYTHONPATH=src python3 -m cryptoforge.semantic_review_package complete \
  --package .local/new-review-tasks/package.json --response reviewed-response.json \
  --directory .local/new-completed-review
```

Preparation writes private `package.json` and `response-template.json`. Each
question starts with status pending, value null and reason null. Reviewer ID,
review kind and reviewed-at are unset. Completed decisions must be answered or
insufficient, with an explanation; insufficient requires null, whereas answered
requires a legal non-null value. Missing/duplicate cases, modified states and
incorrect package identities are rejected before gold is written.

For real human review set review_kind to human_review, provide a reviewer ID,
timezone-aware reviewed_at and explicitly declare human_authored and
no_model_answers_shown. This means no semantic predictions for the target
questions were shown; hypotheses and conclusions in the source record remain
material to judge. Review each supplied state, not hidden context from adjacent
records. The importer records the declaration, not proof of identity or
independent adjudication. Synthetic tests use synthetic_fixture and cannot
claim human authorship.

Output `gold.json` follows the benchmark schema, alongside a private
`review-audit.json` retaining response/package hashes, reviewer declaration and
per-question rationale. No output directory or file is overwritten.

A real blank package is prepared under
`.local/semantic-review-tasks-20261016-v1/`: two records, one dataset group and six
pending answers. Baseline and candidate share one dataset, so
minimum_group_count_met is false. The tool conservatively groups identical
datasets; distinct dataset hashes can still overlap and need an independent
cluster/source audit. These two records cannot establish a random independent
holdout. No human labels were generated by the agent.

**181 profile tests passed**, adding 15 review-package tests. Live Jev, annotation
quality and trading efficacy remain unqualified; this iteration has no external
API calls or runtime changes.


## Retrospective experiment retrieval

`semantic_research_retrieval.py` reads the separate semantic catalog without
initializing or writing it. One read transaction verifies every numerical record
against its stored checksum and the shared development-only record schema.
Limits are 1000 records, 64 KB per record, 8 MB total and 32 KB of candidate state.
This is bounded local provenance, not an external signature or source audit.

Preparation runs deterministic BM25 (k1=1.5, b=0.75) over the approved hypothesis
and conclusion. Unicode case folding handles case differences, but does not
translate or stem words. Only positive word matches enter the shortlist; zero
matches returns an explicit empty list. A semantic reranker cannot recover
relevant records missed by this first stage.

```sh
PYTHONPATH=src python3 -m cryptoforge.semantic_research_retrieval prepare \
  --database .local/semantic-research-20261016/catalog.sqlite \
  --query 'threshold validation selection' --limit 8 \
  --output .local/new-retrieval-request.json

PYTHONPATH=src python3 -m cryptoforge.semantic_research_retrieval mock \
  --database .local/semantic-research-20261016/catalog.sqlite \
  --request .local/new-retrieval-request.json --mock-response retrieval-fixture.json \
  --output .local/new-retrieval-result.json
```

Use `--exclude EXPERIMENT_SHA256` to remove the current registered experiment;
it can be repeated, and unknown/duplicate IDs are refused. The shortlist limit
is 1–16. Oversized states require an explicit smaller limit, rather than silent
evidence truncation. Each positive lexical candidate gets a separate Noul
question over its own evidence and the query. All independent questions are
prepared together. A fixture has `answers` keyed by candidate_00, candidate_01,
etc., each with exactly type=noul and a numeric noul value. Empty shortlists
require an empty answers mapping.

Query, candidate records, questions/criteria, catalog snapshot and implementation
hashes are frozen into the request. Mock execution reopens the source catalog
and reconstructs the request: changed facts, added records, rewritten questions
or different code require a fresh request. Accepted yes answers are sorted by
their relevance probability, with original lexical order for ties. Rejection,
abstention and invalid/missing answers remain separate and are not selected.
The 0.2/0.8 acceptance interval is explicitly uncalibrated. The result retains
all candidate statuses and the normalized mock judgment; files are private and
never overwritten. There is no SDK import, inference, automatic fit, catalog
mutation or model activation.

Relevance includes negative evidence and does not certify a conclusion, a
causal explanation or profitability. Records currently lack a qualified
available_at; requests/results declare point_in_time_qualified=false and are
for retrospective research only. They cannot serve as causal historical trading
features. Cross-language semantic recall, real Jev ranking quality, human
relevance gold, latency/cost and operational benefit remain unmeasured.

The real catalog smoke prepared
`.local/semantic-retrieval-20261016-v1/request.json`: one existing record and one
lexical candidate. Its `observation.json` records identical SQLite file hashes
before and after, zero inference/API calls and zero fits. No relevance prediction
was fabricated for this real record. The blank human-review packet remains
unfilled and has only one dataset group.

**199 profile tests passed in 12.26 s**, adding 18 retrieval tests and retaining
the prior numerical, annotation and review tests. Shared training/runtime code
and dependencies were not changed. The implementation follows the
[reranking cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe) and
[Noul guidance](https://docs.typesafe.ai/primitives/noul), without treating the
documentation's demonstration results as trading evidence.


## Offline TypeSafe SDK bridge

`typesafe_sdk_bridge.py` verifies the optional SDK boundary without constructing
a client. Only the installed, checked `typesafe-sdk 0.7.1` is accepted. Missing
or changed versions fail explicitly; the tool never installs or upgrades packages.
Choice, Noul and Score questions are built as actual SDK objects. Application
acceptance thresholds stay outside their wire payloads.

The request snapshots approved state, the full catalog, wire questions, an
explicit fixture model revision, SDK version and source hashes for the bridge,
normalizer and SDK question/response modules. It rejects latest aliases and
stale/reworded requests. These hashes cover the checked subset, not the entire
dependency graph. A declared model revision is not model discovery or account
entitlement verification.

```sh
PYTHONPATH=src python3 -m cryptoforge.typesafe_sdk_bridge prepare \
  --state approved-research-state.json \
  --questions config/semantic-research-questions-v1.json \
  --model jev-1.13.0 --output .local/new-sdk-fixture-request.json

PYTHONPATH=src python3 -m cryptoforge.typesafe_sdk_bridge fixture \
  --request .local/new-sdk-fixture-request.json --response sdk-shaped-fixture.json \
  --output .local/new-sdk-fixture-result.json
```

Both commands are offline; the model argument above is a test declaration. State
must be an explicitly approved JSON object of at most 32 KB. The response fixture
is bounded to 64 KB and has exactly model, usage and answers. Every raw answer
has the primitive's closed field set; Score also requires a legend matching the
requested ordered criteria, with JSON level keys 0, 1, etc. Unknown answer fields
are checked before SDK parsing, because the SDK may ignore extra fields. Noul
confidence is refused. Distribution sums, selected Choice and expected Score
are checked against the research normalizer.

Valid answers are decoded by the real SDK classes and placed in a local
SystemOneResponse. The bridge maps integer Score keys back to the research
schema's string keys. Invalid/missing answers remain errors per question;
unknown question IDs or a different fixture model reject the whole fixture.
Other valid answers survive a per-question failure.

Usage supports input_tokens/output_tokens with nonnegative integers or null;
missing counts remain null. Fixture-reported tokens are retained as declarations,
with usage_is_external_observation=false and inference_cost_evaluated=false.
No actual external usage or zero-price entitlement is inferred from them. Error
text, raw HTTP headers and provider bodies are not harvested.

Results have origin=offline_sdk_fixture, model_identity_assurance equal to
fixture_declaration_only, and api_calls=0. The nested normalized_judgments keep
origin=mock and can exercise the existing annotation evaluator; the integration
is tested on synthetic groups. This is not a live SDK transport or authenticated
provider response. It cannot generate human labels or qualify Jev/trading quality.
New output files are private (0600) and never overwritten.

The existing document evaluator was also tested against a constructed SDK
SystemOneResponse: its scores property, integer probability keys and unknown
output usage are compatible. No edits to shared document-evaluation code were
needed. Live behavior, other primitives and future SDK versions remain separate
compatibility work.

An explicitly synthetic smoke is saved in
`.local/typesafe-sdk-bridge-20261016-v1/`: request.json, fixture-response.json,
result.json and observation.json. Four questions cover Choice/Noul/Score, with
four locally decoded answers and no API calls or fits. The empty human-review
packet and prior real development evidence remain unchanged.

**227 profile tests passed in 12.85 s**, adding 28 SDK-bridge checks, including
an evaluator integration test and guards against network/client construction.
Live transport, verified free access, external budgets, timeouts/retries and
human-reviewed quality gates remain open. This follows the current
[question](https://docs.typesafe.ai/sdk/python/api/types/questions),
[response](https://docs.typesafe.ai/sdk/python/api/types/responses) and
[Score](https://docs.typesafe.ai/primitives/score) references without upgrading
the shared environment.


## Persistent fixture quotas and bounded execution

`semantic_request_journal.py` optionally runs SDK-fixture evaluations through a
separate private SQLite journal. Existing proposer requests and numeric fits keep
their own ledgers; this is not a shared atomic budget across all research work.
Direct local mock/fixture utilities remain available for contract checks.

```sh
PYTHONPATH=src python3 -m cryptoforge.semantic_request_journal \
  --request .local/typesafe-sdk-bridge-20261016-v1/request.json \
  --response .local/typesafe-sdk-bridge-20261016-v1/fixture-response.json \
  --database .local/semantic-requests.sqlite --output .local/new-budgeted-fixture.json
```

The default immutable policy is schema_version=semantic-fixture-budget-v1,
daily_requests=20, total_requests=100, daily_questions=160,
total_questions=1000 and wall_seconds=15.0. Supply `--policy policy.json` only
for a journal's first initialization; subsequent policy changes are refused.
Initialization remains fixed even if the first reservation exceeds a quota.
Changing the database path is not a legitimate quota reset. The dated smoke
journal below is an isolated test, not a replacement for the stable journal.

All questions in a batch reserve capacity together, under BEGIN IMMEDIATE.
Request identity binds the full SDK request, fixture checksum and executor
implementation. An exact completed result is checksum/contract verified and
reused without spawning another worker or charging another reservation. A
changed fixture or request is a new attempt, still subject to lifetime limits.
Concurrent identical calls have one owner; different calls cannot share the
last free quota slot.

Failed, timed_out, cancelled and crash-left reserved attempts count against
both request and question quotas. No automatic retry or ownership takeover is
allowed, including after a UTC-day change. A cancellation already set before
reservation creates no work or journal. Per-question error/abstain within an
otherwise valid SDK fixture stays a typed completed result; execution failure
has no result and cannot be interpreted as a negative semantic label.

Execution uses a fixed trusted Python worker with CPU at most 5 s, address space
at most 256 MiB, niceness +10 and a policy wall timeout of 0.01–30 s. The default
is 15 s; child cleanup has a separate 2 s limit. Wall timeout, cooperative cancel
and KeyboardInterrupt kill/reap the child. A hard parent crash leaves a visible
reserved attempt for investigation. This is resource isolation for trusted
fixture code, not a sandbox for arbitrary generated code or a network sandbox.
The environment contains only PATH, LANG, PYTHONPATH and PYTHONDONTWRITEBYTECODE;
provider keys/settings are not inherited. No client or endpoint is created.

The journal retains identities, timestamps, sanitized outcome codes and valid
normalized results. It does not serialize arbitrary exception messages. A
foreign ledger is refused without changing its contents or permissions. CLI
outputs are new private files (0600) with started and terminal states; success
also includes a budget snapshot. `SemanticRequests(...).snapshot()` reads usage
without initializing a missing database, changing counters or resetting quotas.
It reports includes_external_proposer_or_fit=false.

Requests/questions here describe local fixture work. Fixture-reported tokens
are not measured external tokens and are not charged as such. Existing API
quota, account billing, combined search budgets and fit limits are not certified
by this journal. Future live integration still needs verified free access,
explicit SDK retry control and reservation of every externally attempted call.
The current runner has no retry loop or paid fallback.

Synthetic smoke artifacts live under
`.local/semantic-request-budget-20261016-v1/`: journal.sqlite, first.json,
cached.json, budget.json and observation.json. They reuse the explicitly
synthetic SDK example: one actual worker run and one cache reuse consume one
reservation/four questions, with zero external inference or fits. Neither
Jev quality nor human review was performed.

**252 profile tests passed in 14.52 s**, adding 25 tests for atomic quotas,
immutable initialization, real child timeout/cancellation/reaping, crash-left
reservations, cache integrity, UTC/lifetime limits and read-only usage. The
main checkout, active services, shared dependencies and numeric evaluator were
not changed. Relevant live references are the
[retry policy](https://docs.typesafe.ai/sdk/python/api/retries),
[synchronous client](https://docs.typesafe.ai/sdk/python/api/clients/sync) and
[parallel questions](https://docs.typesafe.ai/cookbooks/parallel_questions).


## Coordinated admission across proposal, SDK fixture and numeric fit

`llm_research_coordinator.py` is a new opt-in entrypoint over the established
handlers. `research_run_budget.py` reserves a common action before invoking an
inner journal. Existing API quotas, semantic worker limits and numeric attempt
history remain independently enforced. The coordinator never alters the trainer,
evaluator, production registry or execution settings.

The reviewed default policy lives in
`config/coordinated-research-budget-v1.json`: 12 actions per UTC day, 24 total,
at most 5 proposal / 10 semantic_fixture / 12 fit attempts and 80 semantic
questions over the journal lifetime. Only free_only=true is accepted. Counts
are admission units, not prices, tokens or interchangeable compute estimates.
A refused first admission still fixes policy and journal bindings.

Pass all three established inner journal paths explicitly. Their resolved path
hashes are frozen alongside policy; rebinding a journal is refused. Retain the
approved research ledgers rather than creating fresh ones to escape their old
history. Common admission starts prospectively; it does not import or certify
all past research or control independent applications/standalone commands.

For an already approved dataset/protocol, substitute its actual journal paths:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_research_coordinator \
  --database .local/coordinated-research.sqlite \
  --proposal-ledger .local/llm-training-api.sqlite \
  --semantic-ledger .local/semantic-requests.sqlite \
  --fit-ledger .local/approved-study-attempts.sqlite \
  --policy config/coordinated-research-budget-v1.json \
  --output .local/new-coordinated-baseline.json \
  fit --dataset development.json --protocol protocol.json
```

Reuse that same global argument set for subsequent commands, with a new output:

- `proposal --experiment-receipt BASELINE.json --mock-response PROPOSAL.json`
  for an explicitly mocked proposal; or replace mock-response with
  `--provider openrouter --jobpilot-env /home/arthur/Projects/personal/jobpilot-ai/.env`
  for a manually initiated existing free adapter call.
- `fit --dataset development.json --protocol protocol.json --advice-receipt ADVICE.json`
  to consume a completed coordinator proposal receipt.
- `semantic-fixture --request SDK-REQUEST.json --response SDK-FIXTURE.json`
  for the offline SDK runner; optional semantic-policy must agree with its
  existing immutable journal.
- `status` for a read-only common usage snapshot, without initializing a missing
  journal or reserving another action.

Ollama uses the prior loopback-only contract, with --provider ollama and explicit
--model/--ollama-url when needed. No cloud entitlement is inferred from JobPilot
settings. Provider credentials are read only within admitted fresh operations;
common cache reuse needs no key lookup. A non-free OpenRouter name or Cloud
Ollama endpoint is refused before admission. Fresh OpenRouter requests still use
the existing catalog price check and zero maximum price controls. Current model
availability/account billing was not probed by this implementation.

Under one BEGIN IMMEDIATE transaction the common ledger checks daily/lifetime
actions, per-kind limits and full-batch semantic question capacity. Competing
kinds cannot both claim the last slot. The inner action starts after common
commit; there is no distributed transaction across four SQLite databases.
Inner rejection leaves a charged common failure. Failed/cancelled/timed_out and
crash-left reserved actions remain counted and cannot be automatically retried.
A new UTC day does not reset lifetime counts or release a failed identity.

Common cache keys include implementation and effective inputs. Fit keys exclude
hypothesis wording; a candidate with the same data/protocol/config remains one
numerical action. Registered validation evidence is checked even before serving
a cached fit. Old inner caches are preserved: an admitted action may use one,
with a conservative outer reservation and zero newly observed work.

Receipts separate original_observed from invocation_observed. A common cache
hit retains its original inner receipt, possibly containing a historical
training_executed=true, but invocation_observed is all zero. Sum invocation
counts for what happened in the current call. A snapshot distinguishes reserved
attempts, observed completed work and unknown work attempts. Failed external
calls are not proof of zero tokens or no provider-side processing. Completion
counts exclude the provider's model-catalog GET and do not measure all HTTP
requests. Missing/fixture usage is never promoted into real billing data.

Outputs are new private files (0600), separate from every journal, with started
and terminal states. The CLI accepts a legacy completed offline fit receipt for
proposal diagnostics, and coordinator fit/proposal receipts for the new flow.
There is no semantic live command, generated-code execution or model promotion.
Common token/time admission accounting is described below. Hard consumption
bounds and external SDK retry/cancellation remain future work; the existing
per-operation time/resource limits stay active.

A complete synthetic staging smoke is archived as JSON reports under
`.local/coordinator-budget-smoke-20261016-v2/`. Four common reservations covered
two actual numeric fits on synthetic rows, one mock proposal and one SDK fixture
worker, with four semantic questions. A renamed candidate reused common cache;
no additional fit or external completion ran. Budget/observation and individual
receipts retain hashes and the source temporary workspace. These are archived
reports, not relocated active journals: path bindings and snapshot paths still
refer to the staging run. They establish the engineering flow, not market
performance, live Jev quality or human labels.

**280 profile tests passed in 25.92 s**, adding 28 budget/coordinator tests.
Coverage includes mixed-kind concurrency, frozen policies/bindings, preservation
of old fit/semantic history and limits, source/evidence checks, mocked provider
journaling, dual-journal timeout and CLI baseline/proposal/candidate/status.
No real provider credentials, production source files or running services were
changed. Current TypeSafe [retries](https://docs.typesafe.ai/sdk/python/api/retries)
and [parallel-question guidance](https://docs.typesafe.ai/cookbooks/parallel_questions)
were consulted; admission and accounting are deterministic code.


## Token and handler-time accounting — 17 October 2026

The same coordinator now applies an additional immutable resource policy in
`config/coordinated-research-resources-v1.json`. Pass
`--resource-policy config/coordinated-research-resources-v1.json` alongside the
existing global arguments; omission uses that default, not an unlimited mode.
A stored custom policy must be supplied identically on subsequent runs/status.

Lifetime allocation defaults are 160000 input tokens, 10240 output tokens and
600000 ms. Each new proposal reserves 32000 input / 2048 output / 65000 ms;
a fit reserves 25000 ms, and an SDK fixture reserves 35000 ms. Allocations are
admission units, not measured tokenization or a hard consumption cap. Every
admitted proposal conservatively reserves tokens even for mock or inner cache;
failures/interruptions do not refund allocation. Outer cache reserves nothing new.
The existing action/question policies and inner quotas remain independently active.

Resource admission and action insertion are atomic in the same common database.
The additive resource tables preserve the old action manifest and all historical
rows. On the first mutating use of an old ledger, existing actions receive
conservative allocations and legacy_unmeasured observations. Old proposal tokens
and wall times remain unknown; no retrospective measurement is invented. Old
history may already exhaust a newly attached policy. Read-only status on an old
ledger reports resources=null / legacy_unmeasured_not_initialized and does not
migrate. Partial tables, missing rows, bad checksums or changed policies fail closed.

Finish or stop old coordinator processes before upgrading source or migrating,
then restart with the new code. Old code refuses the additional tables and cannot
finish its reservation after migration. Implementation changes invalidate old
outer cache keys; old rows stay charged and established inner caches still avoid
new work. Never replace a journal to escape history or retry an interrupted action.

Fresh provider completions populate original_resources.tokens from
[OpenRouter response usage](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
or [Ollama native counters](https://docs.ollama.com/api/chat). Missing, invalid or
inconsistent aggregate values remain null. Ollama prompt_eval_count/eval_count map
to prompt/completion counts; a total is computed only when both are known. No
text-length tokenizer estimate is used. Partial known counts are summarized as
provider_tokens_known_subtotal with unknown_token_actions_by_field. They do not
claim complete accounting or independently audited billing.

original_resources retains the initial handler observation. On outer cache,
invocation_resources has zero new provider tokens and zero handler time. An inner
API cache also contributes zero new provider usage; offline/mock/SDK-fixture
operations contribute zero provider tokens even if fixtures declare token counts.
A failed proposal has unknown tokens since provider processing may be unknown.

handler_wall_ms measures the trusted handler plus result validation/source checks
using a monotonic clock, rounded upward to milliseconds. It excludes CLI setup,
queueing, initial admission and terminal journal commit. Success and ordinary
failure/cancel/timeout are measured; a crash-left reservation has unknown time.
A read from cache still takes real CLI/SQLite time; zero handler time means the
handler was not executed again.

An observed input/output/wall overrun, or a reported total above the combined
input/output allocation, blocks fresh admissions while allowing completed cache.
This does not kill or rewind the overrun. In-flight actions may already have been
admitted. A socket timeout is not a complete round-trip deadline; the generated
output limit is not a hard prompt-token cap. hard_consumption_cap=false and
billing_audited=false remain explicit. Bounded local provider waiting is added below. Hard total runtime/input-token
enforcement, live semantic access and account-wide coverage remain open gates.

A synthetic smoke archive `.local/resource-accounting-smoke-20261017-v1/`
contains two 3-epoch fits on 8 train / 8 validation rows, one mock proposal, one
4-question SDK fixture and one outer cache reuse. Four reservations allocate
32000 input / 2048 output / 150000 ms; measured handler time was 611 ms, with zero
external inference calls and zero reported provider tokens. JSON reports are
archived only; active path-bound journals remain at the staging workspace named
in observation.json. No real model-quality or human-label conclusion follows.

**319 profile tests passed in 19.94 s** (39 new cases), including resource
concurrency, preserved legacy history, immutable policy, unknown/partial usage,
cache accounting, fixture isolation, total-only overrun and mocked provider/CLI
integration. No new live LLM request or credential read was performed.


## Bounded local provider waiting and cancellation — 17 October 2026

Fresh coordinator proposals now run the existing FreeAdvisor in a fixed child
process. The parent keeps ownership of ResearchRequests and both journals:
common admission, inner cache/reservation, then worker launch. The inner request
identity remains unchanged, so old completed advice is reused and an interrupted
request cannot be retried by changing the deadline, UTC day or common database.
Cached advice is not rewritten to add a new execution receipt.

No extra CLI flag is required. The worker waiting budget is
min(65 seconds, resource_policy.wall_ms_by_kind.proposal / 1000). Configure that
existing immutable resource policy before first initialization; a stored policy
cannot be silently changed. The single parent deadline starts immediately before
Popen, covers waiting for startup, credential read, catalog GET, completion POST
and output validation, and is checked between communicate polls (at most 50 ms).
Timeout and cancellation kill/reap the local process, with a separate 2-second
cleanup allowance. Before the common reservation, a set cancel_event causes no
journal or credential read. KeyboardInterrupt is handled as cancellation.

JobPilot dotenv is read inside the worker only after an inner cache miss. The
process environment's selected OpenRouter key, if present, is sent via private
stdin; the child receives no ambient application secrets. Worker settings and
report use bounded JSON (256000 bytes); the response is bounded to 512000 bytes.
The fixed command accepts no user-chosen program or custom Python transport,
stderr is discarded, and no credentials are added to argv/env/files/journals.
Implementation hashes are checked in parent and child and included in the fresh
provider_execution receipt. Output identity binds provider/model/report.

On Linux the worker uses CPU 5 s, address space 256 MiB and nice +10. Inside the
worker evaluation, ITIMER_REAL is armed with SIGALRM explicitly restored to
SIG_DFL; it can still stop stalled evaluation if the supervisor disappears after
sending the request. This is a bounded trusted provider client with network
access, not an OS sandbox for generated code.

Both journals retain timed_out/cancelled attempts and reservations, with no
refund or automatic retry. Token usage after termination stays unknown. A
successful inner/outer cache requires no Popen or credential-file access, even
when the earlier JobPilot file no longer exists. Mock proposals and the separate
semantic/fit workers are unaffected. Standalone FreeAdvisor/legacy CLI calls
are outside this new supervisor.

The guarantee is bounded local waiting, not hard real-time enforcement for the
entire caller. Body preparation precedes the timer; admission and terminal SQLite
commits are outside it. Popen and non-interruptible Python/OS work can only report
expiry after returning. Scheduling and cleanup can add latency. Handler-time
accounting may therefore exceed its wall allocation and block fresh work.
server_cancellation_verified=false and hard_consumption_cap=false remain true:
stopping a client proves neither provider-side cancellation nor final token
consumption/cost. Hard input-token bounds, whole-runtime limits, semantic live
access and external retry policy remain open gates.

**346 profile tests passed in 23.32 s**, adding 27 provider-worker cases. Tests
use real local subprocesses and a synthetic 127.0.0.1 HTTP server, plus a child
with a test-only OpenRouter transport. They cover slow headers/drip, shared
GET+POST time, redirect refusal, malformed/oversized output, minimal environment,
cancel/Ctrl+C/self-alarm, cache without credentials, both journals and CLI timeout.
Loopback socket tests needed the environment's normal reviewed permission path;
no real provider request or user credential was used.

The private archive `.local/provider-deadline-smoke-20261017-v1/` records success,
outer cache, timeout and cancellation. Each scenario made one synthetic loopback
HTTP call, with zero external inference requests and zero numeric fits. The fake
server's declared 12 input / 3 output tokens are fixture data, not real LLM usage;
observation.json marks synthetic_loopback_fixture provenance. JSON archives do
not relocate active journals: the original path-bound databases stay in the
ignored staging workspace named in that observation. No model-quality conclusion
is drawn. Restart old coordinators before applying updated source; retain their
established journals and never reset history to retry a failed action.

Implementation follows [Python process timeout/cleanup documentation](https://docs.python.org/3.12/library/subprocess.html)
and [signal semantics](https://docs.python.org/3.12/library/signal.html).
[TypeSafe retry configuration](https://docs.typesafe.ai/sdk/python/api/retries)
was consulted; no live semantic transport or SDK retry loop was added.


## Exact input bytes and strict verified-limit refusal — 18 October 2026

The shared llm_prompt_preflight module builds the same system/user messages,
catalog and provider body as before. It permits at most **24000 bytes** for
canonical serialized messages and **32000 bytes** for the complete canonical
provider payload, including JSON escaping. Over-limit evidence is rejected,
never silently truncated or selected. These checks run before key reads, catalog
HTTP, process launch and new coordinator/API admission. Mock-only proposals do
not send a provider prompt and retain their separate bounded fixture contract.

Each fresh advice receipt includes input_preflight: report/messages/system/body
hashes, prompt version, implementation hash and exact byte measurements. The
source-bound policy is fixed in code. Native token bounds remain explicit null /
hard_input_token_limit_verified=false / byte_limit_is_token_limit=false. Provider
usage is a later report, not pre-admission tokenization proof. No tokenizer
library, remote tokenizer code or model weights are downloaded by this feature.

To audit a closed diagnostics JSON without credentials, inference or journals:

```sh
PYTHONPATH=src python3 -m cryptoforge.llm_prompt_preflight \
  --diagnostics validation-diagnostics.json --provider openrouter \
  --output .local/new-input-audit.json
```

The new output must not exist and is private (0600). An ordinary audit can be
completed while its native input-token bound is unknown. Adding
`--require-verified-input-limit` instead produces a rejected audit with
verified_input_token_limit_unavailable; it does not estimate or fabricate a bound.
The receipt stores measurements/hashes, not the full outbound prompt.

The same `--require-verified-input-limit` flag is supported by coordinator
`proposal`. It currently permits verified existing cache and refuses a fresh
provider request before creating either reservation. The flag applies to this
invocation, not a persisted global resource policy. Default mode continues to
apply exact byte bounds and the existing free-only/admission controls; it does
not claim a hard native input-token cap.

A strict call first checks the established API cache with mode=ro/query_only.
It verifies schema, stored quota policy, checksums, report identity and proposal.
Missing files are not initialized and interrupted/corrupt entries are not retried.
The fresh-admission guard is checked again under the API writer lock after cache
miss; a stale preliminary lookup cannot cause inference. In that race a charged
common failure may remain, while no new API attempt or worker is permitted.
The CLI records verified_input_token_limit_unavailable as a fixed error_code.
Pre-cancellation takes precedence over the read-only cache lookup.

Inner request identities and message contents are unchanged; adding the guard
must not force new provider calls. Current input_admission describes the current
invocation separately from cached historical advice. A legacy receipt lacking
input_preflight keeps its original fields. Source changes still invalidate outer
cache normally; established inner cache prevents duplicate work. API cache
serialization is now explicitly bounded to the same 512000-byte envelope as the
worker, including readback; larger fresh results fail without storing content.

**375 profile tests passed in 27.33 s** (29 new cases). Coverage includes the exact
byte boundary, escaped Unicode, oversize evidence/timestamps, no-launch/no-quota
refusal, strict cached/uncached paths, corruption and admission recheck, CLI
entrypoints, unchanged request key and bounded cache readback. Existing loopback
worker tests run through the reviewed local-socket permission path; this new
preflight implementation makes no real provider requests.

A read-only historical audit measured 6486 serialized message bytes and 6650
provider-body bytes for the existing 1060-row / 21-group validation report. The
real API journal's bytes were unchanged. `.local/input-preflight-smoke-20261018-v2/`
archives that audit, a strict refusal and a separate synthetic-cache demonstration:
zero HTTP/inference calls, worker launches, numeric fits or credential reads.
One artificial cache row exists only in its explicitly synthetic namespace.
Archived JSON reports do not move active journals or establish model efficacy.

The hard native input-token gate remains open. A verified contract must account
for the full server-side prompt, templates and tokenizer before processing; a
context setting or post-response usage is insufficient. See the current
[OpenRouter chat contract](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
and [Ollama chat contract](https://docs.ollama.com/api/chat).

The next readiness investigation can inspect the local System One option
in [Ollama Decision](https://docs.ollama.com/capabilities/decision) and
[/v1/systemone](https://docs.ollama.com/api/systemone). Local decision requests
need no API key; cloud access is separately paid. Availability, installed model
identity and compatibility are unverified here. No server was started, model
pulled, local semantic inference performed or existing fixture reclassified.


A read-only readiness check is archived as local-semantic-readiness.json beside
the input smoke. The default http://127.0.0.1:11434 endpoints /api/version and
/api/tags were unavailable, no ollama executable was found in PATH and the
standard model-manifest directory was absent. Version/model count stay null.
This checks only the default loopback, not other hosts/containers/custom ports.
No service, model or credential was changed. A compatible local backend remains
an unmet prerequisite; installed models and local semantic inference are unverified.


Local decision metadata and offline wire preparation (18 October 2026)

Run the metadata probe from this worktree with an explicit local model tag:

```bash
PYTHONPATH=src python -m cryptoforge.ollama_decision_readiness \
  --model nimble:latest --output /absolute/new-readiness.json
```

Use `--expected-digest FULL_SHA256` when checking a known pin. The default endpoint
is http://127.0.0.1:11434; custom endpoints must be explicit loopback HTTP IP/port,
including bracketed IPv6. No DNS names, credentials, proxies or redirects are used.
Only /api/version, /api/tags and /api/show are requested, with bounded metadata
responses and socket timeout 0.05–5 seconds. There is no hard total metadata deadline.
The CLI creates a new private file before HTTP; exit 2 means unavailable/incompatible.

The conservative version floor is 0.35.1, covering the documented Clef requirement.
The probe requires an installed exact model tag with a full digest and decision
capability. Cloud names and nonempty/invalid remote_host or remote_model fields are
refused, including custom aliases. metadata_compatible describes server declarations:
it does not prove local weights, successful loading or atomic model identity, and
does not authorize live inference. Without expected digest, pin comparison is null.

The separate offline bridge has prepare and fixture commands only:

```bash
PYTHONPATH=src python -m cryptoforge.ollama_systemone_fixture prepare \
  --state /absolute/approved-state.json --questions config/semantic-research-questions-v1.json \
  --model nimble:latest --model-digest FULL_SHA256 --server-version 0.35.1 \
  --output /absolute/new-request.json
PYTHONPATH=src python -m cryptoforge.ollama_systemone_fixture fixture \
  --request /absolute/new-request.json --response /absolute/declared-fixture.json \
  --output /absolute/new-result.json
```

Inputs must be explicitly approved research state; prepare is not a data exporter.
The pin is a fixture declaration, not installed-model evidence. The wire represents
/v1/systemone, with 1–16 independent questions, no generation controls/tools/images,
and keep_alive=0. Acceptance thresholds stay in ordinary code. State is limited to
32000 canonical bytes and the whole wire to 48000 bytes, with no truncation and no
claimed hard token bound. No optional SDK is needed or upgraded.

Response model/usage/answers follow the current
[Ollama decision types](https://github.com/ollama/ollama/blob/main/decision/types.go),
including exact Score legend and optional prompt_eval_cached_count. Bad/missing
answers become errors while valid companions survive. The existing probability
sum/score tolerance remains strict; rounded documentation examples are not silently
repaired. Cached count is retained without inferring billing or subtracting tokens.
Outputs have offline_ollama_systemone_fixture origin, nested mock judgments, zero
API calls and no external usage or model-quality provenance. Existing SDK/Jev
fixtures keep their identity. These commands create new 0600 output files only.

The 473-test regression profile passed, including 98 new boundary/fixture tests
and four synthetic loopback HTTP scenarios. The archived smoke under
.local/ollama-systemone-smoke-20261018-v1 has four synthetic abstentions and one
actual default-endpoint metadata attempt: backend_unavailable. No inference, fit,
key read, pull, installation or service change occurred; the real API ledger hash
was unchanged. Only JSON reports are archived, with no moved journals.

Live semantic execution remains gated on an installed compatible backend, a new
explicit action kind and versioned common-budget migration preserving history,
supervised execution, input/deadline enforcement and model-change protection.
Do not relabel a live action as semantic_fixture or reset ledgers. Human gold,
calibration, independent holdout and trading-training benefit remain unproven.
See the current [System One contract](https://docs.ollama.com/api/systemone) and
[decision guide](https://docs.ollama.com/capabilities/decision).


Semantic-live budget extension v2 (18 October 2026)

The common budget now has an explicit semantic_live kind, separate from
semantic_fixture. Its default lifetime kind cap is 5 and its per-action admission
allocation is 32000 input tokens, 2048 output tokens and 35000 ms. All four kinds
share the unchanged v1 daily/total action limits and lifetime resource totals.
Live and fixture questions share the existing semantic_questions limit. These
allocations do not establish a hard consumption bound or generation controls.

Stop existing coordinator jobs before upgrading code or extending an active
journal. First migration refuses any status=reserved row, including orphaned
crash reservations. Do not delete rows or reset the journal to bypass this check;
orphan reconciliation remains an explicit unresolved operation. A normally
finishing active handler allows a subsequent migration.

Use the original absolute common/proposal/fixture/fit paths, plus a separate
future live-semantic path and explicit extension policy:

```bash
PYTHONPATH=src python -m cryptoforge.llm_research_coordinator \
  --database /absolute/existing-common.sqlite \
  --proposal-ledger /absolute/existing-api.sqlite \
  --semantic-ledger /absolute/existing-fixture.sqlite \
  --fit-ledger /absolute/existing-fit.sqlite \
  --semantic-live-ledger /absolute/future-semantic-live.sqlite \
  --semantic-live-policy config/coordinated-semantic-live-budget-v2.json \
  --output /absolute/new-migration-receipt.json migrate-semantic-budget
```

Retain `--policy` and `--resource-policy` as well when the existing journal uses
custom v1 values. Both semantic-live options must be specified together and kept
for all subsequent commands, including status. Omitting/replacing either after
migration fails closed. The fifth ledger is only an immutable path binding for
now: no live inner journal or model request is created by migration.

The explicit migration uses one BEGIN IMMEDIATE transaction to validate the
existing schema, manifests, allocations, completed result/observed checksums and
statuses, then adds coordinated_semantic_extension. Original action/policy rows
are unchanged. Pre-resource legacy journals get conservative unmeasured resource
rows atomically; partial or corrupt accounting is refused. A migration receipt
records legacy row count and logical table digests. Repeating the same migration
returns already_migrated without changing database bytes or reserving an action.

The base manifests retain their v1 identity; migrated snapshots use v2 and expose
semantic_extension. Status remains read-only and never auto-migrates. Source
changes still change execution hashes and may invalidate old outer cache keys;
history remains charged and the existing inner journals retain their protections.
With unchanged code, installing the extension preserves reachable prior cache.

Semantic admission shares one transaction with action/resource reservations.
Unknown failed/cancelled/timed-out/crashed work stays charged, with nullable
provider tokens. Cache reuse has zero new observed work. Input/output/total-only
or measured wall overruns block fresh work while completed cache remains readable.
The new kind accepts only local completion counters, never remote or fixture work.
This low-level budget accepts trusted Python handlers, as before; it does not
itself verify transport/model locality, free access or actual usage. No handler
is selected from user text. A fixed local semantic-live transport is introduced
below; migration/status alone never execute it.

535 profile tests passed in 23.34 seconds, including 62 new migration/admission
checks. The synthetic smoke at .local/semantic-budget-smoke-20261018-v1 preserved
four legacy reservations and added one accounting-only action: five reservations,
seven questions and 96000/6144/225000 input/output/ms allocations. Cache, lifetime
refusal, read-only status and idempotent migration were exercised with zero HTTP,
inference, fit, key reads or service changes. The real API ledger hash did not
change. Only JSON reports and the synthetic policy are archived; bound journals
stay in the durable staging workspace and must not be moved or reused as live data.

Supervised local execution and the live inner journal are implemented in the next
step. Real backend verification and full input/server enforcement remain required.
No real journal was migrated. Human
gold, calibration, independent annotation holdout and training benefit remain open.


Fixed local System One worker (18 October 2026)

The coordinator now offers an explicit semantic-live command, guarded by the
existing v2 common budget and a separate persistent inner journal. It never runs
automatically. Prepare/migrate the original common journal as described above,
then use a registered validation record and a full installed leaf-manifest digest:

```bash
PYTHONPATH=src python -m cryptoforge.llm_research_coordinator \
  --database /absolute/existing-common.sqlite \
  --proposal-ledger /absolute/existing-api.sqlite \
  --semantic-ledger /absolute/existing-fixture.sqlite \
  --fit-ledger /absolute/existing-fit.sqlite \
  --semantic-live-ledger /absolute/semantic-live.sqlite \
  --semantic-live-policy config/coordinated-semantic-live-budget-v2.json \
  --output /absolute/new-semantic-receipt.json semantic-live \
  --catalog-database /absolute/approved-research-catalog.sqlite \
  --experiment-id FULL_EXPERIMENT_SHA256 \
  --questions config/semantic-research-questions-v1.json \
  --model-digest FULL_INSTALLED_LEAF_SHA256 \
  --endpoint http://127.0.0.1:11434
```

Keep custom --policy/--resource-policy values when already bound. The optional
semantic-live --request-policy file freezes the inner request/question/wait policy
on first use. Defaults are 5 requests per UTC day and lifetime, 80 questions per
UTC day and lifetime, and 30 seconds of client waiting. Inner requests are bound
to both the common configuration/path hashes and their own absolute journal path.
Do not relocate/reset these databases. No model, server or real ledger was prepared
or migrated by this development iteration.

This executable profile accepts only the source-checked Ollama version 0.40.5.
It generates sha256-FULLHEX:local and uses that native local reference for both
show and System One, avoiding a mutable display tag. It checks version before and
after the call, decision capability, remote metadata and selected manifest identity.
Only a single pinned leaf is accepted; cloud, tag fallback and unknown profiles
are refused. This trusts the compatible server/model store and is not runtime
attestation. See the pinned
[resolver](https://github.com/ollama/ollama/blob/v0.40.5/server/model_resolver.go) and
[manifest implementation](https://github.com/ollama/ollama/blob/v0.40.5/manifest/paths.go).

Only a bounded checksum-verified validation record from SemanticResearchCatalog
is sent. Extra fields/test partitions are refused. Hypothesis and conclusion must
already be sanitized by the catalog owner; a typed shape cannot prove upstream
lineage or detect every secret in free text. State is capped at 32000 canonical
bytes and the complete wire at 48000 bytes, without truncation. There are 1–16
independent Choice/Noul/Score questions with thresholds kept in ordinary code.
The transport neither claims nor establishes a hard input-token cap.

Common admission precedes inner reservation; inner commit precedes worker launch.
There are no retries, key reads, environment proxies, DNS, redirect following,
pull/install/start, remote fallback, custom commands or generated-code tools.
Fresh success performs two version GETs, one show POST and one System One POST.
A fixed subprocess owns the HTTP call with one parent monotonic waiting deadline,
an independent child SIGALRM, client CPU 5 s/address-space 256 MiB/nice +10, and a
separate 2 s kill/reap allowance. Effective wait fits the common wall allocation,
up to 30 s. Client cleanup does not prove cancellation at the server or limit its
CPU/GPU/RAM/model loading. Preparation/admission/final SQLite writes are outside
the complete waiting guarantee; a hard deadline for the whole coordinator is open.

The parent validates the raw response and persisted cache again. Invalid model,
envelope or usage fails the attempt; an invalid/missing individual answer is an
error while valid companions survive. No failure becomes a false label or zero
feature. Exact Score legend and the prior strict probability/expectation checks
remain in force, with no silent repair. Results have ollama_local_systemone origin,
HTTP-observed transport and provider-reported usage, with no quality/calibration
or independent-trading claim. Mock-only benchmark/retrieval entrypoints retain
their gates. A synthetic server can exercise the same protocol without model weights.

Completed inner cache requires no worker, socket or credentials. A new outer
reservation that hits inner cache remains allocated but records zero new completion
and tokens. Failed/cancelled/timed-out/reserved attempts remain charged in both
journals, with unknown provider tokens where the outcome is unobserved. A refusal
at inner admission does not refund the already committed common reservation.
Fields inside result describe original work on outer cache reuse; use the outer
invocation_observed/invocation_resources for this invocation. Common status reports
budget_does_not_infer_transport_readiness instead of inferring availability from v2.

The inner inference key binds the actual wire, endpoint, model digest and server
profile, rather than executor code or acceptance thresholds. Updating the executor
does not repeat completed or failed inference. Historical execution hashes remain
in the saved receipt. Changing only code-side thresholds re-normalizes the same raw
response; source_request_sha256 preserves its original preparation separately from
the current request hash. Changed state/instructions/criteria change the wire and
consume a new request if admitted.

594 profile tests passed in 28.37 s, including 59 new checks. The archived smoke
under .local/semantic-worker-smoke-20261018-v2 has three synthetic System One POSTs,
ten synthetic HTTP requests and three reaped clients, including timeout/cancel in
both journals. Its normal namespace has three common reservations and one inner
reservation; allocations are 64000 input/4096 output/95000 ms. Setup fit is only
an accounting fixture: actual fit count is zero. Synthetic usage is not external
model/billing evidence. A separate real default-endpoint metadata probe stopped
after one GET with backend_unavailable. Installed-model inference count is zero,
the real API ledger hash is unchanged, and no keys/models/services were changed.
Only JSON reports/configs are archived; bound SQLite journals stay in durable staging.

An installed compatible backend, real digest/model-loading verification, native
input bounds and server resource/cancellation checks remain open. Human gold,
calibration, independent holdout, retrieval utility and trading-training benefit
remain required before using semantic features or changing a trading model.


Local CPU backend preparation and capacity check (18 October 2026)

The next backend candidate is tev1:0.8b-q8_0, an explicit llama.cpp/GGUF leaf.
The generic 0.8b tag can select different platform manifests. The checked public
leaf-manifest digest is
sha256:abc31fdb0bf52506cc47091145ac19c4cfb509b73a6841789324f9e32200c099.
Its pin is metadata evidence; installed blobs/model execution are not verified.
JobPilot still points to https://ollama.com with nemotron-3-nano:30b. That is cloud
configuration, without verified free decision access. It is not a substitute for
this local backend. No JobPilot configuration or credentials were changed.

Run the new offline command before planning a cold isolated CPU installation:

```bash
PYTHONPATH=src python -m cryptoforge.ollama_local_preparation \
  --profile config/ollama-local-preparation-v1.json \
  --storage-directory /absolute/existing/proposed/storage \
  --output /absolute/new-capacity-receipt.json
```

The storage directory must exist and should be on the actual installation/model
filesystem. Nothing is created inside it. Capacity uses filesystem free bytes,
Linux MemAvailable, and the minimum finite memory.max headroom across all readable
cgroup v2 ancestors. The real exempt root is recognized using its root-only kernel
interface; missing/unsupported hierarchies remain unknown. GPU execution
is not probed or assumed; swap is reported separately and never counted as RAM.
The command reads no credentials, performs no network/process operations, does
not start a server, and touches no research budgets. Output is 0600/O_EXCL;
existing receipts are preserved. Exit 2 means blocked or needs_measurement;
exit 0 means only preparation_resources_plausible, not permission or verified
readiness for live inference. Observations reserve no capacity.

The checked profile pins Ollama 0.40.5 Linux amd64 archive at 1438684604 bytes and
sha256:dc5eabc292f9949546c90a97c820f924b035e05243b0de13c7f366182562169c.
The complete cold model store is 833607645 bytes. Project policy allocates
2 GiB working RAM plus 1 GiB host headroom and keeps 2 GiB disk headroom. These
are conservative planning choices, not measured vendor/runtime requirements.
Cold disk adds archive + model files + a separate unpacked runtime + headroom,
without assuming cache reuse/deletion. Unpacked bytes remain null until measured;
never substitute archive size for extracted size. Update the reviewed profile
only with evidence, retaining its earlier version and receipts for comparison.
Do not reduce margins merely to turn this gate green.

The final snapshot recorded 984727552 available RAM bytes and 4000923648 free disk
bytes. The result was blocked by both project policies: disk already falls below
the known 4419775897-byte lower bound before adding unpacked runtime. cgroup
inspection found no finite memory.max across six levels; that does not install a
server limit. Extraction size remains unknown. ollama_in_path=false only checks PATH;
it does not inventory all binaries, stores, containers, ports or remote hosts.
Do not stop other work or remove its files to make room.

The remaining sequence is:

1. Obtain suitable host/storage capacity and verify the full extraction size and
   applicable cgroup limits. Repeat the offline command on that filesystem.
2. Download the exact official runtime into a separate workspace, check the actual
   archive hash, extract with path/size controls, and verify all pinned model blobs
   and the full leaf manifest. Metadata SHA alone does not verify downloaded bytes.
3. Start a separate loopback backend without system/global or JobPilot changes,
   with an isolated model store, cloud disabled, one loaded model and one parallel
   request. Verify actual server RAM/CPU/queue controls; client RLIMIT is not enough.
   A separate endpoint such as 127.0.0.1:11435 avoids assuming the default port is free.
4. Check metadata/version/native digest selection first. Then use the persistent
   v2 coordinator/inner journals for one approved registered development record.
   Preserve prior limits/history and resolve old active reservations before migration.
   Do not spend a real attempt on a backend known to be unavailable.
5. Measure actual model loading/response, reported usage, latency and cancellation.
   Native input enforcement, human gold, calibration, independent holdout and bot
   training utility remain separate open gates. Small Tev1 is a capacity candidate,
   not validated semantic quality or a promoted trading feature.

The capacity check and profile are advisory and are not implicitly inserted into
coordinator execution. The existing worker still enforces its exact version,
loopback and digest contract. This new standalone module changes no coordinator
source fingerprints, request keys, journal schema or active policies.

The archive .local/local-backend-preparation-20261018 contains metadata, sanitized
JobPilot settings, capacity-current.json and observation.json, with no SQLite files.
There were four successful public metadata GETs and two failed sandbox DNS attempts;
the operational capacity check downloaded zero runtime/model content bytes and
performed no installed-model inference, research fits or service changes. Synthetic
test fixtures are excluded from those operational counts.
The actual API journal hash stayed unchanged. The full profile passed 621 tests in
33.34 s, including 27 new checks; synthetic HTTP fixtures are not model evidence.

Official references: [Tev1 CPU leaf](https://ollama.com/library/tev1:0.8b-q8_0),
[release assets](https://github.com/ollama/ollama/releases/expanded_assets/v0.40.5),
[Linux installation](https://docs.ollama.com/linux),
[Decision API guide](https://docs.ollama.com/capabilities/decision), and
[Ollama memory/concurrency](https://docs.ollama.com/faq), and
[kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html). The model card notes that
non-English inputs, calibration and prompt injection need further evaluation.


Development source revisions and as-of text views (18 October 2026)

semantic_source_snapshot is an independent offline data-preparation tool. It reads
an already approved bounded development export; it does not fetch a news feed,
call an LLM, propose factual exchange events, train a model, reserve an inference
budget, or change trading. The current semantic-live worker accepts closed research
records, not this source state. No automatic bridge was added.

The source policy fixes the exact bybit-announcements host to
announcements.bybit.com. It permits local import only; it does not establish that
any source was downloaded or factually verified. Existing announcement_sources and
historical_event_review modules were inspected and remain unchanged. Their source
publication dates do not establish when our system obtained a specific revision.

An input export has schema_version=semantic-source-export-v1, origin=synthetic or
collector_export, partition=development, and observations. Every observation must
provide exactly these fields (nullable values must still be present):

```json
{
  "source_id": "bybit-announcements",
  "source_item_id": "synthetic-notice",
  "source_url": "https://announcements.bybit.com/en/article/synthetic-notice/",
  "title": "SYNTHETIC notice",
  "original_text": "SYNTHETIC example text; no real exchange event is asserted.",
  "published_at": "2026-10-18T10:00:00+00:00",
  "source_revision": null,
  "revised_at": null,
  "first_seen_at": "2026-10-18T10:00:00+00:00",
  "received_at": "2026-10-18T10:01:00+00:00",
  "recorded_at": "2026-10-18T10:02:00+00:00",
  "capture_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

The example's capture hash and times are fixtures. A real exporter must record the
actual raw artifact hash and capture times. collector_export is only a caller
assertion: raw artifact contents, signatures, clock integrity, source coverage,
privacy and upstream development lineage are not verified by this tool. Do not
relabel synthetic records or current historical downloads as prior observed data.
Keep date-only/unknown source publication metadata null instead of inventing an
instant, and retain the original raw metadata separately in the future collector.

```bash
PYTHONPATH=src python -m cryptoforge.semantic_source_snapshot \
  --output /absolute/new-source-snapshot.json snapshot \
  --policy config/semantic-source-policy-v1.json \
  --export /absolute/approved-development-captures.json

PYTHONPATH=src python -m cryptoforge.semantic_source_snapshot \
  --output /absolute/new-source-view.json as-of \
  --snapshot /absolute/new-source-snapshot.json \
  --decision-time 2026-10-18T10:02:00+00:00 \
  --ttl-seconds 3600
```

Known first_seen <= received <= recorded must hold. When all three local times
exist, available_at is the maximum of them plus any known publication/revision
time. A future publication/revision can delay eligibility; an old publication
cannot backdate a newly received revision. Any missing local time leaves
available_at=null/unknown_local_capture_time and quarantines that capture from the
view. Missing source dates alone do not erase trustworthy declared local times.
Known timestamps require timezone; all are normalized to UTC.

The snapshot stores original title/text and every provenance observation, including
exact repeats. Document identity uses source+item; content uses exact title+text;
text revision uses document+content; observation uses the whole normalized record.
Input row order and equivalent timezone offsets do not affect the snapshot. Policy,
normalized export and implementation hashes are frozen and rebuilt before a view.
Changing code requires a new snapshot under the reviewed implementation; preserve
previous files. New output files are 0600/O_EXCL and existing files are not replaced.

A view uses only known captures available at or before decision_time. For each
document, the latest such observation wins; provider version labels are not sorted.
Two different latest texts at the same time give ambiguous_revision, with no older
fallback. A later known reversion can select old text without resetting its age.
Unknown/future observations do not add texts, counters, IDs or absence flags to
model_state. The source snapshot checksum is audit provenance and can change with
archive growth; compare model_state_sha256 for the historical payload invariant.

Exact content copies are grouped after time filtering. All provenance remains in
the snapshot/documents; model_state has one text with document/observation references.
Whitespace/title differences are deliberately distinct. No paraphrase or semantic
event-cluster claims are made. TTL is an integer 1..604800 seconds, measured from
the first known availability of that exact content across all visible captures.
Re-fetching a page or copying it under another item/source does not refresh TTL.
The endpoint is inclusive; expired content gives expired_exact_content and no old
revision fallback. It is a view of known captures, not a live-page completeness
claim or a guarantee the publisher has not made an unseen edit.

source_coverage_verified=false and empty_view_is_negative_label=false. Empty texts
mean no eligible captures in this archive, never a negative event label or a zero
feature. Coverage/failure receipts and the feature mapper's missing policy must be
implemented before any training integration. The tool assigns no asset, sentiment,
event type, trade return, TP/SL, or calibrated semantic judgment.

Bounds: 1–1000 observations, title 1024 UTF-8 bytes, text 32000 UTF-8 bytes, URL
2048 bytes, canonical capture 64000 bytes, input export 8 MB, snapshot 16 MB and
view 32 MB. No truncation. URLs must use the exact allowlisted HTTPS host with no
userinfo, query, fragment or explicit port. These limits are not a model input-token
cap or a privacy guarantee for free text. Source artifacts are private local data,
not automatically approved outbound prompts. No existing coordinator input contract,
source fingerprints, quota manifest or budget journal is changed.

The v2 synthetic smoke archive .local/semantic-source-smoke-20261018-v2 contains a
policy, two exports, two snapshots, four views and an observation report, no SQLite
files. Six CLI subprocesses tested seven captures, delayed correction, an exact
copy/repeat, an unknown clock and conflicting versions. Adding future records kept
past model_state unchanged. After correction one fresh text remained; after expiry
none did, without asserting source completeness or a negative event. Twelve CLI
invocations ran across both smoke versions; the first version remains only in the
staging workspace. Counts exclude synthetic pytest fixtures. No real source fetch,
LLM inference, research fit, model/service change or real-journal mutation occurred.

689 profile tests passed, including 53 new checks and 15 existing source/review
checks in addition to the previous 621-test profile. Final duration is recorded in
observation.json. Real collector/clock/raw-artifact lineage, semantic event/asset
annotations, human gold/calibration/holdout, feature as-of joins, independent event
splits and comparative bot-training benefit remain open. T0/T1 prerequisites are
not bypassed by this independent T2 data-contract work.

TypeSafe [state guidance](https://docs.typesafe.ai/concepts/state) and the
[feature discovery cookbook](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery)
were consulted. Exact time/identity checks remain ordinary code; the cookbook's
wine-review results are not trading evidence.


Explicit real article capture and verified export (18 October 2026)

The new collector obtains one explicitly selected official English Bybit article.
It is separate from the bulk historical-source scripts and does not crawl a feed,
schedule work, classify events, call an LLM, fit a model, or change any trading state.
The existing source policy and snapshot implementation remain unchanged.

```bash
PYTHONPATH=src python -m cryptoforge.semantic_source_collector capture \
  --directory /absolute/new-private-capture \
  --policy config/semantic-source-policy-v1.json \
  --url https://announcements.bybit.com/en/article/EXACT-KNOWN-SLUG/

PYTHONPATH=src python -m cryptoforge.semantic_source_collector export \
  --capture /absolute/completed-private-capture \
  --directory /absolute/new-private-export

PYTHONPATH=src python -m cryptoforge.semantic_source_snapshot \
  --output /absolute/new-source-snapshot.json snapshot \
  --export /absolute/new-private-export/export.json \
  --policy config/semantic-source-policy-v1.json
```

The capture parent directory must already exist. A capture directory is created
exclusively at 0700, with fsynced request metadata before worker launch. Reusing any
completed/failed/partial directory fails before a new GET. A new explicit directory
can intentionally capture a new revision; there is no global crawl quota or hidden
retry. A crash after admission leaves a partial attempt that cannot be exported or
automatically retried. Output files are 0600/O_EXCL. Capture/verification files are
portable evidence; they do not share the absolute-path bindings of active research
SQLite journals. Do not move or reset those research journals.

Only https://announcements.bybit.com/en/article/SLUG/ is supported. No redirect,
query, userinfo, fragment, explicit port, other domain/language, auth/cookie or
account endpoint is accepted. One GET uses normal verified system TLS, identity
encoding and a fixed user agent. Response must be 200 HTML with 1..2000000 raw bytes.
No body truncation or decompression. Other outcomes receive failure status; they do
not become an empty page or negative event label. No provider credentials or
JobPilot dotenv are read. The fixed worker receives only URL/source hash over stdin
and runs with PATH/LANG/PYTHONPATH/PYTHONDONTWRITEBYTECODE, ignoring environment
proxies and credential variables.

The parent starts one waiting deadline before Popen, up to 15 seconds, and kills/
reaps on timeout or Ctrl+C, with a separate 2-second cleanup allowance. The child
sets its own 15-second SIGALRM, CPU 3 s/address space 128 MiB/nice +10. This bounds
client fetch waiting; parent extraction, filesystem/fsync work and uninterruptible
OS segments are not a hard deadline for the whole command. It is trusted fixed code,
not a sandbox for generated code. No HTTP callback/command comes from page text.

Successful captures contain:

- request.json: exact source URL/policy, implementation fingerprints and request start;
- raw.html: exact received bytes and SHA256 evidence;
- article.json: deterministic extracted title/body and original publication metadata;
- receipt.json: terminal outcome, full-response receive time and raw/article hashes;
- commit.json: link to terminal receipt and time sampled after durable payload commit.

first_seen_at is conservatively the parent's full-body response_received_at for this
capture, equal to received_at. It is not first web discovery, first byte, publisher
Date, or an assertion of earliest observation by all processes. recorded_at is
sampled after raw/article/terminal receipt fsync and directory fsync, then written
to a linking commit marker. It refers to already durable payload, not the marker's
own mtime. Check request start <= received <= recorded; backward clock movement
prevents export. Local order checks do not attest clock synchronization or accuracy.

The existing __NEXT_DATA__ article parser runs only after strict validation of one
supported script, refusing duplicate/nonfinite JSON. Raw HTML is preserved. Extracted
text is a reproducible representation, not an assertion that HTML itself was plain
text. An empty/unsupported/oversized article fails without fabricating a partial
record. Keep source publication raw text separately: only an explicit aware instant
becomes published_at, and day-only/unrecognized date stays null. Source revision and
revised_at remain unknown/not_extracted; ETag, Date or a date inside body is not
promoted to publisher revision time. Item identity hashes the exact source URL;
canonical aliases are not silently merged.

read_capture/export are offline. They verify bounded regular files without file
symlinks, closed checksummed schemas, completed commit, current implementation,
clock order, exact raw/article bytes and parser replay. Rehashed text manipulation
still fails if it cannot be extracted from the raw bytes. This establishes local
integrity under trusted code/files; it is not a publisher signature or protection
against an owner able to replace all evidence and clocks. Finish old collector
processes before code updates. An old implementation profile is refused; preserve
old receipts/source versions rather than repeating GET to hide the old capture.

Export accepts 1..32 explicit captures, at most 16 MB aggregate raw bytes and one
unchanged source policy. It validates the existing snapshot bounds before writing
export.json and verification.json into a new 0700 directory. The sidecar binds the
export to request/receipt/commit/raw hashes and records raw_artifacts_verified and
extractor_replay_verified. Clock synchronization, feed coverage, upstream development
lineage and semantic labels remain unverified/false. The generic source snapshot
still describes collector_export as a caller declaration; keep the raw/audit sidecar
for the stronger local verification evidence. No automatic assurance upgrade or
new acceptance path is inserted into semantic-live/trainer/budgets.

The real archive .local/semantic-collector-real-20261018 contains one capture of the
[official source](https://announcements.bybit.com/en/article/spot-token-delisting-notice--artb21444d650ba/),
its verified export, snapshot, four views and observation. One GET returned 34534 raw
bytes and 1212 extracted text bytes. Raw SHA256 is
a664223a6b2fba565c9993780c23f212a955d121288ba19914bd439575567600.
The source declares publication at 2026-08-05T10:20:12Z, but our full body was received
at 2026-10-18T07:22:02.686366Z and durably recorded at 07:22:02.715247Z. These are
unattested local UTC clock observations. The August view and the view one microsecond
before recorded_at have no text; at recorded_at there is one text. TTL +3601-second
view excludes it. That last view checks policy behavior, not a later source fetch or
forward trading outcome. All processing after the original GET was offline.

726 profile tests passed in 57.34 s, including 37 collector/transport checks. Tests
use mocked HTTPS/synthetic loopback, private subprocess input and real-process
kill/reap; they do not fetch Bybit. Operational counts exclude pytest fixtures:
one source GET, zero LLM inference, research fits, model/service changes or real API
journal mutations. The archive has one raw HTML and 12 JSON files, no SQLite/keys.
It is a functional real transport/data-path check, not evidence of semantic accuracy
or improved trading-model training.

Remaining work: prospective collection/coverage/failure history, collector clock and
publisher revision lineage, privacy/sanitization, asset aliases and typed event
judgments, human gold/calibration/independent groups, full feature as-of joins and
comparative market/simple-text/semantic training studies. A page first downloaded
today does not provide a causal August dataset. An empty view does not prove no
event occurred. TypeSafe [state guidance](https://docs.typesafe.ai/concepts/state)
was consulted; exact acquisition, parsing, time and hashes stay ordinary code.


Closed exact asset candidates and registration time (18 October 2026)

semantic_asset_registry adds an offline closed alias roster for source text. It
does not infer an asset's semantic role, establish global token/contract identity,
assert listing/tradability, classify events, call an LLM or train anything. Existing
market_data/instrument_history, collector/snapshot, coordinator and trading checks
remain unchanged. No populated production default registry is installed.

A definition contains schema_version=semantic-asset-definitions-v1, registry_version,
origin (synthetic or assistant_curated_source_candidates), and assets. Each asset has
an explicit unique namespace asset_id, an uppercase ticker and 1..8 aliases. An alias
has surface, kind (pair/ticker/name), and capture_sha256. Example shape:

```json
{
  "asset_id": "bybit_global:spot:EXAMPLE",
  "ticker": "EXAMPLE",
  "aliases": [
    {"surface": "EXAMPLE", "kind": "ticker", "capture_sha256": "FULL_RAW_SHA256"},
    {"surface": "EXAMPLEUSDT", "kind": "pair", "capture_sha256": "FULL_RAW_SHA256"}
  ]
}
```

The example is a shape, not a registered real asset. IDs are declared namespace
identities. The full raw hash must identify one of the supplied verified captures.
Exact standalone alias spelling must exist in that capture's title/body; a proof
stores field, Unicode-code-point offsets, field hash and source recorded_at. The
source proves the spelling exists, not that a project name actually denotes the
declared asset ID. The namespace/scope is intended Bybit Spot/USDT use, not proof
that all source context is Spot or the pair is executable now.

```bash
PYTHONPATH=src python -m cryptoforge.semantic_asset_registry freeze \
  --definition /absolute/reviewed-asset-definitions.json \
  --capture /absolute/completed-source-capture \
  --directory /absolute/new-private-registry

PYTHONPATH=src python -m cryptoforge.semantic_asset_registry lookup \
  --registry /absolute/registered-private-registry \
  --surface EXAMPLEUSDT --kind pair \
  --decision-time 2026-10-18T15:30:00+03:00 \
  --output /absolute/new-alias-lookup.json

PYTHONPATH=src python -m cryptoforge.semantic_asset_registry resolve \
  --registry /absolute/registered-private-registry \
  --snapshot /absolute/verified-source-snapshot.json \
  --decision-time 2026-10-18T15:30:00+03:00 --ttl-seconds 3600 \
  --output /absolute/new-asset-candidates.json
```

Freeze uses read_capture to verify original raw/receipt/commit/parser evidence. It
writes a new 0700 directory and 0600/O_EXCL registry.json, fsyncs registry+directory,
then samples local registered_at and writes its linking registration.json. Source
capture recorded_at must not be later than registration. A partial registry without
registration marker is unusable; existing files are not overwritten. Time is not a
caller --at argument or publication date. This is local ordering, not external clock
attestation. Current implementation/source fingerprints must match on read; preserve
prior source/registry versions and finish old processes before code updates.

Lookup permits an alias only after max(registry registration, source recorded_at).
A source captured earlier does not make a roster created later historically known.
Choose the frozen version actually available at the decision: using a latest roster
for an earlier decision conservatively yields unknown, and does not automatically
recover an older version. Keep old registry artifacts with frozen studies rather
than replacing them. Registry/source hashes are audit provenance; candidate_state
hash describes the emitted mentions.

Matching is exact and case sensitive, with Unicode word boundaries. No case folding,
fuzzy spelling, Unicode normalization, derived quote variant or default ticker/name
conversion. Pair alias must equal ticker+USDT or ticker/USDT and must itself be present
in source. Register each desired spelling explicitly. A symbol cannot be taken from
inside a larger word or pair. Duplicate aliases within one asset and duplicate IDs
are invalid; one alias shared across different assets remains a collision.

Statuses are unknown, unique_alias, ambiguous. Unknown has no invented candidate;
ambiguous lists all candidates without selecting the first. Even a unique spelling
has only candidate_asset_id. Every result retains resolved_asset_id=null,
requires_context_review=true, context_grounding_verified=false and
can_authorize_trades=false. Source string occurrence does not establish its semantic
role; common words, prices that resemble pairs or reused tickers still need review.
No confidence/probabilities, trade targets, current status or global identity are
fabricated. Registry synthetic origin stays visible separately from source origin.

Resolve first rebuilds the existing source as-of/TTL view, so future/unknown/expired
captures cannot bypass its guards. Known aliases are scanned; a generic uppercase
USDT-pair pattern also emits missing pairs as unknown. Unlisted ordinary names/words
are not exhaustively extracted: lexical_coverage_verified=false. Each mention stores
field/content hashes, code-point start/end and the exact copied surface. Repeated
mentions are spans of the same material, not independent evidence. A registry learned
later does not add name/ticker spans to an earlier view. Source/lexical coverage and
empty-negative-label flags remain false; there are no event labels or training calls.

Bounds: 1..128 assets, 1..8 aliases/asset, <=512 aliases, 1..16 unique capture hashes,
registry <=4 MB and definition input <=128000 bytes. Resolve allows <=16 source text
groups, <=1 MB combined title/body and <=128 mentions. Exceeding a bound fails during
span collection without truncation. These are data limits, not a complete CLI runtime
or native model-token guarantee. Registry evidence records a verified raw check at
freeze; later local reads rebuild stored spelling proofs/checksums, not a new network
fetch or independent raw/publisher/clock attestation. Retain the raw capture reference.

The private archive .local/semantic-assets-real-20261018 contains eight JSON files:
definition, registry/registration, before/after candidate reports, unknown lookup,
source reference and observation. It reuses the previous verified source capture
without new GET or raw copying. Assistant-curated definitions contain two venue
candidate IDs (ES/PONKE) and four exact aliases, not human gold or global token IDs.
Registration occurred at 2026-10-18 15:14:45.837416 Europe/Moscow
(12:14:45.837416Z), after the source recorded_at 07:22:02.715247Z.

At the old source recorded_at, six explicit pair mentions remained unknown. At
registry registration, twelve lexical mentions mapped to two distinct candidate IDs;
zero assets were semantically resolved. A separate MISSINGUSDT lookup stayed unknown.
TTL 604800 seconds was an explicit engineering-smoke choice to inspect the same saved
source, not an approved trading freshness setting. Four operational CLI invocations
performed zero source fetches, LLM inference or research fits. Prior raw artifacts and
API journal hashes remained unchanged. No SQLite/keys are archived; registry artifacts
are portable, unlike active path-bound research journals.

766 profile tests passed in 31.87 s, including 40 new checks for collisions, unknown
and future candidates, exact spelling/kinds, Unicode offsets, context-review gates,
TTL/empty views, malformed/tampered proofs, bounded counts and private offline CLI.
Registration clock sampling after payload fsync was checked. Tests and the real-input
smoke prove lexical/provenance behavior, not asset-context accuracy or bot-training
benefit. Semantic asset/event judgments with no-match/abstention, human gold,
calibration/independent event groups, alias lifecycle/identity evidence, prospective
source coverage and comparative training remain open.

TypeSafe [pre-parsed value extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook)
and [Choice guidance](https://docs.typesafe.ai/primitives/choice) were consulted.
Code owns candidate spans and exact strings; semantic selection requires its own
validated judgment and a no-match option. This step adds no model/API dependency.


Source-bound event review questions and mock composition (18 October 2026)

semantic_event_review prepares a provider-neutral offline packet for ONE exact source
mention and ONE explicit event type. It recomputes the original source as-of/TTL view
and registry candidates. No precomputed candidate report is trusted. Supported focal
types are listing, delisting, hack, unlock, network_upgrade, deposit_halt,
withdrawal_halt, transfer_halt and trading_halt; this is not exhaustive event discovery.

Each packet has six independent Choice questions: asset candidate, source support,
message kind, market scope, event state and supporting evidence chunk. Every question
contains the focal event definition and judges the same occurrence. State contains the
full eligible source, exact focus, all closed focal asset candidates, source context
and exact evidence chunks. Source text is untrusted data, not instructions. Registry
namespace is spelling evidence, not global identity or proof of Spot scope.

All questions include unknown. Asset and evidence choices also include no_match.
Ambiguous aliases expose every candidate (up to fourteen), without choosing the first.
Unknown pairs have only no_match/unknown asset choices. Code never invents an asset.
Future source text or aliases cannot enter model state; audit hashes may change when
a snapshot changes. Preserve the snapshot and registry version known at the decision.

Event states remain asserted, scheduled, negated, hypothetical or not_stated. Source
support distinguishes sufficient, incomplete and conflicting context. Market scope is
spot, derivatives, both, other or mixed, with unknown available. Message kind preserves
announcement, rumor, opinion, advertisement, retelling or mixed. These are source
claims, not external facts. Different wallet/trading restrictions never imply one
another. Event timestamps are not extracted: event_time is null, and publication or
capture time does not become the event's time.

Code splits complete title/body fields into contiguous chunks of 2000 Unicode code
points. Up to fourteen chunks are options with original text, field hash and exact
start/end offsets. This is coarse complete segmentation, not semantic extraction or
event grouping. The model must select ONE supporting chunk or no_match/unknown. Claims
requiring several chunks need review or a later evidence protocol. Copying a real
chunk proves string integrity only, not that it supports the semantic judgment.

Limits: six questions, <=14 closed assets, <=14 evidence chunks, state <=32000 bytes,
structured state/questions <=48000 bytes, packet <=128000 bytes, mock response <=64000
bytes. Oversize fails without shortening text or candidate lists. These are serialized
data limits, not native token or complete runtime/model-resource guarantees. All
confidence cutoffs are explicit code policy; 0.8 in this smoke is an uncalibrated
engineering choice, not a demonstrated error rate or probability of truth.

The packet preserves source/registry origins, snapshot/view/registry/registration/
candidate hashes, policy/catalog/parameters and current implementation fingerprints.
Validation rebuilds it from originals, rejecting changed text, spans, options, policy
or implementation even if a caller recomputes a checksum. This is local reproducibility,
not publisher signatures, external clock attestation or verified dataset lineage.

CLI examples (supply a real eligible mention index and explicit aware decision time):

```bash
PYTHONPATH=src python -m cryptoforge.semantic_event_review prepare \
  --snapshot /absolute/source-snapshot.json --registry /absolute/asset-registry \
  --mention-index 0 --event-type withdrawal_halt \
  --decision-time 2026-10-18T15:30:00+03:00 --ttl-seconds 3600 \
  --minimum-confidence 0.8 --output /absolute/new-review-packet.json

PYTHONPATH=src python -m cryptoforge.semantic_event_review evaluate-mock \
  --snapshot /absolute/source-snapshot.json --registry /absolute/asset-registry \
  --packet /absolute/review-packet.json --response /absolute/explicit-mock-response.json \
  --output /absolute/new-mock-review.json
```

A mock response has schema_version=semantic-event-mock-response-v1, origin=mock,
packet_sha256 and answers. Answers use the existing typed Choice shape (type, choice,
confidence, probabilities). Unknown questions or envelope fields are rejected; missing,
malformed, unknown or low-confidence needed answers abstain. A no_match asset ignores
inapplicable event questions but preserves their answer errors. Incomplete/conflicting
context, mixed focal scope, missing evidence and not_stated do not create proposals.
No-match and absent claims never become negative event labels.

A complete fixture produces only status=review_required and an annotation_proposal
with proposed_asset_id, focal event/state/scope/message kind and copied evidence.
Negation/hypothetical states remain distinct. resolved_asset_id/inference_available_at
stay null; human gold, context grounding, external truth, global identity, calibration,
historical feature availability, coverage, event labels, training features and trade
authority stay false. A source first available earlier cannot backdate a new judgment.
Mock results are never accepted as human or provider inference.

Both commands are offline and create private 0600/O_EXCL outputs. They import no SDK,
read no keys and perform no provider call, fit, install or runtime modification. The
catalog conforms to existing question contracts, but the current local worker accepts
closed validation research records, not source packets. Source integration needs an
explicit new version and the existing coordinator/inner budget/resource checks. There
is no shortcut endpoint or automatic live submission in this module.

825 profile tests passed in 30.42 seconds, including 59 new checks. All nine focal
schemas, distinct claim states, malformed/missing/unknown answers, ambiguity, no-match,
future input isolation, exact Unicode evidence, limits, forged/resealed packets and
private CLI behavior were covered. Scripted fixtures test composition, not semantics.

Five operational CLI prepares reused the existing capture: ESUSDT and PONKEUSDT, each
with separate withdrawal_halt and trading_halt packets, plus a pre-registry ESUSDT
packet with no available asset candidates. Thirty questions have ZERO filled answers.
These engineering examples represent one exact content group, not random holdout or
independent event groups. TTL 604800 seconds is the previous engineering smoke choice,
not an approved trading freshness policy. No new source fetch/provider inference/fit
occurred, separately from synthetic pytest fixtures.

.local/semantic-event-review-real-20261018 holds eight JSON files: five packets,
unfilled annotation tasks, source reference and observation. Prior 21 source/asset
artifacts were hash-verified unchanged; no new raw copy, keys or journal is archived.
The API ledger and existing collector/snapshot/registry/coordinator implementations
remain unchanged. Work is prepared in .local/semantic-event-stage-20261018 and
transferred to the isolated worktree only.

Open: a verified resource-ready backend and budgeted source adapter; actual model
behavior and independent human gold; class/source calibration and abstention; source
coverage and alias lifecycle; event groups and time/annotation availability; frozen
feature mapping and equal-budget market/simple-text/semantic training comparison.
No accuracy, automation benefit, trading benefit or model promotion is established.
TypeSafe [Choice](https://docs.typesafe.ai/primitives/choice),
[State](https://docs.typesafe.ai/concepts/state) and
[pre-parsed extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook)
were consulted for this decomposition.


Budgeted source-packet adapter (19 October 2026)

source_semantic_contracts adds local-semantic-source-request-v2 and the matching
local-semantic-source-result-v2. It carries original source snapshot, registry bundle
and event packet so parent and worker can reconstruct every source/temporal/candidate
check. No fake validation experiment or arbitrary caller state is accepted. Only the
eligible source packet state and the unchanged six typed questions enter model wire;
original snapshots (including audit-only observations) never enter the wire directly.

The existing local request validator dispatches by explicit schema. Record request/
result v1 retains its contract. The fixed worker uses the same checked Ollama 0.40.5
native digest reference, version/show/System One/version sequence, keep_alive=0,
explicit loopback IP and existing client CPU/RAM/deadline/cleanup bounds. No keys,
cloud fallback, DNS/proxies, tools, retries, install/pull/start or paid call is added.
Source request including all originals is capped at 180000 bytes; final wire including
model and keep_alive is capped at 48000 bytes. Oversize fails without shortening
sources, evidence or candidate sets. These are not native token limits or guarantees
of server/GPU resource usage or server cancellation.

ResearchCoordinator.semantic_source and the semantic-source CLI dispatch through the
same semantic_live action kind and existing migrated v2 extension. Common action,
question and resource allocations, then inner persistent admission, both precede
worker launch. Record and source calls share the same inner quotas/bindings; there is
no new ledger, schema migration, quota increase or source-specific reset. The existing
policy remains mandatory. Pre-cancel, missing migration, exhausted common quotas and a
source decision later than local admission time reject before inner execution.

Example for a previously configured/migrated coordinator (paths denote ESTABLISHED
journals; do not replace them to recover quota):

```bash
PYTHONPATH=src python -m cryptoforge.llm_research_coordinator \
  --database /absolute/existing-common.sqlite \
  --proposal-ledger /absolute/established-api.sqlite \
  --semantic-ledger /absolute/established-sdk-fixture.sqlite \
  --fit-ledger /absolute/established-study.sqlite \
  --semantic-live-ledger /absolute/bound-local-semantic.sqlite \
  --semantic-live-policy /absolute/immutable-semantic-v2-policy.json \
  --output /absolute/new-source-receipt.json semantic-source \
  --snapshot /absolute/source-snapshot.json --registry /absolute/asset-registry \
  --packet /absolute/event-review-packet.json \
  --model-digest FULL_SHA256 --endpoint http://127.0.0.1:11434
```

The command does not migrate automatically. Use the previously documented explicit
migration only against the actual existing inactive journal and approved immutable
bindings. This iteration has NOT migrated or used the real journals or run inference.
CLI receipts are private 0600/O_EXCL and cannot replace any bound journal.

Inner inference identity remains endpoint/version/digest/exact wire plus immutable
manifest. Code-side confidence policy changes reuse saved raw responses; provenance
hash changes alone do not repeat identical model work. Fresh outer policy/executor
identities can still consume another common action/allocation/questions before an
inner cache hit. This preserves the common cap; it does not bypass an exhausted
outer budget. The cached invocation reports zero new completion/tokens, while original
provider-reported usage and first response times remain in the historical receipt.
Failures, timeouts, cancellation and interrupted reservations stay charged, with no
automatic retry. Client termination is not evidence of stopped server compute.

Worker/coordinator fingerprints now cover source contracts, event protocol, asset
registry, collector/snapshot/transport/extractor. Historical record v1 caches with the
old seven-file execution profile remain readable; source v2 requires the expanded
fourteen-file profile. Historical hashes are retained, not replaced with new ones.
Unknown/incomplete profiles fail without an inference retry. Rebuild requests and
restart processes after code changes; do not move path-bound active journals.

For source responses the worker samples response_received_at immediately after reading
and parsing the HTTP body, and checked_at after the final version check. Normalization
requires decision_time <= response_received_at <= checked_at. Parent stores the local
finish-transaction time as semantic_journal_finished_at; cache reuse retains it. The
composed review exposes judgment_received_at and journal_finished_at as local clock
observations. They do not attest external time or downstream feature visibility after
commit. inference_available_at remains null and historical feature availability is
false; an annotation obtained today cannot be backdated to an earlier source capture.
Event_time extraction is still absent.

Source composition checks packet/state/catalog/model/inference identities and typed
normalized answers. A mock cannot be relabeled into the source-live format. The same
unknown/no-match, insufficient/conflicting context, mixed scope, missing evidence and
not_stated abstentions remain. Bad individual answers do not retry a completed valid
transport. A proposed asset/event is review_required with copied evidence and mandatory
human review. Negation, hypothetical statements and rumors are preserved as source
claim attributes. Human gold, context/global identity, external truth, calibration,
source coverage, event labels, training features and trade authority remain false.

874 profile tests passed in 37.99 seconds, including 49 new source tests. Fixed
synthetic loopback round trips, both budgets and shared record/source quotas, raw
cache policy reevaluation, old receipts, receipt clocks, malformed/resealed inputs,
no-retry failures/timeout/cancel, source abstention and private CLI were covered.
No installed decision model or semantic accuracy was evaluated by those tests.

Operational preparation reused the saved source/registry/withdrawal_halt packet:
six questions, 11763-byte wire, 44054-byte complete request. No source action was
submitted; the prior thirty annotation tasks are still unfilled. A metadata-only
probe of http://127.0.0.1:11434 attempted one GET /api/version and returned unavailable
(backend_unavailable); no tags/show/System One request followed. That result concerns
only this explicit endpoint, not every possible installed server. Ollama was absent
from the observed PATH.

Read-only cold CPU capacity on 19 October reported 1120010240 available RAM bytes
(~1.04 GiB), below the chosen 3221225472-byte (3 GiB) policy. Disk free was 3140341760
bytes (~2.92 GiB), below the 4419775897-byte (~4.12 GiB) cold lower bound; unpacked
runtime size is still unknown and additional. Status blocked. These are project
planning margins and a point-in-time observation, not measured vendor minima or
reserved capacity. No download, installation, startup, inference or service changes
were performed.

.local/source-semantic-real-20261019 holds five private JSON files: prepared request,
capacity/readiness receipts, prior-source reference and observation. Prior twenty-nine
source/asset/event artifacts were hash-verified unchanged. No raw copy, keys or SQLite
is archived. The real API journal was not copied, migrated or used. Operational source
fetch, inference and fit counts are zero, separately from synthetic pytest activity;
one metadata connection attempt is recorded explicitly.

Open: a verified resource-ready installed backend and an actual budgeted source call;
independent human gold/holdout, domain accuracy and calibration; reliable event and
annotation availability; source/alias coverage and event groups; frozen causal feature
mapping and equal-budget market/simple-text/semantic training. No learning/trading
benefit or model promotion is established. TypeSafe [API](https://docs.typesafe.ai/api),
[Choice](https://docs.typesafe.ai/primitives/choice) and
[pre-parsed extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook)
were consulted for typed wire and closed candidate/evidence handling; no live Jev call
or SDK dependency was added.


Frozen source review frame and two-reviewer disagreements (19 October 2026)

source_review_package is an offline source-specific review workflow. It does not
reuse the T1 record benchmark's single-catalog assumptions: each event packet has
its own closed asset/evidence options and full question rubric. Existing source,
registry, event, worker/coordinator implementations, policies and journals are
unchanged. No model inference, source retrieval or training is performed.

prepare validates 1..64 original snapshot/registry/packet entries, each with an
optional declared_event_group. Task identity hashes the exact model state and
questions without code-side confidence thresholds, so confidence-only variants
cannot multiply sampling units. Related tasks form connected groups through exact
content, capture SHA, URL, document identity or explicit caller links. Links are
transitive and merge only; different declared cluster names cannot force revisions
or the same source apart. Paraphrase/event independence is not inferred or audited.

Group IDs hash member task IDs. An explicit 32-bit seed ranks groups by SHA256;
explicit sample/holdout group counts select without replacement within the frozen
frame. Every task from a chosen group stays in one partition. At least one
calibration group must remain. A zero-group holdout is an explicit engineering
pilot; an empty partition cannot be exported as a valid holdout or negative example.
Frame kind is engineering_examples or declared_population, both declarations rather
than evidence of full feed coverage. Source coverage, sampling preregistration,
semantic group audit and statistical qualification remain false. Even enough groups
numerically do not establish their semantic independence or representativeness.

The frozen package retains originals, task/state/rubric identities, grouping,
partitions, policy and implementation fingerprints. Rebuilding rejects altered
text, forged groups/splits or qualification flags even after checksum resealing.
Only eligible observation identities enter grouping; future audit observations do
not merge groups or leak text into reviewer views. Audit hashes may still change.
This is local reproducibility, not an external signature or lineage attestation.

forms exports one partition with complete eligible source context, exact focus,
source/registry origins and all six independent questions/options. It includes no
model probabilities/predictions, confidence thresholds, gold answers or tasks from
another partition. Unknown/no_match choices stay visible. Two separate blank
responses contain pending/null/null decisions, null reviewer metadata and false
attestations. The agent has not authored human answers. Give reviewers separate
copies of the blind view and one blank form, without showing each other's answers
or model results; the program cannot enforce that operational separation.

complete requires the exact frozen package/view/partition/task/state/rubric hashes
and all questions. An answered value must be in that task's criteria. Insufficient
requires null; both need a nonempty reason. Pending, invented quotes/options,
missing/duplicate tasks, wrong partitions and extra fields are rejected. Reviewer ID
is opaque and bounded; reviewed_at is a declared aware timestamp. Human review needs
explicit human_authored/no_model_answers_shown/independent_of_other_reviewers=true.
Synthetic fixtures must leave all three false. These are declarations only, not
human authentication, independent review verification or trusted time evidence.
Imported values never become audited human gold, training targets or historically
available features automatically.

compare requires different declared reviewer IDs of the same origin and partition.
Each question preserves agreed, joint_insufficient or disputed, with both original
reasons/values. Nothing is automatically resolved by taking the first answer or
majority. Counts include both_answered, agreed_answer, joint_insufficient, disputed
and agreement_on_answered (null with no answered denominator). This is reviewer
agreement, not model accuracy or calibration. Human gold, adjudication, independent
groups, statistical qualification, model quality and training labels stay false.
Unknown/no_match/not_stated/insufficient are not silently converted into negative
market-event labels or future-return targets.

Manifest rows have snapshot, registry, packet paths relative to the manifest and
nullable declared_event_group. Examples below deliberately show a ONE-group pilot,
with no holdout; do not claim it qualifies a model:

```bash
PYTHONPATH=src python -m cryptoforge.source_review_package prepare \
  --manifest /absolute/review-manifest.json --seed 19 \
  --sample-groups 1 --holdout-groups 0 --frame-kind engineering_examples \
  --directory /absolute/new-review-package

PYTHONPATH=src python -m cryptoforge.source_review_package forms \
  --package /absolute/new-review-package/package.json --partition calibration \
  --directory /absolute/new-blind-forms

# Only after a real declared reviewer fills a separate response file:
PYTHONPATH=src python -m cryptoforge.source_review_package complete \
  --package /absolute/new-review-package/package.json --partition calibration \
  --response /absolute/completed-response-a.json --output /absolute/new-imported-review.json

PYTHONPATH=src python -m cryptoforge.source_review_package compare \
  --package /absolute/new-review-package/package.json --partition calibration \
  --response-a /absolute/completed-response-a.json --response-b /absolute/completed-response-b.json \
  --output /absolute/new-review-comparison.json
```

Limits: 64 entries, 8 MB originals/package, 128000-byte manifest, 1 MB response,
2000-byte UTF-8 reasons and explicit bounded seed/sample/holdout counts. Oversize
fails without truncation. Bundle directories are 0700, outputs 0600/O_EXCL and
fsynced; existing files/directories are never overwritten. All commands are offline,
with no provider/key loading, database mutation, fit or runtime/service change.

919 profile tests passed in 40.64 seconds, including 45 new tests for source-linked
grouping, transitivity, no false holdout, deterministic sampling, threshold-only
duplicates, future audit isolation, forged/resealed inputs, blind forms, declared
origins, complete coverage, uncertainty/disagreements and private CLI. Synthetic
responses verify interfaces/counts only. The previous 874-test profile was preserved.

Operational prepare/forms reused the five existing real-source packets. They form
one exact source group, with five tasks and zero holdout tasks. Two forms have thirty
pending decisions each and ZERO filled answers. Seed 19/sample_groups=1/holdout_groups=0
is an engineering choice, not statistical preregistration. No imported reviews,
comparison, consensus or gold artifact was created from real material.

.local/source-review-real-20261019 contains seven JSON files: manifest, frozen
package, blind view, two blank responses, prior-source reference and observation,
plus a Russian review instruction. Prior thirty-four source/asset/event/backend
artifacts were hash-verified unchanged. No raw copy, keys or SQLite is archived.
There were no new operational source/metadata/model requests or fits; the prior
19 October unavailable-readiness/blocked-capacity receipts were read only and not
repeated. The real API journal and main checkout source code remain unchanged.

Open: actual independent human annotation and provenance audit, dispute adjudication,
a broader representative frame and independently audited event groups; an installed
resource-ready backend and actual budgeted model predictions; class/source quality,
calibration/abstention and frozen thresholds; annotation/event availability and causal
features; equal-budget market/simple-text/semantic training. No learning/trading gain
or promotion authority is established. TypeSafe [Confidence](https://docs.typesafe.ai/confidence)
and [Choice](https://docs.typesafe.ai/primitives/choice) informed uncertainty and
closed-choice handling; exact sampling, grouping, labels and counts stay ordinary code.


Research code preview and trusted isolation probe (19 October 2026)

This is the first independent gate of plan section 16.2. It does not complete a
code worker or depend on pretending the blocked semantic backend/human labels are
ready. research_code_preview validates and materializes a diff; research_code_isolation
runs only a fixed trusted probe. Neither exposes candidate execution, compile/import,
model generation, fit, promotion or repository-patch application.

config/research-code-preview-v1.json is a fixed, disabled policy: only the VIRTUAL
research/feature_candidate.py, base <=16000 bytes, diff/candidate <=32000 bytes,
<=8 hunks and <=128 changed +/- lines. Policy changes, broader paths or enabling
execution require a new implementation/version; editing the JSON cannot turn it on.
The narrow proposal schema has origin mock/external_unverified, base text/hash,
diff/policy hash, hypothesis/falsification and unique evidence hashes. Commands,
unknown fields and self-declared verified provider provenance are rejected. Base and
evidence are caller declarations, not a Git/dirty-state or journal attestation.

Only plain unified diffs with one exact a/b path, positive old/new ranges, exact
context and coordinates are supported. No extended Git metadata, renames/modes,
file additions/deletions, binary patches, no-newline markers, zero-range hunks,
fuzzy/whitespace matching, overlapping hunks or no-op output. Use contextual hunks
for insertions. UTF-8 is preserved; only LF separates lines, with a final LF and no
NUL/CR/BOM. Source syntax or semantic safety is not established by matching bytes.

Effective candidate identity hashes base/result/path/policy, so hypothesis or
evidence wording alone does not create new model work identity. The standalone preview itself reserves no attempt. The 20 October v3 extension
below accounts only for an exact preview check; a candidate-execution budget and
execution gate are still required before running proposed code. The preview is never represented as a completed code trial.

A new 0700 directory holds proposal.json, policy.json, preview.json and separate
base/candidate/research/feature_candidate.py copies. Files are 0600/O_EXCL and
fsynced. Existing/partial directories are never overwritten. read_preview rebuilds
and verifies source hashes, implementation and copies, refusing tampering/symlinks.
All file names inside are fixed by code. The main checkout and current worktree
research/trading implementation are never patched by this operation.

```bash
PYTHONPATH=src python -m cryptoforge.research_code_preview prepare \
  --proposal /absolute/bounded-proposal.json \
  --policy config/research-code-preview-v1.json --directory /absolute/new-private-preview

PYTHONPATH=src python -m cryptoforge.research_code_preview verify \
  --directory /absolute/new-private-preview

PYTHONPATH=src python -m cryptoforge.research_code_isolation \
  --directory /absolute/new-trusted-probe-receipt
```

The third command accepts no candidate, executable or arbitrary script. It checks
the fixed local Bubblewrap 0.9.0 / system Python 3.12.3 profile and records binary
hashes before/after. Another/missing profile fails without falling back to a host
Python execution. Its trusted script uses new net/pid/user/mount namespaces,
disabled further user namespaces, new session, die-with-parent, clear environment,
dropped capabilities, readonly /usr/root/proc/dev, an 8 MiB /tmp tmpfs and one
readonly canary. It mounts no project, home/root/run/workspace, control socket,
keys or research/final-test data. /usr is still a broad unaudited runtime mount.

The exact child environment is LANG=C.UTF-8, PATH=/usr/bin:/bin, PWD=/tmp. Bubblewrap
adds PWD; an initial self-check caught that, and the final profile pins its value
and verifies the complete environment. Nine checks observed different namespace
identities, only loopback, hidden home/sockets, exact env, zero effective caps,
NoNewPrivs=1, readonly canary/root and working temporary writes. The host canary
remained unchanged. This is a local trusted-process observation, not proof of a
complete untrusted-code security boundary.

The trusted child sets per-process CPU=2 s, AS=128 MiB, FSIZE=1 MiB and CORE=0.
Parent waits at most 5 seconds and kills/reaps its probe group on timeout with
1-second cleanup grace. Version checking has a separate 1-second wait; hashing,
setup and fsync are outside a complete CLI wall cap. Hard process count, aggregate CPU/RAM, seccomp, runtime
mount audit, security audit and common attempt accounting remain unverified. Do
not reuse these probes as a general execution API. Candidate execution/authorization
is explicitly false even when all observed checks pass.

974 profile tests passed in 39.04 seconds, including 55 new checks. Exact diff
schema/paths/policy/context/coordinates, extended/binary/fuzzy/malformed refusal,
limits/no-op, Unicode/LF, effective identity, private copies/tampering/symlinks and
lack of candidate-side effects were covered. Fixed probe argv, missing/unchecked
runtime without fallback, timeout kill/reap and actual trusted namespace checks
were covered. CRYPTOFORGE_TEST_BWRAP=1 enabled the actual namespace test; without
explicit opt-in that one test skips. The previous 919-test profile was preserved.

Operational CLI smoke prepared/verified a mock virtual diff changing constant
0.0 to 1.0, then ran one separate trusted isolation CLI probe. The candidate source
was only copied, never imported/compiled/executed. It is a mechanical fixture with
no feature or training benefit. Development sanity/debug/pytest probes are separate
from this operational smoke and never run candidate code.

.local/research-code-real-20261019 contains ten private files: proposal, five-file
preview bundle, canary/readiness, prior-source reference and observation (seven JSON,
two private Python text copies and a canary). Prior forty-two source/asset/event/
backend/review artifacts were hash-verified unchanged. No raw research data, keys or
SQLite is archived. Real API journals, prior code/policy files and main checkout
source are unchanged. Operational source/metadata/model requests, candidate executions,
fits, installs and service/model changes are zero; a trusted probe process did run.

Open: a trusted approved research snapshot exporter and development-only inputs;
candidate-execution budgets/no-reset failure accounting (the later v3 extension
accounts only for exact previews); hard process-tree
limits and audited runtime/syscall isolation for untrusted code; fixed independent
syntax/contract/causality/reproducibility/regression tests; budgeted free-only model
patch generation/provenance; numerical pilot/ablation and the same development/
walk-forward acceptance as parameter changes. No automatic apply or trading promotion.
Semantic backend, independent gold/holdout and comparative ML benefit remain open.

TypeSafe guidance keeps exact rules/execution in ordinary code; Jev is not the code
generator or executor. Official Bubblewrap [security model](https://github.com/containers/bubblewrap/blob/v0.9.0/README.md)
and [0.9.0 options](https://github.com/containers/bubblewrap/blob/v0.9.0/bwrap.xml) were
consulted. Bubblewrap provides building blocks; a complete security policy remains
the caller's responsibility. No new API/SDK/dependency was introduced.


Shared preview-check budget v3 (20 October 2026)

research_code_budget adds a distinct code_check kind to the SAME coordinated_actions
and coordinated_resources transaction. It is a preview-only stage, with no candidate
execution API or arbitrary command dispatch. A separately initialized database is
not a way to obtain a clean research quota. Real established journals are neither
migrated nor relocated by the development smoke.

The fixed config/coordinated-code-check-budget-v3.json allows three lifetime checks,
zero input/output tokens and 5000 ms wall allocation per check. free_only is true,
stage is exact_preview_only, candidate_execution_enabled is false. All fields and
JSON types must match the code snapshot; editing JSON cannot enlarge it or enable
candidate execution. The shared daily/lifetime action and total time caps remain
unchanged. code_check consumes no semantic questions or proposal/fit kind slots.

Migration requires an EXISTING v2 semantic common journal and complete resource
accounting with no unresolved/running attempts. BEGIN IMMEDIATE creates one additive
coordinated_code_extension; five prior tables are hashed before/after and kept
unchanged, including prior actions, failures, allocations and semantic policy.
Migration adds no action or completion, and is idempotent/transactional. Corrupt or
incomplete history is rejected without repair/backfill. Configuration freezes the
old bindings/policies, preview policy and nine source SHA values. Omission, changed
bindings/policy or changed implementation fails closed. No automatic upgrade path
or new quota on source change is supplied.

Example commands (use the established journal paths and policy files):

```bash
PYTHONPATH=src python -m cryptoforge.research_code_budget \
  --database /absolute/established-common.sqlite \
  --proposal-ledger /absolute/established-api.sqlite \
  --semantic-ledger /absolute/established-fixture.sqlite \
  --fit-ledger /absolute/established-attempts.sqlite \
  --semantic-live-ledger /absolute/established-local-semantic.sqlite \
  --semantic-live-policy config/coordinated-semantic-live-budget-v2.json \
  --code-policy config/coordinated-code-check-budget-v3.json \
  --output /absolute/new-private-migration.json migrate-code-budget
```

For the same arguments use a new --output and `code-check --preview /absolute/preview`
or `status`. Preserve any existing non-default --policy/--resource-policy too.
Missing journals are never implicitly created by this extension. Receipts are
exclusive private 0600 files, outside input policies/journals/preview bundles.
After migration the ordinary llm_research_coordinator CLI requires BOTH its existing
--semantic-live-ledger/--semantic-live-policy and new --code-check-policy. The Python
ResearchCoordinator constructor accepts code_check_policy. This keeps proposal,
semantic and fit on that same shared budget; it does not implicitly migrate.

check_preview validates the bundle before admission, within its fixed trusted
handler, and afterward, including cache hits. Effective identity is candidate
base/result/path/policy, plus frozen execution implementation/configuration.
Directory copies, hypothesis/evidence rewording and UTC day changes cannot create a
new attempt for the same effect. On cache reuse the original result/preview SHA is
preserved, with current_preview_sha256 reported separately. Tampered copies are
rejected even when an old cache entry exists.

Failures/cancellation/timeout/interruption retain full action/time allocations.
KeyboardInterrupt becomes cancelled; SystemExit/process loss leaves reserved. None
is automatically retried/refunded. Early cancellation or invalid input before
admission does not reserve. Concurrent work competes atomically for the last shared
action/time slot; duplicate in-flight effects do not start a second handler.
Completed cache remains readable after cap exhaustion or a recorded overrun.

The observed model/fixture/fit counters retain their legacy schema. ZERO_USAGE does
not mean a code check did no work: reserved_by_kind counts code_check separately.
The result says attempt_budget_reserved=true for shared_preview_check_only, but
candidate_execution_budget_reserved/candidate_executed/syntax_checked/training_executed
and trade authorization are false. No compile/import/execute or LLM call is hidden
inside validation. Model/evidence provenance remains unverified.

5000 ms is an admission ALLOCATION, not a hard timeout. Monotonic timing measures the
handler; preflight, cached revalidation and SQLite commits are outside a complete
CLI deadline. Overrun is recorded and blocks fresh work. hard_consumption_cap=false;
this adds no process-tree/cgroup control, syscall policy or generic code sandbox.
The existing trusted Bubblewrap probe remains separate and unbudgeted here.

1029 tests passed in 64.84 s, including 55 new budget checks; the previous 974-test
profile was preserved with CRYPTOFORGE_TEST_BWRAP=1 enabling actual trusted namespace
checks. Budget migration/rollback, corrupt history, immutable policy/source bindings,
common caps/concurrency, cache/failure/cancellation, source-copy tampering and
coordinator fit-cache/mock-proposal integration were covered. Four final
operational CLI invocations migrated two pre-existing SYNTHETIC accounting rows,
checked the prior mock preview once, reused its cache, then read status. Final shared
usage: three actions (fit/semantic_live/code_check), two semantic questions and
reserved input=32000/output=2048/wall=65000 ms. The two initial rows deliberately
execute no fit or inference; these reservations are not consumed provider tokens.

An earlier development fixture predates the coordinator integration change. Its
post-change status correctly refused access and left its SQLite bytes/history
unchanged. The final fixture is independent synthetic test data for the final
implementation; both active accounting databases stay at their original staging
paths. They are not copies or resets of a real research ledger.

.local/research-code-budget-real-20261020 archives eight JSON reports only. Prior 52
source/asset/event/backend/review/code artifacts and the real API journal were
hash-verified unchanged. No raw source, candidate copy, keys or SQLite is archived.
Operational candidate execution, source/provider requests, numerical fit, trusted
probe runs, installs and model/service changes are zero; synthetic pytest operations
are counted separately. No learning/trading benefit is established.

Open: a versioned execution budget/gate for actual candidate code, hard resource
limits and reviewed minimal runtime/syscalls, fixed independent control checks,
trusted source/development input exporter, budgeted free-only patch generation and
provenance, numerical pilot/ablation and the same causal evaluation protocol. Human
gold/holdout and resource-ready semantic backend prerequisites remain open.
TypeSafe skill/live index were read; the building guide (.md/plain) was unavailable.
Exact budget/execution rules stay in code; no TypeSafe dependency or API was added.


Trusted cgroup controls and local database isolation (20 October 2026)

research_code_resources is a fixed trusted diagnostic with no candidate, command,
custom environment or arbitrary property/mount API. Its only CLI input is a new
private output directory:

```bash
PYTHONPATH=src python -m cryptoforge.research_code_resources \
  --directory /absolute/new-private-resource-receipt
```

The fixed research-code-resources-v1 policy has candidate execution and shared
candidate-budget integration disabled. The checked profile is systemd
255.4-1ubuntu8.18, Bubblewrap 0.9.0, system Python 3.12.3 and cgroups v2. Runtime
binaries are hashed before/after; unsupported/missing controls return unavailable
without installing software or executing an unrestricted host fallback.

Two fresh user scopes apply MemoryMax=64 MiB, MemorySwapMax=0, TasksMax=8,
CPUQuota=25% with 100 ms period, RuntimeMaxSec=3 seconds, TimeoutStopSec=1 second
and SendSIGKILL=yes. Scope mode preserves the working caller context for Bubblewrap;
early development service-mode probes failed the isolated-network setup and were
cleaned up. Neither namespace checks nor resource limits were relaxed to pass.

A constant trusted launcher validates its own cgroup/unit, then execs Bubblewrap:
all separate namespaces, disabled further userns, die-with-parent/new-session,
clearenv, dropped capabilities, readonly root/runtime/proc/dev, private 8 MiB tmpfs
and readonly access only to its OWN cgroup. Home/run/var/workspace/DB secrets and
control sockets are absent. env -i before the launcher and bwrap clearenv leave
only PATH/LANG/PWD inside. CapEff=0 and NoNewPrivs=1 are checked. /usr is still an
unaudited broad runtime mount; this is not a completed untrusted-code boundary.

Actual kernel controls were read: memory.max=67108864, memory.swap.max=0,
pids.max=8, cpu.max=25000 100000. Writing a controller through the readonly mount
failed EROFS. A bounded fork loop hit EAGAIN and increased pids.events.max; its
children were killed/reaped. The timeout probe waits 30 seconds with a child that
confirms ignoring SIGTERM through a pipe. Scope runtime/stop limits terminate that
whole tree earlier; the supervisor exits on SIGTERM, pipe closes after descendant
termination, and both systemd unit and cgroup disappear.

Only after observing a different network namespace and sole loopback does the
trusted child try 127.0.0.1 ports 54321/55432. Both are refused in its OWN namespace,
without reaching the host database. Host sockets/credential directories are absent.
No real DB connection, cloud fallback or direct worker data query occurs.

Supervisor waiting is at most eight seconds; cleanup is separate. finally stops
only the generated cryptoforge-research-resource-<16 hex>.scope; stop timeout uses
kill all SIGKILL then another stop. Each systemctl call has a three-second timeout,
and supervisor kill/reap has its own one-second allowance. A complete hard CLI wall
cap is not claimed. Ordinary sandbox user-bus denial is an unavailable outcome,
not a reason to run candidate code elsewhere.

1067 tests passed in 59.65 seconds, including 38 new resource checks. The prior
1029-test profile was preserved. Both real opt-ins were enabled; fixed argv/unit
allowlists, bad profiles/outputs/controls, cleanup escalation, interruption and
actual scope limits/tree/local-DB isolation were covered.
The real resource test requires CRYPTOFORGE_TEST_CGROUPS=1, and the older namespace
test uses CRYPTOFORGE_TEST_BWRAP=1. Skipping either is not an observed success.
One final operational CLI inspection runs two trusted scopes; a prior invocation
failed before process launch because its parent directory was absent. Development
and pytest probes are counted separately. No candidate compile/import/execute,
provider/source request, numerical fit, package install or existing DB/service/timer change occurs.
Only short-lived diagnostic scopes are created/removed.

.local/research-resources-real-20261020 contains five JSON reports only: resource receipt,
sanitized local storage context, source reference, observation and verification.
The migration row count is historical evidence, not live freshness. Prior 60
artifacts and the real API journal are hash-verified unchanged. No SQLite, raw data,
DB dump, candidate source or credentials are copied. Existing v3 code budgets,
preview/isolation implementations and their source bindings stay unchanged.

candidate_executed/execution_authorized/shared_candidate_budget_integrated remain
false. Memory OOM and CPU-throttle stress tests, a minimal runtime/syscall security
review, execution budget migration and immutable independent control checks remain
open before untrusted code. A new local-source development export and comparative
ML benefit also remain open. TypeSafe and Postgres skills were consulted; exact
resource/storage policies stay in code and no TypeSafe API/dependency was added.


Independent static feature contract (20 October 2026)

research_code_static adds a deterministic read-only verifier for an already
registered preview. It does not change the nine frozen v3/common/preview source
files, budget policy, extension tables or existing operation identities. No
candidate-execution or new quota path is introduced.

The public review requires a matching COMPLETED code_check in the existing v3
journal. One mode=ro/query_only SQLite transaction validates all previous
manifest/semantic/code/resource bindings, operation key/input/executor and stored
result/observed checksums, including the exact v3 preview result shape. Missing,
unregistered, unfinished, failed or corrupt rows fail before parsing. A missing
journal is not created. Wording/copy changes preserve the original registered
preview SHA and separately bind current_preview_sha256. Completed work can be
reviewed after cap exhaustion without a new action, callback, migration or refund.

This is static postprocessing of a previously counted candidate effect. It neither
repurposes the v3 exact_preview_only stage nor claims a static/execution resource
reservation. registration.scope explicitly says existing_completed_preview_not_static_or_execution_reservation;
new_attempt_reserved=false and static_cost_in_common_resource_journal=false. A
monotonic analysis duration is measured separately. Future isolated validation
needs its own versioned accounting; repeated readonly parsing is not a model fit
or search experiment.

The fixed config/research-code-static-v1.json accepts only one ordinary
candidate_features(window) definition, with exactly one return {'value': expression}.
No defaults, annotations, decorators, async function, extra definitions/statements,
module imports or extra output fields. This is a narrow prototype interface, not a
production trainer or arbitrary feature implementation contract.

Expressions may contain finite literals with magnitude <=1000000, unary +/- and
+,-,*,/, abs(x) and min/max with two to four scalar expressions. The only data
access is window[literal_index]['open'|'high'|'low'|'close'|'volume'] with -64..63.
Calls beyond that set, attributes, assignments, comprehensions, eval/IO, kwargs,
starred arguments, slices and target/future fields are rejected. Literal zero
denominators are rejected; general arithmetic is never evaluated by this checker.

Source is <=32000 UTF-8 LF bytes before Python 3.12 AST parsing. The resulting AST
is limited to 512 nodes/depth 32. Parser/resource/recursion errors produce safe
codes/locations with no source/exception text. AST limits apply after parsing;
this is not a hard parser CPU/RAM/deadline boundary. No candidate bytecode/module,
eval or exec is produced/invoked. Syntax validity alone also does not establish
that code would compile/run correctly in the future executor.

The report includes exact sorted/deduplicated window reads and the minimum window
length; constants need zero. A future trusted exporter/runner must supply up to 64
fully closed candles ordered oldest to newest as frozen primitive values. AST
shape cannot prove actual as-of availability, types, enough rows or numeric safety.
Even a structurally accepted denominator (1-1) is NOT declared numerically valid.
input_availability_verified/numeric_validity_verified/runtime_contract_verified,
independent_dynamic_tests_executed/feature_utility_verified and execution_authorized
remain false. No data is loaded or candidate called to manufacture these proofs.

Source/preview copies are rechecked after review. Import-time fingerprints cover
the static checker, Python ast source and previous common/preview implementation;
changed implementation requires restart. Policy is a fixed versioned snapshot,
not a model-controlled switch to widen the grammar or enable execution.

CLI uses the same established journal bindings/policies as the code-budget CLI,
plus --preview, --static-policy config/research-code-static-v1.json and --directory
for a NEW private output directory. --policy/--resource-policy must preserve any
existing non-default settings. Successful parsing/contract review returns 0;
registered structural rejection writes the report and returns 2. Missing/corrupt
registration fails without initializing a journal. Output files are private 0600,
directory 0700, exclusive and fsynced. The full parameter list is in --help.

1156 tests passed in 68.18 seconds, including 89 new static checks; the previous
1067-test profile was preserved with real namespace/cgroup opt-ins enabled. Grammar,
side effects, parser/source bounds, invalid/forged registration, read-only cap/cache
behavior, implementation/preview changes and private CLI output were covered. One
operational CLI reviewed the old mock constant 0-to-1 preview through its existing
synthetic-accounting-v2/common.sqlite at the original staging path. The journal's
bytes were identical before/after. That mechanical fixture passed with syntax=true,
eight AST nodes, depth four, zero window reads and no numerical/training benefit.

.local/research-static-real-20261020 contains four JSON reports only: review, source
reference, observation and verification. Prior 65 artifacts and real API history
are hash-verified unchanged. No raw/candidate source, keys or SQLite is archived.
There is one explicit read-only SQLite connection and zero operational PostgreSQL,
source/provider calls, candidate executions or numerical fits. Main backend and
local database deployment remain unchanged.

Open: fully isolated syntax/runtime checks with shared versioned resource/action
accounting, a trusted development-only primitive exporter/input binding, immutable
numerical/causality/reproducibility/regression controls, stress/security validation,
real free-only patch provenance and equal-budget development/walk-forward efficacy.
Passing AST review grants neither execution nor promotion. TypeSafe skill/live
index and the official Python ast documentation were consulted; exact checks stay
in code with no new SDK/API dependencies.


Frozen primitive feature inputs and independent control fixtures (20 October 2026)

research_feature_windows prepares input/control artifacts without candidate
execution, model work, database access or new attempts. Existing v3/common/preview/
static/resource implementations and budget identities are unchanged. The fixed
config/research-feature-input-v1.json binds the input/output contract to the static
checker's five candle fields and maximum 64-row window.

The closed capture format declares local_postgresql, Bybit spot symbol/timeframe,
origin synthetic_fixture/external_unverified, an upstream export SHA, capture time,
train/validation partition/development_end and 1..1024 candles within 512000 bytes.
Other backends/markets/test partitions, labels/extra fields and fake verified origins
are rejected. Those declarations are NOT authenticated DB lineage, source-clock
proof, approved temporal split or market completeness; their verification flags
remain false. A trusted actual local exporter is still required.

Each row has aligned whole-second open_time, observed_at and only OHLCV. Supported
timeframes are 60/300/900/3600 seconds. observed_at must be at/after candle close and
no later than capture time; close must not exceed capture/development end. Available
time is max(close,observed). Decisions cannot exceed development_end, and only rows
available by that decision are eligible. Aware times normalize to UTC with integer
epoch arithmetic. No implicit historical availability is invented for data first
observed later. Times are bounded to years 1970..2100.

Rows are sorted by open time; duplicate or revised open times require separate
upstream version history and are rejected here. The last N eligible rows must be
exactly the requested 1..64, contiguous, with the latest close at the current closed
grid boundary. Missing history/latest row/gaps yield unavailable with payload=null
and no window identity. There is no interpolation, zero filling or silent use of an
older window. No absent input is turned into a numeric feature value.

The model window has only plain OHLCV dictionaries. Exact builtin int/float values
are finite; prices >0 and <=1e12, volume >=0 and <=1e15; OHLC range is consistent.
Values normalize to binary64/zero, not exact exchange Decimals. These are prototype
engineering bounds, not financial filters. immutable_window validates/copies to a
tuple of MappingProxyType rows, preventing caller aliasing and mutation. Custom
objects/dict subclasses/nested state are refused. A future runner must pass only
this window, not provenance/metadata or full raw capture.

Output validation accepts only a plain {'value': number}, finite with magnitude
<=1e12. Bool/null/nonfinite/extra fields and custom objects are rejected. It does not
compute any candidate value. Window identity hashes policy plus selected market,
cutoff, times/availability and numeric payload; raw capture/export provenance is
separate. Appending future rows changes provenance without changing a past model
window or its effective identity. Actual selected-window changes are not hidden.

Fixed independent controls contain 13 window fixtures (7 valid/6 invalid) and seven
output fixtures (3 valid/4 invalid): flat/rising/falling/zero volume/full64/extreme
finite inputs and boundary/missing/label/bool/range errors. Validators self-check
the fixed fixtures. This is not execution of candidate tests: candidate_controls_executed,
numerical_or_causal_correctness_proven and execution_authorized stay false. Model
responses cannot replace these cases or their versioned policy.

```bash
PYTHONPATH=src python -m cryptoforge.research_feature_windows prepare \
  --capture /absolute/closed-development-capture.json \
  --request /absolute/window-request.json \
  --policy config/research-feature-input-v1.json --directory /absolute/new-window

PYTHONPATH=src python -m cryptoforge.research_feature_windows verify \
  --capture /absolute/closed-development-capture.json --directory /absolute/new-window

PYTHONPATH=src python -m cryptoforge.research_feature_windows controls \
  --policy config/research-feature-input-v1.json --directory /absolute/new-controls

PYTHONPATH=src python -m cryptoforge.research_feature_windows verify-controls \
  --directory /absolute/new-controls
```

Window files are policy/request/window JSON. Verification rebuilds against the
original capture and checks exact result/implementation. The entire capture is not
mounted/copied to a candidate input directory. Controls verification compares the
saved pack to a freshly generated exact fixed pack. Directories/files are new,
private 0700/0600, exclusive and fsynced, with symlink refusal. Prepare/verify return
2 for an unavailable window; verification does not convert unavailable to success.

1222 tests passed in 84.15 seconds, including 66 new input/control checks; the previous
1156-test profile was preserved with real namespace/cgroup opt-ins. Temporal/future
invariance, late/missing bars, source/market/schema bounds, primitive immutability,
output validation and artifact/CLI integrity were covered. Four operational
CLI invocations prepared/verified a synthetic three-row BTCUSDT window and the
control pack. Two extra direct selections confirmed future-tail invariance and
late-observation refusal. The January synthetic times/values are not a real local
DB export, a candidate numerical/causal test or trading evidence.

.local/research-window-real-20261020 stores seven private JSON input/control/evidence
artifacts, with no raw source export, SQLite or credentials. Prior 69 artifacts and
the real API journal remain hash-identical. Operational database/provider/source
requests, candidate executions/fits, new attempt journals, installs and service/model
changes are zero. Existing research budget history is not reset or relocated.

Open: an authenticated actual local PostgreSQL development exporter and approved
baseline/split/revision/observation lineage, isolated candidate controls with shared
versioned resource/action accounting, reproducibility/causality/regression execution,
stress/security validation and equal-budget numerical efficacy. Preparing this pack
does not authorize candidate execution, production apply or promotion. TypeSafe
skill/live index were read; exact rules stay code with no semantic API/dependency.


## Budgeted arithmetic controls v4 — 20 October 2026

`research_numeric_controls` explicitly seals an existing inactive v3 common journal
for a narrow arithmetic-control phase. Its six v3 tables remain byte-derived hash
identical; two added tables retain configuration/migration and numeric attempts.
Legacy clients fail closed after migration. This prototype then exposes only fixed
controls; proposal/fit/semantic/code-check routes require a future explicit versioned
phase transition preserving every v3/v4 quota and record. Never remove the seal,
copy the database or create a new journal to continue with fresh quota. No working
operational research journal was migrated; the smoke used the established synthetic
accounting database at its original location.

The new `numeric_control` kind uses the same legacy+numeric lifetime/daily counts
and shared resource allocation: maximum three controls, tokens 0/0, wall 20000ms.
Reserve is atomic before the fixed worker. Completed cache rechecks the bundles,
registration, packet and controls, preserving original provenance; cache performs
zero new evaluations/actions. Failed/cancelled/timed_out/reserved attempts retain
quota with no automatic retry. SystemExit leaves a reservation. Prior measured
overrun blocks fresh work while completed cache remains readable. Admission wall
is not a full CLI hard cap; preflight/SQLite/cache/cleanup remain outside that claim.

The independent closed AST is translated to a JSON tree of fixed arithmetic/read
operators. Candidate Python is never compiled, imported, mounted or executed.
`candidate_expression_evaluated=true` explicitly differs from
`candidate_python_executed=false`. The trusted interpreter uses binary64 at every
node, bounded finite intermediates <=1e100 and output <=1e12. It is not Python
arbitrary-precision integer or exact exchange Decimal arithmetic. Numeric errors
produce numeric_invalid. A missing required lookback produces insufficient_window
with no value and zero evaluation attempts. No absent input is filled with zero.

Worker input contains only the closed expression tree, 13 immutable input fixtures,
one selected primitive window and seven output fixtures. Full capture, labels,
provenance, paths and credentials are absent. It runs trusted Python in the existing
systemd user scope/Bubblewrap profile: memory64MiB/swap0/tasks8/CPU25%/runtime3s,
parent wait8s, isolated network/private paths/environment/capabilities and scope/tree
cleanup. Parent verifies packet identity, schemas/counts/order, refusals, numeric
bounds, output cases and two repeated evaluations per applicable window. Repeat is
inside one process, not independent cross-process reproducibility. No oracle for an
arbitrary financial feature or trading benefit is invented.

All options are explicit. Reuse the original journal bindings and policies; run
`migrate` only when intentionally entering the sealed phase. CLI creates an exclusive
0600 output receipt. `check` additionally requires --preview, --window and --capture.
Commands are `migrate`, `check` and `status`:

```bash
PYTHONPATH=src python -m cryptoforge.research_numeric_controls \
  --database /absolute/established-common.sqlite \
  --proposal-ledger /absolute/established-proposal.sqlite \
  --semantic-ledger /absolute/established-semantic-fixture.sqlite \
  --fit-ledger /absolute/established-fit.sqlite \
  --semantic-live-ledger /absolute/established-local-semantic.sqlite \
  --semantic-live-policy config/coordinated-semantic-live-budget-v2.json \
  --code-policy config/coordinated-code-check-budget-v3.json \
  --numeric-policy config/coordinated-numeric-controls-v4.json \
  --output /absolute/new-migration-receipt.json migrate
```

1284 profile tests passed in 86.41 seconds, including 62 new checks with actual
namespace/cgroup tests. Four operational smoke CLI invocations migrated the same
established synthetic database, ran the existing mock constant-one expression,
read its cache and status. Three prior rows became four; semantic questions stayed
two; allocations became input32000/output2048/wall85000ms. Six v3 table hashes stayed
identical. The worker attempted 16 arithmetic evaluations over eight applicable
windows, refused six invalid windows, checked seven output fixtures and removed its
scope/cgroup. Cache used zero new evaluations/actions. No new model proposal,
operational DB read, API request or training fit occurred.

`.local/research-numeric-real-20261020` archives eight private JSON reports, no active
SQLite/raw capture/candidate source. Prior 76 artifacts/API ledger stay hash-identical.
The existing synthetic SQLite intentionally changes with explicit seal/new attempt;
both file hashes and preserved table hashes are recorded. Local PostgreSQL, services,
model and main checkout are untouched. Still open: cross-process reproducibility,
frozen oracle/regression/causality protocol, actual local data exporter/lineage and
approved baseline/split, broader runtime/syscall security audit and stress tests,
free-only generation/provenance, equal-budget efficacy and independent test/paper.
TypeSafe skill/live index were read; exact rules remain ordinary code.


## Independent numeric verification — 21 October 2026

`research_numeric_verification` prepares a frozen two-window protocol and reuses
unchanged NumericControlBudget v4. There is no schema migration/new kind/new budget.
The registered candidate and three-bar seed produce one-bar and two-bar selected
windows at the same cutoff. They are different input effects; 13 fixed fixtures are
shared. Candidate/preview/capture/window/packet/key/configuration/implementation and
runtime hashes are saved before execution, with private exclusive fsynced files.
Prepare reserves nothing. Execute calls the old budgeted fixed worker twice; verify
reads completed rows only. Re-executing a receipt is refused. A new directory for the
same effects uses existing cache, never new quota or another worker.

The independent reference walks the closed source AST separately from worker IR.
It computes with Fraction, preserving each float's exact binary value and rounding
to binary64 after every node. Exact normalized float.hex values/statuses are compared,
including zero/missing/numeric-error cases. This is a bounded trusted verifier with
its own evaluation count/time; its work is outside v4 handler_wall accounting. No full
CLI hard resource cap, Decimal-price accuracy or financial oracle is claimed.

Persisted evidence must match the v4 action identity/key/packet/result, fixed runtime
hashes, seven complete isolation checks, Python3.12.3, scope/cgroup syntax and cleanup.
Two distinct scopes plus identical results for 13 common fixtures establish this
fixture-level reproducibility. Selected windows differ, so whole-packet reexecution
is false. Missing required history prevents a full pass. A reference mismatch stops
before the second launch without refunding the completed evidence. Failures and
partial/started receipts cannot be treated as completed or retried automatically.

Selection-only metamorphic checks reverse capture rows and change/add unavailable
future values. Past payload/identity must stay equal. Synthetic transformed inputs
are not authenticated market history; no candidate reruns or upstream/financial
causality proof are invented. If the development boundary prevents a future test,
its result is null and overall verification cannot pass.

CLI uses the same original bindings/policies as `research_numeric_controls`, plus:

```bash
PYTHONPATH=src python -m cryptoforge.research_numeric_verification \
  --database /absolute/established-common.sqlite \
  --proposal-ledger /absolute/established-proposal.sqlite \
  --semantic-ledger /absolute/established-semantic-fixture.sqlite \
  --fit-ledger /absolute/established-fit.sqlite \
  --semantic-live-ledger /absolute/established-local-semantic.sqlite \
  --semantic-live-policy config/coordinated-semantic-live-budget-v2.json \
  --code-policy config/coordinated-code-check-budget-v3.json \
  --numeric-policy config/coordinated-numeric-controls-v4.json \
  --verification-policy config/research-numeric-verification-v1.json \
  --preview /absolute/registered-preview --seed-window /absolute/three-bar-seed \
  --capture /absolute/original-capture.json --directory /absolute/new-protocol prepare
```

Then use identical inputs/directory with `execute` and `verify`. Prepare/execute do
not overwrite existing directories/receipts. Execute/verify return 2 for a negative
verification verdict; only a complete positive summary returns 0.

1334 profile tests passed in 102.31 seconds, including 50 new checks; previous
1284 tests and actual namespace/cgroup/loopback opt-ins were preserved. Operational
prepare/execute/verify used the same established synthetic database: four prior
actions became six, numeric_control cap is now **3/3**, questions stay two, allocations
are input32000/output2048/wall125000ms. Six v3 tables, numeric extension and the prior
numeric action are unchanged. Two new worker scopes attempted 32 evaluations of the
existing mock constant-one candidate. Trusted references computed 16 expectations on
execute and 16 again on readback. Shared fixtures and selected windows agreed; the
readback left journal bytes unchanged. Real API journal and 84 older artifacts keep
their hashes. No operational provider/DB request, fit or production change occurred.

`.local/research-verification-real-20261021` contains 13 private JSON files, no active
SQLite/raw capture/candidate source. New candidate work is blocked by the exhausted
v4 kind cap; the next phase needs an explicit history-preserving transition, never
a journal copy/reset. Actual local PostgreSQL exporter/lineage, approved real baseline,
financial feature oracle/regression/evaluator, broader reproducibility/stress/security,
full verifier resource accounting, free-model provenance and equal-budget efficacy
remain open. TypeSafe live index/skill and official Python Fraction docs were read;
exact calculations remain ordinary code.


## History-preserving research continuation v5 — 21 October 2026

`research_phase` explicitly extends the existing resolved v4 journal with three
phase tables, preserving hashes of all eight old tables. No quotas/policies are
replaced, no actions/resources are refunded, no new budget file is created. Atomic
migration is idempotent and rolls back on failure; unresolved reservations or corrupt
history refuse the first transition. Older clients fail closed on the new schema.
Their frozen records/JSON receipts are retained. Use v5 routes for historical cache
and static readback; the old v4 verifier does not understand the expanded schema.

Shared lifetime/daily/per-kind/question/token/wall limits count v3+v4+v5. New phase
policy defines routing only. Numeric_control remains **completed-cache-only**, with
old lifetime usage3/limit3. No phase handler can reserve fresh numeric_control work.
Post-migration common-path binding also rejects using a copied database at a new
path; copying pre-phase journals is not an allowed reset mechanism.

Old v3 effective keys retain their original executor/semantic/code configurations.
Old completed results return original usage/measurement and zero invocation work;
old failed/cancelled/timed_out/reserved identities cannot retry under a new phase or
UTC day. New phase rows have matched resource coverage and exact allocation/result/
usage/measurement checksums. Measured overruns block fresh work while cache stays
available. Allocations are admission reservations, not full CLI/billing hard caps.

`PhaseResearchCoordinator` reuses the original fixed proposal/fit/semantic handlers,
identities, free adapters, inner journals and data/production checks. API also retains
live/source semantic. CLI supports proposal, fit with optional --advice-receipt,
semantic-fixture, code-check, static-check, numeric-cache, migration and status.
Separate live/source semantic CLI wrappers remain open. No actual model/backend
readiness or approved real dataset is implied. Low-level run accepts trusted Python
handlers only; external strings do not select executable code.

Completed numeric-cache readback verifies the original v4 key/configuration,
registered preview/input/packet/summary and returns zero worker launches/actions.
Missing/failed/mutated effects refuse. Static review can read completed preview
registrations in either old v3 or new phase tables, then applies the existing closed
AST contract without execution/new attempts. Static/reference verification time is
outside common handler measurement; generic Python remains disabled.

Use all established bindings and policy files, then add the fixed phase policy:

```bash
PYTHONPATH=src python -m cryptoforge.research_phase \
  --database /absolute/established-common.sqlite \
  --proposal-ledger /absolute/established-proposal.sqlite \
  --semantic-ledger /absolute/established-semantic-fixture.sqlite \
  --fit-ledger /absolute/established-fit.sqlite \
  --semantic-live-ledger /absolute/established-local-semantic.sqlite \
  --semantic-live-policy config/coordinated-semantic-live-budget-v2.json \
  --code-policy config/coordinated-code-check-budget-v3.json \
  --numeric-policy config/coordinated-numeric-controls-v4.json \
  --phase-policy config/coordinated-research-phase-v5.json \
  --output /absolute/new-phase-receipt.json migrate
```

CLI output is an exclusive0600 receipt; `status` is read-only. Code/static/numeric
commands additionally require their preview/input options. Fit/proposal outputs keep
the coordinator receipt contract for registered diagnostics/advice reuse.

1391 profile tests passed in 132.86 seconds, including57 new cases and all prior
1334 tests with actual namespace/cgroup/loopback opt-ins. A synthetic integration
reused a pre-phase fit cache, then ran mock advice and a candidate fit through the
original handlers/inner journal, keeping production_compatible=false. Operational
smoke ran five CLI calls and two low-level mock accounting calls in the established
synthetic journal: six prior actions became seven, numeric cap stays3/3, questions2,
allocations input64000/output4096/wall190000ms. The fresh proposal is explicitly
synthetic accounting with no provider/schema/effectiveness claim. Eight old tables,
original caches,97 prior artifacts and the real API journal are unchanged.

`.local/research-phase-real-20261021` archives11 private JSON reports, never active
SQLite/raw data/candidate code/keys. No operational provider/DB/fit/numeric worker,
model/service or main-agent code changes occurred. Working operational research
journals were not migrated. Still open: actual local PostgreSQL exporter/lineage,
approved real split/baseline/evaluator, live-model/source provenance and missing CLI
wrappers, explicit numerical protocol/budget decisions, full resource/security/stress
validation, equal-budget efficacy and independent test/paper. TypeSafe skill/live
index were applied; exact rules stay ordinary code.


## Bounded local PostgreSQL observations (21 October 2026)

`cryptoforge.research_local_export` reads the active local PostgreSQL directly,
with one fixed loopback connection and a repeatable-read, read-only transaction.
It uses the existing non-superuser authenticator login/service_role and private
compose secret, never a user-supplied DSN, cloud fallback or arbitrary SQL. The
optional driver pin is `config/research-local-export-requirements.txt`; it was
already installed. No shared dependency files or source-bound legacy modules change.

The fixed policy accepts one bybit spot symbol and aligned 1m/5m/15m/60m range of
at most256 rows, declared train/validation only. It verifies the18 column contract,
unique scope index, effective readonly/isolation/timeouts, row identities and
geometry. The query is parameterized, limited to257 rows and rejects overflow.
Empty/gapped/open or obviously pre-close stored rows produce a blocked receipt
and no capture. Timeouts: connect3s, statement3s, lock250ms, idle transaction5s;
an8s soft deadline is checked between queries, not a whole-command hard limit.

An export directory must be new. It stores policy/request/source/capture/receipt
with0700 directories/0600 files and fsync. Source includes exact decimal OHLCV,
turnover, storage UUID/xmin/timestamps, catalog and transaction snapshot evidence.
Offline replay checks current implementation and canonical content hashes; it
neither reconnects nor authenticates a publisher/cluster or a wholly rewritten,
self-consistent archive. Feature conversion is binary64; the exact decimal source
remains in source.json. Raw records and credentials never enter a model prompt or
candidate input. The exporter does not build labels or approve a development split.

Use from the isolated worktree with its source on PYTHONPATH:

```bash
PYTHONPATH=src python -m cryptoforge.research_local_export export \
  --project /home/arthur/Projects/personal/CryptoForge \
  --directory /private/new-export --request /private/export-request.json \
  --policy config/research-local-export-v1.json
PYTHONPATH=src python -m cryptoforge.research_local_export verify \
  --directory /private/new-export
PYTHONPATH=src python -m cryptoforge.research_local_export window \
  --directory /private/new-export --request /private/window-request.json
```

Export request fields are exactly schema_version=research-local-export-request-v1,
symbol, timeframe_seconds, start, end, partition, development_end. Time values
must include a timezone, start<end<=development_end; start/end align to the
interval. Window requests use the existing research-window-request-v1 contract
(decision_time,bars). A blocked export/unavailable window returns exit2. Outputs
print only safe status. Exceptions omit private driver/SQL/credential text.

The cache is mutable: upsert overwrites values. created_at is row creation,
ingested_at/updated_at are storage clocks; xmin is not a commit timestamp or a
revision history. For these exact current values, observed_at is the new client
observation after the read. Old storage dates cannot backdate feature availability.
The bridge deliberately retains external_unverified origin and every historical,
approved-split/training admission flag false. Storage dates after candle close
only reject obvious partials; they do not establish exchange finality or clock sync.

Operational smoke saved4 actual BTCUSDT 5m rows for2026-10-21T11:00Z..11:20Z from
PostgreSQL17.10. Export status observed, no issues; client observation12:00:52.347118Z.
Offline verify succeeded, and the historical11:20Z window was unavailable with a
null payload. No training, LLM, numeric worker, schema or application-data writes
occurred. The same established SQLite and API journals remain byte-identical;
numeric lifetime 3/3 remains cache-only. Full profile: 1491 passed in153.51s, including100
new tests and the previous1391, actual namespace/cgroup/loopback checks enabled.

`.local/research-local-export-real-20261021` archives11 private JSON files, including
the explicit bounded4-row real source; no active database files or credentials.
The108 prior artifacts are unchanged. Next gates are verified historical/revision
lineage or an explicitly justified historical-data protocol, an approved real
manifest/split/baseline and feature/label binding to the existing evaluator. Current
observation and offline hash checks cannot substitute for these gates. No production
promotion or automatic trading-code changes are enabled. TypeSafe guidance keeps
these exact rules in ordinary code.


## Main/advisor diagnostics interoperability — 22 October 2026

`research_diagnostics_bridge.py` adds a separate boundary rather than overwriting
either existing training_diagnostics module. Its fixed policy recognizes main
training-diagnostics-v1 (strategy outcomes) and native advisor v2 (classifier
prediction metrics), with explicit kind/configuration/evidence-group selection.
A strategy's positive-trade ratio/PnL cannot substitute for model precision/Brier.
Unknown/null values stay unknown; source IDs, decimals, units and four control
roles remain intact. The strategy source contract and all configurations and
attribution are checked even when the selected view omits some of them.

The common research-diagnostics-evidence-v1 strategy view contains 76 aggregate
facts (four roles ×19 metrics), bounded to24000 bytes including its final checksum;
raw native reports are bounded 256KiB. Attribution and unselected configurations
are excluded explicitly, never silently truncated. Strategy reports route to
strategy_research_review_only; legacy_advisor_input rejects them. Prediction
reports return the exact original v2 input, which still passes the old FreeAdvisor
preflight. No provider/fit orchestration or economic-parameter search is added.

The native source, selector, policy and evidence form a private0700/0600 immutable
pack. `bind-main` uses a fixed trusted main exporter command in a separate Python
process with the main source path, cleared environment and bounded log/result.
It checks the original private rollback-format SQLite hash and six producer
source hashes before/after; no active database is copied, reset or migrated.
The child replays original registered development evidence and must reproduce the
frozen report exactly. Parent wait15s, CPU 8s/AS 512MiB/file512KiB/NOFILE64 and
process-group kill/reap/temporary cleanup are set. This trusted exporter is not
an audited untrusted-code sandbox or a whole-CLI/machine resource guarantee.

Started/completed/failed/cancelled/timed_out binding receipts are durable. A prior
binding is never implicitly retried; source changes fail closed. verify-main
checks the saved successful receipt against current source/ledger/interpreter
hashes, without rerunning the exporter. This is a local source binding, not external
publisher authentication, temporal market lineage, active-model qualification or
permission to train/promote. The raw source is private; only the selected bounded
fact view is a potential future research-review input.

```bash
PYTHONPATH=src python -m cryptoforge.research_diagnostics_bridge prepare \
  --directory /private/new-pack --source /private/main-diagnostics.json \
  --selection /private/selection.json --policy config/research-diagnostics-bridge-v1.json
PYTHONPATH=src python -m cryptoforge.research_diagnostics_bridge bind-main \
  --directory /private/new-pack --project /home/arthur/Projects/personal/CryptoForge \
  --ledger /home/arthur/Projects/personal/CryptoForge/.local/state/research-attempts.sqlite
PYTHONPATH=src python -m cryptoforge.research_diagnostics_bridge verify-main \
  --directory /private/new-pack --project /home/arthur/Projects/personal/CryptoForge \
  --ledger /home/arthur/Projects/personal/CryptoForge/.local/state/research-attempts.sqlite
```

A selection has exactly schema_version=research-diagnostics-selection-v1, kind,
and configuration_sha256 for strategy_outcomes or evidence_group for
classifier_predictions. `verify` is fully offline. `legacy-input` checks whether
the old parameter-advisor route is valid; an incompatible report exits2 without
provider calls. The Python legacy_advisor_input API returns the original native
report after verifying its hash again, rather than emitting transformed metrics.

Operational smoke ran 8 CLI calls: 4 successful strategy prepare/verify/bind/verify-main
and one intentional legacy refusal, then 3 prediction compatibility checks, followed
by offline FreeAdvisor preflight. The actual original main 4-config report exactly
matched its 18 October archive; selected compression_breakout/atr produced76 facts,
22437 bytes, all four controls. Native prediction diagnostics came from the prior
registered 16 October baseline, not a refit. Main original strategy ledger and the
same established common/API journals remained byte-identical; no PostgreSQL,
credentials, providers, fits or numeric evaluations occurred. Numeric 3/3 remains
cache-only. Full profile: 1564 passed in 102.00s, 73 new and 1491 previous tests, actual
namespace/cgroup/loopback checks enabled.

Sixteen private JSON artifacts under .local/research-diagnostics-bridge-real-20261022
include both packs, binding, selections, preflight and observation/reference/verification;
121 prior artifacts remain unchanged. No source-bound legacy module, main code,
active model/registry, schema or service is changed. At the bridge milestone R01 was partially complete; the inventory continuation below completes its source/registry audit. Approved real evaluator integration and R02/R03 data/baseline gates remain open. TypeSafe guidance keeps these exact rules in code;
no semantic API or dependency is added. The authoritative remaining list is R01–R20
in the plan; this interoperability boundary does not prove ML/trading efficacy.


## R01 completed: registry and executor source inventory — 22 October 2026

The fixed research_model_inventory CLI captures local model.active/model.candidate
rows and installed systemd ML flags, then replays the main registry against those
rows in a separate trusted process. It does not fetch artifact URIs, open exchange
connections, execute the live executor, infer probabilities, fit or promote models.
Ten source files and eight reviewed AST method shapes bind the source route from
the environment loader/local backend to registry, feature input and entry gate.
The actual loaded image of a live process is not attested by file hashes.

The local PostgreSQL transaction is repeatable-read/read-only with a verified
non-superuser login. Two latest rows per kind allow timestamp-tie detection;
ambiguous selection is refused rather than assigning meaning to an arbitrary id.
Only needed registry payload keys are copied, with256KiB per projected event/1MiB
snapshot caps. Four embedded artifacts are stored privately to replay their exact
checksums; full URI/free event text and credentials are excluded. Offline verify
rebuilds the inventory from saved evidence without a new database read.

At 2026-10-22T13:31:43.696514Z, model.active was the 7 October artifact
pure-python-logistic-candle-v1-20261007-09b486e979. Its checksum/vector shape/seven
feature order are valid, but main registry latest(max_age=36h) returned None.
Installed ML flags are gate, threshold 0.50 and 36h, with no explicit artifact pin.
The oneshot service was activating/start at the property observation; inventory
never started it. Systemd properties and the PostgreSQL snapshot are separate
observations, not an atomic machine/process-state attestation.

The active config lacks declared input_candle_state/calculation_contract/feature
window. Current source defaults to legacy_asof_snapshot; training history 500 is
not a proven runtime width. Actual training/inference feature parity remains false.
The latest candidate from 22 October 12:45Z is fresh to the candidate registry and
explicitly declares closed_only/bounded-window-candle-v1/window 120/5m/horizon3.
This is not an automatic entry fallback, promotion, or an approved baseline.
Both registry availability and metadata checks are retained; even fresh metadata
cannot authorize orders or certify causal market inputs.

Trusted replay uses a cleared environment, fixed worker, CPU 8s/AS 512MiB/file512KiB/
NOFILE64, parent 15s wait and group kill/reap/temp cleanup. It is not a generic
untrusted runner, machine-wide resource guarantee, stress test or trading admission.
The native main registry is replayed with frozen events and no HTTP client access.
All artifact, feature-order/vector, target/legacy-inference, future/staleness and
source/consumer metadata checks remain explicit. A stale/absent model produces a
valid negative inventory, never a fabricated incumbent or a refreshed event date.

```bash
PYTHONPATH=src python -m cryptoforge.research_model_inventory capture \
  --project /home/arthur/Projects/personal/CryptoForge --directory /private/new-model-inventory
PYTHONPATH=src python -m cryptoforge.research_model_inventory verify \
  --directory /private/new-model-inventory
```

Full profile: 1632 passed in 115.70s, 68 new/1564 previous tests; actual namespace/cgroup/
loopback opt-ins enabled. Real smoke ran 2 CLI calls and the offline main replay.
Seven private JSON artifacts are saved under .local/research-model-inventory-real-20261022:
policy/snapshot/native replay/report and observation/reference/verification. 137
prior artifacts and the same API/common SQLite bytes are preserved; numeric 3/3
remains cache-only. No database writes, model/registry/service changes or new
provider/fit/inference/research-budget actions occurred. Other processes may
change the live database after the observation; this report is tied to its time.

R01 is checked as source/contract reconciliation plus a genuine inventory, including
its negative result. Approved historical data/splits/labels remain R02, a valid
reproducible baseline R03, real trainer/evaluator wiring R07 and independent
runtime/paper/admission R09. These requirements are retained explicitly rather
than being implied complete by the inventory. R02 is the next step. TypeSafe and
PostgreSQL guidance keep all exact rules in code; no semantic API or dependency
was added and the cloud database was not used.


## R02 partial: development availability and split audit — 23 October 2026

`research_data_protocol.py` reads original sealed M10 local PostgreSQL export packs
offline; it does not query a database, fit, call a provider or adopt a main W6a
diagnostic probe into a new study. Five source-file pins are checked before/after
native exporter replay. Source UUID/storage revisions and catalog/DB OID consistency
are checked, without claiming authenticated cluster/REST identity or complete polling.

The closed v1 contract uses 5m, candle-v1/bounded-window/window120 and fixed-future-return
horizon3. Partition decision_start/end are half-open candle-close anchor intervals;
actual decision adds an explicit 0..299s delay. Each input selects the latest revision
known at that decision. Missing latest bars never fall back to older windows; late,
missing and tied conflicting versions stay distinct. Label end uses anchor close +
horizon × step, matching the primary candle-target time convention, not order profit.
Every future horizon bar must be observed by its split's fit/validation information
cutoff. Numerical features, returns, thresholds, costs and native label values are
not recomputed and their parity remains an admission requirement.

Four ordered/grid-aligned train/validation/final_test/forward intervals require
at least horizon-sized embargo; label_end is strictly before the next partition.
Final test must start after this audit's captured time. Requests are screened before
source/capture reads; no validated holdout values enter the development audit. These
declared future dates do not register or schedule an approved experiment. All source
windows are automatically recorded as exposures, even with an empty caller inventory.
The global exposure inventory and preregistration remain unauthenticated/incomplete.

The fixed limits are 8 exports, 2048 observed rows, 4 symbols, 4096 development samples,
128 declared exposures, 64KiB metadata inputs and a 4MiB final report. Private new-only
files use 0700/0600/fsync. Six pack JSON files store policy/protocol/exposure/source
references/context/audit; original raw values are pinned and not recopied. Verify
rebuilds offline from those original files at the saved context time. Whole CLI
resource/crash accounting remains R06; this is not a generic sandbox qualification.

```bash
PYTHONPATH=src python -m cryptoforge.research_data_protocol prepare \
  --protocol /private/protocol.json --exposure /private/exposure.json \
  --export /private/original-local-export --directory /private/new-data-audit
PYTHONPATH=src python -m cryptoforge.research_data_protocol verify \
  --directory /private/new-data-audit
```

Full profile: **1690 passed in 108.41s**, 58 new/1632 previous tests, with actual
namespace/cgroup and synthetic loopback opt-ins. The initial sandbox-only run had
66 pre-existing socket/namespace/cgroup failures (Operation not permitted); the same
profile passed with those local test mechanisms enabled, without weakening checks.
Real smoke ran two CLI calls against the original four BTCUSDT rows observed on
21 October at 12:00:52.347118Z. The example train/validation protocol produced **0/2**
metadata-consistent samples: old training inputs were observed too late, both lacked
the required 120-bar coverage and neither had horizon labels. It returned a valid
blocked audit, not a fabricated dataset. One source exposure window is retained.

Nine private JSON files are archived under .local/research-data-protocol-real-20261023.
All 945 pre-stage file hashes outside the two owned docs, original export bytes and
same API/common journals are preserved; numeric 3/3 stays completed-cache-only.
No operational provider/fit/inference/numeric/budget actions or main model/service/
registry/source changes occurred. Fixture fits in older tests do not establish
operational data or training benefit.

R02 remains unchecked, with 19 open groups R02–R20. Original observation/revision
coverage, complete exposure inventory, approved source/split protocol and native
feature/label/target-parameter parity are still required before R03 baseline work.
Even a metadata_consistent report always has training_data_admitted=false and no
promotion rights. TypeSafe live docs keep deterministic selection/rules in code;
no semantic API, dependency or SQL/schema change was introduced.


## R02 partial: original venue revisions and completed poll delivery — 23 October 2026

`research_revision_bridge.py` and its fixed trusted worker bind the original main
W6b reference-source journal to temporal sample audits. Venue natural IDs are kept
separate from PostgreSQL UUID/xmin identity. Primary operational storage stays
local PostgreSQL; original research SQLite is read in place under retained
manifest/registration/database/head pins. No journal copy, new collector, hidden
head adoption, model artifact, forecast or inference is allowed by this route.

Nine reviewed main runtime hashes and package __init__ are checked before/after.
The native main audit replays the source event chain, mandatory responses/negative
outcomes and immutable first-seen index in a separate main-PYTHONPATH process.
Its scratch path alone is redirected into parent-owned temporary storage. Parent
15s deadline, CPU8s/AS512MiB/file2MiB/NOFILE64, cleared environment, DEVNULL stdin,
group kill/reap and cleanup bound this trusted replay. Generic sandbox, whole CLI
accounting and host qualification remain R06/R19.

Projection retains metadata/hashes, never raw HTTP/OHLCV/model/credentials. Fixed
reader caps: original DB 8MiB, 128 events, 1024unique versions, 2048delivered rows,
projection 1MiB/report 4MiB. Original writer policies and all prior source-bound
modules/identities stay unchanged. Offline verify checks original source bytes and
rebuilds saved projection/report without another child, GET or database query.

First-seen is the original HTTP observation. All delivery occurrences remain
available so correction B followed by the old value A selects A after its new
delivery, while preserving A's original first-seen. Effective adapter availability
is the completion of the whole mandatory poll; partial responses cannot leak into
earlier samples. Latest completed failed/stale polls cannot fall back to older
successes. Both response age and latest closed-bar age must be at most 600s.
The M13 temporal/target-time/cutoff/embargo rules and automatic exposures are retained.
This is metadata lineage, not numerical feature/label-value parity or data admission.

Full profile: **1729 passed in 108.19s**, 39 new/1690 previous, actual namespace/cgroup/
loopback opt-ins. New synthetic native tests cover 960 delivered rows/262 versions,
old-value redelivery, first-seen, incomplete polls, negative histories, latest-failure
freshness, cutoffs, pins/tampering/private replay and cancellation/deadline cleanup.

Real smoke ran 4 CLI calls over two original retained W6b journals without new polls.
The public namespace has 240 versions/4 events/0 forecasts, poll completed 07:51:33.006686Z.
At the example 07:52Z train decisions, both pairs have 120 available input rows;
at 08:27Z validation, each has 113 and mandatory reference freshness fails. None has
the three future horizon labels: 0/4 metadata-consistent, status blocked. This describes
that frozen source history, not all market data or current operational storage.
The separate original URLError namespace has 4 events/0 versions and remains a valid
negative trace, not an automatically retried/replaced attempt.

Fifteen private JSON files are saved under .local/research-revision-bridge-real-20261023:
two six-file packs plus observation/reference/verification. All 957 baseline files
outside the two owned docs, original source namespaces/receipts and same common/API
journals are preserved; numeric 3/3 remains cache-only. No operational provider/fit/
inference/numeric/budget action, service/model/registry/main-source change occurred.

R02 stays unchecked: continuous original prospective source/label coverage, complete
exposure inventory, approved data/splits and native feature/label/target-parameter
parity remain required. Native source_trace_integrity_pass is narrower than those
gates; diagnostic mode is never silently adopted into a future study. No semantic
API/dependency, cloud database or Postgres SQL/schema change was introduced.


## R02 partial: native source-value compatibility — 23 October 2026

`research_value_audit.py` and its fixed trusted worker consume an existing verified
M14 pack, its six original file hashes and original source journal pins. Selections
are rebuilt from the complete delivery timeline, without new collection, forecast,
model artifact, fit or journal copy. The new main reader/inference frame remains a
separate namespace/contract and is not silently adopted here.

Eleven reviewed value-runtime module hashes and the existing M14 source profile
are checked before/after. The worker fetches exact source_id/version raw values
readonly, verifies original version SHA/pair/open time and source availability,
and builds Decimal CandleRows without a float round trip. Native extract_features
and executor _model_input_features use identical closed120/as-of inputs, fixed
Decimal28/ROUND_HALF_EVEN and seven-feature order; an explicit NoReader refuses any
implicit fetch. All comparisons use float.hex without tolerance.

Only a complete future horizon permits native build_examples(width120,horizon3).
Its one example must end inputs at anchor−5m and labels at anchor+15m; training
features must equal runtime. Missing/late/stale/purged inputs or horizon values
stay null. Native runtime/extractor/training compatibility shares a core feature
implementation: it is not an independent full feature oracle or proof of actual
production trainer source selection. Those gates remain open.

The explicit audit target declares price-return semantics and decimal threshold/
cost parameters. Smoke uses 0.003/0.002 as an unapproved example, not current model
settings. Fees are not subtracted from fixed-future-return-v1. Long/short labels
use strict binary64 comparisons. Exact Fraction arithmetic from decimal endpoint
quotes supplies a separate return reference, then converts to binary64. Differences
from native Decimal28 rounding/labels remain recorded failures, without tolerance
or automatic code changes. A complete private example may retain two endpoint
quotes and derived vectors; full raw OHLCV windows/database/models are not recopied.

The fixed worker keeps CPU8s/AS512MiB/file2MiB/NOFILE64 and parent15s, cleared env,
DEVNULL stdin, process-group kill/reap and private temporary cleanup. Caps are
16 samples, 2MiB packet, 256KiB native result. This trusted compatibility verifier is
separate from candidate/prototype execution and does not reopen numeric 3/3. Whole
CLI/resource accounting remains R06. Six private new-only files store policy,
source binding, selections, target, native result and audit. Offline verify checks
the original bindings and saved compatibility/Fraction evidence without rerunning
native feature functions; it does not claim a fresh independent numeric replay.

Full profile: **1771 passed in 86.07s**, 42 new/1729 previous, actual namespace/cgroup/
loopback opt-ins. Tests cover native complete synthetic examples, increasing/
decreasing/equality outcomes, future-price changes without historical feature
changes, late/null data, bit differences, target/runtime/source/timing tampering,
private replay and deadline/cancellation cleanup. Fixture examples are not an
operational fit or a measured training benefit.

Four real CLI calls used the same two original M14 packs/journals. Public: two
available 120-candle BTC/ETH windows, 240 selected source rows and 14 feature components
matched extractor/runtime bit-for-bit. There were zero real complete training
examples because future labels were not captured. Stale/incomplete validation
windows and the zero-row negative source remained unavailable. Numeric mismatch
count 0 describes actual comparisons, not approval of missing labels. Both audits
remain blocked. No new network/PG/provider/model-prediction/fit/budget actions.

Fifteen private JSON artifacts are archived under .local/research-value-audit-real-20261023.
All 976 baseline files outside two owned docs, original sources/metadata packs and
same API/common journals remain hash-identical; numeric 3/3 stays completed-cache-only.
Two trusted native source-value worker runs are recorded separately from prototype
numeric executions. Primary operational storage stays local PostgreSQL; main code,
model/registry/services and production admission were not changed.

R02 remains open: approved source/split/target parameters, sufficient prospective
horizon coverage, complete exposure inventory and real native label/source-selection
parity are still needed before baseline/trainer integration R03/R07. TypeSafe guidance
keeps all exact logic in code; no semantic API/dependency or cloud DB was introduced.


## Independent bounded-window feature reference — 23 October 2026

M16 adds research_feature_reference.py, research_feature_reference_worker.py and
research_feature_oracle.py. Frozen JSON specifies all seven candle-v1 formulae.
The reference uses exact rational decimal lexemes, closed weighted EMA sums and
the RSI gain/loss identity, without trainer/runtime imports. The contract is
closed120/5m, first-close EMA seed, RSI zero-loss=1 (also flat), zero-volume=0.
It is not a qualification of legacy prefix EMA or other feature versions.

All six original M15 files and transitive M14 original source/event/selection pins
are rebound. A bounded readonly worker checks exact version IDs/raw SHA, source
identity, grid, availability, closed state and anchor. No original OHLCV window,
database or model is copied. Derived vectors and raw-version digest are retained.
Missing windows stay null; available extractor/runtime and training values are
compared componentwise by finite float.hex. Decimal28 versus exact rational
rounding disagreement, including one ULP, stays a failure without data-driven
tolerance. verify re-executes the independent reference over the original source,
without executing native feature functions or inference.

The existing worker CPU8s/AS512MiB/file2MiB/NOFILE64/parent15s bounds, cleared env,
private temporary files and process-group kill/reap apply. Caps:16samples/2MiB
packet/256KiB result. These fixed compatibility workers are separately recorded;
the exhausted candidate numeric3/3 remains completed-cache-only. Full CLI costs,
mount/syscall/process-tree qualification and statistical testing remain open.

Profile:1819passed/81.30s,48new/1771previous. Hand-derived linear EMA identities
and all-feature expectations, simple RSI/range/volume/body boundaries, Decimal
context independence, source identity/availability/raw hashes, nulls,1ULP failures,
whole-result tampering and worker cancellation are covered. Synthetic complete
windows also compare28components with native training features. Four real CLI
calls independently replay two original BTC/ETH windows:14/14components matched;
negative source has0available. Public prepare+verify read480rows in total, with
zero native feature workers, source polls, network/PG/provider, fit, prediction,
candidate numeric or budget actions. Formula/comparison freeze precedes this real
replay, but is not prospective study/patch preregistration on unseen evidence.

Two six-file packs plus freeze/observation/source-reference/verification are in
.local/research-feature-oracle-real-20261023. All995baseline files outside two
owned docs, original sources and common/API journals remain unchanged. Real
horizon labels are still absent, and source value admission stays blocked.
reference_matches does not authorize training or promotion. R02/R18 remain open
for approved data/protocol/target/exposures, actual trainer source selection,
real-label parity, cross-environment and statistical patch validation. Primary
storage remains local PostgreSQL; main code/model/services were not changed.


## R04 partial: descriptive development slices — 23 October 2026

research_diagnostic_slices.py accepts closed v2 train/validation exports with the
same declared dataset/source and explicit fixed protocol. It checks grid5m,
disjoint ranges, windows tiling each partition,16pairs/32windows and20,000actual/
expected rows per partition. Input/report caps are8MiB/2MiB. Final-test/forward,
extra fields, invalid probabilities/labels and unknown pairs are rejected.

All prediction metrics reuse the frozen v2 implementation. Windows assign rows
by open_time in [start,end); labels must end within the partition's development
boundary. Labels extending beyond an internal descriptive slice boundary are
counted separately with their information end. These groups are not independent
tests or a qualified purge/embargo protocol. Expected/observed/missing pair slots
and per-pair coverage remain explicit. Sample concentration is an observation
share, not economic exposure. Empty windows have null metrics/hash/time; zero
precision/recall denominators retain v2 nulls. Brier/log-loss/calibration gap is
validation−train; descriptive window spread requires two nonempty windows. No
statistical significance, threshold selection or model improvement is inferred.

Regime/strategy/cost/accounting/as-of/history values stay null with fixed reasons.
The pack does not invent prices/fills/equity, historical availability or semantic
regimes from prediction labels. Upstream admission, lineage, purge and statistical
qualification remain false. Five private new-only files store policy/protocol/
train-export/validation-export/report; verify recomputes the entire report and
checks implementation hashes. The old v2/advisor/bridge contracts are unchanged.

1859tests passed in77.00s (40new/1819previous), including hand-derived Brier gap,
coverage/nulls, internal label horizons, boundary/schema/size guards, permutation
invariance, exact v2 compatibility and rehashed-report tampering. Five CLI smoke
calls use explicitly synthetic fixtures: four successful full/empty-window calls
and one final-test refusal. The fixture's5m label horizon is not a claim about
current model settings. No real prediction rows/report were manufactured.

A scoped inventory of33protected prior export/diagnostic JSON files found zero
raw classifier exports. Aggregate v2 and strategy-only facts cannot be expanded
into original probability/label rows. This inventory is not global discovery or
upstream admission. Sixteen private artifacts are in
.local/research-diagnostic-slices-real-20261023. All1017prior files outside two owned
docs, original evidence and API/common journals remain hash-identical. There are
zero new source/PG/network/provider/model-prediction/fit/numeric-prototype/budget
actions; numeric3/3 stays exhausted. Main local PostgreSQL/model/services/code were
not changed. R04 still needs approved real rows, causal regimes and independent
economic/error/history inputs before a combined real training report is complete.


## R19 partial: bounded real kernel stress — 23 October 2026

research_resource_stress.py is a new fixed diagnostic, with no generic candidate
or shell API. It preserves the old resource/arithmetic/budget modules. Two own
disposable user scopes enforce64MiB/swap0/tasks8/CPU25% (100msperiod), runtime5s,
stop1s and parent10s. Host and finite ancestors must leave320MiB headroom before
allocation. The allocator has a96MiB finite virtual workload with page touching.
Bubblewrap keeps separate namespaces, sole-loopback network, empty env, cap0,
no_new_privileges, readonly controller/proc/dev/root, private8MiB tmpfs and hidden
main/database paths. Local ports are tested only inside the distinct namespace.
The /usr mount is broad; no minimal-mount/seccomp/security qualification is claimed.

OOM requires allocator SIGKILL plus increasing memory.events max/oom/oom_kill.
CPU burn1.25s requires own cpu.stat usage/period/throttling deltas without OOM.
Kernel counters, swap0, fixed controls/profile/command/environment/source hashes,
scoped cleanup and vanished cgroup are checked. The initial inspect and debug
replay failed before a signed observation; debug journal confirmed manager stop
after OOM. Both failures and their original receipts are retained. Explicit
OOMPolicy=continue applies only to this fixed diagnostic observer so it can read
events after the allocator dies. Caps/deadlines/cleanup remain, with no production
or candidate-policy change. This is not full-worker recovery qualification.

Final CLI OOM: one kill, allocator−9, after-snapshot peak67108864bytes. CPU:
13throttled periods/974474µs, usage delta309904µs, no OOM, probe wall≈1.435s. Both
scopes vanished. There were8new R19scope invocations in the stage:2failed OOM,
2focused/2full-profile/2CLI successful probes. Null journal-message finalization
was resumed over saved receipts without more stress. verify rechecks saved kernel
evidence/argv/bindings/removal without re-executing workloads. Counters describe
the diagnostic scope to its after-snapshot; supervisor/CLI/control/cleanup/server/
journald/disk costs are not fully accounted. Candidate numeric3/3 is not reopened.

1906tests/78.71s passed,47new/1859previous. Tests cover actual kernel effects and
offline replay, negative deltas/limits/signal/isolation, strict unit/mode allowlist,
timeouts/cancellation/reaping/stuck cleanup, private receipts and rehashed claim
tampering. Ten private artifacts in .local/research-resource-stress-real-20261023
preserve original failed/focused/profile/final evidence. All1036baseline files
outside two owned docs and common/API journals remain unchanged. No candidate,
provider, fit/prediction, source/PG/network or research-budget action occurred.
Main code/local PostgreSQL/model/registry/services were not changed. R06/R19 still
require full accounting and broader runtime/security qualification; no training
or promotion is authorized by these diagnostics.


## R16 partial: actual Git/index/working trainer base — 23 October 2026

research_trainer_base.py snapshots18reviewed allowlisted main sources without
import/execution. It preserves separate exact HEAD/index/working bytes, Git blob
OIDs and SHA256, tracked/staged/unstaged/untracked state and seven original
function source/AST bindings. Existing M14/M15 source/value pins must match.
Only source code is copied; no .env, credentials, database, models or remote URLs.
This is a scoped source attestation, not an entire worktree/process image or an
offline commit-tree/signature proof. Original Git membership is checked at capture.

Read-only Git2.53.0 uses literal paths/no optional locks/replacement/lazy fetch,
disabled fsmonitor/untracked cache, cleared env and no global/system config or
interactive prompt. It never calls filters/textconv/hooks. Promisor/partial clone,
conflict stages, symlink/submodule and paths outside the18file list are rejected.
Per-file512000bytes/total8MiB, capture12s and per-command3s bounds apply. Two
captures must agree before saving. Private source copies and policy/context/base
are new-only. Offline verify requires a separate expected base pin and recomputes
all copies/OIDs/functions/state/manifest hashes. check-current compares the archived
context against live scoped Git/index/working bytes. Unrelated files do not stale
the base; relevant source/index changes do. Historical archive verification remains
possible, without silently promoting it to the latest source version.

Real main HEAD8da4cb17/branch main:18files,40versions,497811bytes,7functions;7untracked,
0staged,9working-vs-index differences including7untracked and2modified. Four CLI
calls passed (prepare/verify/check-current plus wrong-pin refusal). No code patch,
LLM request, fit, inference, source collection or database operation was performed.
1927tests passed/79.81s (21new/1906previous). Synthetic real-Git tests cover dirty
states/known blob hash, private copies, conflicts/paths/promisors/deadline/env,
staleness, source corruption and external-pin claim tampering. The compatibility
profile also repeated the previous two bounded R19stress scopes; the source-base
CLI creates no scopes or candidate numerical attempts.

Forty private .py copies and seven JSON are archived under
.local/research-trainer-base-real-20261023. All1049prior files outside two owned docs,
common/API history and main code/local PostgreSQL/models/services remain unchanged.
Numeric3/3 stays completed-cache-only. R16 remains open: approved data/evidence and
real free-only request/response/diff provenance must be linked to this base before
reviewing a real LLM patch. Existing virtual preview/closed arithmetic IR is not
upgraded or expanded, and no candidate execution/production apply is authorized.


## R06 partial: visible original-journal inventory — 23 October 2026

research_budget_inventory.py accepts explicitly pinned canonical original paths,
SHA256/kind/closed id/options. It supports only API, legacy attempts, offline
semantic fixture and common v5. Caps:16journals/16MiB per file/2000rows per table/
2MiB report. Owner-private regular files, DELETE mode and absent WAL/SHM/hot
journal are required. All reads use mode=ro/query_only; foreign objects/schema
and changed source hashes fail closed. No database copy, initialization, migrate,
reserve/run/reset/refund or provider/model action is exposed.

Common v5 uses native pure constructors and readonly snapshot with original
policies/bindings. Missing inner files remain missing. Legacy identities/grid/
family caps and attempt states are checked without the writer initializer. API
request/response linkage and usage are rechecked without exporting prompt/response
content. Known tokens and unknown-row counts stay separate; unfinished calls
retain reservations and null tokens. Historical zero pricing is not billing or
current-route proof. Semantic fixture counters are not generative provider costs.

Identical files and overlapping study/configuration IDs are reported without
guessing whether they are copies/replays/new executions. Cross-journal global
totals and account spend remain null. Shared jobpilot quota, complete resource
cost and billing verification remain false. This is explicit visible-local scope,
not global discovery. Private policy/request/inventory files replay the original
journals at their archived snapshot day, without granting fresh quota rights.

Real inventory:9journals; API1completed/3165input+908output=4073reported tokens and
historical zero pricing. Six legacy ledgers have1/2/2/2/2/2reservation rows, with
4overlap groups and0byte-identical groups; actual fit invocation totals remain
unknown. Offline semantic fixture has1request/4questions. The established
synthetic-accounting v5 contains7completed reservations and numeric3/3cache-only,
allocations64000input/4096output/190000ms and808ms measured handler subtotal.
Recorded new provider/fit work there is0; that does not erase older standalone
API history. Four synthetic inner binding files are absent, as the old mock/direct
accounting fixture did not initialize them. Main PostgreSQL is not implicated.

1945tests passed/82.72s (18new/1927previous); two real CLI calls replay all9original
ledgers without changing them. Tests cover null usage/pending rows/overlaps/native
snapshot/no writer initialization/hot/schema/hash/checksum/race/private/tampering.
The compatibility profile repeats the previous two R19stress scopes; the inventory
CLI itself creates none. Six private artifacts in
.local/research-budget-inventory-real-20261023 preserve all1099prior files outside
two owned docs, original journals and common/API hashes. No operational PG/network,
provider/model/fit/source/numeric-candidate/budget action occurred. R06 remains
open for real execution/clone lineage, historical/full CLI/server/disk costs,
account-wide/jobpilot quota and explicit safe operational continuation.


## R06/R17 preparation: historical allocation scenario — 23 October 2026

research_historical_debits.py binds the verified M20 three-file pack and reads
original common resource/semantic/code policies readonly. It proposes full
admission allocations for every visible standalone API/legacy-attempt/fixture
reservation, retaining failure/pending rows and ambiguous replay/copy records.
Existing common/numeric charges are not repeated. An already-bound inner path
requires exact operation linkage instead of automatic additional charging.
Known token overruns charge at least recorded usage; missing values do not mean0.
Allocations are not proven consumption upper bounds or full server/CLI costs.

Actual native v5 remains7total/fit1/numeric3/3. The review-only scenario across
9visible original journals proposes20total/fit12/proposal2/fixture1/semantic_live1/
code_check1/numeric3,6questions and96000input/6144output/565000ms allocations.
Original caps24total/fit12/600000ms remain unchanged. Scenario balance is4actions/
64000input/4096output/35000ms: fit/proposal alternatives are0 by kind/wall limits.
Other kind counts are alternative uses of the same balance and cannot be added.
Numeric remains completed-cache-only. These hypothetical numbers are not applied
usage, an actual consumption total or permission to start an operation.

Activation stays disabled for unresolved lineage/4missing synthetic bindings,
incomplete account/jobpilot scope, unknown hard consumption bounds and lack of an
approved operational continuation protocol. No apply/migrate/run/reserve command
exists. Four private files store policy/binding/original policies/proposal; verify
rechecks original9journals and recomputes the entire proposal. Rehashed activation,
policy/source changes and inner-path double charging fail closed.

1959tests/83.58s passed (14new/1945previous); two real readonly CLI calls preserved
native journals/caps. Tests cover hand allocation totals, nullable/overrun tokens,
kind exhaustion, alternative budgets, source/binding/activation tampering and
private replay. The compatibility profile repeats two older bounded R19stress
scopes; the debit CLI creates none. Seven private JSON are in
.local/research-historical-debits-real-20261023; all1108prior files outside two owned
docs and all9original journals stay unchanged. R06/R17 remain open. M21 separately
runs one finite original BTC/ETH capture under its frozen4poll/8GET plan, without
model/fit/provider/budget changes or touching main PostgreSQL/services/models.


### Current provider metadata qualification (M23, 23 October2026)

Three OpenRouter metadata GETs (catalog, singular model endpoint, current key) verified
the exact pinned nvidia/nemotron-3-super-120b-a12b:free with prompt/completion0.
Both existing bounded catalog and targeted receipts match. No prompt/generation was sent.
Provider-declared free daily quota is50/50; key limit100/remaining100/usage0 is
not a zero spend cap or account-wide billing proof. Shared jobpilot settings unchanged.

Current jobpilot primary OpenAI, simple router pool and cloud Ollama are not inherited.
CryptoForge local-only Ollama metadata GET failed backend_unavailable; no pull/load/start.
MemAvailable2085330944B at18:46UTC is below pinned3221225472B requirement;
unpacked runtime/model capacity remains unverified. R05/R10 stay open.

Private8file evidence pack (6JSON/2operator scripts) preserves selected metadata,
bounded process controls and source hashes without key/env contents. Offline verification
adds zero requests. CPU4s/AS256MiB/file2MiB/NOFILE64/parent20s and killpg/reap
were enforced for the metadata operator. Previous1959tests/83.58s remain the last
runtime profile: no runtime edits/new tests claimed. All1118protected files and
original API/common journals unchanged. Native hard token bounds, shared quota,
real generation/model gold/training benefit and account billing remain unqualified.

M21 original prospective operator stopped after1of4polls: it looked for poll_completed,
while the original ledger records poll_complete. Failure/original source retained;
future labels/native value parity were not obtained. No automatic retry occurred.


### Retained partial prospective source capture (M21, 23 October2026)

Original source registration preceded18:15UTC; one18:16UTC poll recorded2GET,
4events/240versions, BTC/ETH ready and0forecasts. The private operator failed
before second HTTP because it queried poll_completed rather than native poll_complete.
The frozen failed operator/plan/logs and original first-seen database remain unchanged.
A separate corrected future template is not executed. Original8GET scope has2used/6remaining;
a new full two-partition capture requires4poll/8GET, so no retry/new namespace was started.

M14 native source projection/replay preserved4blocked samples and original revision lineage.
M15 checked2real120candle feature windows,0real training examples: future labels remain null.
M16 independent Fraction oracle matched14/14available components exactly,0mismatch,
using2workers/480source rows; native features ran once/240rows. Original source DB was
not copied. M15 remains blocked, full M21/R02 incomplete, training admission=false.

Private retained archive binds all source hashes, failure evidence and3existing audit packs.
All1126previous protected files outside2docs and original budget/source hashes stay unchanged.
Prior1959tests/83.58s is retained, no new tests claimed. No new requests/fits/model prediction/
numeric attempts, primary PostgreSQL/service/runtime changes or promotion occurred.


### Actual native loader source-selection audit (M24, 23 October2026)

research_loader_audit.py binds an original verified M15 pack and its M14 timeline.
Two train/validation snapshots select latest completed deliveries known at the
information cutoff, up to512unique candles/pair. The native worker imports the
reviewed main runtime and invokes ModelTrainingRunner._load_examples with a
controlled readonly original-version reader; it never fits/predicts/publishes.

The explicit audit configuration is5m/120bar features/3bar horizon/512lookback/
600s freshness/coverage1.0. It does not attest actual production config or the
operational PostgreSQL reader. Both exact values and source_id/revision lineage
are compared to original decision-as-of examples; a repeated delivery timestamp
of unchanged content is not a version mismatch. Missing examples stay null.

A synthetic A→B→A revision passes all4M15 common-core examples but changes2
actual train loader examples; validation2still match. Stable versions match4/4.
An older-volume revision preserves feature values while exposing2version-only
failures. These are fixed compatibility fixtures, not candidate research attempts.

Prepare runs one trusted native worker. Verify freshly reruns the actual loader
and rejects any changed saved-native result, then recomputes the full report.
Private5file pack policy/request/packet/native/audit, checked original source
hashes and reviewed runtime pins prevent silent stale bindings. Worker limits
CPU8s/AS512MiB/file2MiB/NOFILE64/parent15s, cleared env/killpg/reap/private scratch;
whole CLI/server/security qualification remains open.

The retained real M21 source is stale at both information cutoffs:2CLI calls/
2workers/4loader invocations/8reader calls/960rows total yield0examples and0value
comparisons. No real label parity/admission claim. Original DB and all budget
hashes unchanged.1987tests/93.83s pass,28new/1959prior, including2previous R19
stress scopes. Private8JSON artifacts preserve the result; all1160baseline files
outside2owned docs remain unchanged. R02/R03 and19root groups stay open.

CLI: python -m cryptoforge.research_loader_audit prepare --project ORIGINAL_MAIN
--value-pack ORIGINAL_VERIFIED_M15_PACK --directory NEW_PRIVATE_PACK; verify
--directory PACK performs fresh native execution without network/fit/model work.


### Existing-only semantic phase CLI (M25, 23 October2026)

python -m cryptoforge.research_phase_semantic_cli provides semantic-live and
semantic-source on the established v5 journal with the same ledger/policy flags
as research_phase, plus catalog/experiment/questions or snapshot/registry/packet
and explicit model digest/local endpoint. No migration/fit/proposal/numeric routes.

Original phase/coordinator/inner sources stay byte-identical: their code hashes
are persisted configuration pins. The wrapper reuses exact native request/effect/
allocation/quota/cache/normalization contracts and a fixed handler with an existing-only
inner journal factory. mode=rw/BEGIN IMMEDIATE checks original tables/manifest;
no CREATE/initialization is possible when the file is absent or deleted before open.
Existing canonical regular nonempty common/live files≤16MiB; private0600inner;
exclusive0600output separated from source/journal paths. Missing catalogs stay missing.

Both routes charge once/cache once in synthetic tests, including cross-entry reuse
of an original native API completion. Failed/cancelled/deadline operations remain
charged; policy expansion/copied/unmigrated journals/remote endpoints/alias/deletion
races are refused. These20tests do not qualify a real LLM.

Two original CLI invocations stopped on the existing synthetic common's missing live
binding before native dispatch/backend/input qualification. None of4missing original
inner files were created.7actions/fit1/numeric3/3 and9journals unchanged. R10 still
requires installed free local backend/resources/real typed round trip/native input
bounds/quality and an approved operational data/budget continuation.

2007tests/97.01s passed,20new/1987prior, including2previous R19stress scopes.
Private5JSON artifacts preserve2refusals and source/profile evidence; all1172prior
protected files outside2docs, old native hashes and primary local PostgreSQL/services
remain unchanged. No new original reservation/model/provider/fit/numeric execution.


### Fixed trusted seccomp diagnostic (M26, 23 October2026)

research_seccomp_probe inspect/verify accepts only a new private directory or
a saved receipt; no command/program/mount input. Exact libseccomp2.5.5/x86_64
ABI and184byte BPF are pinned before execution. Export-only preparation installs
no filter.15default-allow deny rules compile;8safe probes return EPERM with
filter count+1/mode2/NoNewPrivs1. Socket creation worked before loading.
Invalid harmless exec/clone/connect/bpf arguments avoid side effects if rules fail;
only8of15rules are mechanically tested. Parent filter stays unchanged.

The fixed namespace child retains CPU2s/AS128MiB/file1MiB/CORE0/NOFILE64/
wait5s+cleanup1s/cap0/cleared env/readonly canary/home hiding. Verify checks
original canary/argv/runtime/source/policy/export/counters without installing
another filter. Receipts are historical diagnostics, not authenticated kernel
attestation. Default-allow, broad /usr, no candidate runtime integration and
unqualified aggregate/process-tree/full mount/syscall/security flags stay explicit.

2030tests/95.83s pass,23new/2007prior; full profile includes1fixed filter and
2previous R19stress scopes. One early focused filter under a previous source
revision plus1final CLI filter makes3diagnostic children total,0candidate attempts.
Private8file archive retains the184Bexport/operator/freeze and original probe
evidence. All1179previous protected files outside2docs,9original journals,
main/local PostgreSQL/services/registry/model remain unchanged. R19 and19root
groups remain open; numeric3/3 stays completed-cache-only.


### Reduced fixed runtime mount probe (M27, 23 October2026)

research_runtime_mounts inspect/verify exposes only fixed diagnostic directories.
Ten readonly runtime mappings include Python3.12 binary, stdlib and8specific
libraries; no whole /usr. Another readonly canary mount is separate.7checks
verify exact executable/library directories, hidden unrelated paths, readonly
placeholder and declared internal/dangling external stdlib symlinks.

Streaming inventory binds1222files/70400092readable disk bytes, not RSS.
Limits2048files/16MiB each/128MiB total/512KiBmanifest; observed manifest188978B.
Special/unknown symlink files and concurrent replacement are refused; nonblocking
open prevents FIFO races. Runtime bytes are not copied, only file metadata/hashes.
The child preserves fixed184Bseccomp/8EPERM probes, CPU2s/AS128MiB/FS1MiB/
CORE0/NOFILE64/deadline5s+cleanup1s/cap0/cleared env/readonly proc/dev/tmp8MiB.

Inspect compares two original inventories around the fixed child. Verify rehashes
installed files and original argv/canary/source/evidence without executing a child
or loading a filter. Broad security, full syscall allowlist, aggregate limits and
candidate runtime integration remain unqualified. The original arithmetic worker
and persisted phase code stay unchanged.

2048tests/97.35s pass,18new/2030prior.3new reduced-profile diagnostic children
(focused/profile/CLI); full profile also repeats1previous M26filter and2R19stress
scopes. Private6file pack and5owned tracked files preserve evidence; all1191prior
files outside2docs/9original journals/main/local PostgreSQL/services unchanged.

M28 is separately preregistered before20:00UTC: original failed M21/2GET retained,
new future BTC/ETH slots20:01/20:16/20:36/20:51UTC allow≤8newGET/≤10cumulative.
Unused old allowance is not reused, no old source cap/history or numeric3/3 limit
changes. This is source-only compatibility; real labels/parity await completion.


### Actual native local REST precision audit (M29, 23 October2026)

research_native_rest_audit prepare/verify exercises reviewed main native reader/loader
on fixed local127.0.0.1:54321,2GET/BTC+ETH/5m/144rows. Existing0600key stays
in worker memory; no redirect/proxy/remote/query/method expansion, response cap512000B.
Private validated original wire bodies preserve numeric text; native default JSON
float→Decimal is compared to Decimal parsing of those same bytes. Synthetic numeric
literals expose precision loss. Real20:13:32UTC responses show1440scalar checks/
0mismatches and identical native/exact21ETH examples. BTC has gapped cache; source
coverage0.5 below explicit audit minimum1.0. This is not training admission.

Known-closed coverage requires close≤ingested_at≤asof. BTC142eligible/144,2cached
forming,1gap103500s (21Oct23:00→23Oct03:45), latest delivered14:00UTC; ETH143/144,
1cached forming,0gaps. Query fetches latest rows without an asof SQL filter; current
ingested_at cannot establish historical revision/first-seen. Production service
config/direct PostgreSQL MVCC/schema and venue-ID provenance remain unverified.

Verify replays retained wire through the actual native worker with0HTTP, recomputes
all scalars/examples/trace and rejects changed results; current DB is not requeried.
CPU8s/AS512MiB/FS2MiB/CORE0/NOFILE64/parent15s/cleared env/killpg/reap. No fit/
model prediction/provider/mutation.2071tests/101.53s pass,23new/2048prior;9private
JSON artifacts,6owned tracked files. All1200previous files outside2docs/original9
journals/keyfile/main/local DB data/schema/services unchanged. R02/R03 stay open.

M28 same-original-source host continuation completed all four slots and audits.
The20:01DNS failure is retained without retry/refund: two validation samples are
available, two train samples remain missing; no data admission or numeric allowance.


### M28 final original source compatibility — 23 октября 2026

- [x] Четыре фиксированных слота завершены: первый сохранил DNS failure, следующие три выполнены в host network context на том же source namespace. Нет повтора первого слота, возврата бюджета или копии source SQLite.
- [x] M14/M15/M16/M24 prepare/verify выполнены: 2 из 4 samples имеют полные validation-примеры; 14 компонентов признаков и 2 loader comparisons совпали без расхождений. Два train samples остаются недоступны.
- [x] Сохранены 16 events, 254 versions, 0 forecasts и первоначальная ошибка. Новое окно ограничено 8 GET attempts; вместе с M21 — максимум 10, без изменения numeric lifetime 3/3.
- [x] Все 44 архивных файла повторно сверены 26 октября с original final-artifacts; private permissions 0700/0600 и 1211 прежних файлов вне двух документов сохранены.
- [ ] Допуск данных к обучению: metadata/native value/loader status остаются blocked; original coverage, approved protocol, global exposure inventory и operational PostgreSQL integration ещё не квалифицированы.

[Сохранённый итог](../.local/research-prospective-source-continuation-real-20261023/verification.json). Final-test/forward даты исходного протокола не сдвигаются при историческом replay. R02–R20 остаются открыты; scoped completion M28 не означает training admission.


### R02/R18/M30 — независимая сверка исходных цен и будущих меток, 26 октября 2026

- [x] Отдельный `research_label_reference_worker.py` читает только original source SQLite через mode=ro/query_only и повторно сверяет checksum до/после. Нет imports trainer/runtime, HTTP, fit, model prediction или candidate program. Для доступного sample читаются last feature close и все 3 label candles; symbol/open/close/raw version/known-at/observed-at/first-seen/cutoff и полный горизонт проверяются независимо.
- [x] Формула `(future_close-reference_close)/reference_close` считается через Fraction из исходных decimal lexemes, затем переводится в binary64. Сверяются 2 endpoint lexemes, return hex, long/short labels и 2 endpoint times без tolerance. Строгие float-domain `>`/`<` соответствуют pinned price target; execution fees не вычитаются. Min-return0.003/cost0.002 — старые unapproved compatibility parameters.
- [x] Устранён пробел M15: самосогласованные подставные цены в native report могут пройти внутренний arithmetic reference; M30 обнаруживает их по original raw revisions. Проверены one-ULP changes, midpoint horizon identity/availability, private rehashed receipts, missing/null samples, фиксированный subprocess env/deadline/cleanup и отсутствие native rerun.
- [x] Real M28 replay: **2 validation label windows, 4 endpoint prices, 4 binary labels, 8 original rows, 0 mismatch**. Два train samples остались missing/null. `all_samples_have_label_comparisons=false`, underlying native/metadata status=blocked, training admission=false. Это исторический replay original context23Oct; final-test24Oct/forward26Oct не объявляются сегодня будущими или unread.
- [x] Synthetic test clocks зафиксированы только в двух test fixtures. Первый focused run:16passed/28fixture errors из-за calendar-dependent holdout; после test-only repair44passed. Production time gate/real protocols не менялись; отдельная regression проверяет отказ expired final-test по26Oct.
- [x] Общий профиль: **2116passed/130.31s**,44 новых label tests +1 expired-gate regression +2071 прежних. Опциональные прежние bounded cgroup/Bubblewrap diagnostics включены; это synthetic compatibility tests, без новых operational model/provider/source/fit/candidate actions. Real CLI prepare+verify запустили2 independent label workers и0native workers.
- [x] Worker bounds: CPU8s/AS512MiB/FS2MiB/CORE0/NOFILE64, parent15s, packet2MiB/result256KiB, private scratch и killpg/reap. Эти child bounds не объявляются полным server/parent/CLI accounting. Original1257files outside4reviewed docs/tests,9original journals,18main sources/local DB/services/model и numeric3/3 preserved.
- [ ] R02: contiguous approved dataset/полный exposure inventory/operational reader qualification и согласованный protocol.
- [ ] R18: независимая whole-packet/cross-environment qualification, approved actual integration и statistical patch study. Две label windows не доказывают качество или прибыльность модели.

[Evidence](../.local/research-label-oracle-real-20261026/verification.json), [real comparisons](../.local/research-label-oracle-real-20261026/labels/audit.json). Ordinary exact calculations follow [TypeSafe design guidance](https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md); [Fraction](https://docs.python.org/3.12/library/fractions.html) и [float.hex](https://docs.python.org/3.12/library/stdtypes.html#float.hex) сверены с актуальной документацией.19root groups R02–R20 остаются открыты.


### M31 registered future source window — 26 октября 2026

- [x] Original source зарегистрирован до05:35UTC по frozen protocol в host network context. Предыдущие10source GET attempts и ошибки сохранены; новое окно имеет отдельный explicit maximum8, cumulative18. Numeric3/3 completed-cache-only не меняется.
- [x] Frozen train anchor05:35/fit cutoff05:55; validation anchor06:10/information end06:30UTC; target0.003/cost0.002 остаётся unapproved compatibility config.8previous exposure entries объявлены; global exposure inventory incomplete.
- [x] Fixed poll05:36: BTC/ETHready,240versions/4events, completed05:36:00.647344UTC.
- [x] Fixed polls05:51/06:11: оба BTC/ETHready; latest12events/254versions.
- [x] Последний fixed poll06:26 completed; all16events/260versions сохранены, без retry.
- [x] M14/M15/M16/M24/M30 completed:4metadata/native/loader samples,28features/4independent labels,0mismatch; admission=false.

Это future source compatibility, без fit/model/provider/numeric/promotion или допуска данных. Новый final-test28–29Oct и forward30–31Oct не читаются; старые dates M28 не переписаны. [Registration](../.local/research-prospective-source-window-registered-20261026/registration.json).


### R19/M32 — фиксированный default-deny syscall allowlist, 26 октября 2026

- [x] Отдельный trusted diagnostic child использует23fixed syscalls с default EPERM. libseccomp2.5.5/x86_64 и248B BPF pinned SHA821fd908d01ddf34c504bd8cc900f15559241ae30d9a0817b0c538ec3d663e6f. Все прочие syscall numbers закрыты политикой; это отдельный профиль, прежние default-allow probes и persisted numeric worker не изменены.
- [x] Реальные9safe denial probes: прежние8 + harmless getppid, который не входит в старый denylist. Baseline socket/getppid success до filter; после filter EPERM, Seccomp_filters+1/Mode2/NNP1. Parent filter unchanged; filter устанавливается только после imports/startup внутри child. Syscall arguments в23allow rules не ограничены; arbitrary candidate Python не разрешён.
- [x] Независимый offline interpreter проверяет31forward-only BPF instructions,55number boundary representatives ×5architecture representatives=275cases. Только arch/syscall-number loads +EQ/GE/RET; классы покрывают весь uint32 domain. Native allow set ровно23, остальные native numbers EPERM; unsupported ABI получает kill_thread. Это проверка semantics exact exported bytes, без kernel filter load в verifier и без authenticated kernel attestation.
- [x] Сохраняются reduced10runtime mappings/7visibility checks/readonly canary, private namespaces/cap-drop/env и inherited RLIMIT CPU2s/AS128MiB/FS1MiB/CORE0/NOFILE64/parent5s+cleanup1s. Полного aggregate parent/CLI/server/disk/log accounting это не даёт.
- [x] **2148passed/109.64s**,32new/2116prior: policy/ABI/BPF/default-action/extra allowrule tampering, unsafe mount rejection, missing evidence, original inventory and offline verify. Четыре новых fixed-child runs: initial validator revision, focused test, full profile, current real CLI; ранний receipt и reconstructed original source byte-for-byte hash сохранены отдельно. Новый candidate/fit/provider/source operation из шага не выполнялся.
- [x] Verify rehashes installed inventory, original canary/command/source/runtime pins и пересчитывает static BPF semantics; не создаёт child/filter. Private11files,5owned tracked files.1274previous files outside2docs/original9journals/API/common/main/local DB/services/model unchanged. Numeric3/3 completed-cache-only.
- [ ] R19: actual arithmetic/candidate runtime integration, reviewed argument/access policy, independent security review и полный resource accounting. Default-deny diagnostic не квалифицирует произвольный код или существующий numeric worker.

[Evidence](../.local/research-syscall-allowlist-real-20261026/verification.json), [current probe](../.local/research-syscall-allowlist-real-20261026/probe/receipt.json). [Linux seccomp documentation](https://docs.kernel.org/userspace-api/seccomp_filter.html) и [pinned libseccomp header](https://github.com/seccomp/libseccomp/blob/v2.5.5/include/seccomp.h.in) сверены перед реализацией.19групп R02–R20 остаются открыты; M31 future source capture продолжается отдельно.


### R01/R03/M33 — свежий local model registry snapshot, 26 октября 2026

- [x] Existing reviewed inventory повторно вызван в bounded worker: CPU8s/AS512MiB/FS2MiB/NOFILE64/CORE0/parent25s/killpg/reap. Только local PostgreSQL127.0.0.1:55432, pinned psycopg3.3.6, authenticator→service_role, READ ONLY/REPEATABLE READ и максимум2latest rows per active/candidate в одном transaction. Credentials/полная service command/environment не копируются.
- [x] Snapshot05:37:24UTC: active event7Oct02:59:38, age1651065.63518s (старше36h), registry_available=false. Candidate event26Oct04:37:18, age3605.607954s, registry_available=true; bounded-window-candle-v1/closed_only/120features, lookback500/horizon3. Checksum/vector/order checks pass; actual execution parity не подтверждена.
- [x] Installed executor unit loaded, inactive/dead/MainPID0, gate/threshold0.5/maxage36h; configured model pin отсутствует. Это состояние только этого unit на момент среза, не утверждение об отсутствии иных процессов. Source functions/shapes/HEAD и files проверены до/после; native registry replay без prediction/inference/fit/promotion. Процесс не запускался и не перенастраивался.
- [x] Capture и offline verify existing tool совпали; сохранены8private artifacts. Runtime code не менялся, новых tests не заявлено; последний compatible profile2148passed/109.64s. Original9journals/1290old files outside2docs/main/local DB/schema/registry/service preserved.
- [ ] R03: свежий approved incumbent и целый experimental protocol всё ещё отсутствуют. Candidate не становится baseline автоматически; legacy active имеет unproven runtime input parity.

[Inventory](../.local/research-registry-refresh-real-20261026/inventory/inventory.json), [verification](../.local/research-registry-refresh-real-20261026/verification.json). Supabase/Postgres skills и current changelog/PG17 isolation docs сверены; schema/auth/migrations не менялись.19групп R02–R20 остаются открыты.


### R06/R19/M34 — aggregate fixed offline verifier accounting, 26 октября 2026

- [x] `research_cli_accounting.py` имеет только2closed modes: existing independent source-label verify и offline syscall-allowlist verify. Весь fixed verifier bootstrap/import/validation и его потомки помещены в отдельный transient user service. Нет command/program/model/provider/HTTP/SQL action API. Перед работой сверяются frozen implementation и actual cgroup controls.
- [x] Kernel memory.max128MiB/swap0/pids8/CPU50000 per100000usec, RuntimeMax15s/stop1s/KillMode=control-group; per-process CPU8s/AS512MiB/FS2MiB/CORE0/NOFILE64/NNP, empty environment exceptPATH/LANG. Stdout/stderr=null; private controls/result≤64KiB each. Aggregate disk quota не установлена, temporary per-file bounds не объявляются общей disk quota. Trusted host verifier не объявляется candidate sandbox.
- [x] RemainAfterExit/Type=exec сохраняет final cached CPUUsageNSec/MemoryPeak после полного выхода main/descendants. Final ControlGroup empty, original cgroup отсутствует; только собственный generated unit останавливается/reset и удаляется. MemoryPeak — cgroup charge peak, не сумма RSS/полное физическое потребление shared pages. TasksCurrent/IOReadBytes/IOWriteBytes на этом runtime unavailable и остаютсяnull.
- [x] Real source-label CLI: CPU521388000ns, charged memory peak26943488B, wall1.131977s с cleanup. Real allowlist CLI: CPU445121000ns, peak70012928B, wall1.121079s. Observer CPU/helper CPU измерены отдельно; observer RSS — process lifetime high-water mark. Unit counters не включают observer/systemd manager/внешние DB или LLM servers; final receipt serialization observer не входит в снятый observerCPU. Это scoped measurement, не account-wide cost.
- [x] Verify повторно сверяет original private controls/result, current source/runtime/argv, исходный pack/report и saved counters без systemd calls/нового unit/нового worker. Receipts не являются authenticated kernel attestation. Изменение claimed disk/server/candidate qualification отвергается.
- [x] Первый focused run24passed/1failure выявил неверную label-pack→value-pack binding при offline verify. Связь исправлена; initial source SHA/receipt и failure summary сохранены. Повтор25passed/5.09s. Full profile **2173passed/116.26s**,25new/2148prior. Total10new transient units: prototype1, initialmodule1, focused4, full2, real2; все удалены. Accounting test fixtures также вызывают trusted fixed filter для подготовки pack; это не candidate trials.
- [x] Сохранены15private artifacts и5owned tracked files;1296previous files outside2docs/original9journals/API/common/main/local DB/schema/services/model preserved. Operational provider/model/fit/numeric actions0, numeric lifetime3/3 completed-cache-only. Ранее начатый source capture M31 отдельно продолжает свой frozen8attempt budget.
- [ ] R06/R19: actual operational CLI/server lifecycle/cold-start resources, account-wide costs, aggregate log/disk bounds, admission-budget integration и independent security review ещё не завершены. Fixed readonly accounting не предоставляет новых попыток модели или cap increase.

[Verification](../.local/research-cli-accounting-real-20261026/verification.json), [real measurements](../.local/research-cli-accounting-real-20261026/observation.json). [systemd255 transient services](https://www.freedesktop.org/software/systemd/man/255/systemd-run.html) и [resource controls](https://www.freedesktop.org/software/systemd/man/255/systemd.resource-control.html) сверены.19root groups R02–R20 остаются открыты.


### R06/R18/M35 — accounting replay после переноса checkout, 26 октября 2026

- [x] Post-transfer проверка M34 обнаружила зависимость v1 argv hash от текущего package path. Original staging v1 replay проходит, импорт из другого checkout отказывал. Старые15artifacts и original v1 source сохранены; v1 receipts не мигрируются и не переписываются.
- [x] V2 receipt явно хранит `original_package_source_directory`. Offline verifier проверяет regular original module SHA и восстанавливает original command только для hash comparison; команду/исходный package path не исполняет. Public inspect всегда запускает текущий фиксированный пакет. Closed modes/resources/operational budgets не расширены; отдельныйconfigv2,configv1 сохранён.
- [x] Regression реально копирует unchanged module в другой checkout, затем проверяет оба modes с подменённым `__file__`: same original source/argv/results/counters match, systemd API и child execution при verify запрещены тестом. Изменение исходника, policy, claimed qualifications и недоступные paths дают отказ.
- [x] Focused26passed/5.04s; full **2174passed/116.61s**,1new/25updated/2148prior.6new transient diagnostic units (focused2/full2/real2) завершены и удалены. Real v2 source labels CPU614446000ns/charged peak26009600B, allowlist CPU451342000ns/peak19685376B; I/O unavailable/null, disk/server/global costs остаются open.
- [x] Сохранены10private artifacts/5owned tracked files;1312previous files outside4reviewed source/test/docs/original9journals/main/local DB/services/model unchanged. Source history/caps/numeric3/3 не сбрасывались. M46повторно импортировал actual worktree module и успешно проверил обаv2receipts с запрещённым child creation; services/workers0. Original initial verification.json сpending флагом сохранён как исторический pre-transfer receipt.
- [ ] R06/R18/R19: operational deployment/security/полный server/disk accounting и statistical model/patch validation не квалифицированы этим portability fix.

Последующий M31 capture завершён4/4slots; результат приведён в его final evidence. Это не закрывает R06/R18/R19.

[Evidence](../.local/research-cli-relocation-real-20261026/verification.json).19групп R02–R20 остаются открыты.


### R02/R04/R18/M36 — actual primary candidate packet, 26 октября 2026

- [x] Bounded readonly `research_primary_packet_audit.py` связывает original M33 embedded candidate26Oct04:37 с двумя original content-addressed gzip files. Проверены compressed/uncompressed hashes, declared lengths, private owner files, canonical paths, ≤4MiB input/≤1MiB source bundle/≤10000examples/32pairs/16sources/256KiB report. Gzip читается только до declared size+1; duplicates/oversize/checksum/path errors отвергаются. Cache/новые datasets не реконструируются.
- [x] Original20pair candidate: source admission сообщает7540examples/coverage1.0; snapshot содержит **7380 =5180train+1060validation+1140test**,160examples не попали в сохранённые splits. Все20pairs присутствуют.7archived source hashes совпали с fitted/current source; archived code только прочитан, не импортируется/исполняется. Это actual primary dataset, отдельный от BTC/ETH compatibility windows M28/M31.
- [x] Проверены schema/7finite features/pair+time identities/duplicate/order/20minute endpoint horizon, binary labels против сохранённого future_return и strict threshold0.003, metadata/cost0.003, split counts/purged boundaries. Train labels end25Oct18:45; validation/fit information end23:30; test/evaluation end26Oct04:35UTC. Data snapshot26Oct04:36:59.978276; late capture не восстанавливает historical availability.
- [x] Согласованность reported confusion counts/metrics с original labels проверена для2heads×3splits. `positive_rate` в metrics — доля предсказанных положительных классов; отдельно вычислена actual prevalence и always-negative-class accuracy. Train-prior Brier/log-loss baseline пересчитан из labels; model Brier/log-loss/AP взяты из сохранённого отчёта, model probabilities не пересчитывались.
- [x] Long validation: saved accuracy0.780188679 vs always-negative0.783018868; reported Brier0.166225732 vs train-prior0.171528828. Long test Brier0.198927626 vs0.207562960 лучше baseline; short test0.223979851 vs0.221795377 хуже. Эти разные сигналы сохраняются раздельно; classifier accuracy/baselines не являются trading profitability/no-trade economic evidence. Significance/retuning/promotion не заявлены.
- [x] Сохранённые rows содержат derived features/returns/labels, без original OHLCV/row-version/first-seen lineage. Native source selection и независимое пересчитывание20pair real features/price labels этим не проверяются. Все3existing splits объявлены просмотренным development material:60pair/split exposure entries описывают example anchor ranges. Global exposure inventory и raw lookback availability остаются incomplete.
- [x] **2207passed/116.59s**,33new/2174prior: label/return/schema/count/metrics/source tampering, strictsplit/pair/horizon bounds, train-prior consistency, gzip bounds/duplicates/checksums, archived source nonexecution, rehashed admission refusal. Focused33passed/0.25s; initial scoped audit/source SHA сохранён. Real prepare/verify bounded CPU8s/AS512MiB/FS2MiB/CORE0/NOFILE64, prediction/refit/DB/HTTP/provider/candidate actions0.
- [x]10private files/5owned tracked files;1325previous files outside2docs/original9journals/main/local DB/schema/services/model preserved. Source snapshots не копируются/переписываются; numeric3/3 cache-only. Last M31 polls05:36/05:51/06:11ready; original06:26slot ещё ожидается.
- [ ] R02/R04/R18: original market lineage/value parity, independent per-row probabilities/causal attribution/strategy-cost report, approved baseline/protocol и statistical study ещё нужны. Новый fit/evaluation/threshold search из этого чтения не разрешается.

[Evidence](../.local/research-primary-packet-real-20261026/verification.json), [actual primary audit](../.local/research-primary-packet-real-20261026/packet/audit.json).19root groups R02–R20 остаются открыты.


### R04/R08/M37 — actual primary temporal groups/overlap, 26 октября 2026

- [x] Bounded readonly dependence audit связан с original M36 primary packet. Exact same input anchors объединены в группы; отдельно посчитаны nominal rows, by-pair labels/counts, pair/time HHI и inverse-HHI group count. Последний не объявляется statistical effectiveN.
- [x] Actual train5180rows/259anchors, validation1060/53, test1140/57; по20pairs на каждом anchor. Pair HHI=1/20; time HHI=1/259,1/53,1/57. Source rows/label values не изменялись и не подавались в model prediction/fit.
- [x] Price-return interval начинается от close последней feature candle (input_open+5min) и заканчивается label_end (input_open+20min):15minutes. При touching endpoint overlap=false. Sweep проверил максимум3overlapping time intervals/60example intervals; greedy earliest-end selection даёт87/18/19неперекрывающихся time windows.
- [x] Групповые counts/descriptive nonoverlap не доказывают independence, statistical effectiveN, significance или profitability. CI/bootstrap/effectiveN не вычисляются; ни model weights, ни classifier probabilities/thresholds не меняются. Для R08 всё ещё нужны preregistered temporal evaluation/uncertainty/stopping rules.
- [x] **2222passed/112.52s**,15new/2207prior: simultaneous assets,5m overlapping and touching horizons, gaps/order invariance, unbalanced coverage HHIs, duplicates/type/schema/horizon/count bounds, private/rehashed CI/admission refusal. Focused15passed/0.19s. Real prepare+verify CPU8s/AS512MiB/FS2MiB/CORE0/NOFILE64, новые model/provider/fit/DB/HTTP/candidate actions0.
- [x]6private artifacts/5owned files,1338previous files outside2docs/original9journals/main/model/DB/services preserved. M31 all4source slots и source/value/feature/label/loader audits завершены; separate canonical archive transfer следующий. Numeric3/3 cache-only.
- [ ] R04/R08: causal regime/strategy-cost attribution, actual probability rows и controlled study/statistical validation остаются open; эти nominal examples не считаются independent repeated trials автоматически.

[Evidence](../.local/research-primary-dependence-real-20261026/verification.json), [group audit](../.local/research-primary-dependence-real-20261026/dependence/audit.json).19групп R02–R20 остаются открыты.


### R02/R18/M31 — final original future source window, 26 октября 2026

- [x] Все original slots05:36/05:51/06:11/06:26UTC завершены в host network context.16events/260versions/0forecasts,8public GET attempts; prior10retained/cumulative18. Source SQLite остаётся в original namespace, без копии/reset/retry/backdating. Все source/native profile hashes сохранены.
- [x]4/4metadata samples consistent,4/4native examples values_consistent,28independent feature components/0mismatch,4independent label windows/0mismatch. Actual `_load_examples` дал4comparisons/0value/0version mismatch: loader_matches_causal_samples. Это точный replay только этих bounded BTC/ETH decision windows.
- [x] M14/M15/M16/M24/M30 prepare/verify завершены.4native metadata/value/loader workers,2independent feature +2independent label workers; fit/model/provider/numeric candidate actions0. Последний full profile2222passed; новых tests из source capture не заявлено.
- [x] Fixed train anchor05:35, decision05:37, label end05:50, fit cutoff05:55; validation anchor06:10/decision06:12/label end06:25/cutoff06:30. First-observed history не backdated на historical candle opens. Closed-window metadata/values проверены внутри этого venue namespace; непрерывное market coverage/независимость/native source_poll_completeness не заявлены.
- [x] Final-test28–29Oct и forward30–31Oct не читаются. Cost0.002/min-return0.003/horizon3 — unapproved compatibility target;4tiny samples не квалифицируют ML study. Actual20pair primary dataset M36 имеет отдельные raw lineage requirements.
- [x] Canonical M31 checklist обновлён с actual results; original1347files outside2docs/9journals/main/local PostgreSQL/model/services preserved. Numeric3/3 completed-cache-only. Source SQLite не переносится в archive/new allowance.
- [ ] R02/R18: approved actual dataset/protocol/global exposure inventory, primary20pair source history/integration/cross-environment/statistical study остаются open. Training admission=false.

[Final verification](../.local/research-prospective-source-window-real-20261026/verification.json).19групп R02–R20 остаются открыты. M21failed/M28partial результаты сохранены; успешный M31 их не отменяет.


### M38 registered future primary20pair local raw source — 26 октября 2026

- [x] Metadata/schema/unique-index preflight и EXPLAIN без ANALYZE:2READ ONLY metadata transactions,0market rows. Existing authenticator→service_role/REPEATABLE READ/3s statement/250ms lock/5s idle timeout, pinned psycopg3.3.6. Новый SQL использует fixed exchange/market/symbol/timeframe composite index, limit500per20symbols; schema/index/role не менялись.
- [x] В06:39:24UTC доanchor06:45 заморожены original20pair cohort из M33candidate04:37,2capture slots06:46/07:01UTC, decision06:47/label end07:00/information end07:05, features120/horizon3/min-return0.003/cost0.003. Это новый future raw source compatibility protocol, не обучение/допуск/повтор старых numerical attempts.
- [x] Source sessions≤2, по≤10000raw rows/16MiBJSON/4MiBgzip, latest500rows perpair до known-closed filtering. Сохраняются UUID/OHLCV/timestamps/storage_xmin/physical revision hash, DB snapshot/namespace и client-observed clock. Current cache observation не backdated в historical first-seen. Preflights отдельно2sessions; publicHTTP/provider calls0.
- [x] Frozen worker CPU8s/AS512MiB/FS16MiB/CORE0/NOFILE64, parent15s+killpg/reap; collector35min/no retry. Original9journals/main18profile protected; numeric3/3 cache-only. Ни исходные таблицы, ни model/registry/service не меняются.
- [x] Feature raw snapshot06:46UTC completed; original receipt/hash preserved. M39 checked actual selected windows.
- [x] Label raw snapshot07:01UTC completed; snapshot receipt is distinct from complete closed-label coverage.
- [x] Original-source lineage/availability and native/independent value audit completed M39:13feature windows/91components match,0complete captured label horizons; anchor/late missing data unchanged.

- [ ] Полное исходное окно всех20pairs и полный label horizon, пригодные для согласованного исследования. Старый M38 не повторяется и не исправляется поздними данными.

[Registration](../.local/research-primary-cohort-source-registered-20261026/registration.json). R02/R03/R18 открыты; dataset/target не approved, global exposure inventory incomplete.19групп R02–R20 остаются открыты.


### M39 — исходные локальные строки и фактическая доступность, 26 октября 2026

- [x] `research_local_cohort_audit.py` связывает original frozen M38 plan/operator hashes, два исходных gzip и receipts, DB namespace/schema/unique key, UUID, storage_xmin и revision hashes. Читает только исходные файлы; новых SQL/HTTP запросов в аудите нет. Original cache observation не выдаётся за исторический market publisher first-seen.
- [x] Feature selection использует только первый снимок до decision06:47, label selection — второй до information end07:05. Native known-closed правило `close_time <= ingested_at <= client_observed_at` сохранено. Последующие восстановленные строки не заимствуются для ранних признаков.
- [x] На original20pairs полные120-candle features есть у13;91компонент независимого Fraction reference побитно совпал с native extractor/runtime feature functions.0полных label horizons;9label rows отсутствуют,17доставлены, но их ingested_at раньше close_time. Проверенных label windows0; mismatch0 здесь не означает успешную label compatibility.
- [x] Missing feature candles: AERO3,BR25,MEGA1,NEAR1,ONDO16,PEPE1,SUI24. AERO3/MEGA1/NEAR1/PEPE1 наблюдались только позднее и не использованы. Простая проверка возраста900s проходит у16pairs, но не гарантирует полного фиксированного окна13/20. Physical metadata revisions отдельно от изменений экономических значений/UUID.
- [x] Trusted fixed worker применяет только feature extraction и, при наличии horizon, example construction; actual production reader не вызывался. Model fit/prediction/provider actions0. Parent CPU8s/AS512MiB/FS16MiB/NOFILE64/CORE0; worker15s+killpg/reap. Первый input-bounded прототип без parent RLIMIT сохранён с точной исходной версией отдельно.
- [x] Full profile2246passed/119.56s pytest,120.27s wrapper.24focused tests после усиления фактического one-ULP regression passed/0.86s; код runtime после full profile не менялся. Отрицательные проверки покрывают clocks/namespace/hash/counts, forming/late/missing rows, native identity/flags, mismatch и offline replay без worker.
- [x] Current pack повторно проверен без повторного native worker. Initial receipt/source retained. Original1400files outside2docs,9journals и main profile проверяются при переносе. Numeric lifetime3/3 completed-cache-only;0new numerical attempts.
- [ ] Approved dataset/target/baseline, historical raw first-seen, полный global exposure inventory и actual production reader equivalence остаются R02/R03/R07/R18. Training admission=false; model promotion отсутствует.

[Проверка значений](../.local/research-local-cohort-audit-real-20261026/local/audit.json), [наблюдения](../.local/research-local-cohort-audit-real-20261026/observations.json), [verification](../.local/research-local-cohort-audit-real-20261026/verification.json). M38 collection завершён; его неполные окна не объявляются готовым training dataset.19групп R02–R20 открыты.


### M38 — завершение двух исходных локальных captures, 26 октября 2026

- [x] Оба заранее зарегистрированных слота06:46/07:01UTC завершены:2READ ONLY source transactions плюс прежние2metadata preflights. Retry0; HTTP/provider/model fit/prediction0. Original compressed payloads остаются в исходном namespace и связаны полными SHA/receipts; нового разрешения на numeric attempts это не создаёт.
- [x] M39 replay из фактического worktree выполнен без worker/SQL/HTTP:13полных feature windows,91компонент/0mismatch,0полных label horizons. Original9journals unchanged. Проверены1420защищённых файлов после M39.
- [x] Original stage PROGRESS и canonical чеклисты синхронизированы. Registration archive остаётся историческим подтверждением до запуска; completion archive добавляет фактические receipts/result.
- [ ] Полнота raw windows/labels для approved actual study остаётся открытой. Более поздние данные не изменяют статус исходного окна.

[Завершение сбора](../.local/research-primary-cohort-source-complete-20261026/verification.json), [M39 post-transfer replay](../.local/research-primary-cohort-source-complete-20261026/M39-post-transfer-check.json).19групп R02–R20 остаются открыты.


### M40 — поздние метки при неизменных ранних признаках, 26 октября 2026

- [x] После information end07:05 зарегистрирован отдельный late diagnostic protocol:1READ ONLY capture в07:42:49UTC,10000rows/6705914BJSON/1052490Bgzip. Старые2M38capture transactions сохранены; вместе3source transactions и прежние2metadata preflights. Public HTTP/provider/model fit/prediction/numeric actions0; retry0.
- [x] `research_late_label_audit.py` проверяет original M38file/source hashes/9journals, unchanged20pairs/target/feature anchor, same DB namespace/schema/unique key и current-observation-only provenance. Полный raw gzip остаётся в исходном namespace; archive хранит ссылки/хеши/receipts.
- [x] Original feature selection не меняется:13complete120bar windows,7missing. Late snapshot содержит18полных label horizons.13из них проверены с original ранними features:91independent binary64 components и13Fraction/native return/long/short label comparisons,0mismatch. Поздно восстановленные признаки не используются.
- [x] Отдельный `research_late_label_value_worker.py` сохраняет feature cutoff06:47 и проверяет late labels по их текущему observation time. Новый typed wrapper явно содержит `original_deadline_qualified=false`; он не меняет original information end07:05. Исходный worker один раз отказал в поздних метках; initial source/refusal сохранены, source повторно не читался.
- [x] Current cache ingested_at не доказывает, когда строку можно было наблюдать исторически. Поздняя сверка не утверждает, что данные обязательно отсутствовали весь период до07:05; она подтверждает значения, доступные в позднем снимке. Original M38/M390complete captured label horizons остаются прежними.
- [x]26focused tests passed/0.94s; full profile2272passed, wrapper119.29s. Проверены missing/forming/late rows, wrong namespace/counts/hash, rehashed invalid sources, попытки заменить originalfeatures/cutoff, nullable result/mismatch, safe CLI и timeout/interrupt killpg/reap. Verify повторно читает original source и пересчитывает references без нового worker/SQL.
- [x] Bounded parent CPU12s/AS512MiB/FS16MiB/CORE0/NOFILE64; fixed worker CPU8s/AS512MiB/15s+killpg/reap. Main runtime18source/value hashes и old journals protected. Перенос сохраняет1437old files outside2docs; код торгового main/DB/model/service не меняется.
- [ ] Actual production reader qualification, approved dataset/target/baseline/global exposures и новое numerical protocol/budget остаются R02/R03/R07/R17/R18. Late compatibility не даёт допуска к fit, candidate comparison, paper или promotion.

[Late audit](../.local/research-late-label-audit-real-20261026/late/audit.json), [observations](../.local/research-late-label-audit-real-20261026/observations.json), [verification](../.local/research-late-label-audit-real-20261026/verification.json).19групп R02–R20 открыты; numeric3/3 completed-cache-only.


### M41 — фактическая структура trainer и черновик продолжения, 26 октября 2026

- [x] `research_training_cost.py` статически проверяет original M33/M36primary source SHA и4reviewed AST function shapes. Archived code не исполняется; original packet повторно валидируется без fit/prediction. Учитывается pinned04:37candidate с5180/1060/1140rows и450epochs.
- [x] Один вызов `train_logistic_model` включает3long L2 trials(0/0.01/0.1),1short head приdefault L2=0 и1train-only standardizer fit. Это4optimizer head fits/1800epoch passes/9324000training row presentations+sigmoid evaluations. Затем3180validation selection probability evaluations плюс14760split metrics и14760diagnostic probability evaluations; всего32700вызовов probability function внеoptimizer.
- [x] Это условный подсчёт операций по exact code, если вызов завершён на сохранённых размерах. Исторический расход CPU/RAM/time/energy им не измерен; promotion/incumbent scoring/data preparation/provider/CLI work не включены. Прежний logical-fit accounting не переписан задним числом, закрытые numericIR attempts этим не переклассифицированы.
- [x] Подготовлен machine-readable review-only accounting scenario:1shared baseline+3ordinary-search+3LLM-search logical bundles. На прежних размерах это28head fits/7standardizer fits/65268000training row presentations/228900outside-optimizer probability calls. Это иллюстрация стоимости unchanged primary trainer, не executable search catalog и не разрешённый бюджет.
- [x] Draft явно перечисляет9unresolved решений: actual dataset/lineage/exposures/windows/baseline+evaluator/search+stopping/metric+useful effect/resource caps/historical overlaps/next protocol decision. Future row counts и реальные all-in costs потребуется определить отдельно. Old numeric3/3 cache-only; новых прав на fit/prediction/provider0.
- [x]15focused checks passed/0.15s; full profile2287passed/117.47s pytest/118.04s wrapper. Проверены exact operation totals, distinction of logical/head fits, bounded nonboolean counts, hostile/unreviewed source rejection безexec, immutable policy/safe CLI и запрет автоматических разрешений. Parent real audit CPU8s/AS512MiB/FS2MiB/NOFILE64/CORE0; native workers/SQL/HTTP/provider0.
- [x] M40post-transfer proof сохранён отдельно:1463protected hashes/9journals, actual worktree verify безworkers/SQL/HTTP. При M41transfer сохраняются1461old files outside2docs, main data/model/services и исходные бюджеты.
- [ ] R03/R17: approved executable protocol, реальные данные/holdout/exposure inventory/evaluator/resource bounds и явное решение о следующем numerical budget ещё нужны. Draft7calls не запускается и не переводит R17 в выполнено.19групп R02–R20 открыты.

[Статический расчёт](../.local/research-training-cost-real-20261026/cost/audit.json), [черновик accounting scenario](../config/research-primary-continuation-accounting-draft-v1.json), [verification](../.local/research-training-cost-real-20261026/verification.json).


### R05/R10/M42 — свежие metadata бесплатного backend, 26 октября 2026

- [x] В08:05:59UTC выполнены ровно1public OpenRouter catalog GET и1local Ollama tags GET, без auth/redirect/proxy/retry/generation. Каталог791569B/HTTP200 сохранён; fixed `nvidia/nemotron-3-super-120b-a12b:free` присутствует, pricing prompt/completion=0. Native `free_model_receipt` воспроизведён по сохранённым bytes/hash без нового HTTP. Это наличие бесплатной catalog entry, не гарантия available completion endpoint/качества/полного spend контроля.
- [x] Local127.0.0.1:11434/api/tags получил URLError; вывода об отсутствии всех возможных установок нет. `ollama` не найден в PATH данного host observation. Jobpilot current literal settings всё ещё https://ollama.com и nemotron-3-nano:30b; экспортированы только2неcredential поля. API key поля не извлекались и не использовались. Cloud free entitlement/decision compatibility остаются неизвестными; remote cloud generation не запрашивалась.
- [x] Pinned local tev1:0.8b-q8_0 CPU profile не изменён: memory policy3221225472B, available1258311680B — blocked. Disk free9772556288B вышеcold lower bound4419775897B; прежний disk blocker18Oct больше не актуален для lower bound, но runtime unpacked size всё ещё unknown и полного disk pass нет. Swap не засчитан вRAM. Model/runtime download/install/start0.
- [x] Probe parent8s+killpg/reap, socket3s/response1MB catalog/64KB local, CPU8s/AS512MiB/FS2MiB/NOFILE64/CORE0. Полные raw metadata/receipts, redacted configuration и capacity self-digest сохранены. Offline replay проверил прежнюю policy/source version и все9journals. Main DB/data/model/services/jobpilot settings неизменны.
- [x] Изменены только2docs и private evidence; runtime code не менялся, новый full profile не запускался. Последний профиль unchanged runtime2287passed. M41actual worktree postcheck1475hashes/9journals сохранён отдельно.
- [ ] R05/R06/R10: реальные structured-output quality/input-token/server/resource/account-spend/gold checks и operational journal bindings не закрыты. Metadata GET не создаёт нового generation/fit/numeric allowance; numeric3/3 completed-cache-only.19групп R02–R20 остаются открыты.

[Metadata verification](../.local/research-backend-refresh-real-20261026/verification.json), [fixed free route](../.local/research-backend-refresh-real-20261026/observations/catalog-receipt.json), [capacity](../.local/research-backend-refresh-real-20261026/observations/capacity.json). Official references: [OpenRouter free variants](https://openrouter.ai/docs/guides/routing/model-variants/free), [Ollama tags](https://docs.ollama.com/api/tags).


### M43 — метаданные общего OpenRouter ключа без раскрытия identity, 26 октября 2026

- [x] Один заранее ограниченный authenticated READ ONLY GET `/api/v1/key`, HTTP200/1076B, наблюдение08:11:53UTC. Использован existing jobpilot-ai key без копирования вargv/env/artifact; redirect/proxy/retry/generation0. Raw response body/label/creator/organization/budget IDs не сохранены. Есть SHA исходного body и строгая очищенная projection с Decimal monetary lexemes.
- [x] В этом срезе native usage/daily/weekly/monthly иBYOKusage=0; limit/remaining=100credits, native key_limit budget100USD/spend0/remaining100/no reset. Free daily counters used0/limit50/remaining50. Это credential-reported snapshot общей с jobpilot области, не отдельная квота CryptoForge и не утверждение нулевых расходов всех других account keys. Текущие счетчики могут меняться после среза.
- [x] `research_provider_limits.py` экспортирует только allowlisted расходы/квоты/flags/reset fields. Missing/unlimited остаютсяnull, явный native0 сохраняется0; отрицательный remaining допустим. Deprecated rate_limit игнорируется как enforcement. Structured budgets ограничены16records, credit magnitude1e12/precision24decimals, counters≤1e7, bool вместочисла/NaN/infinity/hugeexponent/unknownscope отвергаются.
- [x] Неверные native timestamp не раскрывают исходное значение в ошибке. Original capture source/normalized receipt сохранены; новая нормализация той же очищенной projection отличается толькоimplementation/self hashes. Все native values прежние; дополнительных HTTP илиcredential reads при исправлении0.
- [x]27focused checks passed/0.08s; финальный профиль2314passed/109.6s wrapper. Предыдущий профиль2312passed/110.19s доtimestamp error hardening сохранён отдельно. Replay проверяет projection/hash/обе версии receipt без повторного auth/HTTP; old9journals protected. Capture parent8s+killpg/reap/socket3s/body64KB; CPU8s/AS512MiB/FS2MiB/NOFILE64/CORE0.
- [x] M42actual worktree postcheck1488protected hashes/9journals сохранён. M43transfer сохраняет1486old files outside2docs; существующие API/common/numeric ledgers, provider limits/jobpilot settings/main DB/model/services не изменены. Numeric lifetime3/3 completed-cache-only.
- [ ] Full account-wide/historical expense reconciliation, attribution CryptoForge vsjobpilot, races/atomic reservation и explicit operational bindings остаются R06. Native paid-credit limit100 не означает free-only server enforcement; free-only model/routing checks вadvisor сохраняются. Metadata receipt не даёт нового разрешения на generation/fit/prediction. R05quality/native input-token proof и новый R17protocol/budget всё ещё открыты.19групп R02–R20 открыты.

[Очищенный срез](../.local/research-provider-limits-real-20261026/captured/normalized-revalidated.json), [capture receipt](../.local/research-provider-limits-real-20261026/captured/receipt.json), [verification](../.local/research-provider-limits-real-20261026/verification.json). Official contract: [OpenRouter current-key limits](https://openrouter.ai/docs/api_reference/limits).


### M44 — native reader и полный trainer lookback по сохранённым SQL строкам, 26 октября 2026

- [x] `research_cohort_reader_audit.py`/worker вызывают actual main `SupabaseMarketReader.read_candles` и `_load_examples`, fixed20pairs/limit500/120features/h3/target0.003/freshness900s/minimumcoverage0.8. URL transport перехвачен строго на synthetic origin; auth synthetic. JSON-number wire построен из original saved SQL numeric lexemes: это **не original HTTP body** и не новая проверка deployed service. Actual HTTP/SQL/credentials/provider0.
- [x] Native float→Decimal и отдельный exact Decimal parser читают те же projected bytes.50000scalar comparisons/0mismatch, все6786native examples совпали с exact parser.18pairs приняты(coverage0.9);BR/ONDO исключены `stale closed training source`. Это результат `_load_examples`, без вызова `run`/fit/promotion.
- [x] Для original13predecision windows полный native loader дал те же91feature components и13late label windows;0mismatch/0missing comparisons. Пять дополнительно доступных в late cache пар не восстанавливают отсутствовавшие ранние features. Original captured label qualification0 остаётся неизменной.
- [x]15focused tests passed/1.17s; full2329passed/111.75s pytest/112.3s wrapper. Synthetic high-precision volume доказывает float transport loss; gap до выбранного120bar window исключает пару в полном500bar loader. Проверены scope/flags/counts/mismatch/offline replay/timeout/interrupt. Fit/standardizer/predict функции в worker закрыты.
- [x] Worker CPU15s/AS512MiB/FS2MiB/NOFILE64/CORE0/parent25s+killpg/reap. Whole real prepare+verify9.478s; parent CPU20s/AS512MiB/FS16MiB. Первый startup отказал из-за inherited parent CPU hard limit12<child15; initial runner/error сохранены, данных/HTTP повторно не получали. Предыдущий focused import defect исправлен до реального replay.
- [x] M43postcheck1504protected hashes/9journals сохранён. При переносе1502old files outside2docs и original9journals/main source/data/model/services неизменны. Numeric3/3 completed-cache-only; новых numerical allowances0.
- [ ] Original live REST wire/service configuration equivalence, approved actual dataset/target/exposures и controlled study остаются R02/R03/R07/R18. Technical replay не является training admission.19групп R02–R20 открыты.

[Reader audit](../.local/research-cohort-reader-real-20261026/reader/audit.json), [observations](../.local/research-cohort-reader-real-20261026/observations.json), [verification](../.local/research-cohort-reader-real-20261026/verification.json).


### R02/R18/M45 — reviewable точность reader без изменения production, 26 октября 2026

- [x] Подготовлен [ручной one-line patch](RESEARCH_NATIVE_READER_DECIMAL_V1.patch) к exact current main SHA `b3a85306…`: `SupabaseMarketReader._get` использует `json.loads(response.read(), parse_float=Decimal)`. Изменение только этого keyword подтверждено AST. Это инженерный patch proposal, не genuine LLM patch/provenance R16.
- [x] `git apply --check` к текущему dirty main прошёл; main/isolated runtime source не менялись. Before/proposed source bytes иSHA сохранены, proposed module не импортировался/не исполнялся, bytecode не генерировался. Ordinary stdlib JSON проверяет parser primitive.
- [x]50000saved values совпадают при обоих parser; synthetic high-precision volume сохраняется точно вместо legacy rounding. На реальном срезе ошибки цен не обнаружено; улучшение ML/economics не заявлено. HTTP/SQL/model fit/prediction/provider0; runtime tests не повторялись, unchanged profile2329passed.
- [x] [Обзор и integration checklist](RESEARCH_NATIVE_READER_DECIMAL_PATCH.md) содержит source pin, ограничения и проверки перед merge. M44postcheck1518protected hashes/9journals сохранён. Transfer сохраняет1516old files outside2docs; native limits иmain services/model/data unchanged.
- [ ] Применение/actual REST requalification/new source fingerprints/совместимость fitted artifacts требуют отдельной интеграции. Numeric3/3 cache-only; R02/R03/R16/R17/R18 остаются открыты.19групп R02–R20 открыты.

[Patch verification](../.local/research-reader-decimal-patch-final-20261026/verification.json).

M45 final artifact check: blank context-line whitespace normalized after cached diff check flagged the initial representation. Initial patch/receipt retained; final default git apply dry-run and cached diff check required. Runtime/main unchanged.


### M46 — сверка текущих чеклистов и post-transfer evidence, 26 октября 2026

- [x] Закрыты3stale companion M38boxes:обаcapture и scoped audit выполнены. Полная пригодность20pair dataset остаётся отдельным открытым требованием; поздние данные не подменяют ранние.
- [x] Удалена устаревшая фраза об ожидании M31slots из2документов; требования R06/R18/R19 сохранены открытыми. Current root notes R02/R03/R04/R05/R06/R10/R16/R17/R18 обновлены без удаления исходных acceptance criteria.
- [x] M35both v2 accounting modes повторно проверены изactual worktree с запрещённым child creation; M44/M41/M43также replayed offline. Старые receipts не переписаны, pending вoriginal pre-transfer evidence отделён отcurrent post-transfer proof.
- [x] Машинная карта хранит каждый прежний open checkbox/строку/хеш и объясняет изменения. Все19root groups R02–R20 остаются открыты; original failed M21 не превращён в success и не возобновлён. Main/runtime/data/model/budgets неизменны; latest unchanged full profile2329passed.

[Карта сверки](../.local/research-checklist-reconcile-real-20261026/checklist-map.json), [current offline proof](../.local/research-checklist-reconcile-real-20261026/offline-verification.json).


### R02/R03/R06/R10/R17/M47 — read-only evidence readiness, 26 октября 2026

- [x] `research_readiness.py` объединяет verified original M44source/M42free catalog/M43sanitized key limits/M46state и hashes9journals. Проверяет prototype3/3, approved protocol/integration,4original missing operational bindings, evidence clocks и semantic-only backend requirement. Shared provider free counters не становятся project allowance.
- [x] Inspect иverify только создают/проверяют evidence report. Они не заменяют phase/trainer admission и не запускают операции: `operational_actions_enabled=false` при любом результате, включая synthetic complete/fresh facts. Exit0 inspect означает записанный report, не разрешение запуска. Manual Decimal patch не добавлен как новый обязательный MVP gate; semantic backend требуется только semantic branch.
- [x] Для текущего operational context введено отдельное advisory freshness окно900s. Оно не отменяет sealed historical evidence и не утверждает, что frozen historical dataset обязан быть новым; historical protocol нужно проверять отдельно. Future observations/неверные clocks отказывают без вывода исходного значения.
- [x] Actual inspect asof 2026-10-26T08:51:44.947696+00:00:generative8blocking reasons, semantic9. Prototype exhausted/protocol+integration missing/4bindings missing/retained source+catalog+spend observations старше advisory900s/early captured label horizons0; semantic дополнительноunqualified backend. Source/keys не обновлялись для обхода отказа.
- [x]12focused checks passed/0.18s; full2341passed/138.0s wrapper. Проверены boundary0/900/901s/future clocks, nullable quota, строгие budget/boolean types, semantic-only rule и отсутствие operational permission даже при synthetic readiness. Real prepare+verify обоих modes с запрещённым child creation, parentCPU12s/AS512MiB/FS2MiB/NOFILE64/CORE0; workers/services/HTTP/SQL/credential reads/model fits/predictions0.
- [x] M46postcheck1535protected hashes/9journals сохранён. Transfer сохраняет1533old files outside2docs; main code/data/model/services и все прежние caps/journals не меняются этим направлением. Numeric3/3 completed-cache-only.
- [ ] Operational integration после approved data/protocol иявное новое numerical decision остаются R02/R03/R07/R17. Advisory report не разрешает работу и не закрывает statistical/provider/backend gates.19root groups R02–R20 остаются открыты.

[Readiness facts](../.local/research-readiness-real-20261026/observations.json), [verification](../.local/research-readiness-real-20261026/verification.json).


### R02/R04/R18/M48 — настоящий HTTP wire локальной базы для20пар, 26 октября2026

- [x] После2370passing tests выполнен один fixed readonly native reader capture:20GET×500rows, без retry/SQL/provider generation. Original response bytes/attempt-before-request/receipts сохранены приватно; auth values не сохранялись. Источник — local PostgREST127.0.0.1:54321. Это отдельный текущий diagnostic source, не backfill M38/M40 и не approved training study.
- [x] На captured_at 2026-10-26T12:08:39.379786+00:00 сохранены10000rows/50000numeric scalars:legacy native parser иexact Decimal parser совпали, scalar mismatches0. Обе версии native `_load_examples` дали4901identical examples. Патч M45 не применялся; отсутствие потерь на этих значениях не отменяет synthetic precision counterexample.
- [x] Для latest eligible example каждой из13accepted pairs независимый Fraction reference подтвердил91feature components/13label windows,0mismatch. Это другие окна и состав пар, чем13original M38windows; ранняя неполнота иoriginal0captured label horizons не переписаны.
- [x] Зафиксирован отрицательный data-quality результат:accepted13/20=65%<required80%. Native loader исключилAERO/BR/CAP/MON/PEPE/SUI/WLD какstale closed source. `status=native_HTTP_values_compatible` относится только кvalue parity; training admission=false,minimum coverage gate не пройден. Повторный запрос для улучшения результата не выполнялся.
- [x] Offline native replay повторилровнотеже20responses с0HTTP/0key reads. Default verify после этого проверяет saved bodies/receipts/independent values без worker. Capture endpoints запрашивались по20отдельным HTTP transactions:single database snapshot/history first-seen/revisions/all production consumers не аттестованы.
- [x]29new focused tests/129.34s full wrapper:strict JSON/duplicate fields/identity/numeric domains/clocks, native precision counterexample, no-restart capture, timeout/interrupt cleanup иtampered body refusal. Real capture+replay 6.802202s parent wall;children CPU user5.447141s/system0.08692s. Это не whole-server/IO/memory consumption. Model fits/predictions/provider generations/database writes0; numeric3/3cache-only/9journals intact.
- [ ] R02остаётся открытым:approved full dataset/exposure inventory/history protocol иproduction integration. Для current source недостаточно покрытия; M48не закрываетR03/R07/R08/R09/R17/R18 ине разрешает новые numerical actions.

[HTTP capture audit](../.local/research-cohort-http-real-20261026/pack/audit.json), [exposure manifest](../.local/research-cohort-http-real-20261026/exposures.json), [verification](../.local/research-cohort-http-real-20261026/verification.json).


### R02/R04/M49 — независимая диагностика source failures перед model hypotheses, 26 октября2026

- [x] `research_source_diagnostics.py` читает verified M48original HTTP bytes, не запрашивая свежие данные. Для всех20пар независимо определяет mutually exclusive eligibility:9980known_closed/9ingested_before_close/11not_closed_at_cutoff/0ingested_after_cutoff. Числа относятся кsaved12:08:39UTC snapshot, не ксостоянию на момент verify.
- [x] Independently reconstructed native refusal order, latest_known_closed clocks, accepted/excluded pair sets и4901complete examples совпали сactual loader. Все7refusals —stale closed source; gaps/insufficient history проверяются отдельно. Venue outage/collector fault поодномуcache не приписываются.
- [x] Exact coverage13/20<4/5 даёт typed route`review_source_data`, reason`minimum_pair_coverage_not_met`, eligible parameter proposals=[] иprovider/training authorization=false. Даже synthetic sufficient-source route`review_research_protocol` не выдаёт новых прав; native`status=completed` означает завершение загрузки, не пройденный coverage gate.
- [x] Data source failure отделён отnumeric compatibility; model quality/strategy execution/trade accounting остаются`not_evaluated`. Исходныйcandidate04:37иM38/M40windows не подменяются current source; historical availability/current-at-verify/LLM usefulness не заявлены. Hyperparameter tuning не объявлен исправлением stale source.
- [x]23new tests:inclusive900s/±1microsecond, exact80%coverage, forming/preclose/future-ingest boundaries, missing/gapped/short histories иactual native refusal precedence. Full2393passed/136.18s wrapper. Real prepare+verify сзапрещённымPopen/1.640474s, HTTP/SQL/key reads/provider/model actions0;1630prior hashes/9journals intact/numeric3/3cache-only.
- [ ] Advisor/coordinator/main pipeline ещё не подключены кэтомуdiagnostic route; это read-only report contract, не новый admission engine. Approved source/history/exposure/protocol, economics иполнаяerror taxonomy остаютсяR02/R03/R04/R07. Порог80%иcohort не уменьшались подрезультат13пар.

[Source diagnostics](../.local/research-source-diagnostics-real-20261026/report/diagnostics.json), [verification](../.local/research-source-diagnostics-real-20261026/verification.json).


### R05/R06/M50 — очищенные exchange records иявный legacy gap, 26 октября2026

- [x] `llm_exchange_audit.py` формирует full cleaned JSON request/response/validation/provenance packs. Request восстанавливается толькоизтекущего pinned prompt factory дляпереданногоdiagnostic report; это не утверждение, чтосохранён original historical HTTP request. Raw response bytes/HTTP headers/credentials не записываются; original response SHA/bytecount сохраняются.
- [x] Bounded cleaning покрывает explicit secret values, ASCII JSON Unicode escapes, credential patterns/URL userinfo/email иsensitive fields, втомчислевembedded JSON text. Opaque generation/request IDs удаляются; отражённыйключ приводиткprivacy rejection. Invalid/non-JSON/too-deep/oversized-cleaned response остаётсяmetadata-only. Exact Decimal response values записываютсястроками; privacy произвольныхencodings/всехPIIне аттестована.
- [x] Validator фиксирует model/finish/one-choice/assistant/no-tools/no-refusal иexisting proposal/evidence/catalog contract. Успех`proposal_schema_valid_only` не подтверждаетистинуилиполезность иничегоне разрешает. Nullable native usage/cost не заменяются0; валидные usage/cost сохраняются дажеприinvalid proposal. Nonzero reported costнаfree route отклоняется ссохранённымзначением, непереименовываетсяв0.
- [x]39focused tests/0.34s; full2432passed/134.93s wrapper. Шесть явноsynthetic packages:OpenRouter/Ollama schema-only, Unicode-secret rejection, reported-cost0.02rejection, tools rejection, malformed outer JSON. Это0live provider captures; real backend readiness/quality/free entitlement этимне доказаны. Провереныprivate0700/0600, tamper/symlink/no-overwrite иno worker/network semantics.
- [x] Existing original API SQLite прочитанreadonly:1row хранитnormalized advice иinput identities, ноfull original response envelope/exactHTTPpayload вегоnative fields отсутствуют. Legacy receipt не объявлен full exchange; old wire не реконструирован. Scope:1readonly SQLite snapshot/6explicit statements,0newPostgreSQL/HTTP/provider/keyreads/modelactions. Original ambiguous zero-SQL field уточнён additive scope-clarification безпереписыванияinitial observations.
- [x] Раннийfull test run остановленпослеобнаруженногоfocused false positive дляlegal evidence IDs;1223passed/47.60s сохраненыкакinterrupted, некакполныйуспех. Исправленныйfinal профиль2432passed. M49postcheck1641hashes/9journals сохранён; numeric3/3cache-only, common/API budgets/mainruntime unchanged.
- [x] Отдельный opt-in fixed worker/API integration добавлен M55: очищенный exchange сохраняется при прежних reservation/failure/cache/deadline/input-limit rules, без изменения старых worker/advisor/coordinator. Это проверено на synthetic loopback; default CLI/main не переключены. Real provider structured/patch quality, native input-token proof, account-side spending и R05/R06/R16 остаются открытыми.

[Offline fixture results](../.local/research-exchange-audit-real-20261026/observations.json), [legacy gap](../.local/research-exchange-audit-real-20261026/legacy-audit-gap.json), [verification](../.local/research-exchange-audit-real-20261026/verification.json).


### R02/R18/M51 — зарегистрирован prospective source-only срез20пар, 26 октября2026

- [x] Доfeature anchor13:00UTC зафиксированы20исходныхprimary pairs,120feature bars/3label bars,decision13:02 иlabel information end13:17. Public GET end=anchor-1ms исключает forming bar поцелевомуanchor. Current-observer first-seen не переименован вhistorical publisher first-seen; clocks independently unattested.
- [x] Дваfixed slots13:00:10и13:15:10UTC,20requests каждый/90s completion deadline/local3s per request deadline/no retry. Максимум40public market GET, прежние18не списаныповторно/не обнулены:cumulative upper bound58. Ключи/PG/model/provider generation не используются; prototype numeric3/3cache-only. New source namespace — только новые наблюдения,0new ML allowance.
- [x] Exact collector прошёл2synthetic dry-runs:80simulatedGET/0network, success иone failed request/no retry. Frozen code/plan/hashes сохранены; process armed доanchor; обаoriginal slots иscoped value audit завершеныM52. Main DB/collector/trading model не меняются.
- [x] Original feature capture завершён:20qualified pair responses/2400rows,first-seen≤decision; evidenceM52.
- [x] Original label capture завершён:20qualified pair responses/60rows,0retry; evidenceM52.
- [x] Independent/native values провереныM52:140feature components/20label windows,0mismatch. Dataset/protocol approval не выдано.

[Registered plan](../.local/research-primary-prospective-source-registered-20261026/prospective-plan.json), [armed progress](../.local/research-primary-prospective-source-registered-20261026/progress.json), [dry-run proof](../.local/research-primary-prospective-source-registered-20261026/dry-run-verification.json).


### R02/R18/M52 — завершён original prospective20pair source/value срез, 26 октября2026

- [x] Original M51feature13:00:10иlabel13:15:10UTC slots завершены:40public GET/0retry,20successful qualified pair responses вкаждом. Early2400feature rows былиobserved≤decision13:02;60label rows полученыпослеlabel-close13:15 идоinformation-end13:17. Сохраненыoriginal bodies/attempt-before-request/receipts/slot summaries иclient first-seen. Прежние18public market attempts сохраняются:cumulative58; этоsource collection, неnewnumeric allowance.
- [x] Fixed postprocessor/hash/comparison rule frozen13:14:57.571758UTC доlabel anchor13:15. Наoriginal available rows independent Fraction/Decimal reference иactual mainfeature extractor/runtime/build_examples совпали:20feature windows/140components/20label windows,0mismatch;2460source rows. NoReader исключил implicit source reads. Actual production REST reader наэтихvenue responses не запускался; они не объявлены PostgreSQL snapshots.
- [x] Real native worker1/CPU user0.17087s/system0.022982s;parent prepare+verify0.964707s. Это не whole-server consumption. Postprocessor HTTP/SQL/key reads/model fit/prediction/provider generations0. Old M31/M38/M40missing/late histories не исправлялись; M48local-cache65% не заменены этимотдельнымvenue source.
- [x] Original operator-stage source сохранён; exact raw copies дополнены отдельным archived-source binding. Native packet/output идентичны, second native run0, этиже20samples не считаются40. Actual worktree post-transfer verify проверил оба bindings без нового worker: M52/M53 postcheck сохранил1852protected hashes/9journals; итог M54 подтверждён. Original mainruntime/source hashes иregistered source scope по-прежнемуобязательны; cross-environment qualification не заявлена.
- [x]17source tests+11M53graph tests=28new;full2460passed/163.61s wrapper. Реальные20срезов —одинtime anchor сcross-market dependence. All labels now exposed development; approved chronological train/validation/final-test/forward manifest отсутствует. Clock sync/publisher historical first-seen/full revisions не аттестованы; final-test28–29/forward30–31Oct не читались.
- [ ] Approved multi-time dataset/history/exposure protocol иlocal DB/trainer/evaluator integration остаютсяR02/R03/R07/R18. Этот20pair technical pass не даёт новогоnumerical budget иничегоне разрешаетторговать; numeric3/3completed-cache-only/9original journals intact.

[Archived source values](../.local/research-cohort-and-fit-graph-real-20261026/archived-source-values/audit.json), [exposures](../.local/research-cohort-and-fit-graph-real-20261026/exposures.json), [verification](../.local/research-cohort-and-fit-graph-real-20261026/verification.json).

### R03/R04/R06/R08/M53 — fit reuse graph ипроверка полезности текущего catalog, 26 октября2026

- [x] `research_fit_graph.py` проверяетliteral hashes5existing source files иAST optimizer/prediction call shapes. Existing isolated study допускаетbaseline+single-parameter changes:7logical configurations,4distinctL2fit dependencies. Threshold не входитвoptimizer/predict inputs; whole artifacts нельзяпереиспользоватьбезновойthreshold metadata. Main primary multi-head trainer M41 автоматическине подключён.
- [x] Graph связываетdataset/implementation-source/target/features/epochs/learning-rate/train/validation context сfit/prediction/evaluation keys. Approved causal source manifests иapproved protocol identity ещё не входятвэтотreview context; operational cache integration должнаихпроверятьидобавить. Усемипороговых/parameter evaluations сохраняютсяseparate identities иbudget charges; схема7logical evaluations остаётся7. Это неcache migration/неrefund/неbypass existing lifetime caps. Execution command отсутствует; oldworker/coordinator/journal fingerprints unchanged.
- [x] Дляpreviously exposed development dataset5615ca7c…/5180train+1060validation статический fresh-run сценарий:long-head fits7→4,standardizer7→1, optimizer row presentations1813000→1036000, probability evaluations43680→24960. Диагностические/configuration evaluations остаются7. Actual fits/predictions/cache reuse0; CPU/quality savings не измерены. Dataset отличаетсяотM52one-anchor source.
- [x] Current isolated study primary metric`validation_brier_score` не меняетсяотthreshold приодних probabilities;threshold-only3changes расходуютcomparison budget безновогоprimaryBrier outcome. Вunit test precision/recall изменились, Brier/log-loss сохранились. ДляfutureBrier-only fitsearch нуженordinary exhaustive control:baseline+3otherL2values покрываютвесьexisting fitcatalog. Economic/decision objective можетзависетьотпорога; егоэффектэтимне проверен. ПользаLLM/результатouter windowне измерены.
- [x]11new graph tests проверилиfit/evaluation identity separation, data/epochs/source invalidation, fixed scope иforbidden fit/prediction/Popen/ResearchAttempts. Real inspect+verify наretained data сэтимизапретами/0.695856s;0model/provider/budget actions. Prototype numeric3/3 не менялся.
- [ ] Approved executor/cache integration, exact physical+logical accounting иordinary exhaustive comparator требуютновогоprotocol/decisionR03/R06/R07/R08/R17. Graph —готовыйreviewable dependency plan, неразрешениеисполнения илидоказаннаяприбыль.

[Fit reuse graph](../.local/research-cohort-and-fit-graph-real-20261026/fit-graph/graph/graph.json), [graph observations](../.local/research-cohort-and-fit-graph-real-20261026/fit-graph/observations.json).


### M54 — финальная сверка scope/checklists послеM48–M53, 26 октября2026

- [x] M51three pending capture/value boxes закрытыпоM52evidenceвобоихдокументах. Original preregistration progress остаётсяimmutable historical snapshot доcapture; currentstate описанM52.19root groupsR02–R20 иoriginal failedM21 не отмеченывыполненными.
- [x] Latestfull2460passed;source20pairs/140features/20labels означаетодинtechnical anchor, безapproved chronological dataset илиLLM benefit. M48local-cache65%остаётсяотдельнымнепройденнымсрезом.40newpublicGET+18prior=58; no retries/refunds/old-window repair.
- [x] УточнёнM53cache scope:source вегоcontext —implementation hashes. Approved raw observation/revision/source manifest иapproved protocol identity ещё нужно добавить/проверитьприоперационнойинтеграции. Graph не читаети не переиспользуетстарыйfit cache; current phase/ledger не используютегоkeys. Existing isolated worker/native primary multi-head trainer не оптимизированыавтоматически.
- [x] M50full cleaned exchange format проверенoffline;1native legacy row не содержитfull original wire. Live capture/coordinator integration/native token proof/provider quality/shared account billing остаютсяоткрыты. Actual model fits/predictions/provider generations0;numeric3/3cache-only/9journals preserved. Runtime tests послеdocs-only сверки не повторялись.

[Current state](../.local/research-final-checklists-real-20261026/current-state.json), [checklist map](../.local/research-final-checklists-real-20261026/checklist-map.json).


### R05/R06/M55 — очищенный exchange в fixed provider-worker и прежних budgets, 27 октября 2026

- [x] Новый `llm_audited_provider.py` добавляет opt-in API для existing coordinator/v5 phase: тот же common budget, bound API journal, effective request key, daily quota и failure charging. Старые sealed worker/advisor/coordinator/phase sources не менялись; default CLI/main не переключены, migration/reset/refund отсутствуют.
- [x] Fixed child отправляет exact existing factory payload, сохраняет actual transport binding и M50cleaned exchange до принятия proposal. HTTP non-200/tools/invalid JSON/usage/privacy отказы сохраняются; known native usage/cost остаются доступны, null не заменяется нулём. Raw bodies/headers/credentials не записываются; non-JSON metadata-only. Это не upstream/provider/account billing attestation.
- [x] Новые записи привязаны к original API path digest/request key/report/payload/body/manifest/source hashes. Parent проверяет capture перед возвратом и при cache reuse. Missing/changed original capture отказывается без recapture; legacy cache явно сообщает отсутствие original wire. Путь audit root не создаёт новый effective API request.
- [x] Existing local wall/cancel/kill/reap сохранены; child CPU5s/AS256MiB/file1.3MB, body1MB/output64KB/verified attempt2MB. Timeout/transport failure/process death сохраняют unknown completion и charged attempt; server cancellation не заявлена. Global model-server/disk/account costs этим не покрыты.
- [x] Strict native input-token requirement включён по умолчанию: new completion отказывается до reservations/keys/HTTP, поскольку native proof всё ещё отсутствует. Tests отключают его только для synthetic localhost. Fixed free OpenRouter identity/zero-price catalog/no redirects/no retries/no paid fallback сохранены; real provider qualification не выполнена.
- [x]24new focused tests/8.03s; full2484passed/209.79s. Проверены v5history preservation, caps, cache, reflected-secret cleaning, failed usage, timeout/drip/cancel/reap, redirect/start failure, tamper/symlink/privacy. Первоначальный focused23pass/1failure относился к неверному имени snapshot поля в тесте; исправлен.
- [x] Сохранены3synthetic loopback cases: accepted/tools/badJSON, по1HTTPfixture и1common reservation; repeated success cache без HTTP. Parent0.982061s. Это0external provider generations/real key reads/operational model fits/predictions и0original journal mutations. Исторический numeric3/3cache-only остаётся.
- [x] Отдельный existing-only CLI добавленM56; default phase/main не переключены. Реальные backend quality/token proof/account costs/approved data/protocol по-прежнемуR02/R03/R05/R06/R07/R16/R17;19rootgroupsopen.

[Usage and scope](LLM_AUDITED_PROVIDER.md), [synthetic observations](../.local/research-audited-provider-real-20261027/synthetic-artifacts/observations.json), [full profile](../.local/research-audited-provider-real-20261027/profile-result.json).


### R05/R06/M56 — existing-only audited CLI для прежнего v5, 27 октября2026

- [x] Новый `llm_existing_advisor_cli.py` открываеттолько existing initialized API journal сmode=rw/owner0600, exact native tables/persisted policy иunchanged file identity приopen. Нет CREATE TABLE/автоматической migration/new quota. Unlink междуprecheck/native propose не создаётreplacement DB; failed common reservation остаётсяcharged.
- [x] `proposal` CLI используетbound existing v5 common иM55fixed audited worker. Strict native input-token requirement всегдаtrue, CLI bypass flag отсутствует. Current implementation отказываетnew completion доkeys/HTTP/reservations, покаnative proof отсутствует. Established completed cache допустим, legacy full-wire gap остаётсяявным. Это opt-in CLI, main/default phase handler не переключены.
- [x] `verify` проверяетretained actual transport packs offline; exclusive0600receipt не можетсовпастьсsource/journal/audit root. Нельзяперезаписатьoriginal receipt/capture. Ошибкисохраняютсякакstatic safe codes, безraw body/key/path secrets.
- [x]16focused tests/6.93s; full2500passed/203.58s. Existing-only empty/missing/wrong-policy/schema/symlink/public/unlink races, failure retention, strict admission, cache иexclusive offline verify покрыты. Runtime sources M55/старогоcoordinator/phase не менялись.
- [x] Наoriginal established synthetic-accounting paths командаправильноотказалаиз-заmissing bound proposal.sqlite:4missing bindings не созданы,9original journals неизменны, parent0.018448s/0worker/HTTP/keys/provider/model actions. Это неapproved operational study. Initial invalid output-inside-audit-root probe былкорректноотклонёндоreceipt; исправленытолькоаргументыharness.
- [ ] Actual adoption/approved operational bindings/protocol/native input-token proof/free backend quality/account-wide spending остаютсяR02/R03/R05/R06/R07/R10/R17. Existing CLI не инициируетвосстановлениепрошлойисторииилиновуюnumeric phase; numeric3/3cache-only,19root groupsopen.

[CLI usage](LLM_AUDITED_PROVIDER.md#existing-only-cli-m56), [original path refusal](../.local/research-existing-advisor-cli-real-20261027/observations.json), [full profile](../.local/research-existing-advisor-cli-real-20261027/profile-result.json).


### R03/R06/R07/M57 — ephemeral fit reuse с точным численным совпадением, 27 октября2026

- [x] Новый `training_fit_reuse.py` реализуетчисленныйprimitive дляexisting isolated long-head search:shared train-only standardizer,4distinctL2fits вместо7, probabilities reuse тольковнутриодноговызова. Все7logicalconfig evaluations/threshold diagnostics/artifact metadata остаютсяотдельными; whole artifacts не переиспользуютсякакдругойthreshold. Main multi-head trainer/default worker не менялись.
- [x] Наsynthetic20train+20validation fixtures веса/bias/means/stds/exact artifact bytes/checksum/reports/selected observations побитносовпали с7independent original evaluations. Инструментированныеmodel-call counters подтвердилиstandardizer7→1,head fits7→4,probability calls280→160,row presentations700→400;14diagnosticreports сохраняются. Real-data speedup/LLM utility не измерялись.
- [x] Всеlogical admission callbacks вызываютсядопервогоfit. Ошибканаadmission4 не запускаетчисленныеоперации; первые3charges не возвращаются. Ошибкаoptimizer оставляет7alreadyadmitted evaluations. Callback seam —неsecurity/admission authority и неутверждениеactual ledger charges; fixed operational budget adapter ещё нужен. CLI/journal writes/subprocess/persistentcache отсутствуют.
- [x] Fit/prediction/evaluation keys включаютdata/protocol/implementation/target/features/epochs/learningrate иmandatoryrawsource/revisions/exposure/executionmanifest digests. Это declared exact bindings, неverification/approvaloriginal manifests. Outer result bindings/batch digest сохраняютконтекстдажеприодинаковомlegacy artifact. Любойcontextchange инвалидируетreuse; caller mutations/shared result mutations изолированы.
- [x]25new focused tests/1.11s;full2525passed/138.85s. Провереныgolden exact output, actual calls/order, budget refusal/failure, invalid/cross-parameter/duplicateconfigs, input/source invalidation, no cross-callcache, offline plan иseparate metadata. Сохранёнsynthetic equivalence pack; фактическоеобучениенаoperational data/provider requests/newallowance0. Numeric3/3cache-only/9originaljournals intact.
- [x] Fixed worker с process resource limits реализован отдельно в M62; M57 сам остаётся pure primitive.
- [x] Существующие common+inner budgets и fit-reuse worker связаны на synthetic fixtures в M63; public entry пока cache-only.
- [ ] Verified original manifests/approved dataset+protocol, operational admission adapter иactual trainer/evaluator integration остаютсяR02/R03/R06/R07/R08/R17/R18/R19. Этотprimitive неактивируетновыйstudy илиproductionoptimization;19rootgroupsopen.

[Primitive and constraints](TRAINING_FIT_REUSE.md), [synthetic operation evidence](../.local/research-fit-reuse-real-20261027/observations.json), [full profile](../.local/research-fit-reuse-real-20261027/profile-result.json).


### R06/M58 — readonly usage сверка успешных и отклонённых exchange, 27 октября2026

- [x] Новый `research_exchange_usage.py` читаеттолькоexplicit quiescent owner0600 API journals сmode=ro/immutable/query_only,проверяетnative schema/policy/request and completed payload hashes. ActiveWAL/SHM/journal/symlink/missing/changed files отказываются. Native counters берутсяизsaved normalized cache илиbound cleaned transport response; original journals иcommondebits не меняются.
- [x] Включеныusage/cost rejected completions. Каждыйcapture привязанкoriginal APIpath digest/requestkey/report/provider/model иcompletedcache capture/manifest reference. Копииодногоattempt учитываютсяодинраз; conflicting copies/чужойjournal path/normalized-vs-wire mismatch отказываются. Legacy completed cache нельзяповыситьдоoriginal wire безроднойссылки.
- [x] Unknown token/cost fields остаютсяnull сseparate unknown counters; provider-reported credits не названыUSDinvoice иcatalogzero pricing не подменяетcharge. Per-journal subtotals остаютсяраздельными, cross-journal/account/jobpilot global totals=null. Модели/diagnostics/rationale не копируютсяraw вaccountingreport; model identity толькоSHA.
- [x] Original standaloneAPI содержит1completed payload:prompt3165/completion908/total4073; counters повторнопроверенывnative stored payload, ноoriginal response captures0 иreported chargeunknown1. Это неaccount invoice/native wire revalidation. Отдельные3syntheticM55journals показываютknown rejected usage иdedup однойкопии; среальным4073не суммируются.
- [x]24new focused tests/1.58s;full2549passed/139.93s. SQLiteauthorizer запретилDDL/DML иtrace подтвердил5explicitreadonly statements/snapshot. Initial/new hardened reports сохраненыотдельно:8readonly snapshots/40explicit statements доtransfer;0PostgreSQL/HTTP/keys/workers/provider/model/debit actions,9original journals unchanged. Test harness name collision исправлен; runtime failure отсутствовал.
- [ ] Common historical debit/overlap reconciliation, all-jobpilot/account-side billing, original operational bindings, server resources иnew approved protocol/budget остаютсяR06/R17/R19. Accounting report ничегоавтоматическине применяет, неrefund и неcapincrease;numeric3/3cache-only/19rootgroupsopen.

[Usage reconciliation](RESEARCH_EXCHANGE_USAGE.md), [current observations](../.local/research-exchange-usage-real-20261027/revalidated/observations.json), [full profile](../.local/research-exchange-usage-real-20261027/profile-result.json).


### R01/R03/M59 — свежий local registry snapshot, 27 октября2026

- [x] Прежнийfixed inventory/verifier повторнопрочиталlocal PostgreSQL:одинREAD ONLY/REPEATABLE READ snapshot,2bounded event queries, non-superuserauthenticator/service_role; model.active/model.candidate максимум2строкинатип. Credentials/URI/environment не копируютсявreport. Registry/source/service не менялись.
- [x] Срез10:45:54UTC:latestcandidate27Oct10:44:34,artifact08b49385…/versionpure-python-logistic-candle-v1-20261027-429c2912f8,declaredclosed_only/bounded120/5m/horizon3;native registryavailable/checksum/vectororder pass. Candidate age≈80s,event trainingage≈99s наэтотсрез; этоbackground model, неfit данногонаправления.
- [x] Active всёещё7Oct02:59:38,c4a7f4d0…/legacy_asof_snapshot,старше36h;freshactive unavailable/training-runtime parityunproven. Executor unitloaded/inactive/dead,MLgate0.5/36h,MainPID0. Candidate неявляетсяautomaticentryfallback и неactivated. Этистатусыотносятсяк10:45срезу, неко всемпоследующимчасам.
- [x]10main source hashes/8reviewedAST shapes сохранились;dirtymainHEAD8da4cb17… не менялся. Fixed native replay проверилregistrymetadata безprediction/fit/URIload/deployment. Новогоsource repin,modelpromotion,HTTP/LLM/databasewrite/service restart0. Последнийruntimeprofile2549passed(M58);unchangedcode/docs-only этапнеперезапускалполныйпрофиль.
- [ ] Approved incumbent/baseline, actual input-window/productionparity иcontrolledprotocol остаютсяR02/R03/R07/R09/R17. Freshcandidate не даётновыхresearchattempts;numeric3/3cache-only,19rootgroupsopen.

[Registry snapshot](../.local/research-registry-refresh-real-20261027/inventory/inventory.json), [refresh observations](../.local/research-registry-refresh-real-20261027/observations.json).


### R03/R18/M60 — reviewable native dot CPU optimization без изменения main, 27 октября2026

- [x] Подготовленручнойpatch `sum(generator)`→`sum(map(operator.mul,...))` с1standard-library import дляexact native model_training SHA9afb8aab…. Умножения/порядок/builtin sum/shape/finite guards сохранены; модель/weights/target/budget/runtime не изменены. `git apply --check` прошёлвmain иisolated worktree;apply0. Это неgenuineLLM patchR16.
- [x]15tests:2000deterministic adversarial vectors плюс12boundary/type/error cases;finite outputs побитносравненыпоbinary64hex/type сactual native dot. Нет model fit/probability/provider calls; этоscalar arithmetic unit verification, неbudgetedcandidate experiment.
- [x]2syntheticCPU measurements,7alternating rounds×20000calls/variant:proposed/native medianCPU ratios0.54765/0.54820,примерно45%меньшеCPUнаодномfixed7-element dot fixture. Whole training/inference/bot speedup не измерены. Timingassertionsотсутствуют;numbers не называютсяstrategic/financialbenefit.
- [x] Initial context3benchmark/review/full2564profile сохранены. Длячистогоstaged whitespace check patchперегенерированс1linecontext;proposedsourcebytes теже,defaultgitapplycheckпрошёл. Final15focused/0.31s иfull2564passed/138.73s. Originalmodelsource/9journals/budgets неизменны,numeric3/3cache-only.
- [ ] Review/coordinated adoption восновнойветке, source/artifact/runtimequalification иactual approved training-resource measurement остаютсяR03/R07/R18/R19. Этотmanualperfpatch неоткрываетновыеfits и не заменяетLLMpatchstudy/R17decision.

[Patch and measured scope](RESEARCH_NATIVE_DOT_MUL.md), [manual patch](RESEARCH_NATIVE_DOT_MUL_V1.patch), [final observations](../.local/research-dot-optimization-real-20261027/observations.json).

### M61 — сверка остатка и текущих чеклистов послеM55–M60, 27 октября2026

- [x] ВкорневомчеклистеисправленустаревшийтекстR05:opt-in transport capture/API/CLI ужеестьM55/M56;production adoption,backendquality/tokenproof/accountspend ещёне закрыты. M58stored4073counter evidence отделёнотoriginal wire/accountinvoice иsyntheticusage.
- [x] Вначалеплана добавленпорядокследующихдействийR02–R20. M50integration→M55иM55CLI→M56 закрытыпоссылкам,evidence-mapсодержит20rootIDs:19open/1scopedR01closed. OriginalfailedM21/старыенеполныеsourcewindowsнепереименованывуспех.
- [x] SnapshotM59freshcandidateнеподменяетapprovedbaseline;M57exactsyntheticfitreuse/M60scalarCPUbenchmarkневыдаютresearchattemptsилиLLMusefulness. Main/defaultpipelineнепереключены;model/provider/operationalfitactionsэтогонаправления0.

[Checklist map](../.local/research-dot-optimization-real-20261027/checklist-map.json).


### R03/R06/R07/R19/M62 — фиксированный worker для fit reuse, 27 октября 2026

- [x] Новый `training_fit_reuse_worker.py` выполняет пакет M57 в одном trusted процессе: семь логических конфигураций, один train-only standardizer, четыре L2 fit. Все семь caller admissions нужны до запуска; callback не является authority/budget boundary. Existing-budget adapter и verification оригинальных manifests ещё не реализованы.
- [x] CPU10s/address-space256MiB/wall≤20s/nice+10/file-size2MB/core0. Input≤20MB и output передаются anonymous private descriptors; minimal environment без credentials/journal paths, fixed module command, stderr discarded. Parent deadline включает startup/wait/decode/validation; cancel/timeout→kill/reap, cleanup grace1s. Child имеет собственный20s alarm. Network namespace/whole-server bound этим worker не обеспечены.
- [x] Parent/child проверяют source/policy/request/plan, artifact/report/binding hashes, vector shape/finite/positive scales, split/data/source/threshold/boundary/counts. Kernel rlimits/CPU/maxRSS/nice/env keys и отдельный parent wall сохранены в original synthetic receipt. Это structural consistency, не statistical oracle или dataset approval.
- [x] 31 новый тест; вместе с M57 —56passed/6.30s. Полный профиль82files:2595passed/225.39s. Реальный subprocess на synthetic20+20rows дал точно тот же полный результат, что M57; parent не fit/predict. Проверены partial admissions, source/input mutations, launch failure, cancel/deadline, malformed/oversized/nonzero output, no retry/refund/cache.
- [x] Предыдущие coordinator/phase/planner/model implementations, девять original journals и исчерпанный numeric3/3 не менялись. Operational fit/prediction/provider calls0; synthetic unit computations не выдаются за реальный пилот или measured whole-bot speedup. Основной бот/registry/сервисы не переключались.
- [x] После переноса offline-проверка в actual worktree сверила1978файлов, полный original synthetic receipt/plan/source и19открытых групп; fit/predict/Popen/journal constructors были запрещены. Девять original journals и10reviewed main files сохранили hashes. CPU/maxRSS receipt — sample до final serialization, не полный after-exit consumption total.
- [x] M63 связывает original common+inner effect keys и worker на synthetic fixtures; публичный путь пока читает только завершённый cache.
- [ ] Operational admission adapter, approved original manifests/data/protocol/evaluator и controlled study остаются R02/R03/R06/R07/R08/R17/R18/R19. Выполнение M62 не закрывает ни одну из19root groups целиком.

[Worker и границы](TRAINING_FIT_REUSE_WORKER.md), [synthetic receipt](../.local/research-fit-reuse-worker-real-20261027/synthetic-worker-equivalence.json), [полный профиль](../.local/research-fit-reuse-worker-real-20261027/profile-result.json).


### R03/R06/R07/R17/M63 — учёт пакетного fit в существующих журналах, 28 октября 2026

- [x] `training_fit_reuse_budget.py` сохраняет native common effect key и single-candidate ResearchAttempts study/attempt identity, требует существующие private journals и frozen protocol/budget. В synthetic fixture семь отдельных общих и внутренних резервирований предшествуют одному bounded worker; четыре физических L2 fit учтены без скидки на логические попытки.
- [x] Существующий baseline можно взять из согласованного кеша; новые конфигурации используют общий расчёт. Legacy cache отмечается отдельно без новой provenance. Cross-study duplicate effect, отсутствующие/изменённые bindings, незавершённые/failed claims и изменённый context отклоняются; partial writes, cancel, timeout и crash остаются в истории без retry/refund. Между двумя SQLite journals нет общей атомарной транзакции: после сбоя может потребоваться сверка.
- [x] Public `run_existing` пока допускает только completed cache. Synthetic tests используют внутренний экспериментальный путь; private Python API не является security boundary. Оригинальные manifests и approved protocol не подтверждаются переданными digest, прежний numeric-control 3/3 не расширялся. Main trainer и LLM proposal handler не подключены.
- [x] Полный профиль 83 файлов: 2616 passed за 161.79s, включая 21 новый тест. Дополнительная отдельная проверка подтвердила, что прежний `ResearchCoordinator.fit` повторно использует пакетный результат по тому же ключу без worker/fit. Целевой профиль до этой проверки: 77 passed; дополнительная проверка: 1 passed. Исходник теста полного профиля восстановлен из последующего добавления теста и сохранён отдельно.
- [x] На оригинальной привязке existing synthetic common journal адаптер отказал из-за отсутствующего fit.sqlite; все четыре отсутствующие привязки и девять исходных журналов не изменились. Operational fit/predict/provider calls: 0. Nested common wall measurements перекрываются; их сумма не является фактическим wall time одного пакета.
- [x] После переноса actual-worktree postcheck сверил 1994 файла, оба синтетических журнала по сохранённым счётчикам, 9 оригинальных журналов и 10 файлов main; оригинальный отсутствующий fit.sqlite снова отказал до запуска.
- [ ] Подключить проверку оригинальных source/revision/exposure manifests и допущенного protocol к публичному выполнению, reconciliate исторические расходы/привязки и соединить с actual trainer/evaluator; затем провести controlled comparison и независимую проверку R02/R03/R06/R07/R08/R09/R17/R18/R19. Открыты 19 root groups, R01 закрыт в ранее описанной области.

[Adapter и ограничения](TRAINING_FIT_REUSE_BUDGET.md), [synthetic учёт](../.local/research-fit-reuse-budget-real-20261028/synthetic-budget-integration.json), [refusal оригинальной привязки](../.local/research-fit-reuse-budget-real-20261028/original-path-refusal.json), [полный профиль](../.local/research-fit-reuse-budget-real-20261028/profile-result.json).


### R02/R04/R07/M64 — источник → признаки и метки для проверочного набора, 28 октября 2026

- [x] `research_source_dataset.py` воспроизводит original M48 local HTTP capture через закреплённый main `SupabaseMarketReader`/`_load_examples` в фиксированном offline worker. Нет HTTP/SQL/credentials/fit/prediction/publication; source и native runtime hashes проверены. Полный ordered digest всех 4901 examples совпал с двумя исходными native/exact-parser digests.
- [x] Для уже просмотренного snapshot 26 октября сформирован review-only split: train 3915, validation 895, purge 91; validation начинается 06:05 UTC, train labels строго до 05:50 UTC (дополнительное embargo 15 минут). Метки всех 4901 reconstructed examples зарегистрированы как exposed в отдельном exposure record. Это не независимый holdout и не preregistered study; общий реестр всех прежних просмотров остаётся неполным.
- [x] Source review остаётся `review_source_data`: 13/20 пар против минимума16/20. AERO, BR, CAP, MON, PEPE, SUI и WLD исключены как stale на исходном срезе. Current source freshness не проверялась. Historical first-seen/revision lineage неизвестна; dataset/fit/LLM proposal не допущены. Review wrapper не является готовым входным файлом planner; вложенная совместимая схема не доказывает approval.
- [x] Без нового worker offline verify повторно сверил исходные source/diagnostics, полный сохранённый replay, split/dataset checksums и9original journals. Полный профиль84files: 2632 passed за 156.88s; focused38 passed. Исходная synthetic fixture ошибочно включала метки позже cutoff: первые2теста отказали, fixture исправлена, исходный failure log сохранён. Новый fit/predict/provider/DB actions этого направления:0.
- [x] После переноса в isolated worktree offline verify повторно подтвердил full native digest, split 3915/895/91 и exposure record, проверил 2012 файлов и 9 original journals; worker/fit/predict при этой проверке были запрещены.
- [ ] Исправить покрытие источника с учётом работы основного агента, подтвердить историческую доступность и полный exposure inventory, утвердить dataset/protocol/budget; только затем связать data gate с actual advisor/trainer и провести честное сравнение R02/R03/R04/R06/R07/R08/R09/R17/R18. Остаются19root groups, R01 закрыт в ранее указанной области.

[Описание и ограничения](RESEARCH_SOURCE_DATASET.md), [review dataset](../.local/research-source-dataset-real-20261028/review/review.json), [реестр экспозиции M64](../.local/research-source-dataset-real-20261028/exposure.json), [полный профиль](../.local/research-source-dataset-real-20261028/profile-result.json).


### R05/R06/R10/M65 — актуальный free backend metadata, 28 октября 2026

- [x] Один public catalog GET в 03:51 UTC вернул 464 entries; точный старый `nvidia/nemotron-3-super-120b-a12b:free` отсутствует. Существующий free-price guard применён к 16 другим `:free` entries. Candidate для дальнейшей квалификации — `nvidia/nemotron-3.5-super-vl:free`: нулевая цена prompt/completion в каталоге, context 1M, объявлены response_format/structured_outputs. Реальная endpoint availability/качество/стоимость на уровне аккаунта и native input-token proof не установлены.
- [x] Один authenticated GET текущего JobPilot key сообщает free daily 0/50 used, key limit100 и usage0 на момент 03:51 UTC. Это общий key snapshot, не выделенный CryptoForge budget и не account-wide invoice. Raw response/credentials/labels/IDs не сохранены; provider-usage history и расходы остальных keys остаются неизвестны.
- [x] Один loopback Ollama tags GET завершился недоступностью. Host memory available1,613,426,688B ниже fixed policy3,221,225,472B; disk lower bound проходит, unpacked size неизвестен. Model install/start и service changes:0.
- [x] Offline verification повторно связал full public catalog с receipt и candidate pricing, а обезличенные key fields — с original response hash.9original journals и10reviewed main files неизменны; generation/fit/prediction:0. Этот шаг не перезапускал полный профиль без изменения runtime: последний 2632passed(M64).
- [x] После переноса actual-worktree offline verify сверил каталог/16free entries, candidate pricing, sanitized key metadata,2037файлов и9original journals; новых запросов или чтения ключа при проверке не было.
- [ ] Подготовить отдельную версию fixed audited provider для выбранной бесплатной модели с сохранением старых identities/журналов, доказать input-token bound либо явно отказать и проверить качество без paid fallback; затем подключить к согласованному исследованию. Автопереключения сейчас нет: M55/M56 всё ещё закреплены на отсутствующей модели. R05/R06/R10/R16/R17/R19 остаются открыты;19root groups open.

[Обновлённый backend](RESEARCH_BACKEND_CURRENT.md), [candidate metadata](../.local/research-backend-current-real-20261028/candidate-review.json), [проверка](../.local/research-backend-current-real-20261028/verification.json).
