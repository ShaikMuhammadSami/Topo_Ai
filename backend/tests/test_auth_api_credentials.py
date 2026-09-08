from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_session
from app.db.models import AuthApiCredentialRecord
from app.main import create_app
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.security.api_tokens import token_digest
from app.security.auth_config import (
    AuthConfigurationError,
    AuthConfigurationFailure,
    load_auth_configuration,
)
from app.security.session_auth import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from app.services.auth_api_credential_service import (
    AuthApiCredentialPersistenceError,
    create_auth_api_credential,
    credential_secret_digest,
)
from app.services.authority_assignments import grant_installation_operator
from app.services.principal_identity import provision_external_human_principal
import app.services.auth_api_credential_service as credential_service


ORIGIN = "https://topo.test"


@pytest.fixture()
def credential_app(monkeypatch):
    bootstrap = "bootstrap-test-" + secrets.token_urlsafe(48)
    registry = {
        token_digest(bootstrap): {
            "subject": "test:bootstrap-admin",
            "display_name": "Bootstrap Admin",
            "roles": ["admin"],
        }
    }
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", json.dumps(registry))
    monkeypatch.setenv(
        "TOPO_BROWSER_ALLOWED_ORIGINS_JSON",
        json.dumps([ORIGIN]),
    )
    configuration = load_auth_configuration(database_url="sqlite://")

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        principal = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:bootstrap-admin",
            display_name="Bootstrap Admin",
            authentication_type="api_token",
            roles=("admin",),
        )
        grant_installation_operator(
            session,
            principal_id=principal.principal_id,
        )
    application = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=lambda: None,
    )

    def override_get_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application, bootstrap, factory, configuration
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def _bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def _create(
    client: TestClient,
    bootstrap: str,
    *,
    caller_type: str = "human_api",
    subject: str = "test:bootstrap-admin",
    roles: list[str] | None = None,
    tenant_id: str | None = None,
):
    payload = {
        "name": "named operator",
        "caller_type": caller_type,
        "subject": subject,
        "display_name": "Named Operator",
        "roles": roles if roles is not None else ["admin"],
        "expires_in_days": 30,
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if caller_type == "service_api":
        payload["permissions"] = ["incident.read"]
    headers = _bearer(bootstrap)
    if tenant_id is not None:
        headers["X-Topo-Tenant-ID"] = tenant_id
    return client.post(
        "/api/v1/auth/api-credentials",
        headers=headers,
        json=payload,
    )


def test_admin_creates_digest_only_named_human_credential(
    credential_app,
    caplog,
) -> None:
    application, bootstrap, factory, _ = credential_app
    with TestClient(application) as client:
        created = _create(client, bootstrap)
        body = created.json()
        raw_secret = body["api_credential"]
        credential_id = body["credential_id"]

        assert created.status_code == 201
        assert raw_secret.startswith("topo_api_")
        assert raw_secret not in caplog.text
        assert body["caller_type"] == "human_api"
        assert "credential_secret_digest" not in body

        listing = client.get(
            "/api/v1/auth/api-credentials",
            headers=_bearer(bootstrap),
        )
        detail = client.get(
            f"/api/v1/auth/api-credentials/{credential_id}",
            headers=_bearer(bootstrap),
        )
        assert listing.status_code == detail.status_code == 200
        assert "api_credential" not in listing.text
        assert "credential_secret_digest" not in listing.text
        assert "api_credential" not in detail.text
        assert "credential_secret_digest" not in detail.text

    with factory() as session:
        record = session.scalars(select(AuthApiCredentialRecord)).one()
        persisted = "\n".join(
            str(getattr(record, column.name))
            for column in AuthApiCredentialRecord.__table__.columns
        )
        assert raw_secret not in persisted
        assert record.credential_secret_digest == credential_secret_digest(
            raw_secret
        )
        assert len(record.credential_secret_digest) == 64


def test_named_auth_updates_last_used_and_revocation_is_immediate(
    credential_app,
) -> None:
    application, bootstrap, factory, _ = credential_app
    with TestClient(application) as client:
        created = _create(client, bootstrap)
        raw_secret = created.json()["api_credential"]
        credential_id = created.json()["credential_id"]

        identity = client.get(
            "/api/v1/system/whoami",
            headers=_bearer(raw_secret),
        )
        assert identity.status_code == 200
        assert identity.json()["authentication_type"] == "human_api_token"

        revoked = client.post(
            f"/api/v1/auth/api-credentials/{credential_id}/revoke",
            headers=_bearer(raw_secret),
        )
        assert revoked.status_code == 200
        assert revoked.json()["revoked_by_subject"] == "test:bootstrap-admin"
        assert client.get(
            "/api/v1/system/whoami",
            headers=_bearer(raw_secret),
        ).status_code == 401

    with factory() as session:
        record = session.get(AuthApiCredentialRecord, credential_id)
        assert record is not None
        assert record.last_used_at is not None
        assert record.revoked_at is not None


def test_named_human_session_is_invalidated_by_source_revocation(
    credential_app,
) -> None:
    application, bootstrap, _, _ = credential_app
    with TestClient(application, base_url=ORIGIN) as client:
        created = _create(client, bootstrap)
        raw_secret = created.json()["api_credential"]
        credential_id = created.json()["credential_id"]

        login = client.post(
            "/api/v1/auth/session",
            headers={**_bearer(raw_secret), "Origin": ORIGIN},
        )
        assert login.status_code == 201
        assert client.cookies.get(SESSION_COOKIE_NAME)
        assert client.cookies.get(CSRF_COOKIE_NAME)
        assert client.get("/api/v1/auth/session").status_code == 200

        revoked = client.post(
            f"/api/v1/auth/api-credentials/{credential_id}/revoke",
            headers=_bearer(bootstrap),
        )
        assert revoked.status_code == 200
        assert client.get("/api/v1/auth/session").status_code == 401


def test_service_credential_is_api_only_and_cannot_manage_credentials(
    credential_app,
) -> None:
    application, bootstrap, _, _ = credential_app
    with TestClient(application, base_url=ORIGIN) as client:
        tenant = client.post(
            "/api/v1/tenants",
            headers=_bearer(bootstrap),
            json={"display_name": "PH-2E regression tenant"},
        )
        assert tenant.status_code == 201
        created = _create(
            client,
            bootstrap,
            caller_type="service_api",
            subject="service:automation",
            roles=["admin"],
            tenant_id=tenant.json()["tenant_id"],
        )
        raw_secret = created.json()["api_credential"]

        identity = client.get(
            "/api/v1/system/whoami",
            headers=_bearer(raw_secret),
        )
        assert identity.status_code == 200
        assert identity.json()["authentication_type"] == "service_api_token"
        assert client.post(
            "/api/v1/auth/session",
            headers={**_bearer(raw_secret), "Origin": ORIGIN},
        ).status_code == 403
        assert client.get(
            "/api/v1/auth/api-credentials",
            headers=_bearer(raw_secret),
        ).status_code == 403
        assert client.get(
            "/api/v1/agent/config",
            headers=_bearer(raw_secret),
        ).status_code == 401
        assert client.post(
            "/api/v1/change-source-webhooks/unknown",
            headers=_bearer(raw_secret),
            content=b"{}",
        ).status_code in {401, 404}


def test_expired_unknown_and_other_human_targets_fail_closed(
    credential_app,
) -> None:
    application, bootstrap, factory, _ = credential_app
    with factory() as session:
        expired = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="expired",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                subject="test:expired",
                roles=["admin"],
                expires_in_days=1,
            ),
            created_by_subject="test:bootstrap-admin",
            now=datetime(2020, 1, 1, tzinfo=UTC),
        )

    with TestClient(application) as client:
        assert client.get(
            "/api/v1/system/whoami",
            headers=_bearer(expired.api_credential),
        ).status_code == 401
        assert client.get(
            "/api/v1/system/whoami",
            headers=_bearer("topo_api_" + secrets.token_urlsafe(48)),
        ).status_code == 401

        other_human = _create(
            client,
            bootstrap,
            subject="test:viewer",
            roles=["viewer"],
        )
        assert other_human.status_code == 403


