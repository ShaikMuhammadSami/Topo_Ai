from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.incident_outcome import (
    ActionEffectiveness,
    OutcomeRootCause,
    RcaVerdict,
)


class HistoricalSupportLevel(str, Enum):
    NONE = "none"
    LIMITED = "limited"
    MODERATE = "moderate"
    STRONG = "strong"


class HistoricalAiStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class SimilarityFactorScore(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    available: bool
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    weight: float = Field(
        ge=0.0,
        le=1.0,
    )
    weighted_value: float = Field(
        ge=0.0,
        le=1.0,
    )


class SimilarityScoreBreakdown(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    factors: dict[
        str,
        SimilarityFactorScore,
    ] = Field(default_factory=dict)

    weighted_total: float = Field(
        ge=0.0,
        le=1.0,
    )
    available_weight: float = Field(
        ge=0.0,
        le=1.0,
    )


class HistoricalAnalysisContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    causal_analysis_id: str | None = None
    topology_snapshot_id: str | None = None

    root_event_id: str | None = None
    root_event_title: str | None = None
    root_event_source: str | None = None

    root_entity_id: str | None = None
    root_entity_kind: str | None = None
    root_service_name: str | None = None

    causal_change_kind: str | None = None
    causal_change_source: str | None = None

    business_capability: str | None = None
    owner_team: str | None = None

    environment: str | None = None
    severity: str


class HistoricalResolutionAction(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_instance_id: str
    action_type: str
    title: str
    effectiveness: ActionEffectiveness
    response_plan_action_id: str | None = None
    runbook_url: str | None = None


class HistoricalResolutionSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    rca_verdict: RcaVerdict
    rca_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    root_cause: OutcomeRootCause | None = None

    primary_resolution_action: (
        HistoricalResolutionAction | None
    ) = None

    time_to_mitigation_seconds: (
        int | None
    ) = Field(default=None, ge=0)
    time_to_resolution_seconds: (
        int | None
    ) = Field(default=None, ge=0)

    resolution_summary: str
    warnings: list[str] = Field(
        default_factory=list
    )


class HistoricalIncidentFeatureProfile(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    schema_version: str = "14d-structured-v1"
    feature_fingerprint: str

    incident_id: str
    incident_title: str
    incident_time: str
    resolved_at: str | None = None

    severity: str
    environment: str | None = None

    causal_analysis_id: str | None = None
    topology_snapshot_id: str | None = None

    root_event_id: str | None = None
    root_event_title: str | None = None
    root_event_source: str | None = None

    root_entity_id: str | None = None
    root_entity_kind: str | None = None
    root_service_name: str | None = None

    causal_change_kind: str | None = None
    causal_change_source: str | None = None

    owner_team: str | None = None
    business_capability: str | None = None
    criticality: str | None = None

    affected_entity_ids: list[str] = Field(
        default_factory=list
    )
    affected_entity_kinds: list[str] = Field(
        default_factory=list
    )

    topology_neighbor_ids: list[str] = Field(
        default_factory=list
    )
    topology_neighbor_kinds: list[str] = Field(
        default_factory=list
    )

    blast_radius_size: int = Field(
        default=0,
        ge=0,
    )

    resolution: (
        HistoricalResolutionSummary | None
    ) = None

    warnings: list[str] = Field(
        default_factory=list
    )


class HistoricalIncidentMatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    incident_title: str
    incident_time: str
    resolved_at: str | None = None

    feature_fingerprint: str

    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
    )
    similarity_breakdown: (
        SimilarityScoreBreakdown
    )

    matched_factors: list[str] = Field(
        default_factory=list
    )
    differing_factors: list[str] = Field(
        default_factory=list
    )

    resolution: HistoricalResolutionSummary


class HistoricalResolutionPattern(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_type: str
    action_title: str

    observed_cases: int = Field(ge=1)
    effective_cases: int = Field(ge=0)
    ineffective_cases: int = Field(ge=0)
    unknown_effectiveness_cases: int = Field(
        ge=0
    )

    supporting_incident_ids: list[str] = Field(
        default_factory=list
    )


class IncidentHistoricalIntelligence(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    analysis_context: HistoricalAnalysisContext

    historical_support_level: (
        HistoricalSupportLevel
    )

    matches: list[
        HistoricalIncidentMatch
    ] = Field(default_factory=list)

    resolution_patterns: list[
        HistoricalResolutionPattern
    ] = Field(default_factory=list)

    summary: str

    ai_summary: str | None = None
    ai_status: HistoricalAiStatus
    ai_provider: str | None = None
    ai_model: str | None = None

    warnings: list[str] = Field(
        default_factory=list
    )
