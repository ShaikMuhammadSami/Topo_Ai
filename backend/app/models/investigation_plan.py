from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.incident_explanation import (
    ExplanationProvider,
)


class InvestigationPlanStatus(
    str,
    Enum,
):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InvestigationStepStatus(
    str,
    Enum,
):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class InvestigationCommandType(
    str,
    Enum,
):
    KUBECTL = "kubectl"
    HTTP = "http"
    DNS = "dns"
    NONE = "none"


class GeneratedInvestigationStep(
    BaseModel
):
    """
    Every field is required for Groq strict
    structured output.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    sequence: int = Field(
        ge=1,
        le=50,
    )

    title: str = Field(
        min_length=1,
        max_length=500,
    )

    objective: str = Field(
        min_length=1,
        max_length=3000,
    )

    command_type: (
        InvestigationCommandType
    )

    command: str | None

    target: str = Field(
        min_length=1,
        max_length=1000,
    )

    expected_observation: str = Field(
        min_length=1,
        max_length=3000,
    )

    success_criteria: str = Field(
        min_length=1,
        max_length=3000,
    )

    failure_indication: str = Field(
        min_length=1,
        max_length=3000,
    )

    evidence_ids: list[str]


class GeneratedInvestigationPlan(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    title: str
    objective: str
    incident_summary: str

    steps: list[
        GeneratedInvestigationStep
    ]

    evidence_gaps: list[str]

    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )


class InvestigationPlanGenerateRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    provider: ExplanationProvider = (
        ExplanationProvider.AUTO
    )

    force_regenerate: bool = False


class InvestigationStepUpdateRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: (
        InvestigationStepStatus | None
    ) = None

    finding: str | None = Field(
        default=None,
        max_length=8000,
    )

    responder_notes: str | None = Field(
        default=None,
        max_length=8000,
    )

    @model_validator(mode="after")
    def require_change(
        self,
    ) -> "InvestigationStepUpdateRequest":
        if (
            self.status is None
            and self.finding is None
            and self.responder_notes is None
        ):
            raise ValueError(
                "Provide status, finding, "
                "or responder_notes."
            )

        return self


class InvestigationStepView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    step_id: str
    plan_id: str
    incident_id: str

    sequence: int

    title: str
    objective: str

    command_type: (
        InvestigationCommandType
    )

    command: str | None
    target: str

    expected_observation: str
    success_criteria: str
    failure_indication: str

    evidence_ids: list[str]

    status: InvestigationStepStatus

    finding: str | None
    responder_notes: str | None
    completed_at: str | None

    created_at: str
    updated_at: str


class InvestigationPlanSummary(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    plan_id: str
    incident_id: str

    title: str
    objective: str

    provider: ExplanationProvider
    model_name: str | None

    prompt_version: str
    grounding_hash: str

    status: InvestigationPlanStatus

    overall_confidence: float

    step_count: int
    completed_step_count: int
    blocked_step_count: int

    created_at: str
    updated_at: str


class InvestigationPlanDetail(
    InvestigationPlanSummary
):
    incident_summary: str

    evidence_gaps: list[str]
    warnings: list[str]

    evidence_count: int

    steps: list[
        InvestigationStepView
    ]