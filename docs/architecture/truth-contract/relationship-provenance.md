# TC-2 relationship semantics and edge provenance

Status: implemented relationship truth contract v1

Scope: the 14 relationship predicates constructed by TopoAI product code. TC-2 adds assertion provenance to new edges; it does not change causal ranking, blast-radius traversal, temporal semantics, the evidence ledger, connector breadth, or historical snapshot payloads.

## Truth rules

Every new product-generated edge records its subject, predicate and object in the existing `Relationship` fields and records how the assertion was established in `Relationship.provenance`:

| Origin | Exact meaning |
|---|---|
| `observed` | The source directly reported the relationship or runtime observation, such as a Tetragon dependency record, a provider run/head SHA association, or an EndpointSlice target reference. |
| `declared` | Authoritative source configuration explicitly declares the relationship, such as a Kubernetes ownerReference, node scheduling field, Ingress backend, ExternalName, Topo dependency annotation, or cloud attachment/reference. |
| `derived` | A deterministic linker combines strong source facts, such as exact Service selector/Pod-label matching or exact image-reference/digest resolution. |
| `inferred` | A bounded linker combines indirect hints and may be wrong, such as Git/CI image mapping or cloud-to-Kubernetes correlation. |

There is no active human edge-authoring path, so TC-2 does not advertise `user_asserted`. Historical confirmation is not an origin. `Relationship.historical_validation` is a separate optional compatibility field and TC-2 does not populate or automate it.

## Provenance contract

`Relationship.provenance` contains:

- `origin` — the assertion class above;
- `source_component` — the collector/linker module that created the edge;
- `source_references` — bounded structured references to real UIDs, owner references, selectors, annotations, provider resource IDs, build/run IDs, image digests, runtime dependency records, or graph endpoint IDs where no stronger reference exists;
- `linker_version` — the source-specific relationship algorithm version;
- `completeness` — `complete` or `partial` for new edges.

`Relationship.source_system`, `observed_at`, `evidence_ids`, and `properties` retain their existing roles. An `evidence_id` is stored only when the constructor actually creates an `Evidence` object. No placeholder evidence record is generated for agent/cloud/runtime constructors. A source reference is not an evidence-ledger record and never pretends to be one.

New constructors use these linker versions:

| Constructor family | Linker version |
|---|---|
| direct Kubernetes discovery | `kubernetes-collector-linker:v1` |
| agent Kubernetes inventory | `kubernetes-agent-inventory-linker:v1` |
| Kubernetes network enrichment | `kubernetes-network-linker:v1` |
| container image projection | `container-image-linker:v1` |
| GitHub repository/commit | `github-commit-linker:v1` |
| GitHub commit/image | `github-image-linker:v1` |
| GitHub Actions run/trigger/artifact | `github-actions-run-linker:v1`, `github-actions-trigger-linker:v1`, `github-actions-artifact-linker:v1` |
| AWS/Azure/GCP inventory | `aws-inventory-linker:v1`, `azure-inventory-linker:v1`, `gcp-inventory-linker:v1` |
| agent runtime inventory | `runtime-inventory-linker:v1` |
| Tetragon dependency overlay | `tetragon-network-linker:v1` |

Reference lists are deduplicated and sorted by canonical JSON, making serialization deterministic. Relationship identity remains the existing hash of subject ID, predicate and object ID. Observation time, evidence order, provenance content and linker version do not enter the relationship ID.

## Legacy behavior

Snapshots produced before TC-2 omit `provenance`, `confidence_semantics`, and `historical_validation`. Pydantic loads those edges with `provenance=null`; APIs and RCA report their provenance status as `legacy_unspecified`. Their old numeric confidence, when serialized, remains legacy data and is not reinterpreted or rewritten.

Topo does not update persisted `SnapshotRecord.payload_json`, incident pins, change records, or causal analyses merely to add TC-2 fields. A historical edge remains usable for graph traversal with an unknown origin.

## Confidence semantics

Relationship confidence is not a probability.

- New `observed`, `declared`, and `derived` edges store `confidence=null`.
- A new `inferred` edge may omit confidence when the linker has no meaningful computed score.
- GitHub/GitHub Actions image linkers retain their existing deterministic ranking scores and label them `heuristic_score`.
- Existing AWS/Azure/GCP cross-source correlations retain their existing 0.98/0.99 constants as explicitly labeled heuristic scores. They are not calibrated likelihoods and connector maturity is not promoted.
- Legacy edges can retain the historical default/constant `1.0`; because they have no TC-2 provenance it must not be presented as “100% true.”

The model rejects a numeric score on a new non-inferred edge and rejects an inferred numeric score that is not labeled `heuristic_score`. TC-2 does not alter RCA hypothesis confidence, causal weights, thresholds, ranking, or calibration.

## Before-state constructor matrix

