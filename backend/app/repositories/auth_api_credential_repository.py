from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import AuthApiCredentialRecord


def add_auth_api_credential(
    session: Session,
    record: AuthApiCredentialRecord,
) -> None:
    session.add(record)


def load_auth_api_credential(
    session: Session,
    credential_id: str,
) -> AuthApiCredentialRecord | None:
    return session.get(AuthApiCredentialRecord, credential_id)


def load_auth_api_credential_by_digest(
    session: Session,
    credential_secret_digest: str,
) -> AuthApiCredentialRecord | None:
    statement = select(AuthApiCredentialRecord).where(
        AuthApiCredentialRecord.credential_secret_digest
        == credential_secret_digest
    )
    return session.scalars(statement).one_or_none()


def list_auth_api_credentials(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> list[AuthApiCredentialRecord]:
    statement = (
        select(AuthApiCredentialRecord)
        .order_by(
            AuthApiCredentialRecord.created_at.desc(),
            AuthApiCredentialRecord.credential_id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement))


def update_auth_api_credential_last_used(
    session: Session,
    *,
    credential_id: str,
    observed_at: str,
) -> None:
    statement = (
        update(AuthApiCredentialRecord)
        .where(
            AuthApiCredentialRecord.credential_id == credential_id,
            AuthApiCredentialRecord.revoked_at.is_(None),
        )
        .values(last_used_at=observed_at, updated_at=observed_at)
    )
    session.execute(statement)


def active_human_credentials(
    session: Session,
    *,
    reference_time: str,
) -> list[AuthApiCredentialRecord]:
    statement = select(AuthApiCredentialRecord).where(
        AuthApiCredentialRecord.caller_type == "human_api",
        AuthApiCredentialRecord.revoked_at.is_(None),
        AuthApiCredentialRecord.expires_at > reference_time,
    )
    return list(session.scalars(statement))
