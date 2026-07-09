from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)



class OrchestrationStatus(
    str,
    Enum,
):
    COMPLETED = "completed"
    SKIPPED = "skipped"


class IncidentOrchestrationResult(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    orchestration_id: str
    orchestration_version: str

    status: OrchestrationStatus
    message: str

    started_at: datetime
    completed_at: datetime

    signal_id: str
    signal_severity: str

    cluster_name: str
    namespace: str | None = None
    topology_snapshot_id: str | None = None

    analysis_id: str | None = None

    candidate_count: int = Field(
        default=0,
        ge=0,
    )

    hypothesis_count: int = Field(
        default=0,
        ge=0,
    )

    top_hypothesis_id: str | None = None
    top_hypothesis_title: str | None = None

    top_hypothesis_score: (
        float | None
    ) = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    recommendation_count: int = Field(
        default=0,
        ge=0,
    )

    recommendation_ids: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )

    parameters: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )