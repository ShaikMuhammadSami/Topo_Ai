from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.incident_outcome import (
    IncidentOutcome,
    IncidentOutcomeUpdate,
)
from app.services.incident_outcome import (
    get_incident_outcome,
    record_incident_outcome,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-outcomes"],
)


@router.get(
    "/{incident_id}/outcome",
    response_model=IncidentOutcome,
)
def get_outcome(
    incident_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentOutcome:
    try:
        return get_incident_outcome(
            session,
            incident_id=incident_id,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/{incident_id}/outcome",
    response_model=IncidentOutcome,
)
def post_outcome(
    incident_id: str,
    request: IncidentOutcomeUpdate,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentOutcome:
    try:
        return record_incident_outcome(
            session,
            incident_id=incident_id,
            update=request,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
