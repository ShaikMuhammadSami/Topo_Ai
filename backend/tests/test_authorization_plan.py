"""Freeze the PH-5B plan; no test enables PH-5C route enforcement."""

import ast
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.security.authorization_plan import (
    AUTHENTICATOR_CREDENTIAL_POLICY,
    CRITICAL_OPERATION_PLAN,
    ERROR_CONTRACT,
    ROUTE_AUTHORIZATION_PLAN,
    AuthorizationIntent as I,
    operation_authorization_plan,
    route_authorization_plan,
)
from app.security.authorization_policy import (
    INSTALLATION_PERMISSIONS,
    SERVICE_ASSIGNABLE_PERMISSIONS,
    TENANT_PERMISSIONS,
    Permission,
)
from app.security.tenant_routing import classify_tenant_route
from test_authentication_acceptance import _registered_routes


APP = Path(__file__).resolve().parents[1] / "app"

EXPECTED_ROUTE_COUNTS = {
    I.PUBLIC: 2,
    I.AUTHENTICATION_SELF_SERVICE: 7,
    I.TENANT_PERMISSION: 109,
    I.INSTALLATION_PERMISSION: 2,
    I.AGENT_FIXED_PURPOSE: 8,
    I.PROVIDER_FIXED_PURPOSE: 1,
    I.V1_DORMANT_EXECUTION_DENY: 10,
    I.AUTHENTICATOR_CREDENTIAL_POLICY: 4,
}

CREDENTIAL_ROUTES = {
    ("POST", "/api/v1/auth/api-credentials"): "create",
    ("GET", "/api/v1/auth/api-credentials"): "list",
    ("GET", "/api/v1/auth/api-credentials/{credential_id}"): "get",
    ("POST", "/api/v1/auth/api-credentials/{credential_id}/revoke"): "revoke",
}

EXECUTION_ROUTES = {
    ("POST", "/api/v1/incidents/{incident_id}/approvals"),
    ("GET", "/api/v1/incidents/{incident_id}/approvals"),
    ("GET", "/api/v1/incidents/{incident_id}/approvals/{approval_id}"),
    ("POST", "/api/v1/incidents/{incident_id}/approvals/{approval_id}/approve"),
    ("POST", "/api/v1/incidents/{incident_id}/approvals/{approval_id}/reject"),
    ("POST", "/api/v1/incidents/{incident_id}/approvals/{approval_id}/revoke"),
    ("POST", "/api/v1/incidents/{incident_id}/execution-intents"),
    ("GET", "/api/v1/incidents/{incident_id}/execution-intents"),
    ("GET", "/api/v1/incidents/{incident_id}/execution-intents/{execution_id}"),
    ("POST", "/api/v1/incidents/{incident_id}/execution-intents/{execution_id}/cancel"),
}


def _function_source(target):
    module_name, function_name = target.rsplit(".", 1)
    path = APP.parent.joinpath(*module_name.split(".")).with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    functions = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert function_name in functions, target
    return functions[function_name]


def test_every_live_production_route_has_one_explicit_plan(required_auth_app):
    live = [
        (method, route.path)
        for route in _registered_routes(required_auth_app)
        for method in route.methods
    ]
    assert len(live) == len(set(live)) == 143
    assert set(live) == set(ROUTE_AUTHORIZATION_PLAN)
    assert Counter(plan.authority.intent for plan in ROUTE_AUTHORIZATION_PLAN.values()) == EXPECTED_ROUTE_COUNTS
    assert Counter(classify_tenant_route(*key).value for key in live) == {
        "PH3D_TENANT_REQUIRED": 116,
        "MACHINE_BOUND": 9,
        "TENANT_CONTROL": 7,
        "SECURITY_GLOBAL": 9,
        "PUBLIC": 2,
    }


def test_unknown_route_or_operation_never_receives_fallback_authority():
    for key in [
        ("GET", "/api/v1/new-unreviewed-route"),
        ("POST", "/health"),
        ("get", "/api/v1/incident-records"),
        ("GET", "/api/v1/incident-records/actual-object-id"),
    ]:
        with pytest.raises(KeyError):
            route_authorization_plan(*key)
    with pytest.raises(KeyError):
        operation_authorization_plan("unreviewed.operation")
    with pytest.raises(TypeError):
        ROUTE_AUTHORIZATION_PLAN[("GET", "/new")] = None
    with pytest.raises(FrozenInstanceError):
        route_authorization_plan("GET", "/health").method = "POST"


