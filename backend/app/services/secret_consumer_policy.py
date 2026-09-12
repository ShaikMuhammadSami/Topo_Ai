"""Code-owned, non-secret provider and outbound webhook policy."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.change_events import ChangeEventEntityReference
from app.models.change_sources import ChangeSourceType
from app.models.secret_store import SecretBinding, SecretPurpose, SecretScope
from app.security.egress_policy import (
    EgressPolicyError,
    EgressPurpose,
    Resolver,
    SystemResolver,
    prepare_destination,
)


GITLAB_SIGNATURE_DEFAULT_SECONDS = 300
GITLAB_SIGNATURE_MAX_SECONDS = 3600
MAX_PROTECTED_HEADERS = 32
MAX_HEADER_NAME = 128
MAX_HEADER_VALUE = 8192
MAX_PROTECTED_HEADER_BUNDLE = 65536

_CONTROLLED_HEADERS = frozenset(
    {
        "connection",
        "cookie",
        "content-length",
        "content-type",
        "expect",
        "host",
        "proxy-connection",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "user-agent",
        "x-topo-event",
        "x-topo-event-id",
        "x-topo-signature",
        "x-topo-timestamp",
    }
)
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}\Z")


class ProviderPolicyError(ValueError):
    """Bounded policy rejection; never includes submitted values."""


class SourceFileCaptureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maximum_commits: int = Field(default=20, ge=1, le=20)
    maximum_files: int = Field(default=100, ge=1, le=100)
    maximum_bytes_per_file: int = Field(default=65536, ge=1, le=65536)
    maximum_total_bytes: int = Field(default=524288, ge=1, le=524288)
    maximum_scalar_bytes: int = Field(default=256, ge=1, le=256)
    maximum_scalar_characters: int = Field(default=128, ge=1, le=128)


class CommonProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str | None = Field(default=None, max_length=255)
    cluster_name: str | None = Field(default=None, max_length=255)
    namespace: str | None = Field(default=None, max_length=255)
    entity_refs: list[ChangeEventEntityReference] = Field(
        default_factory=list, max_length=100
    )


class GitHubProviderConfig(CommonProviderConfig):
    source_file_capture: SourceFileCaptureConfig = Field(
        default_factory=SourceFileCaptureConfig
    )


class GitLabProviderConfig(CommonProviderConfig):
    auth_mode: Literal["signing", "secret_token"] = "signing"
    signature_max_age: int = Field(
        default=GITLAB_SIGNATURE_DEFAULT_SECONDS,
        ge=1,
        le=GITLAB_SIGNATURE_MAX_SECONDS,
    )


class JenkinsProviderConfig(CommonProviderConfig):
    pass


class AzureDevOpsProviderConfig(CommonProviderConfig):
    username: str = Field(default="topo-webhook", min_length=1, max_length=255)


class TerraformCloudProviderConfig(CommonProviderConfig):
    provider: str | None = Field(default=None, max_length=255)


class ChangeSourceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_types: list[str] = Field(default_factory=list, max_length=100)
    repositories: list[str] = Field(default_factory=list, max_length=100)
    environments: list[str] = Field(default_factory=list, max_length=100)


_CONFIG_MODELS = {
    ChangeSourceType.GITHUB: GitHubProviderConfig,
    ChangeSourceType.GITLAB: GitLabProviderConfig,
    ChangeSourceType.JENKINS: JenkinsProviderConfig,
    ChangeSourceType.AZURE_DEVOPS: AzureDevOpsProviderConfig,
    ChangeSourceType.TERRAFORM_CLOUD: TerraformCloudProviderConfig,
}


def validate_provider_configuration(
    source_type: ChangeSourceType | str,
    config: dict,
    filters: dict,
) -> tuple[dict, dict]:
    try:
        kind = ChangeSourceType(source_type)
        config_value = _CONFIG_MODELS[kind].model_validate(config)
        filters_value = ChangeSourceFilters.model_validate(filters)
        config_document = config_value.model_dump(mode="json", exclude_none=True)
        filters_document = filters_value.model_dump(mode="json", exclude_defaults=True)
        if any(
            not isinstance(value, str) or len(value) > 1000
            for reference in config_document.get("entity_refs", [])
            for value in reference.values()
            if value is not None
        ):
            raise ValueError()
        if any(
            not isinstance(value, str) or len(value) > 1000
            for values in filters_document.values()
            for value in values
        ):
            raise ValueError()
    except (ValueError, TypeError, ValidationError):
        raise ProviderPolicyError("PROVIDER_CONFIGURATION_INVALID") from None
    return config_document, filters_document


def source_purpose(
    source_type: ChangeSourceType | str,
    config: dict,
) -> SecretPurpose:
    try:
        kind = ChangeSourceType(source_type)
        if kind is ChangeSourceType.GITHUB:
            return SecretPurpose.GITHUB_HMAC
        if kind is ChangeSourceType.GITLAB:
            return (
                SecretPurpose.GITLAB_SHARED_TOKEN
                if config.get("auth_mode", "signing") == "secret_token"
                else SecretPurpose.GITLAB_SIGNING
            )
        if kind is ChangeSourceType.TERRAFORM_CLOUD:
            return SecretPurpose.TERRAFORM_HMAC
        if kind is ChangeSourceType.JENKINS:
            return SecretPurpose.JENKINS_HMAC
        if kind is ChangeSourceType.AZURE_DEVOPS:
            return SecretPurpose.AZURE_BASIC_PASSWORD
    except (ValueError, TypeError):
        pass
    raise ProviderPolicyError("PROVIDER_CONFIGURATION_INVALID")


def source_binding(
    *, tenant_id: str, source_id: str, source_type: str, config: dict
) -> SecretBinding:
    return SecretBinding(
        SecretScope.tenant(tenant_id),
        "change_source",
        source_id,
        source_purpose(source_type, config),
    )


def webhook_binding(
    *, tenant_id: str, webhook_id: str, purpose: SecretPurpose
) -> SecretBinding:
    if purpose not in {SecretPurpose.WEBHOOK_SIGNING, SecretPurpose.WEBHOOK_HEADERS}:
        raise ProviderPolicyError("WEBHOOK_CREDENTIAL_INVALID")
    return SecretBinding(
        SecretScope.tenant(tenant_id), "webhook_endpoint", webhook_id, purpose
    )


def validate_webhook_url(
    value: str,
    *,
    resolver: Resolver | None = None,
) -> str:
    try:
        return prepare_destination(
            value,
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=resolver or SystemResolver(),
        ).destination.url
    except EgressPolicyError as exc:
        raise ProviderPolicyError(exc.code.value) from None


def validate_protected_headers(headers: dict[str, str]) -> dict[str, str]:
    if not isinstance(headers, dict) or len(headers) > MAX_PROTECTED_HEADERS:
        raise ProviderPolicyError("WEBHOOK_HEADERS_INVALID")
    result: dict[str, str] = {}
    observed: set[str] = set()
    for name, value in headers.items():
        lowered = name.lower() if isinstance(name, str) else ""
        if (
            not isinstance(name, str)
            or not _HEADER_NAME.fullmatch(name)
            or lowered in observed
            or lowered in _CONTROLLED_HEADERS
            or lowered == "forwarded"
            or lowered.startswith("x-forwarded-")
            or not isinstance(value, str)
            or not 1 <= len(value) <= MAX_HEADER_VALUE
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ProviderPolicyError("WEBHOOK_HEADERS_INVALID")
        observed.add(lowered)
        result[name] = value
    if len(serialize_protected_headers(result)) > MAX_PROTECTED_HEADER_BUNDLE:
        raise ProviderPolicyError("WEBHOOK_HEADERS_INVALID")
    return result


def serialize_protected_headers(headers: dict[str, str]) -> bytes:
    return json.dumps(
        {"version": 1, "headers": headers},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def deserialize_protected_headers(material: bytes) -> dict[str, str]:
    try:
        document = json.loads(material)
        if (
            not isinstance(document, dict)
            or set(document) != {"version", "headers"}
            or document["version"] != 1
        ):
            raise ValueError()
        return validate_protected_headers(document["headers"])
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ProviderPolicyError("WEBHOOK_HEADERS_INVALID") from None
