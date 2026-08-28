from __future__ import annotations

import json
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.auth as auth_api
import app.api.change_source_webhooks as webhook_api
import app.db.database as database
import app.security.agent_tokens as agent_security
from app.db.database import Base, get_session
from app.db.models import AgentEnrollmentTokenRecord, AuthSessionRecord
from app.main import create_app
from app.security.api_tokens import AuthPrincipal, token_digest
from app.security.auth_config import (
    AuthConfigurationError,
    AuthConfigurationFailure,
    load_auth_configuration,
)
from app.security.session_auth import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from app.services.auth_session_service import (
    AuthSessionPersistenceError,
    create_auth_session,
    resolve_auth_session,
    revoke_auth_session,
    touch_auth_session,
)
from app.services.webhook_security import WebhookAuthenticationError


ORIGIN = "https://topo.test"


@pytest.fixture()
def session_app(monkeypatch):
    bootstrap = "topo-test-bootstrap-" + secrets.token_urlsafe(40)
    viewer_bootstrap = "topo-test-viewer-" + secrets.token_urlsafe(40)
    registry = {
        token_digest(bootstrap): {
            "subject": "test:browser-operator",
            "display_name": "Browser Operator",
            "roles": ["admin", "operator"],
        },
        token_digest(viewer_bootstrap): {
            "subject": "test:browser-viewer",
            "display_name": "Browser Viewer",
            "roles": ["viewer"],
        },
    }
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", json.dumps(registry))
    monkeypatch.setenv(
        "TOPO_BROWSER_ALLOWED_ORIGINS_JSON",
        json.dumps([ORIGIN]),
    )
    monkeypatch.setenv("TOPO_SESSION_ABSOLUTE_TTL_MINUTES", "480")
    monkeypatch.setenv("TOPO_SESSION_IDLE_TTL_MINUTES", "60")
    configuration = load_auth_configuration(database_url="sqlite://")

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
    )

    def override_get_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    try:
        yield application, bootstrap, viewer_bootstrap, factory, configuration
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def _login(client: TestClient, bootstrap: str, *, origin: str = ORIGIN):
    return client.post(
        "/api/v1/auth/session",
        headers={
            "Authorization": f"Bearer {bootstrap}",
            "Origin": origin,
        },
    )


def test_valid_human_bearer_creates_digest_only_secure_session(session_app) -> None:
    application, bootstrap, _, factory, _ = session_app
    with TestClient(application, base_url=ORIGIN) as client:
        response = _login(client, bootstrap)
        raw_session = client.cookies.get(SESSION_COOKIE_NAME)
        raw_csrf = client.cookies.get(CSRF_COOKIE_NAME)

    assert response.status_code == 201
    assert response.json() == {
        "subject": "test:browser-operator",
        "display_name": "Browser Operator",
        "roles": ["admin", "operator"],
        "authentication_type": "session",
        "absolute_expires_at": response.json()["absolute_expires_at"],
    }
    assert raw_session and raw_csrf
    assert bootstrap not in response.text
    assert raw_session not in response.text
    assert raw_csrf not in response.text

    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("topo_session="))
    csrf_cookie = next(value for value in cookies if value.startswith("topo_csrf="))
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Secure" in csrf_cookie
    assert "SameSite=lax" in csrf_cookie

    with factory() as session:
        record = session.scalars(select(AuthSessionRecord)).one()
        persisted = "\n".join(
            str(getattr(record, column.name))
            for column in AuthSessionRecord.__table__.columns
        )
        assert raw_session not in persisted
        assert raw_csrf not in persisted
        assert bootstrap not in persisted
        assert len(record.session_secret_digest) == 64
        assert len(record.csrf_digest) == 64
        assert json.loads(record.roles_json) == ["admin", "operator"]


def test_non_admin_human_bearer_can_create_a_session(session_app) -> None:
    application, _, viewer_bootstrap, _, _ = session_app
    with TestClient(application, base_url=ORIGIN) as client:
        response = _login(client, viewer_bootstrap)

    assert response.status_code == 201
    assert response.json()["subject"] == "test:browser-viewer"
    assert response.json()["roles"] == ["viewer"]


def test_login_rejections_and_origin_validation_are_fail_closed(
    session_app,
    monkeypatch,
) -> None:
    application, bootstrap, _, _, _ = session_app
    with TestClient(application, base_url=ORIGIN) as client:
        assert client.post("/api/v1/auth/session").status_code == 401
        assert client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Basic invalid"},
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer invalid"},
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer agent-only"},
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer provider-webhook-secret"},
        ).status_code == 401
        mismatch = _login(client, bootstrap, origin="https://untrusted.example")
        assert mismatch.status_code == 403
        assert SESSION_COOKIE_NAME not in mismatch.cookies

        monkeypatch.setattr(
            auth_api,
            "create_auth_session",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AuthSessionPersistenceError("synthetic persistence failure")
            ),
        )
        failure = _login(client, bootstrap)
        assert failure.status_code == 503
        assert not any(
            value.startswith("topo_session=")
            for value in failure.headers.get_list("set-cookie")
        )


