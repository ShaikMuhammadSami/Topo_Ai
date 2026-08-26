# Evidence-Gated Supported-Hypothesis Classification v1

Status: AR-2 product policy implemented; frozen LINEAGE-2A matrix not rerun.

Accepted foundation commit recorded before implementation:
`68cea672f4b67d8933870289fb72e885212a4677`.

Policy version: `causal-support-gate-v1`.

## Purpose

AR-2 repairs `FALSE_SUPPORTED_DISTRACTOR`. The measured distractor had a high
heuristic score and three supporting TC-4 claims (`runtime_failure`,
`source_change`, and `temporal_precedence`), but its identity was unresolved and
it had no incident-time topology path. The former TC-5 derivation treated zero
contradicting and zero missing ledger items as sufficient for support. It did
not consult causal relevance or candidate-specific linkage.

Temporal precedence is necessary context, not causal relevance. A runtime
failure establishes that an incident occurred; it does not establish that a
particular candidate caused that failure.

## Pipeline position

The support gate is a classification layer over durable product evidence:

```text
candidate selection and AR-1 evaluation frontier
    -> causal-relevance-v2
    -> unchanged TC-4 evidence ledger
    -> causal-support-gate-v1
    -> TC-5 evidence state/completeness
    -> supported-hypothesis filtering
```

It does not discover candidates, traverse the graph, generate claims, or alter
scores.

## Evidence roles

AR-2 classifies existing TC-4 claim types by their role in support gating.
No TC-4 claim type was added.

### Incident-level evidence

- `runtime_failure`

This establishes the operational symptom independently of a candidate.

### Candidate-context evidence

- `source_change`
- `temporal_precedence`

These establish that a candidate exists and its temporal position. They justify
investigation but cannot satisfy candidate linkage.

### Candidate-linkage-capable evidence

- `identity_resolution`
- `entity_linkage`
- `topology_path`
- `relationship_provenance`
- `artifact_provenance`
- `event_lineage`

A linkage-capable claim contributes only when it is supporting, belongs to the
current hypothesis, references the current candidate event, and—when it carries
a snapshot ID—uses the same snapshot as that hypothesis ledger. Claim type
alone is not sufficient.

## Relevance gate

The centralized relevance predicate accepts only the success states already
emitted by the frozen relevance policy:

- `direct` relevance with `direct_entity` semantics and a topology-native
  identity;
- `semantic_path` relevance over an accepted semantic path and a
  topology-native identity; or
- `direct`/`semantic_path` relevance resolved through a valid
  `exact_immutable_lineage_anchor` whose source change is the candidate.

The topology path state must be `supported`, the affected identity and selected
path entities must exist, and the resolution basis must be explicit.

The following do not pass:

- `identity_unresolved`;
- `no_supported_path`;
- `ambiguous`;
- `unsupported_unknown` or structural-only path semantics;
- unresolved resolution basis;
- unsupported topology path state; and
- missing/conflicting exact-lineage anchor state.

Unknown or unresolved is not contradiction. It means the evidence is
insufficient to assert support.

## Candidate-linkage gate

After relevance succeeds, at least one supporting, candidate-bound linkage
claim must exist in the unchanged TC-4 ledger. Incident-level and
candidate-context claims cannot substitute for this requirement.

The gate does not require every linkage claim type. It does not require source
lineage for topology-native changes. It also does not reject a source candidate
merely because `candidate_entity_id` is null.

## Legitimate zero-hop behavior

A topology-native candidate whose entity is the affected entity remains valid
with a zero-hop `direct_entity` relevance result. The gate does not require
`path_hops > 0`; the candidate-bound entity linkage provides the causal-link
evidence.

## Exact-lineage source behavior

A source-domain candidate may retain `candidate_entity_id = null`. It remains
supportable when `causal-relevance-v2` resolves a valid exact immutable artifact
anchor and the TC-4 ledger contains candidate-bound linkage evidence for the
accepted incident-time path. The accepted LINEAGE-1 topology component remains
`0.85`, and the relevance bridge remains score-neutral.

## Topology-native behavior

A legitimate topology-native candidate needs no immutable source lineage. An
exact entity link plus a supported direct or semantic incident-time path can
satisfy both gates.

## Support-state precedence

For new analyses, `causal-support-gate-v1` produces these categorical outcomes:

1. existing contradiction plus missing evidence -> `contested_with_gaps`;
2. existing contradiction -> `contested`;
3. existing expected-but-missing evidence -> `incomplete`;
4. either AR-2 gate unsatisfied ->
   `insufficient_candidate_specific_evidence`;
5. both gates satisfied and no contradiction/missing evidence ->
   `supported_under_current_model`.

AR-2 never converts unresolved evidence into contradiction and never fabricates
a missing TC-4 claim. Missing remains legal only where TC-4 already recorded an
expectation basis.

## Evidence completeness

The TC-4 ledger stays immutable. A ledger may remain internally complete for
the facts it observed while causal support is incomplete. Therefore a gate
failure produces `partial` causal evidence completeness without changing the
ledger's supporting/contradicting/missing counts.

`complete_for_current_model` requires no missing expected evidence and both
AR-2 gates to be satisfied. Contradiction remains separately visible through
the evidence state.

## Safe abstention and ranking surfaces

The persisted hypothesis list and `top_hypothesis` retain the existing
score-ranked diagnostic projection for compatibility. Supported Top1/Top3 are
the ordered subset whose TC-5 `evidence_state` is
`supported_under_current_model`.

If every high-scoring candidate fails AR-2, that supported subset is empty. No
candidate is promoted as “best available” support. A rejected candidate may
retain its raw rank and numerical score for diagnosis without being labeled
supported.

## Score independence

The support classifier accepts no score or confidence input. It does not add a
threshold, bonus, probability, or coefficient. `13c-causal-v1`, TC-5 heuristic
confidence semantics, raw rank, tie behavior, AR-1 frontier membership, and the
final five-hypothesis cap are unchanged.

## Durable audit and versioning

New immutable analyses persist:

- `support_policy_version = causal-support-gate-v1`;
- relevance gate state and reason;
- candidate-linkage gate state and reason;
- candidate-bound linkage claim IDs and claim types;
- incident-level and candidate-context claim IDs;
- categorical support state and reason; and
- causal evidence completeness.

The support policy version participates in the deterministic analysis
fingerprint, so a post-AR-2 analysis cannot reuse a pre-AR-2 analysis ID.

Historical payloads load with null support policy/audit fields. Persisted legacy
confidence semantics are retained on readback and are not silently
reclassified. An unknown policy is rejected when new classification or missing
confidence semantics would require interpreting it.

## Explicit non-goals

AR-2 does not change:

- candidate discovery, Path A, SC-2 admission, or lineage age handling;
- SC-3 image identity;
- `causal-relevance-v2`, topology traversal, anchors, or bridge score;
- TC-4 claim generation, claim enum, evidence IDs, or stance semantics;
- candidate/final score coefficients or confidence calibration;
- `causal-evaluation-budget-v1` or ordinary Top-5;
- the final five-hypothesis cap;
- incident, topology, runtime, agent, frontend, workflow, or evaluator code; or
- the frozen LINEAGE-2A harness and baselines.

No LLM, embeddings, fuzzy matching, provider lookup, current-topology fallback,
or evaluation truth enters this policy.
