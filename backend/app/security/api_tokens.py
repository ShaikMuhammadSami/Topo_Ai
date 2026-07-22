from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response


AUTH_ENABLED_ENV = "TOPO_AUTH_ENABLED"

TOKEN_REGISTRY_ENV = (
    "TOPO_API_TOKEN_HASHES_JSON"
)


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    display_name: str
    roles: tuple[str, ...]
    authentication_type: str


def authentication_enabled() -> bool:
    value = os.getenv(
        AUTH_ENABLED_ENV,
        "false",
    ).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


def _load_registry() -> dict[
    str,
    dict[str, Any],
]:
    raw_value = os.getenv(
        TOKEN_REGISTRY_ENV,
        "{}",
    )

    try:
        value = json.loads(raw_value)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{TOKEN_REGISTRY_ENV} must "
            "contain valid JSON."
        ) from exc

    if not isinstance(value, dict):
        raise RuntimeError(
            f"{TOKEN_REGISTRY_ENV} must "
            "contain a JSON object."
        )

    registry: dict[
        str,
        dict[str, Any],
    ] = {}

    for token_hash, metadata in (
        value.items()
    ):
        if not isinstance(
            metadata,
            dict,
        ):
            continue

        registry[
            str(token_hash).lower()
        ] = metadata

    return registry


def token_digest(
    token: str,
) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def resolve_principal(
    token: str,
) -> AuthPrincipal | None:
    candidate_hash = token_digest(
        token
    )

    registry = _load_registry()

    matched_metadata: (
        dict[str, Any] | None
    ) = None

    for known_hash, metadata in (
        registry.items()
    ):
        if hmac.compare_digest(
            candidate_hash,
            known_hash,
        ):
            matched_metadata = metadata
            break

    if matched_metadata is None:
        return None

    subject = str(
        matched_metadata.get(
            "subject",
            "unknown",
        )
    )

    display_name = str(
        matched_metadata.get(
            "display_name",
            subject,
        )
    )

    raw_roles = matched_metadata.get(
        "roles",
        [],
    )

    roles = (
        tuple(
            str(role)
            for role in raw_roles
        )
        if isinstance(raw_roles, list)
        else ()
    )

    return AuthPrincipal(
        subject=subject,
        display_name=display_name,
        roles=roles,
        authentication_type="api_token",
    )


def development_principal(
) -> AuthPrincipal:
    return AuthPrincipal(
        subject="local-development",
        display_name=(
            "Local Development User"
        ),
        roles=(
            "admin",
            "operator",
        ),
        authentication_type=(
            "development"
        ),
    )


def _unauthorized(
    detail: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "detail": detail,
        },
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


class ApiTokenAuthMiddleware(
    BaseHTTPMiddleware
):
    """
    Protect all /api routes when authentication
    is enabled.

    Health, documentation and browser preflight
    requests remain public.
    """

    PUBLIC_EXACT_PATHS = {
        "/",
        "/health",
        "/openapi.json",
    }

    PUBLIC_PREFIXES = (
        "/docs",
        "/redoc",
    )

    AGENT_EXACT_PATHS = {
       "/api/v1/agents/enroll",
    }

    AGENT_PREFIXES = (
       "/api/v1/agent/",
    )

    async def dispatch(
        self,
        request: Request,
        call_next:
            RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        is_public = (
            request.method == "OPTIONS"
            or path
            in self.PUBLIC_EXACT_PATHS
            or path 
            in self.AGENT_EXACT_PATHS
            or any(
                path.startswith(prefix)
                for prefix
                in self.PUBLIC_PREFIXES
            )
            or any(
                path.startswith(prefix)
                for prefix
                in self.AGENT_PREFIXES
            )            
            or not path.startswith(
                "/api/"
            )
        )

        if is_public:
            return await call_next(
                request
            )

        if not authentication_enabled():
            request.state.principal = (
                development_principal()
            )

            return await call_next(
                request
            )

        authorization = (
            request.headers.get(
                "Authorization",
                "",
            )
        )

        scheme, separator, token = (
            authorization.partition(" ")
        )

        if (
            not separator
            or scheme.lower()
            != "bearer"
            or not token.strip()
        ):
            return _unauthorized(
                "A Bearer API token is "
                "required."
            )

        principal = resolve_principal(
            token.strip()
        )

        if principal is None:
            return _unauthorized(
                "The supplied API token "
                "is invalid."
            )

        request.state.principal = (
            principal
        )

        return await call_next(
            request
        )