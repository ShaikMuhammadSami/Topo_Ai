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
from app.models.lifecycle_automation import (
    IncidentLifecycleStatusResponse,
)
from app.services.incident_briefing import (
    build_incident_briefing,
)
from app.services.lifecycle_status import (
    build_incident_lifecycle_status,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-intelligence"],
)


@router.get(
    "/{incident_id}/lifecycle-status",
    response_model=IncidentLifecycleStatusResponse,
)
def get_incident_lifecycle_status(
    incident_id: str,
    session: Session = Depends(get_session),
) -> IncidentLifecycleStatusResponse:
    try:
        return build_incident_lifecycle_status(
            session,
            incident_id=incident_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


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