def test_permission_authorities_are_explicit_scoped_and_never_execution():
    for plan in (*ROUTE_AUTHORIZATION_PLAN.values(), *CRITICAL_OPERATION_PLAN.values()):
        authority = plan.authority
        if authority.intent is I.TENANT_PERMISSION:
            assert authority.permissions
            assert authority.permissions <= TENANT_PERMISSIONS
        elif authority.intent is I.INSTALLATION_PERMISSION:
            assert authority.permissions
            assert authority.permissions <= INSTALLATION_PERMISSIONS
        else:
            assert not authority.permissions
        assert authority.rationale
        assert all("execute" not in permission.value and "approve" not in permission.value for permission in authority.permissions)


def test_machine_and_public_classifications_are_exactly_frozen():
    machine = {
        key for key, plan in ROUTE_AUTHORIZATION_PLAN.items()
        if plan.authority.intent in {I.AGENT_FIXED_PURPOSE, I.PROVIDER_FIXED_PURPOSE}
    }
    assert len(machine) == 9
    assert {key for key in ROUTE_AUTHORIZATION_PLAN if classify_tenant_route(*key).value == "MACHINE_BOUND"} == machine
    assert {
        key for key, plan in ROUTE_AUTHORIZATION_PLAN.items()
        if plan.authority.intent is I.PUBLIC
    } == {("GET", "/health"), ("GET", "/ready")}
    assert route_authorization_plan("GET", "/api/v1/topology/sample").authority.intent is I.AUTHENTICATION_SELF_SERVICE


def test_tenant_control_and_security_global_maps_do_not_imply_operator_superuser():
    expected = {
        ("POST", "/api/v1/tenants"): (I.INSTALLATION_PERMISSION, {"installation.bootstrap"}),
        ("POST", "/api/v1/tenant-memberships/recover"): (I.INSTALLATION_PERMISSION, {"installation.recovery"}),
        ("GET", "/api/v1/tenants"): (I.AUTHENTICATION_SELF_SERVICE, set()),
        ("GET", "/api/v1/tenant-context"): (I.AUTHENTICATION_SELF_SERVICE, set()),
        ("GET", "/api/v1/tenant-memberships"): (I.TENANT_PERMISSION, {"member.read"}),
        ("POST", "/api/v1/tenant-memberships"): (I.TENANT_PERMISSION, {"member.manage"}),
        ("POST", "/api/v1/tenant-memberships/{membership_id}/disable"): (I.TENANT_PERMISSION, {"member.manage"}),
    }
    for key, (intent, permissions) in expected.items():
        plan = route_authorization_plan(*key)
        assert plan.authority.intent is intent
        assert {permission.value for permission in plan.authority.permissions} == permissions
    security_global = [
        plan for key, plan in ROUTE_AUTHORIZATION_PLAN.items()
        if classify_tenant_route(*key).value == "SECURITY_GLOBAL"
    ]
    assert Counter(plan.authority.intent for plan in security_global) == {
        I.AUTHENTICATION_SELF_SERVICE: 5, I.AUTHENTICATOR_CREDENTIAL_POLICY: 4,
    }


def test_credential_policy_class_applies_only_to_four_architect_approved_routes():
    actual = {
        key: plan.credential_operation
        for key, plan in ROUTE_AUTHORIZATION_PLAN.items()
        if plan.authority.intent is I.AUTHENTICATOR_CREDENTIAL_POLICY
    }
    assert actual == CREDENTIAL_ROUTES
    assert len(AUTHENTICATOR_CREDENTIAL_POLICY) == 8
    assert len({(policy.operation, policy.target_type) for policy in AUTHENTICATOR_CREDENTIAL_POLICY}) == 8
    assert all(not plan.authority.permissions for key, plan in ROUTE_AUTHORIZATION_PLAN.items() if key in actual)
    assert "AUTHENTICATOR_CREDENTIAL_POLICY" not in {permission.value for permission in Permission}


