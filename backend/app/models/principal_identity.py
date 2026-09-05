from __future__ import annotations

import re
from enum import StrEnum
from uuid import UUID, uuid4


LEGACY_LOCAL_ISSUER = "urn:topo:auth:legacy-local-v1"
DEVELOPMENT_ISSUER = "urn:topo:auth:development"

PRINCIPAL_ID_PATTERN = re.compile(
    r"^principal:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
EXTERNAL_IDENTITY_ID_PATTERN = re.compile(
    r"^identity:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class PrincipalType(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class PrincipalStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ExternalIdentityStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


def new_principal_id() -> str:
    return f"principal:{uuid4()}"


def new_external_identity_id() -> str:
    return f"identity:{uuid4()}"


def is_valid_principal_id(value: str) -> bool:
    if PRINCIPAL_ID_PATTERN.fullmatch(value) is None:
        return False
    try:
        return UUID(value.removeprefix("principal:")).version == 4
    except ValueError:
        return False


def is_valid_external_identity_id(value: str) -> bool:
    if EXTERNAL_IDENTITY_ID_PATTERN.fullmatch(value) is None:
        return False
    try:
        return UUID(value.removeprefix("identity:")).version == 4
    except ValueError:
        return False


def validate_identity_authority(value: str, *, field_name: str) -> str:
    if (
        not value
        or len(value) > 500
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(
            f"{field_name} must be a bounded opaque value without outer "
            "whitespace or control characters"
        )
    return value
