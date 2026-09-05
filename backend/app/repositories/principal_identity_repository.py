from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuthPrincipalRecord, ExternalIdentityRecord


def add_principal(session: Session, record: AuthPrincipalRecord) -> None:
    session.add(record)


def add_external_identity(
    session: Session,
    record: ExternalIdentityRecord,
) -> None:
    session.add(record)


def load_principal(
    session: Session,
    principal_id: str,
) -> AuthPrincipalRecord | None:
    return session.get(AuthPrincipalRecord, principal_id)


def load_active_principal(
    session: Session,
    principal_id: str,
) -> AuthPrincipalRecord | None:
    statement = select(AuthPrincipalRecord).where(
        AuthPrincipalRecord.principal_id == principal_id,
        AuthPrincipalRecord.status == "active",
    )
    return session.scalars(statement).one_or_none()


def load_active_principal_for_update(
    session: Session,
    principal_id: str,
) -> AuthPrincipalRecord | None:
    statement = (
        select(AuthPrincipalRecord)
        .where(
            AuthPrincipalRecord.principal_id == principal_id,
            AuthPrincipalRecord.status == "active",
        )
        .with_for_update()
    )
    return session.scalars(statement).one_or_none()


def load_external_identity(
    session: Session,
    *,
    issuer: str,
    subject: str,
) -> ExternalIdentityRecord | None:
    statement = select(ExternalIdentityRecord).where(
        ExternalIdentityRecord.issuer == issuer,
        ExternalIdentityRecord.subject == subject,
    )
    return session.scalars(statement).one_or_none()


def load_active_external_identity(
    session: Session,
    *,
    issuer: str,
    subject: str,
) -> ExternalIdentityRecord | None:
    statement = select(ExternalIdentityRecord).where(
        ExternalIdentityRecord.issuer == issuer,
        ExternalIdentityRecord.subject == subject,
        ExternalIdentityRecord.status == "active",
    )
    return session.scalars(statement).one_or_none()


def list_external_identities_for_principal(
    session: Session,
    principal_id: str,
) -> list[ExternalIdentityRecord]:
    statement = (
        select(ExternalIdentityRecord)
        .where(ExternalIdentityRecord.principal_id == principal_id)
        .order_by(
            ExternalIdentityRecord.created_at,
            ExternalIdentityRecord.external_identity_id,
        )
    )
    return list(session.scalars(statement))
