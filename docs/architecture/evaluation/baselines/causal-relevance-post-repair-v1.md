# Causal relevance post-repair baseline v1

Date: 2026-08-24

Candidate policy: `causal-candidate-v1` (unchanged)

Causal relevance policy: `causal-relevance-v1`

Numeric composition: `13c-causal-v1` (unchanged)

Evaluation harness/manifests: `eval-1.v1` / unchanged Sentinel A, B, and C

This is an engineering measurement, not marketing. **NOT STATISTICALLY
MEANINGFUL.** Three adversarial scenarios cannot establish an accuracy
percentage.

## Summary

| Scenario | Run | Top-1 | Top-3 | Semantic path | Harness status |
|---|---|---:|---:|---|---|
| Sentinel A | `bed4f5c0` | PASS | PASS | `owns/forward → owns/forward` | PASS |
| Sentinel B | `76319f23` | PASS | PASS | victim: `owns/forward → owns/forward`; distractor: `no_supported_path` | FAIL only because the unchanged evaluator counts two independently true identity facts as forbidden causal support |
| Sentinel C | `4ecba848` | PASS | PASS | `owns/forward → owns/forward` | PASS |

All runs retained `score_type=heuristic_ranking`,
`calibration_status=not_calibrated`, and `calibrated_probability=null`.
Post-BR-1 blast precision/recall remained 1.0/1.0 in all three runs.

## Sentinel A

Before CR-1 (`d081ede1`), the correct Deployment mutation was already Top-1
after CC-1, but the undirected generic BFS selected:

```text
Deployment
  <- contains/undirected interpretation - Namespace
  -> contains/undirected interpretation - Pod
```

The candidate had raw rank 10, raw score 55.2, eligible rank 1, 13C score
63.33, and a distance-two topology component of 0.65. The harness failed the
required owner path.

After CR-1 (`bed4f5c0`), the naturally observed candidate was raw rank 11,
raw score 55.2, eligible rank 1, and remained Top-1/Top-3 with score 63.33.
The topology component remains the unchanged distance-two value 0.65, but its
evidence is now:

```text
Deployment 439c3cad…
  -- owns/forward --> ReplicaSet e3885a54…
  -- owns/forward --> Pod 98b63fbf…
```

No `contains` relationship enters the authoritative chain or ledger. Required
path completeness passed and ledger-backed path precision increased from 0.0
in the CC-1 post-repair measurement to 1.0. Candidate score and numeric 13C
composition did not change.

## Sentinel B

Provider truth again established two genuine primary Deployment mutations:
the healthy distractor and the independent bad-image victim.

### Before CR-1 (`854757d2`)

| Component | Victim | Distractor |
|---|---:|---:|
| Raw candidate rank / score | 13 / 55.2 | 14 / 55.2 |
| Candidate contribution (`×0.40`) | 22.08 | 22.08 |
| Generic path | Deployment → Namespace → victim Pod | Deployment → Namespace → victim Pod |
| Topology component / contribution | 0.65 / 16.25 | 0.65 / 16.25 |
| Temporal contribution | 15.00 | 15.00 |
| Change-kind contribution | 10.00 | 10.00 |
| Lineage contribution | 0.00 | 0.00 |
| Final 13C score / rank | 63.33 / 2 | 63.33 / 1 |

Stable event-ID order broke the identical score tie in favor of the
distractor. Its supporting ledger claim types were `entity_linkage`,
`identity_resolution`, `relationship_provenance` (two hops),
`runtime_failure`, `source_change`, `temporal_precedence`, and
`topology_path` (two hops). The evaluator counted exactly four claims that
intersected the distractor entity: `entity_linkage`, `identity_resolution`,
`relationship_provenance`, and `topology_path`.

### After CR-1 (`76319f23`)

The new run's stable IDs naturally gave the victim eligible rank 1 and the
distractor eligible rank 2, while their raw ranks were 16 and 15 respectively.
That incidental ordering is not needed for correctness: the permanent
integrated product test deliberately orders the distractor first and the
victim still wins by the same 16.25 topology contribution.

