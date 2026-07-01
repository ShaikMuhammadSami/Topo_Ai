from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IncidentAnalysisRecord,
    utc_now_iso,
)
from app.models.incidents import (
    IncidentAnalysis,
    IncidentAnalysisSummary,
)


def save_incident_analysis(
    session: Session,
    analysis: IncidentAnalysis,
) -> IncidentAnalysisRecord:
    record = session.get(
        IncidentAnalysisRecord,
        analysis.analysis_id,
    )

    now = utc_now_iso()

    top_hypothesis = (
        analysis.hypotheses[0]
        if analysis.hypotheses
        else None
    )

    if record is None:
        record = IncidentAnalysisRecord(
            analysis_id=(
                analysis.analysis_id
            ),
            signal_id=analysis.signal_id,
            topology_snapshot_id=(
                analysis
                .topology_snapshot_id
            ),
            algorithm_version=(
                analysis
                .algorithm_version
            ),
            generated_at=(
                analysis
                .generated_at
                .isoformat()
            ),
            incident_title=(
                analysis.incident_title
            ),
            cluster_name=(
                analysis.cluster_name
            ),
            namespace=(
                analysis.namespace
            ),
            candidate_count=(
                analysis.candidate_count
            ),
            hypothesis_count=len(
                analysis.hypotheses
            ),
            top_hypothesis_title=(
                top_hypothesis.title
                if top_hypothesis
                else None
            ),
            top_hypothesis_score=(
                str(top_hypothesis.score)
                if top_hypothesis
                else None
            ),
            payload_json=(
                analysis.model_dump_json()
            ),
            created_at=now,
            updated_at=now,
        )

        session.add(record)

    else:
        record.generated_at = (
            analysis
            .generated_at
            .isoformat()
        )

        record.incident_title = (
            analysis.incident_title
        )

        record.candidate_count = (
            analysis.candidate_count
        )

        record.hypothesis_count = len(
            analysis.hypotheses
        )

        record.top_hypothesis_title = (
            top_hypothesis.title
            if top_hypothesis
            else None
        )

        record.top_hypothesis_score = (
            str(top_hypothesis.score)
            if top_hypothesis
            else None
        )

        record.payload_json = (
            analysis.model_dump_json()
        )

        record.updated_at = now

    session.commit()
    session.refresh(record)

    return record


def load_incident_analysis(
    session: Session,
    analysis_id: str,
) -> IncidentAnalysis | None:
    record = session.get(
        IncidentAnalysisRecord,
        analysis_id,
    )

    if record is None:
        return None

    return (
        IncidentAnalysis
        .model_validate_json(
            record.payload_json
        )
    )


def list_incident_analyses(
    session: Session,
    signal_id: str | None = None,
    limit: int = 100,
) -> list[IncidentAnalysisSummary]:
    statement = select(
        IncidentAnalysisRecord
    )

    if signal_id:
        statement = statement.where(
            IncidentAnalysisRecord.signal_id
            == signal_id
        )

    statement = (
        statement
        .order_by(
            IncidentAnalysisRecord
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
        IncidentAnalysisSummary(
            analysis_id=record.analysis_id,
            signal_id=record.signal_id,
            generated_at=(
                datetime.fromisoformat(
                    record.generated_at
                )
            ),
            incident_title=(
                record.incident_title
            ),
            cluster_name=(
                record.cluster_name
            ),
            namespace=record.namespace,
            candidate_count=(
                record.candidate_count
            ),
            hypothesis_count=(
                record.hypothesis_count
            ),
            top_hypothesis_title=(
                record
                .top_hypothesis_title
            ),
            top_hypothesis_score=(
                float(
                    record
                    .top_hypothesis_score
                )
                if (
                    record
                    .top_hypothesis_score
                    is not None
                )
                else None
            ),
        )
        for record in records
    ]