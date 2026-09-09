"""PH-5E proof that every dormant execution surface remains denied."""

from __future__ import annotations

from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import SecurityAuditEventRecord
from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_authentication_self_service,
    authorize_service_operation,
)
from app.security.authorization_plan import (
    CRITICAL_OPERATION_PLAN,
    ROUTE_AUTHORIZATION_PLAN,
    AuthorizationIntent,
)
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal


TOKEN = "ph2b-test-human-bearer-" + ("x" * 32)


def _path(template: str) -> str:
    return (
        template.replace("{incident_id}", "incident%3Aph5e")
        .replace("{approval_id}", "approval%3Aph5e")
        .replace("{execution_id}", "execution%3Aph5e")
    )


def test_all_ten_dormant_http_routes_are_401_or_bounded_403_and_audited_once(
    required_auth_app,
) -> None:
    routes = [
        entry
        for entry in ROUTE_AUTHORIZATION_PLAN.values()
        if entry.authority.intent is AuthorizationIntent.V1_DORMANT_EXECUTION_DENY
    ]
    assert len(routes) == 10
    with TestClient(required_auth_app) as client:
        for entry in routes:
            anonymous = client.request(entry.method, _path(entry.path), json={})
            assert anonymous.status_code == 401
            denied = client.request(
                entry.method,
                _path(entry.path),
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={"hostile": "must not reach dormant business logic"},
            )
            assert denied.status_code == 403
            assert denied.json() == {
                "detail": {"code": "V1_EXECUTION_DISABLED"}
            }

    with required_auth_app.state.session_factory() as session:
        events = list(session.scalars(select(SecurityAuditEventRecord)))
    assert len(events) == 10
    assert Counter(event.action for event in events) == {"execution.denied": 10}
    assert {event.result for event in events} == {"denied"}
    assert {event.reason_code for event in events} == {"execution_disabled"}
    assert {event.permissions_json for event in events} == {"[]"}
    assert all(event.resource_id is None for event in events)


def test_all_eleven_dormant_service_operations_deny_every_context_shape() -> None:
    operations = [
        operation_id
        for operation_id, entry in CRITICAL_OPERATION_PLAN.items()
        if entry.authority.intent is AuthorizationIntent.V1_DORMANT_EXECUTION_DENY
    ]
    assert len(operations) == 11
    assert not any(
        word in permission.value
        for permission in Permission
        for word in ("execute", "execution", "approve", "remediation")
    )
    self_context = authorize_authentication_self_service(
        AuthPrincipal(
            principal_id="principal:00000000-0000-0000-0000-000000000001",
            principal_type="human",
            subject="ph5e:self",
            display_name="PH-5E",
            roles=("admin", "operator"),
            authentication_type="human_api_token",
        )
    )
    for operation_id in operations:
        with pytest.raises(AuthorizationFailure, match="V1_EXECUTION_DISABLED"):
            authorize_service_operation(operation_id)
        with pytest.raises(AuthorizationFailure, match="V1_EXECUTION_DISABLED"):
            authorize_service_operation(
                operation_id, authorization_context=self_context
            )