@pytest.mark.parametrize("operation", ["create", "list", "get", "revoke"])
def test_human_authenticator_plan_is_principal_self_only(operation):
    policy = next(policy for policy in AUTHENTICATOR_CREDENTIAL_POLICY if policy.operation == operation and policy.target_type == "human")
    assert policy.caller_principal_type == "human"
    assert policy.ownership_rule == "target.principal_id == caller.principal_id"
    assert not policy.permissions
    assert not policy.valid_tenant_context_required
    assert not policy.accepted_service_binding_required
    assert not policy.tenant_membership_implies_human_credential_ownership
    assert not policy.installation_assignment_grants_authority
    assert policy.foreign_object_status == 404
    assert policy.raw_credential_returned_once is (operation == "create")
    entry = operation_authorization_plan("authenticator.human." + operation)
    assert entry.authority.intent is I.AUTHENTICATION_SELF_SERVICE
    assert "HUMAN caller only" in entry.authority.rationale
    assert "membership implies no ownership" in entry.authority.rationale


@pytest.mark.parametrize("operation", ["create", "list", "get", "revoke"])
def test_service_authenticator_plan_requires_human_and_same_validated_tenant(operation):
    policy = next(policy for policy in AUTHENTICATOR_CREDENTIAL_POLICY if policy.operation == operation and policy.target_type == "service")
    expected = Permission("credential.metadata.read" if operation in {"get", "list"} else "credential.rotate")
    assert policy.caller_principal_type == "human"
    assert policy.ownership_rule == "service_api_tenant_binding.tenant_id == tenant_context.tenant_id"
    assert policy.permissions == {expected}
    assert policy.valid_tenant_context_required
    assert policy.accepted_service_binding_required
    assert not policy.installation_assignment_grants_authority
    assert not policy.tenant_membership_implies_human_credential_ownership
    assert policy.foreign_object_status == 404
    assert policy.raw_credential_returned_once is (operation == "create")
    # Neither service assignment nor installation assignment can satisfy this.
    assert not (policy.permissions & SERVICE_ASSIGNABLE_PERMISSIONS)
    assert not (policy.permissions & INSTALLATION_PERMISSIONS)
    entry = operation_authorization_plan("authenticator.service." + operation)
    assert entry.authority.permissions == policy.permissions
    assert "HUMAN caller only" in entry.authority.rationale


def test_combined_integration_secret_operations_require_all_permissions():
    for key in [
        ("POST", "/api/v1/change-sources"),
        ("PATCH", "/api/v1/change-sources/{source_id}"),
        ("POST", "/api/v1/integrations/webhooks"),
        ("PATCH", "/api/v1/integrations/webhooks/{webhook_id}"),
    ]:
        permissions = route_authorization_plan(*key).authority.permissions
        assert permissions == {Permission("integration.manage"), Permission("credential.rotate")}
        assert not permissions <= SERVICE_ASSIGNABLE_PERMISSIONS
    for key in [
        ("GET", "/api/v1/change-sources"),
        ("GET", "/api/v1/change-sources/{source_id}"),
        ("GET", "/api/v1/change-sources/{source_id}/doctor"),
        ("GET", "/api/v1/integrations/webhooks"),
    ]:
        assert route_authorization_plan(*key).authority.permissions == {
            Permission("integration.read"), Permission("credential.metadata.read"),
        }


def test_mutation_mapping_preserves_viewer_read_boundaries():
    expected = {
        ("POST", "/api/v1/snapshots/capture"): "integration.manage",
        ("POST", "/api/v1/identities/materialize"): "integration.manage",
        ("POST", "/api/v1/identities/overrides"): "tenant.settings.manage",
        ("POST", "/api/v1/incidents/{incident_id}/reports"): "incident.respond",
        ("PATCH", "/api/v1/recommendations/{recommendation_id}/status"): "incident.respond",
        ("POST", "/api/v1/recovery/verify"): "incident.respond",
        ("POST", "/api/v1/topology/validate"): "topology.read",
        ("POST", "/api/v1/kubernetes/discover"): "topology.read",
    }
    for key, permission in expected.items():
        assert route_authorization_plan(*key).authority.permissions == {Permission(permission)}


