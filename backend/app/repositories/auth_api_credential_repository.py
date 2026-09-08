from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import AuthApiCredentialRecord, ServiceApiTenantBindingRecord


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
    caller_type: str,
    principal_id: str | None = None,
    tenant_id: str | None = None,
) -> list[AuthApiCredentialRecord]:
    statement = select(AuthApiCredentialRecord)
    if caller_type == "human_api" and principal_id and tenant_id is None:
        statement = statement.where(
            AuthApiCredentialRecord.caller_type == "human_api",
            AuthApiCredentialRecord.principal_id == principal_id,
        )
    elif caller_type == "service_api" and tenant_id and principal_id is None:
        statement = statement.join(
            ServiceApiTenantBindingRecord,
            ServiceApiTenantBindingRecord.credential_id
            == AuthApiCredentialRecord.credential_id,
        ).where(
            AuthApiCredentialRecord.caller_type == "service_api",
            ServiceApiTenantBindingRecord.tenant_id == tenant_id,
        )
    else:
        raise ValueError("CREDENTIAL_LIST_SCOPE_REQUIRED")
    statement = (
        statement
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
