from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    AuthApiCredentialRecord,
    AuthPrincipalRecord,
    ExternalIdentityRecord,
    TenantMembershipRecord,
)
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.principal_identity import (
    LEGACY_LOCAL_ISSUER,
    PrincipalStatus,
    PrincipalType,
    new_external_identity_id,
)
from app.security.auth_config import AuthConfiguration, AuthMode, TokenIdentity
from app.security.principals import AuthPrincipal
from app.security.tenant_context import resolve_tenant_context
from app.services.auth_api_credential_service import (
    InactiveAuthApiCredentialError,
    ServiceTenantAccessError,
    authenticate_auth_api_credential,
    create_auth_api_credential,
)
from app.services.auth_session_service import (
    create_auth_session,
    resolve_auth_session,
)
from app.services.principal_identity import (
    PrincipalNotProvisionedError,
    PrincipalTypeMismatchError,
    auth_principal_for_external_identity,
    create_service_principal,
    provision_external_human_principal,
)
from app.services.tenant_service import (
    add_or_reactivate_tenant_membership,
    create_tenant_with_creator_membership,
    disable_tenant_membership,
)


@pytest.fixture()
def identity_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _human(
    session: Session,
    *,
    issuer: str,
    subject: str,
    display_name: str = "Shared display",
    authentication_type: str = "api_token",
    roles: tuple[str, ...] = ("admin",),
) -> AuthPrincipal:
    return provision_external_human_principal(
        session,
        issuer=issuer,
        subject=subject,
        display_name=display_name,
        authentication_type=authentication_type,
        roles=roles,
        now=datetime(2026, 9, 5, tzinfo=UTC),
    )


def test_issuer_subject_is_exact_case_sensitive_authority(identity_factory) -> None:
    with identity_factory() as session:
        a = _human(session, issuer="urn:test:issuer:a", subject="123")
        b = _human(session, issuer="urn:test:issuer:b", subject="123")
        upper = _human(session, issuer="urn:test:issuer:a", subject="User123")
        lower = _human(session, issuer="urn:test:issuer:a", subject="user123")
        email_a = _human(
            session,
            issuer="urn:test:issuer:a",
            subject="alice@example.com",
        )
        email_b = _human(
            session,
            issuer="urn:test:issuer:b",
            subject="alice@example.com",
        )
        repeated = _human(session, issuer="urn:test:issuer:a", subject="123")

        assert a.principal_id != b.principal_id
        assert upper.principal_id != lower.principal_id
        assert email_a.principal_id != email_b.principal_id
        assert repeated.principal_id == a.principal_id
        assert session.scalar(select(func.count()).select_from(ExternalIdentityRecord)) == 6
        assert session.scalar(select(func.count()).select_from(AuthPrincipalRecord)) == 6


