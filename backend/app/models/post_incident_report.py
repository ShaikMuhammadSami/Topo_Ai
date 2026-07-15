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


class PostIncidentReportStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReportActionStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReportActionPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportTimelinePhase(str, Enum):
    DETECTION = "detection"
    ANALYSIS = "analysis"
    IMPACT = "impact"
    RESPONSE = "response"
    RECOVERY = "recovery"
    FOLLOW_UP = "follow_up"


class ReportExportFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class GeneratedReportTimelineItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    timestamp: str | None

    phase: ReportTimelinePhase

    event: str = Field(
        min_length=1,
        max_length=2000,
    )

    evidence_ids: list[str]


class GeneratedReportFinding(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    summary: str = Field(
        min_length=1,
        max_length=3000,
    )

    significance: str = Field(
        min_length=1,
        max_length=3000,
    )

    evidence_ids: list[str]


class GeneratedReportActionItem(BaseModel):
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

    description: str = Field(
        min_length=1,
        max_length=4000,
    )

    owner_team: str | None
    owner_contact: str | None

    priority: ReportActionPriority

    due_date: str | None

    success_criteria: str = Field(
        min_length=1,
        max_length=3000,
    )

    evidence_ids: list[str]


class GeneratedPostIncidentReport(BaseModel):
    """
    No defaults are used because Groq strict
    structured output requires all properties
    to be present.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    title: str

    executive_summary: str
    incident_overview: str

    root_cause: str

    contributing_factors: list[str]

    business_impact: str
    technical_impact: str

    timeline: list[
        GeneratedReportTimelineItem
    ]

    investigation_findings: list[
        GeneratedReportFinding
    ]

    remediation_summary: str
    recovery_validation: str

    lessons_learned: list[str]

    action_items: list[
        GeneratedReportActionItem
    ]

    evidence_gaps: list[str]

    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )


class PostIncidentReportGenerateRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    provider: ExplanationProvider = (
        ExplanationProvider.AUTO
    )

    force_regenerate: bool = False


class PostIncidentReportUpdateRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: (
        PostIncidentReportStatus | None
    ) = None

    reviewer_name: str | None = Field(
        default=None,
        max_length=255,
    )

    review_notes: str | None = Field(
        default=None,
        max_length=8000,
    )

    @model_validator(mode="after")
    def require_update(
        self,
    ) -> "PostIncidentReportUpdateRequest":
        if (
            self.status is None
            and self.reviewer_name is None
            and self.review_notes is None
        ):
            raise ValueError(
                "Provide status, reviewer_name, "
                "or review_notes."
            )

        return self


class ReportActionItemUpdateRequest(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: ReportActionStatus | None = None

    owner_team: str | None = Field(
        default=None,
        max_length=255,
    )

    owner_contact: str | None = Field(
        default=None,
        max_length=500,
    )

    due_date: str | None = Field(
        default=None,
        max_length=50,
    )

    notes: str | None = Field(
        default=None,
        max_length=8000,
    )

    @model_validator(mode="after")
    def require_update(
        self,
    ) -> "ReportActionItemUpdateRequest":
        if (
            self.status is None
            and self.owner_team is None
            and self.owner_contact is None
            and self.due_date is None
            and self.notes is None
        ):
            raise ValueError(
                "Provide at least one action-item "
                "field to update."
            )

        return self


class ReportActionItemView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    action_item_id: str
    report_id: str
    incident_id: str

    sequence: int

    title: str
    description: str

    owner_team: str | None
    owner_contact: str | None

    priority: ReportActionPriority
    due_date: str | None

    success_criteria: str
    evidence_ids: list[str]

    status: ReportActionStatus
    notes: str | None
    completed_at: str | None

    created_at: str
    updated_at: str


class PostIncidentReportSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    report_id: str
    incident_id: str

    version: int
    title: str

    status: PostIncidentReportStatus

    provider: ExplanationProvider
    model_name: str | None

    prompt_version: str
    grounding_hash: str

    overall_confidence: float

    action_item_count: int
    completed_action_item_count: int

    reviewer_name: str | None
    reviewed_at: str | None
    approved_at: str | None

    created_at: str
    updated_at: str


class PostIncidentReportDetail(
    PostIncidentReportSummary
):
    executive_summary: str
    incident_overview: str
    root_cause: str

    contributing_factors: list[str]

    business_impact: str
    technical_impact: str

    timeline: list[
        GeneratedReportTimelineItem
    ]

    investigation_findings: list[
        GeneratedReportFinding
    ]

    remediation_summary: str
    recovery_validation: str

    lessons_learned: list[str]
    evidence_gaps: list[str]

    action_items: list[
        ReportActionItemView
    ]

    review_notes: str | None

    evidence_count: int
    warnings: list[str]