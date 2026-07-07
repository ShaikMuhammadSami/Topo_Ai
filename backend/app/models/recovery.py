from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class RecoveryStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class RecoveryCheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class RecoveryCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    code: str
    title: str

    status: RecoveryCheckStatus

    summary: str

    expected: str | None = None
    observed: str | None = None

    source_type: str
    source_id: str

    checked_at: datetime

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )


class RecoveryVerification(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    verification_id: str
    algorithm_version: str

    recommendation_id: str
    analysis_id: str
    signal_id: str

    pre_snapshot_id: str
    post_snapshot_id: str

    generated_at: datetime
    applied_at: datetime

    status: RecoveryStatus
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    summary: str

    cluster_name: str
    namespace: str | None = None

    target_entity_id: str | None = None
    target_entity_kind: str | None = None
    target_entity_name: str | None = None

    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)

    checks: list[RecoveryCheck] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )


class RecoveryVerificationSummary(
    BaseModel
):
    verification_id: str

    recommendation_id: str
    analysis_id: str
    signal_id: str

    generated_at: datetime

    status: RecoveryStatus
    confidence: float

    summary: str

    cluster_name: str
    namespace: str | None

    target_entity_kind: str | None
    target_entity_name: str | None

    passed_count: int
    failed_count: int
    unknown_count: int