"""Disposable SQLite migration proof for PH-5D."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db.database import Base
from app.db.schema_management import (
    alembic_config,
    current_revisions,
    schema_differences,
    script_directory,
)
from test_minimum_authority_migrations import _seed_0013


PARENT = "0014_min_authority"
HEAD = "0015_security_audit"
TABLE = "security_audit_events"


def _migrate(engine, target: str, *, down: bool = False) -> None:
    with engine.begin() as connection:
        (command.downgrade if down else command.upgrade)(
            alembic_config(connection=connection), target
        )


@pytest.fixture()
def migration_engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'security-audit.db').as_posix()}"
    )
    try:
        yield engine
    finally:
        engine.dispose()


def test_0015_is_the_only_head_and_creates_exactly_one_table() -> None:
    scripts = script_directory()
    assert scripts.get_heads() == [HEAD]
    revision = scripts.get_revision(HEAD)
    assert revision.down_revision == PARENT
    assert Path(revision.path).name == "0015_security_admin_audit.py"
    source = Path(revision.path).read_text(encoding="utf-8")
    assert "from app" not in source
    assert "Base.metadata" not in source
    assert source.count("op.create_table(") == 1


def test_fresh_sqlite_migration_matches_exact_orm_schema(migration_engine) -> None:
    _migrate(migration_engine, PARENT)
    before = set(inspect(migration_engine).get_table_names())
    _migrate(migration_engine, HEAD)
    inspector = inspect(migration_engine)
    assert set(inspector.get_table_names()) - before == {TABLE}
    assert [item["name"] for item in inspector.get_columns(TABLE)] == [
        "audit_event_id", "occurred_at", "actor_principal_id", "actor_kind",
        "actor_reference", "authentication_type", "authority_kind", "tenant_id",
        "action", "permissions_json", "resource_type", "resource_id", "result",
        "reason_code", "request_id",
    ]
    assert len(Base.metadata.tables) == 50
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (HEAD,)
        assert schema_differences(connection) == ()


def test_populated_sqlite_upgrade_preserves_authority_and_starts_empty(
    migration_engine,
) -> None:
    _migrate(migration_engine, "0013_principal_enforce")
    _seed_0013(migration_engine)
    _migrate(migration_engine, PARENT)
    with migration_engine.connect() as connection:
        before = {
            table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            for table in (
                "auth_principals", "tenant_memberships",
                "service_principal_permissions", "installation_operator_assignments",
                "auth_api_credentials",
            )
        }
    _migrate(migration_engine, HEAD)
    with migration_engine.connect() as connection:
        after = {
            table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            for table in before
        }
        assert before == after
        assert connection.scalar(text(f"SELECT COUNT(*) FROM {TABLE}")) == 0


def test_sqlite_downgrade_is_destructive_and_reupgrade_is_empty(migration_engine) -> None:
    _migrate(migration_engine, HEAD)
    with migration_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO security_audit_events VALUES ("
            "'audit:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', "
            "'2026-09-08T00:00:00+00:00', NULL, 'local_operator', NULL, "
            "'local_operator_boundary', 'local_operator', NULL, "
            "'installation_secret.inspected', '[]', 'secret_record', 'openai', "
            "'allowed', 'completed', NULL)"
        ))
    _migrate(migration_engine, PARENT, down=True)
    assert TABLE not in inspect(migration_engine).get_table_names()
    _migrate(migration_engine, HEAD)
    with migration_engine.connect() as connection:
        assert connection.scalar(text(f"SELECT COUNT(*) FROM {TABLE}")) == 0