This matrix was verified against every `Relationship(...)` constructor and local `add_relationship` helper before TC-2 edits.

| Constructor | Subject → predicate → object | Source input / exact evidence available before TC-2 | Actual class | Old confidence | Existing consumers/tests before TC-2 |
|---|---|---|---|---|---|
| `collectors/kubernetes_collector.py:collect` | Cluster/Namespace → `contains` → Namespace/resource | Kubernetes list results, cluster context, object UID, one real discovery Evidence ID | observed/declared inventory | default 1.0 | RCA, blast; no focused collector edge test |
| same | Deployment → `owns` → ReplicaSet | ReplicaSet `ownerReferences[].uid` | declared | default 1.0 | RCA, blast |
| same | ReplicaSet → `runs` → Pod | Pod ReplicaSet owner reference | declared (predicate is historical behavior) | default 1.0 | RCA, blast |
| same | Service → `selects` → Pod | Service selector plus exact Pod-label match | derived | default 1.0 | RCA, blast |
| `services/agent_snapshot_ingest.py:build_agent_snapshot` | cluster/namespace → `contains`; Deployment/ReplicaSet → `owns`; Pod → `attached_to` Node; Service → `selects`/`routes_to`; Ingress → `routes_to` Service | submitted inventory UID, owner UID, node name, selector/labels, Ingress backend, EndpointSlice target UID; no Evidence object | mixed declared/derived/observed | default 1.0 | continuous-lifecycle tests |
| `services/network_topology_enricher.py` | Service → `selects` Pod / `exposes` EndpointSlice / `resolves_to` DNS; Ingress/EndpointSlice → `routes_to`; Pod → `calls` endpoint / `depends_on` Service | Kubernetes API fields, labels, target UID, ExternalName, Ingress backend, Topo annotations; evidence IDs empty | mixed derived/declared/observed | default 1.0 | limited network tests |
| `services/container_image_graph.py` | Deployment/Pod → `uses` ContainerImage | requested reference, runtime image ID/digest, real generated Evidence ID | declared or derived | 1.0 exact / 0.80 reference constant | incident-briefing fixture coverage |
| `services/github_graph.py` | Repository → `contains` Commit; Commit → `produces` Image | provider repository ID, commit SHA, annotation/digest/SHA mapping, real Evidence ID | observed / inferred | 1.0 / computed candidate heuristic | no connector-specific golden test |
| `services/github_actions_graph.py` | Repository → `contains` Run; Commit → `triggers` Run; Run → `produces` Image | run ID, head SHA, revision/digest/workload hints, real Evidence ID | observed / inferred | 1.0 / 0.85–0.99 heuristic | no connector-specific golden test |
| `services/agent_cloud_enrichment.py` | AWS scopes/resources → `contains`, `attached_to`, `protects`, `routes_to`; AWS → `runs`/`routes_to` Kubernetes | account/region/ARN/resource ID, provider references, Kubernetes provider ID/LB hostname; evidence IDs empty | declared / inferred cross-source | default 1.0 / 0.99 constant | AWS enrichment tests |
| `services/agent_azure_enrichment.py` | Azure scopes/resources → `contains`, `attached_to`, `protects`, `exposes`, `routes_to`; Azure → `runs`/`routes_to` Kubernetes | full Azure resource IDs and nested provider references; Kubernetes provider ID/ingress; evidence IDs empty | declared / inferred cross-source | default 1.0 / 0.99 constant | Azure enrichment tests |
| `services/agent_gcp_enrichment.py` | GCP scopes/resources → `contains`, `attached_to`, `protects`, `routes_to`; GCP → `runs`/`routes_to` Kubernetes | full/self-link IDs and nested references; GCE provider ID/GKE labels/ingress; evidence IDs empty | declared / inferred cross-source | default 1.0 / 0.98–0.99 constant | GCP enrichment tests |
| `services/agent_runtime_enrichment.py` | Host → `contains` Process/Container; Container/Pod → `runs`; Container → `attached_to` network; Process/Host → `exposes`; Process/Host → `calls` endpoint | runtime inventory native IDs, PIDs, network IDs, socket tuple; evidence IDs empty | observed | default 1.0 | agent plugin tests, limited backend coverage |
| `services/runtime_snapshot_enrichment.py` | Pod/process source → `calls` RuntimeNetworkEndpoint | durable `RuntimeDependencyRecord`, sensor ID, observation count/window | observed | hard-coded 0.95 | Tetragon parser/storage coverage |
| `services/sample_topology.py` | sample `contains`, `runs`, `selects` | explicit sample definition only | declared/derived sample | default 1.0 | sample endpoint |

No GitLab, Jenkins, Azure DevOps or Terraform module constructs graph relationships today; they produce change evidence. TC-2 does not invent their graph hops.

## Active predicate direction matrix

