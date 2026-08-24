from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


SOURCE_FILE_MUTATION_SCHEMA_VERSION = "source-file-mutation-v1"
SOURCE_FILE_MUTATION_CAPTURE_VERSION = "github-source-file-capture-v1"
BOUNDED_SCALAR_POLICY_VERSION = "bounded-scalar-text-v1"


class SourceFileChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


class SourceFileIdentityState(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


class SourceFileCaptureState(str, Enum):
    CAPTURED = "captured"
    NOT_APPLICABLE = "not_applicable"
    INELIGIBLE = "ineligible"
    LIMIT_EXCEEDED = "limit_exceeded"
    PROVIDER_ERROR = "provider_error"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


class SourceFileEvidenceCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class SourceFileParentContextType(str, Enum):
    ROOT = "root"
    SINGLE_PARENT = "single_parent"
    MULTIPLE_PARENTS = "multiple_parents"


class SourceFileEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    source_system: str = Field(min_length=1)


class SourceRepositoryIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(pattern="^github$")
    provider_repository_id: str = Field(min_length=1)
    full_name: str = Field(min_length=3)


class SourceFileParentContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_type: SourceFileParentContextType
    parent_shas: list[str] = Field(default_factory=list)


class SourceFileMutationSide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_state: SourceFileIdentityState
    path: str = Field(min_length=1)
    provider_blob_oid: str | None = None
    provider_blob_source: str | None = None
    content_sha256: str | None = Field(
        default=None,
        pattern="^[0-9a-f]{64}$",
    )
    size_bytes: int | None = Field(default=None, ge=0)
    content_capture_state: SourceFileCaptureState
    content_capture_reason: str | None = None
    semantic_value: str | None = None
    semantic_capture_state: SourceFileCaptureState
    semantic_capture_reason: str | None = None
    semantic_policy: str = BOUNDED_SCALAR_POLICY_VERSION


class SourceFileMutationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SOURCE_FILE_MUTATION_SCHEMA_VERSION
    mutation_id: str = Field(
        pattern="^source-file-mutation:[0-9a-f]{40}$"
    )
    provider: str = Field(pattern="^github$")
    repository: SourceRepositoryIdentity
    commit_sha: str = Field(min_length=1)
    parent_context: SourceFileParentContext
    change_type: SourceFileChangeType
    provider_status: str = Field(min_length=1)
    current_path: str = Field(min_length=1)
    previous_path: str | None = Field(default=None, min_length=1)
    before: SourceFileMutationSide
    after: SourceFileMutationSide
    completeness: SourceFileEvidenceCompleteness
    completeness_reasons: list[str] = Field(default_factory=list)
    source_component: str = "github-source-file-enrichment"
    source_references: list[SourceFileEvidenceReference] = Field(
        default_factory=list
    )


class SourceFileMutationEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SOURCE_FILE_MUTATION_SCHEMA_VERSION
    capture_version: str = SOURCE_FILE_MUTATION_CAPTURE_VERSION
    provider: str = Field(pattern="^github$")
    repository: SourceRepositoryIdentity | None = None
    completeness: SourceFileEvidenceCompleteness
    reasons: list[str] = Field(default_factory=list)
    requested_commit_count: int = Field(default=0, ge=0)
    enriched_commit_count: int = Field(default=0, ge=0)
    mutation_count: int = Field(default=0, ge=0)
    limits: dict[str, int] = Field(default_factory=dict)
    source_component: str = "github-source-file-enrichment"
    source_references: list[SourceFileEvidenceReference] = Field(
        default_factory=list
    )
