from __future__ import annotations

import json
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_session
from app.db.models import (
    AuthApiCredentialRecord,
    ServiceApiTenantBindingRecord,
    TenantMembershipRecord,
    TenantRecord,
)
from app.main import create_app
from app.repositories import tenant_repository
from app.security.api_tokens import token_digest
from app.security.auth_config import load_auth_configuration
from app.security.principals import AuthPrincipal
from app.security.session_auth import CSRF_COOKIE_NAME


ORIGIN = "https://topo.test"


@pytest.fixture()
def tenant_app(monkeypatch):
    callers = {
        "bootstrap": (
            "test:bootstrap-admin",
            "Bootstrap Admin",
            ["admin"],
        ),
        "other_admin": (
            "test:other-admin",
            "Other Admin",
            ["admin"],
        ),
        "viewer": ("test:viewer", "Viewer", ["viewer"]),
    }
    tokens = {
        name: f"ph3b-{name}-" + secrets.token_urlsafe(40)
        for name in callers
    }
    registry = {
        token_digest(tokens[name]): {
            "subject": subject,
            "display_name": display_name,
            "roles": roles,
        }
        for name, (subject, display_name, roles) in callers.items()
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
        yield application, factory, tokens
    finally:
        application.dependency_overrides.clear()
        engine.dispose()


def _bearer(token: str, tenant_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if tenant_id is not None:
        headers["X-Topo-Tenant-ID"] = tenant_id
    return headers


def _create_tenant(
    client: TestClient,
    token: str,
    display_name: str = "Production",
) -> dict:
    response = client.post(
        "/api/v1/tenants",
        headers=_bearer(token),
        json={"display_name": display_name},
    )
    assert response.status_code == 201
    return response.json()


def _create_named(
    client: TestClient,
    token: str,
    *,
    caller_type: str,
    subject: str,
    roles: list[str],
    tenant_id: str | None = None,
) -> dict:
    payload = {
        "name": f"PH-3B {caller_type}",
        "caller_type": caller_type,
        "subject": subject,
        "display_name": subject,
        "roles": roles,
        "expires_in_days": 30,
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    response = client.post(
        "/api/v1/auth/api-credentials",
        headers=_bearer(token),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def test_tenant_context_does_not_modify_auth_principal_contract() -> None:
    assert tuple(AuthPrincipal.__dataclass_fields__) == (
        "subject",
        "display_name",
        "roles",
        "authentication_type",
    )


def test_tenant_creation_listing_collisions_and_atomic_rollback(
    tenant_app,
    monkeypatch,
) -> None:
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        first = _create_tenant(client, tokens["bootstrap"])
        second = _create_tenant(client, tokens["other_admin"])

        assert first["display_name"] == second["display_name"] == "Production"
        assert first["tenant_id"] != second["tenant_id"]
        assert first["tenant_id"].startswith("tenant:")
        assert client.post(
            "/api/v1/tenants",
            headers=_bearer(tokens["viewer"]),
            json={"display_name": "Forbidden"},
        ).status_code == 403

        bootstrap_list = client.get(
            "/api/v1/tenants",
            headers=_bearer(tokens["bootstrap"]),
        )
        assert bootstrap_list.status_code == 200
        assert [item["tenant_id"] for item in bootstrap_list.json()] == [
            first["tenant_id"]
        ]

        with monkeypatch.context() as scoped:
            scoped.setattr(
                tenant_repository,
                "add_tenant_membership",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    OperationalError("forced membership failure", {}, None)
                ),
            )
            failed = client.post(
                "/api/v1/tenants",
                headers=_bearer(tokens["bootstrap"]),
                json={"display_name": "Atomic failure"},
            )
        assert failed.status_code == 503

        retried = _create_tenant(
            client,
            tokens["bootstrap"],
            "Atomic failure",
        )
        assert retried["display_name"] == "Atomic failure"

    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(TenantRecord).where(
                TenantRecord.display_name == "Atomic failure"
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id == retried["tenant_id"]
            )
        ) == 1


def test_human_tenant_context_is_explicit_membership_scoped_and_non_enumerating(
    tenant_app,
) -> None:
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant_a = _create_tenant(client, tokens["bootstrap"], "Tenant A")
        tenant_b = _create_tenant(client, tokens["other_admin"], "Tenant B")

        missing = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["bootstrap"]),
        )
        assert missing.status_code == 400
        assert missing.json() == {"detail": "TENANT_CONTEXT_REQUIRED"}

        allowed = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["bootstrap"], tenant_a["tenant_id"]),
        )
        assert allowed.status_code == 200
        assert allowed.json()["tenant_id"] == tenant_a["tenant_id"]
        assert allowed.json()["actor_kind"] == "human"
        assert allowed.json()["selection_source"] == "human_header"

        foreign = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["bootstrap"], tenant_b["tenant_id"]),
        )
        unknown = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["bootstrap"], f"tenant:{uuid4()}"),
        )
        assert foreign.status_code == unknown.status_code == 403
        assert foreign.json() == unknown.json() == {
            "detail": "TENANT_ACCESS_DENIED"
        }

    with factory() as session:
        tenant = session.get(TenantRecord, tenant_a["tenant_id"])
        assert tenant is not None
        tenant.status = "disabled"
        session.commit()

    with TestClient(application) as client:
        disabled = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["bootstrap"], tenant_a["tenant_id"]),
        )
        assert disabled.status_code == 403
        assert disabled.json() == {"detail": "TENANT_ACCESS_DENIED"}


def test_membership_lifecycle_is_tenant_scoped_and_preserves_other_access(
    tenant_app,
) -> None:
    application, _, tokens = tenant_app
    with TestClient(application) as client:
        tenant_a = _create_tenant(client, tokens["bootstrap"], "Tenant A")
        tenant_b = _create_tenant(client, tokens["other_admin"], "Tenant B")
        headers_a = _bearer(tokens["bootstrap"], tenant_a["tenant_id"])
        headers_b = _bearer(tokens["other_admin"], tenant_b["tenant_id"])

        added_a = client.post(
            "/api/v1/tenant-memberships",
            headers=headers_a,
            json={"subject": "test:viewer"},
        )
        added_b = client.post(
            "/api/v1/tenant-memberships",
            headers=headers_b,
            json={"subject": "test:viewer"},
        )
        assert added_a.status_code == added_b.status_code == 200
        duplicate = client.post(
            "/api/v1/tenant-memberships",
            headers=headers_a,
            json={"subject": "test:viewer"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["membership_id"] == added_a.json()[
            "membership_id"
        ]

        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["viewer"], tenant_a["tenant_id"]),
        ).status_code == 200
        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["viewer"], tenant_b["tenant_id"]),
        ).status_code == 200
        assert client.get(
            "/api/v1/tenant-memberships",
            headers=_bearer(tokens["viewer"], tenant_a["tenant_id"]),
        ).status_code == 403

        cross_tenant = client.post(
            (
                "/api/v1/tenant-memberships/"
                f"{added_b.json()['membership_id']}/disable"
            ),
            headers=headers_a,
        )
        assert cross_tenant.status_code == 404

        disabled = client.post(
            (
                "/api/v1/tenant-memberships/"
                f"{added_a.json()['membership_id']}/disable"
            ),
            headers=headers_a,
        )
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"
        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["viewer"], tenant_a["tenant_id"]),
        ).status_code == 403
        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["viewer"], tenant_b["tenant_id"]),
        ).status_code == 200

        reactivated = client.post(
            "/api/v1/tenant-memberships",
            headers=headers_a,
            json={"subject": "test:viewer"},
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["membership_id"] == added_a.json()[
            "membership_id"
        ]
        assert reactivated.json()["status"] == "active"


def test_service_credential_binding_is_fixed_visible_and_atomic(
    tenant_app,
    monkeypatch,
) -> None:
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant_a = _create_tenant(client, tokens["bootstrap"], "Tenant A")
        tenant_b = _create_tenant(client, tokens["other_admin"], "Tenant B")

        missing = client.post(
            "/api/v1/auth/api-credentials",
            headers=_bearer(tokens["bootstrap"]),
            json={
                "name": "missing tenant",
                "caller_type": "service_api",
                "subject": "service:missing",
                "roles": [],
            },
        )
        assert missing.status_code == 422

        foreign = client.post(
            "/api/v1/auth/api-credentials",
            headers=_bearer(tokens["bootstrap"]),
            json={
                "name": "foreign tenant",
                "caller_type": "service_api",
                "subject": "service:foreign",
                "roles": [],
                "tenant_id": tenant_b["tenant_id"],
            },
        )
        assert foreign.status_code == 403

        with monkeypatch.context() as scoped:
            scoped.setattr(
                tenant_repository,
                "add_service_api_tenant_binding",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    OperationalError("forced binding failure", {}, None)
                ),
            )
            failed = client.post(
                "/api/v1/auth/api-credentials",
                headers=_bearer(tokens["bootstrap"]),
                json={
                    "name": "atomic service",
                    "caller_type": "service_api",
                    "subject": "service:atomic",
                    "roles": [],
                    "tenant_id": tenant_a["tenant_id"],
                },
            )
        assert failed.status_code == 503

        created = _create_named(
            client,
            tokens["bootstrap"],
            caller_type="service_api",
            subject="service:automation",
            roles=["admin"],
            tenant_id=tenant_a["tenant_id"],
        )
        assert created["tenant_id"] == tenant_a["tenant_id"]
        service_token = created["api_credential"]

        derived = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(service_token),
        )
        matching = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(service_token, tenant_a["tenant_id"]),
        )
        mismatching = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(service_token, tenant_b["tenant_id"]),
        )
        assert derived.status_code == matching.status_code == 200
        assert derived.json()["tenant_id"] == tenant_a["tenant_id"]
        assert derived.json()["actor_kind"] == "service"
        assert derived.json()["selection_source"] == "service_binding"
        assert mismatching.status_code == 403

        listing = client.get(
            "/api/v1/auth/api-credentials",
            headers=_bearer(tokens["bootstrap"]),
        )
        service_view = next(
            item
            for item in listing.json()
            if item["credential_id"] == created["credential_id"]
        )
        assert service_view["tenant_id"] == tenant_a["tenant_id"]
        assert client.post(
            "/api/v1/tenants",
            headers=_bearer(service_token),
            json={"display_name": "Forbidden service tenant"},
        ).status_code == 403
        revoked = client.post(
            (
                "/api/v1/auth/api-credentials/"
                f"{created['credential_id']}/revoke"
            ),
            headers=_bearer(tokens["bootstrap"]),
        )
        assert revoked.status_code == 200
        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(service_token),
        ).status_code == 401

    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(AuthApiCredentialRecord).where(
                AuthApiCredentialRecord.subject == "service:atomic"
            )
        ) == 0
        assert session.scalar(
            select(func.count())
            .select_from(ServiceApiTenantBindingRecord)
            .where(
                ServiceApiTenantBindingRecord.created_by_subject
                == "test:bootstrap-admin"
            )
        ) == 1


