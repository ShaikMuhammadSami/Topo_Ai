from __future__ import annotations

import re
from copy import deepcopy
from enum import Enum
from typing import Any, Iterable

from evaluation.lineage_contracts import deterministic_json


OCI_RUNTIME_IDENTITY_VERSION = "eval-oci-runtime-identity-v1"


class RuntimeIdentityMatch(str, Enum):
    EXACT_INDEX = "EXACT_INDEX"
    VERIFIED_PLATFORM_MANIFEST = "VERIFIED_PLATFORM_MANIFEST"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"


class DescriptorRole(str, Enum):
    EXECUTABLE_IMAGE = "executable_image"
    ATTESTATION = "attestation"
    SBOM = "sbom"
    PROVENANCE = "provenance"
    UNKNOWN = "unknown"


class ProviderVerificationSource(str, Enum):
    DOCKER_BUILDX_IMAGETOOLS_INSPECT = "docker_buildx_imagetools_inspect"
    REGISTRY_MANIFEST_DESCRIPTOR = "registry_manifest_descriptor"
    PROVIDER_BUILD_RECORD = "provider_build_record"


EXECUTABLE_MANIFEST_MEDIA_TYPES = frozenset(
    {
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    }
)

_DIGEST = re.compile(
    r"(?<![A-Za-z0-9])sha256:[0-9a-fA-F]{64}(?![A-Za-z0-9])"
)
_EXACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMMUTABLE_IMAGE = re.compile(
    r"^[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/[^@\s]+@sha256:[0-9a-f]{64}$"
)
_PLATFORM_VALUE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def normalize_digest(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _EXACT_DIGEST.fullmatch(normalized):
        raise ValueError("A normalized immutable SHA-256 digest is required.")
    return normalized


def digest_from_immutable_ref(image_ref: str) -> str:
    normalized = str(image_ref or "").strip().lower()
    if not _IMMUTABLE_IMAGE.fullmatch(normalized):
        raise ValueError("An exact immutable image digest reference is required.")
    return normalize_digest(normalized.rsplit("@", 1)[1])


def digest_from_runtime_image_id(image_id: str) -> str:
    value = str(image_id or "").strip()
    matches = {normalize_digest(item) for item in _DIGEST.findall(value)}
    if not matches:
        raise ValueError("Runtime imageID contains no exact SHA-256 digest.")
    if len(matches) != 1:
        raise ValueError("Runtime imageID contains conflicting SHA-256 digests.")
    return next(iter(matches))


def platform_value(
    *, os_name: str, architecture: str, variant: str | None = None
) -> dict[str, str | None]:
    values = {
        "os": str(os_name or "").strip().lower(),
        "architecture": str(architecture or "").strip().lower(),
        "variant": str(variant).strip().lower() if variant else None,
    }
    if not _PLATFORM_VALUE.fullmatch(values["os"]):
        raise ValueError("OCI platform operating system is invalid.")
    if not _PLATFORM_VALUE.fullmatch(values["architecture"]):
        raise ValueError("OCI platform architecture is invalid.")
    if values["variant"] and not _PLATFORM_VALUE.fullmatch(values["variant"]):
        raise ValueError("OCI platform variant is invalid.")
    return values


def provider_descriptor(
    *,
    parent_index_digest: str,
    digest: str,
    media_type: str,
    role: DescriptorRole | str,
    platform: dict[str, Any] | None,
    provider_verified: bool,
    provider_verification_source: ProviderVerificationSource | str | None,
    annotations: dict[str, str] | None = None,
    topo_output_used: bool = False,
) -> dict[str, Any]:
    value = {
        "parent_index_digest": normalize_digest(parent_index_digest),
        "digest": normalize_digest(digest),
        "media_type": str(media_type or "").strip(),
        "role": DescriptorRole(role).value,
        "platform": (
            platform_value(
                os_name=str(platform.get("os") or ""),
                architecture=str(platform.get("architecture") or ""),
                variant=(
                    str(platform.get("variant"))
                    if platform.get("variant")
                    else None
                ),
            )
            if platform is not None
            else None
        ),
        "provider_verified": provider_verified,
        "provider_verification_source": (
            ProviderVerificationSource(provider_verification_source).value
            if provider_verification_source is not None
            else None
        ),
        "annotations": dict(sorted((annotations or {}).items())),
        "topo_output_used": topo_output_used,
    }
    validate_provider_descriptor(value)
    return value


def validate_provider_descriptor(value: dict[str, Any]) -> None:
    required = {
        "parent_index_digest",
        "digest",
        "media_type",
        "role",
        "platform",
        "provider_verified",
        "provider_verification_source",
        "annotations",
        "topo_output_used",
    }
    if set(value) != required:
        raise ValueError("OCI provider descriptor fields do not match v1.")
    normalize_digest(str(value.get("parent_index_digest") or ""))
    normalize_digest(str(value.get("digest") or ""))
    DescriptorRole(str(value.get("role")))
    if not isinstance(value.get("media_type"), str) or not value["media_type"]:
        raise ValueError("OCI descriptor media type is required.")
    if value.get("topo_output_used") is not False:
        raise ValueError("Topo cannot establish provider descriptor truth.")
    if not isinstance(value.get("provider_verified"), bool):
        raise ValueError("Provider verification state must be explicit.")
    source = value.get("provider_verification_source")
    if source is not None:
        ProviderVerificationSource(str(source))
    if value.get("provider_verified") is True and source is None:
        raise ValueError("Verified OCI descriptors require a provider source.")
    platform = value.get("platform")
    if platform is not None:
        if set(platform) != {"os", "architecture", "variant"}:
            raise ValueError("OCI descriptor platform fields do not match v1.")
        platform_value(
            os_name=str(platform.get("os") or ""),
            architecture=str(platform.get("architecture") or ""),
            variant=(str(platform.get("variant")) if platform.get("variant") else None),
        )
    annotations = value.get("annotations")
    if not isinstance(annotations, dict) or any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in annotations.items()
    ):
        raise ValueError("OCI descriptor annotations must be string pairs.")


