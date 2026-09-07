"""Durable authority assignments independent of PH-3 domain predicates."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    InstallationOperatorAssignmentRecord,
    ServicePrincipalPermissionRecord,
    TenantMembershipRecord,
    TenantRecord,
)


def load_active_membership_role(
    session: Session, *, principal_id: str, tenant_id: str,
) -> str | None:
    # Select a scalar so long-lived ORM identity maps cannot retain an old role.
    statement = (
        select(TenantMembershipRecord.role)
        .join(TenantRecord, TenantRecord.tenant_id == TenantMembershipRecord.tenant_id)
        .where(
            TenantMembershipRecord.principal_id == principal_id,
            TenantMembershipRecord.tenant_id == tenant_id,
            TenantMembershipRecord.status == "active",
            TenantRecord.status == "active",
        )
    )
    return session.scalar(statement)


def load_service_permission_assignment(
    session: Session, principal_id: str,
) -> ServicePrincipalPermissionRecord | None:
    statement = (
        select(ServicePrincipalPermissionRecord)
        .where(ServicePrincipalPermissionRecord.principal_id == principal_id)
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def add_service_permission_assignment(
    session: Session, record: ServicePrincipalPermissionRecord,
) -> None:
    session.add(record)


def compare_and_set_service_permissions(
    session: Session, *, principal_id: str, expected_row_version: int,
    permissions_json: str, updated_at: str,
) -> bool:
    statement = (
        update(ServicePrincipalPermissionRecord)
        .where(
            ServicePrincipalPermissionRecord.principal_id == principal_id,
            ServicePrincipalPermissionRecord.row_version == expected_row_version,
        )
        .values(
            permissions_json=permissions_json,
            row_version=expected_row_version + 1,
            updated_at=updated_at,
        )
        .execution_options(synchronize_session=False)
    )
    return session.execute(statement).rowcount == 1


def load_installation_operator_assignment(
    session: Session, principal_id: str,
) -> InstallationOperatorAssignmentRecord | None:
    statement = (
        select(InstallationOperatorAssignmentRecord)
        .where(InstallationOperatorAssignmentRecord.principal_id == principal_id)
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def add_installation_operator_assignment(
    session: Session, record: InstallationOperatorAssignmentRecord,
) -> None:
    session.add(record)
