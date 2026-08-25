# LINEAGE-1 Post-SC-2 Candidate Admission Baseline v1

Date: 2026-08-26

Branch: `evaluation/lineage-1-post-sc2-baseline-v1`

Accepted product commit: `1cd2a10f0e26eda15387ae4b37550fc717fd06d2`

Final LINEAGE-1G verdict: **MISSING**

First divergence: **`CAUSAL_CANDIDATE_MISSING`**

SC-2 gate: **FAIL**

## 1. Checkpoint purpose

This document permanently preserves the accepted LINEAGE-1G measurement before
repairing the runtime/requested-image identity boundary. It is a documentation
checkpoint only. It does not modify or reinterpret product code, evaluators,
causal policy, provider state, Kubernetes state, or the frozen experiment.

Before SC-2, the source mutation was correct and the immutable provenance chain
was structurally present, but the source event was outside the unchanged
180-minute ordinary lookback. The measured first divergence was
`CAUSAL_CANDIDATE_MISSING`.

## 2. LINEAGE-1G result

| Dimension | Accepted observation |
|---|---|
| Final verdict | `MISSING` |
| First divergence | `CAUSAL_CANDIDATE_MISSING` |
| SC-2 gate | `FAIL` |
| Candidate count | `0` |
| Exact source-candidate occurrence count | `0` |
| Admission policy | `causal-candidate-admission-v2` |
| Lineage admission state | `incomplete` |
| Lineage admission reason | `immutable_image_identity_incomplete` |

SC-2 did not fabricate or weaken admission. It failed closed because the
product could not consolidate the incident-time requested image identity with
runtime image identity strongly enough to establish the exact immutable
artifact required by Path B.

This is an identity-semantics defect immediately upstream of successful SC-2
admission. It is not justification to weaken SC-2.

## 3. Runtime and image identity observation

The Deployment/workload side preserved the requested registry/repository image
identity:

```text
ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval
```

The Pod/runtime-side relationship exposed a runtime/status identity represented
by:

```text
sha256:a339...
```

This value corresponds to a different OCI/runtime semantic than the requested
repository/image identity. The current admission consolidation found no valid
normalized identity intersection.

The following identifiers must not be silently treated as interchangeable:

- requested image reference;
- runtime status image;
- runtime image ID;
- OCI index;
- platform child manifest; and
- image configuration or runtime-status digest.

## 4. Independent runtime truth

| Dimension | Accepted observation |
|---|---|
| Deployment UID | `dc422a5a-fbac-4972-9616-0fcf46ee0711` |
| ReplicaSet UID | `4c753cff-eab5-4ec9-bfa0-ccfeae18bf3e` |
| Pod UID | `df4ea5fe-5f03-411c-b700-98f324cc63a7` |
| Exit code | `42` |
| Restart count | `>= 1` |
| BackOff | present |
| Termination reason | `Error` |
| Deployment state | `1` desired / `0` ready / `0` available |

## 5. Incident context

| Dimension | Accepted observation |
|---|---|
| Failure signal | `signal:kubernetes-event:docker-desktop:8c226a7b-ab6c-4080-bcf8-46c5bfb750e0` |
| Incident | `incident:docker-desktop:topo-eval-lineage-causal-32695735269:workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3` |
| Boundary | `2026-08-25T05:50:05Z` |
| Pinned snapshot | `snapshot:actions-enriched:20260825T055100Z:ed393256` |
| Affected Pod | `k8s:docker-desktop:pod:df4ea5fe-5f03-411c-b700-98f324cc63a7` |

## 6. Source context and SC-1 gate

| Dimension | Accepted observation |
|---|---|
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Source mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Source effective time | `2026-08-24T06:02:03Z` |
| Incident gap | `85682` seconds / `1428.0333` minutes / `23.8006` hours |
| Ordinary Path A lookback | `180` minutes |
| SC-1 gate | `PASS` |

## 7. Preserved provenance

LINEAGE-1G recorded **PASS** for:

- Repository -> Commit;
- Commit -> Actions;
- Actions -> Image;
- Deployment -> Image;
- Deployment -> ReplicaSet;
- ReplicaSet -> Pod; and
- Pod failure.

The graph contains the required structural provenance, but the product's
runtime/requested artifact identity consolidation prevented SC-2 from
establishing the exact immutable artifact at its admission gate.

## 8. SC-2 behavior that remains frozen

SC-2 correctly:

- failed closed;
- preserved the source effective time;
- created no fake candidate;
- created no fake temporal admission;
- created no lineage ranking bonus;
- created no TC-4 causal evidence;
- created no hypothesis; and
- preserved safe abstention.

## 9. Approved next repair boundary

Approved next product repair:

**SC-3 — Pod Requested-vs-Runtime Image Identity Preservation v1**

SC-3 should preserve and reason about requested image identity and
runtime-reported image identities as distinct but related semantic fields so
exact immutable artifact resolution can be established without weakening
SC-2.

SC-3 must not:

- loosen exact immutable-lineage requirements;
- make tag-only identity sufficient;
- modify the 180-minute path;
- modify candidate scoring;
- modify causal relevance;
- modify TC-4;
- force admission;
- modify incident lifecycle;
- repair runtime exit-code evidence; or
- add fuzzy or LLM identity matching.

## 10. Required semantic separation

The product should conceptually preserve these fields independently:

- `requested_image_ref`;
- `requested_repository`;
- `requested_digest`, when explicitly present;
- `runtime_status_image`;
- `runtime_image_id`;
- `resolved_oci_index`;
- `resolved_platform_manifest`; and
- `provider_artifact_identity`.

These fields are not automatically equal. Relationships between them require
explicit provenance.

Accepted EVAL-OCI-1 already established the evaluator-side distinction among
an OCI index, the platform executable child manifest, and
attestation/provenance descriptors. EVAL-RUNTIME-2 already separated
`pod.spec.containers[].image` from `pod.status.containerStatuses[].image` and
`pod.status.containerStatuses[].imageID`.

SC-3 should bring equivalent semantic discipline into product runtime/image
identity without copying evaluator truth into product code.

## 11. Result identities

| Artifact | SHA-256 |
|---|---|
| Runtime receipt | `3BD9E916EE48181E0B01B80E0F0D965B5A6AAAAD4766011F9B2F4ACC566A4AB4` |
| Product database | `C35861178A3AF8B824D658EB1B378EEE55A751E3BE299EB95AF049BAE09EC074` |
| Topo observation | `3BD0CC02...CBDD9C` (reported abbreviated identity) |
| Grade | `EF222007...DC4D68` (reported abbreviated identity) |
| Product diagnostics | `CF431ED0...3FCFDCB` (reported abbreviated identity) |

The omitted characters in the three abbreviated reported identities are not
reconstructed or inferred here.

## 12. Measurement limit

This remains one deterministic scenario. It does not prove generalized
image-resolution correctness.

It proves only that:

- SC-1 remains correct;
- SC-2 fails safely in the real path;
- `CAUSAL_CANDIDATE_MISSING` remains the first divergence; and
- the immediate cause of failed SC-2 admission is requested/runtime immutable
  image identity consolidation.

