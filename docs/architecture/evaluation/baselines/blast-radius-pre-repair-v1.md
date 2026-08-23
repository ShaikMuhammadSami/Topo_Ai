# Blast Radius Pre-Repair Baseline v1

This is the BR-0 measurement record captured on 2026-08-23 against Docker
Desktop Kubernetes v1.34.3. It is deliberately pre-repair. No conclusion in
this document changes product traversal, TC-1 through TC-5, RCA ranking, or
incident behavior.

## 1. Current blast algorithm factual audit

- Customer entrypoint: `GET /api/v1/incidents/{incident_id}/blast-radius`.
- The service loads the incident and its `topology_snapshot_id`, loads that
  immutable snapshot, and resolves the incident affected entity within it. It
  does not fall back to latest topology.
- Traversal is breadth-first from the affected entity with `MAX_DEPTH = 5`.
  Nodes are marked visited when popped. Multiple queued paths can reach the
  same node; the first popped path wins.
- Every relationship is considered. If the current node is either the declared
  source or target, the opposite endpoint is enqueued. Consequently all edges,
  including directed edges, are operationally traversed in both directions.
- No predicate allow/deny policy exists. `contains`, `owns`, `selects`,
  `routes_to`, and any other relationship in the snapshot receive the same
  connectivity treatment.
- Distance labels are `direct` at 0, `dependent` at 1, `indirect` at 2, and
  `potential` at 3 or greater. Impact scores are 1.0, 0.85, 0.65, 0.45, then
  0.25. A second fixed risk score is adjusted by distance.
- Returned dependency paths contain entity IDs only. Each affected entity has
  the final relationship predicate, but the response does not directly expose
  relationship IDs or per-hop directions. BR-0 enriches those paths from the
  incident-pinned snapshot without changing the product response.
- There is no scope filter inside traversal beyond the contents of the pinned
  graph. Runtime health, alternate healthy Service targets, aggregate endpoint
  availability, edge provenance, and entity kind do not participate in
  propagation or scoring.

## 2. Scenarios executed

Four permanent real-Kubernetes cases were executed against isolated backend
databases and agent homes:

| Scenario | Run ID | Provider condition |
|---|---:|---|
| Sentinel D | `ce2142ef` | bad-image Pod plus independent healthy workload |
| blast-01 | `5bdf25d0` | containment-only isolation |
| blast-02 | `5918b0b8` | one failed and one Ready selected Pod |
| blast-03 | `9ef532be` | two failed selected Pods, zero Ready endpoints |

Each incident referenced an incident-time snapshot. Evaluation read the
existing blast API and enriched paths only from that same pinned snapshot.

## 3. Sentinel D reproduction

`evaluation/manifests/sentinel-d.json` remained at frozen Git blob
`e7e2a8f4e2cde066bee209191ec27304a41193f7`.

Provider truth was established. The rerun reproduced the original blast
signature exactly: TP 3, FP 3, FN 0, precision 0.50, recall 1.00. The victim
Service was reached by reverse traversal of `selects`; the independent
Deployment and Service were reached by `contains:reverse` from the failed Pod
to Namespace followed by `contains:forward`. Overall EVAL status remained
`FAIL`, as expected for a preserved defect.

The rerun also retained pre-existing RCA evaluation failures. BR-0 records but
does not repair or tune those failures.

## 4. Structural containment scenario

blast-01 used a Recreate Deployment with one real `ErrImagePull`/
`ImagePullBackOff` Pod and no Service. A separate Deployment, Pod, and Service
remained Ready; the healthy Service had at least one Ready EndpointSlice
target. Namespace membership was classified as structural context.

Topo returned all three required failure/ownership aliases but also returned
the structural Namespace and all three healthy aliases. Result: TP 3, FP 4,
FN 0, precision 0.4286, recall 1.00, overall `FAIL`.

All four declared false positives traversed `contains`. Representative path:

```text
failed Pod
  -- contains:reverse / relationship:ee58db637b80bda77cfe193b --> Namespace
  -- contains:forward / relationship:b09675bcd8e3ec2807bd10bd --> healthy Deployment
```

This isolates structural containment as sufficient for false propagation in
the current implementation.

## 5. Partial backend failure / healthy Service scenario

blast-02 created one Deployment with two replicas and one selecting Service.
The Pod template included a liveness probe backed by Pod-scoped `emptyDir`.
After the healthy baseline, the harness placed a failure flag in exactly one
Pod. Provider truth recorded:

