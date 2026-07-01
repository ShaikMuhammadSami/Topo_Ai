from datetime import timedelta

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.incidents import (
    IncidentAnalysis,
    IncidentAnalysisSummary,
)
from app.repositories.change_repository import (
    find_changes_in_window,
)
from app.repositories.incident_repository import (
    list_incident_analyses,
    load_incident_analysis,
    save_incident_analysis,
)
from app.repositories.signal_repository import (
    load_signal,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.incident_analysis import (
    analyze_incident,
)


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incidents"],
)


@router.post(
    "/analyze",
    response_model=IncidentAnalysis,
    status_code=status.HTTP_201_CREATED,
)
def analyze_signal_incident(
    signal_id: str,
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
    ),
    grace_minutes: int = Query(
        default=2,
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
    session: Session = Depends(
        get_session
    ),
) -> IncidentAnalysis:
    signal = load_signal(
        session=session,
        signal_id=signal_id,
    )

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Signal not found: "
                f"{signal_id}"
            ),
        )

    if not signal.topology_snapshot_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "Signal does not contain a "
                "topology_snapshot_id."
            ),
        )

    snapshot = load_snapshot(
        session=session,
        snapshot_id=(
            signal.topology_snapshot_id
        ),
    )

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Topology snapshot referenced by "
                "the signal was not found: "
                f"{signal.topology_snapshot_id}"
            ),
        )

    start_at = (
        signal.first_observed_at
        - timedelta(
            minutes=lookback_minutes
        )
    )

    end_at = (
        signal.first_observed_at
        + timedelta(
            minutes=grace_minutes
        )
    )

    candidates = find_changes_in_window(
        session=session,
        cluster_name=(
            signal.cluster_name
        ),
        namespace=signal.namespace,
        start_at=start_at,
        end_at=end_at,
        limit=500,
    )

    analysis = analyze_incident(
        signal=signal,
        snapshot=snapshot,
        candidate_changes=candidates,
        lookback_minutes=(
            lookback_minutes
        ),
        grace_minutes=grace_minutes,
        max_graph_hops=(
            max_graph_hops
        ),
        max_hypotheses=(
            max_hypotheses
        ),
    )

    save_incident_analysis(
        session=session,
        analysis=analysis,
    )

    return analysis


@router.get(
    "",
    response_model=list[
        IncidentAnalysisSummary
    ],
)
def get_incident_analyses(
    signal_id: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[
    IncidentAnalysisSummary
]:
    return list_incident_analyses(
        session=session,
        signal_id=signal_id,
        limit=limit,
    )


@router.get(
    "/{analysis_id}",
    response_model=IncidentAnalysis,
)
def get_incident_analysis(
    analysis_id: str,
    session: Session = Depends(
        get_session
    ),
) -> IncidentAnalysis:
    analysis = load_incident_analysis(
        session=session,
        analysis_id=analysis_id,
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Incident analysis not found: "
                f"{analysis_id}"
            ),
        )

    return analysis