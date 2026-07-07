from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    RecoveryVerificationRecord,
    utc_now_iso,
)
from app.models.recovery import (
    RecoveryStatus,
    RecoveryVerification,
    RecoveryVerificationSummary,
)


def save_recovery_verification(
    session: Session,
    verification: RecoveryVerification,
) -> RecoveryVerificationRecord:
    record = session.get(
        RecoveryVerificationRecord,
        verification.verification_id,
    )

    now = utc_now_iso()

    if record is None:
        record = RecoveryVerificationRecord(
            verification_id=(
                verification
                .verification_id
            ),
            recommendation_id=(
                verification
                .recommendation_id
            ),
            analysis_id=(
                verification.analysis_id
            ),
            signal_id=(
                verification.signal_id
            ),
            pre_snapshot_id=(
                verification
                .pre_snapshot_id
            ),
            post_snapshot_id=(
                verification
                .post_snapshot_id
            ),
            algorithm_version=(
                verification
                .algorithm_version
            ),
            generated_at=(
                verification
                .generated_at
                .isoformat()
            ),
            applied_at=(
                verification
                .applied_at
                .isoformat()
            ),
            status=(
                verification.status.value
            ),
            confidence=str(
                verification.confidence
            ),
            summary=(
                verification.summary
            ),
            cluster_name=(
                verification.cluster_name
            ),
            namespace=(
                verification.namespace
            ),
            target_entity_id=(
                verification
                .target_entity_id
            ),
            target_entity_kind=(
                verification
                .target_entity_kind
            ),
            target_entity_name=(
                verification
                .target_entity_name
            ),
            passed_count=(
                verification.passed_count
            ),
            failed_count=(
                verification.failed_count
            ),
            unknown_count=(
                verification.unknown_count
            ),
            payload_json=(
                verification
                .model_dump_json()
            ),
            created_at=now,
            updated_at=now,
        )

        session.add(record)

    else:
        record.generated_at = (
            verification
            .generated_at
            .isoformat()
        )

        record.status = (
            verification.status.value
        )

        record.confidence = str(
            verification.confidence
        )

        record.summary = (
            verification.summary
        )

        record.passed_count = (
            verification.passed_count
        )

        record.failed_count = (
            verification.failed_count
        )

        record.unknown_count = (
            verification.unknown_count
        )

        record.payload_json = (
            verification
            .model_dump_json()
        )

        record.updated_at = now

    session.commit()
    session.refresh(record)

    return record


def load_recovery_verification(
    session: Session,
    verification_id: str,
) -> RecoveryVerification | None:
    record = session.get(
        RecoveryVerificationRecord,
        verification_id,
    )

    if record is None:
        return None

    return (
        RecoveryVerification
        .model_validate_json(
            record.payload_json
        )
    )


def list_recovery_verifications(
    session: Session,
    recommendation_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[
    RecoveryVerificationSummary
]:
    statement = select(
        RecoveryVerificationRecord
    )

    if recommendation_id:
        statement = statement.where(
            RecoveryVerificationRecord
            .recommendation_id
            == recommendation_id
        )

    if status:
        statement = statement.where(
            RecoveryVerificationRecord
            .status
            == status
        )

    statement = (
        statement
        .order_by(
            RecoveryVerificationRecord
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
        RecoveryVerificationSummary(
            verification_id=(
                record.verification_id
            ),
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
            status=RecoveryStatus(
                record.status
            ),
            confidence=float(
                record.confidence
            ),
            summary=record.summary,
            cluster_name=(
                record.cluster_name
            ),
            namespace=record.namespace,
            target_entity_kind=(
                record
                .target_entity_kind
            ),
            target_entity_name=(
                record
                .target_entity_name
            ),
            passed_count=(
                record.passed_count
            ),
            failed_count=(
                record.failed_count
            ),
            unknown_count=(
                record.unknown_count
            ),
        )
        for record in records
    ]