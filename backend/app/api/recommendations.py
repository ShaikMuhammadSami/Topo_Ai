from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.recommendations import (
    RecommendationStatus,
    RecommendationStatusUpdate,
    RecommendationSummary,
    RemediationRecommendation,
)
from app.repositories.change_repository import (
    load_change,
)
from app.repositories.incident_repository import (
    load_incident_analysis,
)
from app.repositories.recommendation_repository import (
    list_recommendations,
    load_recommendation,
    save_recommendation,
    update_recommendation_status,
)
from app.repositories.signal_repository import (
    load_signal,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.recommendation_engine import (
    generate_recommendations,
)


router = APIRouter(
    prefix="/api/v1/recommendations",
    tags=["recommendations"],
)


@router.post(
    "/generate",
    response_model=list[
        RemediationRecommendation
    ],
    status_code=status.HTTP_201_CREATED,
)
def generate_analysis_recommendations(
    analysis_id: str,
    minimum_score: float = Query(
        default=0.50,
        ge=0.0,
        le=1.0,
    ),
    max_recommendations: int = Query(
        default=3,
        ge=1,
        le=20,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[
    RemediationRecommendation
]:
    analysis = load_incident_analysis(
        session=session,
        analysis_id=analysis_id,
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Incident analysis not found: "
                f"{analysis_id}"
            ),
        )

    signal = load_signal(
        session=session,
        signal_id=analysis.signal_id,
    )

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Signal referenced by the "
                "analysis was not found."
            ),
        )

    snapshot = load_snapshot(
        session=session,
        snapshot_id=(
            analysis.topology_snapshot_id
        ),
    )

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Topology snapshot referenced "
                "by the analysis was not found."
            ),
        )

    changes_by_id = {}

    for hypothesis in (
        analysis.hypotheses
    ):
        change = load_change(
            session=session,
            change_id=(
                hypothesis.change_id
            ),
        )

        if change is not None:
            changes_by_id[
                change.change_id
            ] = change

    recommendations = (
        generate_recommendations(
            analysis=analysis,
            signal=signal,
            snapshot=snapshot,
            changes_by_id=(
                changes_by_id
            ),
            minimum_score=(
                minimum_score
            ),
            max_recommendations=(
                max_recommendations
            ),
        )
    )

    for recommendation in (
        recommendations
    ):
        save_recommendation(
            session=session,
            recommendation=(
                recommendation
            ),
        )

    return recommendations


@router.get(
    "",
    response_model=list[
        RecommendationSummary
    ],
)
def get_recommendations(
    analysis_id: str | None = None,
    signal_id: str | None = None,
    status_filter: (
        RecommendationStatus | None
    ) = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[
    RecommendationSummary
]:
    return list_recommendations(
        session=session,
        analysis_id=analysis_id,
        signal_id=signal_id,
        status=(
            status_filter.value
            if status_filter
            else None
        ),
        limit=limit,
    )


@router.get(
    "/{recommendation_id}",
    response_model=(
        RemediationRecommendation
    ),
)
def get_recommendation(
    recommendation_id: str,
    session: Session = Depends(
        get_session
    ),
) -> RemediationRecommendation:
    recommendation = (
        load_recommendation(
            session=session,
            recommendation_id=(
                recommendation_id
            ),
        )
    )

    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Recommendation not found: "
                f"{recommendation_id}"
            ),
        )

    return recommendation


@router.patch(
    "/{recommendation_id}/status",
    response_model=(
        RemediationRecommendation
    ),
)
def change_recommendation_status(
    recommendation_id: str,
    request: (
        RecommendationStatusUpdate
    ),
    session: Session = Depends(
        get_session
    ),
) -> RemediationRecommendation:
    recommendation = (
        update_recommendation_status(
            session=session,
            recommendation_id=(
                recommendation_id
            ),
            status=request.status,
            note=request.note,
        )
    )

    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Recommendation not found: "
                f"{recommendation_id}"
            ),
        )

    return recommendation