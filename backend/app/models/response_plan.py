from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.ownership import (
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
)
from app.models.recommendations import (
    RecommendationRisk,
)


class ResponsePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResponseActionCategory(str, Enum):
    INVESTIGATE = "investigate"
    VALIDATE = "validate"
    MITIGATE = "mitigate"
    ROLLBACK_CANDIDATE = (
        "rollback_candidate"
    )
    ESCALATE = "escalate"
    COMMUNICATE = "communicate"
    MONITOR = "monitor"
    RUNBOOK = "runbook"


class IncidentResponseAction(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_id: str
    sequence: int = Field(ge=1)

    category: ResponseActionCategory
    priority: ResponsePriority

    title: str
    description: str
    reason: str

    risk: RecommendationRisk

    requires_human_approval: bool = False

    owner_team: str | None = None
    oncall_contact: str | None = None

    entity_ids: list[str] = Field(
        default_factory=list
    )
    evidence_event_ids: list[str] = Field(
        default_factory=list
    )
    evidence_ids: list[str] = Field(
        default_factory=list
    )

    runbook_url: str | None = None

    @model_validator(mode="after")
    def require_approval_for_mutation(
        self,
    ) -> "IncidentResponseAction":
        if (
            self.category
            in {
                ResponseActionCategory
                .MITIGATE,
                ResponseActionCategory
                .ROLLBACK_CANDIDATE,
            }
            and not self
            .requires_human_approval
        ):
            raise ValueError(
                "Mitigation and rollback "
                "recommendations require human "
                "approval."
            )

        return self


class ResponseRootCause(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str
    event_title: str
    event_source: str
    event_kind: str | None = None
    occurred_at: str | None = None

    target_event_id: str | None = None
    target_event_title: str | None = None
    target_event_source: str | None = None
    target_event_kind: str | None = None
    target_occurred_at: str | None = None

    entity_id: str | None = None

    causal_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    confidence_level: str

    evidence_ids: list[str] = Field(
        default_factory=list
    )


class RollbackCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    available: bool
    reason: str
    change_event_id: str | None = None

    # This stays true even when no candidate is
    # available so a future caller cannot mistake
    # this response for execution authorization.
    requires_human_approval: bool = True


class RunbookReference(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    runbook_id: str
    title: str
    url: str
    source: str
    entity_id: str | None = None


class IncidentResponsePlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    causal_analysis_id: str

    response_priority: ResponsePriority
    response_priority_reason: str

    root_cause: ResponseRootCause

    primary_owner: (
        EntityOwnershipResolution | None
    ) = None

    business_context: IncidentOwnershipImpact

    recommended_actions: list[
        IncidentResponseAction
    ] = Field(default_factory=list)

    validation_checks: list[
        IncidentResponseAction
    ] = Field(default_factory=list)

    rollback_candidate: RollbackCandidate

    runbooks: list[RunbookReference] = Field(
        default_factory=list
    )

    escalation_targets: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )
