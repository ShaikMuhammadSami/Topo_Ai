from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SnapshotRecord
from app.models.topology import GraphSnapshot
from app.models.temporal import TimeOrigin
from app.services.temporal_semantics import (
    observation_temporal_metadata,
    utc_now,
)


def _observation_origin(source_system: str) -> TimeOrigin:
    value = source_system.lower()
    if any(token in value for token in ("runtime", "tetragon", "ebpf")):
        return TimeOrigin.RUNTIME_OBSERVED
    return TimeOrigin.TOPO_OBSERVED


def _stamp_snapshot_temporal(
    snapshot: GraphSnapshot,
    *,
    recorded_at: datetime,
) -> GraphSnapshot:
    entities = [
        entity
        if entity.temporal is not None
        else entity.model_copy(
            update={
                "temporal": observation_temporal_metadata(
                    observed_at=entity.observed_at,
                    recorded_at=recorded_at,
                    origin=_observation_origin(entity.source_system),
                    source_field="Entity.observed_at",
                )
            }
        )
        for entity in snapshot.entities
    ]
    relationships = [
        relationship
        if relationship.temporal is not None
        else relationship.model_copy(
            update={
                "temporal": observation_temporal_metadata(
                    observed_at=relationship.observed_at,
                    recorded_at=recorded_at,
                    origin=_observation_origin(relationship.source_system),
                    source_field="Relationship.observed_at",
                )
            }
        )
        for relationship in snapshot.relationships
    ]
    evidence = [
        item
        if item.temporal is not None
        else item.model_copy(
            update={
                "temporal": observation_temporal_metadata(
                    observed_at=item.observed_at,
                    recorded_at=recorded_at,
                    origin=_observation_origin(item.source_system),
                    source_field="Evidence.observed_at",
                )
            }
        )
        for item in snapshot.evidence
    ]
    temporal = snapshot.temporal or observation_temporal_metadata(
        observed_at=snapshot.collected_at,
        recorded_at=recorded_at,
        origin=TimeOrigin.TOPO_OBSERVED,
        source_field="GraphSnapshot.collected_at",
    )
    return snapshot.model_copy(
        update={
            "entities": entities,
            "relationships": relationships,
            "evidence": evidence,
            "temporal": temporal,
        }
    )


def save_snapshot(
    session: Session,
    snapshot: GraphSnapshot,
    *,
    tenant_id: DomainTenant,
) -> SnapshotRecord:
    """
    Persist one complete graph snapshot.
    """
    recorded_at = utc_now()
    persisted = _stamp_snapshot_temporal(
        snapshot,
        recorded_at=recorded_at,
    )
    record = SnapshotRecord(
        snapshot_id=persisted.snapshot_id,
        schema_version=persisted.schema_version,
        collected_at=persisted.collected_at.isoformat(),
        collector_name=persisted.collector_name,
        collector_version=persisted.collector_version,
        cluster_name=persisted.scope.get("cluster"),
        namespace=persisted.scope.get("namespace"),
        entity_count=len(persisted.entities),
        relationship_count=len(persisted.relationships),
        evidence_count=len(persisted.evidence),
        scope_json=json.dumps(persisted.scope),
        payload_json=persisted.model_dump_json(),
        created_at=recorded_at.isoformat(),
        tenant_id=tenant_value(tenant_id),
    )

    session.add(record)
    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return record


def list_snapshots(
    session: Session,
    limit: int = 20,
    offset: int = 0,
    *,
    tenant_id: DomainTenant,
) -> list[SnapshotRecord]:
    statement = (
        select(SnapshotRecord)
        .where(tenant_predicate(SnapshotRecord, tenant_id))
        .order_by(SnapshotRecord.collected_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(
        session.scalars(statement).all()
    )


def get_snapshot_record(
    session: Session,
    snapshot_id: str,
    *,
    tenant_id: DomainTenant,
) -> SnapshotRecord | None:
    return tenant_get(
        session,
        SnapshotRecord,
        snapshot_id,
        tenant_id=tenant_id,
    )


def load_snapshot(
    session: Session,
    snapshot_id: str,
    *,
    tenant_id: DomainTenant,
) -> GraphSnapshot | None:
    record = get_snapshot_record(
        session=session,
        snapshot_id=snapshot_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return GraphSnapshot.model_validate_json(
        record.payload_json
    )
