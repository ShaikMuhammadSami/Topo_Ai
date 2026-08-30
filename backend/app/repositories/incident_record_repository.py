from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_predicate,
    tenant_get,
    require_record_owner,
)
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
    *,
    tenant_id: DomainTenant,
) -> IncidentRecord | None:
    statement = (
        select(IncidentRecord)
        .where(tenant_predicate(IncidentRecord, tenant_id))
        .where(IncidentRecord.fingerprint == fingerprint)
    )

    return session.scalars(
        statement
    ).first()


def find_correlatable_incident(
    session: Session,
    *,
    fingerprint: str,
    observed_after: datetime,
    replay_at: datetime | None = None,
    tenant_id: DomainTenant,
) -> IncidentRecord | None:
    """
    Return only an active, recent incident family.

    Terminal or stale incidents must not absorb a later
    recurrence merely because their fingerprint matches.
    """

    statement = (
        select(IncidentRecord)
        .where(tenant_predicate(IncidentRecord, tenant_id))
        .where(
            IncidentRecord.fingerprint == fingerprint,
            IncidentRecord.status.in_(
                [
                    IncidentStatus.OPEN.value,
                    IncidentStatus.INVESTIGATING.value,
                    IncidentStatus.RECOMMENDED.value,
                    IncidentStatus.REMEDIATING.value,
                ]
            ),
            IncidentRecord.last_observed_at >= observed_after.isoformat(),
        )
        .order_by(IncidentRecord.last_observed_at.desc())
        .limit(1)
    )

    active = session.scalar(statement)

    if active is not None or replay_at is None:
        return active

    # An overlapping source poll may replay an event
    # after its incident was resolved. Treat only an
    # observation no newer than the recorded incident as
    # the same evidence; a genuinely later recurrence is
    # still allowed to create a new incident.
    replay_statement = (
        select(IncidentRecord)
        .where(tenant_predicate(IncidentRecord, tenant_id))
        .where(
            IncidentRecord.fingerprint == fingerprint,
            IncidentRecord.last_observed_at >= replay_at.isoformat(),
        )
        .order_by(IncidentRecord.last_observed_at.desc())
        .limit(1)
    )

    return session.scalar(replay_statement)


def list_incidents_by_fingerprint(
    session: Session,
    *,
    fingerprint: str,
    tenant_id: DomainTenant,
) -> list[IncidentRecord]:
    statement = (
        select(IncidentRecord)
        .where(tenant_predicate(IncidentRecord, tenant_id))
        .where(IncidentRecord.fingerprint == fingerprint)
        .order_by(IncidentRecord.created_at.desc())
    )

    return list(
        session.scalars(statement).all()
    )


def load_incident_record(
    session: Session,
    incident_id: str,
    *,
    tenant_id: DomainTenant,
) -> IncidentRecordView | None:
    record = tenant_get(
        session,
        IncidentRecord,
        incident_id,
        tenant_id=tenant_id,
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
    *,
    tenant_id: DomainTenant,
) -> list[IncidentRecordSummary]:
    statement = select(IncidentRecord).where(
        tenant_predicate(IncidentRecord, tenant_id)
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
    *,
    tenant_id: DomainTenant,
) -> IncidentRecord:
    require_record_owner(record, tenant_id=tenant_id)
    session.add(record)
    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return record


def update_incident_status(
    session: Session,
    incident_id: str,
    status: IncidentStatus,
    note: str | None,
    *,
    tenant_id: DomainTenant,
) -> IncidentRecordView | None:
    record = tenant_get(
        session,
        IncidentRecord,
        incident_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    record.status = status.value
    record.status_note = note
    record.updated_at = utc_now_iso()

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return _to_view(record)
