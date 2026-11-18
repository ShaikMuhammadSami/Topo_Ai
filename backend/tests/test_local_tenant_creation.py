from __future__ import annotations

import secrets

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.db.database import Base, get_session
from app.db.models import (
    IncidentRecord,
    SecurityAuditEventRecord,
    SnapshotRecord,
    TenantMembershipRecord,
)
from app.main import create_app
from app.security.auth_config import load_auth_configuration
from app.security.authorization_policy import TenantRole
from app.security.secret_keyring import (
    SecretKeyring,
    SecretStoreConfiguration,
)
from app.services.secret_store import EncryptedDatabaseSecretStore


@pytest.fixture()
def local_development_app(monkeypatch):
    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", "{}")
    monkeypatch.setenv("TOPO_BROWSER_ALLOWED_ORIGINS_JSON", "[]")
    configuration = load_auth_configuration(database_url="sqlite://")
    secret_store = EncryptedDatabaseSecretStore(
        SecretStoreConfiguration(
            "encrypted_db",
            SecretKeyring(
                {"test": secrets.token_bytes(32)},
                "test",
            ),
        )
    )
    monkeypatch.setattr(
        main_module,
        "load_secret_store_configuration",
        lambda: secret_store.configuration,
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    application = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=lambda: None,
        database_readiness_checker=lambda: True,
    )

    def override_get_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application, factory
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_empty_local_install_can_create_and_select_workspace(
    local_development_app,
) -> None:
    application, factory = local_development_app
    transport = httpx.ASGITransport(app=application)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            empty = await client.get("/api/v1/tenants")
            assert empty.status_code == 200
            assert empty.json() == []

            invalid = await client.post(
                "/api/v1/tenants",
                json={"display_name": " invalid"},
            )
            assert invalid.status_code == 422

            created = await client.post(
                "/api/v1/tenants",
                json={"display_name": "Local workspace"},
            )
            assert created.status_code == 201
            workspace = created.json()
            assert workspace["display_name"] == "Local workspace"
            assert workspace["status"] == "active"

            available = await client.get("/api/v1/tenants")
            assert available.status_code == 200
            assert available.json() == [workspace]

            tenant_headers = {
                "X-Topo-Tenant-ID": workspace["tenant_id"],
            }
            incidents = await client.get(
                "/api/v1/incidents",
                headers=tenant_headers,
            )
            snapshots = await client.get(
                "/api/v1/snapshots",
                headers=tenant_headers,
            )
            assert incidents.status_code == 200
            assert incidents.json() == []
            assert snapshots.status_code == 200
            assert snapshots.json() == []

    with factory() as session:
        membership = session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id
                == workspace["tenant_id"]
            )
        )
        assert membership is not None
        assert membership.role == TenantRole.ADMIN.value
        audit = session.scalar(
            select(SecurityAuditEventRecord).where(
                SecurityAuditEventRecord.action == "tenant.created",
                SecurityAuditEventRecord.tenant_id
                == workspace["tenant_id"],
            )
        )
        assert audit is not None
        assert audit.result == "allowed"
        assert session.scalars(select(IncidentRecord)).all() == []
        assert session.scalars(select(SnapshotRecord)).all() == []
