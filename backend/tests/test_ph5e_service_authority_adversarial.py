"""PH-5E adversarial proof for explicit service-principal authority."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import AuthApiCredentialRecord, ServicePrincipalPermissionRecord
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.security.authorization_policy import Permission
from app.services.auth_api_credential_service import (
    InactiveAuthApiCredentialError,
    authenticate_auth_api_credential,
    create_auth_api_credential,
    revoke_auth_api_credential,
)
from app.services.authority_assignments import (
    AuthorityAssignmentError,
    resolve_service_permissions,
    update_service_permissions,
)
from app.services.principal_identity import provision_external_human_principal
from app.services.tenant_service import create_tenant_with_creator_membership


NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


@pytest.fixture()
def service_factory():
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


def _service_credentials(session):
    admin = provision_external_human_principal(
        session,
        issuer=LEGACY_LOCAL_ISSUER,
        subject="ph5e:service-admin",
        display_name="PH-5E service admin",
        authentication_type="api_token",
        roles=(),
        now=NOW,
    )
    tenant = create_tenant_with_creator_membership(
        session,
        display_name="PH-5E service tenant",
        creator_subject=admin.subject,
        creator_principal_id=admin.principal_id,
    )
    first = create_auth_api_credential(
        session,
        request=ApiCredentialCreate(
            name="first",
            caller_type=ApiCredentialCallerType.SERVICE_API,
            subject="service:ph5e",
            tenant_id=tenant.tenant_id,
            permissions=["incident.read", "integration.manage"],
        ),
        created_by_subject=admin.subject,
        created_by_principal_id=admin.principal_id,
        now=NOW,
    )
    second = create_auth_api_credential(
        session,
        request=ApiCredentialCreate(
            name="second",
            caller_type=ApiCredentialCallerType.SERVICE_API,
            principal_id=first.principal_id,
            tenant_id=tenant.tenant_id,
        ),
        created_by_subject=admin.subject,
        created_by_principal_id=admin.principal_id,
        now=NOW,
    )
    return first, second


def test_multiple_credentials_share_one_service_authority_and_revoke_independently(
    service_factory,
) -> None:
    with service_factory() as session:
        first, second = _service_credentials(session)
        assert first.principal_id == second.principal_id
        assert resolve_service_permissions(
            session, principal_id=first.principal_id
        ) == {Permission.INCIDENT_READ, Permission.INTEGRATION_MANAGE}
        assert session.scalar(
            select(func.count()).select_from(ServicePrincipalPermissionRecord)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AuthApiCredentialRecord).where(
                AuthApiCredentialRecord.principal_id == first.principal_id
            )
        ) == 2

        revoke_auth_api_credential(
            session,
            record=session.get(AuthApiCredentialRecord, first.credential_id),
            revoked_by_subject="ph5e:service-admin",
            now=NOW,
        )
        with pytest.raises(InactiveAuthApiCredentialError):
            authenticate_auth_api_credential(
                session, raw_secret=first.api_credential, now=NOW
            )
        active = authenticate_auth_api_credential(
            session, raw_secret=second.api_credential, now=NOW
        )
        assert active is not None
        assert active.principal.principal_id == first.principal_id


@pytest.mark.parametrize(
    "stored",
    [
        "not-json",
        "{}",
        "[]",
        '["incident.read","incident.read"]',
        '["member.manage"]',
        '["credential.rotate"]',
        '["installation.recovery"]',
        '["unknown.permission"]',
        '["incident.read", "integration.manage"]',
        '["integration.manage","incident.read"]',
    ],
)
def test_tampered_service_permission_storage_fails_closed(
    service_factory, stored: str
) -> None:
    with service_factory() as session:
        first, _ = _service_credentials(session)
        assignment = session.get(ServicePrincipalPermissionRecord, first.principal_id)
        assert assignment is not None
        assignment.permissions_json = stored
        session.commit()
        with pytest.raises(
            AuthorityAssignmentError, match="^SERVICE_PERMISSIONS_INVALID$"
        ):
            resolve_service_permissions(session, principal_id=first.principal_id)


def test_service_permission_reduction_is_observed_by_next_resolution(
    service_factory,
) -> None:
    with service_factory() as session:
        first, _ = _service_credentials(session)
        assignment = session.get(ServicePrincipalPermissionRecord, first.principal_id)
        assert assignment is not None
        update_service_permissions(
            session,
            principal_id=first.principal_id,
            permissions=["incident.read"],
            expected_row_version=assignment.row_version,
            now=NOW,
        )
        assert resolve_service_permissions(
            session, principal_id=first.principal_id
        ) == {Permission.INCIDENT_READ}
