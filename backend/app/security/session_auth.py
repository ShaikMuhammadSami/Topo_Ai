from __future__ import annotations

import hmac

from fastapi import Request
from starlette.responses import Response

from app.security.auth_config import AuthConfiguration
from app.services.auth_session_service import IssuedAuthSession


SESSION_COOKIE_NAME = "topo_session"
CSRF_COOKIE_NAME = "topo_csrf"
CSRF_HEADER_NAME = "X-Topo-CSRF"
UNSAFE_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def browser_origin_is_allowed(
    request: Request,
    configuration: AuthConfiguration,
) -> bool:
    origin = request.headers.get("Origin")
    if origin is None:
        # Non-browser bearer clients such as the CLI do not send Origin.
        return True
    return any(
        hmac.compare_digest(origin, allowed_origin)
        for allowed_origin in configuration.browser_allowed_origins
    )


def set_auth_session_cookies(
    response: Response,
    *,
    issued: IssuedAuthSession,
    absolute_ttl_minutes: int,
) -> None:
    max_age = absolute_ttl_minutes * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issued.session_secret,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=issued.csrf_secret,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )


def clear_auth_session_cookies(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )
