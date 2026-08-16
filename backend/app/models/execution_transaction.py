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

from app.models.action_approval import (
    ApprovalPreconditionSnapshot,
)
from app.models.execution_readiness import (
    ExecutionReadinessStatus,
    ExecutionReadinessTarget,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_intelligence import (
    ResponseActionFamily,
    ResponseActionSemantics,
)
from app.models.response_plan import (
    ResponseActionCategory,
)


class ExecutionIntentStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class ExecutionIntentEventType(str, Enum):
    CREATED = "created"
    CLAIMED = "claimed"
    CLAIM_EXPIRED = "claim_expired"
    RELEASED = "released"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class ExecutionIntentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(
        min_length=1,
        max_length=255,
    )

    @field_validator("approval_id")
    @classmethod
    def normalize_approval_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Approval ID cannot be empty."
            )

        return normalized


class ExecutionIntentCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
                "Cancellation reason cannot be empty."
            )

        return normalized


class ExecutionContractSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    incident_id: str
    action_id: str
    action_family: ResponseActionFamily
    action_category: ResponseActionCategory
    action_semantics: ResponseActionSemantics

    policy_version: str
    approval_evidence_fingerprint: str = Field(
        min_length=64,
        max_length=64,
    )
    target: ExecutionReadinessTarget

    risk: RecommendationRisk
    requires_human_approval: bool
    created_from_readiness_status: (
        ExecutionReadinessStatus
    )

    causal_analysis_id: str
    response_plan_reference: str
    root_event_id: str
    target_event_id: str | None = None
    readiness_evidence_ids: list[str] = Field(
        default_factory=list
    )
    preconditions: list[
        ApprovalPreconditionSnapshot
    ] = Field(default_factory=list)

    requires_pre_execution_revalidation: (
        Literal[True]
    ) = True
    execution_performed: Literal[False] = False


class ExecutionIntentAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    sequence: int = Field(ge=1)
    execution_id: str
    incident_id: str
    approval_id: str
    action_id: str
    event_type: ExecutionIntentEventType
    from_status: ExecutionIntentStatus | None
    to_status: ExecutionIntentStatus

    actor_subject: str
    actor_display_name: str
    actor_roles: list[str] = Field(
        default_factory=list
    )
    authentication_type: str

    claim_generation: int = Field(ge=0)
    reason: str | None = None
    occurred_at: datetime


class FutureExecutionTransactionContract(
    BaseModel
):
    model_config = ConfigDict(extra="forbid")

    intent_reference_valid: bool
    requires_approval_revalidation: (
        Literal[True]
    ) = True
    requires_readiness_revalidation: (
        Literal[True]
    ) = True
    requires_pre_execution_revalidation: (
        Literal[True]
    ) = True
    execution_performed: Literal[False] = False
    interpretation: str


class ExecutionIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    incident_id: str
    approval_id: str
    action_id: str
    action_family: ResponseActionFamily
    status: ExecutionIntentStatus

    approval_evidence_fingerprint: str = Field(
        min_length=64,
        max_length=64,
    )
    policy_version: str
    target: ExecutionReadinessTarget
    risk: RecommendationRisk
    idempotency_key: str = Field(
        min_length=64,
        max_length=64,
    )
    execution_snapshot: ExecutionContractSnapshot

    created_by: str
    created_by_display_name: str
    created_by_roles: list[str] = Field(
        default_factory=list
    )
    created_at: datetime

    claimed_by: str | None = None
    claimed_by_display_name: str | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    claim_generation: int = Field(ge=0)
    attempt_count: int = Field(ge=0)

    cancelled_by: str | None = None
    cancelled_by_display_name: str | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None

    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    expired_at: datetime | None = None
    expiration_reason: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    result_reference: str | None = None

    row_version: int = Field(ge=1)
    updated_at: datetime

    approval_currently_valid: bool
    currently_claimable: bool
    retryable: bool
    invalid_reason: str | None = None
    execution_performed: Literal[False] = False
    future_execution_contract: (
        FutureExecutionTransactionContract
    )


class ExecutionIntentDetail(ExecutionIntentView):
    audit_events: list[
        ExecutionIntentAuditEvent
    ] = Field(default_factory=list)
