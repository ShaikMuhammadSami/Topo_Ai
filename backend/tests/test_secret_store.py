"""PH-4B synthetic-only, real SQL/crypto custody and lifecycle acceptance."""

import base64
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import SecretRecord as R, SecretVersionRecord as V, TenantRecord
from app.models.secret_store import *
from app.security.secret_keyring import (
    SecretKeyring, SecretStoreConfiguration, load_keyring, load_secret_store_configuration,
)
from app.services import secret_store as module
from app.services.secret_store import EncryptedDatabaseSecretStore

NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)
TENANT_A = "tenant:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TENANT_B = "tenant:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
INSTALLATION = "installation:cccccccc-cccc-4ccc-8ccc-cccccccccccc"


@pytest.fixture(scope="module", params=["sqlite", "postgres"])
def secret_engine(request, tmp_path_factory):
    if request.param == "postgres":
        if not os.getenv("TOPO_TEST_POSTGRES_URL"):
            pytest.skip("set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 proof")
        from test_postgres_runtime_compatibility import _temporary_database
        with _temporary_database("ph4b_secret") as engine:
            Base.metadata.create_all(engine)
            yield engine
    else:
        path = tmp_path_factory.mktemp("ph4b") / "store.db"
        engine = create_engine(f"sqlite:///{path.as_posix()}")
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
        yield engine
        engine.dispose()


@pytest.fixture
def context(secret_engine, monkeypatch):
    monkeypatch.setattr(module, "utc_now", lambda: NOW)
    with Session(secret_engine) as session, session.begin():
        session.execute(delete(V))
        session.execute(delete(R))
        session.execute(delete(TenantRecord))
        for tenant in (TENANT_A, TENANT_B):
            session.add(TenantRecord(tenant_id=tenant, display_name="Synthetic", status="active",
                created_at=NOW.isoformat(), updated_at=NOW.isoformat(), created_by_subject="test"))
    keys = {"old": os.urandom(32), "new": os.urandom(32)}
    config = SecretStoreConfiguration("encrypted_db", SecretKeyring(keys, "old"), INSTALLATION)
    store = EncryptedDatabaseSecretStore(config)
    binding = SecretBinding(SecretScope.tenant(TENANT_A), "change_source", "source:synthetic", SecretPurpose.GITHUB_HMAC)
    return secret_engine, store, binding, keys


def put(context, *, binding=None, material=None):
    engine, store, default, _ = context
    material = material or SecretMaterial(os.urandom(48))
    with Session(engine) as s, s.begin():
        result = store.put(s, binding or default, material, operation_id="put", actor="test")
    return result, material


def rotate(context, descriptor, material=None, *, operation="rotate", overlap=0):
    engine, store, binding, _ = context
    material = material or SecretMaterial(os.urandom(48))
    with Session(engine) as s, s.begin():
        result = store.rotate(s, binding, descriptor.secret_ref, material,
            operation_id=operation, actor="test", expected_row_version=descriptor.row_version,
            overlap_seconds=overlap)
    return result, material


def test_put_get_idempotency_and_caller_rollback(context):
    engine, store, binding, _ = context
    d, material = put(context)
    assert SECRET_REF_PATTERN.fullmatch(d.secret_ref)
    with Session(engine) as s:
        assert store.get_for_use(s, binding, d.secret_ref)[0].reveal() == material.reveal()
        assert store.put(s, binding, material, operation_id="put", actor="test") == d
        with pytest.raises(SecretStoreError, match="SECRET_OPERATION_CONFLICT"):
            store.put(s, binding, SecretMaterial(os.urandom(30)), operation_id="put", actor="test")
        assert len(s.scalars(select(V)).all()) == 1
    other = replace(binding, owner_id="source:rollback")
    with Session(engine) as s:
        store.put(s, other, material, operation_id="rollback", actor="test")
        s.rollback()
    with Session(engine) as s:
        assert len(s.scalars(select(R)).all()) == 1


