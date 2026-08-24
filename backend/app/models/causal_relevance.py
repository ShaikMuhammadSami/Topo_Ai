from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.topology import (
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipSourceReference,
)


CAUSAL_RELEVANCE_POLICY_VERSION = "causal-relevance-v1"


class CausalPathSemantic(str, Enum):
    DIRECT_ENTITY = "direct_entity"
    CONTROL_OWNERSHIP = "control_ownership"
    ARTIFACT_LINEAGE = "artifact_lineage"
    DEPENDENCY_IMPACT = "dependency_impact"
    RUNTIME_HOSTING = "runtime_hosting"
    OTHER_SUPPORTED = "other_supported"
    STRUCTURAL_CONTEXT = "structural_context"
    UNSUPPORTED_UNKNOWN = "unsupported_unknown"


class CausalRelevanceStatus(str, Enum):
    DIRECT = "direct"
    SEMANTIC_PATH = "semantic_path"
    NO_SUPPORTED_PATH = "no_supported_path"
    IDENTITY_UNRESOLVED = "identity_unresolved"
    AMBIGUOUS = "ambiguous"


class CausalTraversalDirection(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"
    NONE = "none"


class CausalPredicateSupport(str, Enum):
    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    STRUCTURAL_ONLY = "structural_only"
    UNSUPPORTED = "unsupported"


class CausalPathHop(BaseModel):
    """One selected source-to-effect traversal over an immutable TC-2 edge."""

    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    target_entity_id: str
    relationship_id: str
    predicate: str
    traversal_direction: CausalTraversalDirection
    semantic_class: CausalPathSemantic
    relationship_origin: RelationshipOrigin | None = None
    relationship_source_system: str
    relationship_source_component: str | None = None
    relationship_source_references: list[RelationshipSourceReference] = Field(
        default_factory=list
    )
    relationship_linker_version: str | None = None
    relationship_provenance_completeness: (
        RelationshipProvenanceCompleteness
    ) = RelationshipProvenanceCompleteness.LEGACY_UNSPECIFIED


class CandidateCausalRelevanceAudit(BaseModel):
    """Deterministic relevance result for one selected primary candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_event_id: str
    candidate_entity_id: str | None = None
    affected_entity_id: str | None = None
    relevance_policy_version: str = CAUSAL_RELEVANCE_POLICY_VERSION
    relevance_status: CausalRelevanceStatus
    path_semantic: CausalPathSemantic
    path_entity_ids: list[str] = Field(default_factory=list)
    path_relationship_ids: list[str] = Field(default_factory=list)
    path_predicates: list[str] = Field(default_factory=list)
    path_traversal_directions: list[CausalTraversalDirection] = Field(
        default_factory=list
    )
    path_relationship_origins: list[RelationshipOrigin | None] = Field(
        default_factory=list
    )
    path_relationship_source_systems: list[str] = Field(default_factory=list)
    path_hops: int = Field(default=0, ge=0)
    topology_component: float = Field(ge=0, le=1)
    hops: list[CausalPathHop] = Field(default_factory=list)
    reason: str
