from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.execution_readiness import (
    IncidentExecutionReadiness,
)
from app.services.execution_readiness import (
    build_incident_execution_readiness,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["execution-readiness"],
)


@router.get(
    "/{incident_id}/execution-readiness",
    response_model=IncidentExecutionReadiness,
)
def get_incident_execution_readiness(
    incident_id: str,
    include_ai: bool = Query(default=False),
    history_limit: int = Query(
        default=5,
        ge=1,
        le=20,
    ),
    min_similarity: float = Query(
        default=0.5,
        ge=0.0,
        le=1.0,
    ),
    session: Session = Depends(
        get_session
    ),
) -> IncidentExecutionReadiness:
    try:
        return build_incident_execution_readiness(
            session=session,
            incident_id=incident_id,
            history_limit=history_limit,
            min_similarity=min_similarity,
            include_ai=include_ai,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
