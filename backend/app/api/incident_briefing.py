from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.incident_briefing import (
    IncidentBriefing,
)
from app.services.incident_briefing import (
    build_incident_briefing,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-intelligence"],
)


@router.get(
    "/{incident_id}/briefing",
    response_model=IncidentBriefing,
)
def get_incident_briefing(
    incident_id: str,
    include_ai: bool = Query(default=False),
    session: Session = Depends(
        get_session
    ),
) -> IncidentBriefing:
    try:
        return build_incident_briefing(
            session=session,
            incident_id=incident_id,
            include_ai=include_ai,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
