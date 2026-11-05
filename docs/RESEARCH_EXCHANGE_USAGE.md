# Readonly exchange usage (M58)

`python -m cryptoforge.research_exchange_usage --journal <original-api.sqlite>`
`--capture-directory <saved-attempt> --output <new-private-report.json>` reconciles
stored API usage with explicitly supplied M55 transport captures. Repeat input
flags for up to16 journals/64 capture directories. Output is exclusive mode0600
and must be separate from journals and audit directories.

The verifier requires initialized owner0600 standalone API journals, no active
WAL/SHM/rollback sidecars, and unchanged file bytes across the read. SQLite uses
`mode=ro&immutable=1`, query_only and one transaction. It checks the native
two-table schema, persisted daily quota, canonical request keys and completed
payload digests. Each snapshot executes five explicit readonly SQL statements;
authorizer tests deny DDL/DML. No journal or schema is initialized or repaired.

Transport packs must match the original journal path digest, request key, report,
provider/model and the native completed-cache capture/manifest reference. A
copied database at another path is not the original journal. Identical copies
of a capture count once; conflicting versions are refused. Normalized completed
usage must agree with the captured response. A legacy payload without a native
capture reference cannot be upgraded to original wire by attaching a new pack.

Known counters from failed proposals remain useful accounting evidence. Partial
or missing usage stays null, with known subtotals and separate unknown counts.
Native cost values are preserved as reported credits; the older M50 field name
does not turn those values into a USD invoice. Missing charge is not zero, and a
zero catalog price is not an observed charge. A nonzero charge on a rejected
free-route response is retained, not rewritten as free.

Each journal has its own subtotal and status disagreements. Cross-journal/global
totals remain null. The output stores no raw model identifier, diagnostic report,
proposal rationale, key, response body or HTTP headers. Native model identity is
hashed. These file/hash checks do not independently authenticate provider billing
or prove that a host-controlled record is true.

The original retained API row reports3165 prompt+908 completion=4073 tokens in
its normalized completed payload. It has no original transport capture and no
observed charge. Separate M55 fixture journals remain explicitly synthetic;
their usage is not added to the real row. Re-reading a stored counter does not
represent a new generation or additional token consumption.

No common-budget debit, dedup/refund, protocol change, cap increase, provider
request, credential read, model operation or PostgreSQL action is performed.
Historical overlaps, account-wide JobPilot costs, whole-server consumption and
the four missing operational bindings remain unresolved R06/R17/R19 work.
