from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.schema_management import SchemaAuthorityError
from app.db.models import (
    AuthPrincipalRecord,
    InstallationOperatorAssignmentRecord,
    ServicePrincipalPermissionRecord,
    TenantMembershipRecord,
    TenantRecord,
)
from app.models.principal_identity import new_principal_id
from app.security.authorization_policy import (
    INSTALLATION_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
    Permission,
    TenantRole,
)
from app.security.principals import AuthPrincipal
from app.services.authority_assignments import (
    AuthorityAssignmentError,
    create_service_permission_assignment,
    disable_installation_operator,
    get_installation_operator_status,
    grant_installation_operator,
    resolve_installation_permissions,
    resolve_service_permissions,
    resolve_tenant_permissions,
    update_service_permissions,
)
from app.services.principal_identity import PrincipalNotProvisionedError, PrincipalTypeMismatchError


NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


@pytest.fixture()
def authority_factory():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _principal(session: Session, principal_type: str = "human") -> AuthPrincipalRecord:
    record = AuthPrincipalRecord(
        principal_id=new_principal_id(), principal_type=principal_type,
        display_name="Same display is not authority", status="active",
        created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
    )
    session.add(record)
    session.commit()
    return record


def _membership(session: Session, principal_id: str, role: TenantRole) -> TenantMembershipRecord:
    tenant = TenantRecord(
        tenant_id=f"tenant:{uuid4()}", display_name="Authority test tenant", status="active",
        created_at=NOW.isoformat(), updated_at=NOW.isoformat(), created_by_subject="fixture",
    )
    record = TenantMembershipRecord(
        membership_id=f"membership:{uuid4()}", tenant_id=tenant.tenant_id,
        principal_id=principal_id, role=role.value, status="active",
        created_at=NOW.isoformat(), updated_at=NOW.isoformat(), created_by_subject="fixture",
    )
    session.add_all([tenant, record])
    session.commit()
    return record


def test_human_permissions_follow_each_membership_not_global_identity_or_legacy_roles(authority_factory) -> None:
    with authority_factory() as session:
        human = _principal(session)
        viewer = _membership(session, human.principal_id, TenantRole.VIEWER)
        responder = _membership(session, human.principal_id, TenantRole.RESPONDER)
        admin = _membership(session, human.principal_id, TenantRole.ADMIN)
        authenticated = AuthPrincipal(
            subject="same", display_name="Same", roles=(), authentication_type="human_api_token",
            principal_id=human.principal_id, principal_type="human",
        )
        for caller in (authenticated, replace(authenticated, roles=("admin", "operator", "superadmin"))):
            for membership, role in ((viewer, TenantRole.VIEWER), (responder, TenantRole.RESPONDER), (admin, TenantRole.ADMIN)):
                assert resolve_tenant_permissions(session, principal_id=caller.principal_id, tenant_id=membership.tenant_id) == TENANT_ROLE_PERMISSIONS[role]
            assert resolve_installation_permissions(session, principal_id=caller.principal_id) == frozenset()


def test_installation_authority_is_explicit_and_orthogonal(authority_factory) -> None:
    with authority_factory() as session:
        human = _principal(session)
        another = _principal(session)
        admin = _membership(session, another.principal_id, TenantRole.ADMIN)
        assert get_installation_operator_status(session, principal_id=human.principal_id)["assignment_status"] == "unassigned"
        assigned = grant_installation_operator(session, principal_id=human.principal_id, now=NOW)
        repeated = grant_installation_operator(session, principal_id=human.principal_id)
        assert repeated.created_at == assigned.updated_at == NOW.isoformat()
        assert session.scalar(select(func.count()).select_from(InstallationOperatorAssignmentRecord)) == 1
        assert resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=admin.tenant_id) == frozenset()
        assert resolve_installation_permissions(session, principal_id=human.principal_id) == INSTALLATION_PERMISSIONS
        assert resolve_installation_permissions(session, principal_id=another.principal_id) == frozenset()
        viewer = _membership(session, human.principal_id, TenantRole.VIEWER)
        assert resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=viewer.tenant_id) == TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
        disable_installation_operator(session, principal_id=human.principal_id, now=NOW)
        assert resolve_installation_permissions(session, principal_id=human.principal_id) == frozenset()
        assert resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=viewer.tenant_id) == TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
        grant_installation_operator(session, principal_id=human.principal_id)
        assert resolve_installation_permissions(session, principal_id=human.principal_id) == INSTALLATION_PERMISSIONS


def test_membership_and_principal_disablement_remove_current_authority(authority_factory) -> None:
    with authority_factory() as session:
        human = _principal(session)
        member = _membership(session, human.principal_id, TenantRole.ADMIN)
        other = _membership(session, human.principal_id, TenantRole.VIEWER)
        grant_installation_operator(session, principal_id=human.principal_id)
        member.status = "disabled"
        session.commit()
        assert resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=member.tenant_id) == frozenset()
        assert resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=other.tenant_id) == TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
        human.status = "disabled"
        session.commit()
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=other.tenant_id)
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_installation_permissions(session, principal_id=human.principal_id)
        with pytest.raises(PrincipalNotProvisionedError):
            grant_installation_operator(session, principal_id=human.principal_id)
        disable_installation_operator(session, principal_id=human.principal_id)
        assert get_installation_operator_status(session, principal_id=human.principal_id)["effective"] is False


