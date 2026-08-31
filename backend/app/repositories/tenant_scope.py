"""Explicit SQL ownership predicates.

There is no session/global current tenant and no ORM event filter here. Callers
must supply server-authoritative ownership on every operation.
"""

from __future__ import annotations

import json
from typing import TypeVar

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models.tenant import is_valid_tenant_id


DomainTenant = str
Record = TypeVar("Record")


class TenantResourceNotFound(LookupError):
    """A resource or authoritative reference is absent in this boundary."""

    def __init__(self) -> None:
        super().__init__("Resource not found.")


def tenant_value(tenant_id: DomainTenant) -> str:
    if not isinstance(tenant_id, str) or not is_valid_tenant_id(tenant_id):
        raise ValueError("TENANT_CONTEXT_REQUIRED")
    return tenant_id


def tenant_predicate(model: type[Record], tenant_id: DomainTenant):
    value = tenant_value(tenant_id)
    return model.tenant_id == value


def tenant_get(
    session: Session,
    model: type[Record],
    identifier: str,
    *,
    tenant_id: DomainTenant,
) -> Record | None:
    primary_key = inspect(model).primary_key[0]
    # A lookup must not flush a pending child before the explicit writer guard.
    # This also protects callers using an injected autoflush=True Session.
    with session.no_autoflush:
        return session.scalar(
            select(model).where(
                tenant_predicate(model, tenant_id),
                primary_key == identifier,
            )
        )


def require_record_owner(record: object, *, tenant_id: DomainTenant) -> None:
    state = inspect(record)
    if state.detached:
        raise TenantResourceNotFound()
    if state.transient:
        record.tenant_id = tenant_value(tenant_id)
        return
    value = tenant_value(tenant_id)
    original = state.attrs.tenant_id.history.deleted
    if (original and original[0] != value) or getattr(
        record, "tenant_id", None
    ) != value:
        raise TenantResourceNotFound()


def tenant_add(
    session: Session,
    record: Record,
    *,
    tenant_id: DomainTenant,
) -> None:
    """Own new rows; never reassign an existing/detached foreign row.

    Global PK/unique restrictions remain in force until PH-3F. A collision
    must fail at the database boundary, never become an unscoped upsert.
    """
    state = inspect(record)
    value = tenant_value(tenant_id)
    if state.detached:
        raise TenantResourceNotFound()
    if state.persistent:
        require_record_owner(record, tenant_id=tenant_id)
    else:
        record.tenant_id = value
    session.add(record)


