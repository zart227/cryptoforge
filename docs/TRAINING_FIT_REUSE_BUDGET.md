# Existing-journal fit reuse adapter (M63)

`training_fit_reuse_budget.run_existing` currently reads **completed cache
only**. A fresh fit is refused until original source/revision/exposure manifests
and the new numerical protocol are qualified and connected. This public entry
point does not create or migrate journals, approve a study, raise a limit, open
a new numerical allowance, or authorize trading. It has no CLI and is not
connected to the production trainer or LLM proposal handler.

The private experimental implementation has been exercised only with disposable
synthetic datasets and journals. Its `_allow_unqualified_fresh` switch exists to
test unfinished integration; private Python functions are not a security
boundary and must not be used to bypass missing data/protocol qualification.
Before operational use, connect actual verified manifests and an explicitly
admitted numerical protocol to the public entry point, reconcile historic
expenses and bindings, and verify the complete integration and resource limits.

For each one-parameter configuration the adapter preserves the existing
coordinator effective key and the original single-candidate ResearchAttempts
study/attempt key. It requires an existing owner-private, complete fit journal
with the exact protocol version and unchanged family maximum; the common v5
journal and its original bindings and limits are also required. No database is
created, initialized, migrated, copied for admission, or assigned a new budget.
It detects another native study with the same effective configuration and
refuses it for reconciliation rather than repeating an already-counted effect.
History scans are bounded to 500 studies and 50 candidates per study.

Existing completed native results are matched across the common and inner
journals and returned without refitting. Legacy results lack the new full
context binding and are counted separately; this does not upgrade their
provenance. Previously completed reuse results require the same context hash.
An inner attempt without the matching common cache, an interrupted claim,
failed action, or unresolved duplicate study is refused. Mixed batches can
reuse an existing baseline while evaluating only newly admitted configurations.

For experimental synthetic execution, all new common reservations are held
before any inner claim or numerical work. Then each new configuration receives
its original claim and inner reservation. The M62 worker's callbacks verify
both reservations and the claim for each configuration before its single
bounded subprocess starts. All logical configurations remain charged; shared
standardization, fitted L2 heads and probabilities do not make extra attempts
free. Claims persist after failure or process exit. Failed, timed-out, cancelled,
interrupted and partially written work is not automatically retried or refunded.
Because the journals are separate databases, cross-journal updates are not one
atomic transaction: a crash can leave partial records requiring reconciliation.

The common journal reports one `numeric_fits` observation for the first logical
configuration of each physical L2 fit, rather than seven for four shared fits.
Its per-action wall measurements overlap because the original common handlers
are nested to reserve the whole batch. Their sum is conservative accounting,
not measured total wall time. The per-result legacy `elapsed_seconds` is the
same shared batch time and must not be summed as seven independent durations.
The worker receipt supplies the separate batch time and operation counts.

The full profile included 21 new tests; one additional native-coordinator cache
compatibility test passed separately. They cover both native keys, seven reservations/four fits, cached
baseline plus six new configurations, missing protocol or journal, both budget
limits, duplicate effects across studies, incomplete and changed history,
context mismatch, cancellation/timeout/process exit and partial writes. They
use synthetic fixtures, never the original budgets or real trading data.
The actual previously inventoried common journal is synthetic accounting, and
its bound fit journal is absent; a separate read-only refusal probe confirmed
that it stays absent. The prototype numeric-control allowance remains 3/3 and
cache-only. Neither this adapter nor its tests show training speed or trading
profitability on real data.
