# Source coverage remediation diagnostic — retrospective snapshot

`research_source_remediation.analyze_verified` re-verifies the M64 original
review, source diagnostics and full source-to-dataset replay, then produces a
read-only checklist of exclusions. It does not connect to the database, run the
replay worker, fit a model, call a provider or authorize data. The report binds
the review, diagnostics and original capture hashes and uses the pinned native
15-minute freshness rule and 80% pair coverage rule.

At the original cutoff, 26 October 2026 **12:08:39.379786 UTC**, 13 of 20
requested pairs passed. At least 16 are required, so **three more** would have
to pass *if all 13 accepted pairs remained eligible in the same assessment*.
All seven exclusions were stale closed training sources:

- AERO and WLD: latest known closed candle at 11:45 UTC; MON: 11:50; PEPE: 11:35.
- BR: 04:40; CAP: 08:05; SUI: 07:35 UTC.

For each excluded pair the captured 500 rows comprised 499 rows known closed
and one row whose recorded ingestion preceded its candle close. No gaps were
found between the retained known-closed rows. This describes the stored
eligibility evidence in the [original source diagnostics](../.local/research-source-diagnostics-real-20261026/report/diagnostics.json);
it does not identify why the latest data were stale or prove the next candle was available.

Under the captured five-minute schedule and 900-second maximum closed-candle age,
a close at or after **11:55 UTC** would have been necessary for the original
cutoff. This is a timing boundary only: it does not say any such candle existed,
was received after close and before the cutoff, or passed continuity and minimum
history checks. Nor does it establish the upstream or collector fault. A current
snapshot may have different pairs, timing and failures; this report cannot
assess it. Backfilling newer or revised candles today cannot by itself prove
what was available at the original cutoff.

The deterministic next steps for a new eligible study are: obtain an approved
immutable local-source capture, independently verify closed-candle availability,
continuity and historical revision/first-seen lineage for all requested pairs,
reconcile the already exposed periods, then freeze the windows, evaluator and
numerical budget before training. The successful M52 prospective 20-pair snapshot
is separate evidence for its own time; it does not retroactively repair M64 or
supply all historical first-seen lineage. The report is not a training dataset,
a root-cause attribution, a statistical comparison or an LLM proposal.

No attempt is made to create the missing API/fit journals or to modify the
collector, database, trading service, production model or old research budgets.
R02/R03/R04/R07/R08/R09/R17/R18 remain open.
