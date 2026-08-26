# Evidence-Preserving Candidate Evaluation Budget v1

Policy version: `causal-evaluation-budget-v1`

## Purpose

AR-1 separates two concepts that were previously represented by the same
five-candidate collection:

- the ordinary raw Top-K shortlist; and
- the set of candidates permitted to receive causal relevance and evidence
  evaluation.

The LINEAGE-2A baseline proved that an exact immutable-lineage source mutation
could be admitted by `causal-candidate-admission-v2` yet be lost before
`causal-relevance-v2` when five higher-scoring distractors occupied the ordinary
shortlist. AR-1 repairs only that evaluation-opportunity loss. It does not make
the preserved candidate more likely to be supported or highly ranked.

## Pipeline audit and first divergence

The candidate pipeline is:

1. `analyze_incident_change_events()` discovers ordinary Path A records in the
   existing 180-minute window, scores them, sorts them, and caps discovery at
   its existing service limit.
2. `evaluate_lineage_candidate_admission()` may add one older canonical source
   change through exact incident-scoped immutable lineage (Path B).
3. `incident_change_analysis.py` deduplicates Path A and Path B by event ID and
   re-sorts the combined raw candidate list without changing scores.
4. `select_causal_candidates()` classifies the raw candidates and applies the
   existing hypothesis-candidate limit at
   `selected = eligible[:limit]`.
5. Before AR-1, `causal_rca.py` assigned only
   `candidate_selection.selected_candidates` to `candidates`. Consequently,
   relevance, TC-4 ledger generation, hypothesis construction, and supported
   ranking never saw an admitted exact-lineage candidate outside the ordinary
   five.

The root defect was therefore a semantic conflation: the raw presentation /
ordinary selection budget was also used as the evaluation budget.

Increasing the ordinary Top-K is not the repair: any larger fixed raw cap can
still be exhausted by enough higher-scoring controls, and globally enlarging it
would change ordinary candidate behavior and cost. The repair preserves the
distinct semantic class whose exact incident relevance was already proven.

## Policy

The v1 evaluation frontier is the deterministic set union:

```text
existing ordinary shortlist
        UNION
candidates already admitted by SC-2 with:
  policy = causal-candidate-admission-v2
  state = admitted
  reason = exact_immutable_lineage
  basis contains exact_immutable_lineage
  existing candidate-policy eligibility = primary_eligible or fallback_eligible
```

AR-1 consumes persisted candidate-admission state. It does not discover or
reconstruct lineage and performs no provider, registry, Git, image, topology,
or network lookup.

The existing candidate-policy eligibility remains authoritative. Preservation
does not revive supporting-only or ineligible records (for example, an event
explicitly marked `no_change`), so the established safe-abstention behavior is
unchanged.

Ordinary members retain the ordering returned by the existing candidate
policy. Evidence-preserved candidates outside that shortlist are ordered by
stable event ID. A candidate present through both bases occurs once and records
both bases in this fixed order:

1. `ordinary_raw_top_k`
2. `evidence_preserved_exact_immutable_lineage`

Candidates that satisfy neither basis retain raw audit visibility but do not
enter evaluation.

## Boundedness proof

SC-2 is already strictly bounded:

- provider build evidence is bounded by
  `MAX_PROVIDER_PATHS_PER_ARTIFACT = 32` and fails closed above that limit;
- source events for a revision are bounded by
  `MAX_SOURCE_EVENTS_PER_REVISION = 8` and fail closed above that limit;
- provider evidence must resolve to exactly one repository/revision tuple;
- source evidence must resolve to exactly one canonical source event; and
- `evaluate_lineage_candidate_admission()` returns either no admitted change or
  the one-element tuple `admitted=(admitted,)`.

Therefore the accepted AR-1 v1 maximum is:

```text
evaluation_frontier_max
  = ordinary shortlist limit (default 5)
  + SC-2 admitted exact-lineage maximum (1)
  - overlap (0 or 1)

default maximum = 6
```

AR-1 does not apply a second protected-candidate slice or introduce a new
truncation cap. The recorded `SC2_EXACT_LINEAGE_CANDIDATE_MAX = 1` documents the
existing upstream proof and is not used to truncate a collection.

## Raw rank, score, and ranking

AR-1 never mutates an `IncidentChangeCandidate` and adds no score. Raw score,
raw order, raw rank, risk, and existing tie behavior remain owned by the
existing change analysis and candidate-selection policy.

For the frozen LINEAGE-2A shapes, the evidence-preserved source mutation keeps
raw ranks 6, 11, 21, and 51 at distractor counts 5, 10, 20, and 50. It merely
receives an evaluation-frontier position after the five ordinary members.

The existing `13c-causal-v1` formula, `causal-relevance-v2`, TC-4 ledger,
TC-5 support classification, and final `max_hypotheses` output cap remain
unchanged. Evidence preservation is selection metadata, not causal evidence.
It cannot force Top1, Top3, support, or a hypothesis.

## Persisted audit contract

New `CausalAnalysisResponse` payloads add:

- `evaluation_policy_version`;
- `candidate_evaluation_audit`; and
- `evaluation_budget_audit`.

Each candidate evaluation audit records raw rank and score, evaluation
membership, selection bases, ordinary membership, evidence-preserved
membership, frontier position, exclusion reason, and policy version. The budget
summary records ordinary limit/count, preserved count, frontier size, state,
and reason.

The existing `candidate_selection_audit` retains its pre-AR-1 meaning and API
shape. In particular, `selected_for_hypothesis` continues to identify ordinary
candidate-policy selection; AR-1 evaluation membership is expressed only by
the new audit.

## Fingerprint and historical compatibility

`causal-evaluation-budget-v1` is included in the immutable causal-analysis
fingerprint. A new analysis therefore cannot reuse a pre-AR-1 analysis ID under
the old evaluation behavior.

No database migration is required because causal analyses persist a JSON
payload. Historical payloads without AR-1 fields load with:

- `evaluation_policy_version = null`;
- `candidate_evaluation_audit = []`; and
- `evaluation_budget_audit = null`.

Readback does not synthesize selection bases or rewrite historical payloads.
Unknown evaluation-budget versions are rejected by the policy builder.

## Frozen boundaries

AR-1 does not change:

- the 180-minute Path A lookback;
- SC-2 admission logic, traversal, budgets, deduplication, or age semantics;
- SC-3 Kubernetes/container image identity;
- SC-4 / `causal-relevance-v2`, including a zero lineage bridge score;
- TC-4 claim types or evidence-ledger semantics;
- TC-5 confidence or support classification;
- `13c-causal-v1` scoring coefficients;
- incident lifecycle, runtime evidence, deployment health, or graph traversal;
- evaluators, agents, frontend, or workflows; or
- the frozen secondary LINEAGE-2A temporal-distractor false-support finding.

The next measured action after AR-1 is a fresh LINEAGE-2B evaluation. It is not
part of this repair.
