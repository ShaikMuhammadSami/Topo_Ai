from __future__ import annotations
from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.action_approval import (
    ActionApprovalDecisionRequest,
    ActionApprovalDetail,
    ActionApprovalRequest,
    ActionApprovalRevocationRequest,
    ActionApprovalStatus,
    ActionApprovalView,
)
from app.security.approval_authorization import (
    approval_control_principal,
    authenticated_principal,
)
from app.services.action_approval import (
    ActionApprovalAuthorizationError,
    ActionApprovalConflictError,
    ActionApprovalNotFoundError,
    create_action_approval,
    decide_action_approval,
    get_action_approval,
    list_action_approvals,
    revoke_action_approval,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["action-approvals"],
)


def _raise_controlled_error(
    exc: Exception,
) -> None:
    if isinstance(
        exc,
        ActionApprovalNotFoundError,
    ):
        status_code = 404
    elif isinstance(
        exc,
        ActionApprovalAuthorizationError,
    ):
        status_code = 403
    else:
        status_code = 409

    raise HTTPException(
        status_code=status_code,
        detail=str(exc),
    ) from exc


@router.post(
    "/{incident_id}/approvals",
    response_model=ActionApprovalDetail,
)
def create_approval_request(
    incident_id: str,
    request_body: ActionApprovalRequest,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ActionApprovalDetail:
    principal = approval_control_principal(
        request
    )

    try:
        return create_action_approval(
            session,
            incident_id=incident_id,
            action_id=request_body.action_id,
            requester=principal,
            reason=request_body.reason,
            tenant_id=tenant_context.tenant_id,
        )
    except (
        ActionApprovalConflictError,
        ActionApprovalNotFoundError,
        ActionApprovalAuthorizationError,
    ) as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}/approvals",
    response_model=list[ActionApprovalView],
)
def list_approval_history(
    incident_id: str,
    request: Request,
    status: ActionApprovalStatus | None = None,
    action_id: str | None = Query(
        default=None,
        max_length=1000,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[ActionApprovalView]:
    authenticated_principal(request)

    return list_action_approvals(
        session,
        incident_id=incident_id,
        status=status,
        action_id=action_id,
        limit=limit,
        offset=offset,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/{incident_id}/approvals/{approval_id}",
    response_model=ActionApprovalDetail,
)
def get_approval_request(
    incident_id: str,
    approval_id: str,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ActionApprovalDetail:
    authenticated_principal(request)

    try:
        return get_action_approval(
            session,
            incident_id=incident_id,
            approval_id=approval_id,
            tenant_id=tenant_context.tenant_id,
        )
    except ActionApprovalNotFoundError as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{incident_id}/approvals/{approval_id}/approve",
    response_model=ActionApprovalDetail,
)
def approve_request(
    incident_id: str,
    approval_id: str,
    request_body: ActionApprovalDecisionRequest,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ActionApprovalDetail:
    principal = approval_control_principal(
        request
    )

    try:
        return decide_action_approval(
            session,
            incident_id=incident_id,
            approval_id=approval_id,
            decision=(ActionApprovalStatus.APPROVED),
            decider=principal,
            reason=request_body.reason,
            tenant_id=tenant_context.tenant_id,
        )
    except (
        ActionApprovalConflictError,
        ActionApprovalNotFoundError,
        ActionApprovalAuthorizationError,
    ) as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{incident_id}/approvals/{approval_id}/reject",
    response_model=ActionApprovalDetail,
)
def reject_request(
    incident_id: str,
    approval_id: str,
    request_body: ActionApprovalDecisionRequest,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ActionApprovalDetail:
    principal = approval_control_principal(
        request
    )

    try:
        return decide_action_approval(
            session,
            incident_id=incident_id,
            approval_id=approval_id,
            decision=(ActionApprovalStatus.REJECTED),
            decider=principal,
            reason=request_body.reason,
            tenant_id=tenant_context.tenant_id,
        )
    except (
        ActionApprovalConflictError,
        ActionApprovalNotFoundError,
        ActionApprovalAuthorizationError,
    ) as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{incident_id}/approvals/{approval_id}/revoke",
    response_model=ActionApprovalDetail,
)
def revoke_request(
    incident_id: str,
    approval_id: str,
    request_body: ActionApprovalRevocationRequest,
    request: Request,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> ActionApprovalDetail:
    principal = approval_control_principal(
        request
    )

    try:
        return revoke_action_approval(
            session,
            incident_id=incident_id,
            approval_id=approval_id,
            revoker=principal,
            reason=request_body.reason,
            tenant_id=tenant_context.tenant_id,
        )
    except (
        ActionApprovalConflictError,
        ActionApprovalNotFoundError,
        ActionApprovalAuthorizationError,
    ) as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")
