"""Principal-based, scope-specific permission resolution and narrow mutations.

These are PH-5B assignment primitives, not HTTP authorization enforcement.
Callers obtain tenant authority independently through the accepted PH-3 binding.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    AuthPrincipalRecord,
    InstallationOperatorAssignmentRecord,
    ServicePrincipalPermissionRecord,
)
from app.models.principal_identity import PrincipalType, is_valid_principal_id
from app.repositories import authority_repository as repository
from app.repositories import principal_identity_repository
from app.security.authorization_policy import (
    INSTALLATION_ROLE_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
    InstallationRole,
    Permission,
    TenantRole,
    normalize_service_permissions,
)
from app.services.principal_identity import (
    PrincipalNotProvisionedError,
    PrincipalTypeMismatchError,
    require_active_principal,
)


class AuthorityAssignmentError(RuntimeError):
    """A durable assignment is missing, invalid, or concurrently modified."""


def _timestamp(now: datetime | None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _active_principal_for_update(
    session: Session, principal_id: str, principal_type: PrincipalType,
) -> AuthPrincipalRecord:
    require_active_principal(session, principal_id=principal_id, principal_type=principal_type)
    principal = principal_identity_repository.load_active_principal_for_update(session, principal_id)
    if principal is None:
        raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
    if principal.principal_type != principal_type.value:
        raise PrincipalTypeMismatchError("PRINCIPAL_TYPE_MISMATCH")
    return principal


def _serialized_permissions(permissions: list[str | Permission]) -> str:
    return json.dumps(normalize_service_permissions(permissions), separators=(",", ":"))


def _stored_permissions(record: ServicePrincipalPermissionRecord) -> frozenset[Permission]:
    try:
        if type(record.permissions_json) is not str or len(record.permissions_json) > 2048:
            raise ValueError
        values = json.loads(record.permissions_json)
        canonical = _serialized_permissions(values)
        if canonical != record.permissions_json or type(record.row_version) is not int or record.row_version < 1:
            raise ValueError
    except (TypeError, ValueError, RecursionError) as exc:
        raise AuthorityAssignmentError("SERVICE_PERMISSIONS_INVALID") from exc
    return frozenset(Permission(value) for value in values)


def resolve_tenant_permissions(
    session: Session, *, principal_id: str, tenant_id: str,
) -> frozenset[Permission]:
    require_active_principal(session, principal_id=principal_id, principal_type=PrincipalType.HUMAN)
    role = repository.load_active_membership_role(session, principal_id=principal_id, tenant_id=tenant_id)
    if role is None:
        return frozenset()
    try:
        parsed = TenantRole(role)
    except ValueError as exc:
        raise AuthorityAssignmentError("TENANT_ROLE_INVALID") from exc
    return TENANT_ROLE_PERMISSIONS[parsed]


def resolve_service_permissions(
    session: Session, *, principal_id: str,
) -> frozenset[Permission]:
    require_active_principal(session, principal_id=principal_id, principal_type=PrincipalType.SERVICE)
    record = repository.load_service_permission_assignment(session, principal_id)
    if record is None:
        raise AuthorityAssignmentError("SERVICE_PERMISSIONS_UNAVAILABLE")
    return _stored_permissions(record)


def resolve_installation_permissions(
    session: Session, *, principal_id: str,
) -> frozenset[Permission]:
    require_active_principal(session, principal_id=principal_id, principal_type=PrincipalType.HUMAN)
    record = repository.load_installation_operator_assignment(session, principal_id)
    if record is None or record.status == "disabled":
        return frozenset()
    if record.status != "active":
        raise AuthorityAssignmentError("INSTALLATION_ASSIGNMENT_INVALID")
    return INSTALLATION_ROLE_PERMISSIONS[InstallationRole.OPERATOR]


def create_service_permission_assignment(
    session: Session, *, principal_id: str, permissions: list[str | Permission],
    now: datetime | None = None,
) -> ServicePrincipalPermissionRecord:
    """Flush only: principal, assignment and credential share caller's transaction."""
    canonical = _serialized_permissions(permissions)
    _active_principal_for_update(session, principal_id, PrincipalType.SERVICE)
    existing = repository.load_service_permission_assignment(session, principal_id)
    if existing is not None:
        _stored_permissions(existing)
        if existing.permissions_json != canonical:
            raise AuthorityAssignmentError("SERVICE_PERMISSIONS_ALREADY_ASSIGNED")
        return existing
    timestamp = _timestamp(now)
    record = ServicePrincipalPermissionRecord(
        principal_id=principal_id, permissions_json=canonical, row_version=1,
        created_at=timestamp, updated_at=timestamp,
    )
    repository.add_service_permission_assignment(session, record)
    session.flush()
    return record