@pytest.mark.parametrize("days", [0, 91])
def test_credential_expiration_bounds_are_enforced(
    credential_app,
    days: int,
) -> None:
    application, bootstrap, _, _ = credential_app
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/auth/api-credentials",
            headers=_bearer(bootstrap),
            json={
                "name": "invalid expiry",
                "caller_type": "human_api",
                "subject": "test:expiry",
                "roles": [],
                "expires_in_days": days,
            },
        )
    assert response.status_code == 422


def test_required_startup_uses_durable_admin_after_schema_validation(
    credential_app,
    monkeypatch,
) -> None:
    _, _, factory, _ = credential_app
    with factory() as session:
        created = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="restart authority",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                subject="test:restart-admin",
                roles=["admin"],
                expires_in_days=30,
            ),
            created_by_subject="test:bootstrap-admin",
        )

    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", "{}")
    configuration = load_auth_configuration(database_url="sqlite://")
    order: list[str] = []

    def validated_initializer() -> None:
        order.append("schema")

    restarted = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=validated_initializer,
    )
    with TestClient(restarted) as client:
        assert order == ["schema"]
        identity = client.get(
            "/api/v1/system/whoami",
            headers=_bearer(created.api_credential),
        )
        assert identity.status_code == 200
        assert identity.json()["subject"] == "test:restart-admin"


