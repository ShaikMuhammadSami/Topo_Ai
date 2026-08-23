from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import IncidentRecord
from app.models.causal_rca import (
    CausalAnalysisRequest,
)
from app.models.incident_records import (
    IncidentStatus,
)
from app.models.lifecycle_automation import (
    AutomaticAnalysisState,
    AutomaticIncidentAction,
    AutomaticIncidentResult,
    FailureSignalBatchResult,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.topology import GraphSnapshot
from app.models.temporal import (
    TemporalMetadata,
    TemporalStatus,
    TimeOrigin,
    TimeQuality,
)
from app.models.webhooks import WebhookEventType
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
)
from app.repositories.incident_record_repository import (
    find_correlatable_incident,
)
from app.repositories.signal_repository import (
    load_signal,
    save_signals,
)
from app.repositories.snapshot_repository import (
    load_snapshot,
)
from app.services.causal_rca import analyze_causal_rca
from app.services.incident_grouping import (
    incident_fingerprint,
    is_failure_signal,
)
from app.services.incident_lifecycle import (
    upsert_incident_from_orchestration,
)
from app.services.topology_checkpoint import (
    checkpoint_metadata,
    latest_checkpoint_at_or_before,
)
from app.services.canonical_identity import (
    resolve_snapshot_entity_identity,
    resolved_snapshot_entity,
)
from app.services.webhook_delivery import (
    build_webhook_event,
    publish_event_safely,
)


INCIDENT_CORRELATION_WINDOW_MINUTES = max(
    int(
        os.getenv(
            "TOPO_INCIDENT_CORRELATION_WINDOW_MINUTES",
            "120",
        )
    ),
    1,
)


SUPPORTED_KUBERNETES_FAILURE_REASONS = {
    "BackOff",
    "CrashLoopBackOff",
    "ErrImagePull",
    "ImagePullBackOff",
    "Failed",
    "FailedScheduling",
    "FailedMount",
    "FailedAttachVolume",
    "FailedCreate",
    "Unhealthy",
}


def _digest(*parts: object) -> str:
    value = "|".join(
        str(part) for part in parts
    )
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _namespace_for_entity(entity) -> str | None:
    value = entity.properties.get("namespace")
    return str(value) if value else None


def _entity_for_signal(
    snapshot: GraphSnapshot,
    signal: NormalizedSignal,
):
    resolution = resolve_snapshot_entity_identity(
        snapshot,
        identifier=signal.involved_entity_id,
        source_native_id=signal.involved_object_uid,
        source_system=signal.source_system,
        kind=signal.involved_object_kind,
        name=signal.involved_object_name,
        cluster_name=signal.cluster_name,
        namespace=signal.namespace,
    )
    return resolved_snapshot_entity(
        snapshot,
        resolution,
    )


def _snapshot_matches_signal_scope(
    snapshot: GraphSnapshot,
    signal: NormalizedSignal,
) -> bool:
    snapshot_cluster = snapshot.scope.get("cluster")

    if (
        snapshot_cluster
        and snapshot_cluster != signal.cluster_name
    ):
        return False

    snapshot_namespace = snapshot.scope.get(
        "namespace"
    )

    return not (
        signal.namespace
        and snapshot_namespace
        not in (None, "*", signal.namespace)
    )


def _is_safe_incident_snapshot(
    snapshot: GraphSnapshot,
    signal: NormalizedSignal,
) -> bool:
    """
    A checkpoint is incident-time evidence only when it
    predates the observation or explicitly records that it
    was captured for this exact failure signal.
    """

    if snapshot.collected_at <= signal.first_observed_at:
        return True

    checkpoint = checkpoint_metadata(snapshot)

    return (
        checkpoint.get("reason") == "incident_boundary"
        and signal.signal_id
        in checkpoint.get("trigger_signal_ids", [])
    )


