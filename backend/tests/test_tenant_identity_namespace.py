"""PH-3F real-engine namespace/collision and migration acceptance."""

from collections import Counter
import os

import pytest
from alembic import command
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db import models
from app.db.domain_ownership import REQUIRED_OWNERSHIP_TABLES
from app.db.tenant_identity import (
    TENANT_LOCAL_PRIMARY_KEYS, GLOBAL_AUTH_LOCATORS, GLOBAL_RANDOM_STORAGE_KEYS,
)
from app.db.schema_management import (
    alembic_config, schema_differences, current_revisions, script_directory,
    verify_database_revision, SchemaAuthorityError,
)
from app.repositories.tenant_scope import tenant_get, local_primary_key
from frozen_schema_fixtures import frozen_0007_metadata, frozen_0008_metadata
from test_domain_tenant_migration import TENANT_A, TENANT_B, _seed_pre_tenancy_row, _seed_tenant

HEAD = "0008_tenant_scoped_identity_namespace"
PARENT = "0007_machine_tenant_binding"
MIGRATION = script_directory().get_revision(HEAD).module


@pytest.fixture(params=["sqlite", "postgres"])
def identity_engine(request, tmp_path):
    if request.param == "postgres":
        if not os.getenv("TOPO_TEST_POSTGRES_URL"):
            pytest.skip("set TOPO_TEST_POSTGRES_URL for PostgreSQL 16 acceptance")
        from test_postgres_runtime_compatibility import _temporary_database
        with _temporary_database("ph3f_namespace") as engine:
            yield engine
    else:
        engine = create_engine(f"sqlite:///{(tmp_path / 'identity.db').as_posix()}")
        try:
            yield engine
        finally:
            engine.dispose()


def migrate(engine, revision=HEAD, *, downgrade=False):
    with engine.begin() as c:
        (command.downgrade if downgrade else command.upgrade)(alembic_config(connection=c), revision)


def test_selective_identity_inventory():
    assert len(TENANT_LOCAL_PRIMARY_KEYS) == 25
    assert len(GLOBAL_AUTH_LOCATORS) == 3
    assert len(GLOBAL_RANDOM_STORAGE_KEYS) == 10
    groups = [set(TENANT_LOCAL_PRIMARY_KEYS), set(GLOBAL_AUTH_LOCATORS), set(GLOBAL_RANDOM_STORAGE_KEYS)]
    assert Counter(key for group in groups for key in group) == Counter(REQUIRED_OWNERSHIP_TABLES)
    assert MIGRATION.LOCAL_KEYS == TENANT_LOCAL_PRIMARY_KEYS
    for name, key in TENANT_LOCAL_PRIMARY_KEYS.items():
        assert list(Base.metadata.tables[name].primary_key.columns.keys()) == ["tenant_id", key]
    for name, key in {**GLOBAL_AUTH_LOCATORS, **GLOBAL_RANDOM_STORAGE_KEYS}.items():
        assert list(Base.metadata.tables[name].primary_key.columns.keys()) == [key]


def test_fresh_upgrade_parity_clean_downgrade_and_reupgrade(identity_engine):
    migrate(identity_engine)
    with identity_engine.connect() as c:
        assert schema_differences(c, metadata=frozen_0008_metadata()) == ()
        assert current_revisions(c) == (HEAD,)
        assert len(frozen_0008_metadata().tables) == 43
        for name in REQUIRED_OWNERSHIP_TABLES:
            tenant = next(col for col in inspect(c).get_columns(name) if col["name"] == "tenant_id")
            assert not tenant["nullable"] and tenant["default"] is None
            assert not inspect(c).get_foreign_keys(name)
    migrate(identity_engine, PARENT, downgrade=True)
    with identity_engine.connect() as c:
        assert schema_differences(c, metadata=frozen_0007_metadata()) == ()
    with pytest.raises(SchemaAuthorityError, match="state=behind"):
        verify_database_revision(identity_engine)
    migrate(identity_engine)
    with identity_engine.connect() as c:
        assert schema_differences(c, metadata=frozen_0008_metadata()) == ()


