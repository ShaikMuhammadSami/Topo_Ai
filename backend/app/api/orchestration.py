from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.models.orchestration import (
    IncidentOrchestrationResult,
)
from app.services.incident_orchestrator import (
    OrchestrationNotFoundError,
    OrchestrationValidationError,
    orchestrate_signal,
)


router = APIRouter(
    prefix="/api/v1/orchestration",
    tags=["orchestration"],
)


@router.post(
    "/signals/{signal_id}/run",
    response_model=(
        IncidentOrchestrationResult
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def run_signal_orchestration(
    signal_id: str,
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
    ),
    grace_minutes: int = Query(
        default=15,
        ge=0,
        le=30,
    ),
    max_graph_hops: int = Query(
        default=6,
        ge=1,
        le=20,
    ),
    max_hypotheses: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
    minimum_recommendation_score: (
        float
    ) = Query(
        default=0.50,
        ge=0.0,
        le=1.0,
    ),
    max_recommendations: int = Query(
        default=3,
        ge=1,
        le=20,
    ),
    require_failure_severity: (
        bool
    ) = Query(
        default=True,
    ),
    session: Session = Depends(
        get_session
    ),
) -> IncidentOrchestrationResult:
    try:
        return orchestrate_signal(
            session=session,
            signal_id=signal_id,
            lookback_minutes=(
                lookback_minutes
            ),
            grace_minutes=(
                grace_minutes
            ),
            max_graph_hops=(
                max_graph_hops
            ),
            max_hypotheses=(
                max_hypotheses
            ),
            minimum_recommendation_score=(
                minimum_recommendation_score
            ),
            max_recommendations=(
                max_recommendations
            ),
            require_failure_severity=(
                require_failure_severity
            ),
        )

    except (
        OrchestrationNotFoundError
    ) as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (
        OrchestrationValidationError
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc