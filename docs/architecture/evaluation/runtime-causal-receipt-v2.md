# Runtime Causal Receipt v2

Status: **current runtime receipt for LINEAGE causal observation**

Version: `eval-runtime-causal-receipt-v2`

V2 replaces the v1 assumption that runtime `imageID` must contain the exact
requested OCI index digest. V1 remains loadable for historical exact-index
receipts; new observations emit v2.

V2 separates:

- `experiment.requested_artifact`: immutable reference and provider index
  digest;
- `container.image`: the exact image reference requested by the matching named
  container in `pod.spec.containers`;
- `container.image_id`: the matching named container's runtime `imageID`;
- `container.runtime_digest`: the normalized digest derived from `imageID`;
- optional `container.runtime_status_image`: the matching named container's
  runtime-normalized diagnostic `status.containerStatuses[].image` value;
- `artifact_resolution`: the bounded `eval-oci-runtime-identity-v1` decision.

Pod spec containers and container statuses are joined by exact container name.
Missing or ambiguous matches keep the observation gate closed. Array position is
not identity.

`runtime_status_image` is non-authoritative because Kubernetes runtimes may
report a tag, repository digest, normalized digest, image-config digest, or
another runtime-specific representation. Missing, malformed, or different
diagnostic status-image text cannot establish or override the authoritative
Pod-spec request and `imageID` proof.

Only `EXACT_INDEX` and `VERIFIED_PLATFORM_MANIFEST` can appear in a complete
runtime receipt. `MISMATCH` and `UNVERIFIED` keep the runtime ground-truth gate
closed.

The source-cause evaluator continues to use the requested provider index
digest. The selected executable platform manifest is runtime-bound evidence,
not a replacement provider artifact identity.