def test_unknown_identity_reassignment_and_type_swap_fail_closed(identity_factory) -> None:
    with identity_factory() as session:
        human = _human(session, issuer="urn:test:issuer:a", subject="123")
        with pytest.raises(PrincipalNotProvisionedError, match="PRINCIPAL_NOT_PROVISIONED"):
            auth_principal_for_external_identity(
                session,
                issuer="urn:test:issuer:unknown",
                subject="123",
                authentication_type="api_token",
            )

        service = create_service_principal(session, display_name="Automation")
        session.commit()
        session.add(
            ExternalIdentityRecord(
                external_identity_id=new_external_identity_id(),
                principal_id=service.principal_id,
                issuer="urn:test:issuer:service-swap",
                subject="123",
                status="active",
                created_at="2026-09-05T00:00:00+00:00",
                updated_at="2026-09-05T00:00:00+00:00",
            )
        )
        session.commit()
        with pytest.raises(PrincipalTypeMismatchError, match="PRINCIPAL_TYPE_MISMATCH"):
            auth_principal_for_external_identity(
                session,
                issuer="urn:test:issuer:service-swap",
                subject="123",
                authentication_type="api_token",
            )

        replacement = create_service_principal(session, display_name="Replacement")
        session.commit()
        session.add(
            ExternalIdentityRecord(
                external_identity_id=new_external_identity_id(),
                principal_id=replacement.principal_id,
                issuer="urn:test:issuer:a",
                subject="123",
                status="active",
                created_at="2026-09-05T00:00:00+00:00",
                updated_at="2026-09-05T00:00:00+00:00",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert auth_principal_for_external_identity(
            session,
            issuer="urn:test:issuer:a",
            subject="123",
            authentication_type="api_token",
        ).principal_id == human.principal_id


def test_cross_issuer_subject_cannot_inherit_membership(identity_factory) -> None:
    with identity_factory() as session:
        a = _human(session, issuer="urn:test:issuer:a", subject="same")
        b = _human(session, issuer="urn:test:issuer:b", subject="same")
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Tenant A",
            creator_subject=a.subject,
            creator_principal_id=a.principal_id,
        )
        resolved = resolve_tenant_context(
            session,
            principal=a,
            selected_tenant_id=tenant.tenant_id,
            credential_id=None,
        )
        assert resolved.principal_id == a.principal_id
        with pytest.raises(HTTPException) as denied:
            resolve_tenant_context(
                session,
                principal=b,
                selected_tenant_id=tenant.tenant_id,
                credential_id=None,
            )
        assert denied.value.status_code == 403


def test_membership_disable_is_immediate_for_existing_identity(identity_factory) -> None:
    with identity_factory() as session:
        human = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:member",
        )
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Tenant",
            creator_subject=human.subject,
            creator_principal_id=human.principal_id,
        )
        disable_tenant_membership(
            session,
            tenant_id=tenant.tenant_id,
            membership_id=tenant.membership_id,
        )
        with pytest.raises(HTTPException) as denied:
            resolve_tenant_context(
                session,
                principal=human,
                selected_tenant_id=tenant.tenant_id,
                credential_id=None,
            )
        assert denied.value.status_code == 403


def test_service_principal_supports_rotation_without_human_membership(identity_factory) -> None:
    with identity_factory() as session:
        admin = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:admin",
        )
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Service tenant",
            creator_subject=admin.subject,
            creator_principal_id=admin.principal_id,
        )
        first = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="service primary",
                permissions=["incident.read"],
                caller_type=ApiCredentialCallerType.SERVICE_API,
                subject="service:automation",
                display_name="Automation",
                roles=[],
                tenant_id=tenant.tenant_id,
            ),
            created_by_subject=admin.subject,
            created_by_principal_id=admin.principal_id,
        )
        second = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="service rotated",
                caller_type=ApiCredentialCallerType.SERVICE_API,
                principal_id=first.principal_id,
                subject="service:automation",
                roles=[],
                tenant_id=tenant.tenant_id,
            ),
            created_by_subject=admin.subject,
            created_by_principal_id=admin.principal_id,
        )

        assert first.principal_id == second.principal_id
        assert session.scalar(
            select(func.count()).select_from(AuthApiCredentialRecord).where(
                AuthApiCredentialRecord.principal_id == first.principal_id
            )
        ) == 2
        assert session.scalar(
            select(func.count()).select_from(TenantMembershipRecord).where(
                TenantMembershipRecord.principal_id == first.principal_id
            )
        ) == 0


