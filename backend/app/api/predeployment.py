from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.predeployment import (
    PreDeploymentImpactRequest,
    PreDeploymentImpactResponse,
)
from app.services.predeployment_impact import (
    PreDeploymentNotFoundError,
    PreDeploymentValidationError,
    analyze_predeployment_impact,
)


router = APIRouter(
    prefix="/api/v1/predeployment",
    tags=["predeployment"],
)


@router.post(
    "/analyze",
    response_model=(
        PreDeploymentImpactResponse
    ),
)
def analyze_planned_change(
    request: PreDeploymentImpactRequest,
    session: Session = Depends(
        get_session
    ),
) -> PreDeploymentImpactResponse:
    try:
        return (
            analyze_predeployment_impact(
                session=session,
                request=request,
            )
        )

    except (
        PreDeploymentNotFoundError
    ) as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (
        PreDeploymentValidationError
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc