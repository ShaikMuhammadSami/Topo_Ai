from __future__ import annotations

from fastapi import HTTPException, Request

from app.security.api_tokens import (
    AuthPrincipal,
)


APPROVAL_CONTROL_ROLES = frozenset(
    {
        "admin",
        "operator",
    }
)


def authenticated_principal(
    request: Request,
) -> AuthPrincipal:
    principal = getattr(
        request.state,
        "principal",
        None,
    )

    if not isinstance(
        principal,
        AuthPrincipal,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication identity is "
                "unavailable."
            ),
        )

    return principal


def approval_control_principal(
    request: Request,
) -> AuthPrincipal:
    principal = authenticated_principal(
        request
    )

    if (
        not principal.subject.strip()
        or principal.subject.strip().lower()
        == "unknown"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "A stable authenticated subject is "
                "required for approval control-plane "
                "changes."
            ),
        )

    if not (
        set(principal.roles)
        & APPROVAL_CONTROL_ROLES
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "The admin or operator role is "
                "required for approval control-plane "
                "changes."
            ),
        )

    return principal
