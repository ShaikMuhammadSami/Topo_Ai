"""Additive 0009 proof; protected databases are never test databases."""

import os

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import SecretRecord, SecretVersionRecord
from app.db.schema_management import (
    alembic_config, current_revisions, expected_head, schema_differences,
    SchemaAuthorityError, verify_database_revision,
)
from test_domain_tenant_migration import _seed_tenant, _seed_pre_tenancy_row, TENANT_A
from app.db.domain_ownership import REQUIRED_OWNERSHIP_TABLES

PARENT = "0008_tenant_scoped_identity_namespace"
HEAD = "0009_secret_store"
NEW_TABLES = {"secret_records", "secret_versions"}


@pytest.fixture(params=["sqlite", "postgres"])
def store_migration_engine(request, tmp_path):
    if request.param == "postgres":
        if not os.getenv("TOPO_TEST_POSTGRES_URL"):
            pytest.skip("set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 proof")
        from test_postgres_runtime_compatibility import _temporary_database
        with _temporary_database("ph4b_migration") as engine: yield engine
    else:
        engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
        yield engine
        engine.dispose()


def migrate(engine, target, *, down=False):
    with engine.begin() as connection:
        (command.downgrade if down else command.upgrade)(alembic_config(connection=connection), target)


@pytest.mark.parametrize("populated", [False, True])
def test_0009_fresh_populated_downgrade_reupgrade_and_behind(store_migration_engine, populated):
    engine = store_migration_engine
    migrate(engine, PARENT)
    existing = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert len(existing) == 43
    if populated:
        with engine.begin() as c:
            _seed_tenant(c, TENANT_A)
            for name in REQUIRED_OWNERSHIP_TABLES:
                _seed_pre_tenancy_row(c, name, tenant_id=TENANT_A)
    with engine.connect() as c:
        before = {name: c.execute(text(f'SELECT * FROM "{name}"')).all() for name in existing}
        before_columns = {name: inspect(c).get_columns(name) for name in existing}
    with pytest.raises(SchemaAuthorityError, match="state=behind"):
        verify_database_revision(engine)
    migrate(engine, HEAD)
    with engine.connect() as c:
        assert current_revisions(c) == (HEAD,) and expected_head() == HEAD
        assert len(Base.metadata.tables) == 45
        assert schema_differences(c) == ()
        assert set(inspect(c).get_table_names()) - {"alembic_version"} == existing | NEW_TABLES
        for name in existing:
            assert c.execute(text(f'SELECT * FROM "{name}"')).all() == before[name]
            assert repr(inspect(c).get_columns(name)) == repr(before_columns[name])
        assert c.scalar(select(SecretRecord.secret_ref).limit(1)) is None
        assert c.scalar(select(SecretVersionRecord.secret_ref).limit(1)) is None
        assert len(inspect(c).get_check_constraints("secret_records")) == 3
        assert len(inspect(c).get_foreign_keys("secret_versions")) == 1
        assert all(col["default"] is None for name in NEW_TABLES for col in inspect(c).get_columns(name))
    from app.models.secret_store import SecretBinding, SecretMaterial, SecretPurpose, SecretScope
    from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
    from app.services.secret_store import EncryptedDatabaseSecretStore
    installation = "installation:cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    store = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring({"test": os.urandom(32)}, "test"), installation))
    binding = SecretBinding(SecretScope("installation", installation, None), "installation_integration", "synthetic", SecretPurpose.GITHUB_API)
    with Session(engine) as s, s.begin():
        store.put(s, binding, SecretMaterial(os.urandom(48)), operation_id="synthetic", actor="test")
    migrate(engine, PARENT, down=True)
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == existing
    migrate(engine, HEAD)
    with engine.connect() as c:
        assert schema_differences(c) == ()
        for name in existing:
            assert c.execute(text(f'SELECT * FROM "{name}"')).all() == before[name]


def test_transactional_ddl_failure_rolls_back_new_tables(store_migration_engine, monkeypatch):
    engine = store_migration_engine
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL transactional DDL proof")
    from alembic import op
    migrate(engine, PARENT)
    actual = op.create_table
    def fail_after_first(*args, **kwargs):
        actual(*args, **kwargs)
        raise RuntimeError("synthetic migration interruption")
    monkeypatch.setattr(op, "create_table", fail_after_first)
    with pytest.raises(RuntimeError, match="synthetic migration interruption"):
        migrate(engine, HEAD)
    with engine.connect() as c:
        assert current_revisions(c) == (PARENT,)
        assert NEW_TABLES.isdisjoint(inspect(c).get_table_names())
