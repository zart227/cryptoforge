# Candidate v3: existing accounting and audited wire

M69 implements the M68 request contract as separate v3 candidate adapter,
exchange cleaner/verifier, fixed child worker and existing-journal CLI. The
OpenRouter request uses the exact candidate model, identical prompt and
`max_completion_tokens: 2048`; the clean exchange captures and verifies that
same payload. Its API request key is the M68 prospective identity, which binds
the payload and implementation as well as the original native inputs. The v2
implementation, keys, captures and verifiers remain unchanged; v2 and v3
verifiers reject each other's capture identities.

The v3 entry point requires the established v5 common budget and initialized,
owner-private API journal with the exact existing quota policy. V2 and v3
entries use the same daily count. It does not create or migrate the journal,
change the quota, retry failed/interrupted work, or add an allowance. Each new
uncached request must pass strict native input-token admission before any
reservation, key read or worker launch. No CLI switch or public Python option
disables that requirement. Existing cached advice is accepted only when its
original v3 capture verifies, including the proposal and request binding. The
standalone M68 `admit_new_completion` remains a deliberately closed preview
stub; operational v3 admission is the separate existing-only CLI and is also
currently closed to new requests.

Tests synthesize OpenRouter responses with a mocked transport and run the fixed
child process against a local loopback Ollama fixture. The fixture exists solely
to exercise the child boundary; the public v3 entry point allows only the fixed
OpenRouter candidate. Tests cover shared quotas across versions, failed-attempt
accounting and no automatic retry, model/price/output identity, malformed or
truncated responses, capture tampering, and strict failure before admission.
A separate two-case integration test uses a simulated input-bound proof and
mocked responses to exercise one common and one API reservation, including a
failure. The production entry point still requires the real proof. These
tests do not demonstrate actual OpenRouter routing, model quality, provider
cancellation or billing. Internal Python functions are not a security
boundary and do not authorize live operation.

On the original established synthetic common journal binding, the API journal
file is absent. An offline check refused to initialize it, confirmed the v2 and
v3 identities differ, and left the common journal unchanged. No real provider
request, key read, model fit, prediction, production database write or service
change was performed.

Before a live controlled experiment, establish an approved local dataset and
historical/exposure lineage, baseline, evaluator and explicit numerical budget;
reconcile old/shared account usage and original journal bindings; recheck the
free catalog and qualify the exact endpoint, native input bound, response and
model quality. The prototype numeric budget remains 3/3 completed-cache-only.
This work does not qualify generated patches or connect the advisor to the main
trading bot. R02–R20 remain open.
