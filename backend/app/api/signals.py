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