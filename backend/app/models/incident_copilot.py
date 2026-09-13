from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.incident_explanation import (
    ExplanationProvider,
)


class CopilotSessionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class CopilotMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class CopilotAnswerStatus(str, Enum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    INSUFFICIENT_EVIDENCE = (
        "insufficient_evidence"
    )


class CopilotGeneratedAnswer(BaseModel):
    """
    Every field is required for Groq strict
    JSON-schema output.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    answer: str
    evidence_ids: list[str]

    confidence: float

    answer_status: CopilotAnswerStatus

    suggested_questions: list[str]


class CopilotSessionCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    title: str | None = Field(
        default=None,
        max_length=500,
    )

    provider: ExplanationProvider = (
        ExplanationProvider.AUTO
    )


class CopilotQuestionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    question: str = Field(
        min_length=1,
        max_length=4096,
    )


class CopilotMessageView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    message_id: str
    session_id: str
    incident_id: str

    role: CopilotMessageRole
    content: str

    provider: ExplanationProvider | None

    answer_status: (
        CopilotAnswerStatus | None
    )

    confidence: float | None

    evidence_ids: list[str]
    suggested_questions: list[str]

    warning: str | None
    created_at: str


class CopilotSessionSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    session_id: str
    incident_id: str

    title: str

    provider: ExplanationProvider
    model_name: str | None

    status: CopilotSessionStatus

    message_count: int

    created_at: str
    updated_at: str


class CopilotSessionDetail(
    CopilotSessionSummary
):
    messages: list[
        CopilotMessageView
    ]


class CopilotQuestionResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    session_id: str

    user_message: CopilotMessageView
    assistant_message: CopilotMessageView
