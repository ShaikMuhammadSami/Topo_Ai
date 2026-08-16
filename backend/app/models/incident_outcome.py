from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.incident_records import (
    IncidentStatus,
)


class RcaVerdict(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = (
        "partially_confirmed"
    )
    NOT_CONFIRMED = "not_confirmed"
    INCONCLUSIVE = "inconclusive"


class ResponseActionResult(str, Enum):
    SUCCESSFUL = "successful"
    FAILED = "failed"
    NO_EFFECT = "no_effect"
    UNKNOWN = "unknown"


class ActionEffectiveness(str, Enum):
    EFFECTIVE = "effective"
    INEFFECTIVE = "ineffective"
    UNKNOWN = "unknown"


class RecommendationFollowThrough(
    str,
    Enum,
):
    FOLLOWED = "followed"
    NOT_FOLLOWED = "not_followed"
    UNKNOWN = "unknown"


class OutcomeFactSource(str, Enum):
    RESPONDER = "responder"
    INFERRED = "inferred"
    CHANGE_EVENT = "change_event"
    LEGACY_RECOMMENDATION = (
        "legacy_recommendation"
    )


class ReportedRootCause(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str | None = None
    entity_id: str | None = None
    event_source: str | None = None
    title: str = Field(
        min_length=1,
        max_length=2000,
    )
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class ResponseActionObservationInput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_instance_id: str | None = None
    response_plan_action_id: str | None = None
    change_event_id: str | None = None

    action_type: str = Field(
        min_length=1,
        max_length=200,
    )
    title: str = Field(
        min_length=1,
        max_length=1000,
    )

    actor: str | None = Field(
        default=None,
        max_length=500,
    )
    source: str = Field(
        default="responder",
        max_length=200,
    )

    started_at: datetime | None = None
    completed_at: datetime | None = None

    target_entity_ids: list[str] = Field(
        default_factory=list
    )

    result: ResponseActionResult = (
        ResponseActionResult.UNKNOWN
    )

    # This is explicit responder evidence. It is
    # intentionally distinct from `result`: an
    # action can complete successfully without
    # resolving the incident.
    recovery_confirmed: bool | None = None

    notes: str | None = Field(
        default=None,
        max_length=8000,
    )
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class RecommendationDecisionInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    response_plan_action_id: str
    follow_through: (
        RecommendationFollowThrough
    )
    reason: str | None = Field(
        default=None,
        max_length=4000,
    )
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class IncidentOutcomeUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None

    resolution_summary: str | None = Field(
        default=None,
        max_length=12000,
    )

    final_root_cause: (
        ReportedRootCause | None
    ) = None

    # Explicit responder overrides are allowed and
    # retain responder provenance in the result.
    rca_verdict: RcaVerdict | None = None
    rca_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    primary_resolution_action_id: (
        str | None
    ) = None

    actions: list[
        ResponseActionObservationInput
    ] = Field(default_factory=list)

    recommendation_decisions: list[
        RecommendationDecisionInput
    ] = Field(default_factory=list)


class OutcomeRootCause(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str | None = None
    entity_id: str | None = None
    event_source: str | None = None
    title: str
    source: OutcomeFactSource
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class IncidentResponseActionObservation(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_instance_id: str
    response_plan_action_id: str | None = None
    change_event_id: str | None = None

    action_type: str
    title: str
    actor: str | None = None
    source: str

    started_at: datetime | None = None
    completed_at: datetime | None = None

    target_entity_ids: list[str] = Field(
        default_factory=list
    )
    result: ResponseActionResult
    recovery_confirmed: bool | None = None

    effectiveness: ActionEffectiveness
    effectiveness_reason: str

    notes: str | None = None
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class ResponsePlanActionOutcome(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    response_plan_action_id: str
    title: str
    category: str

    follow_through: (
        RecommendationFollowThrough
    )
    effectiveness: ActionEffectiveness

    matched_action_instance_ids: list[
        str
    ] = Field(default_factory=list)
    evidence_ids: list[str] = Field(
        default_factory=list
    )
    reason: str


class IncidentOutcome(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    outcome_id: str
    incident_id: str

    status: IncidentStatus

    causal_analysis_id: str | None = None
    response_plan_reference: str | None = None
    historical_topology_snapshot_id: (
        str | None
    ) = None

    started_at: datetime
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None

    time_to_mitigation_seconds: (
        int | None
    ) = Field(default=None, ge=0)
    time_to_resolution_seconds: (
        int | None
    ) = Field(default=None, ge=0)

    original_root_cause: (
        OutcomeRootCause | None
    ) = None
    final_root_cause: (
        OutcomeRootCause | None
    ) = None

    rca_verdict: RcaVerdict
    rca_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    resolution_summary: str

    actions_taken: list[
        IncidentResponseActionObservation
    ] = Field(default_factory=list)

    primary_resolution_action: (
        IncidentResponseActionObservation
        | None
    ) = None

    response_plan_actions: list[
        ResponsePlanActionOutcome
    ] = Field(default_factory=list)

    recommendations_followed: list[str] = (
        Field(default_factory=list)
    )
    recommendations_not_followed: list[
        str
    ] = Field(default_factory=list)
    recommendations_unknown: list[str] = (
        Field(default_factory=list)
    )

    effective_action_ids: list[str] = Field(
        default_factory=list
    )
    ineffective_action_ids: list[str] = (
        Field(default_factory=list)
    )

    evidence_event_ids: list[str] = Field(
        default_factory=list
    )
    evidence_ids: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )
