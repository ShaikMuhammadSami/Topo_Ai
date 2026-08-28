from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


AUTH_MODE_ENV = "TOPO_AUTH_MODE"
LEGACY_AUTH_ENABLED_ENV = "TOPO_AUTH_ENABLED"
TOKEN_REGISTRY_ENV = "TOPO_API_TOKEN_HASHES_JSON"


class AuthMode(str, Enum):
    REQUIRED = "required"
    DEVELOPMENT_DISABLED = "development-disabled"


class AuthConfigurationFailure(str, Enum):
    INVALID_AUTH_MODE = "INVALID_AUTH_MODE"
    LEGACY_FAIL_OPEN_CONFIG = "LEGACY_FAIL_OPEN_CONFIG"
    DEVELOPMENT_MODE_NON_SQLITE = "DEVELOPMENT_MODE_NON_SQLITE"
    INVALID_TOKEN_REGISTRY = "INVALID_TOKEN_REGISTRY"
    EMPTY_REQUIRED_AUTHORITY = "EMPTY_REQUIRED_AUTHORITY"


class AuthConfigurationError(RuntimeError):
    def __init__(
        self,
        category: AuthConfigurationFailure,
        message: str,
    ) -> None:
        self.category = category
        super().__init__(f"{category.value}: {message}")


@dataclass(frozen=True)
class TokenIdentity:
    subject: str
    display_name: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class AuthConfiguration:
    mode: AuthMode
    token_registry: Mapping[str, TokenIdentity]
    operator_warnings: tuple[str, ...] = ()


_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_LEGACY_TRUE = frozenset({"1", "true", "yes", "on"})
_LEGACY_FALSE = frozenset({"0", "false", "no", "off"})


def _legacy_value(raw_value: str) -> bool:
    value = raw_value.strip().lower()
    if value in _LEGACY_TRUE:
        return True
    if value in _LEGACY_FALSE:
        return False
    raise AuthConfigurationError(
        AuthConfigurationFailure.LEGACY_FAIL_OPEN_CONFIG,
        (
            f"{LEGACY_AUTH_ENABLED_ENV} is malformed. Configure "
            f"{AUTH_MODE_ENV}=required, or use the explicit SQLite-only "
            "development mode."
        ),
    )


def _resolve_mode() -> tuple[AuthMode, tuple[str, ...]]:
    raw_mode = os.environ.get(AUTH_MODE_ENV)
    raw_legacy = os.environ.get(LEGACY_AUTH_ENABLED_ENV)
    warnings: list[str] = []

    if raw_mode is None:
        if raw_legacy is None:
            return AuthMode.REQUIRED, ()
        if not _legacy_value(raw_legacy):
            raise AuthConfigurationError(
                AuthConfigurationFailure.LEGACY_FAIL_OPEN_CONFIG,
                (
                    f"{LEGACY_AUTH_ENABLED_ENV}=false no longer disables "
                    f"authentication. Use {AUTH_MODE_ENV}="
                    "development-disabled only for local SQLite development."
                ),
            )
        warnings.append(
            f"{LEGACY_AUTH_ENABLED_ENV} is deprecated; use "
            f"{AUTH_MODE_ENV}=required."
        )
        return AuthMode.REQUIRED, tuple(warnings)

    try:
        mode = AuthMode(raw_mode)
    except ValueError as exc:
        raise AuthConfigurationError(
            AuthConfigurationFailure.INVALID_AUTH_MODE,
            (
                f"{AUTH_MODE_ENV} must be exactly 'required' or "
                "'development-disabled'."
            ),
        ) from exc

    if raw_legacy is not None:
        legacy_enabled = _legacy_value(raw_legacy)
        compatible = (
            (mode is AuthMode.REQUIRED and legacy_enabled)
            or (
                mode is AuthMode.DEVELOPMENT_DISABLED
                and not legacy_enabled
            )
        )
        if not compatible:
            raise AuthConfigurationError(
                AuthConfigurationFailure.LEGACY_FAIL_OPEN_CONFIG,
                (
                    f"{AUTH_MODE_ENV} and {LEGACY_AUTH_ENABLED_ENV} "
                    "request incompatible authentication behavior."
                ),
            )
        warnings.append(
            f"{LEGACY_AUTH_ENABLED_ENV} is deprecated and should be removed."
        )

    return mode, tuple(warnings)


def _registry_error(message: str) -> AuthConfigurationError:
    return AuthConfigurationError(
        AuthConfigurationFailure.INVALID_TOKEN_REGISTRY,
        f"{TOKEN_REGISTRY_ENV} {message}",
    )


def load_token_registry() -> Mapping[str, TokenIdentity]:
    raw_value = os.environ.get(TOKEN_REGISTRY_ENV, "{}")
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise _registry_error("must contain valid JSON.") from exc

    if not isinstance(value, dict):
        raise _registry_error("must contain a JSON object.")

    registry: dict[str, TokenIdentity] = {}
    for token_hash, metadata in value.items():
        if not isinstance(token_hash, str) or _SHA256_HEX.fullmatch(token_hash) is None:
            raise _registry_error(
                "must use lowercase SHA-256 hexadecimal digest keys."
            )
        if not isinstance(metadata, dict):
            raise _registry_error("entries must contain metadata objects.")

        subject = metadata.get("subject")
        if (
            not isinstance(subject, str)
            or not subject
            or subject != subject.strip()
            or subject.lower() == "unknown"
        ):
            raise _registry_error(
                "entries must contain a stable non-empty subject."
            )

        display_name = metadata.get("display_name", subject)
        if not isinstance(display_name, str):
            raise _registry_error("display_name must be a string when supplied.")

        roles_value = metadata.get("roles")
        if not isinstance(roles_value, list):
            raise _registry_error("roles must be a JSON list.")
        if any(
            not isinstance(role, str)
            or not role
            or role != role.strip()
            for role in roles_value
        ):
            raise _registry_error("each role must be a non-empty string.")

        registry[token_hash] = TokenIdentity(
            subject=subject,
            display_name=display_name,
            roles=tuple(roles_value),
        )

    return MappingProxyType(registry)


def _validate_development_database(database_url: str | None) -> None:
    configured_url = database_url or os.environ.get("TOPO_DATABASE_URL") or "sqlite://"
    try:
        dialect = make_url(configured_url).get_backend_name()
    except (ArgumentError, ValueError) as exc:
        raise AuthConfigurationError(
            AuthConfigurationFailure.DEVELOPMENT_MODE_NON_SQLITE,
            "development-disabled requires a valid SQLite database URL.",
        ) from exc
    if dialect != "sqlite":
        raise AuthConfigurationError(
            AuthConfigurationFailure.DEVELOPMENT_MODE_NON_SQLITE,
            "development-disabled is permitted only with SQLite persistence.",
        )


def load_auth_configuration(
    *,
    database_url: str | None = None,
) -> AuthConfiguration:
    mode, operator_warnings = _resolve_mode()
    registry = load_token_registry()

    if mode is AuthMode.REQUIRED and not registry:
        raise AuthConfigurationError(
            AuthConfigurationFailure.EMPTY_REQUIRED_AUTHORITY,
            (
                "required mode needs at least one valid transitional "
                "API-token mapping."
            ),
        )

    if mode is AuthMode.DEVELOPMENT_DISABLED:
        _validate_development_database(database_url)
        operator_warnings = operator_warnings + (
            (
                "SECURITY WARNING: authentication is explicitly disabled for "
                "local SQLite development; never use this mode in production."
            ),
        )

    return AuthConfiguration(
        mode=mode,
        token_registry=registry,
        operator_warnings=operator_warnings,
    )
