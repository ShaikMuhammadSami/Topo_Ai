# Blast Radius Post-Repair Baseline v1

Date: 2026-08-23  
Product policy: `blast-impact-v1`  
Harness: the accepted EVAL-1 adversarial harness  
Command: `python -m evaluation run-blast --timeout 420`

This is the measured BR-1 result on the same four permanent BR-0 manifests.
No manifest was changed. Four scenarios are **NOT STATISTICALLY MEANINGFUL**;
they are durable adversarial regression cases, not a population estimate.

## Summary

| Scenario | Before TP/FP/FN | After TP/FP/FN | Precision | Recall |
|---|---:|---:|---:|---:|
| Sentinel D | 3 / 3 / 0 | 3 / 0 / 0 | 0.5000 -> 1.0000 | 1.0000 -> 1.0000 |
| blast-01 | 3 / 4 / 0 | 3 / 0 / 0 | 0.4286 -> 1.0000 | 1.0000 -> 1.0000 |
| blast-02 | 3 / 3 / 0 | 3 / 0 / 0 | 0.5000 -> 1.0000 | 1.0000 -> 1.0000 |
| blast-03 | 5 / 4 / 0 | 5 / 0 / 0 | 0.5556 -> 1.0000 | 1.0000 -> 1.0000 |

Across these fixed cases, false-positive entity paths containing `contains`
fell from 12 to 0. Healthy-Service false positives fell from 2 to 0, and the
explicit healthy-sibling false positive in blast-02 fell from 1 to 0. Recall
was preserved in every scenario.

## Sentinel D

- Pre-repair: TP=3, FP=3, FN=0; precision=0.5000, recall=1.0000.
- Post-repair run: `76ee6d2d`.
- Incident: `incident:docker-desktop:topo-eval-d-76ee6d2d:workload-victim-app:75f163bd77f7a8447f2d3efa`.
- Pinned snapshot: `snapshot:agent:69bd60da50c4223c6c61eb10babfbe3e`.
- Post-repair: TP=3, FP=0, FN=0; precision=1.0000, recall=1.0000.
- Before false paths: Namespace containment reached unrelated Deployment and
  Service; reverse `selects` also marked the rolling Service despite retained
  healthy capacity.
- After semantic paths: failed Pod (`direct_failure`) -> ReplicaSet
  (`ownership_rollup`) -> Deployment (`ownership_rollup`), both via reverse
  `owns`.
- Aggregate state: the Service was excluded because a pinned Ready backend
  remained.

Sentinel D still fails its pre-existing RCA top-1/top-3 assertions. BR-1 did
not and must not change causal ranking; both blast assertions pass.

## blast-01

- Pre-repair: TP=3, FP=4, FN=0; precision=0.4286, recall=1.0000.
- Post-repair run: `f154102b`.
- Incident: `incident:docker-desktop:topo-eval-blast-01-f154102b:workload-failing-app:c190cbb451ab07ee899fcbef`.
- Pinned snapshot: `snapshot:agent:4de90daa79e49dcda21fbbeae1573266`.
- Post-repair: TP=3, FP=0, FN=0; precision=1.0000, recall=1.0000.
- Before false paths: reverse containment entered Namespace, then fanned out
  to healthy Deployment, Pod, and Service.
- After semantic paths: failed Pod -> ReplicaSet -> Deployment using only
  reverse `owns`; Namespace and healthy workload are absent.

The scenario's separate RCA assertions remain failed and were not changed.

## blast-02 — partial backend failure

- Pre-repair: TP=3, FP=3, FN=0; precision=0.5000, recall=1.0000.
- Post-repair run: `abc639c9`.
- Incident: `incident:docker-desktop:topo-eval-blast-02-abc639c9:workload-partial-backend:cfc0d22f90def6be1260238b`.
- Pinned snapshot: `snapshot:agent:9bcdf6e37e4c916e694353b76a596a75`.
- Post-repair: TP=3, FP=0, FN=0; precision=1.0000, recall=1.0000.
- Before false paths: containment reached the healthy sibling and Namespace;
  reverse `selects` marked the Service.
- After semantic paths: incident-signaled Pod -> ReplicaSet -> Deployment.
- Pinned aggregate state: the Service target universe contained two Pods. The
  incident signal supplied direct failure evidence for the root target, while
  the other selected Pod was structured `ready=true`, `phase=Running` in the
  pinned snapshot. At least one serving backend remained, so the Service and
  healthy sibling were excluded.

The scenario's unrelated abstention assertion remains failed. Both blast
assertions pass.

## blast-03 — complete backend loss

- Pre-repair: TP=5, FP=4, FN=0; precision=0.5556, recall=1.0000.
- Post-repair run: `448a4507`.
- Incident: `incident:docker-desktop:topo-eval-blast-03-448a4507:workload-failed-backend:fcd7224058f45ab177a4ec5a`.
- Pinned snapshot: `snapshot:agent:74dcd4c9c884f40d29a3f79c3c217cc0`.
- Post-repair: TP=5, FP=0, FN=0; precision=1.0000, recall=1.0000.
- Before false paths: Namespace containment fanned out to unrelated workload,
  Pod, Service, and Namespace context.
- After semantic paths: root failed Pod (`direct_failure`), second explicitly
  failed Pod (`observed_co_failure`), ReplicaSet and Deployment (reverse
  `owns`), and Service (`aggregate_impact`).
- Pinned aggregate state: selected targets=2, Ready/serving=0,
  failed/unavailable=2, unknown=0. Both Pods carried structured
  `ErrImagePull` failure state. The Service path uses reverse `routes_to`, and
  its aggregate evidence cites the pinned `selects` target universe.

The scenario's separate RCA assertions remain failed. Both blast assertions
pass.

## Before/after path behavior

Pre-repair traversal treated every edge as undirected. A first-seen structural
path could win, so `Pod <- contains Namespace -> contains sibling` created
unbounded semantic fan-out within the five-hop cap. Reverse `selects` also
treated one failed target as proof of Service failure.

Post-repair traversal is stateful and predicate-aware:

- `contains` is non-propagating structural context;
- reverse `owns` is attribution-only and cannot fan out;
- co-failed siblings require correlated/pinned failure evidence;
- `selects`/`routes_to` invoke a pinned Service aggregate evaluator;
- dependency-like edges follow one explicit impact direction;
- paths preserve relationship IDs, traversal direction, origin, and source;
- unknown predicates and unknown aggregate health abstain.

No post-repair false-positive path contains `contains`. The numeric impact
score remains the prior distance heuristic and is not a probability.
