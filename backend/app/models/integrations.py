from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class IntegrationType(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    JENKINS = "jenkins"
    AZURE_DEVOPS = "azure_devops"
    TERRAFORM_CLOUD = "terraform_cloud"


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    integration_type: IntegrationType

    secret_ref: str

    enabled: bool = True

    config: dict[str, Any] = Field(
        default_factory=dict
    )

    filters: dict[str, Any] = Field(
        default_factory=dict
    )


class IntegrationUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    enabled: bool | None = None
    secret_ref: str | None = None

    config: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None


class IntegrationView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    integration_id: str
    name: str

    integration_type: IntegrationType

    enabled: bool

    secret_ref: str

    status: str

    config: dict[str, Any]
    filters: dict[str, Any]

    delivery_count: int
    failure_count: int

    last_event_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error: str | None

    webhook_path: str

    created_at: str
    updated_at: str


class IntegrationDoctorResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    integration_id: str

    ready: bool

    checks: dict[str, Any]


class WebhookDeliveryReceipt(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    delivery_id: str

    integration_id: str

    event_type: str | None

    status: str

    duplicate: bool

    event_ids: list[str] = Field(
        default_factory=list
    )


class DeadLetterView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    dead_letter_id: str

    integration_id: str
    delivery_id: str

    event_type: str | None

    reason: str

    attempt_count: int

    status: str

    last_attempt_at: str | None
    replayed_at: str | None

    created_at: str


class ReplayResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    attempted: int
    succeeded: int
    failed: int