def bind_signal_to_incident_topology(
    session: Session,
    signal: NormalizedSignal,
) -> tuple[NormalizedSignal, list[str]]:
    warnings: list[str] = []
    snapshot = None

    if signal.topology_snapshot_id:
        snapshot = load_snapshot(
            session,
            signal.topology_snapshot_id,
        )

        if snapshot is None:
            warnings.append(
                "The failure signal referenced a topology "
                "snapshot that does not exist; Topo did not "
                "substitute a newer snapshot."
            )

            return (
                signal.model_copy(
                    update={
                        "topology_snapshot_id": None,
                        "involved_entity_id": None,
                    }
                ),
                warnings,
            )

        if not _snapshot_matches_signal_scope(
            snapshot,
            signal,
        ):
            warnings.append(
                "The failure signal referenced a topology "
                "snapshot outside its cluster or namespace "
                "scope; Topo did not substitute another "
                "snapshot."
            )

            return (
                signal.model_copy(
                    update={
                        "topology_snapshot_id": None,
                        "involved_entity_id": None,
                    }
                ),
                warnings,
            )

        if not _is_safe_incident_snapshot(
            snapshot,
            signal,
        ):
            warnings.append(
                "The failure signal referenced a topology "
                "snapshot collected after the failure with "
                "no exact incident-boundary association; "
                "Topo did not use it."
            )

            return (
                signal.model_copy(
                    update={
                        "topology_snapshot_id": None,
                        "involved_entity_id": None,
                    }
                ),
                warnings,
            )
    else:
        snapshot = latest_checkpoint_at_or_before(
            session,
            cluster_name=signal.cluster_name,
            namespace=signal.namespace,
            observed_at=(
                signal.first_observed_at.isoformat()
            ),
        )

        if snapshot is None:
            warnings.append(
                "No topology checkpoint at or before the "
                "failure was available. The incident can be "
                "recorded, but automatic RCA remains pending."
            )

            return signal, warnings

    entity = _entity_for_signal(
        snapshot,
        signal,
    )

    if entity is None:
        warnings.append(
            "The incident-time topology is available, but "
            "the failure object could not be resolved by "
            "entity ID, Kubernetes UID, or exact scoped "
            "kind/name identity."
        )

    return (
        signal.model_copy(
            update={
                "topology_snapshot_id": (
                    snapshot.snapshot_id
                ),
                "involved_entity_id": (
                    entity.id
                    if entity is not None
                    else signal.involved_entity_id
                ),
            }
        ),
        warnings,
    )


def _container_failure_reasons(
    properties: dict[str, Any],
) -> set[str]:
    reasons: set[str] = set()
    containers = (
        properties.get("container_statuses")
        or properties.get("containers")
        or []
    )

    if not isinstance(containers, list):
        return reasons

    for container in containers:
        if not isinstance(container, dict):
            continue

        candidates = [
            container.get("waiting_reason"),
            container.get("terminated_reason"),
            container.get("reason"),
        ]
        state = container.get("state")

        if isinstance(state, dict):
            waiting = state.get("waiting")

            if isinstance(waiting, dict):
                candidates.append(
                    waiting.get("reason")
                )

            terminated = state.get("terminated")

            if isinstance(terminated, dict):
                candidates.append(
                    terminated.get("reason")
                )

        for candidate in candidates:
            if candidate in (
                SUPPORTED_KUBERNETES_FAILURE_REASONS
            ):
                reasons.add(str(candidate))

    return reasons


