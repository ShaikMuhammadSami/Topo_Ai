from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import TenantMembershipRecord, TenantRecord
from app.models.principal_identity import LEGACY_LOCAL_ISSUER, PrincipalType
from app.models.tenant import (
    TenantMembershipStatus,
    TenantMembershipView,
    TenantStatus,
    TenantView,
)
from app.repositories import tenant_repository
from app.repositories import principal_identity_repository
from app.security.authorization_policy import TenantRole
from app.services.principal_identity import (
    provision_external_human_principal,
    require_active_principal,
)


MAX_ID_GENERATION_ATTEMPTS = 3


class TenantPersistenceError(RuntimeError):
    """A tenant control-plane persistence operation failed safely."""


class TenantMembershipNotFoundError(RuntimeError):
    """A membership is absent from the already-authorized tenant."""


class ActiveTenantRequiredError(RuntimeError):
    """The target tenant is unavailable for a control-plane mutation."""


def _utc_now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _stable_subject(subject: str) -> str:
    if (
        not subject
        or subject != subject.strip()
        or subject.lower() == "unknown"
    ):
        raise ValueError("A stable subject is required.")
    return subject


def tenant_view(
    tenant: TenantRecord,
    membership: TenantMembershipRecord,
) -> TenantView:
    return TenantView(
        tenant_id=tenant.tenant_id,
        display_name=tenant.display_name,
        status=TenantStatus(tenant.status),
        membership_id=membership.membership_id,
        created_at=tenant.created_at,
    )


def membership_view(
    session: Session,
    record: TenantMembershipRecord,
) -> TenantMembershipView:
    principal = principal_identity_repository.load_principal(
        session,
        record.principal_id,
    )
    if principal is None or principal.principal_type != PrincipalType.HUMAN.value:
        raise TenantPersistenceError("Tenant membership identity is invalid.")
    identities = principal_identity_repository.list_external_identities_for_principal(
        session,
        record.principal_id,
    )
    identity = identities[0] if identities else None
    return TenantMembershipView(
        membership_id=record.membership_id,
        tenant_id=record.tenant_id,
        principal_id=record.principal_id,
        principal_type=principal.principal_type,
        display_name=principal.display_name,
        external_issuer=identity.issuer if identity is not None else None,
        external_subject=identity.subject if identity is not None else None,
        subject=identity.subject if identity is not None else None,
        status=TenantMembershipStatus(record.status),
        role=TenantRole(record.role),
        created_at=record.created_at,
        updated_at=record.updated_at,
        created_by_subject=record.created_by_subject,
    )


def create_tenant_with_creator_membership(
    session: Session,
    *,
    display_name: str,
    creator_subject: str,
    creator_principal_id: str | None = None,
    now: datetime | None = None,
) -> TenantView:
    creator = _stable_subject(creator_subject)
    if creator_principal_id is None:
        creator_identity = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject=creator,
            display_name=creator,
            authentication_type="api_token",
        )
        creator_principal_id = creator_identity.principal_id
    if creator_principal_id is None:
        raise TenantPersistenceError("Principal identity is unavailable.")
    require_active_principal(
        session,
        principal_id=creator_principal_id,
        principal_type=PrincipalType.HUMAN,
    )
    created_at = _utc_now_iso(now)

    for attempt in range(MAX_ID_GENERATION_ATTEMPTS):
        tenant = TenantRecord(
            tenant_id=f"tenant:{uuid4()}",
            display_name=display_name,
            status=TenantStatus.ACTIVE.value,
            created_at=created_at,
            updated_at=created_at,
            created_by_subject=creator,
        )
        membership = TenantMembershipRecord(
            membership_id=f"tenant-membership:{uuid4()}",
            tenant_id=tenant.tenant_id,
            principal_id=creator_principal_id,
            status=TenantMembershipStatus.ACTIVE.value,
            role=TenantRole.ADMIN.value,
            created_at=created_at,
            updated_at=created_at,
            created_by_subject=creator,
        )
        try:
            tenant_repository.add_tenant(session, tenant)
            session.flush()
            tenant_repository.add_tenant_membership(session, membership)
            session.commit()
            return tenant_view(tenant, membership)
        except IntegrityError as exc:
            session.rollback()
            if attempt + 1 == MAX_ID_GENERATION_ATTEMPTS:
                raise TenantPersistenceError(
                    "Tenant identity generation failed safely."
                ) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise TenantPersistenceError(
                "Tenant persistence failed."
            ) from exc
    raise TenantPersistenceError("Tenant identity generation failed safely.")


