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
from app.models.recommendations import (
    RecommendationStatus,
)
from app.models.recovery import (
    RecoveryStatus,
    RecoveryVerification,
    RecoveryVerificationSummary,
)
from app.repositories.incident_repository import (
    load_incident_analysis,
)
from app.repositories.recommendation_repository import (
    load_recommendation,
)
from app.repositories.recovery_repository import (
    list_recovery_verifications,
    load_recovery_verification,
    save_recovery_verification,
)
from app.repositories.signal_repository import (
    find_signals_after,
    load_signal,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.recovery_verification import (
    verify_recovery,
)
from app.models.webhooks import (
    WebhookEventType,
)
from app.services.webhook_delivery import (
    build_webhook_event,
    publish_event_safely,
)

router = APIRouter(
    prefix="/api/v1/recovery",
    tags=["recovery"],
)


@router.post(
    "/verify",
    response_model=RecoveryVerification,
    status_code=status.HTTP_201_CREATED,
)
def verify_applied_recommendation(
    recommendation_id: str,
    post_snapshot_id: str,
    session: Session = Depends(
        get_session
    ),
) -> RecoveryVerification:
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

    if (
        recommendation.status
        != RecommendationStatus.APPLIED
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Recommendation must be marked "
                "as applied before recovery can "
                "be verified."
            ),
        )

    if recommendation.applied_at is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Applied recommendation does not "
                "contain an applied_at timestamp."
            ),
        )

    analysis = load_incident_analysis(
        session=session,
        analysis_id=(
            recommendation.analysis_id
        ),
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Incident analysis referenced by "
                "the recommendation was not found."
            ),
        )

    original_signal = load_signal(
        session=session,
        signal_id=(
            recommendation.signal_id
        ),
    )

    if original_signal is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Original signal referenced by "
                "the recommendation was not found."
            ),
        )

    pre_snapshot = load_snapshot(
        session=session,
        snapshot_id=(
            analysis.topology_snapshot_id
        ),
    )

    if pre_snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Pre-remediation topology "
                "snapshot was not found."
            ),
        )

    post_snapshot = load_snapshot(
        session=session,
        snapshot_id=post_snapshot_id,
    )

    if post_snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Post-remediation topology "
                f"snapshot was not found: "
                f"{post_snapshot_id}"
            ),
        )

    post_cluster = (
        post_snapshot.scope.get(
            "cluster"
        )
    )

    if (
        post_cluster
        != recommendation.cluster_name
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Post-remediation snapshot "
                "belongs to a different cluster."
            ),
        )

    snapshot_namespace = (
        post_snapshot.scope.get(
            "namespace"
        )
    )

    if (
        recommendation.namespace
        and snapshot_namespace
        != recommendation.namespace
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Post-remediation snapshot uses "
                "a different namespace scope."
            ),
        )

    signals_after_action = (
        find_signals_after(
            session=session,
            cluster_name=(
                recommendation
                .cluster_name
            ),
            namespace=(
                recommendation.namespace
            ),
            start_at=(
                recommendation.applied_at
                - timedelta(seconds=1)
            ),
            limit=500,
        )
    )

    try:
        verification = verify_recovery(
            recommendation=(
                recommendation
            ),
            analysis=analysis,
            original_signal=(
                original_signal
            ),
            pre_snapshot=(
                pre_snapshot
            ),
            post_snapshot=(
                post_snapshot
            ),
            signals_after_action=(
                signals_after_action
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    save_recovery_verification(
        session=session,
        verification=verification,
    )
    event_type_by_status = {
     "verified": (
         WebhookEventType
         .RECOVERY_VERIFIED
        ),
     "failed": (
         WebhookEventType
         .RECOVERY_FAILED
        ),
     "inconclusive": (
         WebhookEventType
         .RECOVERY_INCONCLUSIVE
       ),
    }

    recovery_event = (
     build_webhook_event(
         event_type=(
             event_type_by_status[
                 verification.status.value
                ]
           ),
         resource_type=(
             "recovery_verification"
           ),
         resource_id=(
             verification
             .verification_id
            ),
         summary=(
             verification.summary
           ),
         severity=(
             "info"
             if verification
             .status.value
             == "verified"
             else "error"
            ),
         dedupe_key=(
              verification
             .verification_id
            ),
         payload={
             "verification_id": (
                 verification
                 .verification_id
                ),
             "recommendation_id": (
                 verification
                 .recommendation_id
                ),
             "analysis_id": (
                 verification.analysis_id
                ),
             "status": (
                 verification.status.value
                ),
             "confidence": (
                 verification.confidence
                ),
             "passed_count": (
                 verification.passed_count
                ),
             "failed_count": (
                 verification.failed_count
               ),
             "unknown_count": (
                 verification.unknown_count
             ),
            },
        )
    )

    publish_event_safely(
       session=session,
       event=recovery_event,
    )
     

    return verification


@router.get(
    "",
    response_model=list[
        RecoveryVerificationSummary
    ],
)
def get_recovery_verifications(
    recommendation_id: str | None = None,
    status_filter: RecoveryStatus | None = Query(
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
    RecoveryVerificationSummary
]:
    return list_recovery_verifications(
        session=session,
        recommendation_id=(
            recommendation_id
        ),
        status=(
            status_filter.value
            if status_filter
            else None
        ),
        limit=limit,
    )


@router.get(
    "/{verification_id}",
    response_model=RecoveryVerification,
)
def get_recovery_verification(
    verification_id: str,
    session: Session = Depends(
        get_session
    ),
) -> RecoveryVerification:
    verification = (
        load_recovery_verification(
            session=session,
            verification_id=(
                verification_id
            ),
        )
    )

    if verification is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Recovery verification not "
                f"found: {verification_id}"
            ),
        )

    return verification