def update_service_permissions(
    session: Session, *, principal_id: str, permissions: list[str | Permission],
    expected_row_version: int, now: datetime | None = None,
) -> ServicePrincipalPermissionRecord:
    canonical = _serialized_permissions(permissions)
    if type(expected_row_version) is not int or expected_row_version < 1:
        raise AuthorityAssignmentError("SERVICE_PERMISSIONS_CONCURRENT_MODIFICATION")
    try:
        _active_principal_for_update(session, principal_id, PrincipalType.SERVICE)
        existing = repository.load_service_permission_assignment(session, principal_id)
        if existing is None:
            raise AuthorityAssignmentError("SERVICE_PERMISSIONS_UNAVAILABLE")
        _stored_permissions(existing)
        if not repository.compare_and_set_service_permissions(
            session, principal_id=principal_id, expected_row_version=expected_row_version,
            permissions_json=canonical, updated_at=_timestamp(now),
        ):
            raise AuthorityAssignmentError("SERVICE_PERMISSIONS_CONCURRENT_MODIFICATION")
        session.commit()
    except (AuthorityAssignmentError, SQLAlchemyError):
        session.rollback()
        raise
    result = repository.load_service_permission_assignment(session, principal_id)
    if result is None:
        raise AuthorityAssignmentError("SERVICE_PERMISSIONS_UNAVAILABLE")
    return result


def _human_principal(session: Session, principal_id: str) -> AuthPrincipalRecord:
    if not isinstance(principal_id, str) or not is_valid_principal_id(principal_id):
        raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
    principal = principal_identity_repository.load_principal(session, principal_id)
    if principal is None:
        raise PrincipalNotProvisionedError("PRINCIPAL_NOT_PROVISIONED")
    session.refresh(principal)
    if principal.principal_type != PrincipalType.HUMAN.value:
        raise PrincipalTypeMismatchError("PRINCIPAL_TYPE_MISMATCH")
    return principal


def grant_installation_operator(
    session: Session, *, principal_id: str, now: datetime | None = None,
) -> InstallationOperatorAssignmentRecord:
    try:
        # Serialize grants for one human across independent PostgreSQL sessions.
        _active_principal_for_update(session, principal_id, PrincipalType.HUMAN)
        record = repository.load_installation_operator_assignment(session, principal_id)
        if record is None:
            timestamp = _timestamp(now)
            record = InstallationOperatorAssignmentRecord(
                principal_id=principal_id, status="active", created_at=timestamp, updated_at=timestamp,
            )
            repository.add_installation_operator_assignment(session, record)
        elif record.status == "disabled":
            record.status = "active"
            record.updated_at = _timestamp(now)
        elif record.status != "active":
            raise AuthorityAssignmentError("INSTALLATION_ASSIGNMENT_INVALID")
        session.commit()
        return record
    except (AuthorityAssignmentError, SQLAlchemyError):
        session.rollback()
        raise


def disable_installation_operator(
    session: Session, *, principal_id: str, now: datetime | None = None,
) -> InstallationOperatorAssignmentRecord | None:
    # Explicit revocation remains available if the human was already disabled.
    _human_principal(session, principal_id)
    try:
        record = repository.load_installation_operator_assignment(session, principal_id)
        if record is None:
            return None
        if record.status not in {"active", "disabled"}:
            raise AuthorityAssignmentError("INSTALLATION_ASSIGNMENT_INVALID")
        if record.status == "active":
            record.status = "disabled"
            record.updated_at = _timestamp(now)
        session.commit()
        return record
    except (AuthorityAssignmentError, SQLAlchemyError):
        session.rollback()
        raise


def get_installation_operator_status(session: Session, *, principal_id: str) -> dict[str, object]:
    principal = _human_principal(session, principal_id)
    record = repository.load_installation_operator_assignment(session, principal_id)
    if record is not None and record.status not in {"active", "disabled"}:
        raise AuthorityAssignmentError("INSTALLATION_ASSIGNMENT_INVALID")
    return {
        "principal_id": principal.principal_id,
        "principal_status": principal.status,
        "assignment_status": record.status if record is not None else "unassigned",
        "effective": principal.status == "active" and record is not None and record.status == "active",
    }
