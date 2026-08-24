# EVAL-OCI-1 Runtime Image Identity Repair

Date: 2026-08-24

Branch: `evaluation/oci-index-runtime-identity-v1`

Scope: evaluation-only static repair. No Kubernetes, GHCR, provider workflow,
or Topo product path was accessed or mutated.

## Measured defect

Before EVAL-OCI-1, runtime receipt v1 required the digest requested in the Pod
specification to appear directly in container runtime `imageID`:

```text
requested OCI index == runtime imageID digest
```

That falsely rejects a standards-consistent runtime that reports the selected
linux/amd64 executable manifest of the requested multi-platform index.

## Repair

The new `eval-oci-runtime-identity-v1` contract separates provider artifact
identity from runtime execution identity.

Accepted:

```text
runtime digest == requested immutable index
    -> EXACT_INDEX
```

or:

```text
Pod requests exact immutable index
    + runtime imageID contains one exact digest
    + provider proves that digest is a child of that index
    + descriptor role/media identify an executable image manifest
    + descriptor platform exactly matches the explicit runtime target
    -> VERIFIED_PLATFORM_MANIFEST
```

Rejected or unverified:

- arbitrary digest;
- child associated only with another index;
- attestation, SBOM, or provenance-only manifest;
- absent provider proof;
- absent or mismatched platform;
- malformed or conflicting runtime digests;
- mutable image reference.

## Receipt versioning

The semantic change is material, so new observations emit
`eval-runtime-causal-receipt-v2`. V1 validation remains available for accepted
historical exact-index receipts. V2 records:

- requested immutable reference and index digest;
- runtime `imageID` and normalized runtime digest;
- bounded match type;
- target and descriptor platform;
- descriptor media type and role;
- provider verification source and relationship state.

Only accepted `EXACT_INDEX` or `VERIFIED_PLATFORM_MANIFEST` resolutions can
produce a complete v2 receipt. Mismatch and unverified outcomes preserve the
existing inconclusive gate.

## Source-cause compatibility

`eval-source-cause-match-v1` continues to compare against the provider OCI
index digest. The runtime platform manifest is not substituted as the source
artifact identity.

## Independence

The helper imports no product reasoning or image-linking implementation. It
has no network, Kubernetes, provider mutation, fuzzy matching, embeddings, or
LLM dependency. Provider descriptors explicitly declare independent proof and
`topo_output_used: false`.

## Verification

- New focused EVAL-OCI-1 tests: `73 passed in 0.58s`.
- Existing LINEAGE-1C focused tests: `83 passed`.
- Evaluation compile: passed.
- Full evaluation regression: `590 passed in 19.85s`.
- Backend compile: passed.
- Backend regression: `695 passed, 1 existing warning in 23.39s`.
- Agent compile: passed.
- Agent regression: `15 passed in 1.51s`.

## Before/after conclusion

Before:

```text
requested index must equal runtime imageID
=> valid platform-child execution can be falsely rejected
```

After:

```text
exact requested index accepted
OR
provider-verified executable platform child accepted
```

Unrelated, attestation, wrong-index, wrong-platform, and unverified digests
remain rejected.
