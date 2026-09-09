"""Real PostgreSQL 16 PH-5E next-transaction and concurrency proof."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AuthApiCredentialRecord,
    AuthPrincipalRecord,
    ExternalIdentityRecord,
    SecurityAuditEventRecord,
    TenantMembershipRecord,
)
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.models.security_audit import SecurityAuditAction, SecurityAuditResourceType
from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_installation,
    authorize_tenant,
)
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)
from app.services.auth_api_credential_service import (
    InactiveAuthApiCredentialError,
    authenticate_auth_api_credential,
    create_auth_api_credential,
    revoke_auth_api_credential,
)
from app.services.authority_assignments import (
    disable_installation_operator,
    grant_installation_operator,
    update_service_permissions,
)
from app.services.principal_identity import provision_external_human_principal
from app.services.security_audit import append_local_operator_security_event
from app.services.tenant_service import create_tenant_with_creator_membership
from test_postgres_runtime_compatibility import _temporary_database, _upgrade


pytestmark = pytest.mark.skipif(
    not os.getenv("TOPO_TEST_POSTGRES_URL"),
    reason="set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 PH-5E proof",
)
NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


def _human(record) -> AuthPrincipal:
    return AuthPrincipal(
        principal_id=record.principal_id,
        principal_type="human",
        subject=record.subject,
        display_name=record.display_name,
        roles=("admin", "operator", "superuser"),
        authentication_type="human_api_token",
    )


def _human_context(principal: AuthPrincipal, tenant) -> TenantContext:
    return TenantContext(
        tenant_id=tenant.tenant_id,
        principal_id=principal.principal_id,
        authenticated_subject=principal.subject,
        authentication_type=principal.authentication_type,
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id=tenant.membership_id,
    )


def test_next_transaction_observes_every_authority_reduction() -> None:
    with _temporary_database("ph5e_authority_reduction") as engine:
        _upgrade(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory() as setup:
            human_record = provision_external_human_principal(
                setup,
                issuer=LEGACY_LOCAL_ISSUER,
                subject="ph5e:postgres-human",
                display_name="PH-5E PostgreSQL human",
                authentication_type="human_api_token",
                roles=(),
                now=NOW,
            )
            tenant_a = create_tenant_with_creator_membership(
                setup,
                display_name="PH-5E A",
                creator_subject=human_record.subject,
                creator_principal_id=human_record.principal_id,
            )
            tenant_b = create_tenant_with_creator_membership(
                setup,
                display_name="PH-5E B",
                creator_subject=human_record.subject,
                creator_principal_id=human_record.principal_id,
            )
            b_membership = setup.get(TenantMembershipRecord, tenant_b.membership_id)
            assert b_membership is not None
            b_membership.role = "tenant_viewer"
            setup.commit()
            grant_installation_operator(
                setup, principal_id=human_record.principal_id, now=NOW
            )
            human_credential = create_auth_api_credential(
                setup,
                request=ApiCredentialCreate(
                    name="PH-5E human",
                    caller_type=ApiCredentialCallerType.HUMAN_API,
                    principal_id=human_record.principal_id,
                ),
                created_by_subject=human_record.subject,
                created_by_principal_id=human_record.principal_id,
                now=NOW,
            )
            service_credential = create_auth_api_credential(
                setup,
                request=ApiCredentialCreate(
                    name="PH-5E service",
                    caller_type=ApiCredentialCallerType.SERVICE_API,
                    subject="service:ph5e-postgres",
                    tenant_id=tenant_a.tenant_id,
                    permissions=["incident.read", "integration.manage"],
                ),
                created_by_subject=human_record.subject,
                created_by_principal_id=human_record.principal_id,
                now=NOW,
            )

        human = _human(human_record)
        human_a = _human_context(human, tenant_a)
        human_b = _human_context(human, tenant_b)
        service = AuthPrincipal(
            principal_id=service_credential.principal_id,
            principal_type="service",
            subject="service:ph5e-postgres",
            display_name="PH-5E service",
            roles=("admin",),
            authentication_type="service_api_token",
        )
        service_context = TenantContext(
            tenant_id=tenant_a.tenant_id,
            principal_id=service.principal_id,
            authenticated_subject=service.subject,
            authentication_type=service.authentication_type,
            actor_kind=TenantActorKind.SERVICE,
            selection_source=TenantSelectionSource.SERVICE_BINDING,
            credential_id=service_credential.credential_id,
        )
        with factory() as before:
            authorize_tenant(
                before,
                principal=human,
                tenant_context=human_a,
                required_permissions=frozenset({Permission.MEMBER_MANAGE}),
            )
            authorize_installation(
                before,
                principal=human,
                required_permissions=frozenset({Permission.INSTALLATION_RECOVERY}),
            )
            authorize_tenant(
                before,
                principal=service,
                tenant_context=service_context,
                required_permissions=frozenset({Permission.INTEGRATION_MANAGE}),
            )

        with factory() as writer:
            membership_a = writer.get(
                TenantMembershipRecord, tenant_a.membership_id
            )
            membership_b = writer.get(
                TenantMembershipRecord, tenant_b.membership_id
            )
            assert membership_a is not None and membership_b is not None
            membership_a.role = "tenant_viewer"
            membership_b.status = "disabled"
            writer.commit()
            disable_installation_operator(
                writer, principal_id=human.principal_id or "", now=NOW
            )
            update_service_permissions(
                writer,
                principal_id=service.principal_id or "",
                permissions=["incident.read"],
                expected_row_version=1,
                now=NOW,
            )
            human_row = writer.get(
                AuthApiCredentialRecord, human_credential.credential_id
            )
            assert human_row is not None
            revoke_auth_api_credential(
                writer,
                record=human_row,
                revoked_by_subject=human.subject,
                now=NOW,
            )

        with factory() as next_request:
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_tenant(
                    next_request,
                    principal=human,
                    tenant_context=human_a,
                    required_permissions=frozenset({Permission.MEMBER_MANAGE}),
                )
            authorize_tenant(
                next_request,
                principal=human,
                tenant_context=human_a,
                required_permissions=frozenset({Permission.INCIDENT_READ}),
            )
            with pytest.raises(
                AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"
            ):
                authorize_tenant(
                    next_request,
                    principal=human,
                    tenant_context=human_b,
                    required_permissions=frozenset(),
                )
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_installation(
                    next_request,
                    principal=human,
                    required_permissions=frozenset(
                        {Permission.INSTALLATION_RECOVERY}
                    ),
                )
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_tenant(
                    next_request,
                    principal=service,
                    tenant_context=service_context,
                    required_permissions=frozenset(
                        {Permission.INTEGRATION_MANAGE}
                    ),
                )
            authorize_tenant(
                next_request,
                principal=service,
                tenant_context=service_context,
                required_permissions=frozenset({Permission.INCIDENT_READ}),
            )
            with pytest.raises(InactiveAuthApiCredentialError):
                authenticate_auth_api_credential(
                    next_request,
                    raw_secret=human_credential.api_credential,
                    now=NOW,
                )


def test_concurrent_identity_and_audit_appends_are_unique_and_complete() -> None:
    with _temporary_database("ph5e_identity_audit_concurrency") as engine:
        _upgrade(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        barrier = Barrier(2)

        def provision(number: int) -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                principal = provision_external_human_principal(
                    session,
                    issuer="urn:topo:ph5e:concurrent",
                    subject="same-subject",
                    display_name="Concurrent",
                    authentication_type="human_api_token",
                )
            with factory() as session, session.begin():
                append_local_operator_security_event(
                    session,
                    action=SecurityAuditAction.INSTALLATION_SECRET_INSPECTED,
                    permissions=[Permission.INSTALLATION_STATUS_READ],
                    resource_type=SecurityAuditResourceType.SECRET_RECORD,
                    resource_id=f"ph5e-concurrent-{number}",
                )
            return principal.principal_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            principal_ids = list(pool.map(provision, (1, 2)))
        assert len(set(principal_ids)) == 1
        with Session(engine) as session:
            assert session.scalar(
                select(func.count()).select_from(ExternalIdentityRecord)
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(AuthPrincipalRecord)
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(SecurityAuditEventRecord)
            ) == 2
