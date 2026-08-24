# Runtime Causal Receipt v2

Status: **current runtime receipt for LINEAGE causal observation**

Version: `eval-runtime-causal-receipt-v2`

V2 replaces the v1 assumption that runtime `imageID` must contain the exact
requested OCI index digest. V1 remains loadable for historical exact-index
receipts; new observations emit v2.

V2 separates:

- `experiment.requested_artifact`: immutable reference and provider index
  digest;
- `container`: runtime `imageID` and its normalized digest;
- `artifact_resolution`: the bounded `eval-oci-runtime-identity-v1` decision.

Only `EXACT_INDEX` and `VERIFIED_PLATFORM_MANIFEST` can appear in a complete
runtime receipt. `MISMATCH` and `UNVERIFIED` keep the runtime ground-truth gate
closed.

The source-cause evaluator continues to use the requested provider index
digest. The selected executable platform manifest is runtime-bound evidence,
not a replacement provider artifact identity.
