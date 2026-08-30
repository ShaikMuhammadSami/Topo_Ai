from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from typing import Mapping

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
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
from app.security.principals import AuthPrincipal
from app.security.session_auth import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    UNSAFE_HTTP_METHODS,
    clear_auth_session_cookies,
)
from app.services.auth_session_service import (
    AuthSessionPersistenceError,
    csrf_secret_matches,
    resolve_auth_session,
    touch_auth_session,
)
from app.services.auth_api_credential_service import (
    API_CREDENTIAL_PREFIX,
    AuthApiCredentialPersistenceError,
    InactiveAuthApiCredentialError,
    authenticate_auth_api_credential,
)


AUTH_ENABLED_ENV = "TOPO_AUTH_ENABLED"
TOKEN_REGISTRY_ENV = "TOPO_API_TOKEN_HASHES_JSON"


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


def _unauthorized(
    detail: str,
    *,
    clear_session: bool = False,
) -> JSONResponse:
    response = JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
    if clear_session:
        clear_auth_session_cookies(response)
    return response


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": detail})


def _authentication_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Authentication service is unavailable."},
    )


class ApiTokenAuthMiddleware(BaseHTTPMiddleware):
    """Dispatch inbound requests to their explicit authentication domain."""

    def __init__(
        self,
        app,
        *,
        configuration: AuthConfiguration,
        session_factory: Callable[[], Session],
    ) -> None:
        super().__init__(app)
        self.configuration = configuration
        self.session_factory = session_factory

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

        authorization = request.headers.get("Authorization")
        if authorization is not None:
            scheme, separator, token = authorization.partition(" ")
            if not separator or scheme.lower() != "bearer" or not token.strip():
                return _unauthorized("A valid Bearer API token is required.")

            raw_token = token.strip()
            named = None
            if raw_token.startswith(API_CREDENTIAL_PREFIX):
                try:
                    with self.session_factory() as database_session:
                        named = authenticate_auth_api_credential(
                            database_session,
                            raw_secret=raw_token,
                        )
                except InactiveAuthApiCredentialError:
                    return _unauthorized("The supplied API token is invalid.")
                except (SQLAlchemyError, AuthApiCredentialPersistenceError):
                    return _authentication_unavailable()
                principal = named.principal if named is not None else None
            else:
                principal = None

            if principal is None:
                principal = resolve_principal(
                    raw_token,
                    registry=self.configuration.token_registry,
                )
                if principal is None:
                    return _unauthorized("The supplied API token is invalid.")
                request.state.direct_static_bearer = True
            elif named is not None:
                request.state.auth_api_credential_id = (
                    named.record.credential_id
                )
                request.state.auth_api_credential_caller_type = (
                    named.record.caller_type
                )

            request.state.principal = principal
            request.state.source_credential_digest = token_digest(raw_token)
            request.state.authentication_mechanism = "bearer"
            return await call_next(request)

        raw_session_secret = request.cookies.get(SESSION_COOKIE_NAME)
        if not raw_session_secret:
            return _unauthorized(
                "A Bearer API token or browser session is required."
            )

        try:
            with self.session_factory() as database_session:
                resolved = resolve_auth_session(
                    database_session,
                    configuration=self.configuration,
                    raw_session_secret=raw_session_secret,
                )
                if resolved is None:
                    return _unauthorized(
                        "The browser session is invalid or expired.",
                        clear_session=True,
                    )

                if request.method.upper() in UNSAFE_HTTP_METHODS:
                    csrf_secret = request.headers.get(CSRF_HEADER_NAME, "")
                    if not csrf_secret or not csrf_secret_matches(
                        resolved.record,
                        csrf_secret,
                    ):
                        return _forbidden("CSRF validation failed.")

                touch_auth_session(
                    database_session,
                    configuration=self.configuration,
                    record=resolved.record,
                )
                request.state.principal = resolved.principal
                request.state.authentication_mechanism = "session"
                request.state.auth_session_id = resolved.record.session_id
                request.state.auth_session_absolute_expires_at = (
                    resolved.record.absolute_expires_at
                )
        except (SQLAlchemyError, AuthSessionPersistenceError):
            return _authentication_unavailable()

        return await call_next(request)