def failure_signals_from_snapshot(
    snapshot: GraphSnapshot,
) -> list[NormalizedSignal]:
    """
    Derive only explicit supported Kubernetes failure
    states. Healthy rollouts, scaling, and ordinary
    topology changes never become incidents here.
    """

    cluster_name = (
        snapshot.scope.get("cluster")
        or "unknown"
    )
    signals: list[NormalizedSignal] = []

    for entity in snapshot.entities:
        if entity.kind != "KubernetesPod":
            continue

        reasons = _container_failure_reasons(
            entity.properties
        )
        phase = str(
            entity.properties.get("phase")
            or ""
        )

        if phase in {"Failed", "Unknown"}:
            reasons.add("Failed")

        for reason in sorted(reasons):
            namespace = _namespace_for_entity(
                entity
            )
            fingerprint = _digest(
                cluster_name,
                namespace or "",
                entity.external_id or entity.id,
                reason,
            )
            signal_id = (
                "signal:kubernetes-state:"
                + fingerprint[:32]
            )
            category = (
                SignalCategory.IMAGE
                if "Image" in reason
                or "Pull" in reason
                else SignalCategory.HEALTH
            )

            signals.append(
                NormalizedSignal(
                    signal_id=signal_id,
                    fingerprint=fingerprint,
                    signal_type=(
                        SignalType.KUBERNETES_EVENT
                    ),
                    severity=SignalSeverity.ERROR,
                    category=category,
                    source_system="kubernetes",
                    title=(
                        f"{reason} on KubernetesPod/"
                        f"{entity.name}"
                    ),
                    summary=(
                        "Topo observed explicit Kubernetes "
                        f"failure state {reason} on pod "
                        f"{entity.name}."
                    ),
                    reason=reason,
                    first_observed_at=(
                        snapshot.collected_at
                    ),
                    last_observed_at=(
                        snapshot.collected_at
                    ),
                    temporal=TemporalMetadata(
                        effective_at=snapshot.collected_at,
                        observed_at=snapshot.collected_at,
                        time_origin=TimeOrigin.TOPO_OBSERVED,
                        time_quality=TimeQuality.BOUNDED,
                        source_field="GraphSnapshot.collected_at",
                        source_time_authoritative=False,
                        status=TemporalStatus.PARTIAL,
                    ),
                    occurrence_count=1,
                    cluster_name=cluster_name,
                    namespace=namespace,
                    topology_snapshot_id=(
                        snapshot.snapshot_id
                    ),
                    involved_entity_id=entity.id,
                    involved_object_uid=(
                        entity.external_id
                    ),
                    involved_object_kind="Pod",
                    involved_object_name=entity.name,
                    attributes={
                        "observation_source": (
                            "topology_checkpoint"
                        ),
                        "checkpoint_snapshot_id": (
                            snapshot.snapshot_id
                        ),
                    },
                    raw_payload={},
                )
            )

    return signals


def _publish_incident_created(
    session: Session,
    incident: IncidentRecord,
) -> None:
    event = build_webhook_event(
        event_type=(
            WebhookEventType.INCIDENT_CREATED
        ),
        resource_type="incident",
        resource_id=incident.incident_id,
        summary=(
            "Topo AI automatically created incident "
            f"{incident.title}."
        ),
        severity=incident.severity,
        dedupe_key=incident.incident_id,
        payload={
            "incident_id": incident.incident_id,
            "status": incident.status,
            "severity": incident.severity,
            "cluster_name": incident.cluster_name,
            "namespace": incident.namespace,
            "topology_snapshot_id": (
                incident.topology_snapshot_id
            ),
            "automatic": True,
        },
    )

    publish_event_safely(
        session=session,
        event=event,
    )


def _attach_causal_analysis(
    session: Session,
    *,
    incident: IncidentRecord,
    analysis,
) -> None:
    top = analysis.top_hypothesis

    incident.latest_analysis_id = (
        analysis.analysis_id
    )
    incident.top_hypothesis_title = (
        top.root_title if top else None
    )
    incident.top_hypothesis_score = (
        str(top.confidence)
        if top is not None
        else None
    )
    incident.status = (
        IncidentStatus.INVESTIGATING.value
    )
    session.commit()
    session.refresh(incident)


