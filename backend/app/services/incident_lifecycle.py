from __future__ import annotations

from hashlib import sha256

from sqlalchemy.orm import Session

from app.db.models import (
    IncidentRecord,
    utc_now_iso,
)
from app.models.incident_records import (
    IncidentSeverity,
    IncidentStatus,
)
from app.models.incidents import (
    IncidentAnalysis,
)
from app.models.recommendations import (
    RemediationRecommendation,
)
from app.models.signals import (
    NormalizedSignal,
)
from app.repositories.incident_record_repository import (
    get_incident_by_fingerprint,
)
from app.services.incident_grouping import (
    incident_fingerprint,
    incident_group_label,
)


# def _incident_fingerprint(
#     signal: NormalizedSignal,
# ) -> str:
#     value = "|".join(
#         [
#             signal.cluster_name,
#             signal.namespace or "",
#             signal.category.value,
#             signal.reason or "",
#             signal.involved_entity_id or "",
#             signal.involved_object_kind or "",
#             signal.involved_object_name or "",
#         ]
#     )

#     return sha256(
#         value.encode("utf-8")
#     ).hexdigest()


def _incident_id(
    signal: NormalizedSignal,
    fingerprint: str,
) -> str:
    digest = fingerprint[:24]

    namespace = (
        signal.namespace
        or "cluster"
    )
    subject = (
        incident_group_label(signal)
        .lower()
        .replace("/", "-")
        .replace(" ", "-")
        .replace("_", "-")
    )

    # reason = (
    #     signal.reason
    #     or signal.category.value
    #     or "signal"
    # )

    # safe_reason = (
    #     reason.lower()
    #     .replace(" ", "-")
    #     .replace("_", "-")
    # )

    return (
        "incident:"
        f"{signal.cluster_name}:"
        f"{namespace}:"
        f"{subject}:"
        f"{digest}"
    )


def _severity(
    signal: NormalizedSignal,
) -> IncidentSeverity:
    return IncidentSeverity(
        signal.severity.value
    )


def _title(
    signal: NormalizedSignal,
) -> str:
    object_label = "/".join(
        value
        for value in (
            signal.involved_object_kind,
            signal.involved_object_name,
        )
        if value
    )

    if object_label:
        return (
            f"{signal.reason or signal.title} "
            f"on {object_label}"
        )

    return signal.reason or signal.title


def _summary(
    signal: NormalizedSignal,
) -> str:
    return signal.summary or signal.title


def upsert_incident_from_orchestration(
    session: Session,
    signal: NormalizedSignal,
    analysis: IncidentAnalysis | None,
    recommendations: list[
        RemediationRecommendation
    ],
) -> IncidentRecord:
    fingerprint = incident_fingerprint(
        signal
    )

    now = utc_now_iso()

    existing = get_incident_by_fingerprint(
        session=session,
        fingerprint=fingerprint,
    )

    top_hypothesis = (
        analysis.hypotheses[0]
        if analysis and analysis.hypotheses
        else None
    )

    latest_recommendation = (
        recommendations[0]
        if recommendations
        else None
    )

    if recommendations:
        next_status = (
            IncidentStatus.RECOMMENDED
        )

    elif analysis:
        next_status = (
            IncidentStatus.INVESTIGATING
        )

    else:
        next_status = IncidentStatus.OPEN

    if existing is None:
        record = IncidentRecord(
            incident_id=_incident_id(
                signal=signal,
                fingerprint=fingerprint,
            ),
            fingerprint=fingerprint,
            status=next_status.value,
            severity=_severity(
                signal
            ).value,
            title=_title(signal),
            summary=_summary(signal),
            cluster_name=signal.cluster_name,
            namespace=signal.namespace,
            primary_signal_id=signal.signal_id,
            latest_signal_id=signal.signal_id,
            topology_snapshot_id=(
                signal.topology_snapshot_id
            ),
            affected_entity_id=(
                signal.involved_entity_id
            ),
            affected_object_kind=(
                signal.involved_object_kind
            ),
            affected_object_name=(
                signal.involved_object_name
            ),
            first_observed_at=(
                signal.first_observed_at.isoformat()
            ),
            last_observed_at=(
                signal.last_observed_at.isoformat()
            ),
            latest_analysis_id=(
                analysis.analysis_id
                if analysis
                else None
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
            recommendation_count=len(
                recommendations
            ),
            latest_recommendation_id=(
                latest_recommendation.recommendation_id
                if latest_recommendation
                else None
            ),
            recovery_status=None,
            latest_recovery_verification_id=None,
            occurrence_count=(
                signal.occurrence_count
            ),
            created_at=now,
            updated_at=now,
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        return record

    preserved_terminal_statuses = {
        IncidentStatus.RESOLVED.value,
        IncidentStatus.DISMISSED.value,
    }

    if (
        existing.status
        not in preserved_terminal_statuses
    ):
        existing.status = next_status.value

    existing.severity = _severity(
        signal
    ).value

    existing.title = _title(signal)
    existing.summary = _summary(signal)

    existing.latest_signal_id = (
        signal.signal_id
    )

    existing.topology_snapshot_id = (
        signal.topology_snapshot_id
    )

    existing.affected_entity_id = (
        signal.involved_entity_id
    )

    existing.affected_object_kind = (
        signal.involved_object_kind
    )

    existing.affected_object_name = (
        signal.involved_object_name
    )

    existing.last_observed_at = (
        signal.last_observed_at.isoformat()
    )

    existing.latest_analysis_id = (
        analysis.analysis_id
        if analysis
        else existing.latest_analysis_id
    )

    existing.top_hypothesis_title = (
        top_hypothesis.title
        if top_hypothesis
        else existing.top_hypothesis_title
    )

    existing.top_hypothesis_score = (
        str(top_hypothesis.score)
        if top_hypothesis
        else existing.top_hypothesis_score
    )

    existing.recommendation_count = max(
        existing.recommendation_count,
        len(recommendations),
    )

    existing.latest_recommendation_id = (
        latest_recommendation.recommendation_id
        if latest_recommendation
        else existing.latest_recommendation_id
    )

    existing.occurrence_count = max(
        existing.occurrence_count,
        signal.occurrence_count,
    )

    existing.updated_at = now

    session.commit()
    session.refresh(existing)

    return existing