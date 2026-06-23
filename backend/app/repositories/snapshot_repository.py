import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SnapshotRecord
from app.models.topology import GraphSnapshot


def save_snapshot(
    session: Session,
    snapshot: GraphSnapshot,
) -> SnapshotRecord:
    """
    Persist one complete graph snapshot.
    """
    record = SnapshotRecord(
        snapshot_id=snapshot.snapshot_id,
        schema_version=snapshot.schema_version,
        collected_at=snapshot.collected_at.isoformat(),
        collector_name=snapshot.collector_name,
        collector_version=snapshot.collector_version,
        cluster_name=snapshot.scope.get("cluster"),
        namespace=snapshot.scope.get("namespace"),
        entity_count=len(snapshot.entities),
        relationship_count=len(snapshot.relationships),
        evidence_count=len(snapshot.evidence),
        scope_json=json.dumps(snapshot.scope),
        payload_json=snapshot.model_dump_json(),
    )

    session.add(record)
    session.commit()
    session.refresh(record)

    return record


def list_snapshots(
    session: Session,
    limit: int = 20,
) -> list[SnapshotRecord]:
    statement = (
        select(SnapshotRecord)
        .order_by(SnapshotRecord.collected_at.desc())
        .limit(limit)
    )

    return list(
        session.scalars(statement).all()
    )


def get_snapshot_record(
    session: Session,
    snapshot_id: str,
) -> SnapshotRecord | None:
    return session.get(
        SnapshotRecord,
        snapshot_id,
    )


def load_snapshot(
    session: Session,
    snapshot_id: str,
) -> GraphSnapshot | None:
    record = get_snapshot_record(
        session=session,
        snapshot_id=snapshot_id,
    )

    if record is None:
        return None

    return GraphSnapshot.model_validate_json(
        record.payload_json
    )