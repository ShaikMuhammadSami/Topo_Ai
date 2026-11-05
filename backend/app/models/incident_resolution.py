from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.recovery import (
    RecoveryCheckStatus,
    RecoveryStatus,
)


class IncidentResolutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IncidentResolutionTarget(
    IncidentResolutionModel
):
    tenant_id: str
    cluster_name: str
    namespace: str | None = None
    workload_entity_id: str | None = None
    workload_kind: str | None = None
    workload_name: str | None = None


class IncidentResolutionEvidence(
    IncidentResolutionModel
):
    snapshot_id: str
    collected_at: datetime
    collector_name: str
    collector_version: str
    max_age_seconds: int = Field(ge=1)
    collection_mode: Literal[
        "persisted_snapshot"
    ] = "persisted_snapshot"
    live_collection_requested: Literal[False] = False


class IncidentResolutionPlannedCheck(
    IncidentResolutionModel
):
    code: str
    title: str
    description: str
    required: bool = True


class IncidentResolutionCheck(
    IncidentResolutionModel
):
    code: str
    title: str
    status: RecoveryCheckStatus
    summary: str
    required: bool = True
    expected: str | None = None
    observed: str | None = None
    source_type: str
    source_id: str
    checked_at: datetime
    evidence_references: list[str] = Field(
        default_factory=list
    )


class IncidentResolutionPlan(
    IncidentResolutionModel
):
    incident_id: str
    incident_status: str
    target: IncidentResolutionTarget
    evidence: IncidentResolutionEvidence | None
    checks: list[
        IncidentResolutionPlannedCheck
    ] = Field(default_factory=list)
    kubectl_commands: list[str] = Field(
        default_factory=list
    )
    can_check: bool
    limitation: str | None = None
    infrastructure_mutation: Literal[False] = False


class IncidentResolutionCheckRequest(
    IncidentResolutionModel
):
    snapshot_id: str = Field(min_length=3)


class IncidentResolutionCheckResult(
    IncidentResolutionModel
):
    check_id: str
    incident_id: str
    generated_at: datetime
    status: RecoveryStatus
    summary: str
    target: IncidentResolutionTarget
    evidence: IncidentResolutionEvidence
    checks: list[IncidentResolutionCheck] = Field(
        default_factory=list
    )
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    eligible_to_resolve: bool
    resolution_note: str | None = None
    infrastructure_mutation: Literal[False] = False
