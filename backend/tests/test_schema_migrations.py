from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db import models  # noqa: F401
from app.db.database import Base, _synchronous_database_url, init_db
from app.db.schema_management import (
    SchemaAuthorityError,
    adopt_current_schema,
    alembic_config,
    current_revisions,
    expected_head,
    inspect_schema_authority,
    schema_differences,
    script_directory,
    verify_database_revision,
)


DOMAIN_TABLE_COUNT = 40
DOMAIN_COLUMN_COUNT = 715
EXPECTED_HEAD = "0003_auth_api_credentials"
BASELINE_REVISION = "0001_current_schema"
SESSION_REVISION = "0002_auth_sessions"
BASELINE_SHA256 = (
    "b02368d0d15445417a5ede9445a267f34da9d50dddb181870d972bd23124b8a6"
)
LEGACY_TABLES = {
    "change_dead_letters",
    "integration_deliveries",
    "integrations",
}


@pytest.fixture
def migration_engine(tmp_path: Path) -> Engine:
    database_path = tmp_path / "migration.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


def _upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection=connection), revision)


def _downgrade(engine: Engine, revision: str = "base") -> None:
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection=connection), revision)


def _domain_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_alembic_has_exactly_one_head() -> None:
    assert script_directory().get_heads() == [EXPECTED_HEAD]
    assert expected_head() == EXPECTED_HEAD


def test_empty_sqlite_upgrade_has_exact_schema_parity(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)

    inspector = inspect(migration_engine)
    domain_tables = _domain_tables(migration_engine)
    assert domain_tables == set(Base.metadata.tables)
    assert len(domain_tables) == DOMAIN_TABLE_COUNT
    assert sum(len(inspector.get_columns(table)) for table in domain_tables) == (
        DOMAIN_COLUMN_COUNT
    )
    assert sum(
        len(inspector.get_pk_constraint(table)["constrained_columns"])
        for table in domain_tables
    ) == DOMAIN_TABLE_COUNT
    assert sum(len(inspector.get_foreign_keys(table)) for table in domain_tables) == 0
    assert sum(
        column["default"] is not None
        for table in domain_tables
        for column in inspector.get_columns(table)
    ) == 0

    named_multi_column_uniques = [
        constraint
        for table in domain_tables
        for constraint in inspector.get_unique_constraints(table)
        if constraint["name"] is not None
        and len(constraint["column_names"]) > 1
    ]
    indexes = [
        index
        for table in domain_tables
        for index in inspector.get_indexes(table)
    ]
    assert len(named_multi_column_uniques) == 10
    assert sum(bool(index["unique"]) for index in indexes) == 9
    assert len(indexes) == 301

    with migration_engine.connect() as connection:
        assert schema_differences(connection) == ()
        report = inspect_schema_authority(connection)
    assert report.ok


def test_migration_excludes_legacy_tables_and_includes_current_drift_fixes(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)
    inspector = inspect(migration_engine)

    assert LEGACY_TABLES.isdisjoint(inspector.get_table_names())
    dead_letter_columns = {
        column["name"]
        for column in inspector.get_columns("change_source_dead_letters")
    }
    assert {"last_attempt_at", "replayed_at"} <= dead_letter_columns

    delivery_indexes = {
        index["name"]
        for index in inspector.get_indexes("change_source_deliveries")
    }
    assert {
        "ix_change_source_deliveries_payload_sha256",
        "ix_change_source_deliveries_received_at",
    } <= delivery_indexes


def test_revision_is_static_and_does_not_import_application_models() -> None:
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0001_current_schema_baseline.py"
    )
    source = revision_path.read_text(encoding="utf-8")

    assert hashlib.sha256(revision_path.read_bytes()).hexdigest() == BASELINE_SHA256
    assert "from app" not in source
    assert "Base.metadata" not in source
    assert 'revision: str = "0001_current_schema"' in source
    assert "down_revision: str | Sequence[str] | None = None" in source


