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
from app.models.lifecycle_automation import (
    FailureSignalBatchRequest,
    FailureSignalBatchResult,
)
from app.repositories.signal_repository import (
    list_signals,
    load_signal,
    save_signals,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.incident_grouping import (
    incident_fingerprint,
    is_failure_signal,
    signal_priority_key,
)
from app.services.continuous_lifecycle import (
    ingest_failure_signal_batch,
)
from app.models.lifecycle_automation import (
    TopologyCheckpointReason,
)
from app.services.network_topology_enricher import (
    enrich_kubernetes_network_topology,
)
from app.services.topology_checkpoint import (
    persist_topology_checkpoint,
)

def _select_representative_signals(
    signals,
):
    grouped = {}

    for signal in signals:
        fingerprint = (
            incident_fingerprint(signal)
        )

        current = grouped.get(
            fingerprint
        )

        if (
            current is None
            or signal_priority_key(signal)
            > signal_priority_key(current)
        ):
            grouped[fingerprint] = signal

    return sorted(
        grouped.values(),
        key=signal_priority_key,
        reverse=True,
    )
router = APIRouter(
    prefix="/api/v1/signals",
    tags=["signals"],
)


@router.post(
    "/ingest",
    response_model=FailureSignalBatchResult,
    status_code=status.HTTP_201_CREATED,
)
def ingest_normalized_failure_signals(
    request: FailureSignalBatchRequest,
    session: Session = Depends(get_session),
) -> FailureSignalBatchResult:
    """
    Deterministic internal signal contract for current
    and future authenticated source adapters.
    """

    return ingest_failure_signal_batch(
        session=session,
        signals=request.signals,
    )


@router.post(
    "/kubernetes/events/ingest",
    response_model=SignalIngestionResult,
    status_code=status.HTTP_201_CREATED,
)
def ingest_kubernetes_events(
    snapshot_id: str | None = Query(
        default=None,
        description=(
            "Optional stored topology snapshot used "
            "to map Kubernetes object UIDs "
            "to canonical entity IDs. When omitted, "
            "Topo performs and checkpoints discovery "
            "automatically."
        )
    ),
    auto_orchestrate: bool = Query(
        default=True,
    ),
    auto_orchestrate_grouped: bool = Query(
       default=True,
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
    try:
        snapshot = (
            load_snapshot(
                session=session,
                snapshot_id=snapshot_id,
            )
            if snapshot_id
            else None
        )

        if snapshot_id and snapshot is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Snapshot not found: "
                    f"{snapshot_id}"
                ),
            )

        namespace_value = (
            snapshot.scope.get("namespace")
            if snapshot is not None
            else None
        )
        namespace = (
            None
            if namespace_value in (None, "*")
            else namespace_value
        )
        kubernetes = KubernetesCollector(
            namespace=namespace
        )

        if snapshot is None:
            discovered = (
                enrich_kubernetes_network_topology(
                    kubernetes.collect()
                )
            )
            checkpoint = (
                persist_topology_checkpoint(
                    session=session,
                    snapshot=discovered,
                    reason=(
                        TopologyCheckpointReason
                        .PERIODIC_RECONCILE
                    ),
                    derive_changes=True,
                )
            )
            snapshot_id = checkpoint.snapshot_id
            snapshot = load_snapshot(
                session=session,
                snapshot_id=snapshot_id,
            )

        if snapshot is None:
            raise RuntimeError(
                "Automatic topology checkpoint "
                "could not be loaded."
            )

        cluster_name = snapshot.scope.get(
            "cluster"
        )

        if not cluster_name:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Snapshot does not contain "
                    "a cluster scope."
                ),
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
                    snapshot.snapshot_id
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

    lifecycle_result = None

    if auto_orchestrate:
        lifecycle_result = (
            ingest_failure_signal_batch(
                session=session,
                signals=signals,
            )
        )
        created_count = (
            lifecycle_result
            .created_signal_count
        )
        updated_count = (
            lifecycle_result
            .updated_signal_count
        )

    else:
        created_count, updated_count = (
            save_signals(
                session=session,
                signals=signals,
            )
        )
    qualifying_signals = [
        signal
        for signal in signals
        if is_failure_signal(signal)
    ]
    if auto_orchestrate_grouped:
        selected_signals = (
            _select_representative_signals(
                qualifying_signals
            )
        )
    else:
        selected_signals = sorted(
            qualifying_signals,
            key=signal_priority_key,
            reverse=True,
        )
    orchestration_results = []
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
        qualifying_signal_count=len(
          qualifying_signals
        ),
        orchestration_group_count=len(
          selected_signals
        ),
        duplicate_signal_count=max(
          0,
          len(qualifying_signals)
         - len(selected_signals),
        ),
        orchestrated_count=(
            len(lifecycle_result.results)
            if lifecycle_result is not None
            else 0
        ),
        skipped_orchestration_count=(
           max(
              0,
               len(qualifying_signals)
             - (
                 len(lifecycle_result.results)
                 if lifecycle_result is not None
                 else 0
             ),
            )
            if auto_orchestrate
            else 0
        ),
        orchestration_results=(
           orchestration_results
        ),
        incident_created_count=(
            lifecycle_result
            .incident_created_count
            if lifecycle_result is not None
            else 0
        ),
        incident_correlated_count=(
            lifecycle_result
            .incident_correlated_count
            if lifecycle_result is not None
            else 0
        ),
        automatic_analysis_states=(
            [
                result
                .automatic_analysis_state
                .value
                for result in (
                    lifecycle_result.results
                    if lifecycle_result
                    is not None
                    else []
                )
            ]
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
