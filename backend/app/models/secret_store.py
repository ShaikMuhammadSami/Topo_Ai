"""Internal custody types. These are not HTTP request/response models."""

from dataclasses import dataclass
from enum import StrEnum
import re

from app.models.tenant import is_valid_tenant_id

MAX_MATERIAL_BYTES = 65536
MAX_OVERLAP_SECONDS = 86400
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
INSTALLATION_PATTERN = re.compile(
    r"installation:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
SECRET_REF_PATTERN = re.compile(
    r"secret:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)


class SecretStoreError(RuntimeError):
    """Only code-owned, bounded errors cross the internal boundary."""


class SecretPurpose(StrEnum):
    GITHUB_HMAC = "change_source.github_hmac"
    GITLAB_SIGNING = "change_source.gitlab_signing"
    GITLAB_SHARED_TOKEN = "change_source.gitlab_shared_token"
    TERRAFORM_HMAC = "change_source.terraform_hmac"
    JENKINS_HMAC = "change_source.jenkins_hmac"
    AZURE_BASIC_PASSWORD = "change_source.azure_basic_password"
    WEBHOOK_SIGNING = "webhook_endpoint.signing"
    WEBHOOK_HEADERS = "webhook_endpoint.protected_headers"
    OPENAI_API = "installation_integration.openai_api"
    GROQ_API = "installation_integration.groq_api"
    GITHUB_API = "installation_integration.github_api"


INBOUND_PURPOSES = frozenset(p for p in SecretPurpose if p.value.startswith("change_source."))


@dataclass(frozen=True)
class SecretScope:
    """Server code supplies PH-3 authority; never construct from an HTTP body."""

    kind: str
    scope_id: str
    tenant_id: str | None

    def __post_init__(self):
        valid = (
            self.kind == "tenant" and isinstance(self.tenant_id, str)
            and is_valid_tenant_id(self.tenant_id) and self.scope_id == self.tenant_id
        ) or (
            self.kind == "installation" and self.tenant_id is None
            and isinstance(self.scope_id, str) and INSTALLATION_PATTERN.fullmatch(self.scope_id)
        )
        if not valid:
            raise SecretStoreError("SECRET_SCOPE_INVALID")

    @classmethod
    def tenant(cls, tenant_id: str):
        return cls("tenant", tenant_id, tenant_id)


@dataclass(frozen=True)
class SecretBinding:
    scope: SecretScope
    owner_type: str
    owner_id: str
    purpose: SecretPurpose

    def __post_init__(self):
        if (
            not isinstance(self.scope, SecretScope)
            or not isinstance(self.purpose, SecretPurpose)
            or self.owner_type != self.purpose.value.split(".", 1)[0]
            or not isinstance(self.owner_id, str) or not 1 <= len(self.owner_id) <= 255
            or self.owner_id != self.owner_id.strip()
            or (self.scope.kind == "installation") != (self.owner_type == "installation_integration")
        ):
            raise SecretStoreError("SECRET_OWNER_PURPOSE_INVALID")


class SecretMaterial:
    """Explicit use-only bytes; no JSON serialization or zeroization promise."""

    __slots__ = ("__value",)

    def __init__(self, value: bytes):
        if not isinstance(value, bytes) or not 1 <= len(value) <= MAX_MATERIAL_BYTES:
            raise SecretStoreError("SECRET_MATERIAL_INVALID")
        self.__value = value

    def reveal(self) -> bytes:
        return self.__value

    def __repr__(self):
        return "SecretMaterial(<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True)
class SecretDescriptor:
    secret_ref: str
    binding: SecretBinding
    status: str
    active_version: int
    previous_version: int | None
    previous_accept_until: str | None
    row_version: int
    created_at: str
    updated_at: str
    revoked_at: str | None
