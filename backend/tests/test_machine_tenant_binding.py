"""Real PH-2 authentication + persisted PH-3E machine authority, two tenants."""

from datetime import timedelta
from types import SimpleNamespace
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.db import models
from app.repositories.tenant_scope import TenantResourceNotFound, tenant_commit
from test_domain_tenant_enforcement import two_tenants, tenant_app, sqlite_tenant_app
from test_tenant_foundation import _bearer, _create_named
from test_continuous_lifecycle import NOW, _agent_submission
from domain_tenant_fixtures import null_ownership_inventory


def issue(client, token, tenant):
    response = client.post("/api/v1/agents/enrollment-tokens", headers=_bearer(token, tenant),
                           json={"label": "Same label", "max_uses": 2})
    assert response.status_code == 201, response.text
    return response.json()


def enroll(client, issued, *, header_tenant=None):
    response = client.post("/api/v1/agents/enroll",
        headers={} if header_tenant is None else {"X-Topo-Tenant-ID": header_tenant},
        json={"enrollment_token": issued["enrollment_token"], "name": "Same agent",
              "cluster_name": "production", "namespace_scope": ["payments"], "version": "1.0",
              "metadata": {"tenant_id": header_tenant}})
    assert response.status_code == 201, response.text
    return response.json()


def source(client, token, tenant):
    response = client.post("/api/v1/change-sources", headers=_bearer(token, tenant), json={
        "name": "Same source", "source_type": "github", "credential": "ph3e-test-only",
    })
    assert response.status_code == 201, response.text
    return response.json()["source_id"]


def signed(body, *, delivery="same-delivery"):
    return {"X-GitHub-Event": "ping", "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": "sha256=" + hmac.new(b"ph3e-test-only", body, hashlib.sha256).hexdigest()}


def test_agent_binding_inheritance_header_ignored_and_cross_tenant_admin(two_tenants):
    client, factory, tokens, a, b = two_tenants
    issued_a, issued_b = issue(client, tokens["bootstrap"], a), issue(client, tokens["other_admin"], b)
    aa, bb = enroll(client, issued_a, header_tenant=b), enroll(client, issued_b)
    with factory() as s:
        assert s.get(models.AgentEnrollmentTokenRecord, issued_a["enrollment_token_id"]).tenant_id == a
        assert s.get(models.TopoAgentRecord, aa["agent_id"]).tenant_id == a
        assert s.get(models.TopoAgentRecord, bb["agent_id"]).tenant_id == b
    headers = _bearer(tokens["bootstrap"], a)
    assert [x["agent_id"] for x in client.get("/api/v1/agents", headers=headers).json()] == [aa["agent_id"]]
    for suffix in ("", "/health", "/plugins", "/cloud-status"):
        assert client.get(f'/api/v1/agents/{bb["agent_id"]}{suffix}', headers=headers).status_code == 404
        assert client.get(f'/api/v1/agents/{aa["agent_id"]}{suffix}', headers=headers).status_code == 200
    assert client.post(f'/api/v1/agents/{bb["agent_id"]}/revoke', headers=headers).status_code == 404
    assert client.get("/api/v1/agent/config", headers=_bearer(aa["agent_token"], b)).status_code == 200
    assert client.get("/api/v1/agents", headers=_bearer(tokens["bootstrap"], b)).status_code == 403
    assert client.get("/api/v1/agents", headers=_bearer(tokens["bootstrap"])).status_code == 400


def test_disabled_tenant_blocks_enrollment_without_consumption_and_existing_agent(two_tenants):
    client, factory, tokens, a, b = two_tenants
    issued = issue(client, tokens["bootstrap"], a)
    agent = enroll(client, issued)
    with factory.begin() as s:
        s.get(models.TenantRecord, a).status = "disabled"
    denied = client.post("/api/v1/agents/enroll", json={
        "enrollment_token": issued["enrollment_token"], "name": "Again",
        "cluster_name": "production", "version": "1.0"})
    assert denied.status_code == 401
    assert client.get("/api/v1/agent/config", headers=_bearer(agent["agent_token"], b)).status_code == 401
    assert client.post("/api/v1/agent/runtime/heartbeat", headers=_bearer(agent["agent_token"], b),
        json={"sensor_id": "blocked", "node_name": "worker", "cluster_name": "production", "version": "1.0"}).status_code == 401
    with factory() as s:
        assert s.get(models.AgentEnrollmentTokenRecord, issued["enrollment_token_id"]).use_count == 1
        assert len(s.scalars(select(models.TopoAgentRecord)).all()) == 1
        assert s.scalar(select(models.RuntimeSensorRecord)) is None


def test_source_management_provider_binding_idempotency_and_disabled_tenant(two_tenants, monkeypatch):
    client, factory, tokens, a, b = two_tenants
    sa, sb = source(client, tokens["bootstrap"], a), source(client, tokens["other_admin"], b)
    headers = _bearer(tokens["bootstrap"], a)
    assert [x["source_id"] for x in client.get("/api/v1/change-sources", headers=headers).json()] == [sa]
    for suffix in ("", "/doctor"):
        assert client.get(f"/api/v1/change-sources/{sb}{suffix}", headers=headers).status_code == 404
        assert client.get(f"/api/v1/change-sources/{sa}{suffix}", headers=headers).status_code == 200
    assert client.patch(f"/api/v1/change-sources/{sb}", headers=headers, json={"enabled": False}).status_code == 404
    body = json.dumps({"tenant_id": b, "zen": "Tenant payload is not authority"}).encode()
    provider_headers = {**signed(body), "X-Topo-Tenant-ID": b}
    first = client.post(f"/api/v1/change-source-webhooks/{sa}", content=body, headers=provider_headers)
    again = client.post(f"/api/v1/change-source-webhooks/{sa}", content=body, headers=provider_headers)
    other = client.post(f"/api/v1/change-source-webhooks/{sb}", content=body, headers=signed(body))
    assert first.status_code == again.status_code == other.status_code == 200
    assert again.json()["duplicate"] is True
    assert other.json()["delivery_id"] != first.json()["delivery_id"]
    with factory.begin() as s:
        assert s.get(models.ChangeSourceDeliveryRecord, first.json()["delivery_id"]).tenant_id == a
        assert s.get(models.ChangeSourceDeliveryRecord, other.json()["delivery_id"]).tenant_id == b
        s.get(models.TenantRecord, a).status = "disabled"
    blocked = client.post(f"/api/v1/change-source-webhooks/{sa}", content=b"not-json", headers=signed(b"not-json"))
    assert blocked.status_code == 401  # tenant checked before JSON parsing
    with factory() as s:
        assert len(s.scalars(select(models.ChangeSourceDeliveryRecord)).all()) == 2


@pytest.mark.parametrize("path,payload", [
    ("/api/v1/agents/enrollment-tokens", {"max_uses": 1}),
    ("/api/v1/change-sources", {"name": "Spoof", "source_type": "github", "credential": "ph3e-test-only"}),
])
def test_human_machine_creation_rejects_payload_tenant(two_tenants, path, payload):
    client, _, tokens, a, b = two_tenants
    response = client.post(path, headers=_bearer(tokens["bootstrap"], a), json={**payload, "tenant_id": b})
    assert response.status_code == 422


def test_service_fixed_binding_applies_to_machine_admin(two_tenants):
    client, _, tokens, a, b = two_tenants
    credential = _create_named(client, tokens["bootstrap"], caller_type="service_api",
                              subject="service:machine-test", roles=["admin"], tenant_id=a,
                              permissions=["integration.read"])
    headers = _bearer(credential["api_credential"])
    assert client.get("/api/v1/agents", headers=headers).status_code == 200
    assert client.get("/api/v1/change-sources", headers=headers).status_code == 403
    assert client.get("/api/v1/agents", headers={**headers, "X-Topo-Tenant-ID": b}).status_code == 403


