"""PH-5E adversarial proof for orthogonal installation authority."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import TenantMembershipRecord
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.security.authorization_enforcement import (
    AuthorityKind,
    AuthorizationFailure,
    authorize_installation,
    authorize_tenant,
)
from app.security.authorization_policy import (
    INSTALLATION_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
    Permission,
    TenantRole,
)
from app.security.principals import AuthPrincipal
from app.security.tenant_context import resolve_tenant_context
from app.services.authority_assignments import grant_installation_operator
from app.services.principal_identity import provision_external_human_principal
from app.services.tenant_service import create_tenant_with_creator_membership


NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


@pytest.fixture()
def installation_factory():
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


def _principal(record, *, roles=("admin", "operator", "superuser")):
    return AuthPrincipal(
        principal_id=record.principal_id,
        principal_type="human",
        subject=record.subject,
        display_name=record.display_name,
        roles=roles,
        authentication_type="human_api_token",
    )


def test_tenant_admin_has_no_implicit_installation_authority(
    installation_factory,
) -> None:
    with installation_factory() as session:
        record = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="ph5e:tenant-admin-only",
            display_name="Tenant admin only",
            authentication_type="human_api_token",
            roles=("admin", "operator"),
            now=NOW,
        )
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Admin tenant",
            creator_subject=record.subject,
            creator_principal_id=record.principal_id,
        )
        principal = _principal(record)
        context = resolve_tenant_context(
            session,
            principal=principal,
            selected_tenant_id=tenant.tenant_id,
            credential_id=None,
        )
        tenant_authority = authorize_tenant(
            session,
            principal=principal,
            tenant_context=context,
            required_permissions=frozenset({Permission.TENANT_SETTINGS_MANAGE}),
        )
        assert tenant_authority.authority_kind is AuthorityKind.HUMAN_TENANT
        assert tenant_authority.effective_permissions == (
            TENANT_ROLE_PERMISSIONS[TenantRole.ADMIN]
        )
        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_installation(
                session,
                principal=principal,
                required_permissions=frozenset(
                    {Permission.INSTALLATION_SECRET_MANAGE}
                ),
            )


def test_dual_operator_and_viewer_authority_never_unions_permissions(
    installation_factory,
) -> None:
    with installation_factory() as session:
        record = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="ph5e:dual",
            display_name="Dual authority",
            authentication_type="human_api_token",
            roles=("admin",),
            now=NOW,
        )
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Viewer tenant",
            creator_subject=record.subject,
            creator_principal_id=record.principal_id,
        )
        membership = session.get(TenantMembershipRecord, tenant.membership_id)
        assert membership is not None
        membership.role = TenantRole.VIEWER.value
        session.commit()
        grant_installation_operator(session, principal_id=record.principal_id, now=NOW)
        principal = _principal(record)
        tenant_context = resolve_tenant_context(
            session,
            principal=principal,
            selected_tenant_id=tenant.tenant_id,
            credential_id=None,
        )
        tenant_authority = authorize_tenant(
            session,
            principal=principal,
            tenant_context=tenant_context,
            required_permissions=frozenset({Permission.INCIDENT_READ}),
        )
        installation_authority = authorize_installation(
            session,
            principal=principal,
            required_permissions=frozenset({Permission.INSTALLATION_RECOVERY}),
        )
        assert tenant_authority.authority_kind is AuthorityKind.HUMAN_TENANT
        assert tenant_authority.effective_permissions == (
            TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
        )
        assert installation_authority.authority_kind is AuthorityKind.INSTALLATION
        assert installation_authority.tenant_id is None
        assert installation_authority.effective_permissions == INSTALLATION_PERMISSIONS
        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=tenant_context,
                required_permissions=frozenset({Permission.MEMBER_MANAGE}),
            )
