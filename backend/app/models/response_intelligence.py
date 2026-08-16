from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.incident_memory import (
    HistoricalAiStatus,
    HistoricalResolutionPattern,
)
from app.models.incident_outcome import (
    ActionEffectiveness,
    RcaVerdict,
)
from app.models.response_plan import (
    IncidentResponseAction,
    IncidentResponsePlan,
    ResponsePriority,
    RollbackCandidate,
)


class ResponseActionGroup(str, Enum):
    RECOMMENDED = "recommended"
    VALIDATION = "validation"


class ResponseActionFamily(str, Enum):
    ROLLBACK = "rollback"
    CONFIGURATION_REVERT = (
        "configuration_revert"
    )
    PIPELINE_REVERT = "pipeline_revert"
    INFRASTRUCTURE_REVERT = (
        "infrastructure_revert"
    )
    RESTART = "restart"
    SCALE = "scale"
    TRAFFIC_SHIFT = "traffic_shift"
    OTHER_MITIGATION = "other_mitigation"
    INVESTIGATE = "investigate"
    VALIDATE = "validate"
    ESCALATE = "escalate"
    COMMUNICATE = "communicate"
    MONITOR = "monitor"
    RUNBOOK = "runbook"


class ResponseActionSemantics(str, Enum):
    MITIGATION = "mitigation"
    INVESTIGATION = "investigation"
    VALIDATION = "validation"
    COORDINATION = "coordination"
    MONITORING = "monitoring"
    RUNBOOK = "runbook"


class CurrentEvidenceStrength(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class HistoricalActionSupportLevel(
    str,
    Enum,
):
    LIMITED = "limited"
    SUPPORTED = "supported"
    STRONGLY_SUPPORTED = (
        "strongly_supported"
    )
    CONFLICTING = "conflicting"
    INSUFFICIENT_HISTORY = (
        "insufficient_history"
    )
    NOT_APPLICABLE = "not_applicable"


class CombinedDecisionSupport(str, Enum):
    CURRENT_ONLY = "current_only"
    HISTORICALLY_LIMITED = (
        "historically_limited"
    )
    HISTORICALLY_SUPPORTED = (
        "historically_supported"
    )
    HISTORICALLY_STRONGLY_SUPPORTED = (
        "historically_strongly_supported"
    )
    HISTORICALLY_CONFLICTING = (
        "historically_conflicting"
    )
    INSUFFICIENT_HISTORY = (
        "insufficient_history"
    )
    NOT_APPLICABLE = "not_applicable"


class HistoricalActionIncidentEvidence(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    incident_title: str
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
    )
    rca_verdict: RcaVerdict
    action_type: str
    action_effectiveness: ActionEffectiveness
    time_to_mitigation_seconds: (
        int | None
    ) = Field(default=None, ge=0)
    important_differences: list[str] = Field(
        default_factory=list
    )


class HistoricalMitigationTiming(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    effective_case_count: int = Field(ge=2)
    median_mitigation_seconds: float = Field(
        ge=0.0
    )
    minimum_mitigation_seconds: int = Field(
        ge=0
    )
    maximum_mitigation_seconds: int = Field(
        ge=0
    )
    interpretation: str


class HistoricalActionSupport(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    level: HistoricalActionSupportLevel
    score: float = Field(
        ge=0.0,
        le=1.0,
    )
    similar_incident_count: int = Field(ge=0)
    action_observed_count: int = Field(ge=0)
    effective_count: int = Field(ge=0)
    ineffective_count: int = Field(ge=0)
    unknown_effect_count: int = Field(ge=0)
    high_similarity_support_count: int = Field(
        ge=0
    )
    supporting_incident_ids: list[str] = Field(
        default_factory=list
    )
    contradicting_incident_ids: list[str] = Field(
        default_factory=list
    )
    support_reasons: list[str] = Field(
        default_factory=list
    )
    caution_reasons: list[str] = Field(
        default_factory=list
    )
    incident_evidence: list[
        HistoricalActionIncidentEvidence
    ] = Field(default_factory=list)
    mitigation_timing: (
        HistoricalMitigationTiming | None
    ) = None


class ResponseActionIntelligence(
    IncidentResponseAction
):
    baseline_group: ResponseActionGroup
    baseline_rank: int = Field(ge=1)
    action_family: ResponseActionFamily
    action_semantics: ResponseActionSemantics
    current_evidence_strength: (
        CurrentEvidenceStrength
    )
    historical_support: HistoricalActionSupport
    combined_decision_support: (
        CombinedDecisionSupport
    )


class RollbackResponseIntelligence(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    baseline: RollbackCandidate
    historical_support: HistoricalActionSupport


class IncidentResponseIntelligence(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    response_plan_reference: str
    causal_analysis_id: str
    response_priority: ResponsePriority
    response_priority_reason: str

    baseline_response_plan: IncidentResponsePlan
    actions: list[
        ResponseActionIntelligence
    ] = Field(default_factory=list)
    rollback_candidate: (
        RollbackResponseIntelligence
    )

    historical_resolution_patterns: list[
        HistoricalResolutionPattern
    ] = Field(default_factory=list)
    overall_historical_support: (
        HistoricalActionSupportLevel
    )
    deterministic_summary: str

    ai_summary: str | None = None
    ai_status: HistoricalAiStatus
    ai_provider: str | None = None
    ai_model: str | None = None

    warnings: list[str] = Field(
        default_factory=list
    )
