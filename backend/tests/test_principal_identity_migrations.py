from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db.schema_management import alembic_config, current_revisions


@pytest.fixture()
def migration_engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'principal-migration.db').as_posix()}"
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _upgrade(engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection=connection), revision)


def _downgrade(engine, revision: str) -> None:
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection=connection), revision)


def _seed_0011(connection) -> None:
    now = "2026-09-05T00:00:00+00:00"
    connection.execute(
        text(
            "INSERT INTO tenants (tenant_id, display_name, status, created_at, "
            "updated_at, created_by_subject) VALUES "
            "('tenant:11111111-1111-4111-8111-111111111111', 'Tenant', 'active', "
            ":now, :now, 'legacy-human')"
        ),
        {"now": now},
    )
    connection.execute(
        text(
            "INSERT INTO tenant_memberships (membership_id, tenant_id, subject, "
            "status, created_at, updated_at, created_by_subject) VALUES "
            "('membership:legacy', 'tenant:11111111-1111-4111-8111-111111111111', "
            "'legacy-human', 'active', :now, :now, 'legacy-human')"
        ),
        {"now": now},
    )
    connection.execute(
        text(
            "INSERT INTO auth_sessions (session_id, session_secret_digest, csrf_digest, "
            "subject, display_name, roles_json, source_authentication_type, "
            "source_credential_digest, issued_at, absolute_expires_at, idle_expires_at, "
            "last_seen_at, revoked_at) VALUES ('session:legacy', :session_digest, "
            ":csrf_digest, 'legacy-human', 'Legacy Human', '[\"admin\"]', 'api_token', "
            ":source_digest, :now, '2099-01-01T00:00:00+00:00', "
            "'2099-01-01T00:00:00+00:00', :now, NULL)"
        ),
        {
            "session_digest": "1" * 64,
            "csrf_digest": "2" * 64,
            "source_digest": "3" * 64,
            "now": now,
        },
    )
    for credential_id, caller_type, subject, digest in (
        ("credential:human", "human_api", "legacy-human", "4" * 64),
        ("credential:service", "service_api", "service-legacy", "5" * 64),
    ):
        connection.execute(
            text(
                "INSERT INTO auth_api_credentials (credential_id, "
                "credential_secret_digest, credential_hint, name, caller_type, subject, "
                "display_name, roles_json, created_at, created_by_subject, expires_at, "
                "revoked_at, revoked_by_subject, last_used_at, updated_at) VALUES "
                "(:credential_id, :digest, 'fixture', :credential_id, :caller_type, "
                ":subject, :subject, '[]', :now, 'legacy-human', "
                "'2099-01-01T00:00:00+00:00', NULL, NULL, NULL, :now)"
            ),
            {
                "credential_id": credential_id,
                "digest": digest,
                "caller_type": caller_type,
                "subject": subject,
                "now": now,
            },
        )
    connection.execute(
        text(
            "INSERT INTO service_api_tenant_bindings (binding_id, credential_id, "
            "tenant_id, created_at, created_by_subject) VALUES "
            "('binding:legacy', 'credential:service', "
            "'tenant:11111111-1111-4111-8111-111111111111', :now, 'legacy-human')"
        ),
        {"now": now},
    )


def test_fresh_sqlite_principal_migration_downgrade_and_reupgrade(
    migration_engine,
) -> None:
    _upgrade(migration_engine)
    assert current_revisions(migration_engine.connect()) == (
        "0014_min_authority",
    )
    assert {"auth_principals", "external_identities"} <= set(
        inspect(migration_engine).get_table_names()
    )
    _downgrade(migration_engine, "0012_principal_identity")
    assert "subject" in {
        column["name"]
        for column in inspect(migration_engine).get_columns("tenant_memberships")
    }
    _downgrade(migration_engine, "0011_secret_enforce")
    assert {"auth_principals", "external_identities"}.isdisjoint(
        inspect(migration_engine).get_table_names()
    )
    _upgrade(migration_engine)
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ("0014_min_authority",)


