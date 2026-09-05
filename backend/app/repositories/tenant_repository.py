from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuthApiCredentialRecord,
    ServiceApiTenantBindingRecord,
    TenantMembershipRecord,
    TenantRecord,
)


def add_tenant(session: Session, record: TenantRecord) -> None:
    session.add(record)


def load_tenant(session: Session, tenant_id: str) -> TenantRecord | None:
    return session.get(TenantRecord, tenant_id)


def load_active_tenant(
    session: Session,
    tenant_id: str,
) -> TenantRecord | None:
    statement = select(TenantRecord).where(
        TenantRecord.tenant_id == tenant_id,
        TenantRecord.status == "active",
    )
    return session.scalars(statement).one_or_none()


def add_tenant_membership(
    session: Session,
    record: TenantMembershipRecord,
) -> None:
    session.add(record)


def load_tenant_membership(
    session: Session,
    *,
    tenant_id: str,
    principal_id: str,
) -> TenantMembershipRecord | None:
    statement = select(TenantMembershipRecord).where(
        TenantMembershipRecord.tenant_id == tenant_id,
        TenantMembershipRecord.principal_id == principal_id,
    )
    return session.scalars(statement).one_or_none()


def load_active_tenant_membership(
    session: Session,
    *,
    tenant_id: str,
    principal_id: str,
) -> TenantMembershipRecord | None:
    statement = select(TenantMembershipRecord).where(
        TenantMembershipRecord.tenant_id == tenant_id,
        TenantMembershipRecord.principal_id == principal_id,
        TenantMembershipRecord.status == "active",
    )
    return session.scalars(statement).one_or_none()


def load_active_human_tenant_context(
    session: Session,
    *,
    tenant_id: str,
    principal_id: str,
) -> tuple[TenantRecord, TenantMembershipRecord] | None:
    statement = (
        select(TenantRecord, TenantMembershipRecord)
        .join(
            TenantMembershipRecord,
            TenantMembershipRecord.tenant_id == TenantRecord.tenant_id,
        )
        .where(
            TenantRecord.tenant_id == tenant_id,
            TenantRecord.status == "active",
            TenantMembershipRecord.principal_id == principal_id,
            TenantMembershipRecord.status == "active",
        )
    )
    row = session.execute(statement).one_or_none()
    return None if row is None else (row[0], row[1])


def list_active_tenants_for_principal(
    session: Session,
    *,
    principal_id: str,
) -> list[tuple[TenantRecord, TenantMembershipRecord]]:
    statement = (
        select(TenantRecord, TenantMembershipRecord)
        .join(
            TenantMembershipRecord,
            TenantMembershipRecord.tenant_id == TenantRecord.tenant_id,
        )
        .where(
            TenantMembershipRecord.principal_id == principal_id,
            TenantMembershipRecord.status == "active",
            TenantRecord.status == "active",
        )
        .order_by(TenantRecord.created_at, TenantRecord.tenant_id)
    )
    return [(tenant, membership) for tenant, membership in session.execute(statement)]


def list_tenant_memberships(
    session: Session,
    *,
    tenant_id: str,
) -> list[TenantMembershipRecord]:
    statement = (
        select(TenantMembershipRecord)
        .where(TenantMembershipRecord.tenant_id == tenant_id)
        .order_by(
            TenantMembershipRecord.created_at,
            TenantMembershipRecord.membership_id,
        )
    )
    return list(session.scalars(statement))


def load_tenant_membership_by_id(
    session: Session,
    *,
    tenant_id: str,
    membership_id: str,
) -> TenantMembershipRecord | None:
    statement = select(TenantMembershipRecord).where(
        TenantMembershipRecord.tenant_id == tenant_id,
        TenantMembershipRecord.membership_id == membership_id,
    )
    return session.scalars(statement).one_or_none()


def add_service_api_tenant_binding(
    session: Session,
    record: ServiceApiTenantBindingRecord,
) -> None:
    session.add(record)


def load_service_api_tenant_binding(
    session: Session,
    credential_id: str,
) -> ServiceApiTenantBindingRecord | None:
    statement = select(ServiceApiTenantBindingRecord).where(
        ServiceApiTenantBindingRecord.credential_id == credential_id
    )
    return session.scalars(statement).one_or_none()


def service_binding_tenant_ids(
    session: Session,
    credential_ids: Iterable[str],
) -> dict[str, str]:
    identifiers = tuple(dict.fromkeys(credential_ids))
    if not identifiers:
        return {}
    statement = select(ServiceApiTenantBindingRecord).where(
        ServiceApiTenantBindingRecord.credential_id.in_(identifiers)
    )
    return {
        binding.credential_id: binding.tenant_id
        for binding in session.scalars(statement)
    }


def service_principal_tenant_ids(
    session: Session,
    principal_id: str,
) -> set[str]:
    statement = (
        select(ServiceApiTenantBindingRecord.tenant_id)
        .join(
            AuthApiCredentialRecord,
            AuthApiCredentialRecord.credential_id
            == ServiceApiTenantBindingRecord.credential_id,
        )
        .where(
            AuthApiCredentialRecord.principal_id == principal_id,
            AuthApiCredentialRecord.caller_type == "service_api",
        )
    )
    return set(session.scalars(statement))