def test_explicit_reprovision_keeps_ref_and_never_revives_old_material(context):
    engine, store, binding, _ = context
    descriptor, old_material = put(context)
    with Session(engine) as session, session.begin():
        revoked = store.revoke(
            session, binding, descriptor.secret_ref, actor="test",
            expected_row_version=descriptor.row_version,
        )
    replacement = SecretMaterial(os.urandom(48))
    with Session(engine) as session, session.begin():
        active = store.reprovision(
            session, binding, descriptor.secret_ref, replacement,
            operation_id="reprovision", actor="test",
            expected_row_version=revoked.row_version,
        )
    assert active.secret_ref == descriptor.secret_ref
    assert active.status == "active"
    assert active.active_version == descriptor.active_version + 1
    assert active.previous_version is None
    with Session(engine) as session:
        assert [value.reveal() for value in store.get_for_use(
            session, binding, descriptor.secret_ref
        )] == [replacement.reveal()]
        assert old_material.reveal() not in [
            value.reveal() for value in store.get_for_use(
                session, binding, descriptor.secret_ref
            )
        ]
        assert store.reprovision(
            session, binding, descriptor.secret_ref, replacement,
            operation_id="reprovision", actor="test",
            expected_row_version=revoked.row_version,
        ) == active
        with pytest.raises(SecretStoreError, match="SECRET_OPERATION_CONFLICT"):
            store.reprovision(
                session, binding, descriptor.secret_ref, SecretMaterial(os.urandom(48)),
                operation_id="reprovision", actor="test",
                expected_row_version=revoked.row_version,
            )


@pytest.mark.parametrize("attack", ["tenant", "owner", "purpose", "installation", "disabled_tenant"])
def test_authorization_precedes_ciphertext_access(context, monkeypatch, attack):
    engine, store, binding, _ = context
    d, _ = put(context)
    wrong = binding
    if attack == "tenant": wrong = replace(binding, scope=SecretScope.tenant(TENANT_B))
    if attack == "owner": wrong = replace(binding, owner_id="source:other")
    if attack == "purpose": wrong = replace(binding, purpose=SecretPurpose.JENKINS_HMAC)
    if attack == "installation":
        wrong = SecretBinding(SecretScope("installation", INSTALLATION, None), "installation_integration", "openai", SecretPurpose.OPENAI_API)
    if attack == "disabled_tenant":
        with Session(engine) as s, s.begin():
            s.execute(update(TenantRecord).where(TenantRecord.tenant_id == TENANT_A).values(status="disabled"))
    monkeypatch.setattr(store, "_decrypt", lambda *args: pytest.fail("unauthorized decrypt"))
    statements = []
    def capture(_c, _cu, statement, *_): statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as s, pytest.raises(SecretStoreError, match="SECRET_NOT_FOUND"):
            store.get_for_use(s, wrong, d.secret_ref)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any("secret_versions" in q for q in statements)


def test_two_tenants_and_installation_coexist(context):
    engine, store, binding, _ = context
    a, ma = put(context)
    b_binding = replace(binding, scope=SecretScope.tenant(TENANT_B))
    b, mb = put(context, binding=b_binding)
    i_binding = SecretBinding(SecretScope("installation", INSTALLATION, None), "installation_integration", "github", SecretPurpose.GITHUB_API)
    i, mi = put(context, binding=i_binding)
    assert len({a.secret_ref, b.secret_ref, i.secret_ref}) == 3
    with Session(engine) as s:
        for descriptor, material, owner in ((a, ma, binding), (b, mb, b_binding), (i, mi, i_binding)):
            assert store.get_for_use(s, owner, descriptor.secret_ref)[0].reveal() == material.reveal()


