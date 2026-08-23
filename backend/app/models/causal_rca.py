from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.canonical_identity import (
    CanonicalIdentityResolution,
)
from app.models.causal_candidates import CausalCandidateSelectionAudit
from app.models.confidence_semantics import CausalConfidenceSemantics
from app.models.temporal import TemporalMetadata
from app.models.topology import (
    RelationshipOrigin,
    RelationshipProvenanceCompleteness,
    RelationshipSourceReference,
)


CAUSAL_EVIDENCE_LEDGER_VERSION = "tc4.v1"


class CausalNodeType(str, Enum):
    CHANGE_EVENT = "change_event"
    ENTITY = "entity"
    INCIDENT = "incident"


class CausalEdgeType(str, Enum):
    PRECEDES = "precedes"

    TOUCHES_ENTITY = "touches_entity"

    TOPOLOGY_PATH = "topology_path"

    CULMINATES_IN = "culminates_in"


class CausalEvidenceType(str, Enum):
    TEMPORAL = "temporal"

    CHANGE_EVENT = "change_event"

    ENTITY_LINK = "entity_link"

    EVENT_LINEAGE = "event_lineage"

    TOPOLOGY = "topology"

    INCIDENT = "incident"


class CausalConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CausalEvidenceStance(str, Enum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    MISSING = "missing"


class CausalEvidenceClaimType(str, Enum):
    SOURCE_CHANGE = "source_change"
    TEMPORAL_PRECEDENCE = "temporal_precedence"
    IDENTITY_RESOLUTION = "identity_resolution"
    ENTITY_LINKAGE = "entity_linkage"
    TOPOLOGY_PATH = "topology_path"
    RELATIONSHIP_PROVENANCE = "relationship_provenance"
    RUNTIME_FAILURE = "runtime_failure"
    ARTIFACT_PROVENANCE = "artifact_provenance"
    EVENT_LINEAGE = "event_lineage"


class CausalEvidenceQuality(str, Enum):
    DIRECT = "direct"
    STRONG = "strong"
    LIMITED = "limited"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


class CausalEvidenceSourceCategory(str, Enum):
    CHANGE = "change"
    TEMPORAL = "temporal"
    IDENTITY = "identity"
    TOPOLOGY = "topology"
    SIGNAL = "signal"
    ARTIFACT = "artifact"
    LINEAGE = "lineage"


class CausalEvidenceSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    source_system: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class CausalRelationshipEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_id: str
    predicate: str
    direction: str
    origin: RelationshipOrigin | None = None
    source_component: str | None = None
    source_references: list[RelationshipSourceReference] = Field(
        default_factory=list,
    )
    linker_version: str | None = None
    completeness: RelationshipProvenanceCompleteness


class CausalEvidenceLedgerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    hypothesis_id: str
    stance: CausalEvidenceStance
    claim_type: CausalEvidenceClaimType
    summary: str
    reason: str
    source_category: CausalEvidenceSourceCategory
    source_references: list[CausalEvidenceSourceReference] = Field(
        default_factory=list,
    )
    entity_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    change_event_ids: list[str] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None
    temporal: TemporalMetadata | None = None
    incident_boundary_at: str | None = None
    relationship: CausalRelationshipEvidenceReference | None = None
    identity_resolution: CanonicalIdentityResolution | None = None
    quality: CausalEvidenceQuality
    why_it_matters: str
    expectation_basis: str | None = None
    ledger_version: str = CAUSAL_EVIDENCE_LEDGER_VERSION

    @model_validator(mode="after")
    def validate_defensibility(self) -> "CausalEvidenceLedgerItem":
        has_reference = bool(
            self.source_references
            or self.entity_ids
            or self.relationship_ids
            or self.change_event_ids
            or self.signal_ids
            or self.snapshot_id
        )
        if not has_reference:
            raise ValueError(
                "Causal ledger evidence requires a defensible reference"
            )
        claim_is_defensible = {
            CausalEvidenceClaimType.SOURCE_CHANGE: bool(
                self.change_event_ids
            ),
            CausalEvidenceClaimType.TEMPORAL_PRECEDENCE: bool(
                self.change_event_ids and self.incident_boundary_at
            ),
            CausalEvidenceClaimType.IDENTITY_RESOLUTION: bool(
                self.change_event_ids and self.identity_resolution is not None
            ),
            CausalEvidenceClaimType.ENTITY_LINKAGE: bool(
                self.change_event_ids
                and (self.entity_ids or self.source_references)
            ),
            CausalEvidenceClaimType.TOPOLOGY_PATH: bool(
                self.snapshot_id
                and self.entity_ids
                and (
                    self.relationship_ids
                    or self.stance == CausalEvidenceStance.MISSING
                )
            ),
            CausalEvidenceClaimType.RELATIONSHIP_PROVENANCE: bool(
                self.snapshot_id and self.relationship_ids
            ),
            CausalEvidenceClaimType.RUNTIME_FAILURE: bool(
                self.signal_ids
            ),
            CausalEvidenceClaimType.ARTIFACT_PROVENANCE: bool(
                self.snapshot_id
                and self.entity_ids
                and self.relationship_ids
            ),
            CausalEvidenceClaimType.EVENT_LINEAGE: bool(
                len(self.change_event_ids) >= 2
            ),
        }[self.claim_type]
        if not claim_is_defensible:
            raise ValueError(
                "Causal ledger evidence lacks the references required by "
                f"claim type '{self.claim_type.value}'"
            )
        if (
            self.stance == CausalEvidenceStance.MISSING
            and not self.expectation_basis
        ):
            raise ValueError(
                "Missing evidence requires an explicit expectation basis"
            )
        if (
            self.stance != CausalEvidenceStance.MISSING
            and self.expectation_basis is not None
        ):
            raise ValueError(
                "expectation_basis is reserved for missing evidence"
            )
        return self


class CausalEvidenceLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_version: str = CAUSAL_EVIDENCE_LEDGER_VERSION
    hypothesis_id: str
    snapshot_id: str | None = None
    supporting: list[CausalEvidenceLedgerItem] = Field(
        default_factory=list,
    )
    contradicting: list[CausalEvidenceLedgerItem] = Field(
        default_factory=list,
    )
    missing: list[CausalEvidenceLedgerItem] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_stance_buckets(self) -> "CausalEvidenceLedger":
        buckets = (
            (self.supporting, CausalEvidenceStance.SUPPORTING),
            (self.contradicting, CausalEvidenceStance.CONTRADICTING),
            (self.missing, CausalEvidenceStance.MISSING),
        )
        for items, expected_stance in buckets:
            for item in items:
                if item.hypothesis_id != self.hypothesis_id:
                    raise ValueError(
                        "Ledger item belongs to a different hypothesis"
                    )
                if item.stance != expected_stance:
                    raise ValueError(
                        "Ledger item is stored in the wrong stance bucket"
                    )
        return self


class CausalAnalysisRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    lookback_minutes: int = Field(
        default=180,
        ge=1,
        le=10080,
    )

    after_minutes: int = Field(
        default=10,
        ge=0,
        le=1440,
    )

    minimum_change_score: float = Field(
        default=0,
        ge=0,
        le=100,
    )

    max_topology_hops: int = Field(
        default=4,
        ge=0,
        le=10,
    )

    max_hypotheses: int = Field(
        default=5,
        ge=1,
        le=25,
    )


class CausalNode(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    node_id: str

    node_type: CausalNodeType

    label: str

    occurred_at: str | None = None

    event_id: str | None = None

    entity_id: str | None = None

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )


class CausalEvidenceItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    evidence_id: str

    evidence_type: CausalEvidenceType

    source: str

    title: str

    detail: str

    observed_at: str | None = None

    event_id: str | None = None

    entity_id: str | None = None

    weight: float = Field(
        ge=0,
        le=1,
    )

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )


class CausalEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    edge_id: str

    source_node_id: str
    target_node_id: str

    relation: CausalEdgeType

    confidence: float = Field(
        ge=0,
        le=1,
    )

    reasons: list[str] = Field(
        default_factory=list
    )

    evidence_ids: list[str] = Field(
        default_factory=list
    )


class CausalChainStep(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    order: int

    node_id: str

    node_type: CausalNodeType

    label: str

    relation_from_previous: (
        CausalEdgeType | None
    ) = None

    confidence_from_previous: (
        float | None
    ) = None


class CausalHypothesis(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    hypothesis_id: str

    rank: int

    root_event_id: str

    root_source: str

    root_title: str

    target_event_id: str

    target_title: str

    affected_entity_id: str | None = None

    score: float = Field(
        ge=0,
        le=100,
    )

    confidence: float = Field(
        ge=0,
        le=1,
    )

    confidence_level: (
        CausalConfidenceLevel
    )

    confidence_semantics: CausalConfidenceSemantics | None = Field(
        default=None,
        description=(
            "TC-5 interpretation of the heuristic ranking. Historical "
            "payloads load without this field and are enriched in memory."
        ),
    )

    minutes_before_incident: (
        float | None
    ) = None

    summary: str

    reasons: list[str] = Field(
        default_factory=list
    )

    supporting_evidence_ids: list[
        str
    ] = Field(
        default_factory=list
    )

    evidence_ledger: CausalEvidenceLedger | None = Field(
        default=None,
        description=(
            "TC-4 durable evidence ledger. Historical analyses load with "
            "this field absent/null and are not retroactively enriched."
        ),
    )

    chain: list[
        CausalChainStep
    ] = Field(
        default_factory=list
    )


class CausalAnalysisResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    analysis_id: str

    incident_id: str

    incident_title: str

    incident_time: str

    topology_snapshot_id: (
        str | None
    )

    algorithm_version: str

    candidate_policy_version: str | None = Field(
        default=None,
        description=(
            "Candidate-selection policy used for this immutable analysis "
            "generation. Historical payloads load with null."
        ),
    )

    candidate_selection_audit: list[CausalCandidateSelectionAudit] = Field(
        default_factory=list,
        description=(
            "Deterministic raw-rank and eligibility audit for every "
            "incident change candidate considered by this generation."
        ),
    )

    generated_at: str

    parameters: dict[str, Any]

    candidate_count: int

    node_count: int
    edge_count: int
    evidence_count: int

    hypothesis_count: int

    top_hypothesis: (
        CausalHypothesis | None
    )

    confidence_semantics: CausalConfidenceSemantics | None = Field(
        default=None,
        description=(
            "TC-5 semantics for the top-ranked hypothesis, or an explicit "
            "insufficient-evidence state when no hypothesis exists."
        ),
    )

    hypotheses: list[
        CausalHypothesis
    ] = Field(
        default_factory=list
    )

    nodes: list[
        CausalNode
    ] = Field(
        default_factory=list
    )

    edges: list[
        CausalEdge
    ] = Field(
        default_factory=list
    )

    evidence: list[
        CausalEvidenceItem
    ] = Field(
        default_factory=list
    )