def _resolution(
    *,
    match_type: RuntimeIdentityMatch,
    requested_immutable_ref: str,
    requested_index_digest: str,
    runtime_image_id: str | None,
    runtime_digest: str | None,
    target_platform: dict[str, Any],
    descriptor: dict[str, Any] | None,
    accepted: bool,
    reason: str,
) -> dict[str, Any]:
    descriptor = deepcopy(descriptor) if descriptor else None
    return {
        "identity_version": OCI_RUNTIME_IDENTITY_VERSION,
        "match_type": match_type.value,
        "requested_immutable_ref": requested_immutable_ref,
        "requested_index_digest": requested_index_digest,
        "runtime_image_id": runtime_image_id,
        "runtime_digest": runtime_digest,
        "target_platform": deepcopy(target_platform),
        "descriptor_digest": descriptor.get("digest") if descriptor else None,
        "descriptor_media_type": (
            descriptor.get("media_type") if descriptor else None
        ),
        "descriptor_role": descriptor.get("role") if descriptor else None,
        "descriptor_platform": descriptor.get("platform") if descriptor else None,
        "provider_verified": (
            descriptor.get("provider_verified") if descriptor else None
        ),
        "provider_verification_source": (
            descriptor.get("provider_verification_source") if descriptor else None
        ),
        "descriptor_relationship_verified": bool(
            descriptor
            and descriptor.get("parent_index_digest") == requested_index_digest
        ),
        "executable_manifest": bool(
            descriptor
            and descriptor.get("role") == DescriptorRole.EXECUTABLE_IMAGE.value
            and descriptor.get("media_type") in EXECUTABLE_MANIFEST_MEDIA_TYPES
        ),
        "accepted": accepted,
        "reason": reason,
        "topo_output_used": False,
    }


