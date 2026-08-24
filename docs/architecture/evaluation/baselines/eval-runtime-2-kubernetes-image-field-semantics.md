# EVAL-RUNTIME-2 — Kubernetes Image Field Semantics

Status: **post-repair evaluator baseline**

## Measured defect

Docker Desktop/containerd preserved the exact immutable request in the Pod spec
and reported the requested OCI index through `imageID`, while normalizing
`containerStatuses[].image` to a different image-config digest. The observer
incorrectly treated the normalized status field as the requested reference.

Classification: `RUNTIME_OBSERVER_IMAGE_REF_FIELD_MISMATCH`

## Before

`status.image` equality could invalidate otherwise valid requested-artifact and
runtime-identity evidence.

## After

- `pod.spec.containers[matching-name].image` validates the request.
- `pod.status.containerStatuses[matching-name].imageID` validates execution via
  the unchanged EVAL-OCI-1 resolver.
- `pod.status.containerStatuses[matching-name].image` is retained only as the
  optional `runtime_status_image` diagnostic.
- Exact name matching prevents array-order and sidecar contamination.

No product code, OCI resolution policy, source-cause matching, workflow, or
historical v1 receipt semantics changed. The repair is static and performs no
Kubernetes or provider operation.
