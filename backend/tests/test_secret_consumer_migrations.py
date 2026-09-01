"""PH-4C staged migration and controlled legacy-conversion proof."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import create_engine, inspect

from app.db.schema_management import alembic_config, current_revisions, schema_differences
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.services.secret_legacy_conversion import LegacyConversionError, convert_legacy_secrets
from app.services.secret_store import EncryptedDatabaseSecretStore


TENANT = "tenant:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DISABLED = "tenant:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest.fixture()
def migration_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ph4c.db').as_posix()}")
    yield engine
    engine.dispose()


def _upgrade(engine, target):
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection=connection), target)


def _downgrade(engine, target):
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection=connection), target)


def _seed(engine):
    now = "2026-09-01T00:00:00+00:00"
    metadata = sa.MetaData()
    metadata.reflect(engine, only=["tenants", "change_sources", "webhook_endpoints"])
    with engine.begin() as connection:
        for tenant_id, status in ((TENANT, "active"), (DISABLED, "disabled")):
            connection.execute(metadata.tables["tenants"].insert().values(
                tenant_id=tenant_id, display_name=tenant_id, status=status,
                created_at=now, updated_at=now, created_by_subject="test",
            ))
        connection.execute(metadata.tables["change_sources"].insert().values(
            tenant_id=TENANT, source_id="source:legacy-github", name="Legacy GitHub",
            source_type="github", enabled=True, secret_ref="LEGACY_GITHUB_SECRET",
            config_json="{}", filters_json="{}", status="configured",
            delivery_count=0, failure_count=0, created_at=now, updated_at=now,
        ))
        connection.execute(metadata.tables["change_sources"].insert().values(
            tenant_id=DISABLED, source_id="source:disabled-github", name="Disabled",
            source_type="github", enabled=False, secret_ref="DISABLED_GITHUB_SECRET",
            config_json="{}", filters_json="{}", status="disabled",
            delivery_count=0, failure_count=0, created_at=now, updated_at=now,
        ))
        connection.execute(metadata.tables["webhook_endpoints"].insert().values(
            tenant_id=TENANT, webhook_id="webhook:legacy", name="Legacy webhook",
            url="https://example.test/topo", event_types_json='["incident.created"]',
            headers_json=json.dumps({"Authorization": "legacy-header-marker"}),
            signing_secret="legacy-signing-marker", active=True,
            timeout_seconds=10, max_attempts=3, created_at=now, updated_at=now,
        ))
        connection.execute(metadata.tables["webhook_endpoints"].insert().values(
            tenant_id=DISABLED, webhook_id="webhook:disabled", name="Disabled webhook",
            url="https://example.test/disabled", event_types_json='["incident.created"]',
            headers_json=json.dumps({"X-Key": "disabled-header-marker"}),
            signing_secret="disabled-signing-marker", active=True,
            timeout_seconds=10, max_attempts=3, created_at=now, updated_at=now,
        ))


def _manifest():
    return {
        "version": 1,
        "sources": [
            {
                "source_id": "source:legacy-github", "tenant_id": TENANT,
                "expected_provider": "github", "expected_legacy_env_name": "LEGACY_GITHUB_SECRET",
                "action": "import",
            },
            {
                "source_id": "source:disabled-github", "tenant_id": DISABLED,
                "expected_provider": "github", "expected_legacy_env_name": "DISABLED_GITHUB_SECRET",
                "action": "discard_and_disable",
            },
        ],
        "webhooks": [{
            "webhook_id": "webhook:disabled", "tenant_id": DISABLED,
            "action": "discard_and_disable",
        }],
    }


def _store():
    return EncryptedDatabaseSecretStore(SecretStoreConfiguration(
        "encrypted_db", SecretKeyring({"test": os.urandom(32)}, "test")
    ))


def test_fresh_final_schema_is_reference_only_and_exact(migration_engine):
    _upgrade(migration_engine, "head")
    inspector = inspect(migration_engine)
    source_columns = {column["name"] for column in inspector.get_columns("change_sources")}
    webhook_columns = {column["name"] for column in inspector.get_columns("webhook_endpoints")}
    assert "secret_ref" in source_columns
    assert {"signing_secret_ref", "protected_headers_secret_ref", "protected_header_names_json"} <= webhook_columns
    assert {"signing_secret", "headers_json"}.isdisjoint(webhook_columns)
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ("0011_secret_enforce",)
        assert schema_differences(connection) == ()


def test_0011_refuses_unconverted_then_conversion_is_atomic_and_rerunnable(migration_engine, monkeypatch):
    _upgrade(migration_engine, "0009_secret_store")
    _seed(migration_engine)
    _upgrade(migration_engine, "0010_secret_refs")
    with pytest.raises(RuntimeError, match="LEGACY_SECRET_CONVERSION_REQUIRED"):
        _upgrade(migration_engine, "0011_secret_enforce")
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ("0010_secret_refs",)

    manifest = _manifest()
    dry_run = convert_legacy_secrets(migration_engine, manifest)
    assert dry_run["mode"] == "dry_run" and dry_run["converted"] == 0
    monkeypatch.setenv("LEGACY_GITHUB_SECRET", "legacy-provider-marker")
    store = _store()
    applied = convert_legacy_secrets(migration_engine, manifest, apply=True, store=store)
    assert applied["converted"] == 2
    assert applied["discarded"] == 2
    repeated = convert_legacy_secrets(migration_engine, manifest, apply=True, store=store)
    assert all(item["status"] in {"already_converted", "already_discarded", "discarded"} for item in repeated["objects"])

    with migration_engine.connect() as connection:
        sources = sa.Table("change_sources", sa.MetaData(), autoload_with=connection)
        endpoints = sa.Table("webhook_endpoints", sa.MetaData(), autoload_with=connection)
        active = connection.execute(sa.select(sources).where(sources.c.tenant_id == TENANT)).mappings().one()
        disabled = connection.execute(sa.select(sources).where(sources.c.tenant_id == DISABLED)).mappings().one()
        webhook = connection.execute(sa.select(endpoints).where(endpoints.c.tenant_id == TENANT)).mappings().one()
        disabled_webhook = connection.execute(sa.select(endpoints).where(endpoints.c.tenant_id == DISABLED)).mappings().one()
        assert active["secret_ref"].startswith("secret:")
        assert disabled["secret_ref"] is None and disabled["enabled"] is False
        assert webhook["signing_secret"] is None and webhook["headers_json"] == "{}"
        assert webhook["signing_secret_ref"].startswith("secret:")
        assert webhook["protected_headers_secret_ref"].startswith("secret:")
        assert disabled_webhook["active"] is False
        assert disabled_webhook["signing_secret"] is None and disabled_webhook["headers_json"] == "{}"

    _upgrade(migration_engine, "0011_secret_enforce")
    assert {"signing_secret", "headers_json"}.isdisjoint(
        {column["name"] for column in inspect(migration_engine).get_columns("webhook_endpoints")}
    )


def test_manifest_mismatch_fails_before_environment_lookup(migration_engine, monkeypatch):
    _upgrade(migration_engine, "0009_secret_store")
    _seed(migration_engine)
    _upgrade(migration_engine, "0010_secret_refs")
    manifest = _manifest()
    manifest["sources"][0]["tenant_id"] = DISABLED

    def forbidden_get(*args, **kwargs):
        pytest.fail("environment lookup must occur only after exact row match")

    monkeypatch.setattr("app.services.secret_legacy_conversion.os.environ.get", forbidden_get)
    with pytest.raises(LegacyConversionError, match="LEGACY_SOURCE_MANIFEST_MISMATCH"):
        convert_legacy_secrets(migration_engine, manifest, apply=True, store=_store())


def test_converted_0010_cannot_downgrade_to_plaintext_authority(migration_engine, monkeypatch):
    _upgrade(migration_engine, "0009_secret_store")
    _seed(migration_engine)
    _upgrade(migration_engine, "0010_secret_refs")
    monkeypatch.setenv("LEGACY_GITHUB_SECRET", "legacy-provider-marker")
    convert_legacy_secrets(migration_engine, _manifest(), apply=True, store=_store())
    with pytest.raises(RuntimeError, match="SECRET_CONSUMER_REFERENCES_PREVENT_DOWNGRADE"):
        _downgrade(migration_engine, "0009_secret_store")
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ("0010_secret_refs",)


def test_postgresql_conversion_is_row_locked_rerunnable_and_reaches_final_head(monkeypatch):
    if not os.getenv("TOPO_TEST_POSTGRES_URL"):
        pytest.skip("set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 proof")
    from test_postgres_runtime_compatibility import _temporary_database

    with _temporary_database("ph4c_conversion") as engine:
        _upgrade(engine, "0009_secret_store")
        _seed(engine)
        _upgrade(engine, "0010_secret_refs")
        monkeypatch.setenv("LEGACY_GITHUB_SECRET", "postgres-provider-marker")
        configuration = SecretStoreConfiguration(
            "encrypted_db", SecretKeyring({"test": os.urandom(32)}, "test")
        )

        def convert():
            return convert_legacy_secrets(
                engine, _manifest(), apply=True,
                store=EncryptedDatabaseSecretStore(configuration),
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: convert(), range(2)))
        statuses = [item["status"] for result in results for item in result["objects"]]
        assert "converted" in statuses
        assert all(status in {
            "converted", "discarded", "already_converted", "already_discarded",
        } for status in statuses)
        _upgrade(engine, "0011_secret_enforce")
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0011_secret_enforce",)
            assert schema_differences(connection) == ()
