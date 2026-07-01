from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.changes import (
    ChangeCategory,
    ChangeImportance,
    ChangeType,
)


class EvidenceDirection(str, Enum):
    SUPPORTING = "supporting"
    COUNTER = "counter"


class IncidentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    direction: EvidenceDirection

    code: str
    summary: str

    weight: float = Field(
        ge=-1.0,
        le=1.0,
    )

    source_type: str
    source_id: str

    observed_at: datetime | None = None

    related_entity_ids: list[str] = Field(
        default_factory=list
    )

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )


class RootCauseHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    rank: int = Field(ge=1)

    change_id: str

    title: str
    explanation: str

    score: float = Field(
        ge=0.0,
        le=1.0,
    )

    change_type: ChangeType
    category: ChangeCategory
    importance: ChangeImportance

    change_detected_at: datetime

    minutes_before_signal: float

    graph_distance: int | None = None

    affected_entity_id: str | None = None
    changed_entity_id: str | None = None
    changed_entity_kind: str | None = None
    changed_entity_name: str | None = None

    supporting_evidence: list[
        IncidentEvidence
    ] = Field(default_factory=list)

    counter_evidence: list[
        IncidentEvidence
    ] = Field(default_factory=list)

    scoring_components: dict[
        str,
        float,
    ] = Field(default_factory=dict)


class IncidentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    algorithm_version: str

    signal_id: str
    topology_snapshot_id: str

    generated_at: datetime

    incident_title: str

    cluster_name: str
    namespace: str | None = None

    symptom_reason: str | None = None
    symptom_summary: str
    symptom_entity_id: str | None = None

    signal_first_observed_at: datetime
    signal_last_observed_at: datetime

    lookback_minutes: int
    grace_minutes: int
    max_graph_hops: int

    candidate_count: int

    hypotheses: list[
        RootCauseHypothesis
    ] = Field(default_factory=list)

    warnings: list[str] = Field(
        default_factory=list
    )


class IncidentAnalysisSummary(BaseModel):
    analysis_id: str
    signal_id: str

    generated_at: datetime

    incident_title: str

    cluster_name: str
    namespace: str | None

    candidate_count: int
    hypothesis_count: int

    top_hypothesis_title: str | None
    top_hypothesis_score: float | None