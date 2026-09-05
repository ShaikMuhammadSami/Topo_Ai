from __future__ import annotations
from domain_tenant_fixtures import TEST_HEADERS, seed_domain_tenant

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.api.agents as agents_api
import app.api.change_source_webhooks as webhook_api
import app.security.agent_tokens as agent_security
from app.main import create_app
from app.models.agents import AgentEnrollmentTokenResponse
from app.security.api_tokens import AuthPrincipal, token_digest
from app.security.approval_authorization import approval_control_principal
from app.security.auth_config import (
    AuthConfigurationError,
    AuthConfigurationFailure,
    AuthMode,
    load_auth_configuration,
)
from app.security.auth_routing import RouteAuthDomain, classify_route
from app.services.webhook_security import WebhookAuthenticationError


def _registry(
    token: str,
    *,
    subject: str = "test:operator",
    roles: tuple[str, ...] = ("admin", "operator"),
) -> str:
    return json.dumps(
        {
            token_digest(token): {
                "subject": subject,
                "display_name": "PH-2B Test Principal",
                "roles": list(roles),
            }
        }
    )


def _required_app(
    monkeypatch,
    *,
    roles: tuple[str, ...] = ("admin", "operator"),
    tenant_admin: bool = False,
    with_schema: bool = False,
):
    token = "ph2b-human-bearer-" + ("h" * 32)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        _registry(token, roles=roles),
    )
    # Every authenticated request now resolves a durable principal. Keep all
    # variants on a disposable schema; never touch the protected developer DB.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.database import Base

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    if tenant_admin:
        seed_domain_tenant(engine, subject="test:operator")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return create_app(database_initializer=lambda: None, session_factory=factory), token


def _clear_auth_environment(monkeypatch) -> None:
    monkeypatch.delenv("TOPO_AUTH_MODE", raising=False)
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)


def test_absent_mode_defaults_to_required(monkeypatch) -> None:
    _clear_auth_environment(monkeypatch)
    token = "ph2b-default-bearer-" + ("d" * 32)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", _registry(token))

    configuration = load_auth_configuration(database_url="sqlite://")

    assert configuration.mode is AuthMode.REQUIRED


def test_explicit_required_mode_is_accepted(monkeypatch) -> None:
    token = "ph2b-required-bearer-" + ("r" * 32)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", _registry(token))

    configuration = load_auth_configuration(database_url="sqlite://")

    assert configuration.mode is AuthMode.REQUIRED


def test_development_disabled_is_explicit_and_sqlite_only(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)

    application = create_app()

    assert application.state.auth_configuration.mode is AuthMode.DEVELOPMENT_DISABLED
    assert "never use this mode in production" in caplog.text


def test_development_disabled_rejects_postgresql(monkeypatch) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="postgresql://database/topo")

    assert raised.value.category is AuthConfigurationFailure.DEVELOPMENT_MODE_NON_SQLITE


@pytest.mark.parametrize("value", ["disabled", "false", "off", "dev", "development", "maybe", ""])
def test_invalid_auth_mode_fails_closed(monkeypatch, value: str) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", value)
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")

    assert raised.value.category is AuthConfigurationFailure.INVALID_AUTH_MODE


def test_legacy_true_maps_only_to_required(monkeypatch) -> None:
    token = "ph2b-legacy-bearer-" + ("l" * 32)
    monkeypatch.delenv("TOPO_AUTH_MODE", raising=False)
    monkeypatch.setenv("TOPO_AUTH_ENABLED", "true")
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", _registry(token))

    configuration = load_auth_configuration(database_url="sqlite://")

    assert configuration.mode is AuthMode.REQUIRED
    assert configuration.operator_warnings


def test_legacy_false_never_disables_authentication(monkeypatch) -> None:
    monkeypatch.delenv("TOPO_AUTH_MODE", raising=False)
    monkeypatch.setenv("TOPO_AUTH_ENABLED", "false")

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")

    assert raised.value.category is AuthConfigurationFailure.LEGACY_FAIL_OPEN_CONFIG


def test_incompatible_new_and_legacy_modes_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.setenv("TOPO_AUTH_ENABLED", "false")

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")

    assert raised.value.category is AuthConfigurationFailure.LEGACY_FAIL_OPEN_CONFIG


def test_malformed_registry_fails_during_configuration(monkeypatch) -> None:
    marker = "malformed-registry-marker"
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", marker)

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")

    assert raised.value.category is AuthConfigurationFailure.INVALID_TOKEN_REGISTRY
    assert marker not in str(raised.value)


@pytest.mark.parametrize(
    "registry",
    [
        {"not-a-digest": {"subject": "test:user", "roles": []}},
        {"a" * 64: {"subject": "unknown", "roles": []}},
        {"a" * 64: {"subject": "test:user", "roles": "admin"}},
        {"a" * 64: {"subject": "test:user", "roles": [""]}},
    ],
)
def test_registry_structure_is_strict(monkeypatch, registry: dict) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", json.dumps(registry))

    with pytest.raises(AuthConfigurationError) as raised:
        load_auth_configuration(database_url="sqlite://")

    assert raised.value.category is AuthConfigurationFailure.INVALID_TOKEN_REGISTRY