def test_fresh_logins_create_independent_random_sessions(session_app) -> None:
    application, bootstrap, _, factory, _ = session_app
    with TestClient(application, base_url=ORIGIN) as first:
        assert _login(first, bootstrap).status_code == 201
        first_secret = first.cookies.get(SESSION_COOKIE_NAME)
    with TestClient(application, base_url=ORIGIN) as second:
        assert _login(second, bootstrap).status_code == 201
        second_secret = second.cookies.get(SESSION_COOKIE_NAME)

    assert first_secret != second_secret
    with factory() as session:
        records = session.scalars(select(AuthSessionRecord)).all()
        assert len(records) == 2
        assert len({record.session_secret_digest for record in records}) == 2


def test_session_introspection_precedence_csrf_and_logout(session_app) -> None:
    application, bootstrap, _, factory, _ = session_app
    with TestClient(application, base_url=ORIGIN) as client:
        assert _login(client, bootstrap).status_code == 201
        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        introspection = client.get("/api/v1/auth/session")
        assert introspection.status_code == 200
        assert introspection.json()["authentication_type"] == "session"

        explicit_invalid = client.get(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer explicit-invalid"},
        )
        assert explicit_invalid.status_code == 401

        target = "/api/v1/agents/enrollment-tokens"
        assert client.post(target, json={"max_uses": 1}).status_code == 403
        assert client.post(
            target,
            json={"max_uses": 1},
            headers={"X-Topo-CSRF": "wrong"},
        ).status_code == 403
        accepted = client.post(
            target,
            json={"max_uses": 1},
            headers={"X-Topo-CSRF": csrf},
        )
        assert accepted.status_code == 201

        bearer_post = client.post(
            target,
            json={"max_uses": 1},
            headers={"Authorization": f"Bearer {bootstrap}"},
        )
        assert bearer_post.status_code == 201

        logout = client.delete(
            "/api/v1/auth/session",
            headers={"X-Topo-CSRF": csrf},
        )
        assert logout.status_code == 204
        assert logout.content == b""
        assert any(
            value.startswith("topo_session=") and "Max-Age=0" in value
            for value in logout.headers.get_list("set-cookie")
        )
        assert any(
            value.startswith("topo_csrf=") and "Max-Age=0" in value
            for value in logout.headers.get_list("set-cookie")
        )
        assert client.get("/api/v1/auth/session").status_code == 401

    with factory() as session:
        record = session.scalars(select(AuthSessionRecord)).one()
        assert record.revoked_at is not None
        enrollment_records = session.scalars(
            select(AgentEnrollmentTokenRecord)
        ).all()
        assert len(enrollment_records) == 2


def test_session_app_isolates_agent_route_from_default_database(
    session_app,
    monkeypatch,
) -> None:
    application, bootstrap, _, factory, _ = session_app

    def reject_default_database_access():
        raise AssertionError("default product SessionLocal was accessed")

    monkeypatch.setattr(database, "SessionLocal", reject_default_database_access)

    with TestClient(application, base_url=ORIGIN) as client:
        assert _login(client, bootstrap).status_code == 201
        csrf = client.cookies.get(CSRF_COOKIE_NAME)
        response = client.post(
            "/api/v1/agents/enrollment-tokens",
            json={"max_uses": 1},
            headers={"X-Topo-CSRF": csrf},
        )

    assert response.status_code == 201
    with factory() as session:
        assert session.scalars(select(AuthSessionRecord)).one()
        enrollment = session.scalars(select(AgentEnrollmentTokenRecord)).one()
        assert enrollment.max_uses == 1
        assert enrollment.use_count == 0
        assert enrollment.revoked_at is None


def test_expired_revoked_unknown_and_source_invalid_sessions_fail_closed(
    session_app,
) -> None:
    _, _, _, factory, configuration = session_app
    principal = AuthPrincipal(
        subject="test:browser-operator",
        display_name="Browser Operator",
        roles=("admin", "operator"),
        authentication_type="api_token",
    )
    now = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    source_digest = next(iter(configuration.token_registry))

    with factory() as session:
        issued = create_auth_session(
            session,
            configuration=configuration,
            source_principal=principal,
            source_credential_digest=source_digest,
            now=now,
        )
        assert resolve_auth_session(
            session,
            configuration=configuration,
            raw_session_secret="unknown-session",
            now=now,
        ) is None
        assert resolve_auth_session(
            session,
            configuration=configuration,
            raw_session_secret=issued.session_secret,
            now=now + timedelta(minutes=61),
        ) is None

        issued.record.idle_expires_at = (now + timedelta(hours=7)).isoformat()
        session.commit()
        assert resolve_auth_session(
            session,
            configuration=configuration,
            raw_session_secret=issued.session_secret,
            now=now + timedelta(hours=8),
        ) is None

        removed_source = replace(
            configuration,
            token_registry=MappingProxyType({}),
        )
        assert resolve_auth_session(
            session,
            configuration=removed_source,
            raw_session_secret=issued.session_secret,
            now=now,
        ) is None

        revoke_auth_session(session, record=issued.record, now=now)
        assert resolve_auth_session(
            session,
            configuration=configuration,
            raw_session_secret=issued.session_secret,
            now=now,
        ) is None


