from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    SignalRecord,
    utc_now_iso,
)
from app.models.signals import (
    NormalizedSignal,
    SignalSummary,
)
from app.services.incident_grouping import (
    incident_fingerprint,
)
from app.models.temporal import (
    TemporalStatus,
    TimeOrigin,
)
from app.services.temporal_semantics import (
    observation_temporal_metadata,
    parse_utc,
)


def _new_signal_temporal(
    signal: NormalizedSignal,
    *,
    recorded_at: str,
):
    if signal.temporal is not None:
        return signal.temporal.model_copy(
            update={
                "recorded_at": parse_utc(recorded_at),
                "status": TemporalStatus.COMPLETE,
            }
        )
    return observation_temporal_metadata(
        observed_at=signal.first_observed_at,
        recorded_at=recorded_at,
        origin=TimeOrigin.TOPO_OBSERVED,
        source_field="NormalizedSignal.first_observed_at",
    )

def save_signals(
    session: Session,
    signals: Iterable[
        NormalizedSignal
    ],
) -> tuple[int, int]:
    created_count = 0
    updated_count = 0

    now = utc_now_iso()

    for signal in signals:
        record = session.get(
            SignalRecord,
            signal.signal_id,
        )

        if record is None:
            signal = signal.model_copy(
                update={
                    "temporal": _new_signal_temporal(
                        signal,
                        recorded_at=now,
                    )
                }
            )
            record = SignalRecord(
                signal_id=(
                    signal.signal_id
                ),
                fingerprint=(
                    signal.fingerprint
                ),
                signal_type=(
                    signal.signal_type.value
                ),
                severity=(
                    signal.severity.value
                ),
                category=(
                    signal.category.value
                ),
                source_system=(
                    signal.source_system
                ),
                title=signal.title,
                summary=signal.summary,
                reason=signal.reason,
                action=signal.action,
                first_observed_at=(
                    signal
                    .first_observed_at
                    .isoformat()
                ),
                last_observed_at=(
                    signal
                    .last_observed_at
                    .isoformat()
                ),
                occurrence_count=(
                    signal.occurrence_count
                ),
                cluster_name=(
                    signal.cluster_name
                ),
                namespace=(
                    signal.namespace
                ),
                involved_entity_id=(
                    signal
                    .involved_entity_id
                ),
                involved_object_uid=(
                    signal
                    .involved_object_uid
                ),
                involved_object_kind=(
                    signal
                    .involved_object_kind
                ),
                involved_object_name=(
                    signal
                    .involved_object_name
                ),
                payload_json=(
                    signal.model_dump_json()
                ),
                created_at=now,
                updated_at=now,
            )

            session.add(record)

            created_count += 1

        else:
            existing_signal = (
                NormalizedSignal
                .model_validate_json(
                    record.payload_json
                )
            )

            merged_signal = signal.model_copy(
                update={
                    "first_observed_at": min(
                        existing_signal
                        .first_observed_at,
                        signal.first_observed_at,
                    ),
                    "last_observed_at": max(
                        existing_signal
                        .last_observed_at,
                        signal.last_observed_at,
                    ),
                    "occurrence_count": max(
                        existing_signal
                        .occurrence_count,
                        signal.occurrence_count,
                    ),
                    "topology_snapshot_id": (
                        existing_signal
                        .topology_snapshot_id
                        or signal
                        .topology_snapshot_id
                    ),
                    "involved_entity_id": (
                        existing_signal
                        .involved_entity_id
                        or signal
                        .involved_entity_id
                    ),
                    "temporal": (
                        existing_signal.temporal
                        or signal.temporal
                    ),
                }
            )

            record.severity = (
                merged_signal.severity.value
            )

            record.category = (
                merged_signal.category.value
            )

            record.title = merged_signal.title
            record.summary = merged_signal.summary
            record.reason = merged_signal.reason
            record.action = merged_signal.action

            record.first_observed_at = (
                merged_signal
                .first_observed_at
                .isoformat()
            )

            record.last_observed_at = (
                merged_signal
                .last_observed_at
                .isoformat()
            )

            record.occurrence_count = (
                merged_signal.occurrence_count
            )

            record.involved_entity_id = (
                merged_signal.involved_entity_id
            )

            record.payload_json = (
                merged_signal.model_dump_json()
            )

            record.updated_at = now

            updated_count += 1

    session.commit()

    return (
        created_count,
        updated_count,
    )


