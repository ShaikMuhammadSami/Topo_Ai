from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.auth import (
    ApiCredentialCreate,
    ApiCredentialCreated,
    ApiCredentialCallerType,
    ApiCredentialTargetType,
    ApiCredentialView,
    BrowserSessionView,
)
from app.repositories.auth_api_credential_repository import (
    list_auth_api_credentials,
    load_auth_api_credential,
)
from app.repositories.auth_session_repository import load_auth_session
from app.repositories.tenant_repository import (
    load_service_api_tenant_binding,
    service_binding_tenant_ids,
    service_principal_tenant_ids,
)
from app.security.approval_authorization import authenticated_principal
from app.security.authorization_enforcement import (
    authorize_authentication_self_service,
    authorize_persisted_credential_target,
    authorize_service_operation,
    authorize_service_credential_scope,
    require_human_authenticator_caller,
)
from app.security.authorization_policy import Permission
from app.security.auth_config import AuthConfiguration
from app.security.principals import AuthPrincipal
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
from app.services.auth_api_credential_service import (
    AuthApiCredentialPersistenceError,
    ServiceTenantAccessError,
    create_auth_api_credential,
    credential_view,
    revoke_auth_api_credential,
)
from app.services.principal_identity import PrincipalIdentityError
from app.services.authority_assignments import AuthorityAssignmentError


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
            principal_id=principal.principal_id or "",
            principal_type=principal.principal_type or "human",
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
        principal_id=principal.principal_id or "",
        principal_type=principal.principal_type or "human",
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
    if principal.authentication_type not in {
        "api_token",
        "human_api_token",
    }:
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
        principal_id=issued.record.principal_id,
        principal_type="human",
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


@router.post(
    "/api-credentials",
    response_model=ApiCredentialCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_api_credential(
    value: ApiCredentialCreate,
    request: Request,
    session: Session = Depends(_auth_database_session),
) -> ApiCredentialCreated:
    principal = require_human_authenticator_caller(request)
    if value.caller_type is ApiCredentialCallerType.HUMAN_API:
        if value.principal_id not in {None, principal.principal_id}:
            raise HTTPException(status_code=403, detail="CREDENTIAL_TARGET_DENIED")
        if value.subject not in {None, principal.subject}:
            raise HTTPException(status_code=403, detail="CREDENTIAL_TARGET_DENIED")
        # Target identity and legacy authentication metadata are derived from
        # the authenticated caller, never accepted as an authority claim.
        value = value.model_copy(update={
            "principal_id": principal.principal_id,
            "subject": None,
            "roles": list(principal.roles),
        })
        authorize_service_operation(
            "authenticator.human.create",
            authorization_context=authorize_authentication_self_service(principal),
        )
    else:
        tenant_context, _ = authorize_service_credential_scope(
            request,
            session,
            principal=principal,
            required_permission=Permission.CREDENTIAL_ROTATE,
            operation="create",
            expected_tenant_id=value.tenant_id,
        )
        if value.principal_id is not None:
            target_tenants = service_principal_tenant_ids(
                session, value.principal_id
            )
            if target_tenants and target_tenants != {tenant_context.tenant_id}:
                raise HTTPException(
                    status_code=404,
                    detail="Principal identity is unavailable.",
                )
    try:
        return create_auth_api_credential(
            session,
            request=value,
            created_by_subject=principal.subject,
            created_by_principal_id=principal.principal_id,
        )
    except AuthApiCredentialPersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc
    except ServiceTenantAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail="TENANT_ACCESS_DENIED",
        ) from exc
    except AuthorityAssignmentError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Service principal permission assignment is unavailable or conflicts.",
        ) from exc
    except PrincipalIdentityError as exc:
        raise HTTPException(
            status_code=404,
            detail="Principal identity is unavailable.",
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc


@router.get("/api-credentials", response_model=list[ApiCredentialView])
def list_api_credentials(
    request: Request,
    target_type: ApiCredentialTargetType = ApiCredentialTargetType.HUMAN,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(_auth_database_session),
) -> list[ApiCredentialView]:
    principal = require_human_authenticator_caller(request)
    if not 1 <= limit <= 1000 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination.")
    try:
        if target_type is ApiCredentialTargetType.HUMAN:
            authorize_service_operation(
                "authenticator.human.list",
                authorization_context=authorize_authentication_self_service(principal),
            )
            records = list_auth_api_credentials(
                session,
                limit=limit,
                offset=offset,
                caller_type=ApiCredentialCallerType.HUMAN_API.value,
                principal_id=principal.principal_id,
            )
        else:
            tenant_context, _ = authorize_service_credential_scope(
                request,
                session,
                principal=principal,
                required_permission=Permission.CREDENTIAL_METADATA_READ,
                operation="list",
            )
            records = list_auth_api_credentials(
                session,
                limit=limit,
                offset=offset,
                caller_type=ApiCredentialCallerType.SERVICE_API.value,
                tenant_id=tenant_context.tenant_id,
            )
        tenant_ids = service_binding_tenant_ids(
            session,
            (record.credential_id for record in records),
        )
        return [
            credential_view(
                record,
                tenant_id=tenant_ids.get(record.credential_id),
            )
            for record in records
        ]
    except (SQLAlchemyError, AuthApiCredentialPersistenceError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc


@router.get(
    "/api-credentials/{credential_id}",
    response_model=ApiCredentialView,
)
def get_api_credential(
    credential_id: str,
    request: Request,
    session: Session = Depends(_auth_database_session),
) -> ApiCredentialView:
    try:
        record = load_auth_api_credential(session, credential_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="API credential not found.",
            )
        authorize_persisted_credential_target(
            request, session, record=record, operation="get"
        )
        binding = load_service_api_tenant_binding(session, credential_id)
        return credential_view(
            record,
            tenant_id=binding.tenant_id if binding is not None else None,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc


@router.post(
    "/api-credentials/{credential_id}/revoke",
    response_model=ApiCredentialView,
)
def revoke_api_credential(
    credential_id: str,
    request: Request,
    session: Session = Depends(_auth_database_session),
) -> ApiCredentialView:
    principal = require_human_authenticator_caller(request)
    try:
        record = load_auth_api_credential(session, credential_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="API credential not found.",
            )
        authorize_persisted_credential_target(
            request, session, record=record, operation="revoke"
        )
        revoke_auth_api_credential(
            session,
            record=record,
            revoked_by_subject=principal.subject,
        )
        binding = load_service_api_tenant_binding(session, credential_id)
        return credential_view(
            record,
            tenant_id=binding.tenant_id if binding is not None else None,
        )
    except AuthApiCredentialPersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable.",
        ) from exc
