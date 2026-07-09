from collections import Counter

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from kubernetes.client.exceptions import (
    ApiException,
)
from sqlalchemy.orm import Session

from app.collectors.kubernetes_collector import (
    KubernetesCollector,
)
from app.collectors.kubernetes_event_collector import (
    KubernetesEventCollector,
)
from app.db.database import get_session
from app.models.signals import (
    NormalizedSignal,
    SignalIngestionResult,
    SignalSeverity,
    SignalSummary,
)
from app.repositories.signal_repository import (
    list_signals,
    load_signal,
    save_signals,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.incident_orchestrator import (
    orchestrate_signal,
)

FAILURE_SIGNAL_SEVERITIES = {
    SignalSeverity.WARNING,
    SignalSeverity.ERROR,
    SignalSeverity.CRITICAL,
}


def _is_failure_signal(
    severity: SignalSeverity,
) -> bool:
    return severity in FAILURE_SIGNAL_SEVERITIES

router = APIRouter(
    prefix="/api/v1/signals",
    tags=["signals"],
)


@router.post(
    "/kubernetes/events/ingest",
    response_model=SignalIngestionResult,
    status_code=status.HTTP_201_CREATED,
)
def ingest_kubernetes_events(
    snapshot_id: str = Query(
        description=(
            "Stored topology snapshot used "
            "to map Kubernetes object UIDs "
            "to canonical entity IDs."
        )
    ),
    auto_orchestrate: bool = Query(
        default=False,
    ),
    orchestration_lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
    ),
    orchestration_grace_minutes: int = Query(
        default=15,
        ge=0,
        le=30,
    ),
    orchestration_max_graph_hops: int = Query(
        default=6,
        ge=1,
        le=20,
    ),
    orchestration_max_hypotheses: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
    orchestration_minimum_recommendation_score: float = Query(
        default=0.50,
        ge=0.0,
        le=1.0,
    ),
    orchestration_max_recommendations: int = Query(
        default=3,
        ge=1,
        le=20,
    ),
    orchestration_limit: int = Query(
        default=5,
        ge=1,
        le=50,
    ),
    session: Session = Depends(
        get_session
    ),
) -> SignalIngestionResult:
    snapshot = load_snapshot(
        session=session,
        snapshot_id=snapshot_id,
    )

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Snapshot not found: "
                f"{snapshot_id}"
            ),
        )

    cluster_name = (
        snapshot.scope.get(
            "cluster"
        )
    )

    if not cluster_name:
        raise HTTPException(
            status_code=422,
            detail=(
                "Snapshot does not contain "
                "a cluster scope."
            ),
        )

    namespace_value = (
        snapshot.scope.get(
            "namespace"
        )
    )

    namespace = (
        None
        if namespace_value in (
            None,
            "*",
        )
        else namespace_value
    )

    try:
        kubernetes = (
            KubernetesCollector(
                namespace=namespace
            )
        )

        event_collector = (
            KubernetesEventCollector(
                core_api=(
                    kubernetes.core_api
                ),
                cluster_name=(
                    cluster_name
                ),
                namespace=namespace,
            )
        )

        signals = (
            event_collector.collect(
                snapshot=snapshot
            )
        )
        
        signals = [
            signal.model_copy(
                update={
                    "topology_snapshot_id": (
                     snapshot_id
                    )
                }
            )
            for signal in signals
        ]

    except ApiException as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Kubernetes Events API "
                f"returned {exc.status}: "
                f"{exc.reason}"
            ),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    created_count, updated_count = (
        save_signals(
            session=session,
            signals=signals,
        )
    )
    orchestration_results = []

    if auto_orchestrate:
        qualifying_signals = [
        signal
        for signal in signals
        if _is_failure_signal(
            signal.severity
        )
        ]

    qualifying_signals = [
        signal
        for signal in signals
        if _is_failure_signal(
            signal.severity
        )
    ]
    orchestration_results = []

    if auto_orchestrate:
        ordered_qualifying_signals = sorted(
            qualifying_signals,
            key=lambda signal: (
                signal.severity.value,
                signal.last_observed_at,
                signal.signal_id,
            ),
            reverse=True,
        )

        for signal in ordered_qualifying_signals[
           :orchestration_limit
        ]:
            result = orchestrate_signal(
                session=session,
                signal_id=signal.signal_id,
                lookback_minutes=(
                    orchestration_lookback_minutes
                ),
                grace_minutes=(
                    orchestration_grace_minutes
                ),
                max_graph_hops=(
                    orchestration_max_graph_hops
                ),
                max_hypotheses=(
                 orchestration_max_hypotheses
                ),
                minimum_recommendation_score=(
                    orchestration_minimum_recommendation_score
                ),
                max_recommendations=(
                    orchestration_max_recommendations
                ),
                require_failure_severity=True,
            )
            orchestration_results.append(result)
    mapped_count = sum(
        1
        for signal in signals
        if signal.involved_entity_id
    )

    severity_counts = Counter(
        signal.severity.value
        for signal in signals
    )

    return SignalIngestionResult(
        source_system="kubernetes",
        cluster_name=cluster_name,
        namespace=namespace,
        collected_count=len(signals),
        created_count=created_count,
        updated_count=updated_count,
        mapped_entity_count=(
            mapped_count
        ),
        unmapped_entity_count=(
            len(signals)
            - mapped_count
        ),
        severity_counts=dict(
            severity_counts
        ),
        auto_orchestrate=auto_orchestrate,
        orchestrated_count=len(
          orchestration_results
        ),
        skipped_orchestration_count=(
           max(
              0,
               len(qualifying_signals)
             - len(orchestration_results),
            )
            if auto_orchestrate
            else 0
        ),
        orchestration_results=(
           orchestration_results
        ),
    )


@router.get(
    "",
    response_model=list[
        SignalSummary
    ],
)
def get_signals(
    cluster_name: str | None = None,
    namespace: str | None = None,
    severity: SignalSeverity | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[SignalSummary]:
    return list_signals(
        session=session,
        cluster_name=cluster_name,
        namespace=namespace,
        severity=(
            severity.value
            if severity
            else None
        ),
        limit=limit,
    )


@router.get(
    "/{signal_id}",
    response_model=NormalizedSignal,
)
def get_signal(
    signal_id: str,
    session: Session = Depends(
        get_session
    ),
) -> NormalizedSignal:
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

    return signal