from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.execution_readiness import (
    ExecutionReadinessStatus,
    ExecutionReadinessTarget,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_intelligence import (
    CurrentEvidenceStrength,
    HistoricalActionSupportLevel,
    ResponseActionFamily,
    ResponseActionSemantics,
)
from app.models.response_plan import (
    ResponseActionCategory,
)


class ActionApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALIDATED = "invalidated"


class ActionApprovalEventType(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALIDATED = "invalidated"


class ActionApprovalRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_id: str = Field(
        min_length=1,
        max_length=1000,
    )
    reason: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator("action_id")
    @classmethod
    def normalize_action_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Action ID cannot be empty."
            )

        return normalized

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: str | None,
    ) -> str | None:
        normalized = (
            value.strip()
            if value is not None
            else None
        )
        return normalized or None


class ActionApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    reason: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: str | None,
    ) -> str | None:
        normalized = (
            value.strip()
            if value is not None
            else None
        )
        return normalized or None


class ActionApprovalRevocationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    reason: str = Field(
        min_length=1,
        max_length=4000,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Revocation reason cannot be empty."
            )

        return normalized


class ApprovalPreconditionSnapshot(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    code: str
    required: bool
    satisfied: bool
    evidence_ids: list[str] = Field(
        default_factory=list
    )


class ActionApprovalReadinessSnapshot(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    causal_analysis_id: str
    response_plan_reference: str
    policy_version: str

    action_id: str
    action_title: str
    action_family: ResponseActionFamily
    action_category: ResponseActionCategory
    action_semantics: ResponseActionSemantics
    risk: RecommendationRisk
    requires_human_approval: bool
    readiness_status: ExecutionReadinessStatus

    target: ExecutionReadinessTarget

    root_event_id: str
    target_event_id: str | None = None
    causal_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    current_evidence_strength: (
        CurrentEvidenceStrength
    )
    historical_support: (
        HistoricalActionSupportLevel
    )

    readiness_evidence_ids: list[str] = Field(
        default_factory=list
    )
    preconditions: list[
        ApprovalPreconditionSnapshot
    ] = Field(default_factory=list)

    owner_team: str | None = None
    oncall_contact: str | None = None
    service_name: str | None = None

    eligible_for_future_execution: bool


class ActionApprovalAuditEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str
    sequence: int = Field(ge=1)
    approval_id: str
    incident_id: str
    action_id: str
    event_type: ActionApprovalEventType
    from_status: ActionApprovalStatus | None
    to_status: ActionApprovalStatus

    actor_subject: str
    actor_display_name: str
    actor_roles: list[str] = Field(
        default_factory=list
    )
    authentication_type: str

    reason: str | None = None
    evidence_fingerprint: str
    occurred_at: datetime


class FutureApprovalContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    approval_reference_valid: bool
    requires_current_readiness_revalidation: (
        Literal[True]
    ) = True
    execution_performed: Literal[False] = False
    interpretation: str


class ActionApprovalView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    approval_id: str
    incident_id: str
    action_id: str
    action_family: ResponseActionFamily
    status: ActionApprovalStatus

    risk: RecommendationRisk
    requires_human_approval: bool
    policy_version: str
    readiness_status_at_request: (
        ExecutionReadinessStatus
    )

    evidence_fingerprint: str = Field(
        min_length=64,
        max_length=64,
    )
    target: ExecutionReadinessTarget
    readiness_snapshot: (
        ActionApprovalReadinessSnapshot
    )

    request_reason: str | None = None
    requested_by: str
    requested_by_display_name: str
    requested_by_roles: list[str] = Field(
        default_factory=list
    )
    requested_at: datetime

    decided_by: str | None = None
    decided_by_display_name: str | None = None
    decided_by_roles: list[str] = Field(
        default_factory=list
    )
    decided_at: datetime | None = None
    decision_reason: str | None = None

    expires_at: datetime

    revoked_by: str | None = None
    revoked_by_display_name: str | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

    created_at: datetime
    updated_at: datetime

    currently_valid: bool
    invalid_reason: str | None = None
    future_execution_contract: (
        FutureApprovalContract
    )


class ActionApprovalDetail(ActionApprovalView):
    audit_events: list[
        ActionApprovalAuditEvent
    ] = Field(default_factory=list)
