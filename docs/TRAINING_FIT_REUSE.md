# Ephemeral fit reuse primitive (M57)

`training_fit_reuse.evaluate_admitted_batch` computes the existing isolated
long-head catalog with one shared train-only standardizer, one optimizer and one
train/validation probability pass per distinct L2. Threshold diagnostics and
artifact metadata are rebuilt for every logical configuration. There is no
persistent cache, CLI, subprocess launch, journal write or production integration.

The seven existing baseline/single-parameter configurations need four L2 fits,
one standardizer and seven logical admissions. For the synthetic20+20row fixture,
optimizer row presentations fall700→400 and probability calls280→160. Actual
primitive call counters were checked independently in tests. Weights, bias,
standardization, complete legacy artifact bytes/checksum, selected observations
and both diagnostic reports match seven separate original evaluations exactly.
The old environment receipt is not manufactured by this pure primitive. M62
provides the [fixed resource-bounded worker](TRAINING_FIT_REUSE_WORKER.md) with
its own execution/resource evidence; original-budget integration and approval
remain separate requirements.

`plan(data, protocol, configurations, evidence_context=...)` performs only
validation and dependency planning. The protocol must satisfy the existing
planner's immutable data/source/boundary/optimizer/operation contract. Only
baseline plus one existing L2/threshold change is supported. Cross-parameter
searches, duplicates, lookback changes and arbitrary model families are refused.
The batch also bounds total optimizer feature operations at14million.

All configurations must pass the caller's `admit(evaluation, context_sha256)`
callback before any numerical function is invoked. The callback returns None or
raises. Partial admissions stay charged when a later admission or fit fails;
this primitive has no refund mechanism. **The callback seam is not a budget or
authorization boundary.** No operational budget adapter is implemented here.
Tests supply synthetic callbacks; callers cannot claim approval by passing a
no-op callback. Existing coordinator/worker/phase sources and all original
journals remain unchanged. The exhausted3/3prototype allowance is not reopened.

The context includes exact dataset/protocol/implementation/target/feature/epoch/
learning-rate identities plus mandatory raw-source, source-revision, exposure
inventory and execution-protocol manifest digests. These four digests are
**declared bindings, not verification of the original manifests or approval**.
A future admitted executor must perform that verification and protocol/budget
qualification first. Changing any binding invalidates fit and prediction keys.
The outer batch binds each logical evaluation, legacy artifact and reports to
the full context; a legacy artifact alone is not sufficient provenance.

Reuse exists only within one function call. A second call repeats physical work
and needs its own admissions; it cannot use earlier in-memory data as a free
attempt. Shared numerical arrays are copied into separate output artifacts so
mutating one threshold result cannot change another. There is no storage-level
cache migration or ability to ignore existing logical evaluation charges.

The tests establish computational equivalence on synthetic unit data. They do
not measure actual training CPU/wall savings, qualify whole-server resource
limits, approve real data, compare LLM usefulness or show trading profitability.
The native primary multi-head trainer is outside this primitive's scope.
R02/R03/R06/R07/R08/R17/R18/R19 remain open.
