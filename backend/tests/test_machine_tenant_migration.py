"""PH-3E real SQLite/PostgreSQL migration, custody and adoption boundaries."""

from argparse import Namespace
import os

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text, event

from app.db.database import Base, init_db
from app.db.domain_ownership import REQUIRED_OWNERSHIP_TABLES
from app.db.schema_management import (
    alembic_config, current_revisions, inspect_schema_authority,
    schema_differences, script_directory, SchemaAuthorityError, verify_database_revision,
)
from test_domain_tenant_migration import TENANT_A, TENANT_B, _seed_tenant, _seed_pre_tenancy_row
from frozen_schema_fixtures import frozen_0007_metadata

HEAD = "0007_machine_tenant_binding"
PARENT = "0006_domain_tenant_enforcement"
MIGRATION = script_directory().get_revision(HEAD).module


@pytest.fixture(params=["sqlite", "postgres"])
def machine_engine(request, tmp_path):
    if request.param == "postgres":
        if not os.getenv("TOPO_TEST_POSTGRES_URL"):
            pytest.skip("set TOPO_TEST_POSTGRES_URL for PostgreSQL 16 proof")
        from test_postgres_runtime_compatibility import _temporary_database
        with _temporary_database("ph3e_migration") as engine:
            yield engine
    else:
        engine = create_engine(f"sqlite:///{(tmp_path / 'machine.db').as_posix()}")
        try:
            yield engine
        finally:
            engine.dispose()


def migrate(engine, revision=HEAD, target=None, *, downgrade=False):
    with engine.begin() as connection:
        config = alembic_config(connection=connection)
        config.get_section(config.config_ini_section)
        config.config_file_name = None
        config.cmd_opts = Namespace(x=[] if target is None else [
            f"legacy_machine_tenant_id={target}"
        ])
        (command.downgrade if downgrade else command.upgrade)(config, revision)


def test_fresh_38_owned_tables_no_defaults_and_downgrade_parity(machine_engine):
    migrate(machine_engine)
    assert len(REQUIRED_OWNERSHIP_TABLES) == 38
    assert len(Base.metadata.tables) == 43
    with machine_engine.connect() as c:
        assert current_revisions(c) == (HEAD,)
        assert schema_differences(c, metadata=frozen_0007_metadata()) == ()
        for name in sorted(REQUIRED_OWNERSHIP_TABLES):
            column = next(x for x in inspect(c).get_columns(name) if x["name"] == "tenant_id")
            assert column["nullable"] is False
            assert column["default"] is None
            assert Base.metadata.tables[name].c.tenant_id.default is None
            assert c.scalar(text(f'SELECT COUNT(*) FROM "{name}" WHERE tenant_id IS NULL')) == 0
        assert c.scalar(text("SELECT COUNT(*) FROM tenants")) == 0
    migrate(machine_engine, PARENT, downgrade=True)
    with pytest.raises(SchemaAuthorityError, match="state=behind"):
        verify_database_revision(machine_engine)
    if machine_engine.dialect.name == "postgresql":
        with pytest.raises(SchemaAuthorityError, match="state=behind"):
            init_db(bind=machine_engine)
    with machine_engine.connect() as c:
        assert not inspect_schema_authority(c).ok
        for name in MIGRATION.MACHINE_TABLES:
            assert "tenant_id" not in {x["name"] for x in inspect(c).get_columns(name)}
        for name in MIGRATION.RESIDUAL_TABLES:
            assert next(x for x in inspect(c).get_columns(name) if x["name"] == "tenant_id")["nullable"]
    migrate(machine_engine)
    with machine_engine.connect() as c:
        assert schema_differences(c, metadata=frozen_0007_metadata()) == ()


@pytest.mark.parametrize("target,status,error", [
    (None, "active", "REQUIRED"), ("tenant:bad", None, "INVALID"),
    (TENANT_A, None, "NOT_FOUND"), (TENANT_A, "disabled", "DISABLED"),
])
def test_rejected_authority_has_no_ddl_backfill_or_stamp(machine_engine, target, status, error):
    migrate(machine_engine, PARENT)
    with machine_engine.begin() as c:
        if status:
            _seed_tenant(c, TENANT_A, status=status)
        _seed_pre_tenancy_row(c, "topo_agents", agent_id="agent:legacy")
    with pytest.raises(RuntimeError, match=f"^LEGACY_MACHINE_TENANT_{error}$"):
        migrate(machine_engine, target=target)
    with machine_engine.connect() as c:
        assert current_revisions(c) == (PARENT,)
        assert "tenant_id" not in {x["name"] for x in inspect(c).get_columns("topo_agents")}
        assert c.scalar(text("SELECT agent_id FROM topo_agents")) == "agent:legacy"


