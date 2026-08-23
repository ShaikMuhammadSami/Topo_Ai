from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CanonicalIdentityResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class CanonicalIdentityResolutionStrategy(str, Enum):
    CANONICAL_ID = "canonical_id"
    SOURCE_NATIVE_ID = "source_native_id"
    SCOPED_ALIAS = "scoped_alias"
    SOURCE_FALLBACK = "source_fallback"
    NONE = "none"


class CanonicalEntityIdentity(BaseModel):
    """Versioned source-specific graph identity description."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str = Field(min_length=3)
    entity_kind: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    source_native_id: str | None = None
    scope: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    identity_version: str = Field(min_length=1)
    strategy: str = Field(min_length=1)


class CanonicalIdentityResolution(BaseModel):
    """Auditable result of deterministic snapshot entity resolution."""

    model_config = ConfigDict(extra="forbid")

    status: CanonicalIdentityResolutionStatus
    strategy: CanonicalIdentityResolutionStrategy
    input_identifier: str | None = None
    resolved_entity_id: str | None = None
    resolved_canonical_id: str | None = None
    matched_value: str | None = None
    identity_version: str | None = None
    candidate_entity_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
