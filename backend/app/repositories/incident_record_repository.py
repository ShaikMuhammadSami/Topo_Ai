from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IncidentRecord,
    utc_now_iso,
)
from app.models.incident_records import (
    IncidentRecordSummary,
    IncidentRecordView,
    IncidentSeverity,
    IncidentStatus,
)


def _to_view(
    record: IncidentRecord,
) -> IncidentRecordView:
    return IncidentRecordView(
        incident_id=record.incident_id,
        fingerprint=record.fingerprint,
        status=IncidentStatus(record.status),
        severity=IncidentSeverity(record.severity),
        title=record.title,
        summary=record.summary,
        cluster_name=record.cluster_name,
        namespace=record.namespace,
        primary_signal_id=record.primary_signal_id,
        latest_signal_id=record.latest_signal_id,
        topology_snapshot_id=record.topology_snapshot_id,
        affected_entity_id=record.affected_entity_id,
        affected_object_kind=record.affected_object_kind,
        affected_object_name=record.affected_object_name,
        first_observed_at=datetime.fromisoformat(
            record.first_observed_at
        ),
        last_observed_at=datetime.fromisoformat(
            record.last_observed_at
        ),
        latest_analysis_id=record.latest_analysis_id,
        top_hypothesis_title=record.top_hypothesis_title,
        top_hypothesis_score=(
            float(record.top_hypothesis_score)
            if record.top_hypothesis_score is not None
            else None
        ),
        recommendation_count=record.recommendation_count,
        latest_recommendation_id=record.latest_recommendation_id,
        recovery_status=record.recovery_status,
        latest_recovery_verification_id=(
            record.latest_recovery_verification_id
        ),
        occurrence_count=record.occurrence_count,
        created_at=datetime.fromisoformat(
            record.created_at
        ),
        updated_at=datetime.fromisoformat(
            record.updated_at
        ),
        status_note=record.status_note,
    )


def _to_summary(
    record: IncidentRecord,
) -> IncidentRecordSummary:
    view = _to_view(record)

    return IncidentRecordSummary(
        incident_id=view.incident_id,
        status=view.status,
        severity=view.severity,
        title=view.title,
        cluster_name=view.cluster_name,
        namespace=view.namespace,
        affected_object_kind=view.affected_object_kind,
        affected_object_name=view.affected_object_name,
        first_observed_at=view.first_observed_at,
        last_observed_at=view.last_observed_at,
        top_hypothesis_title=view.top_hypothesis_title,
        top_hypothesis_score=view.top_hypothesis_score,
        recommendation_count=view.recommendation_count,
        recovery_status=view.recovery_status,
        occurrence_count=view.occurrence_count,
    )


def get_incident_by_fingerprint(
    session: Session,
    fingerprint: str,
) -> IncidentRecord | None:
    statement = select(
        IncidentRecord
    ).where(
        IncidentRecord.fingerprint
        == fingerprint
    )

    return session.scalars(
        statement
    ).first()


def load_incident_record(
    session: Session,
    incident_id: str,
) -> IncidentRecordView | None:
    record = session.get(
        IncidentRecord,
        incident_id,
    )

    if record is None:
        return None

    return _to_view(record)


def list_incident_records(
    session: Session,
    status: str | None = None,
    severity: str | None = None,
    namespace: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[IncidentRecordSummary]:
    statement = select(
        IncidentRecord
    )

    if status:
        statement = statement.where(
            IncidentRecord.status == status
        )

    if severity:
        statement = statement.where(
            IncidentRecord.severity == severity
        )

    if namespace:
        statement = statement.where(
            IncidentRecord.namespace == namespace
        )

    statement = (
        statement
        .order_by(
            IncidentRecord.last_observed_at.desc()
        )
        .limit(limit)
        .offset(offset)
    )

    records = list(
        session.scalars(statement).all()
    )

    return [
        _to_summary(record)
        for record in records
    ]


def save_incident_record(
    session: Session,
    record: IncidentRecord,
) -> IncidentRecord:
    session.add(record)
    session.commit()
    session.refresh(record)

    return record


def update_incident_status(
    session: Session,
    incident_id: str,
    status: IncidentStatus,
    note: str | None,
) -> IncidentRecordView | None:
    record = session.get(
        IncidentRecord,
        incident_id,
    )

    if record is None:
        return None

    record.status = status.value
    record.status_note = note
    record.updated_at = utc_now_iso()

    session.commit()
    session.refresh(record)

    return _to_view(record)