from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RECOMMENDED = "recommended"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class IncidentSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IncidentRecordView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    fingerprint: str

    status: IncidentStatus
    severity: IncidentSeverity

    title: str
    summary: str

    cluster_name: str
    namespace: str | None = None

    primary_signal_id: str
    latest_signal_id: str | None = None

    topology_snapshot_id: str | None = None

    affected_entity_id: str | None = None
    affected_object_kind: str | None = None
    affected_object_name: str | None = None

    first_observed_at: datetime
    last_observed_at: datetime

    latest_analysis_id: str | None = None
    top_hypothesis_title: str | None = None
    top_hypothesis_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    recommendation_count: int = 0
    latest_recommendation_id: str | None = None

    recovery_status: str | None = None
    latest_recovery_verification_id: str | None = None

    occurrence_count: int = 1

    created_at: datetime
    updated_at: datetime

    status_note: str | None = None


class IncidentRecordSummary(BaseModel):
    incident_id: str

    status: IncidentStatus
    severity: IncidentSeverity

    title: str

    cluster_name: str
    namespace: str | None

    affected_object_kind: str | None
    affected_object_name: str | None

    first_observed_at: datetime
    last_observed_at: datetime

    top_hypothesis_title: str | None
    top_hypothesis_score: float | None

    recommendation_count: int
    recovery_status: str | None

    occurrence_count: int


class IncidentStatusUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: IncidentStatus

    note: str | None = Field(
        default=None,
        max_length=2000,
    )