def test_explicit_adoption_two_tenants_preserves_every_owned_row_and_id(machine_engine):
    migrate(machine_engine, PARENT)
    with machine_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        _seed_tenant(c, TENANT_B)
        for name in MIGRATION.MACHINE_TABLES:
            _seed_pre_tenancy_row(c, name)
        for name in MIGRATION.RESIDUAL_TABLES:
            # Independent rows; generated string references do not match any
            # other fixture's PK. No fabricated ownership relationships.
            _seed_pre_tenancy_row(c, name, tenant_id=None)
        _seed_pre_tenancy_row(c, "signals", signal_id="signal:already-b", tenant_id=TENANT_B)
        before = {
            name: c.execute(text(f'SELECT * FROM "{name}"')).mappings().all()
            for name in REQUIRED_OWNERSHIP_TABLES
        }
    migrate(machine_engine, target=TENANT_A)
    with machine_engine.connect() as c:
        for name in REQUIRED_OWNERSHIP_TABLES:
            primary = inspect(c).get_pk_constraint(name)["constrained_columns"][0]
            after = {r[primary]: dict(r) for r in c.execute(text(f'SELECT * FROM "{name}"')).mappings()}
            for row in before[name]:
                actual = after[row[primary]]
                assert actual["tenant_id"] == (row.get("tenant_id") or TENANT_A)
                assert {k: v for k, v in actual.items() if k != "tenant_id"} == {
                    k: v for k, v in row.items() if k != "tenant_id"
                }
        assert c.scalar(text("SELECT COUNT(*) FROM tenants")) == 2
        assert c.scalar(text("SELECT COUNT(*) FROM tenant_memberships")) == 0


@pytest.mark.parametrize("child_owned", [False, True])
def test_conflicts_in_both_reference_directions_fail_before_ddl(machine_engine, child_owned):
    migrate(machine_engine, PARENT)
    with machine_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        _seed_tenant(c, TENANT_B)
        _seed_pre_tenancy_row(c, "topology_snapshots", snapshot_id="snapshot:parent",
                            tenant_id=None if child_owned else TENANT_B)
        _seed_pre_tenancy_row(c, "incidents", topology_snapshot_id="snapshot:parent",
                            tenant_id=TENANT_B if child_owned else None)
    with pytest.raises(RuntimeError, match="^LEGACY_MACHINE_TENANT_CONFLICT$"):
        migrate(machine_engine, target=TENANT_A)
    with machine_engine.connect() as c:
        assert current_revisions(c) == (PARENT,)
        assert "tenant_id" not in {x["name"] for x in inspect(c).get_columns("topo_agents")}


def test_machine_parent_conflict_rejects_incorrect_assertion(machine_engine):
    migrate(machine_engine, PARENT)
    with machine_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        _seed_tenant(c, TENANT_B)
        _seed_pre_tenancy_row(c, "topo_agents", agent_id="agent:foreign")
        _seed_pre_tenancy_row(c, "runtime_sensors", agent_id="agent:foreign", tenant_id=TENANT_B)
    with pytest.raises(RuntimeError, match="^LEGACY_MACHINE_TENANT_CONFLICT$"):
        migrate(machine_engine, target=TENANT_A)
    migrate(machine_engine, target=TENANT_B)
    with machine_engine.connect() as c:
        assert c.scalar(text("SELECT tenant_id FROM topo_agents")) == TENANT_B


def test_residual_only_data_requires_explicit_adoption(machine_engine):
    migrate(machine_engine, PARENT)
    with machine_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        _seed_pre_tenancy_row(c, "signals", tenant_id=None)
    with pytest.raises(RuntimeError, match="^LEGACY_MACHINE_TENANT_REQUIRED$"):
        migrate(machine_engine)
    migrate(machine_engine, target=TENANT_A)
    with machine_engine.connect() as c:
        assert c.scalar(text("SELECT tenant_id FROM signals")) == TENANT_A


def test_postgres_failure_after_backfill_rolls_back_ddl_data_and_stamp(machine_engine):
    if machine_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL transactional DDL proof; SQLite has pre-DDL rejection gates")
    migrate(machine_engine, PARENT)
    with machine_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        _seed_pre_tenancy_row(c, "topo_agents", agent_id="agent:rollback")
        _seed_pre_tenancy_row(c, "signals", tenant_id=None)

    def reject_closure(_conn, _cursor, statement, *_):
        if "ALTER TABLE topology_snapshots" in statement and "SET NOT NULL" in statement:
            raise RuntimeError("synthetic closure failure")

    event.listen(machine_engine, "before_cursor_execute", reject_closure)
    try:
        with pytest.raises(RuntimeError, match="synthetic closure failure"):
            migrate(machine_engine, target=TENANT_A)
    finally:
        event.remove(machine_engine, "before_cursor_execute", reject_closure)
    with machine_engine.connect() as c:
        assert current_revisions(c) == (PARENT,)
        assert "tenant_id" not in {x["name"] for x in inspect(c).get_columns("topo_agents")}
        assert c.scalar(text("SELECT tenant_id FROM signals")) is None
    migrate(machine_engine, target=TENANT_A)
