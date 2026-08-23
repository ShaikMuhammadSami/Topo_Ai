from __future__ import annotations

import json
import math
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeEntityLinkRecord,
    ChangeEventRecord,
    IncidentRecord,
    SnapshotRecord,
)
from app.models.change_events import (
    IncidentChangeAnalysisResponse,
    IncidentChangeCandidate,
)
from app.models.topology import (
    GraphSnapshot,
)
from app.repositories.change_event_repository import (
    change_event_view,
)
from app.services.canonical_identity import (
    resolve_snapshot_entity_identity,
    resolved_snapshot_entity,
)


def _parse_time(
    value: str,
) -> datetime:
    result = datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result


def _metadata(
    incident: IncidentRecord,
) -> dict:
    raw = getattr(
        incident,
        "metadata_json",
        "{}",
    )

    if isinstance(raw, dict):
        return raw

    try:
        value = json.loads(
            raw or "{}"
        )

        return (
            value
            if isinstance(value, dict)
            else {}
        )

    except json.JSONDecodeError:
        return {}


def _incident_time(
    incident: IncidentRecord,
) -> str:
    for field_name in (
        "first_observed_at",
        "started_at",
        "detected_at",
        "occurred_at",
        "created_at",
    ):
        value = getattr(
            incident,
            field_name,
            None,
        )

        if value:
            return str(value)

    metadata = _metadata(
        incident
    )

    for key in (
        "started_at",
        "detected_at",
        "occurred_at",
    ):
        value = metadata.get(key)

        if value:
            return str(value)

    raise ValueError(
        "Incident does not have "
        "a usable occurrence time."
    )


def _affected_entities(
    incident: IncidentRecord,
) -> set[str]:
    result: set[str] = set()

    for field_name in (
        "entity_id",
        "root_entity_id",
        "affected_entity_id",
        "primary_entity_id",
    ):
        value = getattr(
            incident,
            field_name,
            None,
        )

        if value:
            result.add(str(value))

    metadata = _metadata(
        incident
    )

    for key in (
        "entity_id",
        "root_entity_id",
        "affected_entity_id",
    ):
        value = metadata.get(key)

        if value:
            result.add(str(value))

    for key in (
        "entity_ids",
        "affected_entity_ids",
        "blast_radius_entity_ids",
    ):
        values = metadata.get(
            key,
            [],
        )

        if isinstance(values, list):
            result.update(
                str(item)
                for item in values
                if item
            )

    return result


def _incident_cluster(
    incident: IncidentRecord,
) -> str | None:
    value = getattr(
        incident,
        "cluster_name",
        None,
    )

    if value:
        return str(value)

    value = _metadata(
        incident
    ).get(
        "cluster_name"
    )

    return (
        str(value)
        if value
        else None
    )


def _incident_namespace(
    incident: IncidentRecord,
) -> str | None:
    value = getattr(
        incident,
        "namespace",
        None,
    )

    if value:
        return str(value)

    value = _metadata(
        incident
    ).get(
        "namespace"
    )

    return (
        str(value)
        if value
        else None
    )