| Predicate | Canonical forward meaning | Reverse traversal meaning | Dependency relevance | Impact relevance / current behavior |
|---|---|---|---|---|
| `contains` | scope/container → member | member belongs to scope | normally structural, not dependency | blast currently traverses both directions |
| `owns` | Kubernetes owner → owned object | object is owned by source | lineage, not request dependency | blast currently traverses both directions |
| `produces` | commit/run → artifact | artifact was attributed to producer | source-to-runtime provenance | blast currently traverses both directions |
| `triggers` | commit → workflow run | run was triggered from revision | source-to-runtime provenance | blast currently traverses both directions |
| `runs` | host/workload/owner → running object | object runs under source | hosting/lineage | blast currently traverses both directions |
| `selects` | Service → Pod selected by labels | Pod is selected by Service | request routing dependency | blast currently traverses both directions |
| `exposes` | resource → endpoint/listener | endpoint is exposed by resource | request reachability | blast currently traverses both directions |
| `routes_to` | routing source → destination | destination is reached from source | direct dependency | blast currently traverses both directions |
| `calls` | caller → destination endpoint | endpoint is called by source | direct dependency | blast currently traverses both directions |
| `depends_on` | dependent → dependency | source depends on target | direct dependency | blast currently traverses both directions |
| `uses` | workload → artifact | artifact is used by workload | source/runtime association | blast currently traverses both directions |
| `protects` | intended control → protected object | object is protected by control | security context | blast currently traverses both directions; an AWS direction inconsistency remains documented |
| `resolves_to` | service/name → resolved/declared target | target is named by source | reachability | blast currently traverses both directions |
| `attached_to` | attached object → attachment target | target hosts/attaches source | hosting/network context | blast currently traverses both directions |

Reverse traversal is not semantically equivalent for any active predicate. TC-2 deliberately leaves `blast_radius.py` and its undirected traversal unchanged; this matrix is input to a later policy block.

## Material topology versus provenance

Customer topology comparison includes aligned subject/object, predicate, `directed`, and relationship `properties`. It excludes ID representation, observation time, evidence order, source-system representation, confidence metadata, provenance, and later validation metadata.

Therefore enriching an existing edge with origin/source references/linker version produces no `relationship_updated`, normalized change, `ChangeRecord`, or topology `ChangeEvent`. A true add, removal, direction change, predicate change, endpoint change, or property change remains material. TC-2 does not create a separate provenance-change event ledger.

## RCA and historical correctness

The causal engine's graph distance and scoring code are unchanged. For every topology hop it now deterministically selects the matching relationship by stable relationship ID and embeds its type, direction, source, confidence semantics, provenance, and provenance status into the topology `CausalEvidenceItem.attributes`.

That lookup receives only the same incident-time `GraphSnapshot` already loaded for causal analysis. It does not query a repository, latest snapshot, live graph, or newer checkpoint. Legacy pinned edges expose `legacy_unspecified`; TC-2 edges expose their stored provenance. The briefing can carry this causal evidence without independently reconstructing edge truth.

## Source-to-runtime status

| Hop | Status after TC-2 | Truth boundary |
|---|---|---|
| Repository → Commit | implemented but unproven | GitHub API repository ID and commit SHA |
| Commit → CI/CD | implemented but unproven | GitHub Actions head SHA and run ID |
| CI/CD → Image | partial | bounded heuristic; digest/revision/run evidence where present |
| Image ← Deployment/Pod (`uses`) | partial | exact digest is derived; reference/tag-only use remains mutable |
| Deployment → ReplicaSet | proven for Kubernetes ownerReference path | declared owner UID |
| ReplicaSet → Pod | proven in agent `owns`; direct collector preserves historical `runs` predicate | declared owner UID |

Adding provenance does not raise connector maturity. There is still no universal registry attestation, Helm entity/hop, GitLab/Jenkins/Azure DevOps graph build entity, or committed real-provider golden chain.

## Known limitations

- Provenance references are bounded pointers, not the future append-only evidence ledger.
- New agent/cloud edges can be `partial` when a source supplies no stronger native reference than graph endpoints.
- Cloud API connector maturity remains partial and real authentication/pagination/rate-limit behavior is unproven.
- Cross-cloud/Kubernetes 0.98/0.99 values are inherited deterministic constants labeled as heuristic, not calibrated evidence.
- The active `protects` predicate has an AWS direction inconsistency preserved for a future explicit semantic migration.
- Runtime endpoints are observation/lifetime scoped; NAT, address reuse and incomplete workload mapping remain possible.
- Blast radius still ignores direction, origin, confidence and staleness.
- Historical ownership validity and bitemporal edge validity are outside TC-2.
- Unused enum predicates (`affects`, `deploys`, `derived_from`, `emits`, `observes`, `unknown`) are not falsely listed as active.
