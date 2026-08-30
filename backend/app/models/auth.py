from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.tenant import is_valid_tenant_id


class ApiCredentialCallerType(StrEnum):
    HUMAN_API = "human_api"
    SERVICE_API = "service_api"


class ApiCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    caller_type: ApiCredentialCallerType
    subject: str = Field(min_length=1, max_length=500)
    display_name: str | None = Field(default=None, max_length=500)
    roles: list[str] = Field(default_factory=list, max_length=100)
    expires_in_days: int = Field(default=30, ge=1, le=90)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("name", "subject", "display_name")
    @classmethod
    def validate_identity_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip() or not value:
            raise ValueError(
                "value must be non-empty and have no outer whitespace"
            )
        return value

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        if value.lower() == "unknown":
            raise ValueError("subject must be a stable identity")
        return value

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: list[str]) -> list[str]:
        if any(not role or role != role.strip() for role in value):
            raise ValueError(
                "roles must be non-empty strings without outer whitespace"
            )
        if len(set(value)) != len(value):
            raise ValueError("roles must not contain duplicates")
        return value

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_tenant_id(value):
            raise ValueError("tenant_id has an invalid format")
        return value

    @model_validator(mode="after")
    def validate_tenant_binding_contract(self):
        if (
            self.caller_type is ApiCredentialCallerType.SERVICE_API
            and self.tenant_id is None
        ):
            raise ValueError("tenant_id is required for service_api credentials")
        if (
            self.caller_type is ApiCredentialCallerType.HUMAN_API
            and self.tenant_id is not None
        ):
            raise ValueError("tenant_id is not accepted for human_api credentials")
        return self


class ApiCredentialView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: str
    credential_hint: str
    name: str
    caller_type: ApiCredentialCallerType
    subject: str
    display_name: str
    roles: list[str] = Field(default_factory=list)
    created_at: str
    created_by_subject: str
    expires_at: str
    revoked_at: str | None = None
    revoked_by_subject: str | None = None
    last_used_at: str | None = None
    updated_at: str
    tenant_id: str | None = None


class ApiCredentialCreated(ApiCredentialView):
    api_credential: str


class BrowserSessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    display_name: str
    roles: list[str] = Field(default_factory=list)
    authentication_type: str
    absolute_expires_at: str | None = None