| Component | Victim | Distractor |
|---|---:|---:|
| Raw candidate score | 55.2 | 55.2 |
| Candidate contribution (`×0.40`) | 22.08 | 22.08 |
| Relevance status | `semantic_path` | `no_supported_path` |
| Semantic path | Deployment → ReplicaSet → Pod | none |
| Predicates/directions | `owns/forward`, `owns/forward` | none |
| Topology component / contribution | 0.65 / 16.25 | 0.00 / 0.00 |
| Temporal contribution | 15.00 | 15.00 |
| Change-kind contribution | 10.00 | 10.00 |
| Lineage contribution | 0.00 | 0.00 |
| Final 13C score / rank | 63.33 / 1 | 47.08 / 2 |

Victim Top-1 and Top-3 assertions passed. The victim path is:

```text
Deployment 858103ac…
  -- owns/forward --> ReplicaSet a3bacf34…
  -- owns/forward --> Pod 3c4d6d40…
```

The distractor has no supported path in pinned snapshot
`snapshot:agent:3ef3ab681b5b73c582e931000824b32c`. Its post-repair ledger is:

- supporting: `entity_linkage`, `identity_resolution`, `runtime_failure`,
  `source_change`, `temporal_precedence`;
- missing: one `topology_path` with an explicit expectation basis;
- contradicting: none.

The two false causal/path claim classes, `topology_path` and
`relationship_provenance`, disappeared completely. `entity_linkage` and
`identity_resolution` remain because they truthfully say the candidate change
is linked to and resolves as the distractor Deployment—not that the
Deployment caused the victim Pod failure. `source_change` and
`temporal_precedence` are also independently true and do not carry the
distractor entity ID in the current ledger.

The unchanged EVAL-1 evaluator still classifies `entity_linkage` and
`identity_resolution` as critical causal support whenever their entity IDs
intersect a manifest non-cause. It therefore reports
`explicit_non_cause_supported_count=2` and
`unsupported_critical_claim_count=2`, making the overall run FAIL even though
root-cause Top-1, Top-3, required path, forbidden path, blast, and TC-5 all
pass. Falsifying those two identity facts would violate TC-1/TC-4. This is a
measured evaluation-semantics issue left for architecture review, not repaired
in CR-1.

## Sentinel C

Sentinel C (`4ecba848`) preserved CC-1. The real Deployment mutation was raw
rank 10, raw score 55.2, `observed_resource_mutation`, `primary_eligible`,
eligible rank 1, and Top-1/Top-3 at 63.33. Seven observed derived topology
events remained `derived_topology_consequence/supporting_only`; none seeded a
hypothesis. `KNOWN_FAILURE_REPRODUCED=false` by the manifest's intended
meaning because the source mutation remains Top-1.

The authoritative path is now:

```text
Deployment 96d7cfe4…
  -- owns/forward --> ReplicaSet 1612eaae…
  -- owns/forward --> Pod 9b476f5a…
```

The unchanged topology component is 0.65, required path completeness and
path precision are 1.0, TC-5 remains uncalibrated/probability-null, and the
scenario passes.

## Measured conclusions and limitations

- The same generic undirected path mechanism caused Sentinel A's structural
  path and Sentinel B's false distractor topology relevance.
- `causal-relevance-v1` repairs both without changing candidate scores,
  candidate eligibility, or 13C coefficients.
- No supported path is recorded as missing topology evidence, not proof of a
  non-cause and not contradiction.
- The unchanged evaluator conflates true candidate identity/linkage with
  causal-path support for explicit non-causes; Sentinel B therefore remains a
  harness FAIL for two truth-preserving claims even though the measured
  product relevance defect is corrected.
- This tiny sample is **NOT STATISTICALLY MEANINGFUL** and supports no product
  accuracy percentage.
