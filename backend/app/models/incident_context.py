from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.ownership import (
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
)
from app.models.confidence_semantics import CausalConfidenceSemantics


class IncidentOperationalContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str

    causal_analysis_id: str

    root_event_id: str | None = None
    root_event_title: str | None = None
    root_event_source: str | None = None

    root_entity_id: str | None = None
    causal_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    causal_confidence_semantics: CausalConfidenceSemantics | None = None

    root_cause_ownership: (
        EntityOwnershipResolution | None
    ) = None

    overall_business_impact: (
        IncidentOwnershipImpact
    )

    escalation_targets: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )
