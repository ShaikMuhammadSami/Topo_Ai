"""Two independent transactions at PostgreSQL READ COMMITTED; no Python locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SecretRecord as R, SecretVersionRecord as V
from app.models.secret_store import SecretMaterial, SecretStoreError
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.services.secret_store import EncryptedDatabaseSecretStore
from test_secret_store import context, secret_engine, put


@pytest.mark.parametrize("operations", [("rotate", "rotate"), ("rotate", "revoke"), ("rotate", "rewrap"), ("rewrap", "rewrap")])
def test_independent_transaction_cas(context, monkeypatch, operations):
    engine, store, binding, keys = context
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL READ COMMITTED concurrency proof")
    d, original = put(context)
    store = EncryptedDatabaseSecretStore(SecretStoreConfiguration("encrypted_db", SecretKeyring(keys, "new")))
    barrier = Barrier(2)
    real_cas = store._cas
    def synchronized(*args, **kwargs):
        barrier.wait(timeout=20)
        return real_cas(*args, **kwargs)
    monkeypatch.setattr(store, "_cas", synchronized)
    def writer(index):
        with Session(engine) as session:
            assert session.connection().get_isolation_level() == "READ COMMITTED"
            try:
                if operations[index] == "rotate":
                    result = store.rotate(session, binding, d.secret_ref, SecretMaterial(b"synthetic-rotation-" + bytes([index])),
                        operation_id=f"rotate-{index}", actor="test", expected_row_version=1)
                elif operations[index] == "revoke":
                    result = store.revoke(session, binding, d.secret_ref, actor="test", expected_row_version=1)
                else:
                    result = store.rewrap(session, binding, d.secret_ref, actor="test", expected_row_version=1)
                session.commit()
                return "accepted", operations[index], result
            except SecretStoreError as error:
                session.rollback()
                return str(error), operations[index], None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, (0, 1)))
    assert sorted(r[0] for r in results) == ["SECRET_CONCURRENT_MODIFICATION", "accepted"]
    winner = next(r for r in results if r[0] == "accepted")
    with Session(engine) as session:
        record = session.scalar(select(R))
        assert record.row_version == 2
        versions = session.scalars(select(V).order_by(V.version)).all()
        assert any(v.version == record.active_version for v in versions)
        if winner[1] == "rotate":
            assert record.active_version == 2 and len(versions) == 2
        elif winner[1] == "revoke":
            assert record.status == "revoked"
            with pytest.raises(SecretStoreError, match="SECRET_REVOKED"):
                store.get_for_use(session, binding, d.secret_ref)
        else:
            assert record.active_version == 1 and len(versions) == 1
            assert versions[0].key_id == "new" and versions[0].envelope_revision == 2
            assert store.get_for_use(session, binding, d.secret_ref)[0].reveal() == original.reveal()
