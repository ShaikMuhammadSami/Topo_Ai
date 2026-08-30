from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


TENANT_ID_PATTERN = re.compile(
    r"^tenant:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class TenantStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class TenantMembershipStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


def is_valid_tenant_id(value: str) -> bool:
    return bool(TENANT_ID_PATTERN.fullmatch(value))


def _stable_subject(value: str) -> str:
    if value != value.strip() or not value or value.lower() == "unknown":
        raise ValueError("subject must be a stable identity without outer whitespace")
    return value


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=500)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError(
                "display_name must be non-empty and have no outer whitespace"
            )
        return value


class TenantView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    display_name: str
    status: TenantStatus
    membership_id: str
    created_at: str


class TenantMembershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=500)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _stable_subject(value)


class TenantMembershipRecovery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=500)

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, value: str) -> str:
        if not is_valid_tenant_id(value):
            raise ValueError("tenant_id has an invalid format")
        return value

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _stable_subject(value)


class TenantMembershipView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: str
    tenant_id: str
    subject: str
    status: TenantMembershipStatus
    created_at: str
    updated_at: str
    created_by_subject: str


class TenantContextView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    authenticated_subject: str
    authentication_type: str
    actor_kind: str
    selection_source: str
    membership_id: str | None = None
    credential_id: str | None = None
