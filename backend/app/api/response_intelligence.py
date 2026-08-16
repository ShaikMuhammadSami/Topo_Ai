from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.response_intelligence import (
    IncidentResponseIntelligence,
)
from app.services.response_intelligence import (
    build_incident_response_intelligence,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["response-intelligence"],
)


@router.get(
    "/{incident_id}/response-intelligence",
    response_model=IncidentResponseIntelligence,
)
def get_incident_response_intelligence(
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
) -> IncidentResponseIntelligence:
    try:
        return build_incident_response_intelligence(
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
