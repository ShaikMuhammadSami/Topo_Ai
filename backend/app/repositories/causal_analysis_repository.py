from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CausalAnalysisRecord,
    utc_now_iso,
)
from app.models.causal_rca import (
    CausalAnalysisResponse,
)


def save_causal_analysis(
    session: Session,
    *,
    analysis: CausalAnalysisResponse,
    commit: bool = True,
) -> None:
    record = session.get(
        CausalAnalysisRecord,
        analysis.analysis_id,
    )

    now = utc_now_iso()

    top = analysis.top_hypothesis

    if record is None:
        record = CausalAnalysisRecord(
            analysis_id=(
                analysis.analysis_id
            ),
            incident_id=(
                analysis.incident_id
            ),
            generated_at=(
                analysis.generated_at
            ),
            algorithm_version=(
                analysis.algorithm_version
            ),
            candidate_count=(
                analysis.candidate_count
            ),
            hypothesis_count=(
                analysis.hypothesis_count
            ),
            top_hypothesis_score=(
                top.score
                if top
                else None
            ),
            top_root_event_id=(
                top.root_event_id
                if top
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
            analysis.generated_at
        )

        record.algorithm_version = (
            analysis.algorithm_version
        )

        record.candidate_count = (
            analysis.candidate_count
        )

        record.hypothesis_count = (
            analysis.hypothesis_count
        )

        record.top_hypothesis_score = (
            top.score
            if top
            else None
        )

        record.top_root_event_id = (
            top.root_event_id
            if top
            else None
        )

        record.payload_json = (
            analysis.model_dump_json()
        )

        record.updated_at = now

    if commit:
        session.commit()


def load_causal_analysis(
    session: Session,
    *,
    analysis_id: str,
) -> CausalAnalysisResponse | None:
    record = session.get(
        CausalAnalysisRecord,
        analysis_id,
    )

    if record is None:
        return None

    return (
        CausalAnalysisResponse
        .model_validate_json(
            record.payload_json
        )
    )


def latest_causal_analysis(
    session: Session,
    *,
    incident_id: str,
) -> CausalAnalysisResponse | None:
    statement = (
        select(CausalAnalysisRecord)
        .where(
            CausalAnalysisRecord
            .incident_id
            == incident_id
        )
        .order_by(
            CausalAnalysisRecord
            .generated_at
            .desc()
        )
        .limit(1)
    )

    record = session.scalar(
        statement
    )

    if record is None:
        return None

    return (
        CausalAnalysisResponse
        .model_validate_json(
            record.payload_json
        )
    )