"""Focused SQLite proof for the PH-5D security/admin audit boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_session
from app.db.models import (
    AuthPrincipalRecord,
    SecurityAuditEventRecord,
    TenantMembershipRecord,
    TenantRecord,
)
from app.main import create_app
from app.models.change_sources import ChangeSourceCreate, ChangeSourceType
from app.models.agents import AgentEnrollmentTokenCreateRequest
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.identity import IdentityOverrideAction, IdentityOverrideCreate
from app.models.ownership import OwnershipMappingCreate
from app.models.principal_identity import LEGACY_LOCAL_ISSUER, new_principal_id
from app.models.security_audit import (
    SecurityAuditAction,
    SecurityAuditActorKind,
    SecurityAuditReason,
    SecurityAuditResourceType,
    SecurityAuditResult,
)
from app.repositories.agent_repository import create_enrollment_token
from app.repositories.identity_repository import upsert_identity_override
from app.security.api_tokens import token_digest
from app.security.auth_config import (
    AuthConfiguration,
    AuthMode,
    TokenIdentity,
)
from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_agent_enrollment_fixed_purpose,
    authorize_authentication_self_service,
    authorize_service_operation,
    authorize_tenant,
    bind_authorization_context,
    reset_authorization_context,
)
from app.security.authorization_plan import CRITICAL_OPERATION_PLAN
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal
from app.security.security_audit_inventory import (
    AUDIT_OPERATION_INVENTORY,
    SecurityAuditInventoryClass,
)
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)
from app.services import secret_consumers, tenant_service
from app.services.auth_api_credential_service import (
    create_auth_api_credential,
    revoke_auth_api_credential,
)
from app.services.authority_assignments import grant_installation_operator
from app.services.ownership_resolver import create_ownership_mapping
from app.services.principal_identity import provision_external_human_principal
from app.services.secret_consumers import SecretConsumerError
from app.services.security_audit import (
    SecurityAuditValidationError,
    append_allowed_security_event,
    append_authorization_denial,
    append_local_operator_security_event,
    bind_security_audit_request,
    canonical_permissions,
    reset_security_audit_request,
)


NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
TENANT_ID = "tenant:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture()
def audit_factory():
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


def _seed_human(
    session: Session,
    *,
    role: str = "tenant_admin",
    subject: str = "audit:human",
) -> tuple[AuthPrincipalRecord, AuthPrincipal, TenantContext]:
    caller = provision_external_human_principal(
        session,
        issuer=LEGACY_LOCAL_ISSUER,
        subject=subject,
        display_name="Audit human",
        authentication_type="human_api_token",
        roles=("admin", "operator"),
        now=NOW,
    )
    principal = session.get(AuthPrincipalRecord, caller.principal_id)
    assert principal is not None
    if session.get(TenantRecord, TENANT_ID) is None:
        session.add(
            TenantRecord(
                tenant_id=TENANT_ID,
                display_name="Audit tenant",
                status="active",
                created_at=NOW.isoformat(),
                updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            )
        )
    membership = TenantMembershipRecord(
        membership_id=f"tenant-membership:{uuid4()}",
        tenant_id=TENANT_ID,
        principal_id=principal.principal_id,
        role=role,
        status="active",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by_subject="fixture",
    )
    session.add_all([principal, membership])
    session.commit()
    tenant_context = TenantContext(
        tenant_id=TENANT_ID,
        principal_id=principal.principal_id,
        authenticated_subject=subject,
        authentication_type="human_api_token",
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id=membership.membership_id,
    )
    return principal, caller, tenant_context


def _authorized_context(session: Session, *, role: str = "tenant_admin"):
    _, principal, tenant_context = _seed_human(session, role=role)
    return authorize_tenant(
        session,
        principal=principal,
        tenant_context=tenant_context,
        required_permissions=frozenset(),
    )


def test_security_audit_schema_is_exact_and_has_no_authority_foreign_keys() -> None:
    assert len(Base.metadata.tables) == 50
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
    table = Base.metadata.tables["security_audit_events"]
    assert list(table.columns) == [
        table.c.audit_event_id,
        table.c.occurred_at,
        table.c.actor_principal_id,
        table.c.actor_kind,
        table.c.actor_reference,
        table.c.authentication_type,
        table.c.authority_kind,
        table.c.tenant_id,
        table.c.action,
        table.c.permissions_json,
        table.c.resource_type,
        table.c.resource_id,
        table.c.result,
        table.c.reason_code,
        table.c.request_id,
    ]
    assert not table.foreign_keys
    assert {index.name for index in table.indexes} == {
        "ix_security_audit_tenant_occurred",
        "ix_security_audit_actor_occurred",
        "ix_security_audit_action_occurred",
        "ix_security_audit_request_id",
    }


def test_operation_inventory_is_closed_over_all_98_frozen_operations() -> None:
    assert set(AUDIT_OPERATION_INVENTORY) == set(CRITICAL_OPERATION_PLAN)
    counts = {
        category: tuple(AUDIT_OPERATION_INVENTORY.values()).count(category)
        for category in SecurityAuditInventoryClass
    }
    assert counts == {
        SecurityAuditInventoryClass.AUDIT_ALLOWED_PRIVILEGED_MUTATION: 22,
        SecurityAuditInventoryClass.AUDIT_ALLOWED_SECURITY_READ: 4,
        SecurityAuditInventoryClass.AUDIT_AUTHORIZATION_DENIAL: 11,
        SecurityAuditInventoryClass.OUT_OF_SCOPE_MINIMUM_AUDIT: 60,
        SecurityAuditInventoryClass.NONATOMIC_OPERATOR_ACTION: 1,
    }


def test_audit_vocabulary_and_permission_json_are_closed_and_canonical() -> None:
    assert {item.value for item in SecurityAuditResult} == {"allowed", "denied"}
    assert {item.value for item in SecurityAuditActorKind} == {
        "human",
        "service",
        "agent",
        "provider",
        "local_operator",
    }
    assert canonical_permissions(
        [Permission.INTEGRATION_MANAGE, Permission.CREDENTIAL_ROTATE,
         Permission.INTEGRATION_MANAGE]
    ) == '["credential.rotate","integration.manage"]'
    with pytest.raises(SecurityAuditValidationError, match="AUDIT_PERMISSIONS_INVALID"):
        canonical_permissions(["future.permission"])


def test_human_and_local_actor_events_contain_no_subject_role_or_display_name(
    audit_factory,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session)
        request_token = bind_security_audit_request(audit_factory)
        token = bind_authorization_context(context)
        try:
            append_allowed_security_event(
                session,
                action=SecurityAuditAction.OWNERSHIP_MAPPING_UPSERTED,
                permissions=[Permission.OWNERSHIP_MANAGE],
                resource_type=SecurityAuditResourceType.OWNERSHIP_MAPPING,
                resource_id="ownership:fixture",
                tenant_id=TENANT_ID,
            )
        finally:
            reset_authorization_context(token)
            reset_security_audit_request(request_token)
        append_local_operator_security_event(
            session,
            action=SecurityAuditAction.INSTALLATION_OPERATOR_INSPECTED,
            permissions=[Permission.INSTALLATION_STATUS_READ],
            resource_type=SecurityAuditResourceType.INSTALLATION_OPERATOR_ASSIGNMENT,
            resource_id=context.actor_principal_id,
        )
        session.commit()
        events = list(session.scalars(select(SecurityAuditEventRecord).order_by(
            SecurityAuditEventRecord.occurred_at,
            SecurityAuditEventRecord.audit_event_id,
        )))
    assert len(events) == 2
    human = next(event for event in events if event.actor_kind == "human")
    local = next(event for event in events if event.actor_kind == "local_operator")
    assert human.actor_principal_id == context.actor_principal_id
    assert human.actor_reference is None and human.tenant_id == TENANT_ID
    assert local.actor_principal_id is None and local.actor_reference is None
    serialized = "\n".join(str(value) for event in events for value in vars(event).values())
    assert "Audit human" not in serialized
    assert "audit:human" not in serialized
    assert "tenant_admin" not in serialized


def test_control_characters_are_rejected_not_truncated(audit_factory) -> None:
    with audit_factory() as session:
        with pytest.raises(SecurityAuditValidationError, match="AUDIT_RESOURCE_ID_INVALID"):
            append_local_operator_security_event(
                session,
                action=SecurityAuditAction.INSTALLATION_SECRET_INSPECTED,
                permissions=[Permission.INSTALLATION_STATUS_READ],
                resource_type=SecurityAuditResourceType.SECRET_RECORD,
                resource_id="openai\nsecret",
            )
        assert session.scalar(select(SecurityAuditEventRecord)) is None


def test_membership_audit_failure_rolls_back_business_mutation(
    audit_factory, monkeypatch,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session)
        target = AuthPrincipalRecord(
            principal_id=new_principal_id(),
            principal_type="human",
            display_name="Target",
            status="active",
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        session.add(target)
        session.commit()
        request_token = bind_security_audit_request(audit_factory)
        token = bind_authorization_context(context)
        monkeypatch.setattr(
            tenant_service,
            "append_allowed_security_event",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SQLAlchemyError("synthetic audit failure")
            ),
        )
        try:
            with pytest.raises(tenant_service.TenantPersistenceError):
                tenant_service.add_or_reactivate_tenant_membership(
                    session,
                    tenant_id=TENANT_ID,
                    subject=None,
                    role="tenant_viewer",
                    principal_id=target.principal_id,
                    created_by_subject="audit:human",
                    created_by_principal_id=context.actor_principal_id,
                )
        finally:
            reset_authorization_context(token)
            reset_security_audit_request(request_token)
        assert session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.principal_id == target.principal_id
            )
        ) is None
        assert session.scalar(select(SecurityAuditEventRecord)) is None


def test_integration_audit_failure_rolls_back_business_mutation(
    audit_factory, monkeypatch,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session)
        request_token = bind_security_audit_request(audit_factory)
        token = bind_authorization_context(context)
        monkeypatch.setattr(
            secret_consumers,
            "append_allowed_security_event",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SQLAlchemyError("synthetic audit failure")
            ),
        )
        try:
            with pytest.raises(SQLAlchemyError):
                secret_consumers.create_change_source_secure(
                    session,
                    request=ChangeSourceCreate(
                        name="disabled fixture",
                        source_type=ChangeSourceType.GITHUB,
                        enabled=False,
                    ),
                    tenant_id=TENANT_ID,
                    actor="ignored-by-audit",
                    store=object(),
                )
        finally:
            reset_authorization_context(token)
            reset_security_audit_request(request_token)
        from app.db.models import ChangeSourceRecord

        assert session.scalar(select(ChangeSourceRecord)) is None
        assert session.scalar(select(SecurityAuditEventRecord)) is None


def test_business_failure_does_not_create_false_allowed_event(audit_factory) -> None:
    with audit_factory() as session:
        context = _authorized_context(session)
        request_token = bind_security_audit_request(audit_factory)
        token = bind_authorization_context(context)
        try:
            with pytest.raises(SecretConsumerError):
                secret_consumers.create_change_source_secure(
                    session,
                    request=ChangeSourceCreate(
                        name="missing credential",
                        source_type=ChangeSourceType.GITHUB,
                        enabled=True,
                    ),
                    tenant_id=TENANT_ID,
                    actor="ignored-by-audit",
                    store=object(),
                )
        finally:
            reset_authorization_context(token)
            reset_security_audit_request(request_token)
        assert session.scalar(select(SecurityAuditEventRecord)) is None


def test_privileged_success_matrix_emits_one_event_per_completed_mutation(
    audit_factory,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session)
        target = AuthPrincipalRecord(
            principal_id=new_principal_id(), principal_type="human",
            display_name="Member", status="active", created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        session.add(target)
        session.commit()
        request_token = bind_security_audit_request(audit_factory)
        token = bind_authorization_context(context)
        try:
            tenant_service.add_or_reactivate_tenant_membership(
                session,
                tenant_id=TENANT_ID,
                subject=None,
                role="tenant_viewer",
                principal_id=target.principal_id,
                created_by_subject="audit:human",
                created_by_principal_id=context.actor_principal_id,
            )
            secret_consumers.create_change_source_secure(
                session,
                request=ChangeSourceCreate(
                    name="disabled source",
                    source_type=ChangeSourceType.GITHUB,
                    enabled=False,
                ),
                tenant_id=TENANT_ID,
                actor="not-audit-authority",
                store=object(),
            )
            create_ownership_mapping(
                session,
                OwnershipMappingCreate(
                    service_name="checkout",
                    owner_team="payments",
                ),
                tenant_id=TENANT_ID,
            )
            upsert_identity_override(
                session,
                IdentityOverrideCreate(
                    cluster_name="cluster-a",
                    namespace="payments",
                    entity_kind="Pod",
                    entity_name="checkout-abc",
                    action=IdentityOverrideAction.EXCLUDE,
                    reason="Known synthetic fixture",
                ),
                tenant_id=TENANT_ID,
            )
            create_enrollment_token(
                session,
                request=AgentEnrollmentTokenCreateRequest(label="audit"),
                created_by="not-persisted-in-audit",
                tenant_id=TENANT_ID,
            )
        finally:
            reset_authorization_context(token)
            reset_security_audit_request(request_token)
        actions = [
            event.action
            for event in session.scalars(
                select(SecurityAuditEventRecord).order_by(
                    SecurityAuditEventRecord.occurred_at,
                    SecurityAuditEventRecord.audit_event_id,
                )
            )
        ]
    assert sorted(actions) == sorted([
        "tenant_membership.created",
        "change_source.created",
        "ownership_mapping.upserted",
        "identity_override.upserted",
        "agent_enrollment_token.created",
    ])


def test_human_and_service_credential_lifecycle_is_audited_without_raw_secret(
    audit_factory,
) -> None:
    with audit_factory() as session:
        _, principal, tenant_context = _seed_human(session)
        self_context = authorize_authentication_self_service(principal)
        request_token = bind_security_audit_request(audit_factory)
        token = bind_authorization_context(self_context)
        try:
            human = create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name="Human self",
                    caller_type=ApiCredentialCallerType.HUMAN_API,
                    principal_id=principal.principal_id,
                ),
                created_by_subject=principal.subject,
                created_by_principal_id=principal.principal_id,
                now=NOW,
            )
            from app.db.models import AuthApiCredentialRecord

            human_record = session.get(
                AuthApiCredentialRecord, human.credential_id
            )
            assert human_record is not None
            revoke_auth_api_credential(
                session,
                record=human_record,
                revoked_by_subject=principal.subject,
                now=NOW,
            )
        finally:
            reset_authorization_context(token)

        tenant_context_value = authorize_tenant(
            session,
            principal=principal,
            tenant_context=tenant_context,
            required_permissions=frozenset(),
        )
        token = bind_authorization_context(tenant_context_value)
        try:
            service = create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name="Service credential",
                    caller_type=ApiCredentialCallerType.SERVICE_API,
                    subject="service:audit",
                    tenant_id=TENANT_ID,
                    permissions=[Permission.INTEGRATION_READ.value],
                ),
                created_by_subject=principal.subject,
                created_by_principal_id=principal.principal_id,
                now=NOW,
            )
            service_record = session.get(
                AuthApiCredentialRecord, service.credential_id
            )
            assert service_record is not None
            revoke_auth_api_credential(
                session,
                record=service_record,
                revoked_by_subject=principal.subject,
                now=NOW,
            )
        finally:
            reset_authorization_context(token)
            reset_security_audit_request(request_token)

        events = list(session.scalars(select(SecurityAuditEventRecord)))
        actions = {event.action for event in events}
        assert actions == {
            "api_credential.human.created",
            "api_credential.human.revoked",
            "api_credential.service.created",
            "api_credential.service.revoked",
        }
        assert all(human.api_credential not in value for event in events for value in vars(event).values() if isinstance(value, str))
        assert all(service.api_credential not in value for event in events for value in vars(event).values() if isinstance(value, str))
        assert all(event.tenant_id is None for event in events if ".human." in event.action)
        assert all(event.tenant_id == TENANT_ID for event in events if ".service." in event.action)


def test_service_credential_metadata_reads_are_durably_audited() -> None:
    raw_token = "ph5d-admin-" + secrets.token_urlsafe(40)
    configuration = AuthConfiguration(
        mode=AuthMode.REQUIRED,
        token_registry={
            token_digest(raw_token): TokenIdentity(
                subject="ph5d:admin",
                display_name="PH-5D admin",
                roles=("admin", "operator"),
            )
        },
        browser_allowed_origins=(),
        session_absolute_ttl_minutes=480,
        session_idle_ttl_minutes=60,
    )
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        principal = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="ph5d:admin",
            display_name="PH-5D admin",
            authentication_type="api_token",
            roles=(),
        )
        grant_installation_operator(
            session,
            principal_id=principal.principal_id,
        )
        principal_id = principal.principal_id

    application = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=lambda: None,
    )

    def override_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    try:
        headers = {"Authorization": f"Bearer {raw_token}"}
        with TestClient(application) as client:
            tenant = client.post(
                "/api/v1/tenants",
                headers=headers,
                json={"display_name": "PH-5D audit tenant"},
            )
            assert tenant.status_code == 201
            tenant_id = tenant.json()["tenant_id"]
            tenant_headers = {**headers, "X-Topo-Tenant-ID": tenant_id}
            created = client.post(
                "/api/v1/auth/api-credentials",
                headers=tenant_headers,
                json={
                    "name": "Metadata audit service",
                    "caller_type": "service_api",
                    "subject": "service:metadata-audit",
                    "tenant_id": tenant_id,
                    "permissions": ["incident.read"],
                },
            )
            assert created.status_code == 201
            credential_id = created.json()["credential_id"]

            listing = client.get(
                "/api/v1/auth/api-credentials?target_type=service",
                headers=tenant_headers,
            )
            detail = client.get(
                f"/api/v1/auth/api-credentials/{credential_id}",
                headers=tenant_headers,
            )
            assert listing.status_code == 200
            assert detail.status_code == 200

        with factory() as session:
            events = list(
                session.scalars(
                    select(SecurityAuditEventRecord).where(
                        SecurityAuditEventRecord.action.in_([
                            "api_credential.service.listed",
                            "api_credential.service.inspected",
                        ])
                    )
                )
            )
        assert {event.action for event in events} == {
            "api_credential.service.listed",
            "api_credential.service.inspected",
        }
        assert len(events) == 2
        assert all(event.actor_principal_id == principal_id for event in events)
        assert all(event.tenant_id == tenant_id for event in events)
        assert all(
            event.permissions_json == '["credential.metadata.read"]'
            for event in events
        )
        inspected = next(
            event
            for event in events
            if event.action == "api_credential.service.inspected"
        )
        assert inspected.resource_id == credential_id
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def test_direct_service_denial_is_durable_and_has_required_not_effective_permissions(
    audit_factory,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session, role="tenant_viewer")
    with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
        authorize_service_operation(
            "app.services.secret_consumers.create_change_source_secure",
            authorization_context=context,
            audit_session_factory=audit_factory,
        )
    with audit_factory() as session:
        event = session.scalar(select(SecurityAuditEventRecord))
        assert event is not None
        assert event.result == "denied"
        assert event.reason_code == "missing_permission"
        assert event.permissions_json == '["credential.rotate","integration.manage"]'
        assert event.actor_principal_id == context.actor_principal_id
        assert event.tenant_id == TENANT_ID


def test_one_request_scope_records_only_one_semantic_denial(audit_factory) -> None:
    with audit_factory() as session:
        context = _authorized_context(session, role="tenant_viewer")
    request_token = bind_security_audit_request(audit_factory)
    try:
        first = append_authorization_denial(
            authorization_context=context,
            required_permissions=[Permission.OWNERSHIP_MANAGE],
            failure_code="PERMISSION_DENIED",
        )
        second = append_authorization_denial(
            authorization_context=context,
            required_permissions=[Permission.OWNERSHIP_MANAGE],
            failure_code="PERMISSION_DENIED",
        )
    finally:
        reset_security_audit_request(request_token)
    assert first is True and second is False
    with audit_factory() as session:
        assert len(list(session.scalars(select(SecurityAuditEventRecord)))) == 1


def test_denial_writer_failure_still_denies_and_logs_only_bounded_code(
    audit_factory, monkeypatch,
) -> None:
    with audit_factory() as session:
        context = _authorized_context(session, role="tenant_viewer")

    def unavailable_factory():
        raise RuntimeError("topo_api_HOSTILE secret=https://user:pass@example.test")

    logged: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        "app.services.security_audit.LOGGER.error",
        lambda message, *args: logged.append((message, args)),
    )
    with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
        authorize_service_operation(
            "app.services.ownership_resolver.create_ownership_mapping",
            authorization_context=context,
            audit_session_factory=unavailable_factory,
        )
    assert logged == [
        ("SECURITY_AUDIT_WRITE_FAILED action=%s", ("authorization.denied",))
    ]
    assert "HOSTILE" not in repr(logged)
    assert "user:pass" not in repr(logged)


def test_route_denial_and_execution_disabled_are_audited_but_401_is_not(
    monkeypatch,
) -> None:
    raw_token = "ph5d-viewer-" + secrets.token_urlsafe(40)
    configuration = AuthConfiguration(
        mode=AuthMode.REQUIRED,
        token_registry={
            token_digest(raw_token): TokenIdentity(
                subject="ph5d:viewer",
                display_name="PH-5D viewer",
                roles=("admin", "operator"),
            )
        },
        browser_allowed_origins=(),
        session_absolute_ttl_minutes=480,
        session_idle_ttl_minutes=60,
    )
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        principal = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="ph5d:viewer",
            display_name="PH-5D viewer",
            authentication_type="api_token",
            roles=(),
        )
        session.add(
            TenantRecord(
                tenant_id=TENANT_ID,
                display_name="PH-5D",
                status="active",
                created_at=NOW.isoformat(),
                updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            )
        )
        session.add(
            TenantMembershipRecord(
                membership_id=f"tenant-membership:{uuid4()}",
                tenant_id=TENANT_ID,
                principal_id=principal.principal_id,
                role="tenant_viewer",
                status="active",
                created_at=NOW.isoformat(),
                updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            )
        )
        session.commit()
    application = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=lambda: None,
    )

    def override_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    try:
        with TestClient(application) as client:
            anonymous = client.post(
                "/api/v1/ownership/mappings",
                headers={"X-Topo-Tenant-ID": TENANT_ID},
                json={},
            )
            denied = client.post(
                "/api/v1/ownership/mappings",
                headers={
                    "Authorization": f"Bearer {raw_token}",
                    "X-Topo-Tenant-ID": TENANT_ID,
                },
                json={},
            )
            execution = client.get(
                "/api/v1/incidents/incident%3Afixture/approvals",
                headers={"Authorization": f"Bearer {raw_token}"},
            )
        assert anonymous.status_code == 401
        assert denied.status_code == 403
        assert execution.status_code == 403
        assert execution.json()["detail"]["code"] == "V1_EXECUTION_DISABLED"
        with factory() as session:
            events = list(session.scalars(select(SecurityAuditEventRecord).order_by(
                SecurityAuditEventRecord.action
            )))
        assert [(event.action, event.reason_code) for event in events] == [
            ("authorization.denied", "missing_permission"),
            ("execution.denied", "execution_disabled"),
        ]
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def test_agent_actor_uses_server_record_reference_not_fake_principal(audit_factory) -> None:
    from app.db.models import AgentEnrollmentTokenRecord

    with audit_factory() as session:
        if session.get(TenantRecord, TENANT_ID) is None:
            session.add(TenantRecord(
                tenant_id=TENANT_ID, display_name="Agent tenant", status="active",
                created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            ))
            session.commit()
        enrollment = AgentEnrollmentTokenRecord(
            tenant_id=TENANT_ID,
            enrollment_token_id="agent-enrollment:" + uuid4().hex,
            token_hash="1" * 64,
            token_hint="safe",
            label="fixture",
            max_uses=1,
            use_count=0,
            expires_at="2099-01-01T00:00:00+00:00",
            last_used_at=None,
            revoked_at=None,
            created_by=None,
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        session.add(enrollment)
        session.commit()
        context = authorize_agent_enrollment_fixed_purpose(
            session, enrollment=enrollment, reference_time=NOW
        )
        append_allowed_security_event(
            session,
            action=SecurityAuditAction.AGENT_ENROLLED,
            permissions=[],
            resource_type=SecurityAuditResourceType.AGENT,
            resource_id="agent:" + uuid4().hex,
            tenant_id=TENANT_ID,
            authorization_context=context,
        )
        session.commit()
        event = session.scalar(select(SecurityAuditEventRecord))
        assert event is not None
        assert event.actor_kind == "agent"
        assert event.actor_principal_id is None
        assert event.actor_reference == enrollment.enrollment_token_id
        assert event.authentication_type == "agent_enrollment"


def test_repository_is_append_only_by_supported_api() -> None:
    import app.repositories.security_audit_repository as repository

    public = {
        name for name in vars(repository)
        if not name.startswith("_") and callable(getattr(repository, name))
    }
    assert public == {"Session", "SecurityAuditEventRecord", "append_security_audit_event"}
    assert not any(word in public for word in {"update", "patch", "delete", "upsert"})
