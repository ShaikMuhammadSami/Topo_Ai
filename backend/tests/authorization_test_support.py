"""Real disposable authority construction for service-layer algorithm tests.

These helpers persist an ordinary human principal and Tenant Admin membership
in the test database, then use the production PH-3/PH-5 resolvers.  They are
not imported by product code and do not bypass authorization decisions.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import TenantMembershipRecord
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.repositories import tenant_repository
from app.security.authorization_enforcement import (
    AuthorizationContext,
    authorize_tenant,
    bind_authorization_context,
    reset_authorization_context,
)
from app.security.principals import AuthPrincipal
from app.security.tenant_context import resolve_tenant_context
from app.services.principal_identity import provision_external_human_principal


def tenant_admin_authorization(
    session: Session,
    tenant_id: str,
) -> AuthorizationContext:
    subject = f"authorization-test:{tenant_id}"
    principal_record = provision_external_human_principal(
        session,
        issuer=LEGACY_LOCAL_ISSUER,
        subject=subject,
        display_name="Authorization test administrator",
        authentication_type="api_token",
        roles=(),
    )
    membership = tenant_repository.load_tenant_membership(
        session,
        tenant_id=tenant_id,
        principal_id=principal_record.principal_id,
    )
    if membership is None:
        now = datetime.now(UTC).isoformat()
        membership = TenantMembershipRecord(
            membership_id=f"tenant-membership:{uuid4()}",
            tenant_id=tenant_id,
            principal_id=principal_record.principal_id,
            status="active",
            role="tenant_admin",
            created_at=now,
            updated_at=now,
            created_by_subject=subject,
        )
        tenant_repository.add_tenant_membership(session, membership)
        session.commit()
    principal = AuthPrincipal(
        principal_id=principal_record.principal_id,
        principal_type="human",
        subject=subject,
        display_name=principal_record.display_name,
        roles=(),
        authentication_type="api_token",
        external_issuer=LEGACY_LOCAL_ISSUER,
        external_subject=subject,
    )
    tenant_context = resolve_tenant_context(
        session,
        principal=principal,
        selected_tenant_id=tenant_id,
        credential_id=None,
    )
    return authorize_tenant(
        session,
        principal=principal,
        tenant_context=tenant_context,
        required_permissions=frozenset(),
    )


@contextmanager
def tenant_admin_authority(session: Session, tenant_id: str):
    token = bind_authorization_context(
        tenant_admin_authorization(session, tenant_id)
    )
    try:
        yield
    finally:
        reset_authorization_context(token)
