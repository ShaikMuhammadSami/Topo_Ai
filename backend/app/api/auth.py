from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.auth import BrowserSessionView
from app.repositories.auth_session_repository import load_auth_session
from app.security.approval_authorization import authenticated_principal
from app.security.auth_config import AuthConfiguration
from app.security.session_auth import (
    browser_origin_is_allowed,
    clear_auth_session_cookies,
    set_auth_session_cookies,
)
from app.services.auth_session_service import (
    AuthSessionPersistenceError,
    create_auth_session,
    revoke_auth_session,
)


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _configuration(request: Request) -> AuthConfiguration:
    configuration = getattr(request.app.state, "auth_configuration", None)
    if not isinstance(configuration, AuthConfiguration):
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        )
    return configuration


def _auth_database_session(request: Request) -> Generator[Session, None, None]:
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        )
    with session_factory() as session:
        yield session


def _session_view(request: Request) -> BrowserSessionView:
    principal = authenticated_principal(request)
    if principal.authentication_type == "development":
        return BrowserSessionView(
            subject=principal.subject,
            display_name=principal.display_name,
            roles=list(principal.roles),
            authentication_type=principal.authentication_type,
            absolute_expires_at=None,
        )
    if principal.authentication_type != "session":
        raise HTTPException(
            status_code=401,
            detail="A browser session is required.",
        )
    return BrowserSessionView(
        subject=principal.subject,
        display_name=principal.display_name,
        roles=list(principal.roles),
        authentication_type=principal.authentication_type,
        absolute_expires_at=getattr(
            request.state,
            "auth_session_absolute_expires_at",
            None,
        ),
    )


@router.post(
    "/session",
    response_model=BrowserSessionView,
    status_code=status.HTTP_201_CREATED,
)
def create_browser_session(
    request: Request,
    response: Response,
    session: Session = Depends(_auth_database_session),
) -> BrowserSessionView:
    configuration = _configuration(request)
    principal = authenticated_principal(request)
    if principal.authentication_type != "api_token":
        raise HTTPException(
            status_code=403,
            detail="Browser session exchange requires human API-token authority.",
        )
    if not browser_origin_is_allowed(request, configuration):
        raise HTTPException(
            status_code=403,
            detail="Browser origin is not allowed.",
        )
    source_digest = getattr(
        request.state,
        "source_credential_digest",
        None,
    )
    if not isinstance(source_digest, str):
        raise HTTPException(
            status_code=401,
            detail="Authentication source is unavailable.",
        )

    try:
        issued = create_auth_session(
            session,
            configuration=configuration,
            source_principal=principal,
            source_credential_digest=source_digest,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Authentication source is unavailable.",
        ) from exc
    except AuthSessionPersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc

    set_auth_session_cookies(
        response,
        issued=issued,
        absolute_ttl_minutes=configuration.session_absolute_ttl_minutes,
    )
    return BrowserSessionView(
        subject=issued.record.subject,
        display_name=issued.record.display_name,
        roles=list(principal.roles),
        authentication_type="session",
        absolute_expires_at=issued.record.absolute_expires_at,
    )


@router.get("/session", response_model=BrowserSessionView)
def get_browser_session(request: Request) -> BrowserSessionView:
    return _session_view(request)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_browser_session(
    request: Request,
    session: Session = Depends(_auth_database_session),
) -> Response:
    principal = authenticated_principal(request)
    if principal.authentication_type != "session":
        raise HTTPException(
            status_code=401,
            detail="A browser session is required.",
        )
    session_id = getattr(request.state, "auth_session_id", None)
    if not isinstance(session_id, str):
        raise HTTPException(
            status_code=401,
            detail="A browser session is required.",
        )
    try:
        record = load_auth_session(session, session_id)
        if record is None or record.revoked_at is not None:
            raise HTTPException(
                status_code=401,
                detail="The browser session is invalid or expired.",
            )
        revoke_auth_session(session, record=record)
    except AuthSessionPersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_session_cookies(response)
    return response
