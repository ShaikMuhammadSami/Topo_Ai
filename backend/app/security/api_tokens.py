from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.security.auth_config import (
    AuthConfiguration,
    AuthMode,
    TokenIdentity,
    load_auth_configuration,
    load_token_registry,
)
from app.security.auth_routing import RouteAuthDomain, classify_route


AUTH_ENABLED_ENV = "TOPO_AUTH_ENABLED"
TOKEN_REGISTRY_ENV = "TOPO_API_TOKEN_HASHES_JSON"


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    display_name: str
    roles: tuple[str, ...]
    authentication_type: str


def authentication_enabled() -> bool:
    """Compatibility helper backed by the validated fail-closed contract."""
    return load_auth_configuration().mode is AuthMode.REQUIRED


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resolve_principal(
    token: str,
    *,
    registry: Mapping[str, TokenIdentity] | None = None,
) -> AuthPrincipal | None:
    candidate_hash = token_digest(token)
    configured_registry = registry if registry is not None else load_token_registry()

    matched_identity: TokenIdentity | None = None
    for known_hash, identity in configured_registry.items():
        if hmac.compare_digest(candidate_hash, known_hash):
            matched_identity = identity
            break

    if matched_identity is None:
        return None

    return AuthPrincipal(
        subject=matched_identity.subject,
        display_name=matched_identity.display_name,
        roles=matched_identity.roles,
        authentication_type="api_token",
    )


def development_principal() -> AuthPrincipal:
    return AuthPrincipal(
        subject="local-development",
        display_name="Local Development User",
        roles=("admin", "operator"),
        authentication_type="development",
    )


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


class ApiTokenAuthMiddleware(BaseHTTPMiddleware):
    """Dispatch inbound requests to their explicit authentication domain."""

    def __init__(
        self,
        app,
        *,
        configuration: AuthConfiguration,
    ) -> None:
        super().__init__(app)
        self.configuration = configuration

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        domain = classify_route(request.method, request.url.path)

        if domain in {
            RouteAuthDomain.PUBLIC_LIVENESS,
            RouteAuthDomain.PUBLIC_READINESS_MINIMAL,
            RouteAuthDomain.PUBLIC_CORS_PREFLIGHT,
            RouteAuthDomain.AGENT_AUTHENTICATED,
            RouteAuthDomain.PROVIDER_CALLBACK_AUTHENTICATED,
        }:
            return await call_next(request)

        if domain is RouteAuthDomain.DISABLED_PRODUCTION:
            if self.configuration.mode is AuthMode.DEVELOPMENT_DISABLED:
                return await call_next(request)
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        if domain is None:
            return await call_next(request)

        if domain is not RouteAuthDomain.USER_AUTHENTICATED:
            return _unauthorized("Authentication is required.")

        if self.configuration.mode is AuthMode.DEVELOPMENT_DISABLED:
            request.state.principal = development_principal()
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            return _unauthorized("A Bearer API token is required.")

        principal = resolve_principal(
            token.strip(),
            registry=self.configuration.token_registry,
        )
        if principal is None:
            return _unauthorized("The supplied API token is invalid.")

        request.state.principal = principal
        return await call_next(request)