def _record_to_summary(
    record: SignalRecord,
) -> SignalSummary:
    signal = (
        NormalizedSignal
        .model_validate_json(
            record.payload_json
        )
    )

    return SignalSummary(
        signal_id=signal.signal_id,
        signal_type=signal.signal_type,
        severity=signal.severity,
        category=signal.category,
        title=signal.title,
        reason=signal.reason,
        first_observed_at=(
            signal.first_observed_at
        ),
        last_observed_at=(
            signal.last_observed_at
        ),
        temporal=signal.temporal,
        recorded_at=parse_utc(
            record.created_at,
            allow_legacy_naive=True,
        ),
        occurrence_count=(
            signal.occurrence_count
        ),
        cluster_name=(
            signal.cluster_name
        ),
        namespace=signal.namespace,
        topology_snapshot_id=(
           signal.topology_snapshot_id
        ),
        involved_entity_id=(
            signal.involved_entity_id
        ),
        involved_object_kind=(
            signal.involved_object_kind
        ),
        involved_object_name=(
            signal.involved_object_name
        ),
    )


def list_signals(
    session: Session,
    cluster_name: str | None = None,
    namespace: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[SignalSummary]:
    statement = select(
        SignalRecord
    )

    if cluster_name:
        statement = statement.where(
            SignalRecord.cluster_name
            == cluster_name
        )

    if namespace:
        statement = statement.where(
            SignalRecord.namespace
            == namespace
        )

    if severity:
        statement = statement.where(
            SignalRecord.severity
            == severity
        )

    statement = (
        statement
        .order_by(
            SignalRecord
            .last_observed_at
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
        _record_to_summary(record)
        for record in records
    ]

def list_signals_by_incident_fingerprint(
    session: Session,
    cluster_name: str,
    namespace: str | None,
    fingerprint: str,
    limit: int = 200,
) -> list[SignalSummary]:
    statement = select(
        SignalRecord
    ).where(
        SignalRecord.cluster_name
        == cluster_name,
    )

    if namespace:
        statement = statement.where(
            SignalRecord.namespace
            == namespace
        )

    statement = (
        statement
        .order_by(
            SignalRecord
            .last_observed_at
            .desc()
        )
        .limit(limit * 5)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    matched = []

    for record in records:
        signal = (
            NormalizedSignal
            .model_validate_json(
                record.payload_json
            )
        )

        if (
            incident_fingerprint(signal)
            == fingerprint
        ):
            matched.append(
                _record_to_summary(record)
            )

        if len(matched) >= limit:
            break

    return matched
    
def load_signal(
    session: Session,
    signal_id: str,
) -> NormalizedSignal | None:
    record = session.get(
        SignalRecord,
        signal_id,
    )

    if record is None:
        return None

    return (
        NormalizedSignal
        .model_validate_json(
            record.payload_json
        )
    )

def find_signals_after(
    session: Session,
    cluster_name: str,
    namespace: str | None,
    start_at: datetime,
    limit: int = 500,
) -> list[NormalizedSignal]:
    statement = select(
        SignalRecord
    ).where(
        SignalRecord.cluster_name
        == cluster_name,
        SignalRecord.last_observed_at
        >= start_at.isoformat(),
    )

    if namespace:
        statement = statement.where(
            SignalRecord.namespace
            == namespace
        )

    statement = (
        statement
        .order_by(
            SignalRecord
            .last_observed_at
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
        NormalizedSignal
        .model_validate_json(
            record.payload_json
        )
        for record in records
    ]