def test_service_exact_subset_and_creation_share_callers_transaction(authority_factory) -> None:
    with authority_factory() as session:
        service = _principal(session, "service")
        record = create_service_permission_assignment(
            session, principal_id=service.principal_id,
            permissions=["topology.read", "incident.read"], now=NOW,
        )
        assert record.permissions_json == '["incident.read","topology.read"]'
        assert record.row_version == 1
        session.rollback()
        assert session.get(ServicePrincipalPermissionRecord, service.principal_id) is None
        with pytest.raises(AuthorityAssignmentError, match="SERVICE_PERMISSIONS_UNAVAILABLE"):
            resolve_service_permissions(session, principal_id=service.principal_id)
        create_service_permission_assignment(session, principal_id=service.principal_id, permissions=["incident.read", "incident.respond"])
        session.commit()
        assert resolve_service_permissions(session, principal_id=service.principal_id) == {Permission.INCIDENT_READ, Permission.INCIDENT_RESPOND}
        create_service_permission_assignment(session, principal_id=service.principal_id, permissions=["incident.respond", "incident.read"])
        assert session.scalar(select(func.count()).select_from(ServicePrincipalPermissionRecord)) == 1
        with pytest.raises(AuthorityAssignmentError, match="SERVICE_PERMISSIONS_ALREADY_ASSIGNED"):
            create_service_permission_assignment(session, principal_id=service.principal_id, permissions=["topology.read"])


def test_service_permission_update_is_compare_and_set(authority_factory) -> None:
    with authority_factory() as session:
        service = _principal(session, "service")
        original = create_service_permission_assignment(session, principal_id=service.principal_id, permissions=["incident.read"], now=NOW)
        session.commit()
        updated = update_service_permissions(session, principal_id=service.principal_id, permissions=["evidence.read"], expected_row_version=1)
        assert updated.row_version == 2
        assert updated.created_at == original.created_at == NOW.isoformat()
        with pytest.raises(AuthorityAssignmentError, match="SERVICE_PERMISSIONS_CONCURRENT_MODIFICATION"):
            update_service_permissions(session, principal_id=service.principal_id, permissions=["topology.read"], expected_row_version=1)
        assert resolve_service_permissions(session, principal_id=service.principal_id) == {Permission.EVIDENCE_READ}
        assert session.get(ServicePrincipalPermissionRecord, service.principal_id).row_version == 2
        service.status = "disabled"
        session.commit()
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_service_permissions(session, principal_id=service.principal_id)


def test_long_lived_identity_map_does_not_cache_authority(authority_factory) -> None:
    with authority_factory() as setup:
        human = _principal(setup)
        service = _principal(setup, "service")
        member = _membership(setup, human.principal_id, TenantRole.ADMIN)
        grant_installation_operator(setup, principal_id=human.principal_id)
        create_service_permission_assignment(setup, principal_id=service.principal_id, permissions=["incident.read"])
        setup.commit()
    with authority_factory() as reader:
        held_human = reader.get(AuthPrincipalRecord, human.principal_id)
        held_service = reader.get(AuthPrincipalRecord, service.principal_id)
        held_membership = reader.get(TenantMembershipRecord, member.membership_id)
        held_assignment = reader.get(ServicePrincipalPermissionRecord, service.principal_id)
        held_installation = reader.get(InstallationOperatorAssignmentRecord, human.principal_id)
        assert all(item is not None for item in (held_human, held_service, held_membership, held_assignment, held_installation))
        with authority_factory() as writer:
            changed = writer.get(TenantMembershipRecord, member.membership_id)
            changed.role = TenantRole.VIEWER.value
            writer.commit()
            update_service_permissions(writer, principal_id=service.principal_id, permissions=["evidence.read"], expected_row_version=1)
            disable_installation_operator(writer, principal_id=human.principal_id)
        assert resolve_tenant_permissions(reader, principal_id=human.principal_id, tenant_id=member.tenant_id) == TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
        assert resolve_service_permissions(reader, principal_id=service.principal_id) == {Permission.EVIDENCE_READ}
        assert resolve_installation_permissions(reader, principal_id=human.principal_id) == frozenset()
        with authority_factory() as writer:
            writer.get(AuthPrincipalRecord, human.principal_id).status = "disabled"
            writer.get(AuthPrincipalRecord, service.principal_id).status = "disabled"
            writer.commit()
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_tenant_permissions(reader, principal_id=human.principal_id, tenant_id=member.tenant_id)
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_service_permissions(reader, principal_id=service.principal_id)
        with pytest.raises(PrincipalNotProvisionedError):
            resolve_installation_permissions(reader, principal_id=human.principal_id)
        assert get_installation_operator_status(reader, principal_id=human.principal_id)["principal_status"] == "disabled"


