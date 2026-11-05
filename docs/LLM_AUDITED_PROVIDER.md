# Audited advisor transport (M55)

`llm_audited_provider.propose_audited` is an opt-in API for an existing
`ResearchCoordinator` or `PhaseResearchCoordinator`. It uses the same bound
common budget, proposal journal, daily quota and effective API request key.
It does not repair missing bindings or migrate an established journal.
The native `ResearchRequests` initialization rules remain in place when the
caller explicitly disables strict token admission; tests use that mode only
with disposable synthetic journals. This API is not an existing-only CLI guard. The default coordinator/phase CLI and main trading runtime still use
their earlier handlers.

```python
from cryptoforge.llm_audited_provider import propose_audited

receipt = propose_audited(
    existing_phase,
    approved_validation_diagnostics,
    audit_root=existing_owner_private_directory,
    jobpilot_env=explicit_jobpilot_env_path,
    require_verified_input_limit=True,
)
```

The default strict input-token requirement currently refuses a new completion
before common/API reservations, credentials or HTTP. No native hard input-token
proof was added here. Tests explicitly disable that requirement for synthetic
localhost replies; that is not a qualification of a production provider.
Completed API cache entries remain readable under the strict requirement.

For a fresh admitted request, the existing API journal reserves first. A fixed
child receives bounded settings through stdin and reads the explicitly supplied
JobPilot credential path only inside the child. OpenRouter is pinned to
`nvidia/nemotron-3-super-120b-a12b:free`; its complete pricing entry must contain
only zero prices. The original prompt factory sends a zero maximum prompt and
completion price. Ollama endpoints remain local HTTP only. No redirect, retry,
model substitution or paid fallback is implemented. Provider-internal routing
and transformed upstream requests are not attested.

Each private `audit_root/<existing request key>/` contains:

- `attempt.json`: report/API journal path digest, original effective request key,
  source fingerprints and the intended request payload digest.
- `dispatch.json`: completion dispatch intent, payload/endpoint digests and the
  catalog receipt, written before sending the completion request.
- `exchange/`: M50 cleaned request, complete cleaned JSON response when bounded
  and parseable, validation, provenance and manifest. Raw response bytes, HTTP
  headers and credentials are never persisted. Non-JSON replies retain metadata
  only. Existing M50 provenance describes its offline record builder; the separate
  transport binding identifies the actual body observed by this fixed child.
- `capture.json`: actual transport HTTP status, original body digest, exact
  outgoing payload digest, record manifest and API binding.
- `outcome.json`: the supervisor's local completion/failure/timeout/cancellation
  and child-reaping result. Failure text and provider bodies are not copied here.

The parent validates the saved exchange before returning accepted advice.
Rejected proposals and non-200 responses retain their cleaned records, known
native usage and nonzero reported cost. Unknown usage/cost remains null. On a
transport error, overflow, deadline or process death, a complete response may be
unavailable; dispatch intent is not evidence that the provider did no work.
Killing the client does not prove server cancellation. No attempt is refunded.

Directories require owner mode0700 and records mode0600. No file is overwritten.
The child has CPU5s, address-space256MiB and per-file1.3MB limits; response bodies
are bounded to1MB, output to64KB and the attempt is verified against a2MB total.
These bounds do not cover a model server, HTTP intermediaries or whole-account
spending. The original local wall budget includes process startup, credential
read, catalog, completion and validation, plus the existing2s cleanup grace.

`verify_attempt(directory)` checks saved records without reading keys, starting
workers, making HTTP requests or mutating a journal. New cached advice checks its
original saved capture; missing/changed capture is refused without recapture.
Legacy advice without a capture reports that gap explicitly and is not upgraded
to historical wire evidence. Checksums bind the retained files; they are not an
independent attestation of the provider or the host.

M55 tests use synthetic journals and local fixture servers. No real generation,
model fit/prediction, operational journal migration, account billing audit or
provider-quality study was performed. R02/R03/R05/R06/R07/R16/R17 remain open.


## Existing-only CLI (M56)

`python -m cryptoforge.llm_existing_advisor_cli verify --directory <saved-attempt>
--output <new-private-receipt.json>` verifies a retained capture offline. The output
must be outside the saved attempt and must not already exist.

The `proposal` subcommand accepts the original `--database`, `--proposal-ledger`,
`--semantic-ledger`, `--fit-ledger`, `--semantic-live-ledger`, persisted
`--semantic-live-policy`, `--code-policy`, `--numeric-policy`, `--phase-policy`,
optional `--policy`/`--resource-policy`, a completed `--experiment-receipt`, private
`--audit-root`, and separate `--output`. Provider/model/local Ollama URL and explicit
`--jobpilot-env` follow the same fixed free rules. Use `proposal --help` for syntax.

The CLI always requires native input-token proof for a new completion and offers
no flag to disable it. Currently that preflight refuses new completions. Existing
completed advice can still be delivered under the original common budget; a
legacy cache entry without original wire reports its gap. Missing initialized
API/common journals are refused, including removal between checks and native
open. The four missing original accounting bindings remain absent. No automatic
recovery, new journal, migration, refund, cap increase or new fit is performed.

The internal `propose_existing` adapter's non-strict parameter is used only by
synthetic local fixture tests here; it does not certify a real backend or protocol.
Main and the previous default phase CLI have not been switched to this opt-in path.
