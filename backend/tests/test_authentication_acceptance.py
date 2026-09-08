from __future__ import annotations
from domain_tenant_fixtures import TEST_TENANT, TEST_HEADERS, seed_domain_tenant

import hashlib
import hmac
import json
import secrets
from collections import Counter
from dataclasses import replace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_session
from app.db.models import (
    AuthApiCredentialRecord,
    AuthSessionRecord,
    ChangeSourceRecord,
)
from app.main import create_app
from app import main as main_module
from app.models.secret_store import SecretMaterial
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.services.secret_consumer_policy import source_binding
from app.services.secret_store import EncryptedDatabaseSecretStore
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.services.authority_assignments import grant_installation_operator
from app.services.principal_identity import provision_external_human_principal
from app.security.api_tokens import token_digest
from app.security.auth_config import AuthMode, load_auth_configuration
from app.security.auth_routing import RouteAuthDomain, classify_route


ORIGIN = "https://topo.test"
@pytest.fixture()
def acceptance_app(monkeypatch):
    bootstrap = "ph2f-bootstrap-" + secrets.token_urlsafe(48)
    provider_secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(bootstrap): {
                    "subject": "test:bootstrap-admin",
                    "display_name": "Bootstrap Admin",
                    "roles": ["admin", "operator"],
                }
            }
        ),
    )
    monkeypatch.setenv(
        "TOPO_BROWSER_ALLOWED_ORIGINS_JSON",
        json.dumps([ORIGIN]),
    )
    configuration = load_auth_configuration(database_url="sqlite://")
    store = EncryptedDatabaseSecretStore(SecretStoreConfiguration(
        "encrypted_db", SecretKeyring({"test": secrets.token_bytes(32)}, "test")
    ))
    monkeypatch.setattr(main_module, "load_secret_store_configuration", lambda: store.configuration)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine, subject="test:bootstrap-admin")
    with session_factory() as session:
        principal = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:bootstrap-admin",
            display_name="Bootstrap Admin",
            authentication_type="api_token",
            roles=("admin", "operator"),
        )
        grant_installation_operator(
            session, principal_id=principal.principal_id or ""
        )
    application = create_app(
        auth_configuration=configuration,
        session_factory=session_factory,
        database_initializer=lambda: None,
    )

    def override_get_session():
        with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    with session_factory() as session:
        record = ChangeSourceRecord(
                tenant_id=TEST_TENANT,
                source_id="source:ph2f-github",
                name="PH-2F GitHub source",
                source_type="github",
                enabled=True,
                secret_ref=None,
                config_json="{}",
                filters_json="{}",
                status="configured",
                delivery_count=0,
                failure_count=0,
                created_at="2026-08-30T00:00:00+00:00",
                updated_at="2026-08-30T00:00:00+00:00",
            )
        record.secret_ref = store.put(
            session,
            source_binding(
                tenant_id=TEST_TENANT, source_id=record.source_id,
                source_type=record.source_type, config={},
            ),
            SecretMaterial(provider_secret.encode()),
            operation_id="test:ph2f-provider", actor="test",
        ).secret_ref
        session.add(record)
        session.commit()

    try:
        yield (
            application,
            session_factory,
            configuration,
            bootstrap,
            provider_secret,
        )
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def _bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def _create_named(
    client: TestClient,
    bootstrap: str,
    *,
    name: str,
    caller_type: str,
    subject: str,
    roles: list[str],
    tenant_id: str | None = None,
) -> dict:
    payload = {
        "name": name,
        "caller_type": caller_type,
        "subject": subject,
        "display_name": name,
        "roles": roles,
        "expires_in_days": 30,
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if caller_type == "service_api":
        payload["permissions"] = ["incident.read"]
    headers = _bearer(bootstrap)
    if tenant_id is not None:
        headers["X-Topo-Tenant-ID"] = tenant_id
    response = client.post(
        "/api/v1/auth/api-credentials",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _provider_headers(secret: str, body: bytes) -> dict[str, str]:
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-GitHub-Event": "ping",
        "X-GitHub-Delivery": "ph2f-trust-matrix",
        "X-Hub-Signature-256": f"sha256={signature}",
    }


def _registered_routes(application) -> list:
    routes: list = []
    for route in application.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is None:
            routes.append(route)
        else:
            routes.extend(
                child
                for child in original_router.routes
                if isinstance(child, APIRoute)
            )
    return routes


def test_route_domain_inventory_is_complete_and_production_docs_are_absent(
    acceptance_app,
) -> None:
    application, _, configuration, _, _ = acceptance_app
    production_routes = _registered_routes(application)
    production_pairs = [
        (method, route.path, classify_route(method, route.path))
        for route in production_routes
        for method in route.methods
    ]

    assert len(production_routes) == 143
    assert len(production_pairs) == 143
    assert sum(path.startswith("/api/") for _, path, _ in production_pairs) == 141
    assert Counter(
        domain for _, _, domain in production_pairs
    ) == Counter(
        {
            RouteAuthDomain.PUBLIC_LIVENESS: 1,
            RouteAuthDomain.PUBLIC_READINESS_MINIMAL: 1,
            RouteAuthDomain.USER_AUTHENTICATED: 132,
            RouteAuthDomain.AGENT_AUTHENTICATED: 8,
            RouteAuthDomain.PROVIDER_CALLBACK_AUTHENTICATED: 1,
        }
    )
    assert not any(
        path.startswith("/api/") and domain is None
        for _, path, domain in production_pairs
    )
    assert not {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }.intersection(path for _, path, _ in production_pairs)

    development = create_app(
        auth_configuration=replace(
            configuration,
            mode=AuthMode.DEVELOPMENT_DISABLED,
        ),
        database_initializer=lambda: None,
    )
    development_pairs = [
        (method, route.path, classify_route(method, route.path))
        for route in _registered_routes(development)
        for method in route.methods
    ]
    assert len(_registered_routes(development)) == 147
    assert len(development_pairs) == 151
    assert sum(
        domain is RouteAuthDomain.DISABLED_PRODUCTION
        for _, _, domain in development_pairs
    ) == 8
    assert classify_route(
        "OPTIONS", "/api/v1/auth/api-credentials"
    ) is RouteAuthDomain.PUBLIC_CORS_PREFLIGHT


def test_all_current_caller_classes_are_bounded_to_their_trust_domain(
    acceptance_app,
) -> None:
    application, session_factory, _, bootstrap, provider_secret = acceptance_app
    with TestClient(application, base_url=ORIGIN) as client:
        tenant = client.post(
            "/api/v1/tenants",
            headers=_bearer(bootstrap),
            json={"display_name": "PH-2F regression tenant"},
        )
        assert tenant.status_code == 201
        named_admin = _create_named(
            client,
            bootstrap,
            name="Named Admin",
            caller_type="human_api",
            subject="test:bootstrap-admin",
            roles=["admin"],
        )
        named_viewer = _create_named(
            client,
            bootstrap,
            name="Named Viewer",
            caller_type="human_api",
            subject="test:bootstrap-admin",
            roles=["viewer"],
        )
        named_service = _create_named(
            client,
            bootstrap,
            name="Named Service",
            caller_type="service_api",
            subject="service:ph2f",
            roles=["admin"],
            tenant_id=tenant.json()["tenant_id"],
        )

        enrollment = client.post(
            "/api/v1/agents/enrollment-tokens",
            headers={**_bearer(bootstrap), "X-Topo-Tenant-ID": tenant.json()["tenant_id"]},
            json={"label": "PH-2F matrix", "max_uses": 1},
        )
        assert enrollment.status_code == 201
        enrollment_secret = enrollment.json()["enrollment_token"]

        observed: dict[str, int] = {}

        # A. Anonymous.
        observed["anonymous_public"] = client.get("/health").status_code
        observed["anonymous_human"] = client.get(
            "/api/v1/system/whoami"
        ).status_code
        observed["anonymous_agent"] = client.get(
            "/api/v1/agent/config"
        ).status_code
        observed["anonymous_provider"] = client.post(
            "/api/v1/change-source-webhooks/source%3Aph2f-github",
            content=b"{}",
        ).status_code

        # B-E. Static bootstrap, named human admin/non-admin, and service API.
        human_callers = {
            "bootstrap": bootstrap,
            "named_admin": named_admin["api_credential"],
            "named_viewer": named_viewer["api_credential"],
            "service": named_service["api_credential"],
        }
        for caller, secret in human_callers.items():
            observed[f"{caller}_human"] = client.get(
                "/api/v1/system/whoami",
                headers=_bearer(secret),
            ).status_code
            observed[f"{caller}_admin"] = client.get(
                "/api/v1/auth/api-credentials",
                headers=_bearer(secret),
            ).status_code
            observed[f"{caller}_agent"] = client.get(
                "/api/v1/agent/config",
                headers=_bearer(secret),
            ).status_code
            observed[f"{caller}_provider"] = client.post(
                "/api/v1/change-source-webhooks/source%3Aph2f-github",
                headers=_bearer(secret),
                content=b"{}",
            ).status_code

        observed["service_session"] = client.post(
            "/api/v1/auth/session",
            headers={
                **_bearer(named_service["api_credential"]),
                "Origin": ORIGIN,
            },
        ).status_code

        # H. Enrollment credentials are body-bound and cannot become bearer auth.
        observed["enrollment_human"] = client.get(
            "/api/v1/system/whoami",
            headers=_bearer(enrollment_secret),
        ).status_code
        observed["enrollment_agent"] = client.get(
            "/api/v1/agent/config",
            headers=_bearer(enrollment_secret),
        ).status_code
        enrolled = client.post(
            "/api/v1/agents/enroll",
            json={
                "enrollment_token": enrollment_secret,
                "name": "ph2f-agent",
                "cluster_name": "ph2f-cluster",
                "environment": "test",
                "version": "1.0.0",
                "namespace_scope": ["payments"],
            },
        )
        observed["enrollment_domain"] = enrolled.status_code
        agent_secret = enrolled.json()["agent_token"]

        # I. Steady-state agent credentials remain agent-only.
        observed["agent_agent"] = client.get(
            "/api/v1/agent/config",
            headers=_bearer(agent_secret),
        ).status_code
        observed["agent_human"] = client.get(
            "/api/v1/system/whoami",
            headers=_bearer(agent_secret),
        ).status_code
        observed["agent_provider"] = client.post(
            "/api/v1/change-source-webhooks/source%3Aph2f-github",
            headers=_bearer(agent_secret),
            content=b"{}",
        ).status_code

        # J. Provider material remains callback-only.
        provider_body = b"{}"
        provider_headers = _provider_headers(provider_secret, provider_body)
        observed["provider_provider"] = client.post(
            "/api/v1/change-source-webhooks/source%3Aph2f-github",
            headers=provider_headers,
            content=provider_body,
        ).status_code
        observed["provider_human"] = client.get(
            "/api/v1/system/whoami",
            headers=provider_headers,
        ).status_code
        observed["provider_agent"] = client.get(
            "/api/v1/agent/config",
            headers=provider_headers,
        ).status_code

    # F-G. Browser sessions retain their human authority but never cross domains.
    session_callers = {
        "bootstrap_session": bootstrap,
        "named_session": named_admin["api_credential"],
    }
    for caller, source_secret in session_callers.items():
        with TestClient(application, base_url=ORIGIN) as session_client:
            login = session_client.post(
                "/api/v1/auth/session",
                headers={**_bearer(source_secret), "Origin": ORIGIN},
            )
            assert login.status_code == 201
            observed[f"{caller}_human"] = session_client.get(
                "/api/v1/system/whoami"
            ).status_code
            observed[f"{caller}_admin"] = session_client.get(
                "/api/v1/auth/api-credentials"
            ).status_code
            observed[f"{caller}_agent"] = session_client.get(
                "/api/v1/agent/config"
            ).status_code
            observed[f"{caller}_provider"] = session_client.post(
                "/api/v1/change-source-webhooks/source%3Aph2f-github",
                content=b"{}",
            ).status_code

    assert observed == {
        "anonymous_public": 200,
        "anonymous_human": 401,
        "anonymous_agent": 401,
        "anonymous_provider": 401,
        "bootstrap_human": 200,
        "bootstrap_admin": 200,
        "bootstrap_agent": 401,
        "bootstrap_provider": 401,
        "named_admin_human": 200,
        "named_admin_admin": 200,
        "named_admin_agent": 401,
        "named_admin_provider": 401,
        "named_viewer_human": 200,
        "named_viewer_admin": 200,
        "named_viewer_agent": 401,
        "named_viewer_provider": 401,
        "service_human": 200,
        "service_admin": 403,
        "service_agent": 401,
        "service_provider": 401,
        "service_session": 403,
        "enrollment_human": 401,
        "enrollment_agent": 401,
        "enrollment_domain": 201,
        "agent_agent": 200,
        "agent_human": 401,
        "agent_provider": 401,
        "provider_provider": 200,
        "provider_human": 401,
        "provider_agent": 401,
        "bootstrap_session_human": 200,
        "bootstrap_session_admin": 200,
        "bootstrap_session_agent": 401,
        "bootstrap_session_provider": 401,
        "named_session_human": 200,
        "named_session_admin": 200,
        "named_session_agent": 401,
        "named_session_provider": 401,
    }

    with session_factory() as session:
        creators_and_revokers = [
            value
            for record in session.scalars(select(AuthApiCredentialRecord))
            for value in (
                record.created_by_subject,
                record.revoked_by_subject,
            )
            if value is not None
        ]
        session_subjects = [
            record.subject for record in session.scalars(select(AuthSessionRecord))
        ]
    assert "local-development" not in creators_and_revokers
    assert "local-development" not in session_subjects


def test_persistence_authority_failure_precedes_durable_authority_lookup(
    acceptance_app,
) -> None:
    _, _, configuration, _, _ = acceptance_app
    calls: list[str] = []

    def unavailable_database() -> None:
        calls.append("persistence")
        raise RuntimeError("synthetic persistence authority failure")

    def forbidden_authority_lookup():
        calls.append("durable-authority")
        raise AssertionError("durable authority must not be queried first")

    application = create_app(
        auth_configuration=replace(configuration, token_registry={}),
        session_factory=forbidden_authority_lookup,
        database_initializer=unavailable_database,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic persistence authority failure",
    ):
        with TestClient(application):
            pass

    assert calls == ["persistence"]
