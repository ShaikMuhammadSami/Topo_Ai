# TopoAI Semantic Causal Relevance and Path Policy v1

Status: active product policy

Policy version: `causal-relevance-v1`

## Purpose and boundary

This policy answers whether a `causal-candidate-v1` primary candidate has a
defensible operational path to this incident's affected entity. It consumes
the immutable TC-2 relationships in the incident-pinned topology. It does not
change identity, relationship truth, time semantics, the TC-4 schema, TC-5
confidence meaning, raw incident-change scores, candidate eligibility, blast
radius, or the `13c-causal-v1` coefficients.

The machine-readable contract is
[`causal-relevance-policy-v1.json`](./causal-relevance-policy-v1.json). The
executable registry is `app.services.causal_relevance_policy`. A drift test
requires an explicit entry for all 14 active TC-2 predicates; an unknown or
future predicate has no fallback traversal.

## Measured pre-repair defect

The accepted CC-1 Sentinel artifacts prove a shared mechanism. The old 13C
adjacency inserted both directions for every relationship and selected the
first bounded BFS path. Sentinel A therefore chose Deployment → Namespace →
Pod over the real Deployment → ReplicaSet → Pod owner chain. Sentinel B gave
both the victim and healthy distractor Deployment the same distance-two path
through their shared Namespace. The distractor then received false
`topology_path` and `relationship_provenance` support.

The distractor also received `entity_linkage` and `identity_resolution`
support. Those two facts were independently true: the change really was
linked to, and deterministically resolved as, the distractor Deployment. CR-1
does not falsify them. Candidate identity is not causal relevance.

## Canonical orientation and semantic classes

Every path is stored in causal source → incident effect order. For example:

```text
Deployment --owns/forward--> ReplicaSet --owns/forward--> Pod
```

The semantic classes, in deterministic preference order, are direct entity,
control ownership, artifact lineage, dependency impact, runtime hosting, and
other explicitly supported mixed semantics. Structural context and
unsupported/unknown edges never enter causal adjacency.

Path selection applies semantic validity first, semantic class priority next,
then hop count, then stable relationship/entity IDs. Relationship serialization
order is irrelevant. Search is bounded by the existing
`CausalAnalysisRequest.max_topology_hops` and terminates cycles by retaining
the best state per entity and semantic-class set.

## Predicate policy

| Predicate | TC-2 direction | Causal traversal | Class | V1 status |
|---|---|---|---|---|
| `contains` | scope → member | none | structural context | structural only |
| `owns` | owner → owned | forward | control ownership | supported |
| `produces` | source/run → artifact | forward | artifact lineage | supported |
| `triggers` | revision → workflow | forward | artifact lineage | supported |
| `uses` | workload → artifact | reverse | artifact lineage | supported |
| `depends_on` | dependent → dependency | reverse | dependency impact | supported |
| `calls` | caller → destination | reverse | dependency impact | supported |
| `runs` | host/owner → running object | forward | runtime hosting | supported |
| `exposes` | resource → endpoint | forward | runtime hosting | supported |
| `attached_to` | attached object → target | none | runtime hosting | unsupported |
| `selects` | Service → selected Pod | none | unsupported/unknown | conditional, disabled |
| `routes_to` | routing source → destination | none | unsupported/unknown | conditional, disabled |
| `protects` | intended control → protected object | none | unsupported/unknown | unsupported |
| `resolves_to` | name/service → target | none | unsupported/unknown | unsupported |

`runs` is forward-only. That preserves the direct collector's legacy
ReplicaSet → Pod representation and stable host → runtime observations without
allowing a Pod to reverse to an owner and fan down to healthy siblings.
`attached_to` remains disabled because its frozen TC-2 domains span node,
network, and provider attachment meanings. `protects` remains disabled because
TC-2 documents an AWS direction inconsistency. Static `selects`/`routes_to`
edges remain disabled; causal RCA does not duplicate BR-1 aggregate health
semantics.

## Topology component and evidence

The existing distance mapping remains `1.00, 0.85, 0.65, 0.45, 0.25` for
zero, one, two, three, and four-or-more supported hops. No supported path gives
`0.0`. The existing formula still multiplies this component by 25; there is no
candidate bonus, distractor penalty, weight change, or kind-specific hack.

Each selected primary candidate gets a persisted audit containing status,
source and effect entities, semantic class, exact entity/relationship path,
predicates, TC-2 traversal directions, origins, source systems, hop count,
topology component, and reason. The analysis fingerprint includes the policy
version, so an old generation is never silently reused or rewritten.

TC-4 consumes the exact selected relationship IDs. A supported path can emit
`topology_path` and relationship-provenance support. When a durable candidate
link and affected entity exist but no supported semantic path exists, TC-4
emits its existing missing topology-path evidence. It does not emit a
contradiction. Independently true source-change, temporal, identity, and
candidate-to-own-entity linkage facts remain truthful.

## Historical correctness and limitations

The policy receives only the snapshot already selected by 13C under TC-3:
the explicit incident pin, or the existing safe at-or-before selection when a
legacy incident has no pin. It never loads latest topology, current
Kubernetes, or BR-1 runtime evaluators. A later topology snapshot cannot alter
a persisted historical analysis.

- A path establishes relevant operational connectivity, not proof of root
  cause.
- No path means missing topology support; incomplete inventory is possible.
- Artifact lineage inherits mutable-tag and inferred-producer limitations.
- `attached_to`, `selects`, `routes_to`, `protects`, and `resolves_to` require
  measured scenarios before causal traversal can be enabled.
- Mixed supported paths rank below pure, measured semantic classes; no numeric
  ranking coefficient changes.