def resolve_runtime_artifact_identity(
    *,
    requested_immutable_ref: str,
    runtime_image_id: str | None,
    target_platform: dict[str, Any],
    provider_descriptors: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    requested_index_digest = digest_from_immutable_ref(requested_immutable_ref)
    platform = platform_value(
        os_name=str(target_platform.get("os") or ""),
        architecture=str(target_platform.get("architecture") or ""),
        variant=(
            str(target_platform.get("variant"))
            if target_platform.get("variant")
            else None
        ),
    )
    try:
        runtime_digest = digest_from_runtime_image_id(str(runtime_image_id or ""))
    except ValueError as exc:
        return _resolution(
            match_type=RuntimeIdentityMatch.UNVERIFIED,
            requested_immutable_ref=requested_immutable_ref,
            requested_index_digest=requested_index_digest,
            runtime_image_id=runtime_image_id,
            runtime_digest=None,
            target_platform=platform,
            descriptor=None,
            accepted=False,
            reason=str(exc),
        )
    if runtime_digest == requested_index_digest:
        result = _resolution(
            match_type=RuntimeIdentityMatch.EXACT_INDEX,
            requested_immutable_ref=requested_immutable_ref,
            requested_index_digest=requested_index_digest,
            runtime_image_id=runtime_image_id,
            runtime_digest=runtime_digest,
            target_platform=platform,
            descriptor=None,
            accepted=True,
            reason="Runtime imageID reports the exact requested OCI index digest.",
        )
        validate_runtime_identity_resolution(result)
        return result

    descriptors = [deepcopy(item) for item in provider_descriptors]
    for descriptor in descriptors:
        validate_provider_descriptor(descriptor)
    digest_matches = [
        item for item in descriptors if item["digest"] == runtime_digest
    ]
    exact_parent = [
        item
        for item in digest_matches
        if item["parent_index_digest"] == requested_index_digest
    ]
    if not exact_parent:
        reason = (
            "Runtime manifest belongs only to a different OCI index."
            if digest_matches
            else "Runtime digest is not a provider descriptor of the requested index."
        )
        return _resolution(
            match_type=RuntimeIdentityMatch.MISMATCH,
            requested_immutable_ref=requested_immutable_ref,
            requested_index_digest=requested_index_digest,
            runtime_image_id=runtime_image_id,
            runtime_digest=runtime_digest,
            target_platform=platform,
            descriptor=digest_matches[0] if digest_matches else None,
            accepted=False,
            reason=reason,
        )
    if len(exact_parent) != 1:
        return _resolution(
            match_type=RuntimeIdentityMatch.UNVERIFIED,
            requested_immutable_ref=requested_immutable_ref,
            requested_index_digest=requested_index_digest,
            runtime_image_id=runtime_image_id,
            runtime_digest=runtime_digest,
            target_platform=platform,
            descriptor=None,
            accepted=False,
            reason="Provider descriptor relationship is ambiguous.",
        )
    descriptor = exact_parent[0]
    if not descriptor["provider_verified"]:
        match_type = RuntimeIdentityMatch.UNVERIFIED
        reason = "Provider descriptor relationship is not independently verified."
    elif descriptor["provider_verification_source"] is None:
        match_type = RuntimeIdentityMatch.UNVERIFIED
        reason = "Provider verification source is missing."
    elif descriptor["role"] != DescriptorRole.EXECUTABLE_IMAGE.value:
        match_type = RuntimeIdentityMatch.MISMATCH
        reason = "Provider descriptor is not an executable image manifest."
    elif descriptor["media_type"] not in EXECUTABLE_MANIFEST_MEDIA_TYPES:
        match_type = RuntimeIdentityMatch.MISMATCH
        reason = "Provider descriptor media type is not executable image media."
    elif descriptor["platform"] is None:
        match_type = RuntimeIdentityMatch.UNVERIFIED
        reason = "Executable child manifest has no independently verified platform."
    elif descriptor["platform"] != platform:
        match_type = RuntimeIdentityMatch.MISMATCH
        reason = "Executable child manifest platform does not match the runtime target."
    else:
        match_type = RuntimeIdentityMatch.VERIFIED_PLATFORM_MANIFEST
        reason = (
            "Runtime imageID reports the independently verified executable "
            "platform child of the requested OCI index."
        )
    result = _resolution(
        match_type=match_type,
        requested_immutable_ref=requested_immutable_ref,
        requested_index_digest=requested_index_digest,
        runtime_image_id=runtime_image_id,
        runtime_digest=runtime_digest,
        target_platform=platform,
        descriptor=descriptor,
        accepted=match_type == RuntimeIdentityMatch.VERIFIED_PLATFORM_MANIFEST,
        reason=reason,
    )
    validate_runtime_identity_resolution(result)
    return result


def validate_runtime_identity_resolution(value: dict[str, Any]) -> None:
    required = {
        "identity_version",
        "match_type",
        "requested_immutable_ref",
        "requested_index_digest",
        "runtime_image_id",
        "runtime_digest",
        "target_platform",
        "descriptor_digest",
        "descriptor_media_type",
        "descriptor_role",
        "descriptor_platform",
        "provider_verified",
        "provider_verification_source",
        "descriptor_relationship_verified",
        "executable_manifest",
        "accepted",
        "reason",
        "topo_output_used",
    }
    if set(value) != required:
        raise ValueError("OCI runtime identity fields do not match v1.")
    if value.get("identity_version") != OCI_RUNTIME_IDENTITY_VERSION:
        raise ValueError("Unsupported OCI runtime identity version.")
    match_type = RuntimeIdentityMatch(str(value.get("match_type")))
    requested_digest = digest_from_immutable_ref(
        str(value.get("requested_immutable_ref") or "")
    )
    if value.get("requested_index_digest") != requested_digest:
        raise ValueError("Requested OCI index identity is inconsistent.")
    runtime_digest = value.get("runtime_digest")
    if runtime_digest is not None:
        normalize_digest(str(runtime_digest))
    platform = value.get("target_platform") or {}
    platform_value(
        os_name=str(platform.get("os") or ""),
        architecture=str(platform.get("architecture") or ""),
        variant=(str(platform.get("variant")) if platform.get("variant") else None),
    )
    if value.get("topo_output_used") is not False:
        raise ValueError("Topo cannot establish expected runtime artifact identity.")
    if not isinstance(value.get("accepted"), bool):
        raise ValueError("Runtime identity acceptance must be explicit.")
    if match_type == RuntimeIdentityMatch.EXACT_INDEX:
        if runtime_digest != requested_digest or value["accepted"] is not True:
            raise ValueError("EXACT_INDEX resolution is inconsistent.")
        if any(
            value.get(field) is not None
            for field in (
                "descriptor_digest",
                "descriptor_media_type",
                "descriptor_role",
                "descriptor_platform",
                "provider_verified",
                "provider_verification_source",
            )
        ):
            raise ValueError("EXACT_INDEX cannot fabricate a child descriptor.")
    if match_type == RuntimeIdentityMatch.VERIFIED_PLATFORM_MANIFEST:
        if not all(
            (
                value.get("accepted") is True,
                value.get("descriptor_digest") == runtime_digest,
                value.get("descriptor_relationship_verified") is True,
                value.get("executable_manifest") is True,
                value.get("provider_verified") is True,
                value.get("provider_verification_source") is not None,
                value.get("descriptor_platform") == value.get("target_platform"),
            )
        ):
            raise ValueError("VERIFIED_PLATFORM_MANIFEST resolution is incomplete.")
    if match_type in {RuntimeIdentityMatch.MISMATCH, RuntimeIdentityMatch.UNVERIFIED}:
        if value.get("accepted") is not False:
            raise ValueError("Unproven runtime artifact identity cannot be accepted.")


def deterministic_identity_json(value: dict[str, Any]) -> str:
    validate_runtime_identity_resolution(value)
    return deterministic_json(value)
