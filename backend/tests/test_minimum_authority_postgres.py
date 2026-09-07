"""Real PostgreSQL 16 READ COMMITTED authority persistence and race proofs."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    InstallationOperatorAssignmentRecord, ServicePrincipalPermissionRecord,
)
from app.db.schema_management import current_revisions, schema_differences
from app.services.authority_assignments import (
    AuthorityAssignmentError, grant_installation_operator,
    resolve_service_permissions, update_service_permissions,
)
from test_minimum_authority_migrations import (
    HEAD, HUMAN_A, NEW_TABLES, PARENT, SERVICE_A,
    _assert_populated_authority, _migrate, _seed_0013,
)
from test_postgres_runtime_compatibility import _temporary_database


pytestmark = pytest.mark.skipif(
    not os.getenv("TOPO_TEST_POSTGRES_URL"),
    reason="set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 authority proof",
)


def _assert_postgres_read_committed(engine) -> None:
    with engine.connect() as connection:
        assert connection.scalar(text("SHOW server_version")).startswith("16.")
        assert connection.scalar(text("SHOW transaction_isolation")) == "read committed"


def test_postgresql_fresh_authority_schema_and_disposable_downgrade() -> None:
    with _temporary_database("ph5b_fresh") as engine:
        _assert_postgres_read_committed(engine)
        _migrate(engine, PARENT)
        before = set(inspect(engine).get_table_names())
        _migrate(engine)
        assert set(inspect(engine).get_table_names()) - before == NEW_TABLES
        with engine.connect() as connection:
            assert current_revisions(connection) == (HEAD,)
            assert schema_differences(connection) == ()
        _migrate(engine, PARENT, down=True)
        assert set(inspect(engine).get_table_names()) == before
        _migrate(engine)
        with engine.connect() as connection:
            assert schema_differences(connection) == ()


def test_postgresql_populated_authority_backfill_preserves_identity_and_binding() -> None:
    with _temporary_database("ph5b_populated") as engine:
        _migrate(engine, PARENT)
        _seed_0013(engine)
        _migrate(engine)
        _assert_populated_authority(engine)
        with engine.connect() as connection:
            assert schema_differences(connection) == ()
        _migrate(engine, PARENT, down=True)
        _migrate(engine)
        _assert_populated_authority(engine)


@pytest.mark.parametrize("role", [None, "admin", "Tenant_Viewer", "tenant_viewer ", "*", ""])
def test_postgresql_membership_role_has_physical_closed_constraint(role) -> None:
    with _temporary_database("ph5b_role_check") as engine:
        _migrate(engine, PARENT)
        _seed_0013(engine)
        _migrate(engine)
        role_column = next(column for column in inspect(engine).get_columns("tenant_memberships") if column["name"] == "role")
        assert not role_column["nullable"] and role_column["default"] is None
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(
                "UPDATE tenant_memberships SET role=:role WHERE membership_id='membership:authority-1'"
            ), {"role": role})


@pytest.mark.parametrize("malformed", [
    '["unknown.permission"]', '["installation.status.read"]', '["member.read"]',
    '["incident.read","incident.read"]', '[]', '{}', '[1]',
    '["topology.read","incident.read"]', '[ "incident.read" ]',
])
def test_postgresql_malformed_persisted_service_permissions_fail_closed(malformed) -> None:
    with _temporary_database("ph5b_stored_invalid") as engine:
        _migrate(engine, PARENT)
        _seed_0013(engine)
        _migrate(engine)
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE service_principal_permissions SET permissions_json=:value WHERE principal_id=:principal"
            ), {"value": malformed, "principal": SERVICE_A})
        with Session(engine) as session, pytest.raises(AuthorityAssignmentError, match="SERVICE_PERMISSIONS_INVALID"):
            resolve_service_permissions(session, principal_id=SERVICE_A)


def test_postgresql_service_permissions_cas_has_one_winner_and_no_lost_update() -> None:
    with _temporary_database("ph5b_service_cas") as engine:
        _assert_postgres_read_committed(engine)
        _migrate(engine, PARENT)
        _seed_0013(engine)
        _migrate(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        barrier = Barrier(2)

        def replace(permission: str) -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                try:
                    record = update_service_permissions(
                        session, principal_id=SERVICE_A, permissions=[permission],
                        expected_row_version=1,
                    )
                except AuthorityAssignmentError as exc:
                    assert str(exc) == "SERVICE_PERMISSIONS_CONCURRENT_MODIFICATION"
                    return "stale"
                assert record.row_version == 2
                return permission

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(replace, ("incident.read", "topology.read")))
        assert results.count("stale") == 1
        winner = next(value for value in results if value != "stale")
        with factory() as session:
            record = session.get(ServicePrincipalPermissionRecord, SERVICE_A)
            assert record is not None and record.row_version == 2
            assert record.permissions_json == f'["{winner}"]'
            assert {permission.value for permission in resolve_service_permissions(session, principal_id=SERVICE_A)} == {winner}


def test_postgresql_concurrent_operator_grant_has_one_semantic_assignment() -> None:
    with _temporary_database("ph5b_operator_grant") as engine:
        _assert_postgres_read_committed(engine)
        _migrate(engine, PARENT)
        _seed_0013(engine)
        _migrate(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        barrier = Barrier(2)

        def grant(_: int) -> tuple[str, str]:
            with factory() as session:
                barrier.wait(timeout=10)
                record = grant_installation_operator(session, principal_id=HUMAN_A)
                return record.principal_id, record.created_at

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(grant, (1, 2)))
        assert len(set(results)) == 1
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(InstallationOperatorAssignmentRecord)) == 1
            assert session.get(InstallationOperatorAssignmentRecord, HUMAN_A).status == "active"


def test_postgresql_authority_migration_failure_is_atomic(monkeypatch) -> None:
    from alembic import op

    with _temporary_database("ph5b_atomic") as engine:
        _migrate(engine, PARENT)
        _seed_0013(engine)
        actual = op.create_table

        def interrupt(*args, **kwargs):
            actual(*args, **kwargs)
            raise RuntimeError("synthetic authority migration interruption")

        monkeypatch.setattr(op, "create_table", interrupt)
        with pytest.raises(RuntimeError, match="synthetic authority migration interruption"):
            _migrate(engine)
        with engine.connect() as connection:
            assert current_revisions(connection) == (PARENT,)
            assert NEW_TABLES.isdisjoint(inspect(connection).get_table_names())
            assert "role" not in {column["name"] for column in inspect(connection).get_columns("tenant_memberships")}
            assert connection.scalar(text("SELECT COUNT(*) FROM tenant_memberships")) == 3
