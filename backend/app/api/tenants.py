from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.tenant import (
    TenantContextView,
    TenantCreate,
    TenantMembershipCreate,
    TenantMembershipRecovery,
    TenantMembershipView,
    TenantView,
)
from app.repositories.tenant_repository import (
    list_active_tenants_for_principal,
    list_tenant_memberships,
)
from app.security.approval_authorization import authenticated_principal
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    HUMAN_AUTHENTICATION_TYPES,
    TENANT_ACCESS_DENIED,
    TenantActorKind,
    TenantContext,
    require_tenant_context,
    tenant_database_session,
)
from app.services.tenant_service import (
    ActiveTenantRequiredError,
    TenantMembershipNotFoundError,
    TenantPersistenceError,
    add_or_reactivate_tenant_membership,
    create_tenant_with_creator_membership,
    disable_tenant_membership,
    membership_view,
    tenant_view,
)


router = APIRouter(prefix="/api/v1", tags=["tenancy"])


def _human_principal(request: Request) -> AuthPrincipal:
    principal = authenticated_principal(request)
    if principal.authentication_type not in HUMAN_AUTHENTICATION_TYPES:
        raise HTTPException(
            status_code=403,
            detail="Human authority is required.",
        )
    return principal


def _human_admin_principal(request: Request) -> AuthPrincipal:
    principal = _human_principal(request)
    if "admin" not in principal.roles:
        raise HTTPException(
            status_code=403,
            detail="Administrative human authority is required.",
        )
    return principal


def _tenant_admin(
    request: Request,
    context: TenantContext,
) -> AuthPrincipal:
    principal = _human_admin_principal(request)
    if context.actor_kind is not TenantActorKind.HUMAN:
        raise HTTPException(
            status_code=403,
            detail="Administrative human authority is required.",
        )
    return principal


def _persistence_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Tenant service is unavailable.",
    )


@router.post(
    "/tenants",
    response_model=TenantView,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant(
    value: TenantCreate,
    request: Request,
    session: Session = Depends(tenant_database_session),
) -> TenantView:
    principal = _human_admin_principal(request)
    try:
        return create_tenant_with_creator_membership(
            session,
            display_name=value.display_name,
            creator_subject=principal.subject,
            creator_principal_id=principal.principal_id,
        )
    except TenantPersistenceError as exc:
        raise _persistence_unavailable(exc) from exc


@router.get("/tenants", response_model=list[TenantView])
def list_tenants(
    request: Request,
    session: Session = Depends(tenant_database_session),
) -> list[TenantView]:
    principal = _human_principal(request)
    try:
        return [
            tenant_view(tenant, membership)
            for tenant, membership in list_active_tenants_for_principal(
                session,
                principal_id=principal.principal_id or "",
            )
        ]
    except SQLAlchemyError as exc:
        raise _persistence_unavailable(exc) from exc


@router.get("/tenant-context", response_model=TenantContextView)
def get_tenant_context(
    context: TenantContext = Depends(require_tenant_context),
) -> TenantContextView:
    return context.view()


@router.get(
    "/tenant-memberships",
    response_model=list[TenantMembershipView],
)
def list_memberships(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    session: Session = Depends(tenant_database_session),
) -> list[TenantMembershipView]:
    _tenant_admin(request, context)
    try:
        return [
            membership_view(session, record)
            for record in list_tenant_memberships(
                session,
                tenant_id=context.tenant_id,
            )
        ]
    except SQLAlchemyError as exc:
        raise _persistence_unavailable(exc) from exc


@router.post(
    "/tenant-memberships",
    response_model=TenantMembershipView,
)
def add_membership(
    value: TenantMembershipCreate,
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    session: Session = Depends(tenant_database_session),
) -> TenantMembershipView:
    principal = _tenant_admin(request, context)
    try:
        return add_or_reactivate_tenant_membership(
            session,
            tenant_id=context.tenant_id,
            subject=value.subject,
            role=value.role,
            principal_id=value.principal_id,
            created_by_subject=principal.subject,
            created_by_principal_id=principal.principal_id,
        )
    except ActiveTenantRequiredError as exc:
        raise HTTPException(
            status_code=403,
            detail=TENANT_ACCESS_DENIED,
        ) from exc
    except TenantPersistenceError as exc:
        raise _persistence_unavailable(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid membership assignment.",
        ) from exc


@router.post(
    "/tenant-memberships/{membership_id}/disable",
    response_model=TenantMembershipView,
)
def disable_membership(
    membership_id: str,
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    session: Session = Depends(tenant_database_session),
) -> TenantMembershipView:
    _tenant_admin(request, context)
    try:
        return disable_tenant_membership(
            session,
            tenant_id=context.tenant_id,
            membership_id=membership_id,
        )
    except TenantMembershipNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Tenant membership not found.",
        ) from exc
    except TenantPersistenceError as exc:
        raise _persistence_unavailable(exc) from exc


@router.post(
    "/tenant-memberships/recover",
    response_model=TenantMembershipView,
)
def recover_membership(
    value: TenantMembershipRecovery,
    request: Request,
    session: Session = Depends(tenant_database_session),
) -> TenantMembershipView:
    principal = authenticated_principal(request)
    if (
        principal.authentication_type != "api_token"
        or "admin" not in principal.roles
        or getattr(request.state, "direct_static_bearer", False) is not True
    ):
        raise HTTPException(
            status_code=403,
            detail="Direct bootstrap recovery authority is required.",
        )
    try:
        return add_or_reactivate_tenant_membership(
            session,
            tenant_id=value.tenant_id,
            subject=value.subject,
            role=value.role,
            principal_id=value.principal_id,
            created_by_subject=principal.subject,
            created_by_principal_id=principal.principal_id,
        )
    except ActiveTenantRequiredError as exc:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found.",
        ) from exc
    except TenantPersistenceError as exc:
        raise _persistence_unavailable(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid membership assignment.",
        ) from exc
