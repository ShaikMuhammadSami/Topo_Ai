"""PH-5B additive authority migration proof on disposable databases only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.database import Base
from app.db.schema_management import (
    alembic_config, current_revisions, schema_differences, script_directory,
)


PARENT = "0013_principal_enforce"
AUTHORITY_REVISION = "0014_min_authority"
HEAD = "0015_security_audit"
NEW_TABLES = {"service_principal_permissions", "installation_operator_assignments"}
TENANT_A = "tenant:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TENANT_B = "tenant:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
HUMAN_A = "principal:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
HUMAN_B = "principal:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SERVICE_A = "principal:cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SERVICE_B = "principal:dddddddd-dddd-4ddd-8ddd-dddddddddddd"
NOW = "2026-09-06T00:00:00+00:00"
SERVICE_COMPATIBILITY = (
    "evidence.read", "incident.read", "incident.respond", "integration.manage",
    "integration.read", "ownership.manage", "ownership.read", "report.read",
    "topology.read",
)
CANONICAL_COMPATIBILITY = json.dumps(SERVICE_COMPATIBILITY, separators=(",", ":"))


def _migrate(engine, target: str = HEAD, *, down: bool = False) -> None:
    with engine.begin() as connection:
        operation = command.downgrade if down else command.upgrade
        operation(alembic_config(connection=connection), target)


def _seed_0013(engine) -> None:
    """Two humans, two tenants, two services, and rotating same-principal credentials."""
    metadata = sa.MetaData()
    metadata.reflect(engine, only=[
        "auth_principals", "external_identities", "tenants", "tenant_memberships",
        "auth_api_credentials", "service_api_tenant_bindings",
    ])
    with engine.begin() as connection:
        for principal_id, principal_type in (
            (HUMAN_A, "human"), (HUMAN_B, "human"),
            (SERVICE_A, "service"), (SERVICE_B, "service"),
        ):
            connection.execute(metadata.tables["auth_principals"].insert().values(
                principal_id=principal_id, principal_type=principal_type,
                display_name="Same deliberately non-authoritative display name",
                status="active", created_at=NOW, updated_at=NOW,
            ))
        for principal_id in (HUMAN_A, HUMAN_B):
            connection.execute(metadata.tables["external_identities"].insert().values(
                external_identity_id=principal_id.replace("principal:", "identity:"),
                principal_id=principal_id, issuer="urn:topo:auth:legacy-local-v1",
                subject=principal_id, status="active", created_at=NOW, updated_at=NOW,
            ))
        for tenant_id in (TENANT_A, TENANT_B):
            connection.execute(metadata.tables["tenants"].insert().values(
                tenant_id=tenant_id, display_name=tenant_id, status="active",
                created_at=NOW, updated_at=NOW, created_by_subject=HUMAN_A,
            ))
        for number, (principal_id, tenant_id, status) in enumerate((
            (HUMAN_A, TENANT_A, "active"), (HUMAN_A, TENANT_B, "active"),
            (HUMAN_B, TENANT_A, "disabled"),
        ), 1):
            connection.execute(metadata.tables["tenant_memberships"].insert().values(
                membership_id=f"membership:authority-{number}", tenant_id=tenant_id,
                principal_id=principal_id, status=status, created_at=NOW,
                updated_at=NOW, created_by_subject=HUMAN_A,
            ))
        for number, (principal_id, caller_type, tenant_id) in enumerate((
            (SERVICE_A, "service_api", TENANT_A),
            (SERVICE_A, "service_api", TENANT_A),
            (SERVICE_B, "service_api", TENANT_B),
            (HUMAN_A, "human_api", None),
        ), 1):
            credential_id = f"credential:authority-{number}"
            connection.execute(metadata.tables["auth_api_credentials"].insert().values(
                credential_id=credential_id, principal_id=principal_id,
                credential_secret_digest=str(number) * 64, credential_hint="synthetic",
                name=credential_id, caller_type=caller_type, subject=principal_id,
                display_name="Legacy admin", roles_json='["admin","operator"]',
                created_at=NOW, created_by_subject=HUMAN_A,
                expires_at="2099-01-01T00:00:00+00:00", revoked_at=None,
                revoked_by_subject=None, last_used_at=None, updated_at=NOW,
            ))
            if tenant_id is not None:
                connection.execute(metadata.tables["service_api_tenant_bindings"].insert().values(
                    binding_id=f"binding:authority-{number}", credential_id=credential_id,
                    tenant_id=tenant_id, created_at=NOW, created_by_subject=HUMAN_A,
                ))


def _assert_populated_authority(engine) -> None:
    with engine.connect() as connection:
        roles = connection.execute(text(
            "SELECT membership_id, role FROM tenant_memberships ORDER BY membership_id"
        )).all()
        assert roles == [(f"membership:authority-{n}", "tenant_admin") for n in range(1, 4)]
        assignments = connection.execute(text(
            "SELECT principal_id, permissions_json, row_version FROM "
            "service_principal_permissions ORDER BY principal_id"
        )).all()
        assert assignments == [
            (SERVICE_A, CANONICAL_COMPATIBILITY, 1),
            (SERVICE_B, CANONICAL_COMPATIBILITY, 1),
        ]
        assert connection.scalar(text("SELECT COUNT(*) FROM installation_operator_assignments")) == 0
        bindings = connection.execute(text(
            "SELECT c.principal_id, b.tenant_id, COUNT(*) FROM auth_api_credentials c "
            "JOIN service_api_tenant_bindings b ON b.credential_id=c.credential_id "
            "GROUP BY c.principal_id, b.tenant_id ORDER BY c.principal_id"
        )).all()
        assert bindings == [(SERVICE_A, TENANT_A, 2), (SERVICE_B, TENANT_B, 1)]
        assert connection.scalar(text(
            "SELECT COUNT(*) FROM tenant_memberships m JOIN auth_principals p "
            "ON p.principal_id=m.principal_id WHERE p.principal_type='service'"
        )) == 0


@pytest.fixture()
def authority_migration_engine(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'authority.db').as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


def test_0014_is_the_only_static_minimum_authority_migration() -> None:
    scripts = script_directory()
    assert scripts.get_heads() == [HEAD]
    revision = scripts.get_revision(AUTHORITY_REVISION)
    assert revision.down_revision == PARENT
    assert Path(revision.path).name == "0014_minimum_authority_bundles.py"
    source = Path(revision.path).read_text(encoding="utf-8")
    assert "from app" not in source
    assert "Base.metadata" not in source
    assert source.count("op.create_table(") == 2
    assert revision.module.SERVICE_COMPATIBILITY_PERMISSIONS == SERVICE_COMPATIBILITY


def test_fresh_sqlite_authority_schema_is_exact_without_defaults(authority_migration_engine) -> None:
    engine = authority_migration_engine
    _migrate(engine, PARENT)
    before = set(inspect(engine).get_table_names())
    _migrate(engine, AUTHORITY_REVISION)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - before == NEW_TABLES
    role = next(column for column in inspector.get_columns("tenant_memberships") if column["name"] == "role")
    assert not role["nullable"] and role["default"] is None
    assert Base.metadata.tables["tenant_memberships"].c.role.default is None
    assert Base.metadata.tables["tenant_memberships"].c.role.server_default is None
    for table_name in NEW_TABLES:
        assert "tenant_id" not in Base.metadata.tables[table_name].c
        assert all(column["default"] is None for column in inspector.get_columns(table_name))
    _migrate(engine, HEAD)
    assert len(Base.metadata.tables) == 50
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
    with engine.connect() as connection:
        assert current_revisions(connection) == (HEAD,)
        assert schema_differences(connection) == ()


def test_populated_sqlite_backfills_explicit_legacy_authority_without_operator_inference(authority_migration_engine) -> None:
    engine = authority_migration_engine
    _migrate(engine, PARENT)
    _seed_0013(engine)
    _migrate(engine)
    _assert_populated_authority(engine)


@pytest.mark.parametrize("role", [None, "admin", "Tenant_Viewer", "tenant_viewer ", "*", ""])
def test_sqlite_physically_rejects_missing_or_unknown_membership_role(authority_migration_engine, role) -> None:
    engine = authority_migration_engine
    _migrate(engine, PARENT)
    _seed_0013(engine)
    _migrate(engine)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(
            "UPDATE tenant_memberships SET role=:role WHERE membership_id='membership:authority-1'"
        ), {"role": role})


def test_sqlite_authority_downgrade_is_explicitly_destructive_and_reupgrade_backfills(authority_migration_engine) -> None:
    engine = authority_migration_engine
    _migrate(engine, PARENT)
    _seed_0013(engine)
    _migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE tenant_memberships SET role='tenant_viewer'"))
        connection.execute(text("UPDATE service_principal_permissions SET permissions_json='[\"incident.read\"]', row_version=2"))
        connection.execute(text(
            "INSERT INTO installation_operator_assignments VALUES (:principal, 'active', :now, :now)"
        ), {"principal": HUMAN_A, "now": NOW})
    _migrate(engine, PARENT, down=True)
    assert NEW_TABLES.isdisjoint(inspect(engine).get_table_names())
    assert "role" not in {column["name"] for column in inspect(engine).get_columns("tenant_memberships")}
    with engine.connect() as connection:
        assert current_revisions(connection) == (PARENT,)
        assert connection.scalar(text("SELECT COUNT(*) FROM tenant_memberships")) == 3
        assert connection.scalar(text("SELECT COUNT(*) FROM auth_principals")) == 4
    _migrate(engine)
    _assert_populated_authority(engine)
