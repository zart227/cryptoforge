# Candidate request payload v3 — offline preview

OpenRouter's [chat completion reference](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
marks `max_tokens` deprecated and documents `max_completion_tokens` as the
completion-token limit. `llm_candidate_payload_v3.preview` builds a separate
prospective payload for the M65 candidate, retaining M66's pinned model, message
factory, temperature, non-streaming mode and zero-price routing while using
`max_completion_tokens: 2048`. It is an offline preview; no key, HTTP client,
worker, account or journal is used.

The legacy native API request identity contains the model, diagnostics, prompt
and parameter catalog but does **not** bind this changed output-limit field.
Therefore a v3 identity additionally binds the full payload hash, fixed contract
and implementation hashes. It differs from the legacy key even if the model and
messages are identical. The preview itself never reserves the identity or
migrates a cache entry. M69 integrates the identity in a separate existing-only
v3 CLI, common/API accounting, fixed audited worker and offline verifier, tested
on synthetic fixtures. Strict input-token admission still prevents a new real
dispatch. The old key is not reused for a different payload.

A bounded output is not a native input-token proof. This module's standalone
admission stub remains closed even with a simulated bound. The separate M69 CLI
provides the v3 transport/accounting path but also refuses a new completion
until a real native input bound is qualified. This is not
an endpoint compatibility test or proof of model quality or account billing. The
M66 adapter remains on its original request factory and is not switched to v3.
Actual qualification still requires the approved data/protocol/budget, current
free-route verification, shared-account reconciliation, input-token proof and
controlled quality evaluation.

The saved preview uses synthetic diagnostics only. Its hashes are not approved
study artifacts. The separate v3 factory does not change old source, journal
identities, research allowances, the main trainer or trading services.

See [M69 audited wire and accounting](LLM_CANDIDATE_WIRE_V3.md).
