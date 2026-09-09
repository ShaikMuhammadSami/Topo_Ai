"""PH-5E adversarial proof for tenant-role isolation and revocation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import AuthPrincipalRecord, TenantMembershipRecord, TenantRecord
from app.models.principal_identity import new_principal_id
from app.security.authorization_enforcement import AuthorizationFailure, authorize_tenant
from app.security.authorization_policy import (
    INSTALLATION_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
    Permission,
    TenantRole,
)
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)


NOW = datetime(2026, 9, 9, 12, tzinfo=UTC).isoformat()


@pytest.fixture()
def role_factory():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _membership(session, principal_id: str, role: TenantRole):
    tenant = TenantRecord(
        tenant_id=f"tenant:{uuid4()}",
        display_name=role.value,
        status="active",
        created_at=NOW,
        updated_at=NOW,
        created_by_subject="ph5e",
    )
    membership = TenantMembershipRecord(
        membership_id=f"membership:{uuid4()}",
        tenant_id=tenant.tenant_id,
        principal_id=principal_id,
        role=role.value,
        status="active",
        created_at=NOW,
        updated_at=NOW,
        created_by_subject="ph5e",
    )
    session.add_all([tenant, membership])
    session.commit()
    return membership


def _context(principal: AuthPrincipal, membership: TenantMembershipRecord):
    return TenantContext(
        tenant_id=membership.tenant_id,
        principal_id=principal.principal_id,
        authenticated_subject=principal.subject,
        authentication_type=principal.authentication_type,
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id=membership.membership_id,
    )


def test_same_principal_keeps_viewer_a_and_admin_b_strictly_separate(
    role_factory,
) -> None:
    with role_factory() as session:
        record = AuthPrincipalRecord(
            principal_id=new_principal_id(),
            principal_type="human",
            display_name="PH-5E human",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(record)
        session.commit()
        principal = AuthPrincipal(
            principal_id=record.principal_id,
            principal_type="human",
            subject="ph5e:tenant-switch",
            display_name=record.display_name,
            roles=("admin", "operator", "superuser"),
            authentication_type="human_api_token",
        )
        viewer = _membership(session, record.principal_id, TenantRole.VIEWER)
        admin = _membership(session, record.principal_id, TenantRole.ADMIN)

        for _ in range(3):
            viewer_authority = authorize_tenant(
                session,
                principal=principal,
                tenant_context=_context(principal, viewer),
                required_permissions=frozenset({Permission.INCIDENT_READ}),
            )
            assert viewer_authority.effective_permissions == (
                TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
            )
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_tenant(
                    session,
                    principal=principal,
                    tenant_context=_context(principal, viewer),
                    required_permissions=frozenset({Permission.MEMBER_MANAGE}),
                )
            admin_authority = authorize_tenant(
                session,
                principal=principal,
                tenant_context=_context(principal, admin),
                required_permissions=frozenset({Permission.MEMBER_MANAGE}),
            )
            assert admin_authority.effective_permissions == (
                TENANT_ROLE_PERMISSIONS[TenantRole.ADMIN]
            )
            assert admin_authority.effective_permissions.isdisjoint(
                INSTALLATION_PERMISSIONS
            )


def test_membership_disable_and_role_demotion_apply_without_cross_tenant_cache(
    role_factory,
) -> None:
    with role_factory() as session:
        record = AuthPrincipalRecord(
            principal_id=new_principal_id(),
            principal_type="human",
            display_name="PH-5E demotion",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(record)
        session.commit()
        principal = AuthPrincipal(
            principal_id=record.principal_id,
            principal_type="human",
            subject="ph5e:demotion",
            display_name=record.display_name,
            roles=("admin",),
            authentication_type="human_api_token",
        )
        first = _membership(session, record.principal_id, TenantRole.ADMIN)
        other = _membership(session, record.principal_id, TenantRole.RESPONDER)
        first.role = TenantRole.VIEWER.value
        session.commit()

        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=_context(principal, first),
                required_permissions=frozenset({Permission.INCIDENT_RESPOND}),
            )
        authorize_tenant(
            session,
            principal=principal,
            tenant_context=_context(principal, first),
            required_permissions=frozenset({Permission.INCIDENT_READ}),
        )
        first.status = "disabled"
        session.commit()
        with pytest.raises(AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=_context(principal, first),
                required_permissions=frozenset(),
            )
        authorize_tenant(
            session,
            principal=principal,
            tenant_context=_context(principal, other),
            required_permissions=frozenset({Permission.INCIDENT_RESPOND}),
        )
