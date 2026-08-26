from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.causal_candidates import CandidateAdmissionEvidenceReference
from app.models.topology import (
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipSourceReference,
)


CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION = "causal-relevance-v1"
CAUSAL_RELEVANCE_POLICY_VERSION = "causal-relevance-v2"


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


class CausalRelevanceResolutionBasis(str, Enum):
    TOPOLOGY_ENTITY = "topology_entity"
    EXACT_IMMUTABLE_LINEAGE_ANCHOR = "exact_immutable_lineage_anchor"
    UNRESOLVED = "unresolved"


class LineageRelevanceBridgeState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    VALID = "valid"
    INELIGIBLE = "ineligible"
    INCOMPLETE = "incomplete"
    CONFLICT = "conflict"


class CausalTopologyPathState(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    SUPPORTED = "supported"
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


class LineageRelevanceAnchorAudit(BaseModel):
    """One exact SC-2 anchor and its pinned-topology evaluation."""

    model_config = ConfigDict(extra="forbid")

    anchor_entity_id: str
    anchor_kind: str
    image_digest: str = Field(pattern="^sha256:[0-9a-f]{64}$")
    bridge_state: LineageRelevanceBridgeState
    bridge_reason: str
    bridge_path_ids: list[str] = Field(default_factory=list)
    bridge_evidence_refs: list[CandidateAdmissionEvidenceReference] = Field(
        default_factory=list
    )
    source_change_id: str
    revision: str = Field(pattern="^[0-9a-f]{40}$")
    run_ids: list[str] = Field(default_factory=list)
    provider_evidence_ids: list[str] = Field(default_factory=list)
    topology_path_state: CausalTopologyPathState
    topology_path_semantic: CausalPathSemantic
    topology_path_entity_ids: list[str] = Field(default_factory=list)
    topology_path_relationship_ids: list[str] = Field(default_factory=list)
    topology_hops: int = Field(default=0, ge=0)
    topology_component: float = Field(default=0.0, ge=0, le=1)
    reason: str


class CandidateCausalRelevanceAudit(BaseModel):
    """Deterministic relevance result for one selected primary candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_event_id: str
    candidate_entity_id: str | None = None
    affected_entity_id: str | None = None
    relevance_policy_version: str = CAUSAL_RELEVANCE_TOPOLOGY_POLICY_VERSION
    resolution_basis: CausalRelevanceResolutionBasis | None = Field(
        default=None,
        description=(
            "Absent on historical v1 results. New results distinguish a "
            "topology-native identity from an immutable-lineage anchor."
        ),
    )
    relevance_anchor_entity_id: str | None = None
    relevance_anchor_kind: str | None = None
    bridge_state: LineageRelevanceBridgeState | None = None
    bridge_reason: str | None = None
    bridge_path_ids: list[str] = Field(default_factory=list)
    bridge_evidence_refs: list[CandidateAdmissionEvidenceReference] = Field(
        default_factory=list
    )
    bridge_source_change_id: str | None = None
    bridge_revision: str | None = None
    bridge_run_ids: list[str] = Field(default_factory=list)
    bridge_image_digest: str | None = None
    bridge_score: float | None = Field(default=None, ge=0, le=0)
    topology_path_state: CausalTopologyPathState | None = None
    anchor_audits: list[LineageRelevanceAnchorAudit] = Field(
        default_factory=list
    )
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
