from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
)


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


class WebhookEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    event_id: str
    event_type: WebhookEventType

    occurred_at: datetime

    source: str = "topo-ai"

    resource_type: str
    resource_id: str

    summary: str

    severity: str | None = None

    payload: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )


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