# Only durable application references; source-native entity IDs inside a
# tenant-proven snapshot keep their Truth Contract meaning.
_PARENTS = {
    "identity_resolutions": {"snapshot_id": ("SnapshotRecord",)},
    "signals": {"payload_json.topology_snapshot_id": ("SnapshotRecord",)},
    "topology_snapshots": {"scope_json.agent_id": ("TopoAgentRecord",)},
    "change_events": {
        "origin_change_id": ("ChangeRecord",),
        "agent_id": ("TopoAgentRecord",),
    },
    "changes": {
        "from_snapshot_id": ("SnapshotRecord",),
        "to_snapshot_id": ("SnapshotRecord",),
    },
    "change_entity_links": {
        "event_id": ("ChangeEventRecord",),
        "snapshot_id": ("SnapshotRecord",),
    },
    "incidents": {
        "primary_signal_id": ("SignalRecord",),
        "latest_signal_id": ("SignalRecord",),
        "topology_snapshot_id": ("SnapshotRecord",),
        "latest_analysis_id": ("IncidentAnalysisRecord", "CausalAnalysisRecord"),
        "latest_recommendation_id": ("RecommendationRecord",),
        "latest_recovery_verification_id": ("RecoveryVerificationRecord",),
    },
    "incident_analyses": {
        "signal_id": ("SignalRecord",),
        "topology_snapshot_id": ("SnapshotRecord",),
    },
    "causal_analyses": {
        "incident_id": ("IncidentRecord",),
        "payload_json.topology_snapshot_id": ("SnapshotRecord",),
    },
    "incident_explanations": {
        "incident_id": ("IncidentRecord",),
        "topology_snapshot_id": ("SnapshotRecord",),
        "analysis_id": ("IncidentAnalysisRecord", "CausalAnalysisRecord"),
    },
    "incident_copilot_sessions": {"incident_id": ("IncidentRecord",)},
    "incident_copilot_messages": {
        "incident_id": ("IncidentRecord",),
        "session_id": ("CopilotSessionRecord",),
    },
    "incident_investigation_plans": {"incident_id": ("IncidentRecord",)},
    "incident_investigation_steps": {
        "incident_id": ("IncidentRecord",),
        "plan_id": ("InvestigationPlanRecord",),
    },
    "post_incident_reports": {"incident_id": ("IncidentRecord",)},
    "post_incident_report_actions": {
        "incident_id": ("IncidentRecord",),
        "report_id": ("PostIncidentReportRecord",),
    },
    "incident_outcomes": {
        "incident_id": ("IncidentRecord",),
        "causal_analysis_id": ("CausalAnalysisRecord",),
    },
    "remediation_recommendations": {
        "analysis_id": ("IncidentAnalysisRecord",),
        "signal_id": ("SignalRecord",),
        "change_id": ("ChangeRecord",),
    },
    "recovery_verifications": {
        "recommendation_id": ("RecommendationRecord",),
        "analysis_id": ("IncidentAnalysisRecord",),
        "signal_id": ("SignalRecord",),
        "pre_snapshot_id": ("SnapshotRecord",),
        "post_snapshot_id": ("SnapshotRecord",),
    },
    "action_approvals": {"incident_id": ("IncidentRecord",)},
    "action_approval_events": {
        "incident_id": ("IncidentRecord",),
        "approval_id": ("ActionApprovalRecord",),
    },
    "execution_intents": {
        "incident_id": ("IncidentRecord",),
        "approval_id": ("ActionApprovalRecord",),
    },
    "execution_intent_events": {
        "incident_id": ("IncidentRecord",),
        "approval_id": ("ActionApprovalRecord",),
        "execution_id": ("ExecutionIntentRecord",),
    },
    "webhook_deliveries": {"webhook_id": ("WebhookEndpointRecord",)},
    "change_source_deliveries": {"source_id": ("ChangeSourceRecord",)},
    "change_source_dead_letters": {
        "delivery_id": ("ChangeSourceDeliveryRecord",),
        "source_id": ("ChangeSourceRecord",),
    },
    "runtime_sensors": {"agent_id": ("TopoAgentRecord",)},
    "runtime_dependencies": {
        "sensor_id": ("RuntimeSensorRecord",), "agent_id": ("TopoAgentRecord",),
    },
    "runtime_processes": {
        "sensor_id": ("RuntimeSensorRecord",), "agent_id": ("TopoAgentRecord",),
    },
    "cloud_resources": {"agent_id": ("TopoAgentRecord",)},
}


def validate_tenant_writes(session: Session, *, tenant_id: DomainTenant) -> None:
    """Validate the explicit unit of work before a repository flush/commit.

    This is called explicitly by scoped writers, not installed as a global
    SQLAlchemy hook. It never supplies a default or backfills unowned rows.
    """
    from app.db import models

    value = tenant_value(tenant_id)
    pending = tuple(session.new)
    records = set(pending) | set(session.dirty) | set(session.deleted)
    with session.no_autoflush:
        for record in records:
            if not isinstance(record, models.TenantOwnedRecordMixin):
                continue
            if record.tenant_id != value:
                raise TenantResourceNotFound()
            history = inspect(record).attrs.tenant_id.history.deleted
            if history and history[0] != value:
                raise TenantResourceNotFound()
            if record in session.deleted:
                continue
            for field, names in _PARENTS.get(record.__tablename__, {}).items():
                if "." in field:
                    column, key = field.split(".", 1)
                    identifier = json.loads(getattr(record, column) or "{}").get(key)
                else:
                    identifier = getattr(record, field, None)
                if not identifier:
                    continue
                found = False
                for name in names:
                    model = getattr(models, name)
                    pk = inspect(model).primary_key[0].key
                    if (
                        any(
                            isinstance(parent, model)
                            and getattr(parent, pk) == identifier
                            and parent.tenant_id == value
                            for parent in pending
                        )
                        or tenant_get(session, model, identifier, tenant_id=tenant_id)
                        is not None
                    ):
                        found = True
                        break
                if not found:
                    raise TenantResourceNotFound()


def tenant_flush(session: Session, *, tenant_id: DomainTenant) -> None:
    validate_tenant_writes(session, tenant_id=tenant_id)
    session.flush()


def tenant_commit(session: Session, *, tenant_id: DomainTenant) -> None:
    validate_tenant_writes(session, tenant_id=tenant_id)
    session.commit()
