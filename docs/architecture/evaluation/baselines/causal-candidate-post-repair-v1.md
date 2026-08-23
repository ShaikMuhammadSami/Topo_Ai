# Causal candidate post-repair baseline v1

Date: 2026-08-23

Candidate policy: `causal-candidate-v1`

Scoring algorithm: unchanged `13c-causal-v1`

Evaluation harness: unchanged `eval-1.v1`

This is an engineering measurement, not marketing. The same permanent Sentinel A/B/C manifests were rerun against real Docker Desktop Kubernetes after CC-1. The candidate taxonomy defect is corrected for A and C. Sentinel B exposes a separate relevance/tie defect between two genuinely primary Deployment mutations; CC-1 deliberately does not tune that defect.

**NOT STATISTICALLY MEANINGFUL.** Three adversarial runs cannot establish an accuracy percentage.

## Summary

| Scenario | Run | Causal Top-1 | Causal Top-3 | Derived relationship roots | Other measured result |
|---|---|---:|---:|---:|---|
| Sentinel A | `d081ede1` | PASS | PASS | none | overall harness FAIL only because the existing causal shortest path selected Namespace containment instead of the required owner chain |
| Sentinel B | `854757d2` | FAIL | PASS | none | healthy distractor and victim tied at 63.33; stable event ID placed distractor first; 4 forbidden supporting critical claims |
| Sentinel C | `35312cfe` | PASS | PASS | none | `KNOWN_FAILURE_REPRODUCED=false`; overall harness FAIL only on the same causal-path tie |

All three used `score_type=heuristic_ranking`, `calibration_status=not_calibrated`, and `calibrated_probability=null`. All three had post-BR-1 blast precision/recall 1.0/1.0. CC-1 did not modify blast behavior.

## Sentinel A — obvious bad image

Provider truth established Deployment `sentinel-a-app` as the receipted bad-image mutation and a new ReplicaSet/Pod chain ending in `ErrImagePull`.

### Before CC-1 (`da16e65f`)

| Rank | Event | Raw/13C result |
|---:|---|---|
| 1 | `selects relationship added` | raw incident-change 87.5; 13C 83.5 |
| 2 | `routes_to relationship added` | derived hypothesis |
| 3 | `owns relationship added` | derived hypothesis |
| — | Deployment configuration mutation | absent Top-3 |

### After CC-1 (`d081ede1`)

| Event | Raw rank | Raw score | Role | Eligibility | Eligible rank | 13C rank | 13C score |
|---|---:|---:|---|---|---:|---:|---:|
| `selects relationship added` | 1 | 87.5 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| `routes_to relationship added` | 2 | 87.5 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| `owns relationship added` | 3 | 84.8 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| `Deployment configuration changed` | 10 | 55.2 | `observed_resource_mutation` | `primary_eligible` | 1 | 1 | 63.33 |

Top-1 and Top-3 causal assertions passed. The leading evidence state was `supported_under_current_model`; TC-5 remained uncalibrated/probability-null. A structured Kubernetes `ScalingReplicaSet` event was retained as `derived_runtime_consequence/supporting_only`, so it no longer became the hypothesis root.

The unchanged evaluator still failed `required_path`: 13C's existing undirected shortest-path tie selected Deployment → Namespace → Pod rather than Deployment → ReplicaSet → Pod. That path-selection issue was newly exposed after the correct Deployment candidate reached 13C and was not repaired in CC-1.

## Sentinel B — attractive nearby non-cause

Provider truth established two real Deployment mutations: healthy `distractor-app` changed to a valid image, then independent `victim-app` changed to the bad image and produced the failing ReplicaSet/Pod. The distractor remained available and its Service retained a ready endpoint.

### Before CC-1 (`214925d1`)

Derived `selects`, `routes_to`, and `owns` events occupied Top-3. The victim mutation was absent. The distractor did not become Top-1 and received zero forbidden supporting critical claims only because no source Deployment mutation reached the five hypotheses.

### After CC-1 (`854757d2`)

