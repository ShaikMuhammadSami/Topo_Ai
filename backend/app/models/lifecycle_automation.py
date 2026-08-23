from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.signals import (
    NormalizedSignal,
)


class TopologyCheckpointReason(str, Enum):
    MANUAL = "manual"
    AUTOMATIC_CHANGE = "automatic_change"
    PERIODIC_RECONCILE = "periodic_reconcile"
    INCIDENT_BOUNDARY = "incident_boundary"


class TopologyCheckpointResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    snapshot_id: str
    previous_snapshot_id: str | None = None

    reason: TopologyCheckpointReason
    created: bool
    reused: bool
    debounced: bool = False

    state_digest: str
    detected_change_count: int = Field(
        default=0,
        ge=0,
    )

    trigger_event_ids: list[str] = Field(
        default_factory=list
    )
    trigger_signal_ids: list[str] = Field(
        default_factory=list
    )


class AutomaticIncidentAction(str, Enum):
    IGNORED = "ignored"
    CREATED = "created"
    CORRELATED = "correlated"
    DEGRADED = "degraded"


class AutomaticAnalysisState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING_TOPOLOGY = "pending_topology"
    PENDING_ENTITY = "pending_entity"
    PENDING_ANALYSIS = "pending_analysis"
    COMPLETED = "completed"
    COMPLETED_NO_HYPOTHESIS = (
        "completed_no_hypothesis"
    )
    REUSED = "reused"
    FAILED = "failed"


class AutomaticIncidentResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    signal_id: str
    action: AutomaticIncidentAction

    incident_id: str | None = None
    incident_created: bool = False
    incident_correlated: bool = False

    topology_snapshot_id: str | None = None

    causal_analysis_id: str | None = None
    automatic_analysis_state: (
        AutomaticAnalysisState
    ) = AutomaticAnalysisState.NOT_REQUIRED

    warnings: list[str] = Field(
        default_factory=list
    )


class FailureSignalBatchRequest(BaseModel):
    """
    Transport-neutral normalized failure input.

    Source adapters remain responsible for turning
    vendor-specific payloads into Topo's existing
    NormalizedSignal contract. Incident decisions are
    made by the deterministic lifecycle service.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    signals: list[NormalizedSignal] = Field(
        min_length=1,
        max_length=500,
    )


class FailureSignalBatchResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    received_count: int = Field(ge=0)
    created_signal_count: int = Field(ge=0)
    updated_signal_count: int = Field(ge=0)
    qualifying_failure_count: int = Field(ge=0)
    ignored_non_failure_count: int = Field(ge=0)

    incident_created_count: int = Field(ge=0)
    incident_correlated_count: int = Field(ge=0)

    results: list[AutomaticIncidentResult] = Field(
        default_factory=list
    )


class LifecycleStatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    cluster_name: str | None = None

    last_successful_discovery_at: str | None = None
    last_topology_checkpoint_id: str | None = None
    last_topology_checkpoint_at: str | None = None
    last_topology_checkpoint_reason: (
        TopologyCheckpointReason | None
    ) = None

    latest_change_event_id: str | None = None
    latest_change_event_at: str | None = None

    latest_failure_signal_id: str | None = None
    latest_failure_signal_at: str | None = None

    latest_incident_id: str | None = None
    latest_incident_correlation: str | None = None
    automatic_analysis_state: (
        AutomaticAnalysisState | None
    ) = None

    checkpoint_debounce_seconds: int = Field(
        ge=0
    )
    incident_correlation_window_minutes: int = Field(
        ge=1
    )


class IncidentLifecycleStatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str
    automatic_analysis_state: AutomaticAnalysisState
    topology_snapshot_id: str | None = None
    affected_entity_id: str | None = None
    causal_analysis_id: str | None = None
    briefing_ready: bool = False
    retryable: bool = False
    message: str