@pytest.mark.parametrize("stored", [
    "not-json", "{}", "null", "[]", '["incident.read","incident.read"]',
    '["member.manage"]', '["installation.secret.manage"]', '["execution.execute"]',
    '["unknown"]', '[true]', '[42]', '["incident.read", "topology.read"]',
    '["topology.read","incident.read"]', " " * 2049,
])
def test_corrupt_stored_service_authority_fails_closed(authority_factory, stored) -> None:
    with authority_factory() as session:
        service = _principal(session, "service")
        record = create_service_permission_assignment(session, principal_id=service.principal_id, permissions=["incident.read"])
        record.permissions_json = stored
        session.commit()
        with pytest.raises(AuthorityAssignmentError, match="^SERVICE_PERMISSIONS_INVALID$"):
            resolve_service_permissions(session, principal_id=service.principal_id)


def test_unknown_stored_role_is_rejected_physically_and_at_resolution(authority_factory) -> None:
    with authority_factory() as session:
        human = _principal(session)
        membership = _membership(session, human.principal_id, TenantRole.VIEWER)
        membership.role = "superadmin"
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.execute(text("PRAGMA ignore_check_constraints=ON"))
        session.execute(text("UPDATE tenant_memberships SET role='superadmin'"))
        session.commit()
        session.execute(text("PRAGMA ignore_check_constraints=OFF"))
        with pytest.raises(AuthorityAssignmentError, match="TENANT_ROLE_INVALID"):
            resolve_tenant_permissions(session, principal_id=human.principal_id, tenant_id=membership.tenant_id)


def test_wrong_principal_types_and_machine_identifiers_never_resolve_authority(authority_factory) -> None:
    with authority_factory() as session:
        human = _principal(session)
        service = _principal(session, "service")
        member = _membership(session, human.principal_id, TenantRole.ADMIN)
        with pytest.raises(PrincipalTypeMismatchError):
            resolve_service_permissions(session, principal_id=human.principal_id)
        with pytest.raises(PrincipalTypeMismatchError):
            create_service_permission_assignment(session, principal_id=human.principal_id, permissions=["incident.read"])
        for resolver in (resolve_installation_permissions, grant_installation_operator, disable_installation_operator):
            with pytest.raises(PrincipalTypeMismatchError):
                resolver(session, principal_id=service.principal_id)
        with pytest.raises(PrincipalTypeMismatchError):
            resolve_tenant_permissions(session, principal_id=service.principal_id, tenant_id=member.tenant_id)
        for machine_id in ("agent:fixture", "change-source:fixture", "same-display", "test:subject"):
            for resolver in (resolve_service_permissions, resolve_installation_permissions):
                with pytest.raises(PrincipalNotProvisionedError):
                    resolver(session, principal_id=machine_id)


def test_local_operator_utility_accepts_only_exact_human_ids_and_safe_output(authority_factory, monkeypatch, capsys) -> None:
    from app import installation_operator_admin as admin

    monkeypatch.setattr(admin, "init_db", lambda: None)
    monkeypatch.setattr(admin, "SessionLocal", authority_factory)
    with authority_factory() as session:
        human = _principal(session)
        service = _principal(session, "service")
    assert admin.main(["status", human.principal_id]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "principal_id": human.principal_id, "principal_status": "active",
        "assignment_status": "unassigned", "effective": False,
    }
    assert admin.main(["grant", human.principal_id]) == 0
    assert json.loads(capsys.readouterr().out)["effective"] is True
    assert admin.main(["disable", human.principal_id]) == 0
    assert json.loads(capsys.readouterr().out)["assignment_status"] == "disabled"
    assert admin.main(["grant", service.principal_id]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "PRINCIPAL_TYPE_MISMATCH"
    with pytest.raises(SystemExit) as invalid:
        admin.main(["grant", "secret-like-arbitrary-input"])
    assert invalid.value.code == 2
    assert "secret-like-arbitrary-input" not in capsys.readouterr().err

    def unavailable():
        raise SQLAlchemyError("connection-string-with-secret")

    monkeypatch.setattr(admin, "init_db", unavailable)
    assert admin.main(["status", human.principal_id]) == 2
    output = capsys.readouterr().err
    assert "connection-string-with-secret" not in output
    assert json.loads(output)["code"] == "INSTALLATION_OPERATOR_OPERATION_FAILED"

    def legacy_schema():
        raise SchemaAuthorityError("private-database-path-and-schema-detail")

    monkeypatch.setattr(admin, "init_db", legacy_schema)
    assert admin.main(["status", human.principal_id]) == 2
    output = capsys.readouterr().err
    assert "private-database-path-and-schema-detail" not in output
    assert json.loads(output)["code"] == "INSTALLATION_OPERATOR_SCHEMA_UNAVAILABLE"
