"""PH-5E adversarial proof for fixed-purpose machine authority."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.db.models import (
    AgentEnrollmentTokenRecord,
    ChangeSourceDeliveryRecord,
    SecurityAuditEventRecord,
    TopoAgentRecord,
)
from test_domain_tenant_enforcement import tenant_app, two_tenants
from test_machine_tenant_binding import enroll, issue, signed, source
from test_tenant_foundation import _bearer, tenant_app as sqlite_tenant_app


def test_agent_token_cannot_enter_human_service_or_execution_authority(
    two_tenants,
) -> None:
    client, factory, tokens, tenant_a, tenant_b = two_tenants
    enrollment = issue(client, tokens["bootstrap"], tenant_a)
    agent = enroll(client, enrollment, header_tenant=tenant_b)
    agent_headers = _bearer(agent["agent_token"], tenant_b)

    assert client.get("/api/v1/agent/config", headers=agent_headers).status_code == 200
    for method, path in (
        ("get", "/api/v1/tenant-memberships"),
        ("get", "/api/v1/auth/api-credentials"),
        ("post", "/api/v1/tenants"),
        ("get", "/api/v1/incidents/incident%3Aph5e/approvals"),
    ):
        response = client.request(method.upper(), path, headers=agent_headers, json={})
        assert response.status_code == 401

    with factory() as session:
        persisted = session.get(
            AgentEnrollmentTokenRecord, enrollment["enrollment_token_id"]
        )
        assert persisted is not None
        assert persisted.tenant_id == tenant_a
        agent_record = session.get(TopoAgentRecord, agent["agent_id"])
        assert agent_record is not None
        assert agent_record.tenant_id == tenant_a


def test_provider_proof_precedes_parse_and_payload_tenant_is_never_authority(
    two_tenants,
) -> None:
    client, factory, tokens, tenant_a, tenant_b = two_tenants
    source_id = source(client, tokens["bootstrap"], tenant_a)
    malformed = b'{"tenant_id":"' + tenant_b.encode() + b'"'
    with factory() as session:
        before_deliveries = session.scalar(
            select(func.count()).select_from(ChangeSourceDeliveryRecord)
        )
        before_audit = session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        )
    invalid = client.post(
        f"/api/v1/change-source-webhooks/{source_id}",
        content=malformed,
        headers={
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "ph5e-invalid",
            "X-Hub-Signature-256": "sha256=" + ("0" * 64),
        },
    )
    assert invalid.status_code == 401
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(ChangeSourceDeliveryRecord)
        ) == before_deliveries
        assert session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        ) == before_audit

    body = json.dumps({"tenant_id": tenant_b, "zen": "not authority"}).encode()
    accepted = client.post(
        f"/api/v1/change-source-webhooks/{source_id}",
        content=body,
        headers={**signed(body, delivery="ph5e-valid"), "X-Topo-Tenant-ID": tenant_b},
    )
    assert accepted.status_code == 200
    with factory() as session:
        delivery = session.get(
            ChangeSourceDeliveryRecord, accepted.json()["delivery_id"]
        )
        assert delivery is not None
        assert delivery.tenant_id == tenant_a


def test_provider_headers_cannot_authenticate_human_or_installation_routes(
    two_tenants,
) -> None:
    client, _, tokens, tenant_a, _ = two_tenants
    source_id = source(client, tokens["bootstrap"], tenant_a)
    body = b"{}"
    provider_headers = signed(body, delivery="ph5e-human-attack")
    assert client.get(
        "/api/v1/tenant-memberships", headers=provider_headers
    ).status_code == 401
    assert client.post(
        "/api/v1/tenants", headers=provider_headers, json={"display_name": source_id}
    ).status_code == 401
