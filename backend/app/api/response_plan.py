from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.response_plan import (
    IncidentResponsePlan,
)
from app.services.response_plan import (
    build_incident_response_plan,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["response-intelligence"],
)


@router.get(
    "/{incident_id}/response-plan",
    response_model=IncidentResponsePlan,
)
def get_incident_response_plan(
    incident_id: str,
    session: Session = Depends(
        get_session
    ),
) -> IncidentResponsePlan:
    try:
        return build_incident_response_plan(
            session=session,
            incident_id=incident_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
