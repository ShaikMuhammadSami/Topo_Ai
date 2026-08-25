from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from app.models.container_image_identity import (
    MAX_CONTAINER_IMAGE_REFERENCE_LENGTH,
    ContainerImageCaptureState,
    ContainerImageIdentityEvidenceReference,
    ContainerImageJoinState,
    ContainerImageReferenceKind,
    ContainerImageReferenceObservation,
    ContainerImageSemanticRole,
    KubernetesContainerImageObservation,
    RequestedArtifactIdentity,
)


_SHA256 = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_SCHEME = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<value>.+)$"
)

_SOURCE_FIELDS = {
    ContainerImageSemanticRole.REQUESTED_IMAGE: (
        "pod.spec.containers[].image"
    ),
    ContainerImageSemanticRole.RUNTIME_STATUS_IMAGE: (
        "pod.status.containerStatuses[].image"
    ),
    ContainerImageSemanticRole.RUNTIME_IMAGE_ID: (
        "pod.status.containerStatuses[].imageID"
    ),
}


def _field_value(item: object, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _repository_parts(value: str) -> tuple[str, str]:
    """Apply the existing container graph's Docker reference defaults."""

    segments = value.split("/")
    first = segments[0]
    explicit_registry = (
        "." in first or ":" in first or first == "localhost"
    )
    if len(segments) == 1:
        return "docker.io", f"library/{segments[0]}"
    if explicit_registry:
        return first, "/".join(segments[1:])
    return "docker.io", "/".join(segments)


def parse_container_image_observation(
    value: object,
    *,
    semantic_role: ContainerImageSemanticRole,
    source_field: str | None = None,
) -> ContainerImageReferenceObservation:
    """Parse syntax only; semantic role determines identity eligibility."""

    resolved_source_field = source_field or _SOURCE_FIELDS[semantic_role]
    if not isinstance(value, str) or not value.strip():
        return ContainerImageReferenceObservation(
            semantic_role=semantic_role,
            source_field=resolved_source_field,
            capture_state=ContainerImageCaptureState.MISSING,
        )

    raw = value
    raw_length = len(raw)
    if raw_length > MAX_CONTAINER_IMAGE_REFERENCE_LENGTH:
        return ContainerImageReferenceObservation(
            semantic_role=semantic_role,
            source_field=resolved_source_field,
            capture_state=ContainerImageCaptureState.REJECTED,
            raw_value_length=raw_length,
            rejection_reason="reference_too_long",
        )

    scheme: str | None = None
    reference = raw.strip()
    scheme_match = _SCHEME.fullmatch(reference)
    if scheme_match is not None:
        scheme = scheme_match.group("scheme").lower()
        reference = scheme_match.group("value")

    base = {
        "semantic_role": semantic_role,
        "source_field": resolved_source_field,
        "capture_state": ContainerImageCaptureState.CAPTURED,
        "raw_value": raw,
        "raw_value_length": raw_length,
        "scheme": scheme,
    }

    if _SHA256.fullmatch(reference):
        digest = reference.lower()
        return ContainerImageReferenceObservation(
            **base,
            digest=digest,
            normalized_reference=digest,
            reference_kind=ContainerImageReferenceKind.DIGEST_ONLY,
        )

    if "@" in reference:
        repository_value, digest_value = reference.rsplit("@", maxsplit=1)
        if (
            repository_value
            and not any(character.isspace() for character in repository_value)
            and _SHA256.fullmatch(digest_value)
        ):
            registry, repository_path = _repository_parts(repository_value)
            repository = f"{registry}/{repository_path}"
            digest = digest_value.lower()
            normalized = f"{repository}@{digest}"
            eligible = (
                semantic_role == ContainerImageSemanticRole.REQUESTED_IMAGE
            )
            return ContainerImageReferenceObservation(
                **base,
                registry=registry,
                repository=repository,
                digest=digest,
                normalized_reference=normalized,
                reference_kind=(
                    ContainerImageReferenceKind.REPOSITORY_DIGEST
                ),
                immutable_identity_eligible=eligible,
            )
        return ContainerImageReferenceObservation(
            **base,
            reference_kind=ContainerImageReferenceKind.MALFORMED,
            rejection_reason="malformed_repository_digest_reference",
        )

    if any(character.isspace() for character in reference):
        return ContainerImageReferenceObservation(
            **base,
            reference_kind=ContainerImageReferenceKind.MALFORMED,
            rejection_reason="malformed_image_reference",
        )

    final_segment = reference.rsplit("/", maxsplit=1)[-1]
    repository_value = reference
    tag = "latest"
    if ":" in final_segment:
        repository_value, tag = reference.rsplit(":", maxsplit=1)
    if not repository_value or not tag:
        return ContainerImageReferenceObservation(
            **base,
            reference_kind=ContainerImageReferenceKind.MALFORMED,
            rejection_reason="malformed_repository_tag_reference",
        )
    registry, repository_path = _repository_parts(repository_value)
    repository = f"{registry}/{repository_path}"
    return ContainerImageReferenceObservation(
        **base,
        registry=registry,
        repository=repository,
        tag=tag,
        normalized_reference=f"{repository}:{tag}",
        reference_kind=ContainerImageReferenceKind.REPOSITORY_TAG,
    )


def _missing(
    role: ContainerImageSemanticRole,
    *,
    source_field: str | None = None,
) -> ContainerImageReferenceObservation:
    return parse_container_image_observation(
        None,
        semantic_role=role,
        source_field=source_field,
    )


def _evidence_refs(
    observations: Iterable[ContainerImageReferenceObservation],
) -> list[ContainerImageIdentityEvidenceReference]:
    refs = {
        (
            item.semantic_role.value,
            item.source_field,
            item.raw_value,
        ): ContainerImageIdentityEvidenceReference(
            semantic_role=item.semantic_role,
            source_field=item.source_field,
            raw_value=item.raw_value,
        )
        for item in observations
        if item.capture_state == ContainerImageCaptureState.CAPTURED
        and item.raw_value
    }
    return [refs[key] for key in sorted(refs)]


def _resolved_requested_identity(
    requested: ContainerImageReferenceObservation,
) -> RequestedArtifactIdentity | None:
    if (
        requested.immutable_identity_eligible
        and requested.repository
        and requested.digest
        and requested.normalized_reference
    ):
        return RequestedArtifactIdentity(
            repository=requested.repository,
            digest=requested.digest,
            normalized_reference=requested.normalized_reference,
        )
    return None


def normalize_regular_container_images(
    *,
    spec_containers: Iterable[object],
    status_containers: Iterable[object] = (),
    spec_source_field: str = "pod.spec.containers[].image",
) -> list[dict[str, Any]]:
    """Join regular spec/status containers by exact name and retain roles."""

    specs: dict[str, list[object]] = defaultdict(list)
    statuses: dict[str, list[object]] = defaultdict(list)
    for item in spec_containers:
        name = _field_value(item, "name")
        if isinstance(name, str) and name.strip():
            specs[name.strip()].append(item)
    for item in status_containers:
        name = _field_value(item, "name")
        if isinstance(name, str) and name.strip():
            statuses[name.strip()].append(item)

    result: list[dict[str, Any]] = []
    for name in sorted(set(specs) | set(statuses)):
        spec_matches = specs.get(name, [])
        status_matches = statuses.get(name, [])
        requested = (
            parse_container_image_observation(
                _field_value(spec_matches[0], "image"),
                semantic_role=ContainerImageSemanticRole.REQUESTED_IMAGE,
                source_field=spec_source_field,
            )
            if len(spec_matches) == 1
            else _missing(
                ContainerImageSemanticRole.REQUESTED_IMAGE,
                source_field=spec_source_field,
            )
        )

        status_candidates = sorted(
            (
                parse_container_image_observation(
                    _field_value(item, "image"),
                    semantic_role=(
                        ContainerImageSemanticRole.RUNTIME_STATUS_IMAGE
                    ),
                )
                for item in status_matches
            ),
            key=lambda item: item.raw_value or "",
        )
        image_id_candidates = sorted(
            (
                parse_container_image_observation(
                    _field_value(item, "image_id"),
                    semantic_role=ContainerImageSemanticRole.RUNTIME_IMAGE_ID,
                )
                for item in status_matches
            ),
            key=lambda item: item.raw_value or "",
        )

        if len(spec_matches) > 1:
            join_state = ContainerImageJoinState.SPEC_AMBIGUOUS
        elif not spec_matches:
            join_state = ContainerImageJoinState.SPEC_MISSING
        elif len(status_matches) > 1:
            join_state = ContainerImageJoinState.RUNTIME_STATUS_AMBIGUOUS
        elif not status_matches:
            join_state = ContainerImageJoinState.RUNTIME_STATUS_MISSING
        else:
            join_state = ContainerImageJoinState.MATCHED

        runtime_status = (
            status_candidates[0]
            if len(status_matches) == 1
            else _missing(ContainerImageSemanticRole.RUNTIME_STATUS_IMAGE)
        )
        runtime_image_id = (
            image_id_candidates[0]
            if len(status_matches) == 1
            else _missing(ContainerImageSemanticRole.RUNTIME_IMAGE_ID)
        )
        resolved = _resolved_requested_identity(requested)
        evidence = _evidence_refs(
            [requested, *status_candidates, *image_id_candidates]
        )
        observation = KubernetesContainerImageObservation(
            container_name=name,
            join_state=join_state,
            spec_match_count=len(spec_matches),
            status_match_count=len(status_matches),
            requested_image=requested,
            runtime_status_image=runtime_status,
            runtime_image_id=runtime_image_id,
            resolved_artifact_identity=resolved,
            resolved_artifact_basis=(resolved.basis if resolved else None),
            identity_evidence_refs=evidence,
            ambiguous_runtime_status_images=(
                status_candidates if len(status_matches) > 1 else []
            ),
            ambiguous_runtime_image_ids=(
                image_id_candidates if len(status_matches) > 1 else []
            ),
        )

        status = status_matches[0] if len(status_matches) == 1 else None
        result.append(
            {
                "name": name,
                # Compatibility: this field historically means the image
                # requested by the workload. SC-3 makes that meaning exact.
                "image": requested.raw_value,
                "image_id": runtime_image_id.raw_value,
                "runtime_status_image": runtime_status.raw_value,
                "container_id": (
                    _field_value(status, "container_id") if status else None
                ),
                "ready": _field_value(status, "ready") if status else None,
                "restart_count": (
                    int(_field_value(status, "restart_count") or 0)
                    if status
                    else 0
                ),
                "image_identity": observation.model_dump(mode="json"),
            }
        )
    return result
