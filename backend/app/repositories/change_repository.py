from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)
from collections.abc import Iterable
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeRecord,
    utc_now_iso,
)
from app.models.changes import (
    ChangeSummary,
    NormalizedChange,
)
from app.models.temporal import (
    TemporalStatus,
    TimeOrigin,
    TimeQuality,
)
from app.services.temporal_semantics import (
    build_temporal_metadata,
    parse_utc,
)


def save_changes(
    session: Session,
    changes: Iterable[NormalizedChange],
    *,
    tenant_id: DomainTenant,
) -> tuple[int, int]:
    created_count = 0
    updated_count = 0

    now = utc_now_iso()

    for change in changes:
        record = tenant_get(
            session,
            ChangeRecord,
            change.change_id,
            tenant_id=tenant_id,
        )

        if record is None:
            temporal = change.temporal or build_temporal_metadata(
                source_event_at=None,
                observed_at=change.detected_at,
                recorded_at=now,
                source_time_trusted=False,
                source_field="NormalizedChange.detected_at",
                fallback_origin=TimeOrigin.DERIVED,
                fallback_quality=TimeQuality.BOUNDED,
            )
            temporal = temporal.model_copy(
                update={
                    "recorded_at": parse_utc(now),
                    "status": TemporalStatus.COMPLETE,
                }
            )
            change = change.model_copy(
                update={"temporal": temporal}
            )
            record = ChangeRecord(
                change_id=(change.change_id),
                fingerprint=(change.fingerprint),
                change_type=(change.change_type.value),
                category=(change.category.value),
                importance=(change.importance.value),
                source_system=(change.source_system),
                title=change.title,
                summary=change.summary,
                detected_at=(change.detected_at.isoformat()),
                from_snapshot_id=(change.from_snapshot_id),
                to_snapshot_id=(change.to_snapshot_id),
                cluster_name=(change.cluster_name),
                namespace=(change.namespace),
                entity_id=change.entity_id,
                entity_kind=(change.entity_kind),
                entity_name=(change.entity_name),
                relationship_id=(change.relationship_id),
                relationship_type=(change.relationship_type),
                payload_json=(change.model_dump_json()),
                created_at=now,
                updated_at=now,
                tenant_id=tenant_value(tenant_id),
            )

            session.add(record)
            created_count += 1

        else:
            record.category = (
                change.category.value
            )

            record.importance = (
                change.importance.value
            )

            record.title = change.title
            record.summary = change.summary

            record.payload_json = (
                change.model_dump_json()
            )

            record.updated_at = now

            updated_count += 1

    tenant_commit(session, tenant_id=tenant_id)

    return created_count, updated_count


def _to_summary(
    record: ChangeRecord,
) -> ChangeSummary:
    change = (
        NormalizedChange
        .model_validate_json(
            record.payload_json
        )
    )

    return ChangeSummary(
        change_id=change.change_id,
        change_type=change.change_type,
        category=change.category,
        importance=change.importance,
        title=change.title,
        summary=change.summary,
        detected_at=change.detected_at,
        from_snapshot_id=(
            change.from_snapshot_id
        ),
        to_snapshot_id=(
            change.to_snapshot_id
        ),
        cluster_name=(
            change.cluster_name
        ),
        namespace=change.namespace,
        entity_id=change.entity_id,
        entity_kind=change.entity_kind,
        entity_name=change.entity_name,
        relationship_id=(
            change.relationship_id
        ),
        relationship_type=(
            change.relationship_type
        ),
    )


def list_changes(
    session: Session,
    cluster_name: str | None = None,
    namespace: str | None = None,
    category: str | None = None,
    importance: str | None = None,
    limit: int = 200,
    *,
    tenant_id: DomainTenant,
) -> list[ChangeSummary]:
    statement = select(ChangeRecord).where(tenant_predicate(ChangeRecord, tenant_id))

    if cluster_name:
        statement = statement.where(
            ChangeRecord.cluster_name
            == cluster_name
        )

    if namespace:
        statement = statement.where(
            ChangeRecord.namespace
            == namespace
        )

    if category:
        statement = statement.where(
            ChangeRecord.category
            == category
        )

    if importance:
        statement = statement.where(
            ChangeRecord.importance
            == importance
        )

    statement = (
        statement
        .order_by(
            ChangeRecord
            .detected_at
            .desc()
        )
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    return [
        _to_summary(record)
        for record in records
    ]


def load_change(
    session: Session,
    change_id: str,
    *,
    tenant_id: DomainTenant,
) -> NormalizedChange | None:
    record = tenant_get(
        session,
        ChangeRecord,
        change_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return (
        NormalizedChange
        .model_validate_json(
            record.payload_json
        )
    )


def find_changes_in_window(
    session: Session,
    cluster_name: str,
    namespace: str | None,
    start_at: datetime,
    end_at: datetime,
    limit: int = 500,
    *,
    tenant_id: DomainTenant,
) -> list[NormalizedChange]:
    statement = (
        select(ChangeRecord)
        .where(tenant_predicate(ChangeRecord, tenant_id))
        .where(
            ChangeRecord.cluster_name == cluster_name,
            ChangeRecord.detected_at >= start_at.isoformat(),
            ChangeRecord.detected_at <= end_at.isoformat(),
        )
    )

    if namespace:
        statement = statement.where(
            ChangeRecord.namespace
            == namespace
        )

    statement = (
        statement
        .order_by(
            ChangeRecord
            .detected_at
            .desc()
        )
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    return [
        NormalizedChange
        .model_validate_json(
            record.payload_json
        )
        for record in records
    ]
