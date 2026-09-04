"""PH-4E PostgreSQL ciphertext-only backup/root-key separation proof."""

from __future__ import annotations

import base64
import os
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.models import SecretVersionRecord, TenantRecord
from app.models.secret_store import SecretBinding, SecretMaterial, SecretPurpose, SecretScope, SecretStoreError
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.services.secret_store import EncryptedDatabaseSecretStore
from test_database_migration_operations import (
    POSTGRES_CONTAINER,
    _drop_database,
    _postgres_url,
    _temporary_database,
    _upgrade,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("TOPO_TEST_POSTGRES_URL") or not POSTGRES_CONTAINER,
    reason="set PH-4E disposable PostgreSQL URL and container for backup proof",
)


def test_postgres_backup_contains_ciphertext_but_not_material_or_root_key():
    tenant_id = "tenant:4e4e4e4e-4e4e-4e4e-8e4e-4e4e4e4e4e4e"
    installation_id = "installation:4e4e4e4e-4e4e-4e4e-8e4e-4e4e4e4e4e4e"
    marker = f"PH4E_BACKUP_SECRET_{uuid4().hex}"
    root_key = os.urandom(32)
    root_b64 = base64.urlsafe_b64encode(root_key).decode("ascii")
    binding = SecretBinding(
        SecretScope.tenant(tenant_id),
        "change_source",
        f"source:backup:{uuid4().hex}",
        SecretPurpose.GITHUB_HMAC,
    )

    with _temporary_database("ph4e_secret_backup") as (engine, database_name):
        _upgrade(engine)
        store = EncryptedDatabaseSecretStore(
            SecretStoreConfiguration(
                "encrypted_db", SecretKeyring({"backup-root": root_key}, "backup-root"), installation_id
            )
        )
        with Session(engine) as session, session.begin():
            session.add(
                TenantRecord(
                    tenant_id=tenant_id,
                    display_name="PH-4E backup",
                    status="active",
                    created_at="2026-09-04T12:00:00+00:00",
                    updated_at="2026-09-04T12:00:00+00:00",
                    created_by_subject="test:ph4e",
                )
            )
        with Session(engine) as session, session.begin():
            descriptor = store.put(
                session,
                binding,
                SecretMaterial(marker.encode()),
                operation_id="ph4e-backup-put",
                actor="test:ph4e",
            )
        with Session(engine) as session:
            ciphertext = bytes(session.scalar(select(SecretVersionRecord)).ciphertext)

        dump_path = f"/tmp/{database_name}.dump"
        database_user = make_url(_postgres_url()).username
        assert database_user
        try:
            subprocess.run(
                [
                    "docker", "exec", POSTGRES_CONTAINER, "pg_dump", "-U", database_user,
                    "-d", database_name, "--format=custom", f"--file={dump_path}",
                ],
                check=True,
                capture_output=True,
            )
            dump = subprocess.run(
                ["docker", "exec", POSTGRES_CONTAINER, "cat", dump_path],
                check=True,
                capture_output=True,
            ).stdout
            assert marker.encode() not in dump
            assert root_key not in dump
            assert root_b64.encode() not in dump

            base_url = make_url(_postgres_url())
            admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
            engine.dispose()
            try:
                _drop_database(admin, database_name)
                with admin.connect() as connection:
                    connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            finally:
                admin.dispose()
            subprocess.run(
                [
                    "docker", "exec", POSTGRES_CONTAINER, "pg_restore", "-U", database_user,
                    "-d", database_name, "--exit-on-error", dump_path,
                ],
                check=True,
                capture_output=True,
            )

            restored = create_engine(base_url.set(database=database_name))
            try:
                missing = EncryptedDatabaseSecretStore(
                    SecretStoreConfiguration(
                        "encrypted_db",
                        SecretKeyring({"other-root": os.urandom(32)}, "other-root"),
                        installation_id,
                    )
                )
                wrong = EncryptedDatabaseSecretStore(
                    SecretStoreConfiguration(
                        "encrypted_db",
                        SecretKeyring({"backup-root": os.urandom(32)}, "backup-root"),
                        installation_id,
                    )
                )
                with Session(restored) as session:
                    restored_ciphertext = bytes(session.scalar(select(SecretVersionRecord)).ciphertext)
                    assert restored_ciphertext == ciphertext
                    with pytest.raises(SecretStoreError, match="SECRET_REQUIRED_KEY_MISSING"):
                        missing.validate_readiness(session)
                    wrong.validate_readiness(session)
                    with pytest.raises(SecretStoreError, match="SECRET_DECRYPT_FAILED"):
                        wrong.get_for_use(session, binding, descriptor.secret_ref)
                    assert store.get_for_use(session, binding, descriptor.secret_ref)[0].reveal() == marker.encode()
            finally:
                restored.dispose()
        finally:
            subprocess.run(
                ["docker", "exec", POSTGRES_CONTAINER, "rm", "-f", dump_path],
                check=False,
                capture_output=True,
            )