def test_empty_required_authority_defers_to_post_schema_startup(monkeypatch) -> None:
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)

    configuration = load_auth_configuration(database_url="sqlite://")

    assert configuration.mode is AuthMode.REQUIRED
    assert not configuration.token_registry


def test_unknown_non_empty_roles_are_preserved_without_privilege(monkeypatch) -> None:
    token = "ph2b-custom-role-bearer-" + ("u" * 32)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        _registry(token, roles=("custom-observer",)),
    )

    configuration = load_auth_configuration(database_url="sqlite://")

    assert configuration.token_registry[token_digest(token)].roles == (
        "custom-observer",
    )


def test_required_human_bearer_contract(monkeypatch) -> None:
    application, token = _required_app(monkeypatch)
    client = TestClient(application)

    assert client.get("/api/v1/system/whoami").status_code == 401
    assert client.get(
        "/api/v1/system/whoami",
        headers={"Authorization": "Basic invalid"},
    ).status_code == 401
    assert client.get(
        "/api/v1/system/whoami",
        headers={"Authorization": "Bearer invalid-human-token"},
    ).status_code == 401

    response = client.get(
        "/api/v1/system/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "principal_id": response.json()["principal_id"],
        "principal_type": "human",
        "subject": "test:operator",
        "display_name": "PH-2B Test Principal",
        "roles": ["admin", "operator"],
        "authentication_type": "api_token",
    }
    assert response.json()["subject"] != "local-development"


def test_non_admin_is_forbidden_on_admin_route(monkeypatch) -> None:
    application, token = _required_app(monkeypatch, roles=("viewer",), tenant_admin=True)
    response = TestClient(application).post(
        "/api/v1/agents/enrollment-tokens",
        headers={"Authorization": f"Bearer {token}", **TEST_HEADERS},
        json={"max_uses": 1},
    )

    assert response.status_code == 403


def test_valid_admin_preserves_admin_route(monkeypatch) -> None:
    application, token = _required_app(monkeypatch, roles=("admin",), tenant_admin=True)
    monkeypatch.setattr(
        agents_api,
        "create_enrollment_token",
        lambda **kwargs: AgentEnrollmentTokenResponse(
            enrollment_token_id="enrollment:test",
            enrollment_token="synthetic-enrollment-output",
            token_hint="synthetic",
            label=None,
            max_uses=1,
            expires_at="2026-08-29T00:00:00Z",
            created_at="2026-08-28T00:00:00Z",
        ),
    )

    response = TestClient(application).post(
        "/api/v1/agents/enrollment-tokens",
        headers={"Authorization": f"Bearer {token}", **TEST_HEADERS},
        json={"max_uses": 1},
    )

    assert response.status_code == 201


def test_operator_and_viewer_approval_authorization_is_preserved() -> None:
    operator = AuthPrincipal(
        subject="test:operator",
        display_name="Operator",
        roles=("operator",),
        authentication_type="api_token",
    )
    viewer = AuthPrincipal(
        subject="test:viewer",
        display_name="Viewer",
        roles=("viewer",),
        authentication_type="api_token",
    )

    assert approval_control_principal(
        SimpleNamespace(state=SimpleNamespace(principal=operator))
    ) is operator
    with pytest.raises(HTTPException) as raised:
        approval_control_principal(
            SimpleNamespace(state=SimpleNamespace(principal=viewer))
        )
    assert raised.value.status_code == 403