def _snapshot_for_incident(
    session: Session,
    incident: IncidentRecord,
) -> GraphSnapshot | None:
    for field_name in (
        "snapshot_id",
        "topology_snapshot_id",
    ):
        value = getattr(
            incident,
            field_name,
            None,
        )

        if value:
            record = session.get(
                SnapshotRecord,
                str(value),
            )

            if record:
                return (
                    GraphSnapshot
                    .model_validate_json(
                        record.payload_json
                    )
                )

    statement = select(
        SnapshotRecord
    )

    cluster = _incident_cluster(
        incident
    )

    if cluster:
        statement = statement.where(
            SnapshotRecord.cluster_name
            == cluster
        )

    statement = (
        statement
        .order_by(
            SnapshotRecord
            .collected_at
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
        GraphSnapshot
        .model_validate_json(
            record.payload_json
        )
    )


def _neighbors(
    snapshot: GraphSnapshot | None,
    affected: set[str],
) -> set[str]:
    if snapshot is None:
        return set()

    result: set[str] = set()

    for relationship in (
        snapshot.relationships
    ):
        if (
            relationship
            .source_entity_id
            in affected
        ):
            result.add(
                relationship
                .target_entity_id
            )

        if (
            relationship
            .target_entity_id
            in affected
        ):
            result.add(
                relationship
                .source_entity_id
            )

    return result - affected


def analyze_incident_change_events(
    session: Session,
    *,
    incident_id: str,
    lookback_minutes: int = 120,
    after_minutes: int = 10,
    minimum_score: float = 0,
    limit: int = 100,
) -> IncidentChangeAnalysisResponse:
    incident = session.get(
        IncidentRecord,
        incident_id,
    )

    if incident is None:
        raise ValueError(
            "Incident not found."
        )

    incident_time_value = (
        _incident_time(
            incident
        )
    )

    incident_time = _parse_time(
        incident_time_value
    )

    start = (
        incident_time
        - timedelta(
            minutes=lookback_minutes
        )
    )

    end = (
        incident_time
        + timedelta(
            minutes=after_minutes
        )
    )

    statement = (
        select(ChangeEventRecord)
        .where(
            ChangeEventRecord.occurred_at
            >= start.isoformat(),
            ChangeEventRecord.occurred_at
            <= end.isoformat(),
        )
        .order_by(
            ChangeEventRecord
            .occurred_at
            .desc()
        )
        .limit(2000)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    affected = _affected_entities(
        incident
    )

    snapshot = (
        _snapshot_for_incident(
            session,
            incident,
        )
    )

    if snapshot is not None:
        resolved_affected: set[str] = set()
        for entity_reference in sorted(affected):
            resolution = resolve_snapshot_entity_identity(
                snapshot,
                identifier=entity_reference,
            )
            entity = resolved_snapshot_entity(
                snapshot,
                resolution,
            )
            resolved_affected.add(
                entity.id
                if entity is not None
                else entity_reference
            )
        affected = resolved_affected

    neighbors = _neighbors(
        snapshot,
        affected,
    )

    incident_cluster = str(
        _incident_cluster(
            incident
        )
        or ""
    ).lower()

    incident_namespace = str(
        _incident_namespace(
            incident
        )
        or ""
    ).lower()

    incident_environment = str(
        getattr(
            incident,
            "environment",
            None,
        )
        or _metadata(
            incident
        ).get(
            "environment"
        )
        or ""
    ).lower()

    candidates = []

    for record in records:
        change_time = _parse_time(
            record.occurred_at
        )

        minutes_before = (
            incident_time
            - change_time
        ).total_seconds() / 60

        # 40 points:
        # strongest near incident.
        if minutes_before >= 0:
            time_score = (
                40
                * math.exp(
                    -minutes_before
                    / 60
                )
            )

        else:
            # Post-incident changes should
            # score very little.
            time_score = max(
                0,
                5
                - abs(
                    minutes_before
                ),
            )

        links = list(
            session.scalars(
                select(
                    ChangeEntityLinkRecord
                ).where(
                    ChangeEntityLinkRecord
                    .event_id
                    == record.event_id
                )
            ).all()
        )

        linked_ids = {
            link.entity_id
            for link in links
        }

        direct = sorted(
            linked_ids & affected
        )

        neighboring = sorted(
            linked_ids & neighbors
        )

        entity_score = 0.0

        reasons = []

        if direct:
            entity_score = 35

            reasons.append(
                "Change event is directly "
                "linked to an affected "
                "incident entity."
            )

        elif neighboring:
            entity_score = 20

            reasons.append(
                "Change event is linked "
                "to a one-hop dependency "
                "of an affected entity."
            )

        scope_score = 0.0

        if (
            incident_environment
            and str(
                record.environment or ""
            ).lower()
            == incident_environment
        ):
            scope_score += 4

            reasons.append(
                "Same environment."
            )

        if (
            incident_cluster
            and str(
                record.cluster_name or ""
            ).lower()
            == incident_cluster
        ):
            scope_score += 4

            reasons.append(
                "Same cluster."
            )

        if (
            incident_namespace
            and str(
                record.namespace or ""
            ).lower()
            == incident_namespace
        ):
            scope_score += 4

            reasons.append(
                "Same namespace."
            )

        risk_score = (
            record.risk_score
            * 0.09
        )

        total = min(
            100,
            time_score
            + entity_score
            + scope_score
            + risk_score,
        )

        if total < minimum_score:
            continue

        if minutes_before >= 0:
            reasons.append(
                (
                    f"Change occurred "
                    f"{minutes_before:.1f} "
                    "minutes before the "
                    "incident."
                )
            )

        else:
            reasons.append(
                (
                    "Change occurred "
                    f"{abs(minutes_before):.1f} "
                    "minutes after incident "
                    "start."
                )
            )

        candidates.append(
            IncidentChangeCandidate(
                event=change_event_view(
                    session,
                    record=record,
                ),
                score=round(
                    total,
                    2,
                ),
                reasons=reasons,
                direct_entity_matches=(
                    direct
                ),
                neighboring_entity_matches=(
                    neighboring
                ),
                minutes_before_incident=(
                    round(
                        minutes_before,
                        2,
                    )
                ),
            )
        )

    candidates.sort(
        key=lambda item: (
            item.score,
            item.event.risk_score,
            item.event.occurred_at,
        ),
        reverse=True,
    )

    candidates = candidates[
        :limit
    ]

    return (
        IncidentChangeAnalysisResponse(
            incident_id=incident_id,
            incident_time=(
                incident_time_value
            ),
            lookback_minutes=(
                lookback_minutes
            ),
            after_minutes=(
                after_minutes
            ),
            affected_entity_ids=(
                sorted(affected)
            ),
            candidate_count=len(
                candidates
            ),
            candidates=candidates,
        )
    )
