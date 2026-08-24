# OCI Index to Runtime Manifest Identity v1

Status: **authoritative evaluation-only runtime identity contract**

Version: `eval-oci-runtime-identity-v1`

## Why two digests can both be correct

An immutable OCI index identifies a set of descriptors. Kubernetes requests
the index, while containerd may report the selected executable platform
manifest in `imageID`. Therefore index digest inequality alone is not an
artifact mismatch.

## ImageID normalization

The evaluator extracts exactly one normalized SHA-256 digest from bounded
forms including:

- `containerd://sha256:<digest>`;
- `docker-pullable://repository@sha256:<digest>`;
- `repository@sha256:<digest>`;
- `sha256:<digest>`.

Malformed values, missing digests, and conflicting digests fail closed. No
tag, repository name, timestamp, title, fuzzy comparison, embedding, or LLM
participates.

## Match types

- `EXACT_INDEX`: runtime reports the exact requested index digest. No child
  descriptor is invented or required.
- `VERIFIED_PLATFORM_MANIFEST`: runtime reports one exact child descriptor
  whose parent is the requested index, role and media type identify an
  executable image manifest, platform exactly matches the explicit runtime
  target, and provider proof is present.
- `MISMATCH`: a different index, unrelated digest, non-executable descriptor,
  or platform conflict.
- `UNVERIFIED`: provider proof, platform, runtime digest, or an unambiguous
  relationship is unavailable.

## Attestation and provenance rejection

Attestation, SBOM, and provenance-only descriptors are never executable
runtime identity, even when they are legitimate children of the requested
index and use image-manifest media types. Classification uses structured role,
media type, platform, and provider relationship evidence; no digest literal
is special-cased.

## Provider independence

Allowed verification sources are bounded to registry/provider evidence:

- `docker_buildx_imagetools_inspect`;
- `registry_manifest_descriptor`;
- `provider_build_record`.

Topo graph entities, Topo RCA, and Topo image linking cannot establish the
expected descriptor relationship. Every descriptor carries
`topo_output_used: false`.

## Receipt and source-cause relationship

Runtime receipt v2 records requested index and runtime manifest separately.
`eval-source-cause-match-v1` remains anchored to the provider index digest;
runtime platform selection never changes source/provider artifact truth.
