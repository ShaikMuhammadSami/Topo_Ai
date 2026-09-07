"""PH-5B assignment inputs and atomic credential integration (not PH-5C gates)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    AuthApiCredentialRecord,
    AuthPrincipalRecord,
    InstallationOperatorAssignmentRecord,
    ServicePrincipalPermissionRecord,
    TenantMembershipRecord,
)
from app.models.auth import ApiCredentialCreate
from app.models.tenant import TenantMembershipCreate, TenantMembershipRecovery
from app.services.authority_assignments import resolve_service_permissions
from app.services.principal_identity import create_service_principal
from test_tenant_foundation import tenant_app, _bearer, _create_tenant


def _payload(tenant_id, **changes):
    return {
        "name": "PH-5B service", "caller_type": "service_api",
        "subject": "service:ph5b", "roles": ["admin"], "tenant_id": tenant_id,
        "permissions": ["topology.read", "incident.read"], **changes,
    }


@pytest.mark.parametrize("role", [None, "admin", "tenant_admin ", "TENANT_ADMIN", "", "*", ["tenant_admin"]])
def test_membership_input_requires_exact_explicit_role(role):
    values = {"subject": "human:test"}
    if role is not None:
        values["role"] = role
    with pytest.raises(ValueError):
        TenantMembershipCreate(**values)
    with pytest.raises(ValueError):
        TenantMembershipRecovery(tenant_id="tenant:11111111-1111-4111-8111-111111111111", **values)


@pytest.mark.parametrize("permissions", [None, [], ["*"], ["member.manage"], ["incident.read", "incident.read"], [" INCIDENT.READ"], "incident.read", {"incident.read": True}, [1]])
def test_new_service_input_requires_exact_nonempty_explicit_permissions(permissions):
    with pytest.raises(ValueError):
        ApiCredentialCreate(**_payload("tenant:11111111-1111-4111-8111-111111111111", permissions=permissions))


def test_human_credential_cannot_assign_service_permissions():
    with pytest.raises(ValueError):
        ApiCredentialCreate(name="human", caller_type="human_api", subject="human:test", permissions=["incident.read"])


def test_membership_explicit_role_bootstrap_and_reactivation(tenant_app):
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        headers = _bearer(tokens["bootstrap"], tenant["tenant_id"])
        missing = client.post("/api/v1/tenant-memberships", headers=headers, json={"subject": "test:viewer"})
        assert missing.status_code == 422
        request = {"subject": "test:viewer", "role": "tenant_viewer"}
        added = client.post("/api/v1/tenant-memberships", headers=headers, json=request)
        assert added.status_code == 200
        body = added.json()
        assert body["role"] == "tenant_viewer"
        assert body["principal_type"] == "human"
        assert client.post("/api/v1/tenant-memberships", headers=headers, json={**request, "role": "tenant_admin"}).status_code == 422
        assert client.post(f'/api/v1/tenant-memberships/{body["membership_id"]}/disable', headers=headers).status_code == 200
        restored = client.post("/api/v1/tenant-memberships", headers=headers, json={**request, "role": "tenant_responder"})
        assert restored.json()["role"] == "tenant_responder"
        assert restored.json()["membership_id"] == body["membership_id"]
        assert restored.json()["principal_id"] == body["principal_id"]
    with factory() as session:
        assert session.get(TenantMembershipRecord, tenant["membership_id"]).role == "tenant_admin"
        assert session.scalar(select(func.count()).select_from(InstallationOperatorAssignmentRecord)) == 0
        assert session.scalar(select(func.count()).select_from(TenantMembershipRecord)) == 2


def test_service_rotation_preserves_principal_authority_and_revocation(tenant_app):
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        headers = _bearer(tokens["bootstrap"])
        path = "/api/v1/auth/api-credentials"
        first = client.post(path, headers=headers, json=_payload(tenant["tenant_id"]))
        assert first.status_code == 201
        original = first.json()
        following = _payload(tenant["tenant_id"], principal_id=original["principal_id"])
        following.pop("permissions")
        second = client.post(path, headers=headers, json=following)
        assert second.status_code == 201
        assert second.json()["principal_id"] == original["principal_id"]
        assert client.post(path, headers=headers, json={**following, "permissions": ["incident.respond"]}).status_code == 409
        assert client.post(path + "/" + original["credential_id"] + "/revoke", headers=headers).status_code == 200
    with factory() as session:
        assignment = session.get(ServicePrincipalPermissionRecord, original["principal_id"])
        assert assignment.permissions_json == '["incident.read","topology.read"]'
        assert assignment.row_version == 1
        assert resolve_service_permissions(session, principal_id=original["principal_id"]) == {"incident.read", "topology.read"}
        assert session.scalar(select(func.count()).select_from(ServicePrincipalPermissionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(AuthApiCredentialRecord)) == 2


def test_existing_service_missing_assignment_cannot_infer_from_credential(tenant_app):
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        with factory() as session:
            service = create_service_principal(session, display_name="No authority")
            principal_id = service.principal_id
            session.commit()
        response = client.post("/api/v1/auth/api-credentials", headers=_bearer(tokens["bootstrap"]), json=_payload(tenant["tenant_id"], principal_id=principal_id))
        assert response.status_code == 409
    with factory() as session:
        assert session.get(ServicePrincipalPermissionRecord, principal_id) is None
        assert session.scalar(select(func.count()).select_from(AuthApiCredentialRecord)) == 0


def test_failed_service_binding_does_not_leave_orphan_authority(tenant_app, monkeypatch):
    from app.repositories import tenant_repository
    from sqlalchemy.exc import OperationalError

    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        def unavailable(*args, **kwargs):
            raise OperationalError("binding", {}, RuntimeError("unavailable"))
        monkeypatch.setattr(tenant_repository, "add_service_api_tenant_binding", unavailable)
        response = client.post("/api/v1/auth/api-credentials", headers=_bearer(tokens["bootstrap"]), json=_payload(tenant["tenant_id"]))
        assert response.status_code == 503
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuthPrincipalRecord).where(AuthPrincipalRecord.principal_type == "service")) == 0
        assert session.scalar(select(func.count()).select_from(ServicePrincipalPermissionRecord)) == 0
        assert session.scalar(select(func.count()).select_from(AuthApiCredentialRecord)) == 0


def test_generated_credential_collision_retry_keeps_service_assignment_atomic(tenant_app, monkeypatch):
    import app.services.auth_api_credential_service as service

    application, factory, tokens = tenant_app
    original_add = service.add_auth_api_credential
    attempts = []
    def once(session, record):
        attempts.append(record.credential_id)
        if len(attempts) == 1:
            raise IntegrityError("generated collision", {}, RuntimeError("duplicate"))
        original_add(session, record)
    with TestClient(application) as client:
        tenant = _create_tenant(client, tokens["bootstrap"])
        monkeypatch.setattr(service, "add_auth_api_credential", once)
        response = client.post("/api/v1/auth/api-credentials", headers=_bearer(tokens["bootstrap"]), json=_payload(tenant["tenant_id"]))
        assert response.status_code == 201
        principal_id = response.json()["principal_id"]
    assert len(attempts) == 2
    with factory() as session:
        assert session.get(AuthPrincipalRecord, principal_id).principal_type == "service"
        assert json.loads(session.get(ServicePrincipalPermissionRecord, principal_id).permissions_json) == ["incident.read", "topology.read"]
        assert session.scalar(select(func.count()).select_from(AuthApiCredentialRecord)) == 1
