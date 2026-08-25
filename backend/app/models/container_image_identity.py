from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


KUBERNETES_CONTAINER_IMAGE_IDENTITY_VERSION = (
    "kubernetes-container-image-identity-v1"
)
MAX_CONTAINER_IMAGE_REFERENCE_LENGTH = 2048


class ContainerImageSemanticRole(str, Enum):
    REQUESTED_IMAGE = "requested_image"
    RUNTIME_STATUS_IMAGE = "runtime_status_image"
    RUNTIME_IMAGE_ID = "runtime_image_id"


class ContainerImageCaptureState(str, Enum):
    CAPTURED = "captured"
    MISSING = "missing"
    REJECTED = "rejected"


class ContainerImageReferenceKind(str, Enum):
    REPOSITORY_DIGEST = "repository_digest"
    REPOSITORY_TAG = "repository_tag"
    DIGEST_ONLY = "digest_only"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"


class ContainerImageJoinState(str, Enum):
    MATCHED = "matched"
    RUNTIME_STATUS_MISSING = "runtime_status_missing"
    RUNTIME_STATUS_AMBIGUOUS = "runtime_status_ambiguous"
    SPEC_MISSING = "spec_missing"
    SPEC_AMBIGUOUS = "spec_ambiguous"


class ContainerImageReferenceObservation(BaseModel):
    """One provider value with its source-specific semantic role intact."""

    model_config = ConfigDict(extra="forbid")

    semantic_role: ContainerImageSemanticRole
    source_field: str = Field(min_length=1)
    capture_state: ContainerImageCaptureState
    raw_value: str | None = Field(
        default=None,
        max_length=MAX_CONTAINER_IMAGE_REFERENCE_LENGTH,
    )
    raw_value_length: int = Field(default=0, ge=0)
    scheme: str | None = None
    registry: str | None = None
    repository: str | None = None
    tag: str | None = None
    digest: str | None = None
    normalized_reference: str | None = None
    reference_kind: ContainerImageReferenceKind = (
        ContainerImageReferenceKind.UNKNOWN
    )
    immutable_identity_eligible: bool = False
    rejection_reason: str | None = None


class RequestedArtifactIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=1)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    normalized_reference: str = Field(min_length=1)
    basis: str = "kubernetes_requested_immutable_reference"


class ContainerImageIdentityEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_role: ContainerImageSemanticRole
    source_field: str = Field(min_length=1)
    raw_value: str = Field(
        min_length=1,
        max_length=MAX_CONTAINER_IMAGE_REFERENCE_LENGTH,
    )


class KubernetesContainerImageObservation(BaseModel):
    """SC-3 regular-container identity contract persisted in snapshots."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = KUBERNETES_CONTAINER_IMAGE_IDENTITY_VERSION
    container_name: str = Field(min_length=1)
    container_family: str = "regular"
    join_state: ContainerImageJoinState
    spec_match_count: int = Field(ge=0)
    status_match_count: int = Field(ge=0)
    requested_image: ContainerImageReferenceObservation
    runtime_status_image: ContainerImageReferenceObservation
    runtime_image_id: ContainerImageReferenceObservation
    resolved_artifact_identity: RequestedArtifactIdentity | None = None
    resolved_artifact_basis: str | None = None
    identity_evidence_refs: list[
        ContainerImageIdentityEvidenceReference
    ] = Field(default_factory=list)
    ambiguous_runtime_status_images: list[
        ContainerImageReferenceObservation
    ] = Field(default_factory=list)
    ambiguous_runtime_image_ids: list[
        ContainerImageReferenceObservation
    ] = Field(default_factory=list)