def test_human_credentials_share_subject_membership_and_never_get_binding(
    tenant_app,
) -> None:
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        named_same = _create_named(
            client,
            tokens["bootstrap"],
            caller_type="human_api",
            subject="test:bootstrap-admin",
            roles=["admin"],
        )
        named_other = _create_named(
            client,
            tokens["bootstrap"],
            caller_type="human_api",
            subject="test:different-admin",
            roles=["admin"],
        )

        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(
                named_same["api_credential"],
                tenant["tenant_id"],
            ),
        ).status_code == 200
        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(
                named_other["api_credential"],
                tenant["tenant_id"],
            ),
        ).status_code == 403
        assert named_same["tenant_id"] is None

    with factory() as session:
        human_bindings = session.scalar(
            select(func.count())
            .select_from(ServiceApiTenantBindingRecord)
            .where(
                ServiceApiTenantBindingRecord.credential_id.in_(
                    [
                        named_same["credential_id"],
                        named_other["credential_id"],
                    ]
                )
            )
        )
        assert human_bindings == 0


def test_direct_bootstrap_recovery_is_narrow_and_other_callers_are_denied(
    tenant_app,
) -> None:
    application, _, tokens = tenant_app
    with TestClient(application, base_url=ORIGIN) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        named = _create_named(
            client,
            tokens["bootstrap"],
            caller_type="human_api",
            subject="test:bootstrap-admin",
            roles=["admin"],
        )
        service = _create_named(
            client,
            tokens["bootstrap"],
            caller_type="service_api",
            subject="service:recovery-denied",
            roles=["admin"],
            tenant_id=tenant["tenant_id"],
        )
        membership_id = tenant["membership_id"]

        login = client.post(
            "/api/v1/auth/session",
            headers={**_bearer(tokens["bootstrap"]), "Origin": ORIGIN},
        )
        assert login.status_code == 201
        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        assert client.post(
            f"/api/v1/tenant-memberships/{membership_id}/disable",
            headers=_bearer(tokens["bootstrap"], tenant["tenant_id"]),
        ).status_code == 200

        recovery_body = {
            "tenant_id": tenant["tenant_id"],
            "subject": "test:recovered-admin",
        }
        assert client.post(
            "/api/v1/tenant-memberships/recover",
            headers=_bearer(named["api_credential"]),
            json=recovery_body,
        ).status_code == 403
        assert client.post(
            "/api/v1/tenant-memberships/recover",
            headers=_bearer(service["api_credential"]),
            json=recovery_body,
        ).status_code == 403

        session_denied = client.post(
            "/api/v1/tenant-memberships/recover",
            headers={"X-Topo-CSRF": csrf},
            json=recovery_body,
        )
        assert session_denied.status_code == 403

        recovered = client.post(
            "/api/v1/tenant-memberships/recover",
            headers=_bearer(tokens["bootstrap"]),
            json=recovery_body,
        )
        assert recovered.status_code == 200
        assert recovered.json()["subject"] == "test:recovered-admin"

        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(tokens["bootstrap"], tenant["tenant_id"]),
        ).status_code == 403

        restored = client.post(
            "/api/v1/tenant-memberships/recover",
            headers=_bearer(tokens["bootstrap"]),
            json={
                "tenant_id": tenant["tenant_id"],
                "subject": "test:bootstrap-admin",
            },
        )
        assert restored.status_code == 200
        assert restored.json()["membership_id"] == membership_id
        assert client.get(
            "/api/v1/tenant-context",
            headers=_bearer(named["api_credential"], tenant["tenant_id"]),
        ).status_code == 200


def test_unbound_legacy_service_authenticates_but_cannot_resolve_context(
    tenant_app,
) -> None:
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        created = _create_named(
            client,
            tokens["bootstrap"],
            caller_type="service_api",
            subject="service:legacy-unbound",
            roles=[],
            tenant_id=tenant["tenant_id"],
        )

    with factory() as session:
        binding = session.scalars(
            select(ServiceApiTenantBindingRecord).where(
                ServiceApiTenantBindingRecord.credential_id
                == created["credential_id"]
            )
        ).one()
        session.delete(binding)
        session.commit()

    with TestClient(application) as client:
        assert client.get(
            "/api/v1/system/whoami",
            headers=_bearer(created["api_credential"]),
        ).status_code == 200
        denied = client.get(
            "/api/v1/tenant-context",
            headers=_bearer(created["api_credential"]),
        )
        assert denied.status_code == 403
        assert denied.json() == {"detail": "TENANT_ACCESS_DENIED"}
