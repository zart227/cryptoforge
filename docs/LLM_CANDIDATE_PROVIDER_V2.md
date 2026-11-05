# Versioned free-model candidate: offline qualification only

The existing M55/M56 OpenRouter implementation pins the now-absent
`nvidia/nemotron-3-super-120b-a12b:free`. Its exact source is part of its
record identity, including the exchange cleaner. M66 adds separate
`llm_exchange_audit_v2`, `llm_audited_provider_v2` and
`llm_existing_advisor_v2_cli` modules pinned to
`nvidia/nemotron-3.5-super-vl:free`. Earlier sources, request keys, attempts and
verifiers are retained. A v2 record has different source/policy hashes; the old
verifier must not claim it as an old record. The shared API request key still
includes the exact requested model, prompt, parameter catalog and diagnostics.

The public v2 entry point accepts only this exact OpenRouter model, existing v5
phase and initialized private API journal. It refuses a new completion before
any common or API reservation, credential read or worker launch while the
verified native input-token limit is unavailable. Passing `False` cannot disable
this requirement in the public Python API or CLI. An existing candidate cache
entry is accepted only with its original verified v2 capture; a legacy entry
without wire evidence is refused rather than reconstructed. A cache read may
still be recorded in the existing common phase, as in the earlier coordinator.
No journal is created or migrated and no allowance is added.

The fixed worker retains the prior bounds, no automatic retry, catalog price
check and zero prompt/completion max-price request, private cleaned capture,
report/model/payload binding and no billing/semantic-quality claim. The
internal low-level worker and evaluator are not security boundaries: tests use
synthetic OpenRouter bodies and an Ollama loopback fixture directly. They do
not prove the new model's live behavior, free routing or quality. This version
has no public Ollama option; existing v1 Ollama behavior is unchanged.

M65 catalog evidence is a dated snapshot, not a live qualification. Account
limits are shared with jobpilot-ai. OpenRouter's
[chat completion reference](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
identifies `max_tokens` as deprecated in favour of `max_completion_tokens`;
that response limit is not evidence of a native input-token bound. The pinned
factory remains unchanged to preserve the old request factory and audit
identity. M68 adds an offline v3 preview for the modern output-limit field; M69 integrates
it into separate existing-only accounting and audited transport on synthetic
fixtures. Input/output-limit and endpoint qualification remain prerequisites
for live use. A model catalog entry does not prove endpoint
availability, the final invoice, provider cancellation or the statistical
quality of any advice.

Remaining before controlled use: approved development data and lineage,
complete exposure inventory, evaluator and explicit numeric/research budget;
reconcile old and shared-account usage; qualify the candidate endpoint and
native token limit; run a bounded preregistered quality comparison. R02–R20
remain open; R01 is complete only within its previously documented scope. The experimental advisor is not
imported into the primary bot and does not authorize training or trading.

See [v3 request contract](LLM_CANDIDATE_PAYLOAD_V3.md).