@pytest.mark.parametrize("purpose", list(SecretPurpose))
def test_exact_purpose_scope_policy(context, purpose):
    engine, store, _, _ = context
    owner_type = purpose.value.split(".")[0]
    scope = SecretScope("installation", INSTALLATION, None) if owner_type == "installation_integration" else SecretScope.tenant(TENANT_A)
    binding = SecretBinding(scope, owner_type, "synthetic", purpose)
    d, _ = put(context, binding=binding)
    with Session(engine) as s:
        assert len(store.get_for_use(s, binding, d.secret_ref)) == 1
        if purpose not in INBOUND_PURPOSES:
            with pytest.raises(SecretStoreError, match="SECRET_OVERLAP_INVALID"):
                store.rotate(s, binding, d.secret_ref, SecretMaterial(os.urandom(10)),
                    operation_id="rotation", actor="test", expected_row_version=1, overlap_seconds=1)
    with pytest.raises(SecretStoreError):
        replace(binding, owner_type="wrong")


def test_rotation_overlap_expiry_second_rotation_retry_and_revoke(context, monkeypatch):
    engine, store, binding, _ = context
    d, first = put(context)
    d2, second = rotate(context, d, overlap=3600)
    with Session(engine) as s:
        assert [m.reveal() for m in store.get_for_use(s, binding, d.secret_ref)] == [second.reveal(), first.reveal()]
    monkeypatch.setattr(module, "utc_now", lambda: NOW + timedelta(minutes=10))
    retry, _ = rotate(context, d, second, overlap=3600)
    assert retry == d2  # no deadline extension / version insertion
    with pytest.raises(SecretStoreError, match="SECRET_OPERATION_CONFLICT"):
        rotate(context, d, second, overlap=60)
    d3, third = rotate(context, d2, operation="rotate-again", overlap=60)
    with Session(engine) as s:
        assert [m.reveal() for m in store.get_for_use(s, binding, d.secret_ref)] == [third.reveal(), second.reveal()]
    monkeypatch.setattr(module, "utc_now", lambda: NOW + timedelta(minutes=11))
    with Session(engine) as s, s.begin():
        assert [m.reveal() for m in store.get_for_use(s, binding, d.secret_ref)] == [third.reveal()]
        revoked = store.revoke(s, binding, d.secret_ref, actor="test", expected_row_version=d3.row_version)
        assert store.revoke(s, binding, d.secret_ref, actor="test", expected_row_version=1) == revoked
        for method in (lambda: store.get_for_use(s, binding, d.secret_ref),
                       lambda: store.rotate(s, binding, d.secret_ref, first, operation_id="late", actor="test", expected_row_version=revoked.row_version)):
            with pytest.raises(SecretStoreError, match="SECRET_REVOKED"): method()


@pytest.mark.parametrize("overlap", [-1, 86401, True, "1"])
def test_overlap_bounds(context, overlap):
    d, _ = put(context)
    with pytest.raises(SecretStoreError, match="SECRET_OVERLAP_INVALID"):
        rotate(context, d, overlap=overlap)


def test_rewrap_live_material_only_retire_key_and_preserve_versions(context, monkeypatch):
    engine, store, binding, keys = context
    d, first = put(context)
    d2, second = rotate(context, d, overlap=60)
    new_store = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring(keys, "new"), INSTALLATION))
    with Session(engine) as s:
        before = [(v.version, bytes(v.nonce), bytes(v.ciphertext), v.operation_id) for v in s.scalars(select(V).order_by(V.version))]
    with Session(engine) as s, s.begin():
        rewrapped = new_store.rewrap(s, binding, d.secret_ref, actor="test", expected_row_version=d2.row_version)
        assert rewrapped.active_version == 2 and rewrapped.previous_accept_until == d2.previous_accept_until
    retired = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring({"new": keys["new"]}, "new"), INSTALLATION))
    with Session(engine) as s:
        retired.validate_readiness(s)
        assert [m.reveal() for m in retired.get_for_use(s, binding, d.secret_ref)] == [second.reveal(), first.reveal()]
        assert retired.rewrap(s, binding, d.secret_ref, actor="test", expected_row_version=rewrapped.row_version) == rewrapped
        after = s.scalars(select(V).order_by(V.version)).all()
        for prior, row in zip(before, after):
            assert row.version == prior[0] and row.operation_id == prior[3]
            assert row.nonce != prior[1] and row.ciphertext != prior[2] and row.envelope_revision == 2


