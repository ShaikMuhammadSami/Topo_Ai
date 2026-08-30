from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.incident_memory import (
    IncidentHistoricalIntelligence,
)
from app.services.incident_similarity import (
    build_historical_incident_intelligence,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-history"],
)


@router.get(
    "/{incident_id}/historical-intelligence",
    response_model=(IncidentHistoricalIntelligence),
)
def get_historical_incident_intelligence(
    incident_id: str,
    limit: int = Query(
        default=5,
        ge=1,
        le=20,
    ),
    min_similarity: float = Query(
        default=0.25,
        ge=0.0,
        le=1.0,
    ),
    include_ai: bool = Query(
        default=False,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> IncidentHistoricalIntelligence:
    try:
        return build_historical_incident_intelligence(
            session=session,
            incident_id=incident_id,
            limit=limit,
            min_similarity=min_similarity,
            include_ai=include_ai,
            tenant_id=tenant_context.tenant_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