def test_successful_session_touch_renews_idle_expiry_but_not_absolute_expiry(
    session_app,
) -> None:
    _, _, _, factory, configuration = session_app
    principal = AuthPrincipal(
        subject="test:browser-operator",
        display_name="Browser Operator",
        roles=("admin", "operator"),
        authentication_type="api_token",
    )
    issued_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    touched_at = issued_at + timedelta(minutes=30)
    source_digest = next(
        digest
        for digest, identity in configuration.token_registry.items()
        if identity.subject == principal.subject
    )

    with factory() as session:
        issued = create_auth_session(
            session,
            configuration=configuration,
            source_principal=principal,
            source_credential_digest=source_digest,
            now=issued_at,
        )
        absolute_expiry = issued.record.absolute_expires_at
        touch_auth_session(
            session,
            configuration=configuration,
            record=issued.record,
            now=touched_at,
        )

        assert issued.record.last_seen_at == touched_at.isoformat()
        assert issued.record.idle_expires_at == (
            touched_at + timedelta(minutes=60)
        ).isoformat()
        assert issued.record.absolute_expires_at == absolute_expiry


@pytest.mark.parametrize(
    ("absolute", "idle"),
    [("0", "1"), ("abc", "1"), ("60", "61"), ("10081", "1")],
)
def test_session_ttl_configuration_is_bounded(
    monkeypatch,
    absolute: str,
    idle: str,
) -> None:
    token = secrets.token_urlsafe(40)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(token): {
                    "subject": "test:ttl",
                    "roles": [],
                }
            }
        ),
    )
    monkeypatch.setenv("TOPO_SESSION_ABSOLUTE_TTL_MINUTES", absolute)
    monkeypatch.setenv("TOPO_SESSION_IDLE_TTL_MINUTES", idle)

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")
    assert raised.value.category is AuthConfigurationFailure.INVALID_SESSION_TTL


@pytest.mark.parametrize(
    "value",
    ["*", '["*"]', '["https://example.com/"]', '["ftp://example.com"]'],
)
def test_browser_origin_configuration_rejects_wildcard_and_non_origins(
    monkeypatch,
    value: str,
) -> None:
    token = secrets.token_urlsafe(40)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(token): {
                    "subject": "test:origin",
                    "roles": [],
                }
            }
        ),
    )
    monkeypatch.setenv("TOPO_BROWSER_ALLOWED_ORIGINS_JSON", value)

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")
    assert raised.value.category is AuthConfigurationFailure.INVALID_BROWSER_ORIGINS


def test_missing_browser_origin_configuration_denies_browser_exchange(
    session_app,
) -> None:
    _, bootstrap, _, factory, configuration = session_app
    application = create_app(
        auth_configuration=replace(
            configuration,
            browser_allowed_origins=(),
        ),
        session_factory=factory,
        database_initializer=lambda: None,
    )

    with TestClient(application, base_url=ORIGIN) as client:
        response = _login(client, bootstrap)

    assert response.status_code == 403
    assert SESSION_COOKIE_NAME not in response.cookies


def test_development_mode_introspects_without_persisting_a_session(monkeypatch) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)
    application = create_app(database_initializer=lambda: None)
    client = TestClient(application, base_url=ORIGIN)

    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["authentication_type"] == "development"
    assert client.post("/api/v1/auth/session").status_code == 403


def test_session_cookie_never_authenticates_agent_or_provider(
    session_app,
    monkeypatch,
) -> None:
    application, bootstrap, _, _, _ = session_app
    agent_record = SimpleNamespace(
        agent_id="agent:test",
        collection_interval_seconds=30,
        heartbeat_interval_seconds=10,
        namespace_scope_json="[]",
    )
    monkeypatch.setattr(
        agent_security,
        "authenticate_agent",
        lambda *, session, token: agent_record if token == "agent-only" else None,
    )
    monkeypatch.setattr(
        webhook_api,
        "load_change_source",
        lambda *args, **kwargs: SimpleNamespace(source_id="source:test"),
    )

    def reject_provider(*args, **kwargs):
        raise WebhookAuthenticationError("provider authority still required")

    monkeypatch.setattr(webhook_api, "ingest_change_source_webhook", reject_provider)
    with TestClient(application, base_url=ORIGIN) as client:
        assert _login(client, bootstrap).status_code == 201
        assert client.get("/api/v1/agent/config").status_code == 401
        assert client.post(
            "/api/v1/change-source-webhooks/source%3Atest",
            content=b"{}",
        ).status_code == 401
