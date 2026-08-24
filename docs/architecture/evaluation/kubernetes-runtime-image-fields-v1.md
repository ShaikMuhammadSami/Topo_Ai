# Kubernetes Runtime Image Fields v1

Status: **evaluation identity contract**

Kubernetes exposes three related but non-interchangeable image fields. The
LINEAGE runtime observer correlates them through the exact evaluation container
name; array position is never identity.

## Requested artifact

`pod.spec.containers[].image` is the authoritative requested artifact reference.
The matching named container must contain the exact digest-pinned immutable
reference supplied to the evaluation. Mutable tags, missing matches, duplicate
matches, and different immutable digests keep the gate closed.

## Runtime execution identity

`pod.status.containerStatuses[].imageID` is the authoritative runtime execution
identity for the same named container. Its value is resolved by the unchanged
`eval-oci-runtime-identity-v1` policy. Only an exact requested OCI index or an
independently verified executable platform child is accepted.

## Runtime-normalized diagnostic

`pod.status.containerStatuses[].image` is recorded as
`container.runtime_status_image` when a v2 receipt is emitted. A runtime may use
a tag, repository digest, normalized digest, image-config digest, or another
implementation-specific string. It neither establishes nor invalidates image
identity and cannot override Pod-spec or `imageID` evidence.

The diagnostic field is optional for compatibility with historical v2
receipts. New observations include it with its string value or `null` when the
runtime omits it. Historical v1 receipt meaning is unchanged.

## Fail-closed container correlation

The expected container name must resolve to exactly one Pod-spec container and
exactly one container status. Missing or duplicate matches are inconclusive.
Sidecars cannot supply the request, runtime identity, or diagnostic status image
for the evaluated container.
