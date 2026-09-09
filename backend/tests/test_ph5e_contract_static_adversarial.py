"""PH-5E static closure proof for frozen authority and audit contracts."""

from __future__ import annotations

import ast
from pathlib import Path

from app.db.models import SecurityAuditEventRecord
from app.models.security_audit import SecurityAuditAction, SecurityAuditReason
from app.security.authorization_plan import (
    AUTHENTICATOR_CREDENTIAL_POLICY,
    CRITICAL_OPERATION_PLAN,
    ROUTE_AUTHORIZATION_PLAN,
)
from app.security.authorization_policy import Permission


APP = Path(__file__).resolve().parents[1] / "app"


def _function(path: Path, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    assert len(matches) == 1, (path, name)
    return matches[0]


def test_authoritative_permission_resolvers_never_read_subject_or_legacy_roles() -> None:
    targets = {
        APP / "services" / "authority_assignments.py": (
            "resolve_tenant_permissions",
            "resolve_service_permissions",
            "resolve_installation_permissions",
        ),
        APP / "security" / "authorization_enforcement.py": (
            "authorize_tenant",
            "authorize_installation",
            "authorize_service_operation",
        ),
    }
    for path, functions in targets.items():
        for name in functions:
            node = _function(path, name)
            identifiers = {
                child.id for child in ast.walk(node) if isinstance(child, ast.Name)
            }
            attributes = {
                child.attr
                for child in ast.walk(node)
                if isinstance(child, ast.Attribute)
            }
            assert not ({"subject", "external_subject", "roles"} & identifiers)
            assert not ({"subject", "external_subject", "roles"} & attributes)


def test_production_has_no_generic_authorization_bypass_identifier() -> None:
    forbidden = {
        "bypass_authorization",
        "skip_authorization",
        "system_admin",
        "internal_superuser",
        "authorize_all",
        "is_superuser",
        "allow_all",
    }
    found: list[tuple[str, str]] = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
            if name in forbidden:
                found.append((str(path.relative_to(APP)), name))
    assert found == []


def test_route_operation_permission_and_authenticator_contracts_are_frozen() -> None:
    assert len(ROUTE_AUTHORIZATION_PLAN) == 143
    assert len(CRITICAL_OPERATION_PLAN) == 98
    assert len(AUTHENTICATOR_CREDENTIAL_POLICY) == 8
    assert {
        (policy.operation, policy.target_type)
        for policy in AUTHENTICATOR_CREDENTIAL_POLICY
    } == {
        (operation, target_type)
        for operation in ("create", "list", "get", "revoke")
        for target_type in ("human", "service")
    }
    assert len(Permission) == 18
    assert not any(
        marker in permission.value
        for permission in Permission
        for marker in ("*", "execute", "execution", "approve", "remediation")
    )


def test_audit_registry_schema_and_append_only_repository_are_frozen() -> None:
    assert len(SecurityAuditAction) == 33
    assert len(SecurityAuditReason) == 11
    assert [column.name for column in SecurityAuditEventRecord.__table__.columns] == [
        "audit_event_id",
        "occurred_at",
        "actor_principal_id",
        "actor_kind",
        "actor_reference",
        "authentication_type",
        "authority_kind",
        "tenant_id",
        "action",
        "permissions_json",
        "resource_type",
        "resource_id",
        "result",
        "reason_code",
        "request_id",
    ]
    repository = APP / "repositories" / "security_audit_repository.py"
    tree = ast.parse(repository.read_text(encoding="utf-8-sig"))
    public_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_functions == {"append_security_audit_event"}
