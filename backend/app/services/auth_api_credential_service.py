from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import AuthApiCredentialRecord
from app.models.auth import (
    ApiCredentialCallerType,
    ApiCredentialCreate,
    ApiCredentialCreated,
    ApiCredentialView,
)
from app.repositories.auth_api_credential_repository import (
    active_human_credentials,
    add_auth_api_credential,
    load_auth_api_credential_by_digest,
    update_auth_api_credential_last_used,
)
from app.security.principals import AuthPrincipal


API_CREDENTIAL_PREFIX = "topo_api_"
MAX_GENERATION_ATTEMPTS = 3


class AuthApiCredentialPersistenceError(RuntimeError):
    """A named API-credential persistence operation failed closed."""


class InactiveAuthApiCredentialError(RuntimeError):
    """A digest matched a named credential that is not active."""


@dataclass(frozen=True)
class ResolvedApiCredential:
    record: AuthApiCredentialRecord
    principal: AuthPrincipal


def credential_secret_digest(secret: str) -> str:
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


def _record_roles(record: AuthApiCredentialRecord) -> tuple[str, ...] | None:
    try:
        value = json.loads(record.roles_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, list)
        or any(
            not isinstance(role, str) or not role or role != role.strip()
            for role in value
        )
        or len(set(value)) != len(value)
    ):
        return None
    return tuple(value)


def _active_resolution(
    record: AuthApiCredentialRecord,
    *,
    now: datetime,
) -> ResolvedApiCredential | None:
    if record.revoked_at is not None:
        return None
    if (
        not record.subject
        or record.subject != record.subject.strip()
        or record.subject.lower() == "unknown"
        or not record.display_name
    ):
        return None
    expiry = _parse_utc(record.expires_at)
    roles = _record_roles(record)
    if expiry is None or now >= expiry or roles is None:
        return None
    try:
        caller_type = ApiCredentialCallerType(record.caller_type)
    except ValueError:
        return None
    authentication_type = (
        "human_api_token"
        if caller_type is ApiCredentialCallerType.HUMAN_API
        else "service_api_token"
    )
    return ResolvedApiCredential(
        record=record,
        principal=AuthPrincipal(
            subject=record.subject,
            display_name=record.display_name,
            roles=roles,
            authentication_type=authentication_type,
        ),
    )


def create_auth_api_credential(
    session: Session,
    *,
    request: ApiCredentialCreate,
    created_by_subject: str,
    now: datetime | None = None,
) -> ApiCredentialCreated:
    if (
        not created_by_subject
        or created_by_subject != created_by_subject.strip()
        or created_by_subject.lower() == "unknown"
    ):
        raise ValueError("A stable creator subject is required.")
    created_at = _as_utc(now or _utc_now())
    expires_at = created_at + timedelta(days=request.expires_in_days)
    display_name = request.display_name or request.subject

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        raw_secret = API_CREDENTIAL_PREFIX + secrets.token_urlsafe(48)
        record = AuthApiCredentialRecord(
            credential_id=f"api-credential:{uuid4()}",
            credential_secret_digest=credential_secret_digest(raw_secret),
            credential_hint=raw_secret[-8:],
            name=request.name,
            caller_type=request.caller_type.value,
            subject=request.subject,
            display_name=display_name,
            roles_json=json.dumps(request.roles, separators=(",", ":")),
            created_at=created_at.isoformat(),
            created_by_subject=created_by_subject,
            expires_at=expires_at.isoformat(),
            revoked_at=None,
            revoked_by_subject=None,
            last_used_at=None,
            updated_at=created_at.isoformat(),
        )
        try:
            add_auth_api_credential(session, record)
            session.commit()
            return credential_created_view(record, raw_secret)
        except IntegrityError as exc:
            session.rollback()
            if attempt + 1 == MAX_GENERATION_ATTEMPTS:
                raise AuthApiCredentialPersistenceError(
                    "API credential generation failed safely."
                ) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise AuthApiCredentialPersistenceError(
                "API credential persistence failed."
            ) from exc
    raise AuthApiCredentialPersistenceError(
        "API credential generation failed safely."
    )


def resolve_auth_api_credential_by_digest(
    session: Session,
    *,
    digest: str,
    now: datetime | None = None,
) -> ResolvedApiCredential | None:
    record = load_auth_api_credential_by_digest(session, digest)
    if record is None:
        return None
    return _active_resolution(record, now=_as_utc(now or _utc_now()))


def authenticate_auth_api_credential(
    session: Session,
    *,
    raw_secret: str,
    now: datetime | None = None,
) -> ResolvedApiCredential | None:
    reference_time = _as_utc(now or _utc_now())
    digest = credential_secret_digest(raw_secret)
    record = load_auth_api_credential_by_digest(session, digest)
    if record is None:
        return None
    resolved = _active_resolution(record, now=reference_time)
    if resolved is None:
        raise InactiveAuthApiCredentialError(
            "The named API credential is inactive."
        )
    observed_at = reference_time.isoformat()
    try:
        update_auth_api_credential_last_used(
            session,
            credential_id=resolved.record.credential_id,
            observed_at=observed_at,
        )
        session.commit()
        resolved.record.last_used_at = observed_at
        resolved.record.updated_at = observed_at
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthApiCredentialPersistenceError(
            "API credential usage persistence failed."
        ) from exc
    return resolved


def revoke_auth_api_credential(
    session: Session,
    *,
    record: AuthApiCredentialRecord,
    revoked_by_subject: str,
    now: datetime | None = None,
) -> None:
    if (
        not revoked_by_subject
        or revoked_by_subject != revoked_by_subject.strip()
        or revoked_by_subject.lower() == "unknown"
    ):
        raise ValueError("A stable revoker subject is required.")
    if record.revoked_at is not None:
        return
    revoked_at = _as_utc(now or _utc_now()).isoformat()
    record.revoked_at = revoked_at
    record.revoked_by_subject = revoked_by_subject
    record.updated_at = revoked_at
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthApiCredentialPersistenceError(
            "API credential revocation failed."
        ) from exc


def credential_view(record: AuthApiCredentialRecord) -> ApiCredentialView:
    roles = _record_roles(record)
    if roles is None:
        raise AuthApiCredentialPersistenceError(
            "API credential metadata is invalid."
        )
    try:
        caller_type = ApiCredentialCallerType(record.caller_type)
    except ValueError as exc:
        raise AuthApiCredentialPersistenceError(
            "API credential metadata is invalid."
        ) from exc
    return ApiCredentialView(
        credential_id=record.credential_id,
        credential_hint=record.credential_hint,
        name=record.name,
        caller_type=caller_type,
        subject=record.subject,
        display_name=record.display_name,
        roles=list(roles),
        created_at=record.created_at,
        created_by_subject=record.created_by_subject,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        revoked_by_subject=record.revoked_by_subject,
        last_used_at=record.last_used_at,
        updated_at=record.updated_at,
    )


def credential_created_view(
    record: AuthApiCredentialRecord,
    raw_secret: str,
) -> ApiCredentialCreated:
    return ApiCredentialCreated(
        **credential_view(record).model_dump(),
        api_credential=raw_secret,
    )


def has_active_human_admin_credential(
    session: Session,
    *,
    now: datetime | None = None,
) -> bool:
    reference_time = _as_utc(now or _utc_now())
    records = active_human_credentials(
        session,
        reference_time=reference_time.isoformat(),
    )
    return any(
        (resolved := _active_resolution(record, now=reference_time)) is not None
        and "admin" in resolved.principal.roles
        for record in records
    )
