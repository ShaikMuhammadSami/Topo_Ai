from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import TenantMembershipRecord, TenantRecord
from app.models.tenant import (
    TenantMembershipStatus,
    TenantMembershipView,
    TenantStatus,
    TenantView,
)
from app.repositories import tenant_repository


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


def membership_view(record: TenantMembershipRecord) -> TenantMembershipView:
    return TenantMembershipView(
        membership_id=record.membership_id,
        tenant_id=record.tenant_id,
        subject=record.subject,
        status=TenantMembershipStatus(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
        created_by_subject=record.created_by_subject,
    )


def create_tenant_with_creator_membership(
    session: Session,
    *,
    display_name: str,
    creator_subject: str,
    now: datetime | None = None,
) -> TenantView:
    creator = _stable_subject(creator_subject)
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
            subject=creator,
            status=TenantMembershipStatus.ACTIVE.value,
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
    subject: str,
    created_by_subject: str,
    now: datetime | None = None,
) -> TenantMembershipView:
    target_subject = _stable_subject(subject)
    creator = _stable_subject(created_by_subject)
    timestamp = _utc_now_iso(now)

    if tenant_repository.load_active_tenant(session, tenant_id) is None:
        raise ActiveTenantRequiredError("The tenant is not active.")

    existing = tenant_repository.load_tenant_membership(
        session,
        tenant_id=tenant_id,
        subject=target_subject,
    )
    if existing is not None:
        if existing.status == TenantMembershipStatus.DISABLED.value:
            existing.status = TenantMembershipStatus.ACTIVE.value
            existing.updated_at = timestamp
            try:
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise TenantPersistenceError(
                    "Tenant membership persistence failed."
                ) from exc
        return membership_view(existing)

    record = TenantMembershipRecord(
        membership_id=f"tenant-membership:{uuid4()}",
        tenant_id=tenant_id,
        subject=target_subject,
        status=TenantMembershipStatus.ACTIVE.value,
        created_at=timestamp,
        updated_at=timestamp,
        created_by_subject=creator,
    )
    try:
        tenant_repository.add_tenant_membership(session, record)
        session.commit()
        return membership_view(record)
    except IntegrityError as exc:
        session.rollback()
        concurrent = tenant_repository.load_tenant_membership(
            session,
            tenant_id=tenant_id,
            subject=target_subject,
        )
        if (
            concurrent is not None
            and concurrent.status == TenantMembershipStatus.ACTIVE.value
        ):
            return membership_view(concurrent)
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
        return membership_view(record)
    record.status = TenantMembershipStatus.DISABLED.value
    record.updated_at = _utc_now_iso(now)
    try:
        session.commit()
        return membership_view(record)
    except SQLAlchemyError as exc:
        session.rollback()
        raise TenantPersistenceError(
            "Tenant membership persistence failed."
        ) from exc