def test_populated_upgrade_changes_no_row_values(identity_engine):
    migrate(identity_engine, PARENT)
    with identity_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        for name in REQUIRED_OWNERSHIP_TABLES:
            _seed_pre_tenancy_row(c, name, tenant_id=TENANT_A)
        before = {name: [dict(row) for row in c.execute(text(f'SELECT * FROM "{name}"')).mappings()]
                  for name in frozen_0008_metadata().tables}
    migrate(identity_engine)
    with identity_engine.connect() as c:
        assert schema_differences(c, metadata=frozen_0008_metadata()) == ()
        for name, rows in before.items():
            assert [dict(row) for row in c.execute(text(f'SELECT * FROM "{name}"')).mappings()] == rows
    migrate(identity_engine, PARENT, downgrade=True)
    migrate(identity_engine)
    with identity_engine.connect() as c:
        for name, rows in before.items():
            assert [dict(row) for row in c.execute(text(f'SELECT * FROM "{name}"')).mappings()] == rows


@pytest.mark.parametrize("table_name", sorted(TENANT_LOCAL_PRIMARY_KEYS))
def test_equal_local_ids_coexist_orm_identity_and_downgrade_gate(identity_engine, table_name):
    migrate(identity_engine)
    key = TENANT_LOCAL_PRIMARY_KEYS[table_name]
    with identity_engine.begin() as c:
        _seed_tenant(c, TENANT_A)
        _seed_tenant(c, TENANT_B)
        # This schema corpus tests exact DB identities, independently of the
        # valid-world service corpus. No fake references are used as evidence.
        _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_A, **{key: "same-local-id"})
        _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_B, **{key: "same-local-id"})
    model = next(m.class_ for m in Base.registry.mappers if m.local_table.name == table_name)
    with Session(identity_engine) as session:
        a = tenant_get(session, model, "same-local-id", tenant_id=TENANT_A)
        b = tenant_get(session, model, "same-local-id", tenant_id=TENANT_B)
        assert a is not None and b is not None and a is not b
        assert inspect(a).identity == (TENANT_A, "same-local-id")
        assert inspect(b).identity == (TENANT_B, "same-local-id")
        assert session.get(model, (TENANT_A, "same-local-id")) is a
        assert session.get(model, (TENANT_B, "same-local-id")) is b
        before_b = {col.key: getattr(b, col.key) for col in model.__table__.columns}
        a.created_at = "2026-08-31T02:00:00+00:00"
        session.commit()
        session.refresh(b)
        assert {col.key: getattr(b, col.key) for col in model.__table__.columns} == before_b
        session.delete(a)
        session.commit()
        assert tenant_get(session, model, "same-local-id", tenant_id=TENANT_A) is None
        assert tenant_get(session, model, "same-local-id", tenant_id=TENANT_B) is b
    with identity_engine.begin() as c:
        _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_A, **{key: "same-local-id"})
    statements = []
    def capture(_conn, _cursor, statement, *_):
        statements.append(statement)
    event.listen(identity_engine, "before_cursor_execute", capture)
    try:
        with pytest.raises(RuntimeError, match="^TENANT_IDENTITY_COLLISION_PREVENTS_DOWNGRADE$"):
            migrate(identity_engine, PARENT, downgrade=True)
    finally:
        event.remove(identity_engine, "before_cursor_execute", capture)
    assert not any(s.lstrip().upper().startswith(("ALTER ", "CREATE ", "DROP ", "DELETE ", "UPDATE ")) for s in statements)
    with identity_engine.connect() as c:
        assert current_revisions(c) == (HEAD,)
        assert c.scalar(text(f'SELECT COUNT(*) FROM "{table_name}"')) == 2
        assert schema_differences(c, metadata=frozen_0008_metadata()) == ()


@pytest.mark.parametrize("table_name,column", [
    (table, column) for table, columns in MIGRATION.GLOBAL_INDEXES.items() for column in columns
])
def test_tenant_unique_business_keys_do_not_globally_collide(identity_engine, table_name, column):
    migrate(identity_engine)
    key = next(col.name for col in Base.metadata.tables[table_name].primary_key if col.name != "tenant_id")
    with identity_engine.begin() as c:
        for tenant, suffix in [(TENANT_A, "a"), (TENANT_B, "b")]:
            _seed_pre_tenancy_row(c, table_name, tenant_id=tenant, **{key: f"local-{suffix}", column: "same-value"})
    with pytest.raises(IntegrityError):
        with identity_engine.begin() as c:
            _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_A, **{key: "third-id", column: "same-value"})
    with pytest.raises(RuntimeError, match="TENANT_IDENTITY_COLLISION_PREVENTS_DOWNGRADE"):
        migrate(identity_engine, PARENT, downgrade=True)