def _complete_automatic_analysis(
    session: Session,
    *,
    incident: IncidentRecord,
    signal_id: str,
    created: bool,
    warnings: list[str],
) -> AutomaticIncidentResult:
    action = (
        AutomaticIncidentAction.CREATED
        if created
        else AutomaticIncidentAction.CORRELATED
    )

    if not incident.topology_snapshot_id:
        return AutomaticIncidentResult(
            signal_id=signal_id,
            action=AutomaticIncidentAction.DEGRADED,
            incident_id=incident.incident_id,
            incident_created=created,
            incident_correlated=not created,
            automatic_analysis_state=(
                AutomaticAnalysisState.PENDING_TOPOLOGY
            ),
            warnings=warnings,
        )

    if not incident.affected_entity_id:
        return AutomaticIncidentResult(
            signal_id=signal_id,
            action=AutomaticIncidentAction.DEGRADED,
            incident_id=incident.incident_id,
            incident_created=created,
            incident_correlated=not created,
            topology_snapshot_id=(
                incident.topology_snapshot_id
            ),
            automatic_analysis_state=(
                AutomaticAnalysisState.PENDING_ENTITY
            ),
            warnings=warnings,
        )

    existing_analysis = latest_causal_analysis(
        session,
        incident_id=incident.incident_id,
    )

    if existing_analysis is not None:
        return AutomaticIncidentResult(
            signal_id=signal_id,
            action=action,
            incident_id=incident.incident_id,
            incident_created=created,
            incident_correlated=not created,
            topology_snapshot_id=(
                incident.topology_snapshot_id
            ),
            causal_analysis_id=(
                existing_analysis.analysis_id
            ),
            automatic_analysis_state=(
                AutomaticAnalysisState.REUSED
            ),
            warnings=warnings,
        )

    try:
        analysis = analyze_causal_rca(
            session,
            incident_id=incident.incident_id,
            request=CausalAnalysisRequest(),
            persist=True,
        )
        _attach_causal_analysis(
            session,
            incident=incident,
            analysis=analysis,
        )
        analysis_state = (
            AutomaticAnalysisState.COMPLETED
            if analysis.top_hypothesis is not None
            else AutomaticAnalysisState
            .COMPLETED_NO_HYPOTHESIS
        )

        if analysis.top_hypothesis is None:
            warnings.append(
                "Automatic causal analysis completed, "
                "but current evidence did not produce a "
                "ranked causal hypothesis."
            )

        return AutomaticIncidentResult(
            signal_id=signal_id,
            action=action,
            incident_id=incident.incident_id,
            incident_created=created,
            incident_correlated=not created,
            topology_snapshot_id=(
                incident.topology_snapshot_id
            ),
            causal_analysis_id=analysis.analysis_id,
            automatic_analysis_state=analysis_state,
            warnings=warnings,
        )

    except Exception as exc:
        warnings.append(
            "Automatic causal analysis failed; the "
            "incident and pinned topology were preserved: "
            f"{type(exc).__name__}: {exc}"
        )

        return AutomaticIncidentResult(
            signal_id=signal_id,
            action=AutomaticIncidentAction.DEGRADED,
            incident_id=incident.incident_id,
            incident_created=created,
            incident_correlated=not created,
            topology_snapshot_id=(
                incident.topology_snapshot_id
            ),
            automatic_analysis_state=(
                AutomaticAnalysisState.FAILED
            ),
            warnings=warnings,
        )


def process_failure_signal(
    session: Session,
    *,
    signal: NormalizedSignal,
    initial_warnings: list[str] | None = None,
) -> AutomaticIncidentResult:
    warnings = list(initial_warnings or [])

    if not is_failure_signal(signal):
        return AutomaticIncidentResult(
            signal_id=signal.signal_id,
            action=AutomaticIncidentAction.IGNORED,
            automatic_analysis_state=(
                AutomaticAnalysisState.NOT_REQUIRED
            ),
        )

    fingerprint = incident_fingerprint(signal)
    existing = find_correlatable_incident(
        session,
        fingerprint=fingerprint,
        observed_after=(
            signal.first_observed_at
            - timedelta(
                minutes=(
                    INCIDENT_CORRELATION_WINDOW_MINUTES
                )
            )
        ),
        replay_at=signal.last_observed_at,
    )
    incident = upsert_incident_from_orchestration(
        session=session,
        signal=signal,
        analysis=None,
        recommendations=[],
        correlation_window_minutes=(
            INCIDENT_CORRELATION_WINDOW_MINUTES
        ),
    )
    created = existing is None

    if created:
        _publish_incident_created(
            session,
            incident,
        )

    return _complete_automatic_analysis(
        session,
        incident=incident,
        signal_id=signal.signal_id,
        created=created,
        warnings=warnings,
    )


