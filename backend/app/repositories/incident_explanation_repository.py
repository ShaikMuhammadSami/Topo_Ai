import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IncidentExplanationRecord,
    utc_now_iso,
)
from app.models.incident_explanation import (
    ExplanationProvider,
    GeneratedIncidentExplanation,
    GroundingEvidence,
    IncidentExplanationResponse,
)


def _to_response(
    record: IncidentExplanationRecord,
) -> IncidentExplanationResponse:
    evidence_values = json.loads(
        record.evidence_json
    )

    warnings = json.loads(
        record.warnings_json
    )

    return IncidentExplanationResponse(
        explanation_id=record.explanation_id,
        incident_id=record.incident_id,
        topology_snapshot_id=(
            record.topology_snapshot_id
        ),
        analysis_id=record.analysis_id,
        provider=ExplanationProvider(
            record.provider
        ),
        model_name=record.model_name,
        prompt_version=record.prompt_version,
        grounding_hash=record.grounding_hash,
        confidence=float(record.confidence),
        generated_at=record.generated_at,
        explanation=(
            GeneratedIncidentExplanation
            .model_validate_json(
                record.payload_json
            )
        ),
        evidence=[
            GroundingEvidence.model_validate(
                item
            )
            for item in evidence_values
        ],
        warnings=[
            str(item)
            for item in warnings
        ],
    )


def load_incident_explanation(
    session: Session,
    explanation_id: str,
) -> IncidentExplanationResponse | None:
    record = session.get(
        IncidentExplanationRecord,
        explanation_id,
    )

    if record is None:
        return None

    return _to_response(record)


def load_latest_incident_explanation(
    session: Session,
    incident_id: str,
) -> IncidentExplanationResponse | None:
    statement = (
        select(
            IncidentExplanationRecord
        )
        .where(
            IncidentExplanationRecord
            .incident_id
            == incident_id
        )
        .order_by(
            IncidentExplanationRecord
            .generated_at
            .desc()
        )
        .limit(1)
    )

    record = session.scalars(
        statement
    ).first()

    if record is None:
        return None

    return _to_response(record)


def list_incident_explanations(
    session: Session,
    incident_id: str,
    limit: int = 20,
) -> list[IncidentExplanationResponse]:
    statement = (
        select(
            IncidentExplanationRecord
        )
        .where(
            IncidentExplanationRecord
            .incident_id
            == incident_id
        )
        .order_by(
            IncidentExplanationRecord
            .generated_at
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
        _to_response(record)
        for record in records
    ]


def save_incident_explanation(
    session: Session,
    record: IncidentExplanationRecord,
) -> IncidentExplanationResponse:
    existing = session.get(
        IncidentExplanationRecord,
        record.explanation_id,
    )

    if existing is None:
        session.add(record)
        session.commit()
        session.refresh(record)

        return _to_response(record)

    existing.topology_snapshot_id = (
        record.topology_snapshot_id
    )

    existing.analysis_id = record.analysis_id
    existing.provider = record.provider
    existing.model_name = record.model_name

    existing.prompt_version = (
        record.prompt_version
    )

    existing.grounding_hash = (
        record.grounding_hash
    )

    existing.confidence = record.confidence
    existing.generated_at = record.generated_at
    existing.payload_json = record.payload_json
    existing.evidence_json = record.evidence_json
    existing.warnings_json = record.warnings_json
    existing.updated_at = utc_now_iso()

    session.commit()
    session.refresh(existing)

    return _to_response(existing)