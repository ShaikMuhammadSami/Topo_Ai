"""Real PostgreSQL 16 proof for the PH-5D security/admin audit ledger."""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import SecurityAuditEventRecord, TenantMembershipRecord
from app.db.schema_management import current_revisions, schema_differences
from app.models.security_audit import (
    SecurityAuditAction,
    SecurityAuditResourceType,
)
from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_service_operation,
    authorize_tenant,
    bind_authorization_context,
    reset_authorization_context,
)
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)
from app.services import tenant_service
from app.services.security_audit import append_local_operator_security_event
from app.services.security_audit import (
    bind_security_audit_request,
    reset_security_audit_request,
)
from test_minimum_authority_migrations import (
    HUMAN_A,
    HUMAN_B,
    TENANT_A,
    _seed_0013,
)
from test_postgres_runtime_compatibility import (
    _postgres_url,
    _temporary_database,
    _upgrade,
)


POSTGRES_URL = os.getenv("TOPO_TEST_POSTGRES_URL", "").strip()
POSTGRES_CONTAINER = os.getenv("TOPO_TEST_POSTGRES_CONTAINER", "").strip()
PARENT = "0014_min_authority"
HEAD = "0015_security_audit"
TABLE = "security_audit_events"

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 PH-5D proof",
)


def _migrate_populated(engine) -> None:
    _upgrade(engine, "0013_principal_enforce")
    _seed_0013(engine)
    _upgrade(engine, PARENT)
    _upgrade(engine, HEAD)


def _human_context(session: Session, *, role: str = "tenant_admin"):
    membership = session.scalar(
        select(TenantMembershipRecord).where(
            TenantMembershipRecord.tenant_id == TENANT_A,
            TenantMembershipRecord.principal_id == HUMAN_A,
        )
    )
    assert membership is not None
    if membership.role != role:
        membership.role = role
        session.commit()
    principal = AuthPrincipal(
        subject="ph5d:postgres-human",
        display_name="PH-5D PostgreSQL human",
        roles=(),
        authentication_type="human_api_token",
        principal_id=HUMAN_A,
        principal_type="human",
    )
    tenant_context = TenantContext(
        tenant_id=TENANT_A,
        principal_id=HUMAN_A,
        authenticated_subject=principal.subject,
        authentication_type=principal.authentication_type,
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id=membership.membership_id,
    )
    return authorize_tenant(
        session,
        principal=principal,
        tenant_context=tenant_context,
        required_permissions=frozenset(),
    )


def test_postgres_fresh_migration_matches_exact_audit_schema() -> None:
    with _temporary_database("ph5d_fresh") as engine:
        _upgrade(engine, PARENT)
        before = set(inspect(engine).get_table_names())
        _upgrade(engine, HEAD)
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) - before == {TABLE}
        assert len(Base.metadata.tables) == 50
        assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
        assert [column["name"] for column in inspector.get_columns(TABLE)] == [
            "audit_event_id",
            "occurred_at",
            "actor_principal_id",
            "actor_kind",
            "actor_reference",
            "authentication_type",
            "authority_kind",
            "tenant_id",
            "action",
            "permissions_json",
            "resource_type",
            "resource_id",
            "result",
            "reason_code",
            "request_id",
        ]
        assert {index["name"] for index in inspector.get_indexes(TABLE)} == {
            "ix_security_audit_action_occurred",
            "ix_security_audit_actor_occurred",
            "ix_security_audit_request_id",
            "ix_security_audit_tenant_occurred",
        }
        with engine.connect() as connection:
            assert current_revisions(connection) == (HEAD,)
            assert schema_differences(connection) == ()


def test_postgres_populated_upgrade_preserves_authority_and_starts_empty() -> None:
    with _temporary_database("ph5d_populated") as engine:
        _upgrade(engine, "0013_principal_enforce")
        _seed_0013(engine)
        _upgrade(engine, PARENT)
        tables = (
            "auth_principals",
            "tenant_memberships",
            "service_principal_permissions",
            "installation_operator_assignments",
            "auth_api_credentials",
        )
        with engine.connect() as connection:
            before = {
                table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
                for table in tables
            }
        _upgrade(engine, HEAD)
        with engine.connect() as connection:
            after = {
                table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
                for table in tables
            }
            assert after == before
            assert connection.scalar(text(f"SELECT COUNT(*) FROM {TABLE}")) == 0


def test_postgres_concurrent_independent_audit_appends_are_unique() -> None:
    with _temporary_database("ph5d_concurrent") as engine:
        _upgrade(engine)
        factory = sessionmaker(engine, expire_on_commit=False)

        def append(number: int) -> str:
            with factory() as session, session.begin():
                event = append_local_operator_security_event(
                    session,
                    action=SecurityAuditAction.INSTALLATION_SECRET_INSPECTED,
                    permissions=[Permission.INSTALLATION_STATUS_READ],
                    resource_type=SecurityAuditResourceType.SECRET_RECORD,
                    resource_id=f"postgres-audit-{number}",
                )
                return event.audit_event_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            identifiers = list(executor.map(append, (1, 2)))
        assert len(set(identifiers)) == 2
        with Session(engine) as session:
            events = list(session.scalars(select(SecurityAuditEventRecord)))
        assert {event.audit_event_id for event in events} == set(identifiers)
        assert all(event.occurred_at.endswith("+00:00") for event in events)


