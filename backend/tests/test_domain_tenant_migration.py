from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from app.db.database import Base
from app.db.schema_management import (
    alembic_config,
    current_revisions,
    inspect_schema_authority,
    schema_differences,
    script_directory,
)


TENANT_A = "tenant:11111111-1111-4111-8111-111111111111"
TENANT_B = "tenant:22222222-2222-4222-8222-222222222222"
UNKNOWN_TENANT = "tenant:33333333-3333-4333-8333-333333333333"
TENANT_FOUNDATION_REVISION = "0004_tenant_foundation"
DOMAIN_OWNERSHIP_REVISION = "0005_domain_tenant_ownership"
PH3E_MACHINE_AUTHORITY = {
    "agent_enrollment_tokens",
    "topo_agents",
    "change_sources",
}
SECURITY_GLOBAL = {"auth_sessions", "auth_api_credentials"}
TENANT_CONTROL = {
    "tenants",
    "tenant_memberships",
    "service_api_tenant_bindings",
}


def _revision_module():
    return script_directory().get_revision(DOMAIN_OWNERSHIP_REVISION).module


PH3C_DOMAIN = set(_revision_module().PH3C_DOMAIN_TABLES)


@pytest.fixture
def migration_engine(tmp_path: Path) -> Engine:
    database_path = tmp_path / "domain-tenant-migration.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


def _migration_config(
    connection: Connection,
    *,
    legacy_tenant_id: str | None = None,
):
    config = alembic_config(connection=connection)
    arguments = (
        []
        if legacy_tenant_id is None
        else [f"legacy_tenant_id={legacy_tenant_id}"]
    )
    config.cmd_opts = Namespace(x=arguments)
    return config


def _upgrade(
    engine: Engine,
    revision: str = "head",
    *,
    legacy_tenant_id: str | None = None,
) -> None:
    with engine.begin() as connection:
        command.upgrade(
            _migration_config(
                connection,
                legacy_tenant_id=legacy_tenant_id,
            ),
            revision,
        )


def _downgrade(engine: Engine, revision: str) -> None:
    with engine.begin() as connection:
        command.downgrade(_migration_config(connection), revision)


def _seed_tenant(
    connection: Connection,
    tenant_id: str,
    *,
    status: str = "active",
) -> None:
    connection.execute(
        text(
            "INSERT INTO tenants "
            "(tenant_id, display_name, status, created_at, updated_at, "
            "created_by_subject) VALUES "
            "(:tenant_id, :display_name, :status, :created_at, :updated_at, "
            ":created_by_subject)"
        ),
        {
            "tenant_id": tenant_id,
            "display_name": f"Fixture {tenant_id[-1]}",
            "status": status,
            "created_at": "2026-08-30T00:00:00+00:00",
            "updated_at": "2026-08-30T00:00:00+00:00",
            "created_by_subject": "test:ph3c-operator",
        },
    )


def _string_value(table_name: str, column: sa.Column) -> str:
    if column.name.endswith("_json"):
        return "{}"
    if column.name.endswith("_at"):
        return "2026-08-30T00:00:00+00:00"
    value = f"legacy-{table_name}-{column.name}"
    length = getattr(column.type, "length", None)
    if length is not None:
        return value[:length]
    return value


def _seed_pre_tenancy_row(
    connection: Connection,
    table_name: str,
    **overrides,
) -> dict[str, object]:
    table = sa.Table(
        table_name,
        MetaData(),
        autoload_with=connection,
    )
    values: dict[str, object] = {}
    for column in table.columns:
        if column.name in overrides:
            values[column.name] = overrides[column.name]
        elif column.nullable or column.server_default is not None:
            continue
        elif isinstance(column.type, sa.Boolean):
            values[column.name] = False
        elif isinstance(column.type, sa.Integer):
            values[column.name] = 1
        elif isinstance(column.type, sa.Float):
            values[column.name] = 0.5
        elif isinstance(column.type, (sa.String, sa.Text)):
            values[column.name] = _string_value(table_name, column)
        else:  # pragma: no cover - keeps new unsupported schema types explicit
            raise AssertionError(
                f"Unsupported fixture type {column.type} for "
                f"{table_name}.{column.name}"
            )
    values.update(overrides)
    connection.execute(table.insert().values(**values))
    return values


