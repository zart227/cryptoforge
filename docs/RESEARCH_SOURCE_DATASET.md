# Retrospective source-to-dataset review (M64)

`research_source_dataset` reconstructs **review-only** feature and label rows
from a previously captured local HTTP source pack. The original source
diagnostics and capture, native trainer source hashes, query contract, accepted
pairs and as-of time are checked. A fixed trusted subprocess loads the retained
rows through the original main `SupabaseMarketReader` and
`ModelTrainingRunner._load_examples`; fitting, standardization, prediction and
publication functions are disabled. Its full ordered example digest must match
both the native and exact-parser hashes recorded by M48. Source data are read
locally; no database or HTTP request is made.

The review then creates a fixed exploratory split: the last six hours form the
validation interval and training labels must end strictly before the start of
validation minus a further 15-minute embargo. Examples in the intervening gap
are retained in the count as purged. The split was chosen **after** the source
had already been inspected; it is not a preregistered experiment or an
independent holdout. Features are converted from the exact recorded binary64 hex
values, and the result is checked against the existing development schema.

On the original 26 October 2026 snapshot, the reconstructed digest matches all
4,901 native examples. The review contains 3,915 train examples, 895 validation
examples and 91 purged examples. Thirteen of twenty pairs met the native source
checks; the required minimum is sixteen. The saved diagnostic route therefore
remains `review_source_data`. Counts and freshness apply to the original capture
time, not to the current database.

The `review.json` artifact wraps the candidate under a review-only schema and
includes the source and dataset checksums, split and explicit non-admission
flags. The nested dataset has the same structure as the existing offline planner
input, but schema compatibility and checksum equality are not approval. The
snapshot does not establish when each historical candle revision was first
available; the source was already exposed and the pair-coverage gate failed.
All 4,901 derived examples and labels reconstructed in M64 are recorded as
exposed in the accompanying local exposure record. The generic builder does not
update a global exposure inventory automatically; each use must be registered.
Consequently, this artifact must not be used to train, compare candidates or
authorize an LLM proposal. Approved historical lineage, exposure inventory,
coverage and a separately fixed protocol remain open.

The subprocess has CPU20s, address-space512MiB, wall60s, output8MB, nice+10,
no core dumps, a minimal environment, and fixed offline input/output. The fixed code uses an in-memory reader and refuses socket connect/bind calls;
it does not enforce an OS-level network namespace or whole-server limits. `verify` rechecks the original source
and saved complete replay and reconstructs the split without rerunning the
subprocess, fitting or predicting. The process and arithmetic used for source
reconstruction are not evidence of actual training speed or profitability.

R02/R03/R04/R07/R08/R17/R18 remain open. M64 does not alter the original
journals, numerical allowance, production model or services.

The subsequent [M67 remediation diagnostic](RESEARCH_SOURCE_REMEDIATION.md)
rechecks this same retained source and explains the seven stale exclusions and
conditional three-pair coverage shortfall at the original cutoff. It does not
refresh the snapshot or change the non-admission flags above.
