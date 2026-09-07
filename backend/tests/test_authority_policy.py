from __future__ import annotations

import pytest

from app.security.authorization_policy import (
    INSTALLATION_PERMISSIONS,
    INSTALLATION_ROLE_PERMISSIONS,
    SERVICE_ASSIGNABLE_PERMISSIONS,
    TENANT_PERMISSIONS,
    TENANT_ROLE_PERMISSIONS,
    AuthorityValidationError,
    InstallationRole,
    Permission,
    TenantRole,
    normalize_service_permissions,
)


TENANT_CODES = {
    "incident.read", "incident.respond", "topology.read", "evidence.read",
    "report.read", "integration.read", "integration.manage", "ownership.read",
    "ownership.manage", "member.read", "member.manage", "credential.metadata.read",
    "credential.rotate", "tenant.settings.manage",
}
INSTALLATION_CODES = {
    "installation.status.read", "installation.bootstrap", "installation.recovery",
    "installation.secret.manage",
}
VIEWER_CODES = {
    "incident.read", "topology.read", "evidence.read", "report.read",
    "integration.read", "ownership.read",
}
SERVICE_CODES = {
    "incident.read", "incident.respond", "topology.read", "evidence.read",
    "report.read", "integration.read", "integration.manage", "ownership.read",
    "ownership.manage",
}


def test_exact_v1_vocabulary_and_four_authority_bundles() -> None:
    assert {permission.value for permission in Permission} == TENANT_CODES | INSTALLATION_CODES
    assert {permission.value for permission in TENANT_PERMISSIONS} == TENANT_CODES
    assert {permission.value for permission in INSTALLATION_PERMISSIONS} == INSTALLATION_CODES
    assert {role.value for role in TenantRole} == {"tenant_viewer", "tenant_responder", "tenant_admin"}
    assert {role.value for role in InstallationRole} == {"installation_operator"}
    assert TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER] == VIEWER_CODES
    assert TENANT_ROLE_PERMISSIONS[TenantRole.RESPONDER] == VIEWER_CODES | {"incident.respond"}
    assert TENANT_ROLE_PERMISSIONS[TenantRole.ADMIN] == TENANT_CODES
    assert INSTALLATION_ROLE_PERMISSIONS[InstallationRole.OPERATOR] == INSTALLATION_CODES
    assert len(TENANT_ROLE_PERMISSIONS) + len(INSTALLATION_ROLE_PERMISSIONS) == 4


def test_role_bundles_are_immutable_monotone_and_scoped() -> None:
    viewer = TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER]
    responder = TENANT_ROLE_PERMISSIONS[TenantRole.RESPONDER]
    admin = TENANT_ROLE_PERMISSIONS[TenantRole.ADMIN]
    assert viewer < responder < admin
    assert admin == TENANT_PERMISSIONS
    assert admin.isdisjoint(INSTALLATION_PERMISSIONS)
    assert all(isinstance(bundle, frozenset) for bundle in TENANT_ROLE_PERMISSIONS.values())
    with pytest.raises(TypeError):
        TENANT_ROLE_PERMISSIONS[TenantRole.VIEWER] = admin
    with pytest.raises(TypeError):
        INSTALLATION_ROLE_PERMISSIONS[InstallationRole.OPERATOR] = admin
    assert not any(
        word in permission.value
        for permission in Permission
        for word in ("execution", "execute", "approve", "remediation", "*", "secret.read")
    )


def test_service_allowlist_is_explicit_and_excludes_sensitive_administration() -> None:
    assert SERVICE_ASSIGNABLE_PERMISSIONS == SERVICE_CODES
    assert SERVICE_ASSIGNABLE_PERMISSIONS < TENANT_PERMISSIONS
    assert TENANT_PERMISSIONS - SERVICE_ASSIGNABLE_PERMISSIONS == {
        "member.read", "member.manage", "credential.metadata.read", "credential.rotate",
        "tenant.settings.manage",
    }
    assert SERVICE_ASSIGNABLE_PERMISSIONS.isdisjoint(INSTALLATION_PERMISSIONS)
    assert normalize_service_permissions([Permission.TOPOLOGY_READ, "incident.read"]) == [
        "incident.read", "topology.read",
    ]


@pytest.mark.parametrize("role", ["", "admin", "tenant_Admin", " tenant_viewer", "tenant_admin ", "*", "owner"])
def test_role_strings_are_exact(role) -> None:
    with pytest.raises(ValueError):
        TenantRole(role)


@pytest.mark.parametrize("permissions", [
    [], None, {}, "incident.read", ("incident.read",), {"incident.read"},
    [1], [True], [None], [b"incident.read"], ["incident.read", "incident.read"],
    ["incident.read", Permission.INCIDENT_READ], ["*"], ["execution.execute"],
    ["incident.Read"], [" incident.read"], ["incident.read "], ["unknown.permission"],
    ["member.read"], ["member.manage"], ["credential.metadata.read"],
    ["credential.rotate"], ["tenant.settings.manage"], ["installation.secret.manage"],
    ["installation.credential.rotate"], ["incident.read"] * 10,
])
def test_invalid_service_permission_input_is_not_silently_normalized(permissions) -> None:
    with pytest.raises(AuthorityValidationError, match="^SERVICE_PERMISSIONS_INVALID$"):
        normalize_service_permissions(permissions)
