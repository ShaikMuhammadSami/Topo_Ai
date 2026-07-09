from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from hashlib import sha256

from sqlalchemy.orm import Session

from app.models.orchestration import (
    IncidentOrchestrationResult,
    OrchestrationStatus,
)
from app.models.signals import (
    SignalSeverity,
)
from app.repositories.change_repository import (
    find_changes_in_window,
    load_change,
)
from app.repositories.incident_repository import (
    save_incident_analysis,
)
from app.repositories.recommendation_repository import (
    save_recommendation,
)
from app.repositories.signal_repository import (
    load_signal,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.incident_analysis import (
    analyze_incident,
)
from app.services.recommendation_engine import (
    generate_recommendations,
)
from app.services.incident_lifecycle import (
    upsert_incident_from_orchestration,
)

ORCHESTRATION_VERSION = (
    "incident-orchestration-0.1.0"
)


FAILURE_SEVERITIES = {
    SignalSeverity.WARNING,
    SignalSeverity.ERROR,
    SignalSeverity.CRITICAL,
}


class OrchestrationNotFoundError(
    Exception
):
    pass


class OrchestrationValidationError(
    Exception
):
    pass


def _orchestration_id(
    signal_id: str,
    topology_snapshot_id: str | None,
    lookback_minutes: int,
    grace_minutes: int,
    max_graph_hops: int,
    max_hypotheses: int,
    minimum_recommendation_score: float,
    max_recommendations: int,
) -> str:
    value = "|".join(
        [
            signal_id,
            topology_snapshot_id or "",
            str(lookback_minutes),
            str(grace_minutes),
            str(max_graph_hops),
            str(max_hypotheses),
            (
                f"{minimum_recommendation_score:.4f}"
            ),
            str(max_recommendations),
            ORCHESTRATION_VERSION,
        ]
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return f"orchestration:{digest}"


def orchestrate_signal(
    session: Session,
    signal_id: str,
    lookback_minutes: int = 60,
    grace_minutes: int = 15,
    max_graph_hops: int = 6,
    max_hypotheses: int = 10,
    minimum_recommendation_score: (
        float
    ) = 0.50,
    max_recommendations: int = 3,
    require_failure_severity: (
        bool
    ) = True,
) -> IncidentOrchestrationResult:
    started_at = datetime.now(
        timezone.utc
    )

    signal = load_signal(
        session=session,
        signal_id=signal_id,
    )

    if signal is None:
        raise OrchestrationNotFoundError(
            f"Signal not found: {signal_id}"
        )

    orchestration_id = (
        _orchestration_id(
            signal_id=signal.signal_id,
            topology_snapshot_id=(
                signal
                .topology_snapshot_id
            ),
            lookback_minutes=(
                lookback_minutes
            ),
            grace_minutes=(
                grace_minutes
            ),
            max_graph_hops=(
                max_graph_hops
            ),
            max_hypotheses=(
                max_hypotheses
            ),
            minimum_recommendation_score=(
                minimum_recommendation_score
            ),
            max_recommendations=(
                max_recommendations
            ),
        )
    )

    parameters = {
        "lookback_minutes": (
            lookback_minutes
        ),
        "grace_minutes": (
            grace_minutes
        ),
        "max_graph_hops": (
            max_graph_hops
        ),
        "max_hypotheses": (
            max_hypotheses
        ),
        (
            "minimum_recommendation_score"
        ): (
            minimum_recommendation_score
        ),
        "max_recommendations": (
            max_recommendations
        ),
        "require_failure_severity": (
            require_failure_severity
        ),
    }

    if (
        require_failure_severity
        and signal.severity
        not in FAILURE_SEVERITIES
    ):
        completed_at = datetime.now(
            timezone.utc
        )

        return (
            IncidentOrchestrationResult(
                orchestration_id=(
                    orchestration_id
                ),
                orchestration_version=(
                    ORCHESTRATION_VERSION
                ),
                status=(
                    OrchestrationStatus
                    .SKIPPED
                ),
                message=(
                    "Signal was skipped because "
                    f"severity "
                    f"'{signal.severity.value}' "
                    "does not qualify as a "
                    "failure signal."
                ),
                started_at=started_at,
                completed_at=completed_at,
                signal_id=signal.signal_id,
                signal_severity=(
                    signal.severity.value
                ),
                cluster_name=(
                    signal.cluster_name
                ),
                namespace=(
                    signal.namespace
                ),
                topology_snapshot_id=(
                    signal
                    .topology_snapshot_id
                ),
                parameters=parameters,
            )
        )

    if not signal.topology_snapshot_id:
        raise (
            OrchestrationValidationError(
                "Signal does not contain a "
                "topology_snapshot_id."
            )
        )

    snapshot = load_snapshot(
        session=session,
        snapshot_id=(
            signal.topology_snapshot_id
        ),
    )

    if snapshot is None:
        raise OrchestrationNotFoundError(
            "Topology snapshot referenced by "
            "the signal was not found: "
            f"{signal.topology_snapshot_id}"
        )

    start_at = (
        signal.first_observed_at
        - timedelta(
            minutes=lookback_minutes
        )
    )

    end_at = (
        signal.first_observed_at
        + timedelta(
            minutes=grace_minutes
        )
    )

    candidate_changes = (
        find_changes_in_window(
            session=session,
            cluster_name=(
                signal.cluster_name
            ),
            namespace=(
                signal.namespace
            ),
            start_at=start_at,
            end_at=end_at,
            limit=500,
        )
    )

    analysis = analyze_incident(
        signal=signal,
        snapshot=snapshot,
        candidate_changes=(
            candidate_changes
        ),
        lookback_minutes=(
            lookback_minutes
        ),
        grace_minutes=(
            grace_minutes
        ),
        max_graph_hops=(
            max_graph_hops
        ),
        max_hypotheses=(
            max_hypotheses
        ),
    )

    save_incident_analysis(
        session=session,
        analysis=analysis,
    )

    changes_by_id = {}

    for hypothesis in (
        analysis.hypotheses
    ):
        change = load_change(
            session=session,
            change_id=(
                hypothesis.change_id
            ),
        )

        if change is not None:
            changes_by_id[
                change.change_id
            ] = change

    recommendations = (
        generate_recommendations(
            analysis=analysis,
            signal=signal,
            snapshot=snapshot,
            changes_by_id=(
                changes_by_id
            ),
            minimum_score=(
                minimum_recommendation_score
            ),
            max_recommendations=(
                max_recommendations
            ),
        )
    )

    for recommendation in (
        recommendations
    ):
        save_recommendation(
            session=session,
            recommendation=(
                recommendation
            ),
        )
    
    incident_record = (
     upsert_incident_from_orchestration(
          session=session,
          signal=signal,
          analysis=analysis,
          recommendations=recommendations,
        )
    )
    warnings = list(
        analysis.warnings
    )

    if not candidate_changes:
        warnings.append(
            "No persisted topology changes "
            "were found inside the configured "
            "analysis window."
        )

    elif not analysis.hypotheses:
        warnings.append(
            "Candidate changes were found, but "
            "no ranked hypotheses were produced."
        )

    if (
        analysis.hypotheses
        and not recommendations
    ):
        warnings.append(
            "Hypotheses were produced, but none "
            "met the recommendation confidence "
            "threshold."
        )

    top_hypothesis = (
        analysis.hypotheses[0]
        if analysis.hypotheses
        else None
    )

    completed_at = datetime.now(
        timezone.utc
    )

    return IncidentOrchestrationResult(
        orchestration_id=(
            orchestration_id
        ),
        orchestration_version=(
            ORCHESTRATION_VERSION
        ),
        status=(
            OrchestrationStatus.COMPLETED
        ),
        message=(
            "Incident orchestration completed."
        ),
        started_at=started_at,
        completed_at=completed_at,
        signal_id=signal.signal_id,
        signal_severity=(
            signal.severity.value
        ),
        cluster_name=(
            signal.cluster_name
        ),
        namespace=signal.namespace,
        topology_snapshot_id=(
            snapshot.snapshot_id
        ),
        analysis_id=(
            analysis.analysis_id
        ),
        incident_id=(
          incident_record.incident_id
        ),
        candidate_count=(
            analysis.candidate_count
        ),
        hypothesis_count=len(
            analysis.hypotheses
        ),
        top_hypothesis_id=(
            top_hypothesis.hypothesis_id
            if top_hypothesis
            else None
        ),
        top_hypothesis_title=(
            top_hypothesis.title
            if top_hypothesis
            else None
        ),
        top_hypothesis_score=(
            top_hypothesis.score
            if top_hypothesis
            else None
        ),
        recommendation_count=len(
            recommendations
        ),
        recommendation_ids=[
            recommendation
            .recommendation_id
            for recommendation
            in recommendations
        ],
        warnings=warnings,
        parameters=parameters,

    )