- failed Pod UID `25f315c0-64e2-49a5-b56c-ebaad1f6eb3f`,
  `CrashLoopBackOff`, Ready=false;
- healthy sibling UID `49f35990-ab28-48ef-813a-168457d1f65d`, Ready=true;
- Service UID `8c8bb001-1c9a-43d0-9877-2fe442fa6c53`, selector
  `app=partial-backend`;
- EndpointSlice UID `91ddf5ca-a011-4339-8c78-b13ac5b43b64`, with the failed
  target Ready=false and healthy target Ready=true;
- Ready endpoint count 1.

The Service and healthy sibling were independently classified unaffected.
Topo returned both plus the structural Namespace. Result: TP 3, FP 3, FN 0,
precision 0.50, recall 1.00, overall `FAIL`.

The Service false-positive path was the direct reverse of
`relationship:3005f9e97d1e7868ce9498a3` (`selects`). The healthy sibling path
was `contains:reverse > contains:forward`. Static connectivity did not encode
the remaining Ready backend.

## 6. Complete backend failure / impacted Service scenario

blast-03 created a two-replica Recreate Deployment and selecting Service, plus
an unrelated healthy Deployment, Pod, and Service. A bad image made both new
backend Pods unavailable. Provider truth recorded both Pods Ready=false with
`ErrImagePull`, a valid Pod → ReplicaSet → Deployment owner chain, and
EndpointSlice UID `6017a66c-b5ec-45c4-8239-51dfa3c09483` with both targets
Ready=false. Ready endpoint count was 0. The unrelated Pod remained Ready and
its Service retained one Ready endpoint.

Here Service impact was real. Topo included all five required aliases: two
failed Pods, ReplicaSet, Deployment, and Service. It also included the
structural Namespace and all three unrelated aliases. Result: TP 5, FP 4,
FN 0, precision 0.5556, recall 1.00, overall `FAIL`.

The genuinely impacted Service was reached through `routes_to:reverse`. Every
declared false positive was reached through `contains`.

## 7. Per-scenario TP / FP / FN / precision / recall

| Scenario | Provider affected | Explicitly unaffected | Topo blast count | TP | FP | FN | Precision | Recall | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Sentinel D | 3 | 3 | 16 | 3 | 3 | 0 | 0.5000 | 1.0000 | FAIL |
| blast-01 | 3 | 4 | 13 | 3 | 4 | 0 | 0.4286 | 1.0000 | FAIL |
| blast-02 | 3 | 3 | 11 | 3 | 3 | 0 | 0.5000 | 1.0000 | FAIL |
| blast-03 | 5 | 4 | 16 | 5 | 4 | 0 | 0.5556 | 1.0000 | FAIL |

Counts use permanent manifest aliases. `Topo blast count` is the complete raw
API count, which includes graph entities outside each manifest's bounded
truth set. This four-case sample is **NOT STATISTICALLY MEANINGFUL** and must
not be reported as marketing accuracy.

## 8. False-positive path inventory

The diagnostic predicate totals below count hop occurrences in attributed FP
paths, not unique false-positive entities.

| Scenario | False-positive alias | Observed path pattern | Relationship IDs |
|---|---|---|---|
| Sentinel D | victim_service | `selects:reverse` | `relationship:24bf4b4f54b5b114ef43251d` |
| Sentinel D | unaffected_deployment | `contains:reverse > contains:forward` | `a6f4eb… > 880def…` |
| Sentinel D | unaffected_service | `contains:reverse > contains:forward` | `a6f4eb… > f78a0a…` |
| blast-01 | scenario_namespace | `contains:reverse` | `ee58db…` |
| blast-01 | healthy_deployment | `contains:reverse > contains:forward` | `ee58db… > b09675…` |
| blast-01 | healthy_pod | `contains:reverse > contains:forward` | `ee58db… > eef763…` |
| blast-01 | healthy_service | `contains:reverse > contains:forward` | `ee58db… > 1e46f0…` |
| blast-02 | scenario_namespace | `contains:reverse` | `805a5d…` |
| blast-02 | healthy_pod | `contains:reverse > contains:forward` | `805a5d… > 4534bd…` |
| blast-02 | root_service | `selects:reverse` | `relationship:3005f9e97d1e7868ce9498a3` |
| blast-03 | scenario_namespace | `contains:reverse` | `d1ca23…` |
| blast-03 | unrelated_deployment | `contains:reverse > contains:forward` | `d1ca23… > 5eb23e…` |
| blast-03 | unrelated_pod | `contains:reverse > contains:forward` | `d1ca23… > 35f55a…` |
| blast-03 | unrelated_service | `contains:reverse > contains:forward` | `d1ca23… > e35737…` |

