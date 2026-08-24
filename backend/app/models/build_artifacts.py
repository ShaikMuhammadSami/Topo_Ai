from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.temporal import TemporalMetadata


class BuildArtifactType(str, Enum):
    CONTAINER_IMAGE = "container_image"


class BuildArtifactEvidenceType(str, Enum):
    GITHUB_ACTIONS_DOCKER_BUILD_RECORD = (
        "github_actions_docker_build_record"
    )


class BuildArtifactEvidenceCompleteness(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class BuildArtifactEvidence(BaseModel):
    """Normalized provider evidence for one immutable build artifact."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=3)
    provider: str = Field(pattern="^github_actions$")

    repository_id: str = Field(min_length=1)
    repository: str = Field(min_length=3)
    workflow_id: str | None = None
    workflow_ref: str | None = None

    run_id: str = Field(min_length=1)
    run_attempt: int = Field(ge=1)
    commit_sha: str = Field(pattern="^[0-9a-f]{40}$")

    artifact_type: BuildArtifactType
    image_repository: str
    image_reference: str | None = None
    image_digest: str = Field(pattern="^sha256:[0-9a-f]{64}$")
    immutable_image_ref: str

    provider_evidence_type: BuildArtifactEvidenceType
    provider_evidence_id: str = Field(min_length=1)
    provider_evidence_reference: str = Field(min_length=1)
    provider_evidence_digest: str = Field(
        pattern="^sha256:[0-9a-f]{64}$"
    )
    provider_build_record_digest: str = Field(
        pattern="^sha256:[0-9a-f]{64}$"
    )
    provider_builder_id: str = Field(min_length=1)

    provider_build_started_at: datetime | None = None
    provider_build_finished_at: datetime | None = None
    provider_run_updated_at: datetime
    observed_at: datetime
    temporal: TemporalMetadata

    completeness: BuildArtifactEvidenceCompleteness

    @field_validator(
        "provider_build_started_at",
        "provider_build_finished_at",
        "provider_run_updated_at",
        "observed_at",
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Build artifact evidence times require a timezone")
        return value


class BuildArtifactEvidenceParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: list[BuildArtifactEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BuildArtifactLineageStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_artifacts_inspected: int = 0
    provider_build_records_accepted: int = 0
    evidence_records_persisted: int = 0
    evidence_records_considered: int = 0
    relationship_count: int = 0
    mapped_run_count: int = 0
    mapped_image_count: int = 0
    unresolved_evidence_count: int = 0
    warnings: list[str] = Field(default_factory=list)