@pytest.mark.parametrize("state", ["live", "expired_previous", "revoked"])
def test_readiness_retirement_policy(context, monkeypatch, state):
    engine, store, binding, keys = context
    d, _ = put(context)
    new_store = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring(keys, "new"), INSTALLATION))
    if state == "expired_previous":
        with Session(engine) as s, s.begin():
            new_store.rotate(s, binding, d.secret_ref, SecretMaterial(os.urandom(30)),
                operation_id="new-key-material", actor="test", expected_row_version=1, overlap_seconds=30)
        monkeypatch.setattr(module, "utc_now", lambda: NOW + timedelta(seconds=30))
    if state == "revoked":
        with Session(engine) as s, s.begin(): store.revoke(s, binding, d.secret_ref, actor="test", expected_row_version=1)
    retired = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring({"new": keys["new"]}, "new"), INSTALLATION))
    monkeypatch.setattr(retired, "_decrypt", lambda *a: pytest.fail("readiness decrypted"))
    with Session(engine) as s:
        if state == "live":
            with pytest.raises(SecretStoreError, match="SECRET_REQUIRED_KEY_MISSING"): retired.validate_readiness(s)
        else: retired.validate_readiness(s)


@pytest.mark.parametrize("field", ["ciphertext", "nonce", "key_id", "algorithm", "envelope_version", "version", "owner_id", "scope_id", "tenant_id", "purpose", "secret_ref", "scope_kind"])
def test_envelope_and_aad_tamper_never_releases_material(context, field):
    engine, store, binding, _ = context
    d, _ = put(context)
    # In-memory copies let every authenticated field be attacked independently
    # of SQL constraints, including the otherwise immutable FK/PK bindings.
    with Session(engine) as s:
        record = s.scalar(select(R))
        version = s.scalar(select(V))
        target = version if field in {"ciphertext", "nonce", "key_id", "algorithm", "envelope_version", "version"} else record
        original = getattr(target, field)
        if isinstance(original, bytes): value = bytes([original[0] ^ 1]) + original[1:]
        elif isinstance(original, int): value = original + 1
        else: value = str(original) + "-tampered"
        setattr(target, field, value)
        with pytest.raises(SecretStoreError, match="^SECRET_DECRYPT_FAILED$"):
            store._decrypt(record, version)


def test_wrong_key_missing_version_nonce_bounds_and_no_plaintext_repr(context):
    engine, store, binding, keys = context
    d, material = put(context)
    with Session(engine) as s:
        row = s.scalar(select(V))
        raw = material.reveal()
        for obj in (material, d, store.configuration, store.configuration.keyring, row, s.scalar(select(R))):
            assert raw.hex() not in repr(obj) and repr(raw) not in repr(obj)
            assert row.ciphertext.hex() not in repr(obj) and repr(bytes(row.ciphertext)) not in repr(obj)
        with pytest.raises(TypeError): json.dumps(material)
        assert not {"ciphertext", "nonce", "material", "key"} & asdict(d).keys()
        bad = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring({"old": os.urandom(32)}, "old")))
        with pytest.raises(SecretStoreError, match="^SECRET_DECRYPT_FAILED$"): bad.get_for_use(s, binding, d.secret_ref)
        for nonce, ciphertext in ((b"", b"x" * 17), (b"x" * 12, b"x" * 16), (b"x" * 12, b"x" * 65553)):
            row.nonce, row.ciphertext = nonce, ciphertext
            with pytest.raises(SecretStoreError, match="^SECRET_DECRYPT_FAILED$"): store._decrypt(s.scalar(select(R)), row)
    with engine.connect() as c:
        rows = c.exec_driver_sql("SELECT * FROM secret_versions").all()
        assert all(raw not in bytes(value) for row in rows for value in row if isinstance(value, (bytes, memoryview)))
        assert raw.hex() not in repr(rows)


