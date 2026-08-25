# Pod Requested-vs-Runtime Image Identity v1

Status: SC-3 product contract

Version: `kubernetes-container-image-identity-v1`

## Why this contract exists

LINEAGE-1G measured `immutable_image_identity_incomplete`. The Deployment edge
retained its requested repository context, while the Pod edge was constructed
from `containerStatuses[].image` and its runtime `imageID`. The first semantic
loss occurred in `KubernetesCollector.collect`: Pod `spec.containers[].image`
was not collected and `status.containerStatuses[].image` occupied the legacy
`image` field. Container-image graph construction then allowed `imageID` to
replace the requested digest.

SC-3 repairs that boundary. It does not change causal policy.

## Semantic roles

For each regular Kubernetes container, Topo stores three observations:

| Role | Source | Meaning |
|---|---|---|
| Requested image | `pod.spec.containers[].image` | Kubernetes' authoritative requested image |
| Runtime status image | `pod.status.containerStatuses[].image` | Diagnostic runtime status value |
| Runtime image ID | `pod.status.containerStatuses[].imageID` | Runtime identity, including its scheme when supplied |

Each observation retains the bounded raw value, semantic role, exact source
field, syntactically parsed registry/repository, tag, digest, scheme, capture
state, and reference kind. A raw reference is limited to 2,048 characters
before storage. Malformed or oversized data is not eligible as immutable
identity.

The implementation is deterministic and local. It performs no registry,
provider, container-runtime, Git, evaluator, embedding, LLM, or fuzzy lookup.

## Requested artifact authority

Only an exact requested regular-container reference of the form
`repository@sha256:<64 hex characters>` establishes the SC-3 v1 requested
immutable artifact. The repository and digest remain together in the
normalized reference. The requested value is never replaced by either runtime
field.

A tag-only request preserves repository and tag, but fabricates no digest. A
repository-qualified runtime `imageID` remains runtime evidence; it does not
make that tag-only request eligible for SC-2 exact immutable admission.

`status.image` and `imageID` may carry an OCI index, platform child-manifest,
configuration digest, or another runtime-specific identity. SC-3 records their
syntax and provenance but does not infer which OCI layer they denote. It never
asserts that a requested index digest equals a different runtime digest.

## Container joining and ambiguity

Regular spec and status containers are joined by exact container name, never
array position. Status order therefore has no effect. Sidecars remain isolated
from application containers.

- Missing status: requested identity remains available and the join is
  `runtime_status_missing`.
- Missing spec: runtime observations may be retained, but requested identity is
  absent and no requested artifact edge is created.
- Duplicate exact status name: runtime fields are not selected; candidate
  observations are retained under `runtime_status_ambiguous`.
- Duplicate exact spec name: no requested identity is selected and the join is
  `spec_ambiguous`.

SC-3 covers regular containers only. It does not combine regular, init, or
ephemeral container families.

## Topology representation

No new graph entity family or database table is introduced. The versioned
observation is additive structured JSON on the existing Kubernetes entity's
`containers` property and on its existing `uses` relationship.

An exact requested repository and digest resolves through the existing
`canonical_container_image_identity` function and therefore reuses the
canonical `ContainerImage`. Deployment and Pod requests for the same exact
immutable reference point to the same artifact. A differing runtime diagnostic
digest does not switch that relationship or create a competing artifact.

TC-1's accepted canonical ContainerImage identity is digest-based. Consequently
the same digest seen with distinct explicit repositories can reuse the artifact
entity, but the two repository claims remain separate relationship evidence.
SC-2's repository intersection still fails closed; SC-3 does not infer registry
aliasing or repository equivalence.

Each SC-3 `uses` relationship includes:

- the existing `container_image_reference` and `container_image_digest`
  references required by SC-2, both derived only from the requested field;
- typed requested-image, runtime-status-image, and runtime-image-ID references;
- the exact container name, source fields, join state, structured observation,
  resolution method, and resolution basis.

Multiple containers using one image retain separate container-scoped edge IDs.
Numeric relationship confidence is not added; identity evidence is not a
probability or causal claim.

## Historical behavior

Graph snapshots already persist entity and relationship properties as JSON.
The SC-3 observation therefore survives the provider observation → normalized
topology → snapshot persistence → fresh-session readback path without a schema
migration. SC-2 continues to use the incident-pinned snapshot; latest topology
is neither required nor substituted.

Older snapshots still load without rewriting. A legacy `containers[].image`
value remains legacy input to the v1 image graph linker. Absence of the SC-3
contract never fabricates requested/runtime distinctions that were not
captured.

## Truth-contract interactions

- TC-1: exact deterministic canonical identity remains unchanged; no basename
  or similarity matching is introduced.
- TC-2: provider source fields and semantic roles are explicit in relationship
  provenance; runtime observations cannot masquerade as H3 provider evidence.
- TC-3: observation, incident, activation, and source effective times are not
  rewritten.
- SC-2: `causal-candidate-admission-v2`, exact immutable requirement,
  multi-container behavior, budgets, deduplication, and source-age admission
  remain unchanged.

The 180-minute ordinary path, candidate scores, ranking, causal-relevance-v1,
TC-4 claims, incident lifecycle, and runtime exit-code behavior are frozen.

## Explicit non-goals

SC-3 does not:

- establish index → platform manifest → image config relationships;
- claim arbitrary runtime digest membership in a requested index;
- promote runtime status to provider artifact identity;
- make tag-only workloads sufficient for exact lineage;
- expand init or ephemeral container collection;
- add image observation/manifest/config graph nodes;
- change the Topo Agent inventory contract;
- change SC-2 or downstream causal reasoning; or
- rerun LINEAGE-1.

