from __future__ import annotations
from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)

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


from app.services.tenant_world_model import tenant_world, bind_world_value

@tenant_world(prefetched=())
def save_causal_analysis(
    session: Session,
    *,
    analysis: CausalAnalysisResponse,
    commit: bool = True,
    tenant_id: DomainTenant,
) -> CausalAnalysisResponse:
    bind_world_value(analysis, tenant_id=tenant_id)
    analysis = ensure_analysis_confidence_semantics(analysis)
    record = tenant_get(
        session,
        CausalAnalysisRecord,
        analysis.analysis_id,
        tenant_id=tenant_id,
    )

    now = utc_now_iso()

    top = analysis.top_hypothesis

    if record is None:
        record = CausalAnalysisRecord(
            analysis_id=(analysis.analysis_id),
            incident_id=(analysis.incident_id),
            generated_at=(analysis.generated_at),
            algorithm_version=(analysis.algorithm_version),
            candidate_count=(analysis.candidate_count),
            hypothesis_count=(analysis.hypothesis_count),
            top_hypothesis_score=(top.score if top else None),
            top_root_event_id=(top.root_event_id if top else None),
            payload_json=(analysis.model_dump_json()),
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
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
        tenant_commit(session, tenant_id=tenant_id)

    return analysis


@tenant_world(prefetched=())
def load_causal_analysis(
    session: Session,
    *,
    analysis_id: str,
    tenant_id: DomainTenant,
) -> CausalAnalysisResponse | None:
    record = tenant_get(
        session,
        CausalAnalysisRecord,
        analysis_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return ensure_analysis_confidence_semantics(
        CausalAnalysisResponse.model_validate_json(record.payload_json)
    )


@tenant_world(prefetched=())
def latest_causal_analysis(
    session: Session,
    *,
    incident_id: str,
    tenant_id: DomainTenant,
) -> CausalAnalysisResponse | None:
    statement = (
        select(CausalAnalysisRecord)
        .where(tenant_predicate(CausalAnalysisRecord, tenant_id))
        .where(CausalAnalysisRecord.incident_id == incident_id)
        .order_by(CausalAnalysisRecord.generated_at.desc())
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
