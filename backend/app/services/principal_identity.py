from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import AuthPrincipalRecord, ExternalIdentityRecord
from app.models.principal_identity import (
    ExternalIdentityStatus,
    PrincipalStatus,
    PrincipalType,
    is_valid_principal_id,
    new_external_identity_id,
    new_principal_id,
    validate_identity_authority,
)
from app.repositories import principal_identity_repository as repository
from app.security.principals import AuthPrincipal


class PrincipalIdentityError(RuntimeError):
    """Issuer-aware identity persistence failed closed."""


class PrincipalNotProvisionedError(PrincipalIdentityError):
    """A trusted external identity has no durable Topo principal."""


class PrincipalTypeMismatchError(PrincipalIdentityError):
    """A principal was used through an incompatible authentication path."""


def _utc_now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def require_active_principal(
    session: Session,
    *,
    principal_id: str,
    principal_type: PrincipalType | None = None,
) -> AuthPrincipalRecord:
    if not is_valid_principal_id(principal_id):
        raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
    principal = repository.load_active_principal(session, principal_id)
    if principal is None:
        raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
    if principal_type is not None and principal.principal_type != principal_type.value:
        raise PrincipalTypeMismatchError("PRINCIPAL_TYPE_MISMATCH")
    return principal


def auth_principal_for_external_identity(
    session: Session,
    *,
    issuer: str,
    subject: str,
    authentication_type: str,
    roles: tuple[str, ...] = (),
) -> AuthPrincipal:
    trusted_issuer = validate_identity_authority(issuer, field_name="issuer")
    trusted_subject = validate_identity_authority(subject, field_name="subject")
    identity = repository.load_active_external_identity(
        session,
        issuer=trusted_issuer,
        subject=trusted_subject,
    )
    if identity is None:
        raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
    principal = require_active_principal(
        session,
        principal_id=identity.principal_id,
        principal_type=PrincipalType.HUMAN,
    )
    return AuthPrincipal(
        principal_id=principal.principal_id,
        principal_type=principal.principal_type,
        subject=identity.subject,
        external_issuer=identity.issuer,
        external_subject=identity.subject,
        display_name=principal.display_name,
        roles=roles,
        authentication_type=authentication_type,
    )


def provision_external_human_principal(
    session: Session,
    *,
    issuer: str,
    subject: str,
    display_name: str,
    authentication_type: str,
    roles: tuple[str, ...] = (),
    now: datetime | None = None,
) -> AuthPrincipal:
    trusted_issuer = validate_identity_authority(issuer, field_name="issuer")
    trusted_subject = validate_identity_authority(subject, field_name="subject")
    if not display_name or display_name != display_name.strip() or len(display_name) > 500:
        raise ValueError("display_name must be a bounded non-empty value")

    existing = repository.load_external_identity(
        session,
        issuer=trusted_issuer,
        subject=trusted_subject,
    )
    if existing is not None:
        if existing.status != ExternalIdentityStatus.ACTIVE.value:
            raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
        return auth_principal_for_external_identity(
            session,
            issuer=trusted_issuer,
            subject=trusted_subject,
            authentication_type=authentication_type,
            roles=roles,
        )

    timestamp = _utc_now_iso(now)
    try:
        with session.begin_nested():
            principal = AuthPrincipalRecord(
                principal_id=new_principal_id(),
                principal_type=PrincipalType.HUMAN.value,
                display_name=display_name,
                status=PrincipalStatus.ACTIVE.value,
                created_at=timestamp,
                updated_at=timestamp,
            )
            identity = ExternalIdentityRecord(
                external_identity_id=new_external_identity_id(),
                principal_id=principal.principal_id,
                issuer=trusted_issuer,
                subject=trusted_subject,
                status=ExternalIdentityStatus.ACTIVE.value,
                created_at=timestamp,
                updated_at=timestamp,
            )
            repository.add_principal(session, principal)
            repository.add_external_identity(session, identity)
            session.flush()
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = repository.load_external_identity(
            session,
            issuer=trusted_issuer,
            subject=trusted_subject,
        )
        if existing is None:
            raise PrincipalIdentityError("PRINCIPAL_IDENTITY_CONFLICT")
    except SQLAlchemyError as exc:
        session.rollback()
        raise PrincipalIdentityError("PRINCIPAL_IDENTITY_UNAVAILABLE") from exc

    return auth_principal_for_external_identity(
        session,
        issuer=trusted_issuer,
        subject=trusted_subject,
        authentication_type=authentication_type,
        roles=roles,
    )


def create_service_principal(
    session: Session,
    *,
    display_name: str,
    now: datetime | None = None,
) -> AuthPrincipalRecord:
    if not display_name or display_name != display_name.strip() or len(display_name) > 500:
        raise ValueError("display_name must be a bounded non-empty value")
    timestamp = _utc_now_iso(now)
    principal = AuthPrincipalRecord(
        principal_id=new_principal_id(),
        principal_type=PrincipalType.SERVICE.value,
        display_name=display_name,
        status=PrincipalStatus.ACTIVE.value,
        created_at=timestamp,
        updated_at=timestamp,
    )
    repository.add_principal(session, principal)
    session.flush()
    return principal
