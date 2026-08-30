"""Reviewed PH-3D route classification; authentication remains PH-2's job.

Machine administration is NOT tenant isolated. These exceptions need the
server-owned enrollment/agent/source bindings reserved for PH-3E.
"""

from enum import StrEnum

from app.security.auth_routing import RouteAuthDomain, classify_route


class TenantRouteDomain(StrEnum):
    PH3D_TENANT_REQUIRED = "PH3D_TENANT_REQUIRED"
    MACHINE_AUTHORITY_DEFERRED = "MACHINE_AUTHORITY_DEFERRED"
    MACHINE_DEFERRED = "MACHINE_DEFERRED"
    TENANT_CONTROL = "TENANT_CONTROL"
    SECURITY_GLOBAL = "SECURITY_GLOBAL"
    PUBLIC = "PUBLIC"


MACHINE_AUTHORITY_ROUTES = {
    ("POST", "/api/v1/agents/enrollment-tokens"): "agent_enrollment_tokens",
    ("GET", "/api/v1/agents"): "topo_agents",
    ("GET", "/api/v1/agents/{agent_id}"): "topo_agents",
    ("GET", "/api/v1/agents/{agent_id}/health"): "topo_agents",
    ("POST", "/api/v1/agents/{agent_id}/revoke"): "topo_agents",
    ("GET", "/api/v1/agents/{agent_id}/plugins"): "topo_agents",
    ("GET", "/api/v1/agents/{agent_id}/cloud-status"): "topo_agents",
    ("POST", "/api/v1/change-sources"): "change_sources",
    ("GET", "/api/v1/change-sources"): "change_sources",
    ("GET", "/api/v1/change-sources/{source_id}"): "change_sources",
    ("PATCH", "/api/v1/change-sources/{source_id}"): "change_sources",
    ("GET", "/api/v1/change-sources/{source_id}/doctor"): "change_sources",
}

TENANT_CONTROL_PATHS = {
    "/api/v1/tenants",
    "/api/v1/tenant-context",
    "/api/v1/tenant-memberships",
    "/api/v1/tenant-memberships/recover",
    "/api/v1/tenant-memberships/{membership_id}/disable",
}


def classify_tenant_route(method: str, path: str) -> TenantRouteDomain | None:
    authentication = classify_route(method, path)
    if authentication in {
        RouteAuthDomain.PUBLIC_LIVENESS,
        RouteAuthDomain.PUBLIC_READINESS_MINIMAL,
        RouteAuthDomain.PUBLIC_CORS_PREFLIGHT,
    }:
        return TenantRouteDomain.PUBLIC
    if authentication in {
        RouteAuthDomain.AGENT_AUTHENTICATED,
        RouteAuthDomain.PROVIDER_CALLBACK_AUTHENTICATED,
    }:
        return TenantRouteDomain.MACHINE_DEFERRED
    if authentication is not RouteAuthDomain.USER_AUTHENTICATED:
        return None
    if (method.upper(), path) in MACHINE_AUTHORITY_ROUTES:
        return TenantRouteDomain.MACHINE_AUTHORITY_DEFERRED
    if path in TENANT_CONTROL_PATHS:
        return TenantRouteDomain.TENANT_CONTROL
    if path.startswith("/api/v1/auth/") or path in {
        "/api/v1/topology/sample",
        "/api/v1/system/whoami",
    }:
        return TenantRouteDomain.SECURITY_GLOBAL
    # New product routes are required by default, never silently deferred.
    # Acceptance inspects their actual FastAPI dependency graph.
    return TenantRouteDomain.PH3D_TENANT_REQUIRED
