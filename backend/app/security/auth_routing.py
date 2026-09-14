from __future__ import annotations

import re
from enum import Enum


class RouteAuthDomain(str, Enum):
    PUBLIC_LIVENESS = "PUBLIC_LIVENESS"
    PUBLIC_READINESS_MINIMAL = "PUBLIC_READINESS_MINIMAL"
    PUBLIC_CORS_PREFLIGHT = "PUBLIC_CORS_PREFLIGHT"
    USER_AUTHENTICATED = "USER_AUTHENTICATED"
    AGENT_AUTHENTICATED = "AGENT_AUTHENTICATED"
    PROVIDER_CALLBACK_AUTHENTICATED = "PROVIDER_CALLBACK_AUTHENTICATED"
    INTERNAL_SERVICE_AUTHENTICATED = "INTERNAL_SERVICE_AUTHENTICATED"
    DISABLED_PRODUCTION = "DISABLED_PRODUCTION"


_PROVIDER_CALLBACK = re.compile(
    r"^/api/v1/change-source-webhooks/[^/]+$"
)


def classify_route(
    method: str,
    path: str,
) -> RouteAuthDomain | None:
    normalized_method = method.upper()

    if normalized_method == "OPTIONS":
        return RouteAuthDomain.PUBLIC_CORS_PREFLIGHT
    if normalized_method == "GET" and path == "/startup":
        return RouteAuthDomain.PUBLIC_LIVENESS
    if normalized_method == "GET" and path == "/health":
        return RouteAuthDomain.PUBLIC_LIVENESS
    if normalized_method == "GET" and path == "/ready":
        return RouteAuthDomain.PUBLIC_READINESS_MINIMAL
    if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
        return RouteAuthDomain.DISABLED_PRODUCTION
    if normalized_method == "POST" and path == "/api/v1/agents/enroll":
        return RouteAuthDomain.AGENT_AUTHENTICATED
    if path.startswith("/api/v1/agent/"):
        return RouteAuthDomain.AGENT_AUTHENTICATED
    if normalized_method == "POST" and _PROVIDER_CALLBACK.fullmatch(path):
        return RouteAuthDomain.PROVIDER_CALLBACK_AUTHENTICATED
    if path.startswith("/api/"):
        return RouteAuthDomain.USER_AUTHENTICATED
    return None