def add_or_reactivate_tenant_membership(
    session: Session,
    *,
    tenant_id: str,
    subject: str | None,
    role: TenantRole,
    principal_id: str | None = None,
    created_by_subject: str,
    created_by_principal_id: str | None = None,
    now: datetime | None = None,
) -> TenantMembershipView:
    # Explicit authority input, never derived from the caller's legacy roles.
    assigned_role = TenantRole(role)
    creator = _stable_subject(created_by_subject)
    timestamp = _utc_now_iso(now)

    if created_by_principal_id is not None:
        require_active_principal(
            session,
            principal_id=created_by_principal_id,
            principal_type=PrincipalType.HUMAN,
        )
    if principal_id is None:
        if subject is None:
            raise ValueError("principal_id or explicit legacy subject is required")
        target_subject = _stable_subject(subject)
        identity = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject=target_subject,
            display_name=target_subject,
            authentication_type="api_token",
        )
        principal_id = identity.principal_id
    elif subject is not None:
        target_subject = _stable_subject(subject)
        identity = principal_identity_repository.load_external_identity(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject=target_subject,
        )
        if identity is None or identity.principal_id != principal_id:
            raise ValueError("Explicit subject does not identify principal_id")
    if principal_id is None:
        raise TenantPersistenceError("Principal identity is unavailable.")
    require_active_principal(
        session,
        principal_id=principal_id,
        principal_type=PrincipalType.HUMAN,
    )

    if tenant_repository.load_active_tenant(session, tenant_id) is None:
        raise ActiveTenantRequiredError("The tenant is not active.")

    existing = tenant_repository.load_tenant_membership(
        session,
        tenant_id=tenant_id,
        principal_id=principal_id,
    )
    if existing is not None:
        if existing.status == TenantMembershipStatus.DISABLED.value:
            existing.status = TenantMembershipStatus.ACTIVE.value
            existing.role = assigned_role.value
            existing.updated_at = timestamp
            try:
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise TenantPersistenceError(
                    "Tenant membership persistence failed."
                ) from exc
        elif existing.role != assigned_role.value:
            raise ValueError("An active membership already has a different role.")
        return membership_view(session, existing)

    record = TenantMembershipRecord(
        membership_id=f"tenant-membership:{uuid4()}",
        tenant_id=tenant_id,
        principal_id=principal_id,
        status=TenantMembershipStatus.ACTIVE.value,
        role=assigned_role.value,
        created_at=timestamp,
        updated_at=timestamp,
        created_by_subject=creator,
    )
    try:
        tenant_repository.add_tenant_membership(session, record)
        session.commit()
        return membership_view(session, record)
    except IntegrityError as exc:
        session.rollback()
        concurrent = tenant_repository.load_tenant_membership(
            session,
            tenant_id=tenant_id,
            principal_id=principal_id,
        )
        if (
            concurrent is not None
            and concurrent.status == TenantMembershipStatus.ACTIVE.value
            and concurrent.role == assigned_role.value
        ):
            return membership_view(session, concurrent)
        raise TenantPersistenceError(
            "Tenant membership persistence failed."
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise TenantPersistenceError(
            "Tenant membership persistence failed."
        ) from exc


def disable_tenant_membership(
    session: Session,
    *,
    tenant_id: str,
    membership_id: str,
    now: datetime | None = None,
) -> TenantMembershipView:
    record = tenant_repository.load_tenant_membership_by_id(
        session,
        tenant_id=tenant_id,
        membership_id=membership_id,
    )
    if record is None:
        raise TenantMembershipNotFoundError("Tenant membership not found.")
    if record.status == TenantMembershipStatus.DISABLED.value:
        return membership_view(session, record)
    record.status = TenantMembershipStatus.DISABLED.value
    record.updated_at = _utc_now_iso(now)
    try:
        session.commit()
        return membership_view(session, record)
    except SQLAlchemyError as exc:
        session.rollback()
        raise TenantPersistenceError(
            "Tenant membership persistence failed."
        ) from exc