def test_agent_and_human_bearers_are_not_interchangeable(monkeypatch) -> None:
    application, human_token = _required_app(monkeypatch)
    agent_token = "ph2b-agent-bearer-" + ("a" * 32)
    agent_record = SimpleNamespace(
        agent_id="agent:test",
        collection_interval_seconds=30,
        heartbeat_interval_seconds=10,
        namespace_scope_json="[]",
    )

    monkeypatch.setattr(
        agent_security,
        "authenticate_agent",
        lambda *, session, token: agent_record if token == agent_token else None,
    )
    client = TestClient(application)

    agent_response = client.get(
        "/api/v1/agent/config",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    agent_on_human = client.get(
        "/api/v1/system/whoami",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    human_on_agent = client.get(
        "/api/v1/agent/config",
        headers={"Authorization": f"Bearer {human_token}"},
    )

    assert agent_response.status_code == 200
    assert agent_on_human.status_code == 401
    assert human_on_agent.status_code == 401


def test_provider_callback_uses_only_provider_authentication(monkeypatch) -> None:
    application, human_token = _required_app(monkeypatch)
    monkeypatch.setattr(
        webhook_api,
        "load_change_source_for_authentication",
        lambda *args, **kwargs: SimpleNamespace(source_id="source:test"),
    )
    monkeypatch.setattr(
        webhook_api,
        "ingest_change_source_webhook",
        lambda *args, **kwargs: {
            "delivery_id": "delivery:test",
            "source_id": "source:test",
            "event_type": "push",
            "status": "accepted",
            "duplicate": False,
            "event_ids": [],
        },
    )
    client = TestClient(application)

    provider_only = client.post(
        "/api/v1/change-source-webhooks/source%3Atest",
        content=b"{}",
        headers={"X-Hub-Signature-256": "synthetic-signature"},
    )
    provider_on_human = client.get(
        "/api/v1/system/whoami",
        headers={"X-Hub-Signature-256": "synthetic-signature"},
    )

    assert provider_only.status_code == 200
    assert provider_on_human.status_code == 401

    def reject_provider(*args, **kwargs):
        raise WebhookAuthenticationError("synthetic rejection")

    monkeypatch.setattr(webhook_api, "ingest_change_source_webhook", reject_provider)
    invalid_with_human = client.post(
        "/api/v1/change-source-webhooks/source%3Atest",
        content=b"{}",
        headers={"Authorization": f"Bearer {human_token}"},
    )
    assert invalid_with_human.status_code == 401


def test_health_and_readiness_are_public_and_minimal(monkeypatch) -> None:
    application, _ = _required_app(monkeypatch, with_schema=True)
    client = TestClient(application)

    health = client.get("/health")
    not_ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {
        "status": "available",
        "service": "Topo AI",
        "version": "0.1.0",
    }
    assert not_ready.status_code == 503
    assert not_ready.json() == {"status": "not_ready"}

    with TestClient(application) as started_client:
        ready = started_client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_docs_are_disabled_required_and_available_development(
    monkeypatch,
) -> None:
    required_application, _ = _required_app(monkeypatch)
    assert TestClient(required_application).get("/openapi.json").status_code == 404
    assert TestClient(required_application).get("/docs").status_code == 404

    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)
    development_application = create_app()

    assert TestClient(development_application).get("/openapi.json").status_code == 200
    assert TestClient(development_application).get("/docs").status_code == 200


def test_route_domain_coverage_has_no_unknown_api_routes(monkeypatch) -> None:
    application, _ = _required_app(monkeypatch)
    api_pairs = []

    registered_routes = []
    for route in application.routes:
        if isinstance(route, APIRoute):
            registered_routes.append(route)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            registered_routes.extend(
                child
                for child in original_router.routes
                if isinstance(child, APIRoute)
            )

    for route in registered_routes:
        for method in route.methods:
            domain = classify_route(method, route.path)
            if route.path.startswith("/api/v1/"):
                assert domain is not None
                api_pairs.append((method, route.path, domain))

    assert api_pairs
    for method, path, domain in api_pairs:
        if method == "POST" and path == "/api/v1/agents/enroll":
            assert domain is RouteAuthDomain.AGENT_AUTHENTICATED
        elif path.startswith("/api/v1/agent/"):
            assert domain is RouteAuthDomain.AGENT_AUTHENTICATED
        elif method == "POST" and path == "/api/v1/change-source-webhooks/{source_id}":
            assert domain is RouteAuthDomain.PROVIDER_CALLBACK_AUTHENTICATED
        else:
            assert domain is RouteAuthDomain.USER_AUTHENTICATED

    assert classify_route("GET", "/health") is RouteAuthDomain.PUBLIC_LIVENESS
    assert (
        classify_route("GET", "/ready")
        is RouteAuthDomain.PUBLIC_READINESS_MINIMAL
    )
    assert (
        classify_route("OPTIONS", "/api/v1/incidents")
        is RouteAuthDomain.PUBLIC_CORS_PREFLIGHT
    )


def test_credentials_are_absent_from_errors_and_development_warning(
    monkeypatch,
    caplog,
) -> None:
    application, _ = _required_app(monkeypatch)
    marker = "invalid-sensitive-bearer-marker"
    response = TestClient(application).get(
        "/api/v1/system/whoami",
        headers={"Authorization": f"Bearer {marker}"},
    )

    assert response.status_code == 401
    assert marker not in response.text
    assert marker not in caplog.text

    monkeypatch.setenv("TOPO_AUTH_MODE", "development-disabled")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("TOPO_API_TOKEN_HASHES_JSON", raising=False)
    create_app()
    assert marker not in caplog.text


def test_cors_preflight_does_not_grant_business_authority(monkeypatch) -> None:
    application, _ = _required_app(monkeypatch)
    client = TestClient(application)
    headers = {
        "Origin": "http://127.0.0.1:3000",
        "Access-Control-Request-Method": "POST",
    }

    preflight = client.options(
        "/api/v1/agents/enrollment-tokens",
        headers=headers,
    )
    business_request = client.post(
        "/api/v1/agents/enrollment-tokens",
        json={"max_uses": 1},
    )

    assert preflight.status_code == 200
    assert business_request.status_code == 401