| Event/entity | Raw rank | Raw score | Role | Eligibility | Eligible rank | 13C rank | 13C score |
|---|---:|---:|---|---|---:|---:|---:|
| leading derived `selects` | 1 | 87.5 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| second derived `selects/routes_to` | 2 | 87.5 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| derived `owns` | 3 | 84.8 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| victim Deployment mutation | 13 | 55.2 | `observed_resource_mutation` | `primary_eligible` | 2 | 2 | 63.33 |
| distractor Deployment mutation | 14 | 55.2 | `observed_resource_mutation` | `primary_eligible` | 1 | 1 | 63.33 |

Top-3 contained truth, but Top-1 failed. Both snapshot-derived Deployment mutations share the same checkpoint effective time, raw score, kind prior, and current 13C topology score. The required deterministic stable-ID tie-break placed the distractor first. Its hypothesis then received 4 supporting critical ledger claims, so the explicit non-cause assertion also failed. Both hypotheses reported `supported_under_current_model`; TC-5 remained uncalibrated/probability-null.

This is the exact distinct multiple-primary relevance problem anticipated by the CC-1 acceptance nuance. Candidate taxonomy cannot distinguish two genuinely primary mutations without additional evidence relevance. No numeric weight, temporal formula, topology formula, lineage formula, TC contract, or manifest was changed to force this scenario green.

The evaluator also failed the existing owner-path assertion because each Deployment candidate's undirected shortest path selected Namespace containment.

## Sentinel C — source mutation versus topology-diff noise

Provider truth established the Deployment image mutation as the source change, followed by ReplicaSet/Pod generation and `ErrImagePull`.

### Before CC-1 (`f1a448e9`)

| Event | Raw rank | Raw score | Role before policy | 13C rank | 13C score |
|---|---:|---:|---|---:|---:|
| `selects relationship added` | 1 | 87.5 | primary hypothesis seed | 1 | 83.5 |
| `routes_to relationship added` | 2 | 87.5 | primary hypothesis seed | 2 | 83.5 |
| `owns relationship added` | 3 | 84.8 | primary hypothesis seed | 3 | 80.42 |
| `Deployment configuration changed` | 11 | 55.2 | excluded | — | — |

`KNOWN_FAILURE_REPRODUCED=true`.

### After CC-1 (`35312cfe`)

| Event | Raw rank | Raw score | Role | Eligibility | Eligible rank | 13C rank | 13C score |
|---|---:|---:|---|---|---:|---:|---:|
| `selects relationship added` | 1 | 87.5 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| `routes_to relationship added` | 2 | 87.5 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| `owns relationship added` | 3 | 84.8 | `derived_topology_consequence` | `supporting_only` | — | — | — |
| `Deployment configuration changed` | 10 | 55.2 | `observed_resource_mutation` | `primary_eligible` | 1 | 1 | 63.33 |

The current run naturally produced one fewer preceding candidate than the original baseline, so the unchanged 55.2 mutation was raw rank 10 rather than 11. Its score was not changed. It became eligible rank 1 and 13C rank 1 only because all candidates were classified before the existing limit. Top-1 and Top-3 passed; the leading evidence state remained `supported_under_current_model`; `KNOWN_FAILURE_REPRODUCED=false`.

The only overall harness failure was the separately measured causal owner-path tie described under Sentinel A.

## Derived consequence retention

Every considered derived event remains in `candidate_selection_audit` with its durable event/change ID, raw rank, unchanged raw score, role, eligibility, structured reason, exclusion reason, policy version, and selection flag. It remains available beside change events and signals for audit/context. CC-1 does not manufacture TC-4 support merely because an event was excluded, and supporting-only events cannot seed or legacy-fallback into a root hypothesis.

## Measured conclusions

- The source-versus-derived eligibility defect is repaired in A and C without score tuning.
- All measured `selects`, `routes_to`, and `owns` consequences remain auditable and no longer seed hypotheses.
- Sentinel B establishes a separate source-mutation relevance/tie defect. It remains open by design.
- Correct Deployment hypotheses expose a separate existing causal path-selection tie through Namespace containment. It remains open by design.
- The sample is **NOT STATISTICALLY MEANINGFUL** and supports no product accuracy percentage.
