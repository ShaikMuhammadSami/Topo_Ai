from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, TypeAlias
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)

from app.security.customer_data_policy import scrub_outbound_text


def _webhook_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("webhook_text_invalid")
    return scrub_outbound_text(value, maximum=4096)


def _webhook_identifier(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError("webhook_identifier_invalid")
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise ValueError("webhook_identifier_invalid")
    if scrub_outbound_text(value, maximum=len(value)) != value:
        raise ValueError("webhook_identifier_not_allowed")
    return value


WebhookIdentifier: TypeAlias = Annotated[
    str,
    BeforeValidator(_webhook_identifier),
    StringConstraints(min_length=1, max_length=256),
]
WebhookText: TypeAlias = Annotated[
    str,
    BeforeValidator(_webhook_text),
    StringConstraints(max_length=4096),
]


class WebhookEventType(str, Enum):
    INCIDENT_CREATED = "incident.created"

    INCIDENT_STATUS_CHANGED = (
        "incident.status_changed"
    )

    RECOMMENDATION_GENERATED = (
        "recommendation.generated"
    )

    RECOVERY_VERIFIED = (
        "recovery.verified"
    )

    RECOVERY_FAILED = "recovery.failed"

    RECOVERY_INCONCLUSIVE = (
        "recovery.inconclusive"
    )

    CHANGE_RISK_DETECTED = (
        "change.risk_detected"
    )

    TEST = "webhook.test"


class WebhookDeliveryStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


DEFAULT_EVENT_TYPES = [
    WebhookEventType.INCIDENT_CREATED,
    WebhookEventType.INCIDENT_STATUS_CHANGED,
    WebhookEventType.RECOMMENDATION_GENERATED,
    WebhookEventType.RECOVERY_VERIFIED,
    WebhookEventType.RECOVERY_FAILED,
    WebhookEventType.RECOVERY_INCONCLUSIVE,
    WebhookEventType.CHANGE_RISK_DETECTED,
]


class WebhookEndpointCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    url: str = Field(
        min_length=8,
        max_length=2000,
    )

    event_types: list[
        WebhookEventType
    ] = Field(
        default_factory=lambda:
            list(DEFAULT_EVENT_TYPES)
    )

    headers: dict[str, SecretStr] = Field(
        default_factory=dict
    )

    signing_secret: SecretStr | None = None

    active: bool = True

    timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
    )

class WebhookEndpointUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    url: str | None = None

    event_types: list[
        WebhookEventType
    ] | None = None

    headers: dict[
        str,
        SecretStr,
    ] | None = None

    signing_secret: SecretStr | None = None

    active: bool | None = None

    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=30,
    )

    max_attempts: int | None = Field(
        default=None,
        ge=1,
        le=5,
    )


class WebhookEndpointView(BaseModel):
    webhook_id: str

    name: str
    url: str

    event_types: list[
        WebhookEventType
    ]

    has_signing_secret: bool
    has_protected_headers: bool
    protected_header_names: list[str]

    active: bool

    timeout_seconds: int
    max_attempts: int

    created_at: str
    updated_at: str


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IncidentCreatedWebhookPayload(WebhookPayload):
    incident_id: WebhookIdentifier
    status: WebhookIdentifier
    severity: WebhookIdentifier
    cluster_name: WebhookIdentifier
    namespace: WebhookIdentifier | None = None
    topology_snapshot_id: WebhookIdentifier | None = None
    automatic: bool | None = None
    affected_object_kind: WebhookIdentifier | None = None
    affected_object_name: WebhookIdentifier | None = None
    analysis_id: WebhookIdentifier | None = None


class IncidentStatusChangedWebhookPayload(WebhookPayload):
    incident_id: WebhookIdentifier
    status: WebhookIdentifier
    status_note: WebhookText | None = None
    updated_at: WebhookIdentifier


class RecommendationGeneratedWebhookPayload(WebhookPayload):
    recommendation_id: WebhookIdentifier
    analysis_id: WebhookIdentifier
    signal_id: WebhookIdentifier
    action_type: WebhookIdentifier
    status: WebhookIdentifier
    confidence: float
    risk: WebhookIdentifier
    target_entity_name: WebhookIdentifier | None = None


class RecoveryWebhookPayload(WebhookPayload):
    verification_id: WebhookIdentifier
    recommendation_id: WebhookIdentifier
    analysis_id: WebhookIdentifier
    status: WebhookIdentifier
    confidence: float
    passed_count: int
    failed_count: int
    unknown_count: int


class ChangeRiskDetectedWebhookPayload(WebhookPayload):
    analysis_id: WebhookIdentifier
    snapshot_id: WebhookIdentifier
    root_entity_id: WebhookIdentifier
    root_entity_name: WebhookIdentifier
    change_type: WebhookIdentifier
    risk_score: float
    risk_level: WebhookIdentifier
    deployment_decision: WebhookIdentifier
    affected_entity_count: int
    recommendation: WebhookText


class WebhookTestPayload(WebhookPayload):
    webhook_id: WebhookIdentifier
    test: Literal[True] = True


WebhookEventPayload: TypeAlias = (
    IncidentCreatedWebhookPayload
    | IncidentStatusChangedWebhookPayload
    | RecommendationGeneratedWebhookPayload
    | RecoveryWebhookPayload
    | ChangeRiskDetectedWebhookPayload
    | WebhookTestPayload
)


WEBHOOK_PAYLOAD_TYPE_BY_EVENT: dict[
    WebhookEventType, type[WebhookPayload]
] = {
    WebhookEventType.INCIDENT_CREATED: IncidentCreatedWebhookPayload,
    WebhookEventType.INCIDENT_STATUS_CHANGED: IncidentStatusChangedWebhookPayload,
    WebhookEventType.RECOMMENDATION_GENERATED: RecommendationGeneratedWebhookPayload,
    WebhookEventType.RECOVERY_VERIFIED: RecoveryWebhookPayload,
    WebhookEventType.RECOVERY_FAILED: RecoveryWebhookPayload,
    WebhookEventType.RECOVERY_INCONCLUSIVE: RecoveryWebhookPayload,
    WebhookEventType.CHANGE_RISK_DETECTED: ChangeRiskDetectedWebhookPayload,
    WebhookEventType.TEST: WebhookTestPayload,
}


class WebhookEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: WebhookIdentifier
    event_type: WebhookEventType

    occurred_at: datetime

    source: Literal["topo-ai"] = "topo-ai"

    resource_type: WebhookIdentifier
    resource_id: WebhookIdentifier

    summary: WebhookText

    severity: WebhookIdentifier | None = None

    payload: WebhookEventPayload

    @model_validator(mode="after")
    def validate_payload_contract(self) -> "WebhookEvent":
        expected_payload = WEBHOOK_PAYLOAD_TYPE_BY_EVENT[self.event_type]
        if not isinstance(self.payload, expected_payload):
            raise ValueError("webhook_payload_type_invalid")
        return self


class WebhookDeliveryView(BaseModel):
    delivery_id: str

    webhook_id: str
    webhook_name: str | None = None

    event_id: str
    event_type: WebhookEventType

    resource_type: str
    resource_id: str

    status: WebhookDeliveryStatus

    attempt_count: int

    response_status: int | None
    response_body: str | None

    error_message: str | None

    requested_at: str
    completed_at: str | None

    created_at: str
    updated_at: str


class WebhookTestRequest(BaseModel):
    summary: str = Field(
        default=(
            "Topo AI webhook test delivery."
        ),
        min_length=1,
        max_length=500,
    )
