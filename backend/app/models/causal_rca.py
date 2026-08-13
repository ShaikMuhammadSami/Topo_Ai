from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


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