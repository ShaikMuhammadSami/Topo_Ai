from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.incident_memory import (
    HistoricalAiStatus,
)
from app.models.response_intelligence import (
    IncidentResponseIntelligence,
    ResponseActionIntelligence,
)


class ExecutionReadinessStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    READ_ONLY_SAFE = "read_only_safe"
    NEEDS_MORE_EVIDENCE = (
        "needs_more_evidence"
    )
    NEEDS_VALIDATION = "needs_validation"
    BLOCKED = "blocked"
    READY_FOR_HUMAN_APPROVAL = (
        "ready_for_human_approval"
    )


class IncidentExecutionPosture(str, Enum):
    NO_MUTATIONS_PROPOSED = (
        "no_mutations_proposed"
    )
    MUTATIONS_BLOCKED = "mutations_blocked"
    MORE_EVIDENCE_REQUIRED = (
        "more_evidence_required"
    )
    VALIDATION_REQUIRED = (
        "validation_required"
    )
    HUMAN_APPROVAL_POSSIBLE = (
        "human_approval_possible"
    )


class ActionPrecondition(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    code: str
    title: str
    required: bool
    satisfied: bool
    reason: str
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class ExecutionReadinessTarget(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_ids: list[str] = Field(
        default_factory=list
    )
    change_event_id: str | None = None
    uniquely_identified: bool


class ActionApprovalContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    required: bool
    reason: str
    owner_team: str | None = None
    oncall_contact: str | None = None
    service_name: str | None = None
    suggested_roles: list[str] = Field(
        default_factory=list
    )


class FutureExecutionContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    eligible_for_future_execution: bool
    execution_authorized: Literal[False] = False
    execution_performed: Literal[False] = False
    interpretation: str


class ActionExecutionReadiness(
    ResponseActionIntelligence
):
    mutation: bool
    readiness_status: ExecutionReadinessStatus
    target: ExecutionReadinessTarget

    preconditions: list[
        ActionPrecondition
    ] = Field(default_factory=list)
    satisfied_preconditions: list[str] = Field(
        default_factory=list
    )
    missing_preconditions: list[str] = Field(
        default_factory=list
    )

    reasons: list[str] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(
        default_factory=list
    )
    cautions: list[str] = Field(
        default_factory=list
    )
    readiness_evidence_ids: list[str] = Field(
        default_factory=list
    )

    approval_context: ActionApprovalContext
    execution_contract: FutureExecutionContract


class IncidentExecutionReadiness(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    causal_analysis_id: str
    response_plan_reference: str
    policy_version: str

    overall_execution_posture: (
        IncidentExecutionPosture
    )
    response_intelligence: (
        IncidentResponseIntelligence
    )
    actions: list[
        ActionExecutionReadiness
    ] = Field(default_factory=list)

    deterministic_summary: str

    ai_summary: str | None = None
    ai_status: HistoricalAiStatus
    ai_provider: str | None = None
    ai_model: str | None = None

    warnings: list[str] = Field(
        default_factory=list
    )
