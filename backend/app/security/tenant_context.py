from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.tenant import TenantContextView, is_valid_tenant_id
from app.repositories.tenant_repository import (
    load_active_human_tenant_context,
    load_active_tenant,
    load_service_api_tenant_binding,
)
from app.security.approval_authorization import authenticated_principal
from app.security.principals import AuthPrincipal

TENANT_HEADER_NAME = "X-Topo-Tenant-ID"
TENANT_CONTEXT_REQUIRED = "TENANT_CONTEXT_REQUIRED"
TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"

HUMAN_AUTHENTICATION_TYPES = frozenset(
    {
        "api_token",
        "human_api_token",
        "session",
        "development",
    }
)


class TenantActorKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class TenantSelectionSource(StrEnum):
    HUMAN_HEADER = "human_header"
    SERVICE_BINDING = "service_binding"


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    authenticated_subject: str
    authentication_type: str
    actor_kind: TenantActorKind
    selection_source: TenantSelectionSource
    principal_id: str | None = None
    membership_id: str | None = None
    credential_id: str | None = None

    def view(self) -> TenantContextView:
        return TenantContextView(
            tenant_id=self.tenant_id,
            principal_id=self.principal_id or "",
            authenticated_subject=self.authenticated_subject,
            authentication_type=self.authentication_type,
            actor_kind=self.actor_kind.value,
            selection_source=self.selection_source.value,
            membership_id=self.membership_id,
            credential_id=self.credential_id,
        )


def tenant_database_session(request: Request) -> Generator[Session, None, None]:
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant service is unavailable.",
        )
    with session_factory() as session:
        yield session


def _required() -> HTTPException:
    return HTTPException(status_code=400, detail=TENANT_CONTEXT_REQUIRED)


def _denied() -> HTTPException:
    return HTTPException(status_code=403, detail=TENANT_ACCESS_DENIED)


def _human_tenant_selector(request: Request) -> str:
    value = request.headers.get(TENANT_HEADER_NAME)
    if (
        value is None
        or not value
        or value != value.strip()
        or len(value) > 64
        or not is_valid_tenant_id(value)
    ):
        raise _required()
    return value


def resolve_tenant_context(
    session: Session,
    *,
    principal: AuthPrincipal,
    selected_tenant_id: str | None,
    credential_id: str | None,
) -> TenantContext:
    if principal.principal_id is None or principal.principal_type is None:
        raise _denied()
    if principal.authentication_type == "service_api_token":
        if not credential_id:
            raise _denied()
        binding = load_service_api_tenant_binding(session, credential_id)
        if binding is None:
            raise _denied()
        if (
            selected_tenant_id is not None
            and selected_tenant_id != binding.tenant_id
        ):
            raise _denied()
        if load_active_tenant(session, binding.tenant_id) is None:
            raise _denied()
        return TenantContext(
            tenant_id=binding.tenant_id,
            principal_id=principal.principal_id,
            authenticated_subject=principal.subject,
            authentication_type=principal.authentication_type,
            actor_kind=TenantActorKind.SERVICE,
            selection_source=TenantSelectionSource.SERVICE_BINDING,
            credential_id=credential_id,
        )

    if principal.authentication_type not in HUMAN_AUTHENTICATION_TYPES:
        raise _denied()
    if selected_tenant_id is None:
        raise _required()
    resolved = load_active_human_tenant_context(
        session,
        tenant_id=selected_tenant_id,
        principal_id=principal.principal_id,
    )
    if resolved is None:
        raise _denied()
    _, membership = resolved
    return TenantContext(
        tenant_id=selected_tenant_id,
        principal_id=principal.principal_id,
        authenticated_subject=principal.subject,
        authentication_type=principal.authentication_type,
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id=membership.membership_id,
    )


def require_tenant_context(
    request: Request,
    session: Session = Depends(get_session),
) -> TenantContext:
    principal = authenticated_principal(request)
    selected_tenant_id: str | None
    if principal.authentication_type == "service_api_token":
        selected_tenant_id = request.headers.get(TENANT_HEADER_NAME)
    else:
        selected_tenant_id = _human_tenant_selector(request)
    try:
        return resolve_tenant_context(
            session,
            principal=principal,
            selected_tenant_id=selected_tenant_id,
            credential_id=getattr(
                request.state,
                "auth_api_credential_id",
                None,
            ),
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Tenant service is unavailable.",
        ) from exc
