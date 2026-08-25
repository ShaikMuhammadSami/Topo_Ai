# SC-3 Pod Requested-vs-Runtime Image Identity Repair

Date: 2026-08-26

Contract: `kubernetes-container-image-identity-v1`

## Before

The accepted LINEAGE-1G checkpoint recorded:

| Dimension | Result |
|---|---|
| SC-1 gate | PASS |
| SC-2 admission policy | `causal-candidate-admission-v2` |
| Candidate count | `0` |
| Lineage admission state | `incomplete` |
| Admission reason | `immutable_image_identity_incomplete` |
| Final verdict | `MISSING` |
| First divergence | `CAUSAL_CANDIDATE_MISSING` |

The Deployment requested-image relationship preserved repository/artifact
context. Pod collection did not preserve `pod.spec.containers[].image`; its
relationship instead collapsed requested and runtime-status semantics around a
runtime digest. The strict SC-2 repository/immutable-artifact consolidation
therefore had no valid identity intersection and correctly failed closed.

## SC-3 repair target

The Pod/container observation now preserves, independently:

- exact requested raw reference, repository, tag, and digest from `pod.spec`;
- diagnostic `containerStatuses[].image` structure;
- runtime `containerStatuses[].imageID` structure and scheme; and
- exact-name join state and source provenance.

When the incident-time Pod specification requests an exact immutable
`repository@sha256` artifact, the existing canonical `ContainerImage` and Pod
`uses` edge are built from that requested identity. Runtime diagnostic digests
remain attached separately and cannot replace it. The same structured fields
survive topology snapshot persistence and readback.

Deterministic product tests show that Deployment and Pod exact requested
identities can now agree in the SC-2 incident path even when runtime status
reports a different digest. These tests validate the repair contract, not the
real frozen scenario.

## Preserved boundaries

SC-3 does not weaken SC-2, make tag-only identity sufficient, equate an OCI
index with a platform/config/runtime digest, modify the 180-minute ordinary
path, change scoring or ranking, create causal evidence, change lifecycle
behavior, or repair missing runtime exit-code evidence. It introduces no graph
entity family, database migration, provider call, evaluator change, workflow
change, frontend change, or agent change.

## Measurement status

SC-3 does **not** claim that SC-2 now succeeds in the real LINEAGE path. The
unchanged preserved LINEAGE-1 scenario must be rerun only after review and
merge. That remeasurement will determine whether
`immutable_image_identity_incomplete`, and therefore
`CAUSAL_CANDIDATE_MISSING`, disappear at the previously measured first
divergence.
