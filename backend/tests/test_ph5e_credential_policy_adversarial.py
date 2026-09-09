"""PH-5E HTTP proof for the frozen authenticator credential policy."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import SecurityAuditEventRecord
from test_domain_tenant_enforcement import tenant_app, two_tenants
from test_tenant_foundation import (
    _bearer,
    _create_named,
    tenant_app as sqlite_tenant_app,
)


def _human_payload(subject: str) -> dict[str, object]:
    return {
        "name": "PH-5E human credential",
        "caller_type": "human_api",
        "subject": subject,
        "roles": ["admin", "operator"],
        "expires_in_days": 30,
    }


def test_human_credential_is_self_only_despite_tenant_or_installation_authority(
    two_tenants,
) -> None:
    client, _, tokens, tenant_a, _ = two_tenants
    own = client.post(
        "/api/v1/auth/api-credentials",
        headers=_bearer(tokens["bootstrap"]),
        json=_human_payload("test:bootstrap-admin"),
    )
    assert own.status_code == 201, own.text
    credential_id = own.json()["credential_id"]
    raw = own.json()["api_credential"]

    listing = client.get(
        "/api/v1/auth/api-credentials",
        headers=_bearer(tokens["bootstrap"], tenant_a),
    )
    detail = client.get(
        f"/api/v1/auth/api-credentials/{credential_id}",
        headers=_bearer(tokens["bootstrap"], tenant_a),
    )
    assert listing.status_code == detail.status_code == 200
    assert [item["credential_id"] for item in listing.json()] == [credential_id]

    other = client.get(
        f"/api/v1/auth/api-credentials/{credential_id}",
        headers=_bearer(tokens["other_admin"]),
    )
    assert other.status_code == 404
    impersonation = client.post(
        "/api/v1/auth/api-credentials",
        headers=_bearer(tokens["bootstrap"], tenant_a),
        json=_human_payload("test:other-admin"),
    )
    assert impersonation.status_code == 403
    assert "api_credential" not in impersonation.text

    revoked = client.post(
        f"/api/v1/auth/api-credentials/{credential_id}/revoke",
        headers=_bearer(raw),
    )
    assert revoked.status_code == 200
    assert client.get(
        "/api/v1/system/whoami", headers=_bearer(raw)
    ).status_code == 401


def test_same_tenant_admin_controls_service_credentials_but_service_cannot(
    two_tenants,
) -> None:
    client, _, tokens, tenant_a, _ = two_tenants
    service = _create_named(
        client,
        tokens["bootstrap"],
        caller_type="service_api",
        subject="service:ph5e-policy",
        roles=["admin"],
        tenant_id=tenant_a,
        permissions=["integration.manage"],
    )
    credential_id = service["credential_id"]
    service_headers = _bearer(service["api_credential"])
    admin_headers = _bearer(tokens["bootstrap"], tenant_a)

    assert client.get(
        "/api/v1/auth/api-credentials?target_type=service",
        headers=admin_headers,
    ).status_code == 200
    assert client.get(
        f"/api/v1/auth/api-credentials/{credential_id}",
        headers=admin_headers,
    ).status_code == 200
    for method, path in (
        ("get", "/api/v1/auth/api-credentials?target_type=service"),
        ("get", f"/api/v1/auth/api-credentials/{credential_id}"),
        ("post", f"/api/v1/auth/api-credentials/{credential_id}/revoke"),
    ):
        response = getattr(client, method)(path, headers=service_headers)
        assert response.status_code == 403

    revoked = client.post(
        f"/api/v1/auth/api-credentials/{credential_id}/revoke",
        headers=admin_headers,
    )
    assert revoked.status_code == 200


def test_foreign_and_nonexistent_service_credentials_are_identical_and_unaudited(
    two_tenants,
) -> None:
    client, factory, tokens, tenant_a, tenant_b = two_tenants
    service_b = _create_named(
        client,
        tokens["other_admin"],
        caller_type="service_api",
        subject="service:ph5e-foreign",
        roles=[],
        tenant_id=tenant_b,
        permissions=["incident.read"],
    )
    with factory() as session:
        before = session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        )
    headers = _bearer(tokens["bootstrap"], tenant_a)
    foreign = client.get(
        f"/api/v1/auth/api-credentials/{service_b['credential_id']}",
        headers=headers,
    )
    absent = client.get(
        "/api/v1/auth/api-credentials/api-credential:00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json()
    with factory() as session:
        after = session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        )
    assert after == before
