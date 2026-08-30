from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_predicate,
    tenant_get,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeEventRecord,
    IncidentRecord,
    SignalRecord,
    SnapshotRecord,
)
from app.models.lifecycle_automation import (
    AutomaticAnalysisState,
    IncidentLifecycleStatusResponse,
    LifecycleStatusResponse,
    TopologyCheckpointReason,
)
from app.models.topology import GraphSnapshot
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
)
from app.services.continuous_lifecycle import (
    INCIDENT_CORRELATION_WINDOW_MINUTES,
)
from app.services.topology_checkpoint import (
    CHECKPOINT_DEBOUNCE_SECONDS,
    checkpoint_metadata,
)


def _latest(
    session: Session,
    model,
    order_by,
    *,
    cluster_name: str | None,
    tenant_id: DomainTenant,
):
    statement = select(model).where(tenant_predicate(model, tenant_id))

    if cluster_name and hasattr(
        model,
        "cluster_name",
    ):
        statement = statement.where(
            model.cluster_name == cluster_name
        )

    return session.scalar(
        statement.order_by(
            order_by.desc().nulls_last()
        ).limit(1)
    )


def build_lifecycle_status(
    session: Session,
    *,
    cluster_name: str | None = None,
    tenant_id: DomainTenant,
) -> LifecycleStatusResponse:
    snapshot_record = _latest(
        session,
        SnapshotRecord,
        SnapshotRecord.collected_at,
        cluster_name=cluster_name,
        tenant_id=tenant_id,
    )
    change = _latest(
        session,
        ChangeEventRecord,
        ChangeEventRecord.received_at,
        cluster_name=cluster_name,
        tenant_id=tenant_id,
    )
    signal_statement = (
        select(SignalRecord)
        .where(tenant_predicate(SignalRecord, tenant_id))
        .where(SignalRecord.severity != "info")
    )

    if cluster_name:
        signal_statement = signal_statement.where(
            SignalRecord.cluster_name
            == cluster_name
        )

    signal = session.scalar(
        signal_statement.order_by(
            SignalRecord.last_observed_at.desc()
        ).limit(1)
    )
    incident = _latest(
        session,
        IncidentRecord,
        IncidentRecord.last_observed_at,
        cluster_name=cluster_name,
        tenant_id=tenant_id,
    )
    reason = None

    if snapshot_record is not None:
        snapshot = (
            GraphSnapshot.model_validate_json(
                snapshot_record.payload_json
            )
        )
        raw_reason = checkpoint_metadata(
            snapshot
        ).get("reason")

        try:
            reason = (
                TopologyCheckpointReason(
                    raw_reason
                )
                if raw_reason
                else None
            )

        except ValueError:
            reason = None

    analysis_state = None

    if incident is not None:
        analysis = latest_causal_analysis(
            session,
            incident_id=incident.incident_id,
            tenant_id=tenant_id,
        )

        if analysis is not None:
            analysis_state = (
                AutomaticAnalysisState.COMPLETED
                if analysis.top_hypothesis
                is not None
                else AutomaticAnalysisState
                .COMPLETED_NO_HYPOTHESIS
            )

        elif not incident.topology_snapshot_id:
            analysis_state = (
                AutomaticAnalysisState
                .PENDING_TOPOLOGY
            )

        elif not incident.affected_entity_id:
            analysis_state = (
                AutomaticAnalysisState
                .PENDING_ENTITY
            )

        else:
            analysis_state = (
                AutomaticAnalysisState
                .PENDING_ANALYSIS
            )

    return LifecycleStatusResponse(
        cluster_name=cluster_name,
        last_successful_discovery_at=(
            snapshot_record.collected_at if snapshot_record is not None else None
        ),
        last_topology_checkpoint_id=(
            snapshot_record.snapshot_id if snapshot_record is not None else None
        ),
        last_topology_checkpoint_at=(
            snapshot_record.collected_at if snapshot_record is not None else None
        ),
        last_topology_checkpoint_reason=reason,
        latest_change_event_id=(change.event_id if change is not None else None),
        latest_change_event_at=(change.received_at if change is not None else None),
        latest_failure_signal_id=(signal.signal_id if signal is not None else None),
        latest_failure_signal_at=(
            signal.last_observed_at if signal is not None else None
        ),
        latest_incident_id=(incident.incident_id if incident is not None else None),
        latest_incident_correlation=(
            ("correlated" if incident.occurrence_count > 1 else "created")
            if incident is not None
            else None
        ),
        automatic_analysis_state=analysis_state,
        checkpoint_debounce_seconds=(CHECKPOINT_DEBOUNCE_SECONDS),
        incident_correlation_window_minutes=(INCIDENT_CORRELATION_WINDOW_MINUTES),
    )


def build_incident_lifecycle_status(
    session: Session,
    *,
    incident_id: str,
    tenant_id: DomainTenant,
) -> IncidentLifecycleStatusResponse:
    incident = tenant_get(
        session,
        IncidentRecord,
        incident_id,
        tenant_id=tenant_id,
    )

    if incident is None:
        raise ValueError(
            f"Incident not found: {incident_id}"
        )

    analysis = latest_causal_analysis(
        session,
        incident_id=incident_id,
        tenant_id=tenant_id,
    )

    if analysis is not None:
        if analysis.top_hypothesis is not None:
            state = AutomaticAnalysisState.COMPLETED
            message = (
                "Topo completed the causal investigation "
                "and the incident briefing is available."
            )
            briefing_ready = True
        else:
            state = (
                AutomaticAnalysisState
                .COMPLETED_NO_HYPOTHESIS
            )
            message = (
                "Topo completed the investigation but has "
                "not identified a supported root cause yet."
            )
            briefing_ready = False

    elif not incident.topology_snapshot_id:
        state = AutomaticAnalysisState.PENDING_TOPOLOGY
        message = (
            "Topo detected the incident and is waiting for "
            "a historically safe incident-time topology "
            "checkpoint."
        )
        briefing_ready = False

    elif not incident.affected_entity_id:
        state = AutomaticAnalysisState.PENDING_ENTITY
        message = (
            "Topo pinned the incident-time topology and is "
            "resolving the affected infrastructure entity."
        )
        briefing_ready = False

    else:
        state = AutomaticAnalysisState.PENDING_ANALYSIS
        message = (
            "Topo pinned the affected infrastructure and "
            "is investigating this incident."
        )
        briefing_ready = False

    return IncidentLifecycleStatusResponse(
        incident_id=incident_id,
        automatic_analysis_state=state,
        topology_snapshot_id=(
            incident.topology_snapshot_id
        ),
        affected_entity_id=(
            incident.affected_entity_id
        ),
        causal_analysis_id=(
            analysis.analysis_id
            if analysis is not None
            else None
        ),
        briefing_ready=briefing_ready,
        retryable=state in {
            AutomaticAnalysisState.PENDING_TOPOLOGY,
            AutomaticAnalysisState.PENDING_ENTITY,
            AutomaticAnalysisState.PENDING_ANALYSIS,
        },
        message=message,
    )