def reconcile_pending_incidents_for_checkpoint(
    session: Session,
    *,
    snapshot_id: str,
    limit: int = 100,
) -> list[AutomaticIncidentResult]:
    """
    Complete only incidents for which this checkpoint is
    historically safe. This never searches for or adopts
    the newest topology snapshot.
    """

    snapshot = load_snapshot(session, snapshot_id)

    if snapshot is None:
        return []

    statement = (
        select(IncidentRecord)
        .where(
            IncidentRecord.status.in_(
                [
                    IncidentStatus.OPEN.value,
                    IncidentStatus.INVESTIGATING.value,
                    IncidentStatus.RECOMMENDED.value,
                    IncidentStatus.REMEDIATING.value,
                ]
            ),
            or_(
                IncidentRecord.topology_snapshot_id
                .is_(None),
                IncidentRecord.affected_entity_id
                .is_(None),
            ),
        )
        .order_by(IncidentRecord.created_at.asc())
        .limit(max(1, min(limit, 500)))
    )
    incidents = list(
        session.scalars(statement).all()
    )
    results: list[AutomaticIncidentResult] = []

    for incident in incidents:
        if (
            incident.topology_snapshot_id
            and incident.topology_snapshot_id
            != snapshot_id
        ):
            # Once pinned, an incident never moves. A
            # missing entity can only be resolved against
            # that same immutable topology.
            continue

        signal_ids = list(
            dict.fromkeys(
                value
                for value in (
                    incident.primary_signal_id,
                    incident.latest_signal_id,
                )
                if value
            )
        )
        bound_signal = None
        warnings: list[str] = []

        for signal_id in signal_ids:
            signal = load_signal(session, signal_id)

            if signal is None:
                continue

            candidate = signal.model_copy(
                update={
                    "topology_snapshot_id": snapshot_id,
                }
            )
            candidate, candidate_warnings = (
                bind_signal_to_incident_topology(
                    session,
                    candidate,
                )
            )

            if (
                candidate.topology_snapshot_id
                != snapshot_id
            ):
                continue

            bound_signal = candidate
            warnings = candidate_warnings
            break

        if bound_signal is None:
            continue

        save_signals(
            session=session,
            signals=[bound_signal],
        )

        if not incident.topology_snapshot_id:
            incident.topology_snapshot_id = snapshot_id

        if (
            not incident.affected_entity_id
            and bound_signal.involved_entity_id
        ):
            incident.affected_entity_id = (
                bound_signal.involved_entity_id
            )

        session.commit()
        session.refresh(incident)
        results.append(
            _complete_automatic_analysis(
                session,
                incident=incident,
                signal_id=bound_signal.signal_id,
                created=False,
                warnings=warnings,
            )
        )

    return results


def ingest_failure_signal_batch(
    session: Session,
    *,
    signals: list[NormalizedSignal],
) -> FailureSignalBatchResult:
    bound: list[
        tuple[NormalizedSignal, list[str]]
    ] = [
        bind_signal_to_incident_topology(
            session,
            signal,
        )
        for signal in signals
    ]
    normalized: list[NormalizedSignal] = []

    for signal, _ in bound:
        existing = load_signal(
            session,
            signal.signal_id,
        )

        if (
            existing is not None
            and signal.attributes.get(
                "observation_source"
            ) == "topology_checkpoint"
        ):
            signal = signal.model_copy(
                update={
                    "occurrence_count": (
                        existing.occurrence_count
                        + max(
                            signal.occurrence_count,
                            1,
                        )
                    )
                }
            )

        normalized.append(signal)
    created_count, updated_count = save_signals(
        session=session,
        signals=normalized,
    )
    results: list[AutomaticIncidentResult] = []

    for signal, (_, warnings) in zip(
        normalized,
        bound,
        strict=True,
    ):
        results.append(
            process_failure_signal(
                session,
                # Correlation uses this observation's time.
                # The repository separately preserves the
                # durable signal's original first-seen time.
                signal=signal,
                initial_warnings=warnings,
            )
        )

    qualifying = sum(
        1
        for signal in normalized
        if is_failure_signal(signal)
    )

    return FailureSignalBatchResult(
        received_count=len(signals),
        created_signal_count=created_count,
        updated_signal_count=updated_count,
        qualifying_failure_count=qualifying,
        ignored_non_failure_count=(
            len(signals) - qualifying
        ),
        incident_created_count=sum(
            1
            for result in results
            if result.incident_created
        ),
        incident_correlated_count=sum(
            1
            for result in results
            if result.incident_correlated
        ),
        results=results,
    )
