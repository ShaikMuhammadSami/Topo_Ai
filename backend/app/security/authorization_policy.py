"""Code-owned PH-5B authority vocabulary; route enforcement belongs to PH-5C."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class Permission(StrEnum):
    INCIDENT_READ = "incident.read"
    INCIDENT_RESPOND = "incident.respond"
    TOPOLOGY_READ = "topology.read"
    EVIDENCE_READ = "evidence.read"
    REPORT_READ = "report.read"
    INTEGRATION_READ = "integration.read"
    INTEGRATION_MANAGE = "integration.manage"
    OWNERSHIP_READ = "ownership.read"
    OWNERSHIP_MANAGE = "ownership.manage"
    MEMBER_READ = "member.read"
    MEMBER_MANAGE = "member.manage"
    CREDENTIAL_METADATA_READ = "credential.metadata.read"
    CREDENTIAL_ROTATE = "credential.rotate"
    TENANT_SETTINGS_MANAGE = "tenant.settings.manage"
    INSTALLATION_STATUS_READ = "installation.status.read"
    INSTALLATION_BOOTSTRAP = "installation.bootstrap"
    INSTALLATION_RECOVERY = "installation.recovery"
    INSTALLATION_SECRET_MANAGE = "installation.secret.manage"


class TenantRole(StrEnum):
    VIEWER = "tenant_viewer"
    RESPONDER = "tenant_responder"
    ADMIN = "tenant_admin"


class InstallationRole(StrEnum):
    OPERATOR = "installation_operator"


TENANT_PERMISSIONS = frozenset({
    Permission.INCIDENT_READ,
    Permission.INCIDENT_RESPOND,
    Permission.TOPOLOGY_READ,
    Permission.EVIDENCE_READ,
    Permission.REPORT_READ,
    Permission.INTEGRATION_READ,
    Permission.INTEGRATION_MANAGE,
    Permission.OWNERSHIP_READ,
    Permission.OWNERSHIP_MANAGE,
    Permission.MEMBER_READ,
    Permission.MEMBER_MANAGE,
    Permission.CREDENTIAL_METADATA_READ,
    Permission.CREDENTIAL_ROTATE,
    Permission.TENANT_SETTINGS_MANAGE,
})

INSTALLATION_PERMISSIONS = frozenset({
    Permission.INSTALLATION_STATUS_READ,
    Permission.INSTALLATION_BOOTSTRAP,
    Permission.INSTALLATION_RECOVERY,
    Permission.INSTALLATION_SECRET_MANAGE,
})

# Every bundle is explicit: a new enum member grants no authority implicitly.
TENANT_ROLE_PERMISSIONS = MappingProxyType({
    TenantRole.VIEWER: frozenset({
        Permission.INCIDENT_READ,
        Permission.TOPOLOGY_READ,
        Permission.EVIDENCE_READ,
        Permission.REPORT_READ,
        Permission.INTEGRATION_READ,
        Permission.OWNERSHIP_READ,
    }),
    TenantRole.RESPONDER: frozenset({
        Permission.INCIDENT_READ,
        Permission.INCIDENT_RESPOND,
        Permission.TOPOLOGY_READ,
        Permission.EVIDENCE_READ,
        Permission.REPORT_READ,
        Permission.INTEGRATION_READ,
        Permission.OWNERSHIP_READ,
    }),
    TenantRole.ADMIN: frozenset({
        Permission.INCIDENT_READ,
        Permission.INCIDENT_RESPOND,
        Permission.TOPOLOGY_READ,
        Permission.EVIDENCE_READ,
        Permission.REPORT_READ,
        Permission.INTEGRATION_READ,
        Permission.INTEGRATION_MANAGE,
        Permission.OWNERSHIP_READ,
        Permission.OWNERSHIP_MANAGE,
        Permission.MEMBER_READ,
        Permission.MEMBER_MANAGE,
        Permission.CREDENTIAL_METADATA_READ,
        Permission.CREDENTIAL_ROTATE,
        Permission.TENANT_SETTINGS_MANAGE,
    }),
})

INSTALLATION_ROLE_PERMISSIONS = MappingProxyType({
    InstallationRole.OPERATOR: frozenset({
        Permission.INSTALLATION_STATUS_READ,
        Permission.INSTALLATION_BOOTSTRAP,
        Permission.INSTALLATION_RECOVERY,
        Permission.INSTALLATION_SECRET_MANAGE,
    }),
})

SERVICE_ASSIGNABLE_PERMISSIONS = frozenset({
    Permission.INCIDENT_READ,
    Permission.INCIDENT_RESPOND,
    Permission.TOPOLOGY_READ,
    Permission.EVIDENCE_READ,
    Permission.REPORT_READ,
    Permission.INTEGRATION_READ,
    Permission.INTEGRATION_MANAGE,
    Permission.OWNERSHIP_READ,
    Permission.OWNERSHIP_MANAGE,
})


class AuthorityValidationError(ValueError):
    """An authority code or explicit permission list is invalid."""


def normalize_service_permissions(values: list[str | Permission]) -> list[str]:
    """Validate exact codes before canonicalizing order; never discard values."""
    if type(values) is not list or not 1 <= len(values) <= len(SERVICE_ASSIGNABLE_PERMISSIONS):
        raise AuthorityValidationError("SERVICE_PERMISSIONS_INVALID")
    parsed: set[Permission] = set()
    for value in values:
        if type(value) not in {str, Permission}:
            raise AuthorityValidationError("SERVICE_PERMISSIONS_INVALID")
        try:
            permission = Permission(value)
        except ValueError as exc:
            raise AuthorityValidationError("SERVICE_PERMISSIONS_INVALID") from exc
        if permission not in SERVICE_ASSIGNABLE_PERMISSIONS or permission in parsed:
            raise AuthorityValidationError("SERVICE_PERMISSIONS_INVALID")
        parsed.add(permission)
    return sorted(permission.value for permission in parsed)
