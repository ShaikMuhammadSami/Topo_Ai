# TopoAI Blast Impact Propagation v1

Status: active product policy  
Policy version: `blast-impact-v1`

This contract is separate from TC-2 relationship truth. TC-2 explains why a
directed edge exists; this policy decides whether incident impact may cross
that edge in a particular semantic state. It does not modify relationship
direction or provenance.

## Product meaning

Blast radius is the bounded set of entities for which Topo has defensible
incident-time impact evidence. It is not the set of graph nodes reachable
within a hop count. The policy recognizes:

- `direct_failure`: the incident's affected entity with durable failure evidence.
- `observed_co_failure`: another entity with a correlated pinned signal or
  explicit structured failure state in the same immediate ownership group.
- `ownership_rollup`: reverse traversal of `owner -> owned` solely to attribute
  the failed object to its ReplicaSet, Deployment, or other owner.
- `operational_impact`: directional propagation from a failed dependency to a
  dependent.
- `aggregate_impact`: impact established only after a group evaluator proves
  loss of serving capacity.
- `structural_context`: useful topology context that never enters the affected set.
- `unknown_unproven`: evidence is insufficient, so no impact is claimed.

The machine-readable contract is
[`impact-propagation-v1.json`](impact-propagation-v1.json). A backend drift test
requires every active TC-2 predicate to have one explicit entry and compares
the executable registry with that contract.

## Historical evidence boundary

The product loads only `incident.topology_snapshot_id`. Correlated failure
signals are consumed only when they reference that same immutable snapshot.
Pod health and Service target coverage are read only from that snapshot. The
implementation never queries latest topology, live Kubernetes, current Pods,
or current EndpointSlices.

Later topology and recovery observations therefore cannot change the blast
result for an older incident.

## Kubernetes health semantics

Pod health uses structured snapshot fields:

- Ready: `ready=true` and phase is `Running` (or absent for legacy data).
- Failed: phase is `Failed`/`Unknown`, or a structured container waiting or
  termination reason is one of the explicit failure reasons supported by v1.
- Unknown: every other state, including `ready=false` without a supported
  failure reason.

Unknown never becomes failed.

## Service aggregate evaluator

`kubernetes_service_backend_availability_v1` applies only to a
`KubernetesService -> KubernetesPod` `selects`/`routes_to` candidate. The
target universe is the complete set of pinned `selects` relationships. A
`routes_to` edge alone is not accepted as a complete denominator.

The evaluator records:

- selected target count and IDs;
- Ready/serving target count and IDs;
- failed/unavailable target count and IDs;
- unknown target count and IDs;
- the pinned snapshot and target relationship IDs.

The Service is aggregate-impacted only when the selected universe is nonempty,
every target is classified, no Ready target remains, and every selected target
is explicitly failed/unavailable. One Ready target excludes the Service.
Unknown coverage or health also excludes it and produces an additive warning.

An impacted Service does not fan back out through `selects` or `routes_to`.

## State-controlled traversal

Traversal is deterministic, bounded to five edges, and keyed by entity plus
semantic state. Direct/co-failure state may roll up through `owns`, enter a
supported dependency direction, or trigger the aggregate evaluator.
Ownership-rollup state may only continue upward through `owns`; it cannot fan
out to healthy children through `owns` or `runs`. Aggregate/operational state
may continue only through explicitly supported dependency policies.

When several valid paths reach an entity, the selected path preference is:
direct failure, observed co-failure, ownership roll-up, aggregate impact, then
operational impact. Predicate priority and stable relationship/entity IDs break
ties, so relationship serialization order cannot change the result.

## Predicate summary

| Predicate | BR-1 impact behavior |
|---|---|
| `contains` | Structural only; never propagates. |
| `owns` | Reverse ownership roll-up only. |
| `selects`, `routes_to` | Conditional reverse Kubernetes Service aggregate evaluation. |
| `depends_on`, `calls`, `uses`, `resolves_to`, `attached_to` | Reverse dependency impact. |
| `exposes`, `runs` | Forward impact; ownership-rollup state cannot use `runs`. |
| `produces`, `protects`, `triggers` | Unsupported/non-propagating in v1. |

Unknown predicates have no fallback and never propagate.

## Scores and API

The legacy distance score remains `1.0, 0.85, 0.65, 0.45, 0.25`. It is a
deterministic prioritization heuristic, not a probability and not TC-5 causal
confidence. The API remains backward compatible and adds policy version,
semantic state, evidence IDs, selected relationship IDs/directions, aggregate
evidence, and warnings.

## Known limitations

- V1 has one aggregate evaluator: Kubernetes Service backend availability.
- Target-set completeness requires pinned `selects` edges.
- Runtime health outside Kubernetes Pods remains predicate-driven rather than
  provider-specific aggregate reasoning.
- Pinned failure state can add a co-failed Pod only when it shares an immediate
  owner with a direct/correlated failure; healthy and unknown siblings remain
  excluded.
- The policy does not estimate request percentages, customer count, or
  probability of impact.
