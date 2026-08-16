from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.execution_transaction import (
    ExecutionIntentCancelRequest,
    ExecutionIntentCreateRequest,
    ExecutionIntentDetail,
    ExecutionIntentStatus,
    ExecutionIntentView,
)
from app.security.approval_authorization import (
    approval_control_principal,
    authenticated_principal,
)
from app.services.execution_transaction import (
    ExecutionIntentConflictError,
    ExecutionIntentNotFoundError,
    cancel_execution_intent,
    create_execution_intent,
    get_execution_intent,
    list_execution_intents,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["execution-intents"],
)


def _raise_controlled_error(
    exc: Exception,
) -> None:
    status_code = (
        404
        if isinstance(
            exc,
            ExecutionIntentNotFoundError,
        )
        else 409
    )
    raise HTTPException(
        status_code=status_code,
        detail=str(exc),
    ) from exc


@router.post(
    "/{incident_id}/execution-intents",
    response_model=ExecutionIntentDetail,
)
def create_intent(
    incident_id: str,
    request_body: ExecutionIntentCreateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ExecutionIntentDetail:
    principal = approval_control_principal(
        request
    )

    try:
        return create_execution_intent(
            session,
            incident_id=incident_id,
            approval_id=request_body.approval_id,
            creator=principal,
        )
    except (
        ExecutionIntentNotFoundError,
        ExecutionIntentConflictError,
    ) as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/{incident_id}/execution-intents",
    response_model=list[ExecutionIntentView],
)
def list_intents(
    incident_id: str,
    request: Request,
    status: ExecutionIntentStatus | None = None,
    approval_id: str | None = Query(
        default=None,
        max_length=255,
    ),
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
) -> list[ExecutionIntentView]:
    authenticated_principal(request)
    return list_execution_intents(
        session,
        incident_id=incident_id,
        status=status,
        approval_id=approval_id,
        action_id=action_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{incident_id}/execution-intents/{execution_id}",
    response_model=ExecutionIntentDetail,
)
def get_intent(
    incident_id: str,
    execution_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ExecutionIntentDetail:
    authenticated_principal(request)

    try:
        return get_execution_intent(
            session,
            incident_id=incident_id,
            execution_id=execution_id,
        )
    except ExecutionIntentNotFoundError as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")


@router.post(
    (
        "/{incident_id}/execution-intents/"
        "{execution_id}/cancel"
    ),
    response_model=ExecutionIntentDetail,
)
def cancel_intent(
    incident_id: str,
    execution_id: str,
    request_body: ExecutionIntentCancelRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ExecutionIntentDetail:
    principal = approval_control_principal(
        request
    )

    try:
        return cancel_execution_intent(
            session,
            incident_id=incident_id,
            execution_id=execution_id,
            actor=principal,
            reason=request_body.reason,
        )
    except (
        ExecutionIntentNotFoundError,
        ExecutionIntentConflictError,
    ) as exc:
        _raise_controlled_error(exc)
        raise AssertionError("unreachable")