def test_auth_session_revision_is_one_narrow_static_addition() -> None:
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0002_auth_sessions.py"
    )
    source = revision_path.read_text(encoding="utf-8")

    assert "from app" not in source
    assert "Base.metadata" not in source
    assert 'revision: str = "0002_auth_sessions"' in source
    assert (
        'down_revision: str | Sequence[str] | None = "0001_current_schema"'
        in source
    )
    assert source.count("op.create_table(") == 1
    assert '"auth_sessions"' in source
    for forbidden in (
        "tenant_id",
        "auth_api_credentials",
        "users",
        "passwords",
        "oidc",
    ):
        assert forbidden not in source.lower()


def test_api_credential_revision_is_one_narrow_static_addition() -> None:
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0003_auth_api_credentials.py"
    )
    source = revision_path.read_text(encoding="utf-8")

    assert "from app" not in source
    assert "Base.metadata" not in source
    assert 'revision: str = "0003_auth_api_credentials"' in source
    assert (
        'down_revision: str | Sequence[str] | None = "0002_auth_sessions"'
        in source
    )
    assert source.count("op.create_table(") == 1
    assert '"auth_api_credentials"' in source
    for forbidden in ("tenant_id", "password", "oidc", "provider_secret"):
        assert forbidden not in source.lower()


def test_sqlite_upgrade_from_0001_through_0002_to_0003(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine, BASELINE_REVISION)
    baseline_tables = _domain_tables(migration_engine)
    assert baseline_tables == set(Base.metadata.tables) - {
        "auth_sessions",
        "auth_api_credentials",
    }
    assert len(baseline_tables) == 38
    baseline_columns = sum(
        len(inspect(migration_engine).get_columns(table))
        for table in baseline_tables
    )
    assert baseline_columns == 687

    _upgrade(migration_engine, SESSION_REVISION)
    assert _domain_tables(migration_engine) == set(Base.metadata.tables) - {
        "auth_api_credentials"
    }

    _upgrade(migration_engine)
    assert _domain_tables(migration_engine) == set(Base.metadata.tables)
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (EXPECTED_HEAD,)
        assert schema_differences(connection) == ()


def test_disposable_0003_downgrade_preserves_0002_schema(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)
    _downgrade(migration_engine, SESSION_REVISION)

    assert _domain_tables(migration_engine) == set(Base.metadata.tables) - {
        "auth_api_credentials"
    }
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (SESSION_REVISION,)


def test_disposable_0002_downgrade_preserves_0001_domain_schema(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine, SESSION_REVISION)
    _downgrade(migration_engine, BASELINE_REVISION)

    assert _domain_tables(migration_engine) == set(Base.metadata.tables) - {
        "auth_sessions",
        "auth_api_credentials",
    }
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (BASELINE_REVISION,)


def test_disposable_downgrade_and_reupgrade(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)
    _downgrade(migration_engine)

    assert _domain_tables(migration_engine) == set()
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ()

    _upgrade(migration_engine)
    with migration_engine.connect() as connection:
        assert inspect_schema_authority(connection).ok


def test_exact_existing_schema_can_be_explicitly_adopted(
    migration_engine: Engine,
) -> None:
    Base.metadata.create_all(migration_engine)
    before_tables = _domain_tables(migration_engine)

    with migration_engine.begin() as connection:
        before = inspect_schema_authority(connection)
        assert before.schema_matches
        assert before.current_revisions == ()
        after = adopt_current_schema(connection)

    assert after.ok
    assert _domain_tables(migration_engine) == before_tables


def test_drifted_existing_schema_is_rejected_without_stamp_or_repair(
    migration_engine: Engine,
) -> None:
    Base.metadata.create_all(migration_engine)
    legacy = MetaData()
    sa.Table(
        "integrations",
        legacy,
        sa.Column("integration_id", sa.String(255), primary_key=True),
    ).create(migration_engine)

    with migration_engine.begin() as connection:
        with pytest.raises(SchemaAuthorityError, match="not an exact match"):
            adopt_current_schema(connection)

    inspector = inspect(migration_engine)
    assert "integrations" in inspector.get_table_names()
    assert "alembic_version" not in inspector.get_table_names()


