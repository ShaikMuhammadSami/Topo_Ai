"""PH-5E adversarial proof for issuer-aware durable principal identity."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    AuthPrincipalRecord,
    ExternalIdentityRecord,
    SecurityAuditEventRecord,
)
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.principal_identity import LEGACY_LOCAL_ISSUER, PrincipalStatus
from app.security.auth_config import AuthConfiguration, AuthMode, TokenIdentity
from app.security.authorization_enforcement import authorize_installation
from app.security.authorization_policy import Permission
from app.security.tenant_context import resolve_tenant_context
from app.services.auth_api_credential_service import (
    InactiveAuthApiCredentialError,
    authenticate_auth_api_credential,
    create_auth_api_credential,
)
from app.services.auth_session_service import create_auth_session, resolve_auth_session
from app.services.authority_assignments import (
    create_service_permission_assignment,
    grant_installation_operator,
    resolve_service_permissions,
    resolve_tenant_permissions,
)
from app.services.principal_identity import (
    PrincipalNotProvisionedError,
    PrincipalTypeMismatchError,
    create_service_principal,
    provision_external_human_principal,
)
from app.services.tenant_service import (
    add_or_reactivate_tenant_membership,
    create_tenant_with_creator_membership,
)


NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


@pytest.fixture()
def identity_factory():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _human(session, *, issuer: str, subject: str, display_name: str = "Shared"):
    return provision_external_human_principal(
        session,
        issuer=issuer,
        subject=subject,
        display_name=display_name,
        authentication_type="api_token",
        roles=("admin", "operator", "superuser"),
        now=NOW,
    )


def test_issuer_subject_case_and_display_collisions_never_merge_authority(
    identity_factory,
) -> None:
    with identity_factory() as session:
        issuer_a = _human(
            session,
            issuer="urn:topo:test:issuer:A",
            subject="same@example.test",
        )
        issuer_b = _human(
            session,
            issuer="urn:topo:test:issuer:B",
            subject="same@example.test",
        )
        issuer_case = _human(
            session,
            issuer="urn:topo:test:issuer:a",
            subject="same@example.test",
        )
        upper = _human(
            session,
            issuer="urn:topo:test:issuer:A",
            subject="User123",
        )
        lower = _human(
            session,
            issuer="urn:topo:test:issuer:A",
            subject="user123",
        )
        repeated = _human(
            session,
            issuer="urn:topo:test:issuer:A",
            subject="same@example.test",
            display_name="Changed display metadata",
        )
        service = create_service_principal(session, display_name="Shared")
        session.commit()

        assert len({
            issuer_a.principal_id,
            issuer_b.principal_id,
            issuer_case.principal_id,
            upper.principal_id,
            lower.principal_id,
            service.principal_id,
        }) == 6
        assert repeated.principal_id == issuer_a.principal_id
        assert session.scalar(
            select(func.count()).select_from(ExternalIdentityRecord)
        ) == 5
        assert session.scalar(
            select(func.count()).select_from(AuthPrincipalRecord)
        ) == 6

        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Issuer A only",
            creator_subject=issuer_a.subject,
            creator_principal_id=issuer_a.principal_id,
        )
        assert resolve_tenant_context(
            session,
            principal=issuer_a,
            selected_tenant_id=tenant.tenant_id,
            credential_id=None,
        ).principal_id == issuer_a.principal_id
        for impostor in (issuer_b, issuer_case, upper, lower):
            with pytest.raises(HTTPException) as denied:
                resolve_tenant_context(
                    session,
                    principal=impostor,
                    selected_tenant_id=tenant.tenant_id,
                    credential_id=None,
                )
            assert denied.value.status_code == 403


def test_human_service_and_machine_shaped_identifiers_cannot_cross_types(
    identity_factory,
) -> None:
    with identity_factory() as session:
        human = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="ph5e:human",
        )
        service = create_service_principal(session, display_name="Shared")
        session.commit()
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Type boundary",
            creator_subject=human.subject,
            creator_principal_id=human.principal_id,
        )

        with pytest.raises(PrincipalTypeMismatchError):
            add_or_reactivate_tenant_membership(
                session,
                tenant_id=tenant.tenant_id,
                principal_id=service.principal_id,
                subject=None,
                role="tenant_viewer",
                created_by_subject=human.subject,
                created_by_principal_id=human.principal_id,
            )
        with pytest.raises(PrincipalTypeMismatchError):
            create_service_permission_assignment(
                session,
                principal_id=human.principal_id,
                permissions=["incident.read"],
            )
        with pytest.raises(PrincipalTypeMismatchError):
            grant_installation_operator(session, principal_id=service.principal_id)
        with pytest.raises(PrincipalTypeMismatchError):
            resolve_tenant_permissions(
                session,
                principal_id=service.principal_id,
                tenant_id=tenant.tenant_id,
            )
        for machine_identifier in (
            "agent:fixture",
            "change-source:fixture",
            human.subject,
        ):
            with pytest.raises(PrincipalNotProvisionedError):
                resolve_service_permissions(session, principal_id=machine_identifier)


def test_principal_disablement_invalidates_every_owned_authority_next_request(
    identity_factory,
) -> None:
    digest = "d" * 64
    configuration = AuthConfiguration(
        mode=AuthMode.REQUIRED,
        token_registry=MappingProxyType({
            digest: TokenIdentity(
                subject="ph5e:disable-human",
                display_name="Disable target",
                roles=("admin",),
            )
        }),
        browser_allowed_origins=(),
        session_absolute_ttl_minutes=60,
        session_idle_ttl_minutes=30,
    )
    with identity_factory() as session:
        human = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="ph5e:disable-human",
            display_name="Disable target",
            authentication_type="api_token",
            roles=("admin",),
            now=NOW,
        )
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Disablement tenant",
            creator_subject=human.subject,
            creator_principal_id=human.principal_id,
        )
        tenant_context = resolve_tenant_context(
            session,
            principal=human,
            selected_tenant_id=tenant.tenant_id,
            credential_id=None,
        )
        browser = create_auth_session(
            session,
            configuration=configuration,
            source_principal=human,
            source_credential_digest=digest,
            now=NOW,
        )
        human_credential = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="Disable human",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                principal_id=human.principal_id,
            ),
            created_by_subject=human.subject,
            created_by_principal_id=human.principal_id,
            now=NOW,
        )
        service_credential = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="Disable service",
                caller_type=ApiCredentialCallerType.SERVICE_API,
                subject="service:disable-target",
                tenant_id=tenant.tenant_id,
                permissions=["incident.read"],
            ),
            created_by_subject=human.subject,
            created_by_principal_id=human.principal_id,
            now=NOW,
        )
        grant_installation_operator(session, principal_id=human.principal_id, now=NOW)
        audit_count = session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        )

        human_record = session.get(AuthPrincipalRecord, human.principal_id)
        assert human_record is not None
        human_record.status = PrincipalStatus.DISABLED.value
        session.commit()

        assert resolve_auth_session(
            session,
            configuration=configuration,
            raw_session_secret=browser.session_secret,
            now=NOW,
        ) is None
        with pytest.raises(InactiveAuthApiCredentialError):
            authenticate_auth_api_credential(
                session,
                raw_secret=human_credential.api_credential,
                now=NOW,
            )
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_tenant_permissions(
                session,
                principal_id=human.principal_id,
                tenant_id=tenant_context.tenant_id,
            )
        with pytest.raises(PrincipalNotProvisionedError):
            authorize_installation(
                session,
                principal=human,
                required_permissions=frozenset({
                    Permission.INSTALLATION_STATUS_READ
                }),
            )
        assert session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        ) == audit_count

        resolved_service = authenticate_auth_api_credential(
            session,
            raw_secret=service_credential.api_credential,
            now=NOW,
        )
        assert resolved_service is not None
        service_record = session.get(
            AuthPrincipalRecord, resolved_service.principal.principal_id
        )
        assert service_record is not None
        service_record.status = PrincipalStatus.DISABLED.value
        session.commit()
        with pytest.raises(InactiveAuthApiCredentialError):
            authenticate_auth_api_credential(
                session,
                raw_secret=service_credential.api_credential,
                now=NOW,
            )
