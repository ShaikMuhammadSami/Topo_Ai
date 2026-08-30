from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    RecommendationRecord,
    utc_now_iso,
)
from app.models.recommendations import (
    RecommendationStatus,
    RecommendationSummary,
    RemediationRecommendation,
    RecommendationActionType,
    RecommendationRisk,
)


def save_recommendation(
    session: Session,
    recommendation: RemediationRecommendation,
    *,
    tenant_id: DomainTenant,
) -> RecommendationRecord:
    record = tenant_get(
        session,
        RecommendationRecord,
        recommendation.recommendation_id,
        tenant_id=tenant_id,
    )

    now = utc_now_iso()

    if record is None:
        record = RecommendationRecord(
            recommendation_id=(recommendation.recommendation_id),
            analysis_id=(recommendation.analysis_id),
            hypothesis_id=(recommendation.hypothesis_id),
            signal_id=(recommendation.signal_id),
            change_id=(recommendation.change_id),
            algorithm_version=(recommendation.algorithm_version),
            generated_at=(recommendation.generated_at.isoformat()),
            title=recommendation.title,
            action_type=(recommendation.action_type.value),
            status=(recommendation.status.value),
            confidence=str(recommendation.confidence),
            risk=recommendation.risk.value,
            cluster_name=(recommendation.cluster_name),
            namespace=(recommendation.namespace),
            target_entity_id=(recommendation.target_entity_id),
            target_entity_kind=(recommendation.target_entity_kind),
            target_entity_name=(recommendation.target_entity_name),
            applied_at=(
                recommendation.applied_at.isoformat()
                if recommendation.applied_at
                else None
            ),
            payload_json=(recommendation.model_dump_json()),
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )

        session.add(record)

    else:
        current = (
            RemediationRecommendation
            .model_validate_json(
                record.payload_json
            )
        )

        recommendation.status = (
            current.status
        )

        recommendation.status_note = (
            current.status_note
        )

        recommendation.applied_at = (
            current.applied_at
        )

        record.title = (
            recommendation.title
        )

        record.action_type = (
            recommendation
            .action_type.value
        )

        record.confidence = str(
            recommendation.confidence
        )

        record.risk = (
            recommendation.risk.value
        )

        record.status = (
            recommendation.status.value
        )

        record.applied_at = (
            recommendation
            .applied_at
            .isoformat()
            if recommendation.applied_at
            else None
        )

        record.payload_json = (
            recommendation
            .model_dump_json()
        )

        record.updated_at = now

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return record


def load_recommendation(
    session: Session,
    recommendation_id: str,
    *,
    tenant_id: DomainTenant,
) -> RemediationRecommendation | None:
    record = tenant_get(
        session,
        RecommendationRecord,
        recommendation_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return (
        RemediationRecommendation
        .model_validate_json(
            record.payload_json
        )
    )


def list_recommendations(
    session: Session,
    analysis_id: str | None = None,
    signal_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    *,
    tenant_id: DomainTenant,
) -> list[RecommendationSummary]:
    statement = select(RecommendationRecord).where(
        tenant_predicate(RecommendationRecord, tenant_id)
    )

    if analysis_id:
        statement = statement.where(
            RecommendationRecord.analysis_id
            == analysis_id
        )

    if signal_id:
        statement = statement.where(
            RecommendationRecord.signal_id
            == signal_id
        )

    if status:
        statement = statement.where(
            RecommendationRecord.status
            == status
        )

    statement = (
        statement
        .order_by(
            RecommendationRecord
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
        RecommendationSummary(
            recommendation_id=(
                record.recommendation_id
            ),
            analysis_id=(
                record.analysis_id
            ),
            signal_id=record.signal_id,
            generated_at=(
                datetime.fromisoformat(
                    record.generated_at
                )
            ),
            title=record.title,
            action_type=(
                RecommendationActionType(
                   record.action_type
                )
            ),
            status=(
              RecommendationStatus(
                  record.status
            )
            ),
            confidence=float(
                record.confidence
            ),
            risk=(
               RecommendationRisk(
                  record.risk
                )
            ),
            namespace=record.namespace,
            target_entity_kind=(
                record.target_entity_kind
            ),
            target_entity_name=(
                record.target_entity_name
            ),
            applied_at=(
                datetime.fromisoformat(
                    record.applied_at
                )
                if record.applied_at
                else None
            ),
        )
        for record in records
    ]


def update_recommendation_status(
    session: Session,
    recommendation_id: str,
    status: RecommendationStatus,
    note: str | None,
    *,
    tenant_id: DomainTenant,
) -> RemediationRecommendation | None:
    record = tenant_get(
        session,
        RecommendationRecord,
        recommendation_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    recommendation = (
        RemediationRecommendation
        .model_validate_json(
            record.payload_json
        )
    )

    recommendation.status = status
    recommendation.status_note = note

    if (
        status
        == RecommendationStatus.APPLIED
    ):
        recommendation.applied_at = (
            datetime.now(timezone.utc)
        )

    elif (
        status
        != RecommendationStatus.APPLIED
    ):
        recommendation.applied_at = None

    record.status = status.value

    record.applied_at = (
        recommendation.applied_at
        .isoformat()
        if recommendation.applied_at
        else None
    )

    record.payload_json = (
        recommendation.model_dump_json()
    )

    record.updated_at = utc_now_iso()

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return recommendation