def test_bootstrap_removal_preserves_named_authority_and_invalidates_only_bootstrap_session(
    credential_app,
    monkeypatch,
) -> None:
    application, bootstrap, factory, _ = credential_app
    with TestClient(application, base_url=ORIGIN) as bootstrap_client:
        created = _create(bootstrap_client, bootstrap)
        raw_named = created.json()["api_credential"]
        assert bootstrap_client.post(
            "/api/v1/auth/session",
            headers={**_bearer(bootstrap), "Origin": ORIGIN},
        ).status_code == 201
        bootstrap_session = bootstrap_client.cookies.get(SESSION_COOKIE_NAME)

    with TestClient(application, base_url=ORIGIN) as named_client:
        assert named_client.post(
            "/api/v1/auth/session",
            headers={**_bearer(raw_named), "Origin": ORIGIN},
        ).status_code == 201
        named_session = named_client.cookies.get(SESSION_COOKIE_NAME)

    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", "{}")
    configuration = load_auth_configuration(database_url="sqlite://")
    restarted = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=lambda: None,
    )
    with TestClient(restarted, base_url=ORIGIN) as client:
        client.cookies.set(SESSION_COOKIE_NAME, bootstrap_session)
        assert client.get("/api/v1/auth/session").status_code == 401

        client.cookies.set(SESSION_COOKIE_NAME, named_session)
        assert client.get("/api/v1/auth/session").status_code == 200
        assert client.get(
            "/api/v1/system/whoami",
            headers=_bearer(raw_named),
        ).status_code == 200


def test_required_startup_without_any_human_admin_fails_closed(
    credential_app,
    monkeypatch,
) -> None:
    _, _, factory, _ = credential_app
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", "{}")
    configuration = load_auth_configuration(database_url="sqlite://")
    application = create_app(
        auth_configuration=configuration,
        session_factory=factory,
        database_initializer=lambda: None,
    )

    with pytest.raises(AuthConfigurationError) as raised:
        with TestClient(application):
            pass
    assert raised.value.category is AuthConfigurationFailure.EMPTY_REQUIRED_AUTHORITY


def test_generation_collision_retries_are_bounded(
    credential_app,
    monkeypatch,
) -> None:
    _, _, factory, _ = credential_app
    calls = 0

    def colliding_secret(_: int) -> str:
        nonlocal calls
        calls += 1
        return "generated-collision-material"

    monkeypatch.setattr(credential_service.secrets, "token_urlsafe", colliding_secret)
    request = ApiCredentialCreate(
        name="collision",
        caller_type=ApiCredentialCallerType.HUMAN_API,
        subject="test:collision",
        roles=[],
        expires_in_days=1,
    )
    with factory() as session:
        create_auth_api_credential(
            session,
            request=request,
            created_by_subject="test:bootstrap-admin",
        )
        with pytest.raises(AuthApiCredentialPersistenceError):
            create_auth_api_credential(
                session,
                request=request,
                created_by_subject="test:bootstrap-admin",
            )

    assert calls == 4
