# Manual native dot optimization (M60)

[RESEARCH_NATIVE_DOT_MUL_V1.patch](RESEARCH_NATIVE_DOT_MUL_V1.patch) replaces the
generator in `model_training.dot` with `sum(map(operator.mul, left, right))` and
adds one standard-library import. Multiplication order, builtin `sum`, dimensions,
finite-result checks and exception behavior stay the same. No dependency, target,
weights, fitting algorithm, risk rule or budget is changed.

The patch is generated only for the reviewed native source SHA256
`9afb8aab375ec786aa8f9c9a7f617a5db642e49fcfbf45d311a413a05e63aeb7`.
`git apply --check` passes in the primary checkout and isolated worktree. It has
not been applied. The other agent's main implementation and model/service state
remain untouched. A changed source must be reviewed rather than silently repinned.

Fifteen focused tests cover2000 deterministic vectors, empty/mismatched lengths,
underflow, overflow, cancellation, infinities/NaN and existing type/error cases.
Finite scalar outputs are compared by type and exact binary64 hexadecimal value.
No model fit, probability prediction, LLM request or numerical-study admission is
performed by this review helper or these scalar tests.

Two recorded synthetic CPU measurements used seven alternating rounds of20000
calls per variant on the same seven-element vectors. Proposed/native median CPU
ratios were0.54765 and0.54820, about45% less CPU for this scalar fixture. This is
not a measured45% speedup of whole training, inference or the running bot.
There is no timing assertion in the tests. CPU/resource and numerical integration
must be checked in the actual approved execution context before adoption.

The final patch uses one line of unified-diff context, allowing default
`git apply --check` and a clean staged whitespace check. Initial three-line
context included whitespace-only context lines; its review/benchmark/full-profile
evidence was retained separately. The proposed source bytes are identical across
these patch-format variants.

This is a manual implementation optimization. It is not the genuine budgeted
LLM patch required by R16 and does not approve R17 continuation, replace the
broader R18/R19 checks or reopen the exhausted3/3prototype allowance.