def test_all_current_execution_control_surfaces_are_planned_deny():
    actual = {
        key for key, plan in ROUTE_AUTHORIZATION_PLAN.items()
        if plan.authority.intent is I.V1_DORMANT_EXECUTION_DENY
    }
    assert actual == EXECUTION_ROUTES
    denied = {
        entry.target for entry in CRITICAL_OPERATION_PLAN.values()
        if entry.authority.intent is I.V1_DORMANT_EXECUTION_DENY
    }
    assert denied == {
        "app.services.action_approval.create_action_approval",
        "app.services.action_approval.get_action_approval",
        "app.services.action_approval.list_action_approvals",
        "app.services.action_approval.decide_action_approval",
        "app.services.action_approval.revoke_action_approval",
        "app.services.execution_transaction.create_execution_intent",
        "app.services.execution_transaction.get_execution_intent",
        "app.services.execution_transaction.list_execution_intents",
        "app.services.execution_transaction.cancel_execution_intent",
        "app.services.execution_transaction.claim_execution_intent",
        "app.services.execution_transaction.release_execution_claim",
    }
    assert route_authorization_plan("GET", "/api/v1/incidents/{incident_id}/execution-readiness").authority.permissions == {Permission("evidence.read")}


def test_execution_getters_are_not_misclassified_as_read_only():
    for target, refresh in [
        ("app.services.action_approval.get_action_approval", "_refresh_active_record"),
        ("app.services.action_approval.list_action_approvals", "_refresh_active_record"),
        ("app.services.execution_transaction.get_execution_intent", "_refresh_active_intent"),
        ("app.services.execution_transaction.list_execution_intents", "_refresh_active_intent"),
    ]:
        source = _function_source(target)
        assert refresh in {ast.unparse(node.func) for node in ast.walk(source) if isinstance(node, ast.Call)}
        assert operation_authorization_plan(target).authority.intent is I.V1_DORMANT_EXECUTION_DENY


def test_critical_operation_inventory_references_actual_functions_and_callers():
    assert len(CRITICAL_OPERATION_PLAN) == 98
    assert Counter(plan.authority.intent for plan in CRITICAL_OPERATION_PLAN.values()) == {
        I.TENANT_PERMISSION: 65, I.INSTALLATION_PERMISSION: 8,
        I.AUTHENTICATION_SELF_SERVICE: 8, I.AGENT_FIXED_PURPOSE: 5,
        I.PROVIDER_FIXED_PURPOSE: 1, I.V1_DORMANT_EXECUTION_DENY: 11,
    }
    for entry in CRITICAL_OPERATION_PLAN.values():
        _function_source(entry.target)
        for parent in entry.delegated_callers:
            source = _function_source(parent)
            called_names = {ast.unparse(node.func).rsplit(".", 1)[-1] for node in ast.walk(source) if isinstance(node, ast.Call)}
            assert entry.target.rsplit(".", 1)[-1] in called_names, (parent, entry.target)
    agent_pipeline = operation_authorization_plan("app.services.continuous_lifecycle.ingest_failure_signal_batch")
    assert "app.api.agents.submit_failure_signals" in agent_pipeline.delegated_callers
    assert "app.services.agent_snapshot_ingest.persist_agent_snapshot" in agent_pipeline.delegated_callers


def test_new_authority_assignment_operations_are_explicitly_planned():
    expected = {
        "app.services.authority_assignments.create_service_permission_assignment": (I.TENANT_PERMISSION, "credential.rotate"),
        "app.services.authority_assignments.update_service_permissions": (I.TENANT_PERMISSION, "credential.rotate"),
        "app.services.authority_assignments.get_installation_operator_status": (I.INSTALLATION_PERMISSION, "installation.status.read"),
        "app.services.authority_assignments.grant_installation_operator": (I.INSTALLATION_PERMISSION, "installation.recovery"),
        "app.services.authority_assignments.disable_installation_operator": (I.INSTALLATION_PERMISSION, "installation.recovery"),
    }
    for operation, (intent, permission) in expected.items():
        plan = operation_authorization_plan(operation)
        assert plan.authority.intent is intent
        assert plan.authority.permissions == {Permission(permission)}
        assert "tenant" in plan.authority.rationale.lower()


def test_registry_is_planning_only_and_preserves_error_contract():
    assert dict(ERROR_CONTRACT) == {
        "unauthenticated": 401,
        "valid_tenant_insufficient_permission": 403,
        "foreign_or_absent_object": 404,
    }
    for path in [APP / "main.py", *(APP / "api").glob("*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert "app.security.authorization_plan" not in imports, path
