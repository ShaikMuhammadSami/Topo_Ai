from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class RecommendationStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    DISMISSED = "dismissed"


class RecommendationRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationActionType(str, Enum):
    ROLLBACK_DEPLOYMENT = (
        "rollback_deployment"
    )

    RESTORE_REPLICA_COUNT = (
        "restore_replica_count"
    )

    RESTORE_CONFIGURATION = (
        "restore_configuration"
    )

    VERIFY_IMAGE_ACCESS = (
        "verify_image_access"
    )

    INVESTIGATE_RUNTIME = (
        "investigate_runtime"
    )


class RecommendationStep(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    order: int = Field(ge=1)

    title: str
    description: str

    command: str | None = None

    requires_approval: bool = False

    expected_result: str | None = None


class RemediationRecommendation(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    recommendation_id: str
    algorithm_version: str

    analysis_id: str
    hypothesis_id: str
    signal_id: str
    change_id: str

    generated_at: datetime

    title: str
    rationale: str

    action_type: (
        RecommendationActionType
    )

    status: RecommendationStatus

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    risk: RecommendationRisk

    cluster_name: str
    namespace: str | None = None

    target_entity_id: str | None = None
    target_entity_kind: str | None = None
    target_entity_name: str | None = None

    requires_approval: bool = True

    steps: list[
        RecommendationStep
    ] = Field(default_factory=list)

    expected_outcome: str

    verification_checks: list[str] = Field(
        default_factory=list
    )

    safety_notes: list[str] = Field(
        default_factory=list
    )

    evidence_ids: list[str] = Field(
        default_factory=list
    )

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )

    status_note: str | None = None
    applied_at: datetime | None = None


class RecommendationSummary(BaseModel):
    recommendation_id: str

    analysis_id: str
    signal_id: str

    generated_at: datetime

    title: str
    action_type: RecommendationActionType

    status: RecommendationStatus
    confidence: float
    risk: RecommendationRisk

    namespace: str | None

    target_entity_kind: str | None
    target_entity_name: str | None

    applied_at: datetime | None


class RecommendationStatusUpdate(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: RecommendationStatus

    note: str | None = Field(
        default=None,
        max_length=2000,
    )