def test_schema_verifier_reports_structural_drift_deterministically(
    migration_engine: Engine,
) -> None:
    actual = MetaData()
    sa.Table(
        "parents",
        actual,
        sa.Column("id", sa.String(12), primary_key=True),
    )
    sa.Table(
        "children",
        actual,
        sa.Column("id", sa.String(12), nullable=True),
        sa.Column("parent_id", sa.String(12), nullable=True),
        sa.Column("extra", sa.Text(), nullable=True),
    )
    actual.create_all(migration_engine)

    expected = MetaData()
    sa.Table(
        "parents",
        expected,
        sa.Column("id", sa.String(10), primary_key=True),
    )
    sa.Table(
        "children",
        expected,
        sa.Column("id", sa.String(10), primary_key=True, nullable=False),
        sa.Column(
            "parent_id",
            sa.String(10),
            sa.ForeignKey("parents.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("parent_id", name="uq_children_parent"),
        sa.Index("ix_children_parent", "parent_id"),
    )

    with migration_engine.connect() as connection:
        first = schema_differences(connection, metadata=expected)
        second = schema_differences(connection, metadata=expected)

    assert first == second
    kinds = {difference.kind for difference in first}
    assert "remove_column" in kinds
    assert "modify_type" in kinds
    assert "modify_nullable" in kinds
    assert "modify_primary_key" in kinds
    assert "add_index" in kinds
    assert "add_constraint" in kinds
    assert "add_fk" in kinds


def test_production_revision_verifier_accepts_only_expected_head(
    migration_engine: Engine,
) -> None:
    with pytest.raises(SchemaAuthorityError, match="state=missing"):
        verify_database_revision(migration_engine)

    Base.metadata.create_all(migration_engine)
    with pytest.raises(SchemaAuthorityError, match="state=missing"):
        verify_database_revision(migration_engine)

    with migration_engine.begin() as connection:
        adopt_current_schema(connection)
    verify_database_revision(migration_engine)

    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE alembic_version "
                "SET version_num = 'future_unknown_revision'"
            )
        )
    with pytest.raises(SchemaAuthorityError, match="ahead-or-unknown") as exc:
        verify_database_revision(migration_engine)
    assert "sqlite" not in str(exc.value).lower()
    assert "TOPO_DATABASE_URL" not in str(exc.value)


def test_production_revision_verifier_rejects_multiple_revisions(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)
    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('another_revision')"
            )
        )

    with pytest.raises(SchemaAuthorityError, match="state=multiple"):
        verify_database_revision(migration_engine)


def test_sqlite_init_remains_metadata_created_and_unstamped(
    migration_engine: Engine,
) -> None:
    init_db(bind=migration_engine)

    inspector = inspect(migration_engine)
    assert _domain_tables(migration_engine) == set(Base.metadata.tables)
    assert "alembic_version" not in inspector.get_table_names()


def test_non_sqlite_init_verifies_revision_without_create_all() -> None:
    production_engine = MagicMock()
    production_engine.dialect.name = "postgresql"

    with (
        patch.object(Base.metadata, "create_all") as create_all,
        patch(
            "app.db.schema_management.verify_database_revision"
        ) as verify_revision,
    ):
        init_db(bind=production_engine)

    create_all.assert_not_called()
    verify_revision.assert_called_once_with(production_engine)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "postgresql://user:password@db.example/topo",
            "postgresql+psycopg://user:password@db.example/topo",
        ),
        (
            "postgres://user:password@db.example/topo",
            "postgresql+psycopg://user:password@db.example/topo",
        ),
        (
            "postgresql+psycopg://user:password@db.example/topo",
            "postgresql+psycopg://user:password@db.example/topo",
        ),
        ("sqlite:///:memory:", "sqlite:///:memory:"),
    ],
)
def test_database_url_selects_psycopg_without_changing_other_urls(
    value: str,
    expected: str,
) -> None:
    assert _synchronous_database_url(value) == expected


def test_python_defaults_never_become_server_defaults(
    migration_engine: Engine,
) -> None:
    assert sum(column.default is not None for table in Base.metadata.tables.values() for column in table.columns) > 0
    assert all(
        column.server_default is None
        for table in Base.metadata.tables.values()
        for column in table.columns
    )

    _upgrade(migration_engine)
    inspector = inspect(migration_engine)
    assert all(
        column["default"] is None
        for table in _domain_tables(migration_engine)
        for column in inspector.get_columns(table)
    )
