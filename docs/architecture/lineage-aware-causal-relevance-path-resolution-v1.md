# Lineage-Aware Causal Relevance Path Resolution v1

Date: 2026-08-26

Product policy: `causal-relevance-v2`

Topology path semantics: `causal-relevance-v1` (unchanged)

## Purpose

LINEAGE-1I measured `CAUSAL_RELEVANCE_PATH_MISSING` after SC-1 source
identity, SC-3 requested image identity, and SC-2 exact immutable-lineage
admission all passed. The admitted source event correctly had
`candidate_entity_id=null`: a source/change-domain event is not a topology
entity. The failure occurred because v1 could start relevance traversal only
from a candidate topology entity and did not consume SC-2's persisted immutable
artifact bridge.

SC-4 adds exact immutable-lineage anchor resolution. It does not add a second
RCA engine, graph entity family, relationship predicate, ranking rule, or
causal-evidence claim type.

## Three separate questions

- Lineage asks where an artifact came from.
- Causal relevance asks whether a candidate can be defensibly connected to the
  affected runtime scope.
- Causality asks whether the candidate actually caused the incident.

An exact lineage bridge supplies a legitimate topology starting anchor. It is
not proof of causality and contributes no score.

## Two identity domains

SC-2 persists a provider/change-domain segment:

```text
canonical source change
    -> source revision
    -> producer run
    -> exact immutable ContainerImage
```

The incident-pinned topology supplies the runtime segment:

```text
exact immutable ContainerImage
    -> workload
    -> runtime descendants
    -> affected entity
```

The canonical immutable `ContainerImage` identity is the cross-domain anchor.
Provider evidence remains provider evidence; topology relationship IDs remain
topology evidence. They are serialized in separate audit fields.

## Policy versioning and compatibility

`causal-relevance-v2` means:

```text
unchanged causal-relevance-v1 topology path semantics
    + exact immutable-lineage relevance-anchor resolution
```

New analyses persist v2 in the analysis fingerprint, response, and per-candidate
audit. The predicate allow-list, directions, semantic priorities, bounded path
search, path ordering, hop score, and topology-component mapping remain the v1
contract.

Historical analyses with v1 audits load without v2 anchor fields. Missing v2
fields remain absent or empty and are never reconstructed or backfilled.
Unknown policy versions fail safely.

## Mode A: topology-native candidate

When the candidate already has an exact entity ID in the incident-pinned
snapshot, v2 calls the existing topology path evaluator with that entity. No
SC-2 metadata is required. Candidate identity, selected relationship order,
semantic classification, hop count, and score are behaviorally identical to
v1.

The audit records `resolution_basis=topology_entity`.

## Mode B: exact immutable-lineage anchor

Mode B is eligible only when persisted candidate context records:

- `causal-candidate-admission-v2`;
- admission state `admitted`;
- admission reason and basis `exact_immutable_lineage`;
- a canonical source ID matching the candidate;
- a complete lineage path with deterministic evidence;
- an explicit immutable image entity ID, kind, and full digest; and
- provider evidence references.

The anchor must exist by exact canonical ID in the supplied incident-pinned
snapshot. Its kind must be `ContainerImage`, and its immutable digest and
external identity must exactly match the persisted SC-2 path. There is no
repository-only, tag-only, name-only, digest-prefix, fuzzy, or global digest
lookup.

For a source candidate, `candidate_entity_id` remains null. The image is stored
separately as `relevance_anchor_entity_id`; the source candidate is never
relabeled as an image.

## One topology path evaluator

Both modes call `evaluate_topology_path`. Anchor resolution occurs before this
call and does not alter traversal. The accepted relationship behavior remains:

| Predicate | Traversal |
|---|---|
| `uses` | reverse, artifact to explicit consumer |
| `owns` | forward, owner to owned runtime object |
| `runs` | forward, host/controller to runtime object |
| `contains` | excluded from causal propagation |

All other predicates retain the frozen v1 allow-list behavior. No reverse
relationship is persisted to make traversal work.

## Score and ranking semantics

The bridge score is explicitly zero. Multiple bridge paths or anchors never
add score. Once an exact anchor is available, the unchanged topology evaluator
may produce a non-zero topology component from its selected path. That is an
existing input becoming available, not a new bonus.

The existing RCA formula, candidate score, temporal score, kind prior, event
lineage component, Top-N selection, and deterministic rank ordering remain
unchanged. SC-4 does not force the lineage candidate to Top1.

## Multiple paths and anchors

Multiple lineage paths claiming the same exact anchor are deduplicated. Their
path IDs, run IDs, evidence references, and provider evidence IDs are retained
in deterministic sorted order. The topology path is evaluated once, so score
does not multiply.

Only distinct anchors explicitly persisted by SC-2 for this incident-scoped
candidate are evaluated. There is no global produced-image expansion. If more
than one admitted anchor produces a supported topology path, canonical audit
selection uses the existing path semantic order, then hop count, relationship
IDs, entity path, and stable anchor identity. Scores are not summed.

## Fail-closed behavior

Relevance remains unresolved or unsupported when:

- admission policy, state, reason, or basis is ineligible;
- candidate and persisted lineage IDs disagree;
- bridge paths or required provider evidence are missing;
- the exact anchor is absent from the pinned snapshot;
- anchor kind, entity identity, or immutable digest conflicts;
- duplicate records claim conflicting identities for one anchor; or
- the bridge is exact but the existing topology evaluator finds no supported
  path to the affected entity.

An anchor that exists only in latest/current topology is never used. A source
candidate admitted only through the ordinary temporal path is not rescued by
provider history.

## Truth-contract boundaries

- **TC-1:** Exact canonical IDs and full immutable digests only; no fuzzy
  identity resolution.
- **TC-2:** Provider provenance and incident-pinned topology relationships are
  separately attributed.
- **TC-3:** Source effective time, provider time, incident boundary, topology
  pin time, and candidate time are unchanged.
- **TC-4:** Relevance audit metadata is not a causal claim. No claim type is
  added; existing evidence generation may use only existing claim types.

## Persistence

SC-2 lineage paths now add the already-known exact `image_entity_id` and
`image_entity_kind`. The fields are optional on the model so historical SC-2
payloads remain readable. New v2 relevance audits persist the resolution basis,
selected anchor, bridge evidence, all anchor evaluations, and the selected
topology path in the existing serialized causal-analysis payload. No table or
database migration is required.

## Explicit non-goals

SC-4 does not change candidate admission, the 180-minute Path A, timestamps,
ranking weights, candidate ordering, TC-4 claim types, incident lifecycle,
topology pinning, SC-3 requested/runtime image identity, runtime exit-code
capture, or Deployment health timing. It does not add source/change topology
entities, synthetic bridge entities, reverse graph edges, provider calls,
current-state lookup, LLMs, embeddings, or fuzzy matching.

