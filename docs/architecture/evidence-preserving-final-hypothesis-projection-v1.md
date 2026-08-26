# Evidence-Preserving Final Hypothesis Projection v1

Policy version: `causal-hypothesis-projection-v1`

## Purpose

AR-3 repairs the final projection defect measured by LINEAGE-2A at distractor
count 50, insertion order 0. AR-1 admitted a six-candidate bounded evaluation
frontier: five ordinary temporal controls and one exact-lineage source change.
AR-2 rejected all five controls and qualified the source change. The old final
step nevertheless sorted the six hypotheses by the existing causal score and
truncated to five before consumers selected evidence-supported hypotheses.
The supported source hypothesis was therefore absent from the persisted result.

The governing invariant is:

> Evidence qualification must happen before supported-output budgeting.

A support-qualified hypothesis already inside the bounded AR-1 evaluation
frontier cannot be excluded from the supported causal projection solely because
unsupported hypotheses have higher heuristic scores.

## Four-layer causal contract

AR-3 preserves the existing four layers:

1. Raw candidates retain the incident-change numerical ordering.
2. AR-1 creates the bounded evaluation frontier: ordinary Top-N union the
   already-proven exact immutable-lineage candidate.
3. Every frontier candidate is evaluated for causal relevance, receives its
   TC-4 evidence ledger, and receives its AR-2 support-gate classification.
4. AR-3 projects that one bounded evaluated set for diagnostic and supported
   uses.

AR-3 operates only at layer 4. It does not reopen raw candidates or perform
discovery, scoring, relevance evaluation, evidence generation, or support
classification.

## Canonical evaluated hypotheses

`CausalAnalysisResponse.hypotheses` is the single canonical bounded collection
of fully evaluated hypotheses. The previous code built this collection in
memory and then truncated it before persistence. AR-3 persists the complete
bounded collection produced from the AR-1 frontier after the existing
best-per-root behavior.

Each canonical hypothesis continues to own its existing identity, causal
score, relevance-derived chain, TC-4 ledger, and AR-2 support gate. Projections
contain only deterministic hypothesis IDs and lightweight membership audit;
they do not duplicate hypotheses or evidence ledgers.

## Diagnostic projection

The diagnostic projection answers:

> What looked most suspicious under the existing heuristic ordering?

It is ordered by the existing causal score. Exact score ties are resolved by
stable root event ID, target event ID, and hypothesis ID so projection results
do not depend on insertion or database order. The existing `max_hypotheses`
value remains the diagnostic limit and is applied after diagnostic ordering.

Unsupported hypotheses are permitted in this projection. The existing
`top_hypothesis` remains the first diagnostic hypothesis for compatibility.
AR-3 does not promote an evidence-supported candidate to diagnostic Top1.

`diagnostic_hypothesis_ids` stores the ordered references.

## Supported causal projection

The supported projection answers:

> Which evaluated causal hypotheses can Topo defend under AR-2?

Its deterministic order is:

1. take the one canonical bounded evaluated set;
2. retain only hypotheses whose current AR-2 gate state is
   `supported_under_current_model`;
3. preserve the existing causal score order and deterministic tie-break;
4. apply the supported projection limit.

The existing `max_hypotheses` value is reused as an independently applied
supported limit. Its numeric value remains 5 by default. An unsupported
hypothesis consumes no supported capacity.

`supported_hypothesis_ids` stores the ordered references. Supported Top1 is
the first ID and supported Top3 is the first three IDs. Consumers can resolve
those references against the canonical `hypotheses` collection.

## Cap semantics

AR-3 does not increase a cap. Before and after AR-3, the configured default is
5. The repair separates two applications of that value:

- diagnostic limit: first five hypotheses in diagnostic causal order;
- supported limit: first five AR-2-qualified hypotheses in causal order.

The canonical evaluated collection is bounded upstream by AR-1 and is not a
display or supported-output cap. In the measured case it contains six items
because AR-1 deliberately preserves one exact-lineage candidate outside the
ordinary Top-5.

When more than five evaluated hypotheses pass AR-2, the highest-ranked five
supported hypotheses are retained. Remaining supported hypotheses are audited
as `supported_projection_cap_reached`. This legitimate supported-cap overflow
is distinct from eviction by unsupported hypotheses.

## Safe abstention

If no evaluated hypothesis passes AR-2, `supported_hypothesis_ids` is empty.
Diagnostic hypotheses remain available, but none is promoted as a supported
cause. There is no score fallback, threshold bypass, or best-available cause.

## Projection audit

New analyses persist:

- `projection_policy_version`;
- ordered `diagnostic_hypothesis_ids`;
- ordered `supported_hypothesis_ids`;
- one lightweight audit row per canonical hypothesis;
- an analysis-level projection summary.

Each audit row records inclusion, projection rank, and reason for both
projections. Reasons distinguish diagnostic-cap exclusion, AR-2 gate failure,
and legitimate supported-cap overflow.

The summary records both limits and counts, including:

- evaluated hypothesis count;
- diagnostic projection count;
- support-qualified hypothesis count;
- supported projection count;
- supported-cap excluded count;
- `projection_dropped_supported_count`.

`projection_dropped_supported_count` is permanently constrained to zero. It
represents support-qualified hypotheses lost for a reason other than legitimate
supported-cap overflow. Unsupported hypotheses never increment it.

## Persistence and identity

Projection metadata is stored inside the existing immutable causal-analysis
JSON payload. No database table or migration is required. The projection
policy version participates in the causal analysis fingerprint, so a
post-AR-3 computation cannot reuse a pre-AR-3 immutable analysis identity when
its observable supported conclusions differ.

Historical payloads have no projection policy or projection metadata. The new
fields are nullable/default-compatible. Readback leaves them null or empty and
does not reconstruct, rewrite, or reinterpret historical projection truth.

## Measured count-50 behavior

For five higher-scoring temporal controls and one lower-scoring exact-lineage
source candidate:

- canonical evaluated hypotheses: six;
- diagnostic projection: the five controls;
- diagnostic `top_hypothesis`: the highest-scoring control;
- supported projection: the source candidate;
- supported Top1: the source candidate;
- `projection_dropped_supported_count`: zero.

Raw rank 51, scores, AR-1 membership, AR-2 decisions, relevance output, and
TC-4 ledgers remain unchanged.

## Non-goals and frozen behavior

AR-3 does not change candidate discovery, raw ordering, the `13c-causal-v1`
score formula, confidence calibration, AR-1, AR-2, causal relevance, TC-4,
SC-2, SC-3, SC-4, the 180-minute temporal path, incident behavior, runtime
evidence, topology, or provider integrations. It does not use an LLM,
embeddings, fuzzy matching, evaluator labels, or scenario-specific identities.

Before the V1 API/UI contract freezes, naming should be reviewed so the legacy
diagnostic `top_hypothesis` cannot be confused with a future explicit
`supported_top_hypothesis`. AR-3 intentionally does not perform that rename.
