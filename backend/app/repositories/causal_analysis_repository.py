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
from app.services.confidence_semantics import (
    ensure_analysis_confidence_semantics,
)


def save_causal_analysis(
    session: Session,
    *,
    analysis: CausalAnalysisResponse,
    commit: bool = True,
) -> CausalAnalysisResponse:
    analysis = ensure_analysis_confidence_semantics(analysis)
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
        # A causal analysis ID identifies one immutable generation. Repeated
        # calculation with the same deterministic fingerprint returns the
        # original persisted payload instead of silently changing its ledger,
        # generated_at, or conclusions.
        return ensure_analysis_confidence_semantics(
            CausalAnalysisResponse.model_validate_json(record.payload_json)
        )

    if commit:
        session.commit()

    return analysis


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

    return ensure_analysis_confidence_semantics(
        CausalAnalysisResponse.model_validate_json(record.payload_json)
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

    return ensure_analysis_confidence_semantics(
        CausalAnalysisResponse.model_validate_json(record.payload_json)
    )