def test_postgres_privileged_mutation_and_audit_are_atomic(monkeypatch) -> None:
    with _temporary_database("ph5d_allowed_atomic") as engine:
        _migrate_populated(engine)
        with Session(engine) as session:
            context = _human_context(session)
            request_token = bind_security_audit_request(
                sessionmaker(engine, expire_on_commit=False)
            )
            token = bind_authorization_context(context)
            try:
                tenant_service.add_or_reactivate_tenant_membership(
                    session,
                    tenant_id=TENANT_A,
                    subject=None,
                    role="tenant_viewer",
                    principal_id=HUMAN_B,
                    created_by_subject="ph5d:postgres-human",
                    created_by_principal_id=HUMAN_A,
                )
            finally:
                reset_authorization_context(token)
                reset_security_audit_request(request_token)
        with Session(engine) as session:
            membership = session.scalar(
                select(TenantMembershipRecord).where(
                    TenantMembershipRecord.tenant_id == TENANT_A,
                    TenantMembershipRecord.principal_id == HUMAN_B,
                )
            )
            event = session.scalar(select(SecurityAuditEventRecord))
            assert membership is not None and membership.status == "active"
            assert event is not None
            assert event.action == "tenant_membership.reactivated"
            assert event.result == "allowed"

    with _temporary_database("ph5d_allowed_rollback") as engine:
        _migrate_populated(engine)
        with Session(engine) as session:
            context = _human_context(session)
            request_token = bind_security_audit_request(
                sessionmaker(engine, expire_on_commit=False)
            )
            token = bind_authorization_context(context)
            monkeypatch.setattr(
                tenant_service,
                "append_allowed_security_event",
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    SQLAlchemyError("synthetic PostgreSQL audit failure")
                ),
            )
            try:
                with pytest.raises(tenant_service.TenantPersistenceError):
                    tenant_service.add_or_reactivate_tenant_membership(
                        session,
                        tenant_id=TENANT_A,
                        subject=None,
                        role="tenant_viewer",
                        principal_id=HUMAN_B,
                        created_by_subject="ph5d:postgres-human",
                        created_by_principal_id=HUMAN_A,
                    )
            finally:
                reset_authorization_context(token)
                reset_security_audit_request(request_token)
        with Session(engine) as session:
            membership = session.scalar(
                select(TenantMembershipRecord).where(
                    TenantMembershipRecord.tenant_id == TENANT_A,
                    TenantMembershipRecord.principal_id == HUMAN_B,
                )
            )
            assert membership is not None and membership.status == "disabled"
            assert session.scalar(select(SecurityAuditEventRecord)) is None


def test_postgres_denial_is_independent_and_writer_failure_never_allows() -> None:
    with _temporary_database("ph5d_denial") as engine:
        _migrate_populated(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory() as request_session:
            context = _human_context(request_session, role="tenant_viewer")
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_service_operation(
                    "app.services.secret_consumers.create_change_source_secure",
                    authorization_context=context,
                    audit_session_factory=factory,
                )
            request_session.rollback()
        with factory() as session:
            event = session.scalar(select(SecurityAuditEventRecord))
            assert event is not None
            assert event.result == "denied"
            assert event.reason_code == "missing_permission"
            assert event.permissions_json == (
                '["credential.rotate","integration.manage"]'
            )

        def unavailable_factory():
            raise RuntimeError("postgres audit writer unavailable")

        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_service_operation(
                "app.services.secret_consumers.create_change_source_secure",
                authorization_context=context,
                audit_session_factory=unavailable_factory,
            )
        with factory() as session:
            assert session.scalar(
                text("SELECT COUNT(*) FROM security_audit_events")
            ) == 1


def test_postgres_logical_backup_restore_preserves_exact_audit_event() -> None:
    if not POSTGRES_CONTAINER:
        pytest.skip("set TOPO_TEST_POSTGRES_CONTAINER for PH-5D restore proof")
    with _temporary_database("ph5d_restore") as engine:
        _upgrade(engine)
        with Session(engine) as session, session.begin():
            event = append_local_operator_security_event(
                session,
                action=SecurityAuditAction.INSTALLATION_SECRET_ROTATED,
                permissions=[Permission.INSTALLATION_SECRET_MANAGE],
                resource_type=SecurityAuditResourceType.SECRET_RECORD,
                resource_id="openai",
            )
            expected = {
                column.name: getattr(event, column.name)
                for column in SecurityAuditEventRecord.__table__.columns
            }

        database_name = make_url(engine.url).database
        database_user = make_url(_postgres_url()).username
        assert database_name and database_user
        dump_path = f"/tmp/{database_name}.dump"
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "pg_dump",
                    "-U",
                    database_user,
                    "-d",
                    database_name,
                    "--format=custom",
                    f"--file={dump_path}",
                ],
                check=True,
                capture_output=True,
            )
            base_url = make_url(_postgres_url())
            admin = create_engine(
                base_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
            )
            engine.dispose()
            try:
                with admin.connect() as connection:
                    connection.execute(
                        text(
                            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE datname = :database_name "
                            "AND pid <> pg_backend_pid()"
                        ),
                        {"database_name": database_name},
                    )
                    connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
                    connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            finally:
                admin.dispose()
            subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "pg_restore",
                    "-U",
                    database_user,
                    "-d",
                    database_name,
                    "--exit-on-error",
                    dump_path,
                ],
                check=True,
                capture_output=True,
            )
            restored = create_engine(base_url.set(database=database_name))
            try:
                with Session(restored) as session:
                    restored_event = session.get(
                        SecurityAuditEventRecord, expected["audit_event_id"]
                    )
                    assert restored_event is not None
                    assert {
                        column.name: getattr(restored_event, column.name)
                        for column in SecurityAuditEventRecord.__table__.columns
                    } == expected
                    assert session.scalar(
                        text("SELECT COUNT(*) FROM security_audit_events")
                    ) == 1
            finally:
                restored.dispose()
        finally:
            subprocess.run(
                ["docker", "exec", POSTGRES_CONTAINER, "rm", "-f", dump_path],
                check=False,
                capture_output=True,
            )
