"""Internal startup gates; no new endpoint and no public custody diagnostics."""

from dataclasses import replace
import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import SecretRecord as R, SecretVersionRecord as V
from app.models.secret_store import SecretStoreError, SecretScope
from app.security import secret_keyring as keyring_module
from app.security.secret_keyring import SecretStoreConfiguration, SecretKeyring, load_keyring
from app.services.secret_store import EncryptedDatabaseSecretStore
from test_secret_store import context, secret_engine, put, INSTALLATION


def test_actual_lifespan_public_output_and_default_disabled_gate(context, monkeypatch, caplog):
    engine, store, binding, _ = context
    import app.main as main
    # Existing default-on auth is unchanged; this isolated synthetic app uses the
    # existing explicit test development mode only on SQLite.
    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite development-mode HTTP fixture; PG store gates tested directly")
    factory = sessionmaker(engine)
    monkeypatch.setattr(main, "load_secret_store_configuration", lambda: store.configuration)
    application = main.create_app(session_factory=factory, database_initializer=lambda: None)
    with TestClient(application) as client:
        assert client.get("/ready").json() == {"status": "ready"}
        assert client.get("/health").json() == {"status": "available", "service": "Topo AI", "version": "0.1.0"}
    descriptor, material = put(context)
    monkeypatch.setattr(main, "load_secret_store_configuration", SecretStoreConfiguration)
    with pytest.raises(SecretStoreError, match="^SECRET_STORE_DISABLED$"):
        with TestClient(application): pass
    assert application.state.ready is False
    assert material.reveal().hex() not in caplog.text
    assert descriptor.secret_ref not in caplog.text


def test_schema_failure_precedes_keyring_and_auth(context, monkeypatch):
    engine, _, _, _ = context
    import app.main as main
    def schema_failure(): raise RuntimeError("synthetic schema behind")
    monkeypatch.setattr(main, "load_secret_store_configuration", lambda: pytest.fail("schema must be first"))
    application = main.create_app(session_factory=sessionmaker(engine), database_initializer=schema_failure)
    with pytest.raises(RuntimeError, match="synthetic schema behind"):
        with TestClient(application): pass
    assert not application.state.ready


def test_readiness_missing_active_or_live_previous_version(context):
    engine, store, binding, _ = context
    d, _ = put(context)
    with Session(engine) as s, s.begin():
        s.execute(delete(V).where(V.secret_ref == d.secret_ref))
    with Session(engine) as s, pytest.raises(SecretStoreError, match="SECRET_DECRYPT_FAILED"):
        store.validate_readiness(s)
    with Session(engine) as s, pytest.raises(SecretStoreError, match="SECRET_DECRYPT_FAILED"):
        store.get_for_use(s, binding, d.secret_ref)


def test_readiness_first_page_does_not_skip_malformed_empty_reference(context):
    engine, store, binding, _ = context
    descriptor, _ = put(context)
    with Session(engine) as s, s.begin():
        record = s.scalar(select(R))
        values = {column.name: getattr(record, column.name) for column in R.__table__.columns}
        values.update(secret_ref="", owner_id="source:corrupt-empty-ref")
        s.add(R(**values))
    with Session(engine) as s, pytest.raises(SecretStoreError, match="^SECRET_DECRYPT_FAILED$"):
        store.validate_readiness(s)


def test_explicit_installation_id_required_only_for_installation(context):
    engine, store, binding, _ = context
    no_installation = EncryptedDatabaseSecretStore(replace(store.configuration, installation_id=None))
    d, _ = put(context)
    with Session(engine) as s:
        assert no_installation.get_for_use(s, binding, d.secret_ref)
    from app.models.secret_store import SecretBinding, SecretPurpose
    installation_binding = SecretBinding(SecretScope("installation", INSTALLATION, None), "installation_integration", "github", SecretPurpose.GITHUB_API)
    with Session(engine) as s, pytest.raises(SecretStoreError, match="SECRET_SCOPE_INVALID"):
        no_installation.describe(s, installation_binding, d.secret_ref)


@pytest.mark.parametrize("kwargs", [dict(backend="plaintext"), dict(backend="encrypted_db"), dict(installation_id="hostname"), dict(installation_id="")])
def test_no_fallback_configuration(kwargs):
    with pytest.raises(SecretStoreError): SecretStoreConfiguration(**kwargs)


@pytest.mark.parametrize("length", [0, 16, 24, 31, 33, 64])
def test_exact_256_bit_keys_only(length):
    with pytest.raises(SecretStoreError, match="^SECRET_KEYRING_INVALID$"):
        SecretKeyring({"synthetic": os.urandom(length)}, "synthetic")


def test_posix_permission_policy_rejects_group_read_without_claiming_windows_acl(tmp_path, monkeypatch):
    path = tmp_path / "not-a-real-keyring.json"
    path.write_text("{}")
    real_lstat = type(path).lstat
    def permissive(candidate, *args, **kwargs):
        result = real_lstat(candidate, *args, **kwargs)
        if candidate == path:
            return SimpleNamespace(st_mode=0o100640, st_size=2, st_dev=result.st_dev, st_ino=result.st_ino)
        return result
    monkeypatch.setattr(type(path), "lstat", permissive)
    monkeypatch.setattr(keyring_module, "os", SimpleNamespace(name="posix"))
    with pytest.raises(SecretStoreError, match="^SECRET_KEYRING_INVALID$"):
        load_keyring(str(path), "synthetic")


def test_symlink_reparse_policy_refuses_before_open(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-link"
    monkeypatch.setattr(type(path), "lstat", lambda p: SimpleNamespace(st_mode=0o120777, st_file_attributes=0x400))
    with pytest.raises(SecretStoreError, match="^SECRET_KEYRING_INVALID$"):
        load_keyring(str(path), "synthetic")