def _seed_representative_domain(connection: Connection) -> dict[str, str]:
    overrides: dict[str, dict[str, object]] = {
        "topology_snapshots": {"snapshot_id": "snapshot:legacy"},
        "signals": {
            "signal_id": "signal:legacy",
            "involved_entity_id": "entity:legacy",
        },
        "incidents": {
            "incident_id": "incident:legacy",
            "topology_snapshot_id": "snapshot:legacy",
            "primary_signal_id": "signal:legacy",
        },
        "causal_analyses": {
            "analysis_id": "causal-analysis:legacy",
            "incident_id": "incident:legacy",
        },
        "change_events": {"event_id": "change-event:legacy"},
        "change_entity_links": {
            "link_id": "change-link:legacy",
            "event_id": "change-event:legacy",
            "entity_id": "entity:legacy",
            "snapshot_id": "snapshot:legacy",
        },
        "ownership_mappings": {"ownership_id": "ownership:legacy"},
        "post_incident_reports": {
            "report_id": "report:legacy",
            "incident_id": "incident:legacy",
        },
    }
    identities: dict[str, str] = {}
    for table_name in sorted(PH3C_DOMAIN):
        values = _seed_pre_tenancy_row(
            connection,
            table_name,
            **overrides.get(table_name, {}),
        )
        primary_key = inspect(connection).get_pk_constraint(table_name)[
            "constrained_columns"
        ][0]
        identities[table_name] = str(values[primary_key])
    return identities


def test_domain_table_partition_and_nullable_orm_ownership_are_exact() -> None:
    all_tables = set(Base.metadata.tables)
    assert len(all_tables) == 43
    assert len(PH3C_DOMAIN) == 35
    assert len(PH3E_MACHINE_AUTHORITY) == 3
    assert len(SECURITY_GLOBAL) == 2
    assert len(TENANT_CONTROL) == 3
    assert (
        PH3C_DOMAIN
        | PH3E_MACHINE_AUTHORITY
        | SECURITY_GLOBAL
        | TENANT_CONTROL
    ) == all_tables
    assert not any(
        left & right
        for left, right in (
            (PH3C_DOMAIN, PH3E_MACHINE_AUTHORITY),
            (PH3C_DOMAIN, SECURITY_GLOBAL),
            (PH3C_DOMAIN, TENANT_CONTROL),
            (PH3E_MACHINE_AUTHORITY, SECURITY_GLOBAL),
            (PH3E_MACHINE_AUTHORITY, TENANT_CONTROL),
            (SECURITY_GLOBAL, TENANT_CONTROL),
        )
    )

    for table_name in PH3C_DOMAIN:
        column = Base.metadata.tables[table_name].c.tenant_id
        assert column.nullable is True
        assert column.type.length == 255
        assert column.default is None
        assert column.server_default is None
        assert any(
            index.name == f"ix_{table_name}_tenant_id"
            for index in Base.metadata.tables[table_name].indexes
        )
    for table_name in PH3E_MACHINE_AUTHORITY | SECURITY_GLOBAL:
        assert "tenant_id" not in Base.metadata.tables[table_name].c


def test_fresh_sqlite_requires_no_legacy_tenant_and_creates_none(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)

    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (DOMAIN_OWNERSHIP_REVISION,)
        assert connection.scalar(text("SELECT COUNT(*) FROM tenants")) == 0
        assert schema_differences(connection) == ()
        assert inspect_schema_authority(connection).ok


def test_populated_sqlite_requires_explicit_legacy_tenant_before_ddl(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine, TENANT_FOUNDATION_REVISION)
    with migration_engine.begin() as connection:
        _seed_pre_tenancy_row(
            connection,
            "topology_snapshots",
            snapshot_id="snapshot:requires-tenant",
        )

    with pytest.raises(RuntimeError, match="LEGACY_TENANT_REQUIRED"):
        _upgrade(migration_engine)

    inspector = inspect(migration_engine)
    assert "tenant_id" not in {
        column["name"]
        for column in inspector.get_columns("topology_snapshots")
    }
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (TENANT_FOUNDATION_REVISION,)


@pytest.mark.parametrize(
    ("tenant_id", "tenant_status", "error"),
    [
        ("tenant:not-valid", None, "LEGACY_TENANT_INVALID"),
        (UNKNOWN_TENANT, None, "LEGACY_TENANT_NOT_FOUND"),
        (TENANT_A, "disabled", "LEGACY_TENANT_DISABLED"),
    ],
)
def test_populated_sqlite_rejects_invalid_backfill_authority_before_ddl(
    migration_engine: Engine,
    tenant_id: str,
    tenant_status: str | None,
    error: str,
) -> None:
    _upgrade(migration_engine, TENANT_FOUNDATION_REVISION)
    with migration_engine.begin() as connection:
        if tenant_status is not None:
            _seed_tenant(connection, tenant_id, status=tenant_status)
        _seed_pre_tenancy_row(
            connection,
            "topology_snapshots",
            snapshot_id=f"snapshot:{error.lower()}",
        )

    with pytest.raises(RuntimeError, match=error):
        _upgrade(
            migration_engine,
            legacy_tenant_id=tenant_id,
        )

    inspector = inspect(migration_engine)
    assert "tenant_id" not in {
        column["name"]
        for column in inspector.get_columns("topology_snapshots")
    }
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == (TENANT_FOUNDATION_REVISION,)


