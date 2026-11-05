# Free backend metadata refresh — 28 October 2026 (M65)

At 03:51 UTC the public [OpenRouter model catalog](https://openrouter.ai/docs/api/api-reference/models/get-models)
contained no exact entry for the previously pinned
`nvidia/nemotron-3-super-120b-a12b:free`. The catalog response was complete and
the existing fixed-price guard therefore rejects that model. The old M42/M43
observations remain historical evidence, not current availability.

Sixteen `:free` entries passed the existing catalog check for zero prices. One
review candidate is `nvidia/nemotron-3.5-super-vl:free`: the catalog reported
zero prompt/completion prices, a one-million-token context and support for
`response_format` and `structured_outputs`. These are catalog properties, not
proof that a provider endpoint currently serves this request, that responses
meet the project's schema or quality requirements, or that there is a verified
native input-token bound. The model has not been automatically selected or
used. The original M55/M56 audited worker/CLI remain pinned to the unavailable model.
M66 adds a separate candidate v2 with preserved journal identity and strict
input-token refusal; its endpoint and live quality are still unqualified. No paid fallback is enabled.

One authenticated read of the existing JobPilot key's
[current-key metadata](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)
reported 0/50 free requests used and a 100-credit key limit at the time of the
snapshot. These are shared key counters and limits, not a dedicated CryptoForge
allowance or an account-wide invoice. Other keys, historic activity and actual
provider-side expenses remain unreconciled. The response was reduced to
allowlisted counters and budgets; credential, labels, account IDs and raw key
response were not saved.

The local Ollama tags endpoint was unavailable. Available host memory was
1,613,426,688 bytes against the fixed policy requirement of 3,221,225,472 bytes;
the disk lower bound passed while unpacked size remained unknown. This snapshot
does not demonstrate an installed or runnable local decision model. No model was
downloaded or started and no service configuration was changed.

The refresh used one catalog GET, one loopback tags GET and one current-key GET,
with no automatic retries and no generation, training, prediction, quota reset
or journal mutation. A current free catalog row is time-sensitive; it must be
rechecked before use. Structured output quality, source/data admission, full
account cost, hard input-token proof, operational integration and a genuinely
LLM-produced patch remain open.