@pytest.mark.parametrize("operation", ["put", "rotate", "rewrap"])
def test_injected_failure_is_atomic_even_if_caller_catches_and_commits(context, monkeypatch, operation):
    engine, store, binding, keys = context
    d, material = put(context) if operation != "put" else (None, SecretMaterial(os.urandom(30)))
    if operation == "rewrap":
        store = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring(keys, "new")))
    with engine.connect() as c:
        before = ([tuple(r) for r in c.execute(select(R.__table__))], [tuple(r) for r in c.execute(select(V.__table__))])
    def fail(_c, _cu, statement, *_):
        if (operation in {"put", "rotate"} and statement.startswith("INSERT INTO secret_versions")) or (operation == "rewrap" and statement.startswith("UPDATE secret_versions")):
            raise RuntimeError("synthetic injected failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with Session(engine) as s, s.begin():
            with pytest.raises(RuntimeError, match="synthetic injected failure"):
                if operation == "put": store.put(s, binding, material, operation_id="put", actor="test")
                elif operation == "rotate": store.rotate(s, binding, d.secret_ref, material, operation_id="rotate", actor="test", expected_row_version=1)
                else: store.rewrap(s, binding, d.secret_ref, actor="test", expected_row_version=1)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with engine.connect() as c:
        assert ([tuple(r) for r in c.execute(select(R.__table__))], [tuple(r) for r in c.execute(select(V.__table__))]) == before
    with Session(engine) as s, s.begin():
        if operation == "put": store.put(s, binding, material, operation_id="put", actor="test")
        elif operation == "rotate": store.rotate(s, binding, d.secret_ref, material, operation_id="rotate", actor="test", expected_row_version=1)
        else: store.rewrap(s, binding, d.secret_ref, actor="test", expected_row_version=1)


def test_fresh_nonce_for_equal_plaintext_and_zero_overlap(context):
    engine, store, binding, _ = context
    d, material = put(context)
    d2, _ = rotate(context, d, material)
    assert d2.previous_version is None
    with Session(engine) as s:
        versions = s.scalars(select(V).order_by(V.version)).all()
        assert len({bytes(v.nonce) for v in versions}) == 2
        assert len({bytes(v.ciphertext) for v in versions}) == 2
        assert len(store.get_for_use(s, binding, d.secret_ref)) == 1


@pytest.mark.parametrize("material", [b"", b"a" * 65537, "not-bytes"], ids=["empty", "oversized", "wrong-type"])
def test_material_size_rejections(material):
    with pytest.raises(SecretStoreError, match="^SECRET_MATERIAL_INVALID$"): SecretMaterial(material)


def test_keyring_file_and_configuration(tmp_path, monkeypatch):
    key = os.urandom(32)
    path = tmp_path / "synthetic-keyring.json"
    path.write_text(json.dumps({"version": 1, "keys": {"test": base64.urlsafe_b64encode(key).decode()}}))
    path.chmod(0o600)
    ring = load_keyring(str(path), "test")
    assert ring.key("test") == key and repr(key) not in repr(ring)
    monkeypatch.setenv("TOPO_SECRET_STORE_BACKEND", "encrypted_db")
    monkeypatch.setenv("TOPO_SECRET_KEYRING_FILE", str(path))
    monkeypatch.setenv("TOPO_SECRET_ACTIVE_KEY_ID", "test")
    monkeypatch.delenv("TOPO_INSTALLATION_ID", raising=False)
    assert load_secret_store_configuration().installation_id is None
    with pytest.raises(SecretStoreError, match="SECRET_ACTIVE_KEY_MISSING"): load_keyring(str(path), "missing")
    with pytest.raises(SecretStoreError): load_keyring(str(tmp_path), "test")
    with pytest.raises(SecretStoreError): load_keyring(str(tmp_path / "missing"), "test")


@pytest.mark.parametrize("document", ["", "invalid", "[]", '{"version":1,"version":1,"keys":{}}',
    '{"version":1,"keys":{"same":"a","same":"b"}}', '{"version":true,"keys":{}}',
    '{"version":2,"keys":{}}', '{"version":1,"keys":{}}', "x" * 65537,
    json.dumps({"version": 1, "keys": {"invalid key": "a" * 43}}),
    json.dumps({"version": 1, "keys": {"test": "!" * 43}}),
    json.dumps({"version": 1, "keys": {str(i): "a" * 43 for i in range(33)}})], ids=[f"invalid-{i}" for i in range(12)])
def test_malformed_keyrings_fail_generic_without_input(tmp_path, document):
    path = tmp_path / "synthetic-invalid.json"
    path.write_text(document)
    path.chmod(0o600)
    with pytest.raises(SecretStoreError, match="^SECRET_KEYRING_INVALID$") as error:
        load_keyring(str(path), "test")
    assert error.value.__context__ is None


def test_disabled_store_empty_and_nonempty(context):
    engine, _, _, _ = context
    disabled = EncryptedDatabaseSecretStore(SecretStoreConfiguration())
    with Session(engine) as s: disabled.validate_readiness(s)
    put(context)
    with Session(engine) as s, pytest.raises(SecretStoreError, match="SECRET_STORE_DISABLED"):
        disabled.validate_readiness(s)


def test_disabled_rejects_version_only_orphan(tmp_path):
    # SQLite can contain corrupt/orphan rows when a non-application writer turns
    # FK enforcement off. Disabled mode must inspect BOTH tables regardless.
    engine = create_engine(f"sqlite:///{(tmp_path / 'orphan.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as s, s.begin():
        s.add(V(secret_ref=f"secret:{uuid4()}", version=1, key_id="synthetic", algorithm="AES-256-GCM",
            envelope_version=1, nonce=os.urandom(12), ciphertext=os.urandom(32), operation_id="synthetic",
            operation_kind="put", overlap_seconds=0, envelope_revision=1, created_at=NOW.isoformat(), created_by_subject="test"))
    with Session(engine) as s, pytest.raises(SecretStoreError, match="SECRET_STORE_DISABLED"):
        EncryptedDatabaseSecretStore(SecretStoreConfiguration()).validate_readiness(s)
    engine.dispose()


@pytest.mark.parametrize("mutation", ["tenant_null", "tenant_mismatch", "installation_tenant", "scope_unknown", "owner_duplicate", "operation_duplicate"])
def test_database_structural_constraints(context, mutation):
    from sqlalchemy.exc import IntegrityError
    engine, _, binding, _ = context
    d, _ = put(context)
    with Session(engine) as s:
        record = s.scalar(select(R))
        if mutation == "tenant_null": record.tenant_id = None
        elif mutation == "tenant_mismatch": record.scope_id = TENANT_B
        elif mutation == "installation_tenant": record.scope_kind = "installation"
        elif mutation == "scope_unknown": record.scope_kind = "unknown"
        elif mutation == "owner_duplicate":
            values = {column.name: getattr(record, column.name) for column in R.__table__.columns}
            values["secret_ref"] = f"secret:{uuid4()}"
            s.add(R(**values))
        else:
            version = s.scalar(select(V))
            values = {column.name: getattr(version, column.name) for column in V.__table__.columns}
            values["version"] = 2
            s.add(V(**values))
        with pytest.raises(IntegrityError): s.flush()
        s.rollback()


def test_boundary_errors_and_logs_contain_no_secret_or_ciphertext(context, caplog, monkeypatch):
    from sqlalchemy.exc import OperationalError
    import traceback
    engine, store, binding, keys = context
    d, material = put(context)
    with Session(engine) as s:
        row = s.scalar(select(V))
        ciphertext = bytes(row.ciphertext)
    def fail(*args, **kwargs):
        raise OperationalError("synthetic SQL", {"secret": material.reveal(), "ciphertext": ciphertext}, Exception("synthetic driver"))
    with Session(engine) as s:
        monkeypatch.setattr(s, "scalar", fail)
        with pytest.raises(SecretStoreError, match="^SECRET_STORE_UNAVAILABLE$") as caught:
            store.get_for_use(s, binding, d.secret_ref)
    output = "".join(traceback.format_exception(caught.value)) + caplog.text
    assert caught.value.__context__ is None
    for value in (material.reveal(), ciphertext, *keys.values()):
        assert repr(value) not in output and value.hex() not in output
