from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_predicate,
)

# import json

# from sqlalchemy.orm import Session

# from app.db.models import (
#     SnapshotRecord,
# )
# from app.models.topology import (
#     GraphSnapshot,
# )


# def save_snapshot(
#     session: Session,
#     snapshot: GraphSnapshot,
# ):

#     record = SnapshotRecord(
#         id=snapshot.snapshot_id,
#         snapshot_id=snapshot.snapshot_id,
#         cluster_name=(
#             snapshot.scope.get(
#                 "cluster",
#                 "unknown",
#             )
#         ),
#         payload_json=snapshot.model_dump_json(),
#     )

#     session.add(record)
#     session.commit()


# def load_snapshot(
#     session: Session,
#     snapshot_id: str,
# ):

#     record = (
#         session.query(
#             SnapshotRecord
#         )
#         .filter(
#             SnapshotRecord.snapshot_id
#             == snapshot_id
#         )
#         .first()
#     )

#     if not record:
#         return None

#     return GraphSnapshot.model_validate_json(
#         record.payload_json
#     )
import json

from sqlalchemy.orm import Session

from app.db.models import SnapshotRecord
from app.models.topology import GraphSnapshot
from app.services.tenant_world_model import snapshot_from_owned_record


def load_topology_snapshot(
    session: Session,
    snapshot_id: str,
    *,
    tenant_id: DomainTenant,
) -> GraphSnapshot | None:

    record = (
        session.query(SnapshotRecord)
        .filter(tenant_predicate(SnapshotRecord, tenant_id))
        .filter(SnapshotRecord.snapshot_id == snapshot_id)
        .first()
    )

    if record is None:
        return None

    return snapshot_from_owned_record(record, tenant_id=tenant_id)