def test_service_principal_cannot_acquire_a_second_tenant(identity_factory) -> None:
    with identity_factory() as session:
        admin = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:admin",
        )
        tenant_a = create_tenant_with_creator_membership(
            session,
            display_name="Service tenant A",
            creator_subject=admin.subject,
            creator_principal_id=admin.principal_id,
        )
        tenant_b = create_tenant_with_creator_membership(
            session,
            display_name="Service tenant B",
            creator_subject=admin.subject,
            creator_principal_id=admin.principal_id,
        )
        first = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="service primary",
                permissions=["incident.read"],
                caller_type=ApiCredentialCallerType.SERVICE_API,
                subject="service:automation",
                roles=[],
                tenant_id=tenant_a.tenant_id,
            ),
            created_by_subject=admin.subject,
            created_by_principal_id=admin.principal_id,
        )

        with pytest.raises(ServiceTenantAccessError):
            create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name="cross-tenant credential",
                    caller_type=ApiCredentialCallerType.SERVICE_API,
                    principal_id=first.principal_id,
                    roles=[],
                    tenant_id=tenant_b.tenant_id,
                ),
                created_by_subject=admin.subject,
                created_by_principal_id=admin.principal_id,
            )

        assert session.scalar(
            select(func.count()).select_from(AuthApiCredentialRecord).where(
                AuthApiCredentialRecord.principal_id == first.principal_id
            )
        ) == 1


def test_human_api_credential_is_bound_to_principal_not_subject(identity_factory) -> None:
    with identity_factory() as session:
        admin = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:admin",
        )
        a = _human(session, issuer="urn:test:issuer:a", subject="same")
        _human(session, issuer="urn:test:issuer:b", subject="same")
        created = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="human A",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                principal_id=a.principal_id,
                roles=["admin"],
            ),
            created_by_subject=admin.subject,
            created_by_principal_id=admin.principal_id,
        )
        resolved = authenticate_auth_api_credential(
            session,
            raw_secret=created.api_credential,
        )
        assert resolved is not None
        assert resolved.principal.principal_id == a.principal_id


def test_principal_disablement_invalidates_session_and_credentials(identity_factory) -> None:
    token_digest = "a" * 64
    configuration = AuthConfiguration(
        mode=AuthMode.REQUIRED,
        token_registry=MappingProxyType(
            {
                token_digest: TokenIdentity(
                    subject="test:human",
                    display_name="Human",
                    roles=("admin",),
                )
            }
        ),
        browser_allowed_origins=(),
        session_absolute_ttl_minutes=60,
        session_idle_ttl_minutes=30,
    )
    with identity_factory() as session:
        human = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:human",
            display_name="Human",
        )
        issued_session = create_auth_session(
            session,
            configuration=configuration,
            source_principal=human,
            source_credential_digest=token_digest,
        )
        credential = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="human API",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                principal_id=human.principal_id,
                subject=human.subject,
                roles=["admin"],
            ),
            created_by_subject=human.subject,
            created_by_principal_id=human.principal_id,
        )
        principal = session.get(AuthPrincipalRecord, human.principal_id)
        assert principal is not None
        principal.status = PrincipalStatus.DISABLED.value
        session.commit()

        assert resolve_auth_session(
            session,
            configuration=configuration,
            raw_session_secret=issued_session.session_secret,
        ) is None
        with pytest.raises(InactiveAuthApiCredentialError):
            authenticate_auth_api_credential(
                session,
                raw_secret=credential.api_credential,
            )


def test_human_and_service_principal_types_cannot_substitute(identity_factory) -> None:
    with identity_factory() as session:
        admin = _human(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:admin",
        )
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="Tenant",
            creator_subject=admin.subject,
            creator_principal_id=admin.principal_id,
        )
        service = create_service_principal(session, display_name="Service")
        session.commit()
        with pytest.raises(PrincipalTypeMismatchError):
            add_or_reactivate_tenant_membership(
                session,
                tenant_id=tenant.tenant_id,
                principal_id=service.principal_id,
                subject=None,
                role="tenant_viewer",
                created_by_subject=admin.subject,
                created_by_principal_id=admin.principal_id,
            )
        with pytest.raises(PrincipalTypeMismatchError):
            create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name="wrong type",
                    caller_type=ApiCredentialCallerType.SERVICE_API,
                    principal_id=admin.principal_id,
                    roles=[],
                    tenant_id=tenant.tenant_id,
                ),
                created_by_subject=admin.subject,
                created_by_principal_id=admin.principal_id,
            )