def test_real_agent_snapshot_failure_rca_briefing_carries_tenant(two_tenants, monkeypatch):
    client, factory, tokens, a, b = two_tenants
    from app.models.webhooks import WebhookEndpointCreate
    from app.services.secret_consumers import create_webhook_endpoint_secure
    from app.services import webhook_delivery

    delivered_urls = []

    # Only network I/O is substituted; event selection, dispatch and durable
    # delivery bookkeeping run unchanged through the actual lifecycle.
    monkeypatch.setattr(
        webhook_delivery,
        "deliver_webhook_once",
        lambda destination, **_: delivered_urls.append(
            destination.destination.url
        ) or 200,
    )
    with factory() as s:
        for tenant, name in ((a, "a"), (b, "b")):
            create_webhook_endpoint_secure(
                s,
                request=WebhookEndpointCreate(
                    name=name, url=f"https://{name}.example.test/incidents", max_attempts=1
                ),
                tenant_id=tenant,
                actor="test:machine-tenant",
                store=client.app.state.secret_store,
            )
    agent = enroll(client, issue(client, tokens["bootstrap"], a))
    headers = _bearer(agent["agent_token"], b)  # deliberately misleading
    heartbeat = {"sensor_id": "sensor:ph3e", "node_name": "worker", "cluster_name": "production", "version": "1.0"}
    assert client.post("/api/v1/agent/runtime/heartbeat", headers=headers, json=heartbeat).status_code == 200
    batch = {**heartbeat, "batch_id": "batch:ph3e", "window_start": NOW.isoformat(),
        "window_end": NOW.isoformat(), "processed_event_count": 1, "dropped_event_count": 0,
        "parser_error_count": 0, "dependencies": [{"source": {"pod_uid": "pod-0", "namespace": "payments"},
            "destination": {"address": "10.0.0.10", "port": 443}, "protocol": "tcp",
            "first_seen_at": NOW.isoformat(), "last_seen_at": NOW.isoformat()}],
        "processes": [{"binary": "/app/payment", "pid": 42, "first_seen_at": NOW.isoformat(),
            "last_seen_at": NOW.isoformat()}]}
    runtime = client.post("/api/v1/agent/runtime/batches", headers=headers, json=batch)
    assert runtime.status_code == 201, runtime.text
    for number, failure in enumerate((None, "ImagePullBackOff")):
        payload = _agent_submission(f"ph3e-{number}", collected_at=NOW + timedelta(minutes=number),
            image=f"example/payment:v{number}", pod_uid=f"pod-{number}", pod_name=f"payment-{number}",
            replica_uid=f"rs-{number}", failure_reason=failure).model_dump(mode="json")
        payload["inventory"]["aws_accounts"] = [{"provider": "aws", "account_id": "123456789012",
            "region": "global", "resource_type": "aws_account", "resource_id": "123456789012", "name": "Account"}]
        payload["inventory"]["aws_vpcs"] = [{"provider": "aws", "account_id": "123456789012",
            "region": "us-east-1", "resource_type": "aws_vpc", "resource_id": "vpc-test", "name": "VPC"}]
        response = client.post("/api/v1/agent/snapshots", headers=headers, json=payload)
        assert response.status_code == 201, response.text
    with factory() as s:
        incident = s.scalar(select(models.IncidentRecord))
        assert incident is not None and incident.tenant_id == a
        assert incident.affected_entity_id and incident.topology_snapshot_id
        causal = s.scalar(select(models.CausalAnalysisRecord))
        assert causal is not None and causal.tenant_id == a
        for model in (models.SnapshotRecord, models.SignalRecord, models.ChangeRecord,
                      models.ChangeEventRecord, models.ChangeEntityLinkRecord,
                      models.RuntimeSensorRecord, models.RuntimeDependencyRecord,
                      models.RuntimeProcessRecord, models.CloudAccountRecord,
                      models.CloudResourceRecord, models.WebhookDeliveryRecord):
            rows = s.scalars(select(model)).all()
            assert rows, model.__name__
            assert all(row.tenant_id == a for row in rows)
        audit = null_ownership_inventory(s)
        assert len(audit) == 38 and all(row["null"] == 0 for row in audit.values())
        print("PH3E_NULL_AUDIT " + json.dumps(audit, sort_keys=True))
        incident_id = incident.incident_id
    assert delivered_urls and set(delivered_urls) == {"https://a.example.test/incidents"}
    briefing = client.get(f"/api/v1/incidents/{incident_id}/briefing", headers=_bearer(tokens["bootstrap"], a))
    assert briefing.status_code == 200, briefing.text
    assert client.get(f"/api/v1/incidents/{incident_id}/briefing", headers=_bearer(tokens["other_admin"], b)).status_code == 404


def test_machine_parent_references_cannot_cross_tenants(two_tenants):
    client, factory, tokens, a, b = two_tenants
    sb = source(client, tokens["other_admin"], b)
    with factory() as s:
        s.add(models.ChangeSourceDeliveryRecord(tenant_id=a, delivery_id="delivery:forged",
            source_id=sb, delivery_key="forged", payload_sha256="a" * 64, status="received",
            headers_json="{}", payload_json="{}", event_ids_json="[]", received_at=NOW.isoformat()))
        with pytest.raises(TenantResourceNotFound):
            tenant_commit(s, tenant_id=a)
        s.rollback()
        assert s.get(models.ChangeSourceDeliveryRecord, "delivery:forged") is None
