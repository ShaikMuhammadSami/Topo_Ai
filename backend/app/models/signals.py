from datetime import datetime
from enum import Enum
from typing import Any
from app.models.orchestration import (
    IncidentOrchestrationResult,
)
from pydantic import BaseModel, ConfigDict, Field


class SignalType(str, Enum):
    KUBERNETES_EVENT = "kubernetes_event"


class SignalSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SignalCategory(str, Enum):
    AVAILABILITY = "availability"
    HEALTH = "health"
    SCHEDULING = "scheduling"
    IMAGE = "image"
    STORAGE = "storage"
    CONFIGURATION = "configuration"
    LIFECYCLE = "lifecycle"
    SECURITY = "security"
    OTHER = "other"


class NormalizedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    fingerprint: str

    signal_type: SignalType
    severity: SignalSeverity
    category: SignalCategory

    source_system: str

    title: str
    summary: str

    reason: str | None = None
    action: str | None = None

    first_observed_at: datetime
    last_observed_at: datetime

    occurrence_count: int = Field(
        default=1,
        ge=1,
    )

    cluster_name: str

    namespace: str | None = None

    topology_snapshot_id: str | None = None

    involved_entity_id: str | None = None

    involved_object_uid: str | None = None
    involved_object_kind: str | None = None
    involved_object_name: str | None = None

    reporting_controller: str | None = None
    reporting_instance: str | None = None

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )

    raw_payload: dict[str, Any] = Field(
        default_factory=dict
    )


class SignalSummary(BaseModel):
    signal_id: str

    signal_type: SignalType
    severity: SignalSeverity
    category: SignalCategory

    title: str
    reason: str | None

    first_observed_at: datetime
    last_observed_at: datetime

    occurrence_count: int

    cluster_name: str
    namespace: str | None
    topology_snapshot_id: str | None = None

    involved_entity_id: str | None

    involved_object_kind: str | None
    involved_object_name: str | None


class SignalIngestionResult(BaseModel):
    source_system: str
    cluster_name: str
    namespace: str | None

    collected_count: int
    created_count: int
    updated_count: int

    mapped_entity_count: int
    unmapped_entity_count: int

    severity_counts: dict[str, int] = Field(
        default_factory=dict
    )
    
    auto_orchestrate: bool = False
    orchestrated_count: int = 0
    skipped_orchestration_count: int = 0
    orchestration_results: list[
        IncidentOrchestrationResult
    ] = Field(default_factory=list)