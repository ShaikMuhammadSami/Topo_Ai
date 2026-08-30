from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.incident_copilot import (
    CopilotQuestionRequest,
    CopilotQuestionResponse,
    CopilotSessionCreateRequest,
    CopilotSessionDetail,
    CopilotSessionSummary,
)
from app.repositories.copilot_repository import (
    list_incident_copilot_sessions,
    load_copilot_session_detail,
)
from app.services.incident_copilot import (
    CopilotGenerationError,
    CopilotSessionError,
    answer_copilot_question,
    create_incident_copilot_session,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-copilot"],
)


@router.post(
    "/{incident_id}/copilot/sessions",
    response_model=CopilotSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    incident_id: str,
    request: CopilotSessionCreateRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> CopilotSessionDetail:
    try:
        return create_incident_copilot_session(
            session=session,
            incident_id=incident_id,
            request=request,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}/copilot/sessions",
    response_model=list[CopilotSessionSummary],
)
def get_sessions(
    incident_id: str,
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
) -> list[CopilotSessionSummary]:
    return list_incident_copilot_sessions(
        session=session,
        incident_id=incident_id,
        limit=limit,
        offset=offset,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/{incident_id}/copilot/sessions/{session_id}",
    response_model=CopilotSessionDetail,
)
def get_session_detail(
    incident_id: str,
    session_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> CopilotSessionDetail:
    result = load_copilot_session_detail(
        session=session,
        session_id=session_id,
        tenant_id=tenant_context.tenant_id,
    )

    if (
        result is None
        or result.incident_id
        != incident_id
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Copilot session not found."
            ),
        )

    return result


@router.post(
    "/{incident_id}/copilot/sessions/{session_id}/messages",
    response_model=(CopilotQuestionResponse),
)
def post_message(
    incident_id: str,
    session_id: str,
    request: CopilotQuestionRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> CopilotQuestionResponse:
    try:
        return answer_copilot_question(
            session=session,
            incident_id=incident_id,
            session_id=session_id,
            question=request.question,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except CopilotSessionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except CopilotGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
