from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import AuthSessionRecord
from app.repositories.auth_session_repository import (
    add_auth_session,
    load_auth_session_by_secret_digest,
)
from app.security.auth_config import AuthConfiguration
from app.security.principals import AuthPrincipal
from app.services.auth_api_credential_service import (
    resolve_auth_api_credential_by_digest,
)


SESSION_SECRET_PREFIX = "topo_session_"
CSRF_SECRET_PREFIX = "topo_csrf_"


class AuthSessionPersistenceError(RuntimeError):
    """A browser-session persistence operation failed closed."""


@dataclass(frozen=True)
class IssuedAuthSession:
    record: AuthSessionRecord
    session_secret: str
    csrf_secret: str


@dataclass(frozen=True)
class ResolvedAuthSession:
    record: AuthSessionRecord
    principal: AuthPrincipal


def secret_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _as_utc(parsed)


def _roles(record: AuthSessionRecord) -> tuple[str, ...] | None:
    try:
        value = json.loads(record.roles_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, list) or any(
        not isinstance(role, str) or not role for role in value
    ):
        return None
    return tuple(value)


def create_auth_session(
    session: Session,
    *,
    configuration: AuthConfiguration,
    source_principal: AuthPrincipal,
    source_credential_digest: str,
    now: datetime | None = None,
) -> IssuedAuthSession:
    if source_principal.authentication_type not in {
        "api_token",
        "human_api_token",
    }:
        raise ValueError("Only a human API-token principal can create a session.")
    if source_principal.authentication_type == "api_token":
        source_identity = configuration.token_registry.get(source_credential_digest)
        source_is_valid = source_identity is not None and (
            source_identity.subject == source_principal.subject
            and source_identity.display_name == source_principal.display_name
            and source_identity.roles == source_principal.roles
        )
    else:
        source_named = resolve_auth_api_credential_by_digest(
            session,
            digest=source_credential_digest,
            now=now,
        )
        source_is_valid = source_named is not None and (
            source_named.principal.authentication_type == "human_api_token"
            and source_named.principal.subject == source_principal.subject
            and source_named.principal.display_name == source_principal.display_name
            and source_named.principal.roles == source_principal.roles
        )
    if not source_is_valid:
        raise ValueError("The source authentication authority is unavailable.")

    issued_at = _as_utc(now or _utc_now())
    absolute_expires_at = issued_at + timedelta(
        minutes=configuration.session_absolute_ttl_minutes
    )
    idle_expires_at = min(
        issued_at
        + timedelta(minutes=configuration.session_idle_ttl_minutes),
        absolute_expires_at,
    )
    raw_session_secret = SESSION_SECRET_PREFIX + secrets.token_urlsafe(48)
    raw_csrf_secret = CSRF_SECRET_PREFIX + secrets.token_urlsafe(32)
    record = AuthSessionRecord(
        session_id=f"auth-session:{uuid4()}",
        session_secret_digest=secret_digest(raw_session_secret),
        csrf_digest=secret_digest(raw_csrf_secret),
        subject=source_principal.subject,
        display_name=source_principal.display_name,
        roles_json=json.dumps(list(source_principal.roles), separators=(",", ":")),
        source_authentication_type=source_principal.authentication_type,
        source_credential_digest=source_credential_digest,
        issued_at=issued_at.isoformat(),
        absolute_expires_at=absolute_expires_at.isoformat(),
        idle_expires_at=idle_expires_at.isoformat(),
        last_seen_at=issued_at.isoformat(),
        revoked_at=None,
    )
    try:
        add_auth_session(session, record)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthSessionPersistenceError(
            "Browser session persistence failed."
        ) from exc
    return IssuedAuthSession(
        record=record,
        session_secret=raw_session_secret,
        csrf_secret=raw_csrf_secret,
    )


def resolve_auth_session(
    session: Session,
    *,
    configuration: AuthConfiguration,
    raw_session_secret: str,
    now: datetime | None = None,
) -> ResolvedAuthSession | None:
    record = load_auth_session_by_secret_digest(
        session,
        secret_digest(raw_session_secret),
    )
    if record is None or record.revoked_at is not None:
        return None

    reference_time = _as_utc(now or _utc_now())
    absolute_expiry = _parse_utc(record.absolute_expires_at)
    idle_expiry = _parse_utc(record.idle_expires_at)
    if (
        absolute_expiry is None
        or idle_expiry is None
        or reference_time >= absolute_expiry
        or reference_time >= idle_expiry
    ):
        return None

    roles = _roles(record)
    if roles is None or record.source_authentication_type not in {
        "api_token",
        "human_api_token",
    }:
        return None
    if record.source_authentication_type == "api_token":
        source_identity = configuration.token_registry.get(
            record.source_credential_digest
        )
        source_is_valid = source_identity is not None and (
            source_identity.subject == record.subject
            and source_identity.display_name == record.display_name
            and source_identity.roles == roles
        )
    else:
        source_named = resolve_auth_api_credential_by_digest(
            session,
            digest=record.source_credential_digest,
            now=reference_time,
        )
        source_is_valid = source_named is not None and (
            source_named.principal.authentication_type == "human_api_token"
            and source_named.principal.subject == record.subject
            and source_named.principal.display_name == record.display_name
            and source_named.principal.roles == roles
        )
    if not source_is_valid:
        return None

    return ResolvedAuthSession(
        record=record,
        principal=AuthPrincipal(
            subject=record.subject,
            display_name=record.display_name,
            roles=roles,
            authentication_type="session",
        ),
    )


def csrf_secret_matches(record: AuthSessionRecord, supplied_secret: str) -> bool:
    return hmac.compare_digest(
        secret_digest(supplied_secret),
        record.csrf_digest,
    )


def touch_auth_session(
    session: Session,
    *,
    configuration: AuthConfiguration,
    record: AuthSessionRecord,
    now: datetime | None = None,
) -> None:
    reference_time = _as_utc(now or _utc_now())
    absolute_expiry = _parse_utc(record.absolute_expires_at)
    if absolute_expiry is None:
        raise AuthSessionPersistenceError("Browser session state is invalid.")
    record.last_seen_at = reference_time.isoformat()
    record.idle_expires_at = min(
        reference_time
        + timedelta(minutes=configuration.session_idle_ttl_minutes),
        absolute_expiry,
    ).isoformat()
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthSessionPersistenceError(
            "Browser session persistence failed."
        ) from exc


def revoke_auth_session(
    session: Session,
    *,
    record: AuthSessionRecord,
    now: datetime | None = None,
) -> None:
    record.revoked_at = _as_utc(now or _utc_now()).isoformat()
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthSessionPersistenceError(
            "Browser session revocation failed."
        ) from exc
