from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)
from kubernetes.client.exceptions import ApiException
from sqlalchemy.orm import Session

from app.collectors.kubernetes_collector import (
    KubernetesCollector,
)
from app.db.database import get_session
from app.db.models import SnapshotRecord
from app.models.snapshots import (
    SnapshotDiffResult,
    SnapshotSummary,
)
from app.models.topology import GraphSnapshot
from app.repositories.snapshot_repository import (
    get_snapshot_record,
    list_snapshots,
    load_snapshot,
)
from app.services.snapshot_diff import compare_snapshots
from app.services.network_topology_enricher import (
    enrich_kubernetes_network_topology,
)
from app.models.lifecycle_automation import (
    TopologyCheckpointReason,
)
from app.services.topology_checkpoint import (
    checkpoint_metadata,
    persist_topology_checkpoint,
)

router = APIRouter(
    prefix="/api/v1/snapshots",
    tags=["snapshots"],
)


def record_to_summary(
    record: SnapshotRecord,
) -> SnapshotSummary:
    snapshot = GraphSnapshot.model_validate_json(
        record.payload_json
    )
    checkpoint = checkpoint_metadata(
        snapshot
    )

    return SnapshotSummary(
        snapshot_id=record.snapshot_id,
        schema_version=record.schema_version,
        collected_at=record.collected_at,
        recorded_at=record.created_at,
        temporal=snapshot.temporal,
        collector_name=record.collector_name,
        collector_version=record.collector_version,
        cluster_name=record.cluster_name,
        namespace=record.namespace,
        entity_count=record.entity_count,
        relationship_count=(
            record.relationship_count
        ),
        evidence_count=record.evidence_count,
        checkpoint_reason=(
            str(checkpoint.get("reason"))
            if checkpoint.get("reason")
            else None
        ),
        state_digest=(
            str(checkpoint.get("state_digest"))
            if checkpoint.get("state_digest")
            else None
        ),
    )


@router.post(
    "/capture",
    response_model=SnapshotSummary,
    status_code=status.HTTP_201_CREATED,
)
def capture_snapshot(
    namespace: str | None = Query(
        default=None,
        description=(
            "Optional namespace filter. " "Leave empty for the entire cluster."
        ),
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> SnapshotSummary:
    """
    Collect the current Kubernetes topology and persist it.
    """
    try:
        collector = KubernetesCollector(
            namespace=namespace
        )

        snapshot = collector.collect()
        snapshot = (
            enrich_kubernetes_network_topology(
                snapshot
            )
        )
        checkpoint = persist_topology_checkpoint(
            session=session,
            snapshot=snapshot,
            reason=(TopologyCheckpointReason.MANUAL),
            derive_changes=False,
            force=True,
            tenant_id=tenant_context.tenant_id,
        )
        record = get_snapshot_record(
            session=session,
            snapshot_id=checkpoint.snapshot_id,
            tenant_id=tenant_context.tenant_id,
        )

        if record is None:
            raise RuntimeError(
                "Captured snapshot could not be loaded."
            )

        return record_to_summary(record)

    except ApiException as exc:
        raise HTTPException(
            status_code=502,
            detail=(f"Kubernetes API error " f"{exc.status}: {exc.reason}"),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[SnapshotSummary],
)
def get_snapshot_list(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[SnapshotSummary]:
    records = list_snapshots(
        session=session,
        limit=limit,
        offset=offset,
        tenant_id=tenant_context.tenant_id,
    )

    return [
        record_to_summary(record)
        for record in records
    ]


@router.get(
    "/diff",
    response_model=SnapshotDiffResult,
)
def get_snapshot_diff(
    from_snapshot_id: str,
    to_snapshot_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> SnapshotDiffResult:
    before = load_snapshot(
        session=session,
        snapshot_id=from_snapshot_id,
        tenant_id=tenant_context.tenant_id,
    )

    after = load_snapshot(
        session=session,
        snapshot_id=to_snapshot_id,
        tenant_id=tenant_context.tenant_id,
    )

    if before is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Starting snapshot was not found: "
                f"{from_snapshot_id}"
            ),
        )

    if after is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Ending snapshot was not found: "
                f"{to_snapshot_id}"
            ),
        )

    return compare_snapshots(
        before=before,
        after=after,
    )


@router.get(
    "/{snapshot_id}",
    response_model=GraphSnapshot,
)
def get_snapshot(
    snapshot_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> GraphSnapshot:
    snapshot = load_snapshot(
        session=session,
        snapshot_id=snapshot_id,
        tenant_id=tenant_context.tenant_id,
    )

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Snapshot not found: {snapshot_id}"
            ),
        )

    return snapshot