def test_two_tenant_sqlite_backfill_uses_only_explicit_target_and_preserves_ids(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine, TENANT_FOUNDATION_REVISION)
    with migration_engine.begin() as connection:
        _seed_tenant(connection, TENANT_A)
        _seed_tenant(connection, TENANT_B)
        identities_before = _seed_representative_domain(connection)

    _upgrade(migration_engine, legacy_tenant_id=TENANT_B)

    with migration_engine.connect() as connection:
        for table_name, identity in identities_before.items():
            table = sa.Table(
                table_name,
                MetaData(),
                autoload_with=connection,
            )
            primary_key = next(iter(table.primary_key.columns))
            row = connection.execute(
                sa.select(primary_key, table.c.tenant_id)
            ).one()
            assert str(row[0]) == identity
            assert row[1] == TENANT_B
            assert connection.scalar(
                sa.select(sa.func.count()).select_from(table).where(
                    table.c.tenant_id.is_(None)
                )
            ) == 0
            assert connection.scalar(
                sa.select(sa.func.count()).select_from(table).where(
                    table.c.tenant_id == TENANT_A
                )
            ) == 0

        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM incidents "
                "WHERE incident_id = 'incident:legacy' "
                "AND topology_snapshot_id = 'snapshot:legacy' "
                "AND tenant_id = :tenant_id"
            ),
            {"tenant_id": TENANT_B},
        ) == 1
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM causal_analyses "
                "WHERE incident_id = 'incident:legacy' "
                "AND tenant_id = :tenant_id"
            ),
            {"tenant_id": TENANT_B},
        ) == 1
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM change_entity_links "
                "WHERE event_id = 'change-event:legacy' "
                "AND snapshot_id = 'snapshot:legacy' "
                "AND tenant_id = :tenant_id"
            ),
            {"tenant_id": TENANT_B},
        ) == 1
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM post_incident_reports "
                "WHERE incident_id = 'incident:legacy' "
                "AND tenant_id = :tenant_id"
            ),
            {"tenant_id": TENANT_B},
        ) == 1
        assert schema_differences(connection) == ()


def test_sqlite_downgrade_and_explicit_reupgrade_preserve_logical_ids(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine, TENANT_FOUNDATION_REVISION)
    with migration_engine.begin() as connection:
        _seed_tenant(connection, TENANT_B)
        _seed_pre_tenancy_row(
            connection,
            "topology_snapshots",
            snapshot_id="snapshot:downgrade",
        )

    _upgrade(migration_engine, legacy_tenant_id=TENANT_B)
    _downgrade(migration_engine, TENANT_FOUNDATION_REVISION)
    assert "tenant_id" not in {
        column["name"]
        for column in inspect(migration_engine).get_columns(
            "topology_snapshots"
        )
    }

    _upgrade(migration_engine, legacy_tenant_id=TENANT_B)
    with migration_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT snapshot_id, tenant_id FROM topology_snapshots"
            )
        ).one()
        assert row == ("snapshot:downgrade", TENANT_B)
        assert inspect_schema_authority(connection).ok


def test_parallel_tenant_unique_rules_preserve_global_compatibility_rules(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)
    revision_module = _revision_module()
    inspector = inspect(migration_engine)

    for table_name, definitions in (
        revision_module.TENANT_SCOPED_UNIQUE_CONSTRAINTS.items()
    ):
        actual = {
            item["name"]: tuple(item["column_names"])
            for item in inspector.get_unique_constraints(table_name)
        }
        for name, columns in definitions:
            assert actual[name] == columns

    for table_name, definitions in (
        revision_module.TENANT_SCOPED_UNIQUE_INDEXES.items()
    ):
        actual = {
            item["name"]: (
                tuple(item["column_names"]),
                bool(item["unique"]),
            )
            for item in inspector.get_indexes(table_name)
        }
        for name, columns in definitions:
            assert actual[name] == (columns, True)

    assert any(
        item["name"] == "uq_change_event_entity_link"
        for item in inspector.get_unique_constraints("change_entity_links")
    )
    assert any(
        item["name"] == "ix_change_events_event_fingerprint"
        and item["unique"]
        for item in inspector.get_indexes("change_events")
    )


def test_transitional_new_domain_row_may_still_have_null_tenant(
    migration_engine: Engine,
) -> None:
    _upgrade(migration_engine)
    with migration_engine.begin() as connection:
        _seed_pre_tenancy_row(
            connection,
            "topology_snapshots",
            snapshot_id="snapshot:transitional-null",
        )
    with migration_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM topology_snapshots "
                "WHERE tenant_id IS NULL"
            )
        ) == 1