def test_postgres_ddl_failure_rolls_back_namespace_and_revision(identity_engine):
    if identity_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL transactional DDL proof")
    migrate(identity_engine, PARENT)
    def reject(_conn, _cursor, statement, *_):
        if "ADD CONSTRAINT pk_incidents" in statement:
            raise RuntimeError("injected identity DDL failure")
    event.listen(identity_engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(RuntimeError, match="injected identity DDL failure"):
            migrate(identity_engine)
    finally:
        event.remove(identity_engine, "before_cursor_execute", reject)
    with identity_engine.connect() as c:
        assert current_revisions(c) == (PARENT,)
        assert schema_differences(c, metadata=frozen_0007_metadata()) == ()


@pytest.mark.parametrize("table_name", sorted(MIGRATION.GLOBAL_UNIQUES))
def test_tenant_unique_constraint_tuples_coexist_but_reject_same_tenant(identity_engine, table_name):
    migrate(identity_engine)
    key = next(col.name for col in Base.metadata.tables[table_name].primary_key if col.name != "tenant_id")
    with identity_engine.begin() as c:
        _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_A, **{key: "row-a"})
        _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_B, **{key: "row-b"})
    with pytest.raises(IntegrityError):
        with identity_engine.begin() as c:
            _seed_pre_tenancy_row(c, table_name, tenant_id=TENANT_A, **{key: "row-c"})
    with pytest.raises(RuntimeError, match="TENANT_IDENTITY_COLLISION_PREVENTS_DOWNGRADE"):
        migrate(identity_engine, PARENT, downgrade=True)


@pytest.mark.parametrize("table_name,key", [
    *GLOBAL_AUTH_LOCATORS.items(),
    ("agent_enrollment_tokens", "token_hash"), ("topo_agents", "token_hash"),
    ("auth_sessions", "session_secret_digest"),
    ("auth_api_credentials", "credential_secret_digest"),
])
def test_authentication_locator_uniqueness_is_not_tenant_partitioned(identity_engine, table_name, key):
    migrate(identity_engine)
    primary = next(col.name for col in Base.metadata.tables[table_name].primary_key)
    for owner, suffix in [(TENANT_A, "a"), (TENANT_B, "b")]:
        values = {primary: f"row-{suffix}", key: "same-auth-locator"}
        if "tenant_id" in Base.metadata.tables[table_name].columns:
            values["tenant_id"] = owner
        if suffix == "a":
            with identity_engine.begin() as c:
                _seed_pre_tenancy_row(c, table_name, **values)
        else:
            with pytest.raises(IntegrityError):
                with identity_engine.begin() as c:
                    _seed_pre_tenancy_row(c, table_name, **values)


def test_null_ownership_is_rejected_before_ddl_without_assignment(identity_engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import String

    migrate(identity_engine, PARENT)
    with identity_engine.begin() as c:
        # Deliberately corrupt only this disposable preflight fixture.
        ops = Operations(MigrationContext.configure(c))
        with ops.batch_alter_table("signals") as batch:
            batch.alter_column("tenant_id", existing_type=String(255), nullable=True)
        _seed_pre_tenancy_row(c, "signals", tenant_id=None)
    statements = []
    def capture(_conn, _cursor, statement, *_):
        statements.append(statement)
    event.listen(identity_engine, "before_cursor_execute", capture)
    try:
        with pytest.raises(RuntimeError, match="^TENANT_IDENTITY_NULL_OWNERSHIP$"):
            migrate(identity_engine)
    finally:
        event.remove(identity_engine, "before_cursor_execute", capture)
    assert not any(s.lstrip().upper().startswith(("ALTER ", "CREATE ", "DROP ", "UPDATE ")) for s in statements)
    with identity_engine.connect() as c:
        assert current_revisions(c) == (PARENT,)
        assert c.scalar(text("SELECT tenant_id FROM signals")) is None
