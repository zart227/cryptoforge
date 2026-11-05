# Fixed fit reuse worker (M62)

`training_fit_reuse_worker.run` executes the M57 batch primitive in one trusted
subprocess. The seven existing baseline/single-parameter configurations share
one train-only standardizer and four L2 fits. All seven logical evaluations
still require their own admission callback before the process starts. Partial
admissions, launch errors, cancellation, timeout and fit errors have no refund
or automatic retry. The module never opens or creates a journal.

This completes the resource-bounded **execution primitive**, not operational
budget integration. `admit` remains a caller-owned callback, not an authority or
security boundary. Neither a no-op callback nor supplied manifest digests prove
that data, exposures, protocol or budget were approved. No real dataset is
admitted by this module. The existing coordinator, ResearchAttempts and phase v5
sources/identities/history remain unchanged. A future adapter must verify the
original source/revision/exposure/execution manifests, preserve each effective
configuration's existing attempt/cache identity, and reserve the original common
and inner budgets before calling this executor. The old3/3numeric cap stays shut.

The fixed process uses CPU10seconds, address space256MiB, wall time at most20s,
nice+10, file size2MB and core dumps disabled. The parent checks a single local
deadline through startup, waiting, decoding and receipt validation, then kills
and reaps on cancellation/deadline; cleanup has a separate1s grace. The child
also has its own20s alarm. Shorter parent deadlines are supported; higher limits
are refused. The same limit covers the whole batch, not each of its fits.

Input is canonical JSON of at most20MB. Input/output use anonymous owner-private
temporary files, inherited only as stdin/stdout. This avoids an unbounded pipe
capture; the child's kernel file-size limit bounds stdout before it is read.
Stderr is discarded. Commands contain only the fixed Python module invocation.
The child receives PATH, LANG, PYTHONPATH and PYTHONDONTWRITEBYTECODE only, without
credentials, host settings or journal paths. The files close after success and
failure; no persistent model cache is created. Generated Python, shell commands
and candidate imports are never accepted. This is a trusted worker with process
limits; it does **not** enforce a network namespace or whole-server CPU/memory.

Parent and child bind the same implementation, policy, request, complete plan,
configurations, artifact and report hashes. Parent validation checks numerical
vector shape/finiteness/positive scales, diagnostic split/data/source/threshold/
boundary/counts, selection fields and exact logical bindings. This is structural
and source consistency, not an independent statistical oracle. Kernel rlimits,
process CPU, Linux max RSS, nice and environment keys are retained in the child
receipt. Parent wall time and cleanup allowance are separate. The CPU/max-RSS values are sampled before final envelope serialization and
stdout flush; they are not a complete after-exit process-consumption total.
Kernel limits continue to apply through those final steps. Metrics from the
child's own usage receipt are not whole-server measurements or account billing.

Real subprocess tests use synthetic20+20row data only. They prove exact complete
result equality to the original M57 primitive, one launch after seven admissions,
no parent-side fit/prediction, enforced kernel configuration, deadline/cancel
kill/reap, no retry on malformed/oversized/nonzero output and immutable input
capture across callback mutations. An original synthetic receipt is retained for
offline replay. No operational fit, prediction, LLM completion, registry change
or production integration is performed by this milestone. Whole-bot acceleration,
LLM usefulness, trading quality and profitability remain unmeasured.

M63 adds a [budget adapter](TRAINING_FIT_REUSE_BUDGET.md) tested on disposable
journals. Its public entry remains completed-cache-only until actual manifests
and protocol are qualified; no operational use is enabled.

R02/R03/R06/R07/R08/R17/R18/R19 remain open. The next integration work requires
an approved numerical protocol and an adapter that accounts for each logical
evaluation without reopening prior attempts or inventing new allowance.
