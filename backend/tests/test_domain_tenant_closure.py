"""0006 no-assignment preflight and exact physical ownership closure."""

import os

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.database import Base
from app.db.domain_ownership import REQUIRED_OWNERSHIP_TABLES, MACHINE_DEPENDENT_WRITERS
from app.db.schema_management import (
    current_revisions,
    inspect_schema_authority,
    schema_differences,
    script_directory,
)
from test_domain_tenant_migration import (
    PH3C_DOMAIN,
    TENANT_A,
    _upgrade,
    _downgrade,
    _seed_pre_tenancy_row,
    _seed_tenant,
)

REVISION = "0006_domain_tenant_enforcement"
PARENT = "0005_domain_tenant_ownership"


@pytest.fixture(params=["sqlite", "postgres"])
def closure_engine(request, tmp_path):
    if request.param == "postgres":
        if not os.getenv("TOPO_TEST_POSTGRES_URL"):
            pytest.skip("set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16")
        from test_postgres_runtime_compatibility import _temporary_database

        with _temporary_database("ph3d_closure") as engine:
            yield engine
    else:
        engine = create_engine(f"sqlite:///{(tmp_path / 'closure.db').as_posix()}")
        try:
            yield engine
        finally:
            engine.dispose()


def test_inventory_has_no_ambiguous_writer_or_default():
    residual = set(MACHINE_DEPENDENT_WRITERS)
    assert len(REQUIRED_OWNERSHIP_TABLES) == 19
    assert len(residual) == 16
    assert REQUIRED_OWNERSHIP_TABLES | residual == PH3C_DOMAIN
    assert not REQUIRED_OWNERSHIP_TABLES & residual
    revision = script_directory().get_revision(REVISION).module
    assert set(revision.REQUIRED_OWNERSHIP_TABLES) == REQUIRED_OWNERSHIP_TABLES
    assert script_directory().get_heads() == [REVISION]
    for name in PH3C_DOMAIN:
        column = Base.metadata.tables[name].c.tenant_id
        assert column.nullable is (name in residual)
        assert column.default is None and column.server_default is None


def test_closure_fresh_upgrade_downgrade_and_parity(closure_engine):
    _upgrade(closure_engine, PARENT)
    with closure_engine.connect() as connection:
        assert not inspect_schema_authority(connection).ok
    _upgrade(closure_engine)
    with closure_engine.connect() as connection:
        assert current_revisions(connection) == (REVISION,)
        assert schema_differences(connection) == ()
        assert connection.scalar(text("SELECT COUNT(*) FROM tenants")) == 0
        inspector = inspect(connection)
        for name in PH3C_DOMAIN:
            column = next(
                c for c in inspector.get_columns(name) if c["name"] == "tenant_id"
            )
            assert column["nullable"] is (name not in REQUIRED_OWNERSHIP_TABLES)
    _downgrade(closure_engine, PARENT)
    with closure_engine.connect() as connection:
        for name in PH3C_DOMAIN:
            assert next(
                c
                for c in inspect(connection).get_columns(name)
                if c["name"] == "tenant_id"
            )["nullable"]
    _upgrade(closure_engine)
    with closure_engine.connect() as connection:
        assert schema_differences(connection) == ()


@pytest.mark.parametrize("table_name", sorted(REQUIRED_OWNERSHIP_TABLES))
def test_null_preflight_never_assigns_or_stamps(closure_engine, table_name):
    _upgrade(closure_engine, PARENT)
    with closure_engine.begin() as connection:
        _seed_tenant(connection, TENANT_A)
        _seed_pre_tenancy_row(connection, table_name, tenant_id=None)
    with pytest.raises(
        RuntimeError, match=f"TENANT_OWNERSHIP_NULL_ROWS_PRESENT: {table_name}=1"
    ):
        # A legacy argument belongs to 0005 and cannot assign rows in 0006.
        _upgrade(closure_engine, legacy_tenant_id=TENANT_A)
    with closure_engine.connect() as connection:
        assert current_revisions(connection) == (PARENT,)
        table = Base.metadata.tables[table_name]
        assert (
            connection.scalar(table.select().with_only_columns(table.c.tenant_id))
            is None
        )
        for name in REQUIRED_OWNERSHIP_TABLES:
            assert next(
                c
                for c in inspect(connection).get_columns(name)
                if c["name"] == "tenant_id"
            )["nullable"]
