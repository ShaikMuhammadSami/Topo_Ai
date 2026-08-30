from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.incident_explanation import (
    IncidentExplanationGenerateRequest,
    IncidentExplanationResponse,
)
from app.repositories.incident_explanation_repository import (
    list_incident_explanations,
    load_latest_incident_explanation,
)
from app.services.incident_explanation import (
    ExplanationGenerationError,
    generate_incident_explanation,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-explanations"],
)


@router.post(
    "/{incident_id}/explanations",
    response_model=(IncidentExplanationResponse),
)
def create_explanation(
    incident_id: str,
    request: IncidentExplanationGenerateRequest,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentExplanationResponse:
    try:
        return generate_incident_explanation(
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

    except ExplanationGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}/explanations/latest",
    response_model=(IncidentExplanationResponse | None),
)
def get_latest_explanation(
    incident_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentExplanationResponse | None:
    return load_latest_incident_explanation(
        session=session,
        incident_id=incident_id,
        tenant_id=tenant_context.tenant_id,
    )


@router.get(
    "/{incident_id}/explanations",
    response_model=list[IncidentExplanationResponse],
)
def get_explanation_history(
    incident_id: str,
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[IncidentExplanationResponse]:
    return list_incident_explanations(
        session=session,
        incident_id=incident_id,
        limit=limit,
        tenant_id=tenant_context.tenant_id,
    )