def test_populated_legacy_identity_backfill_reuses_human_and_separates_service(
    migration_engine,
) -> None:
    _upgrade(migration_engine, "0011_secret_enforce")
    with migration_engine.begin() as connection:
        _seed_0011(connection)
    _upgrade(migration_engine, "0012_principal_identity")
    with migration_engine.connect() as connection:
        membership = connection.scalar(
            text("SELECT principal_id FROM tenant_memberships")
        )
        session = connection.scalar(text("SELECT principal_id FROM auth_sessions"))
        human = connection.scalar(
            text(
                "SELECT principal_id FROM auth_api_credentials "
                "WHERE caller_type='human_api'"
            )
        )
        service = connection.scalar(
            text(
                "SELECT principal_id FROM auth_api_credentials "
                "WHERE caller_type='service_api'"
            )
        )
        assert membership == session == human
        assert service != human
        assert connection.scalar(
            text("SELECT COUNT(*) FROM auth_principals WHERE principal_type='human'")
        ) == 1
        assert connection.scalar(
            text("SELECT COUNT(*) FROM auth_principals WHERE principal_type='service'")
        ) == 1
        assert connection.scalar(
            text("SELECT COUNT(*) FROM external_identities")
        ) == 1

    _upgrade(migration_engine)
    columns = {
        column["name"]
        for column in inspect(migration_engine).get_columns("tenant_memberships")
    }
    assert "principal_id" in columns
    assert "subject" not in columns
    with migration_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM service_api_tenant_bindings b JOIN "
                "auth_api_credentials c ON c.credential_id=b.credential_id "
                "WHERE c.principal_id IS NOT NULL"
            )
        ) == 1

    _downgrade(migration_engine, "0012_principal_identity")
    with migration_engine.connect() as connection:
        assert connection.scalar(
            text("SELECT subject FROM tenant_memberships")
        ) == "legacy-human"
    _downgrade(migration_engine, "0011_secret_enforce")


def test_nonlegacy_external_identity_refuses_legacy_downgrade(
    migration_engine,
) -> None:
    _upgrade(migration_engine, "0012_principal_identity")
    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO auth_principals VALUES "
                "('principal:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'human', "
                "'External', 'active', :now, :now)"
            ),
            {"now": "2026-09-05T00:00:00+00:00"},
        )
        connection.execute(
            text(
                "INSERT INTO external_identities VALUES "
                "('identity:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', "
                "'principal:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', "
                "'urn:test:external', 'same', 'active', :now, :now)"
            ),
            {"now": "2026-09-05T00:00:00+00:00"},
        )
    with pytest.raises(RuntimeError, match="PRINCIPAL_IDENTITY_PREVENTS_DOWNGRADE"):
        _downgrade(migration_engine, "0011_secret_enforce")
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ("0012_principal_identity",)


def test_enforcement_preflight_fails_without_partial_schema_change(
    migration_engine,
) -> None:
    _upgrade(migration_engine, "0011_secret_enforce")
    with migration_engine.begin() as connection:
        _seed_0011(connection)
    _upgrade(migration_engine, "0012_principal_identity")
    with migration_engine.begin() as connection:
        human = connection.scalar(
            text(
                "SELECT principal_id FROM auth_principals "
                "WHERE principal_type='human'"
            )
        )
        connection.execute(
            text(
                "UPDATE auth_api_credentials SET principal_id=:human "
                "WHERE caller_type='service_api'"
            ),
            {"human": human},
        )
    with pytest.raises(RuntimeError, match="PRINCIPAL_IDENTITY_INTEGRITY_FAILURE"):
        _upgrade(migration_engine)
    assert "subject" in {
        column["name"]
        for column in inspect(migration_engine).get_columns("tenant_memberships")
    }
    with migration_engine.connect() as connection:
        assert current_revisions(connection) == ("0012_principal_identity",)
