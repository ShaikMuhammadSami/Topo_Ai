"""Tenant-scoped repository authority for GitHub enrichment operations."""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.connectors.github_connector import GitHubSettings
from app.models.secret_store import SecretStoreError
from app.repositories.change_source_repository import load_change_source
from app.repositories.tenant_scope import DomainTenant
from app.services.secret_consumer_policy import source_binding
from app.services.secret_store import SecretStore

SOURCE_NOT_FOUND = "GITHUB_CHANGE_SOURCE_NOT_FOUND"
SOURCE_PROVIDER_INVALID = "GITHUB_CHANGE_SOURCE_PROVIDER_INVALID"
SOURCE_UNAVAILABLE = "GITHUB_CHANGE_SOURCE_UNAVAILABLE"
REPOSITORY_REQUIRED = "GITHUB_CHANGE_SOURCE_REPOSITORY_REQUIRED"
REPOSITORY_AMBIGUOUS = "GITHUB_CHANGE_SOURCE_REPOSITORY_AMBIGUOUS"
REPOSITORY_INVALID = "GITHUB_CHANGE_SOURCE_REPOSITORY_INVALID"

_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9._-]{1,100}\Z")


class GitHubSourceAuthorityError(ValueError):
    """Bounded source-authority rejection that never contains caller data."""


def parse_github_repository(value: object) -> tuple[str, str]:
    """Parse one persisted GitHub ``owner/repository`` authority."""

    if not isinstance(value, str) or value != value.strip():
        raise GitHubSourceAuthorityError(REPOSITORY_INVALID)
    parts = value.split("/")
    if len(parts) != 2:
        raise GitHubSourceAuthorityError(REPOSITORY_INVALID)
    owner, repository = parts
    if (
        _OWNER.fullmatch(owner) is None
        or _REPOSITORY.fullmatch(repository) is None
        or not any(character.isalnum() for character in repository)
    ):
        raise GitHubSourceAuthorityError(REPOSITORY_INVALID)
    return owner, repository


def github_settings_from_filters_json(filters_json: str) -> GitHubSettings:
    """Build call-local connector settings from persisted source filters."""

    try:
        filters = json.loads(filters_json or "{}")
    except (TypeError, json.JSONDecodeError):
        raise GitHubSourceAuthorityError(REPOSITORY_INVALID) from None
    if not isinstance(filters, dict):
        raise GitHubSourceAuthorityError(REPOSITORY_INVALID)
    repositories = filters.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise GitHubSourceAuthorityError(REPOSITORY_REQUIRED)
    if len(repositories) != 1:
        raise GitHubSourceAuthorityError(REPOSITORY_AMBIGUOUS)
    owner, repository = parse_github_repository(repositories[0])
    return GitHubSettings.for_repository(owner=owner, repository=repository)


def resolve_github_source_settings(
    session: Session,
    *,
    tenant_id: DomainTenant,
    source_id: str,
    secret_store: SecretStore,
) -> GitHubSettings:
    """Resolve one usable tenant-owned GitHub source to immutable settings."""

    record = load_change_source(
        session,
        tenant_id=tenant_id,
        source_id=source_id,
    )
    if record is None:
        raise GitHubSourceAuthorityError(SOURCE_NOT_FOUND)
    if record.source_type != "github":
        raise GitHubSourceAuthorityError(SOURCE_PROVIDER_INVALID)
    if not record.enabled or not record.secret_ref:
        raise GitHubSourceAuthorityError(SOURCE_UNAVAILABLE)

    try:
        config = json.loads(record.config_json or "{}")
        if not isinstance(config, dict):
            raise TypeError()
        descriptor = secret_store.describe(
            session,
            source_binding(
                tenant_id=str(record.tenant_id),
                source_id=record.source_id,
                source_type=record.source_type,
                config=config,
            ),
            record.secret_ref,
        )
    except (TypeError, ValueError, json.JSONDecodeError, SecretStoreError):
        raise GitHubSourceAuthorityError(SOURCE_UNAVAILABLE) from None
    if descriptor.status != "active":
        raise GitHubSourceAuthorityError(SOURCE_UNAVAILABLE)

    return github_settings_from_filters_json(record.filters_json)
