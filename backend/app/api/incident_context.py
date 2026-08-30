from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.incident_context import (
    IncidentOperationalContext,
)
from app.services.incident_context import (
    build_incident_operational_context,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-context"],
)


@router.get(
    "/{incident_id}/operational-context",
    response_model=(IncidentOperationalContext),
)
def get_incident_operational_context(
    incident_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentOperationalContext:
    try:
        return build_incident_operational_context(
            session=session,
            incident_id=incident_id,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
