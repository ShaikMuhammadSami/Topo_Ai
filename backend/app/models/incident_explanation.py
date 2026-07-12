from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class ExplanationProvider(str, Enum):
    AUTO = "auto"
    GROQ = "groq"
    DETERMINISTIC = "deterministic"


class EvidenceType(str, Enum):
    INCIDENT = "incident"
    SIGNAL = "signal"
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    RECOVERY = "recovery"
    TOPOLOGY = "topology"
    OWNERSHIP = "ownership"
    NETWORK = "network"


class GroundingEvidence(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    evidence_id: str
    evidence_type: EvidenceType
    summary: str
    observed_at: str | None

    data: dict[str, Any] = Field(
        default_factory=dict
    )


class ExplanationClaim(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    text: str
    evidence_ids: list[str]
    confidence: float


class ExplanationTimelineItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    timestamp: str | None
    event: str
    evidence_ids: list[str]


class ExplanationAction(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    priority: int
    action: str
    rationale: str
    evidence_ids: list[str]


class GeneratedIncidentExplanation(BaseModel):
    """
    Every field intentionally has no default.

    This makes every field required in the JSON
    Schema, which is needed for Groq strict
    structured output.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    executive_summary: str
    technical_summary: str
    probable_root_cause: str
    business_impact: str

    response_steps: list[
        ExplanationAction
    ]

    timeline: list[
        ExplanationTimelineItem
    ]

    claims: list[
        ExplanationClaim
    ]

    uncertainty: list[str]

    overall_confidence: float


class IncidentExplanationGenerateRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    provider: ExplanationProvider = (
        ExplanationProvider.AUTO
    )

    force_regenerate: bool = False


class IncidentExplanationResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    explanation_id: str
    incident_id: str

    topology_snapshot_id: str | None
    analysis_id: str | None

    provider: ExplanationProvider
    model_name: str | None

    prompt_version: str
    grounding_hash: str

    confidence: float
    generated_at: str

    explanation: GeneratedIncidentExplanation

    evidence: list[GroundingEvidence]
    warnings: list[str]