Hop-occurrence totals were: Sentinel D `contains=4, selects=1`; blast-01
`contains=7`; blast-02 `contains=3, selects=1`; blast-03 `contains=7`.
Complete relationship IDs, entity IDs, directions, and TC-2 provenance remain
in the ignored run artifacts.

## 9. Predicate/direction observation matrix

| Predicate | Observed traversal | Scenario | Truth result | Observation |
|---|---|---|---|---|
| `contains` | Pod → Namespace (`reverse`) | all four | false impact | structural container itself was returned |
| `contains` | Pod → Namespace → unrelated member (`reverse`, `forward`) | all four | false impact | spread to healthy siblings/services/controllers |
| `selects` | Pod → Service (`reverse`) | Sentinel D, blast-02 | false impact | Service still had Ready capacity |
| `routes_to` | Pod → Service (`reverse`) | blast-03 | correct impact | all selected backends unavailable, zero Ready endpoints |
| `owns` | Pod → ReplicaSet (`reverse`) | all four | useful ownership roll-up | controller attribution was included |
| `contains` | Pod → Namespace → Deployment | all four | set result coincides with roll-up, path semantics wrong/ambiguous | shortest winning path to Deployment was structural, not ownership |

This matrix reports observed current behavior. It is not a BR-1 policy.

## 10. Ownership-rollup observations

Sentinel D and all three new manifests explicitly classify the failed Pod as
`direct_failure` and its ReplicaSet/Deployment as `ownership_rollup`. This
means “attribute the failed runtime instance to its owning workload,” not
“every controller process is independently degraded” and not downstream
failure propagation.

Current traversal reliably returned the ReplicaSet and Deployment, so it has
useful roll-up behavior at the set level. The ReplicaSet path used
`owns:reverse`. The Deployment path often won through
`contains:reverse > contains:forward`, however, because visited-on-pop BFS and
uniform edge treatment allow an equally short structural route. Thus the set
can be correct while the explanatory path is semantically poor.

## 11. Static-vs-conditional semantic conclusion

**Conclusion B — some relationships require conditional / aggregate
semantics.**

blast-02 and blast-03 intentionally used nearly the same Deployment/Service/
Pod graph. In blast-02, one selected backend failed while one remained Ready
and the Service retained one Ready endpoint; Service impact was false. In
blast-03, all selected backends failed and the Service had zero Ready
endpoints; Service impact was true. Current connectivity included the Service
in both cases.

Direction and predicate awareness are necessary to stop containment
overreach, but they are insufficient to distinguish these two Service states.
The evidence supports an aggregate condition involving selected targets and
Ready targets. BR-0 does not implement that condition.

## 12. Known environment limitations

- One Docker Desktop cluster (control plane plus one worker) was measured.
- Scenarios use Kubernetes provider truth and do not generate application
  traffic or validate user-visible HTTP availability.
- Invalid registry images establish container unavailability; the partial
  scenario uses a persistent liveness failure flag in a Pod-local `emptyDir`.
- The manifest-bounded TP/FP/FN sets do not classify every entity returned by
  the raw blast API.
- A relationship path contains entity IDs in product output. Exact hop
  relationship selection is reconstructed deterministically from the pinned
  snapshot; alternative parallel edges are retained when present.
- Overall EVAL status includes existing RCA/abstention assertions outside the
  BR-0 blast focus. Those failures remain evidence and were not tuned.

## 13. Inputs for BR-1 repair design

Evidence to carry into architecture review, without prescribing code:

1. Namespace `contains` is structural context and must not alone imply
   operational failure propagation.
2. Declared edge direction must be considered; uniform reverse traversal is
   not semantically safe.
3. Failure attribution/ownership roll-up is a separate concept from downstream
   operational impact.
4. Service impact needs selected-target aggregate health evidence; one failed
   target is not enough when Ready alternatives remain.
5. Path selection should preserve semantically relevant relationships instead
   of allowing a structural equal-length path to win silently.
6. Incident-pinned topology remains the sole graph source for historical
   evaluation and repair verification.
7. The four manifests and their provider assertions become permanent
   regression cases for BR-1; expected failures must not be erased or rewritten
   from future Topo output.
