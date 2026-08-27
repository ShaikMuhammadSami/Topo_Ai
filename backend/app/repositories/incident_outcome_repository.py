from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IncidentOutcomeRecord,
    utc_now_iso,
)
from app.models.incident_outcome import (
    IncidentOutcome,
)


def load_incident_outcome_record(
    session: Session,
    *,
    incident_id: str,
) -> IncidentOutcomeRecord | None:
    statement = (
        select(IncidentOutcomeRecord)
        .where(
            IncidentOutcomeRecord.incident_id
            == incident_id
        )
        .limit(1)
    )

    return session.scalar(statement)


def list_incident_outcome_records(
    session: Session,
    *,
    exclude_incident_id: str | None = None,
    limit: int = 500,
) -> list[IncidentOutcomeRecord]:
    """Return a bounded historical-outcome set.

    The service layer validates payloads and decides
    whether a durable outcome is sufficiently complete
    for historical comparison.
    """
    statement = select(IncidentOutcomeRecord)

    if exclude_incident_id is not None:
        statement = statement.where(
            IncidentOutcomeRecord.incident_id
            != exclude_incident_id
        )

    statement = (
        statement
        .order_by(
            IncidentOutcomeRecord
            .resolved_at
            .desc()
            .nulls_last(),
            IncidentOutcomeRecord
            .updated_at
            .desc(),
            IncidentOutcomeRecord
            .incident_id
            .asc(),
        )
        .limit(max(1, min(limit, 1000)))
    )

    return list(
        session.scalars(statement).all()
    )


def load_incident_outcome(
    session: Session,
    *,
    incident_id: str,
) -> IncidentOutcome | None:
    record = load_incident_outcome_record(
        session,
        incident_id=incident_id,
    )

    if record is None:
        return None

    return IncidentOutcome.model_validate_json(
        record.payload_json
    )


def outcome_source(
    record: IncidentOutcomeRecord,
) -> dict[str, Any]:
    try:
        value = json.loads(record.source_json)

    except json.JSONDecodeError:
        return {}

    return (
        value
        if isinstance(value, dict)
        else {}
    )


def save_incident_outcome(
    session: Session,
    *,
    outcome: IncidentOutcome,
    source: dict[str, Any],
) -> IncidentOutcomeRecord:
    record = load_incident_outcome_record(
        session,
        incident_id=outcome.incident_id,
    )

    now = utc_now_iso()
    source_json = json.dumps(
        source,
        sort_keys=True,
        default=str,
    )
    payload_json = outcome.model_dump_json()

    if record is None:
        record = IncidentOutcomeRecord(
            outcome_id=outcome.outcome_id,
            incident_id=outcome.incident_id,
            status=outcome.status.value,
            causal_analysis_id=(
                outcome.causal_analysis_id
            ),
            response_plan_reference=(
                outcome.response_plan_reference
            ),
            rca_verdict=(
                outcome.rca_verdict.value
            ),
            mitigated_at=(
                outcome.mitigated_at.isoformat()
                if outcome.mitigated_at
                else None
            ),
            resolved_at=(
                outcome.resolved_at.isoformat()
                if outcome.resolved_at
                else None
            ),
            source_json=source_json,
            payload_json=payload_json,
            created_at=now,
            updated_at=now,
        )
        session.add(record)

    else:
        record.status = outcome.status.value
        record.causal_analysis_id = (
            outcome.causal_analysis_id
        )
        record.response_plan_reference = (
            outcome.response_plan_reference
        )
        record.rca_verdict = (
            outcome.rca_verdict.value
        )
        record.mitigated_at = (
            outcome.mitigated_at.isoformat()
            if outcome.mitigated_at
            else None
        )
        record.resolved_at = (
            outcome.resolved_at.isoformat()
            if outcome.resolved_at
            else None
        )
        record.source_json = source_json
        record.payload_json = payload_json
        record.updated_at = now

    session.commit()
    session.refresh(record)

    return record
