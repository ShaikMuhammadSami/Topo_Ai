from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
)


class ChangeSourceType(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    JENKINS = "jenkins"
    AZURE_DEVOPS = "azure_devops"
    TERRAFORM_CLOUD = "terraform_cloud"


class ChangeSourceCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    source_type: ChangeSourceType

    credential: SecretStr | None = None

    enabled: bool = True

    config: dict[str, Any] = Field(
        default_factory=dict
    )

    filters: dict[str, Any] = Field(
        default_factory=dict
    )


class ChangeSourceUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    enabled: bool | None = None

    credential: "ChangeSourceCredentialMutation | None" = None

    config: (
        dict[str, Any] | None
    ) = None

    filters: (
        dict[str, Any] | None
    ) = None


class ChangeSourceView(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    source_id: str
    name: str

    source_type: ChangeSourceType

    enabled: bool

    credential_configured: bool
    credential_status: Literal["configured", "unconfigured"]
    rotation_supported: bool = True
    credential_updated_at: str | None = None

    status: str

    config: dict[str, Any]

    filters: dict[str, Any]

    delivery_count: int
    failure_count: int

    last_event_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error: str | None

    receiver_path: str

    created_at: str
    updated_at: str


class ChangeSourceDoctorResponse(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    source_id: str

    ready: bool

    checks: dict[str, Any]


class ChangeSourceCredentialMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["rotate", "replace", "revoke", "reprovision"]
    credential: SecretStr | None = None
    overlap_seconds: int = Field(default=0, ge=0, le=86400)


class ChangeSourceDeliveryView(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    delivery_id: str
    source_id: str

    source_delivery_id: str | None

    event_type: str | None

    status: str

    payload_sha256: str

    event_ids: list[str] = Field(
        default_factory=list
    )

    error: str | None

    received_at: str
    processed_at: str | None


class ChangeSourceDeliveryReceipt(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    delivery_id: str
    source_id: str

    event_type: str | None

    status: str

    duplicate: bool

    event_ids: list[str] = Field(
        default_factory=list
    )


class ChangeSourceDeadLetterView(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    dead_letter_id: str

    source_id: str
    delivery_id: str

    event_type: str | None

    reason: str

    attempt_count: int

    status: str

    last_attempt_at: str | None
    replayed_at: str | None

    created_at: str


class ChangeSourceReplayResponse(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid"
    )

    dead_letter_id: str

    succeeded: bool

    event_ids: list[str] = Field(
        default_factory=list
    )

    error: str | None = None
