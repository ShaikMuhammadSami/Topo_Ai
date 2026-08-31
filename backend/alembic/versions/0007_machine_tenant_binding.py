"""Bind machine authority and close residual customer ownership.

Revision ID: 0007_machine_tenant_binding
Revises: 0006_domain_tenant_enforcement

Frozen, model-independent migration. The optional x-argument is an operator
assertion, never a tenant inference. All rejection preflights precede DDL.
"""

import json
import re

from alembic import context, op
import sqlalchemy as sa

revision = "0007_machine_tenant_binding"
down_revision = "0006_domain_tenant_enforcement"
branch_labels = None
depends_on = None

MACHINE_TABLES = ("agent_enrollment_tokens", "topo_agents", "change_sources")
RESIDUAL_TABLES = (
    "topology_snapshots", "changes", "signals", "incidents", "causal_analyses",
    "build_artifact_evidence", "change_events", "change_entity_links",
    "change_source_deliveries", "change_source_dead_letters", "cloud_accounts",
    "cloud_resources", "runtime_sensors", "runtime_dependencies",
    "runtime_processes", "webhook_deliveries",
)

# Recorded application references, not names, clusters, creators, payload tenant
# claims, or similarity. Alternative parents preserve existing polymorphic IDs.
# [] means an existing JSON array of durable IDs, not arbitrary payload traversal.
REFERENCES = {
    "topology_snapshots": {"scope_json.agent_id": ("topo_agents",)},
    "identity_resolutions": {"snapshot_id": ("topology_snapshots",)},
    "signals": {"payload_json.topology_snapshot_id": ("topology_snapshots",)},
    "changes": {
        "from_snapshot_id": ("topology_snapshots",),
        "to_snapshot_id": ("topology_snapshots",),
    },
    "change_events": {"agent_id": ("topo_agents",), "origin_change_id": ("changes",)},
    "change_entity_links": {
        "event_id": ("change_events",), "snapshot_id": ("topology_snapshots",),
    },
    "incidents": {
        "primary_signal_id": ("signals",), "latest_signal_id": ("signals",),
        "topology_snapshot_id": ("topology_snapshots",),
        "latest_analysis_id": ("incident_analyses", "causal_analyses"),
        "latest_recommendation_id": ("remediation_recommendations",),
        "latest_recovery_verification_id": ("recovery_verifications",),
    },
    "incident_analyses": {
        "signal_id": ("signals",), "topology_snapshot_id": ("topology_snapshots",),
    },
    "causal_analyses": {
        "incident_id": ("incidents",),
        "payload_json.topology_snapshot_id": ("topology_snapshots",),
    },
    "incident_explanations": {
        "incident_id": ("incidents",), "topology_snapshot_id": ("topology_snapshots",),
        "analysis_id": ("incident_analyses", "causal_analyses"),
    },
    "incident_copilot_sessions": {"incident_id": ("incidents",)},
    "incident_copilot_messages": {
        "incident_id": ("incidents",), "session_id": ("incident_copilot_sessions",),
    },
    "incident_investigation_plans": {"incident_id": ("incidents",)},
    "incident_investigation_steps": {
        "incident_id": ("incidents",), "plan_id": ("incident_investigation_plans",),
    },
    "post_incident_reports": {"incident_id": ("incidents",)},
    "post_incident_report_actions": {
        "incident_id": ("incidents",), "report_id": ("post_incident_reports",),
    },
    "incident_outcomes": {
        "incident_id": ("incidents",), "causal_analysis_id": ("causal_analyses",),
    },
    "remediation_recommendations": {
        "analysis_id": ("incident_analyses",), "signal_id": ("signals",),
        "change_id": ("changes",),
    },
    "recovery_verifications": {
        "recommendation_id": ("remediation_recommendations",),
        "analysis_id": ("incident_analyses",), "signal_id": ("signals",),
        "pre_snapshot_id": ("topology_snapshots",),
        "post_snapshot_id": ("topology_snapshots",),
    },
    "action_approvals": {"incident_id": ("incidents",)},
    "action_approval_events": {
        "incident_id": ("incidents",), "approval_id": ("action_approvals",),
    },
    "execution_intents": {
        "incident_id": ("incidents",), "approval_id": ("action_approvals",),
    },
    "execution_intent_events": {
        "incident_id": ("incidents",), "approval_id": ("action_approvals",),
        "execution_id": ("execution_intents",),
    },
    "webhook_deliveries": {"webhook_id": ("webhook_endpoints",)},
    "change_source_deliveries": {
        "source_id": ("change_sources",), "event_ids_json[]": ("change_events",),
    },
    "change_source_dead_letters": {
        "source_id": ("change_sources",), "delivery_id": ("change_source_deliveries",),
    },
    "runtime_sensors": {"agent_id": ("topo_agents",)},
    "runtime_dependencies": {
        "agent_id": ("topo_agents",), "sensor_id": ("runtime_sensors",),
    },
    "runtime_processes": {
        "agent_id": ("topo_agents",), "sensor_id": ("runtime_sensors",),
    },
    "cloud_resources": {"agent_id": ("topo_agents",)},
}

_TENANT_ID = re.compile(
    r"^tenant:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _legacy_target(connection):
    has_legacy = any(
        connection.scalar(sa.text(f'SELECT COUNT(*) FROM "{name}"'))
        for name in MACHINE_TABLES
    ) or any(
        connection.scalar(sa.text(
            f'SELECT COUNT(*) FROM "{name}" WHERE tenant_id IS NULL'
        )) for name in RESIDUAL_TABLES
    )
    target = context.get_x_argument(as_dictionary=True).get("legacy_machine_tenant_id")
    if target is None:
        if has_legacy:
            raise RuntimeError("LEGACY_MACHINE_TENANT_REQUIRED")
        return None
    if not _TENANT_ID.fullmatch(target):
        raise RuntimeError("LEGACY_MACHINE_TENANT_INVALID")
    status = connection.scalar(sa.text(
        "SELECT status FROM tenants WHERE tenant_id = :target"
    ), {"target": target})
    if status is None:
        raise RuntimeError("LEGACY_MACHINE_TENANT_NOT_FOUND")
    if status != "active":
        raise RuntimeError("LEGACY_MACHINE_TENANT_DISABLED")
    return target


def _identifiers(raw, field):
    if "." in field or field.endswith("[]"):
        try:
            raw = json.loads(raw or "null")
        except (ValueError, TypeError):
            return ()  # Invalid historical evidence does not prove ownership.
        if "." in field:
            raw = raw.get(field.split(".", 1)[1]) if isinstance(raw, dict) else None
        elif not isinstance(raw, list):
            return ()
    values = raw if isinstance(raw, list) else (raw,)
    return tuple(value for value in values if isinstance(value, str) and value)


def _check_conflicts(connection, target):
    """Check both reference directions using prospective owners before DDL.

    No default is written or inferred. Missing references prove nothing. Only
    a found durable parent with contradictory existing ownership rejects the
    operator assertion. Streaming rows bounds migration memory usage.
    """
    inspector = sa.inspect(connection)
    keys = {
        name: inspector.get_pk_constraint(name)["constrained_columns"][0]
        for parents in REFERENCES.values() for names in parents.values() for name in names
    }
    for child, references in REFERENCES.items():
        for field, parents in references.items():
            column = field.split(".", 1)[0].removesuffix("[]")
            rows = connection.execute(sa.text(
                f'SELECT tenant_id, "{column}" AS reference FROM "{child}"'
            )).yield_per(256)
            for row in rows:
                child_owner = row.tenant_id
                for identifier in _identifiers(row.reference, field):
                    for parent in parents:
                        owner_column = "NULL" if parent in MACHINE_TABLES else "tenant_id"
                        found = connection.execute(sa.text(
                            f'SELECT {owner_column} AS owner FROM "{parent}" '
                            f'WHERE "{keys[parent]}" = :identifier'
                        ), {"identifier": identifier}).first()
                        if found is None:
                            continue
                        parent_owner = found.owner
                        if (child_owner is None or parent_owner is None) and (
                            (target if child_owner is None else child_owner)
                            != (target if parent_owner is None else parent_owner)
                        ):
                            raise RuntimeError("LEGACY_MACHINE_TENANT_CONFLICT")


def upgrade():
    connection = op.get_bind()
    target = _legacy_target(connection)
    if target is not None:
        _check_conflicts(connection, target)
    for name in MACHINE_TABLES:
        with op.batch_alter_table(name) as batch:
            batch.add_column(sa.Column("tenant_id", sa.String(255), nullable=True))
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"], unique=False)
    if target is not None:
        for name in MACHINE_TABLES + RESIDUAL_TABLES:
            connection.execute(sa.text(
                f'UPDATE "{name}" SET tenant_id = :target WHERE tenant_id IS NULL'
            ), {"target": target})
    for name in MACHINE_TABLES + RESIDUAL_TABLES:
        if connection.scalar(sa.text(
            f'SELECT COUNT(*) FROM "{name}" WHERE tenant_id IS NULL'
        )):
            raise RuntimeError("MACHINE_TENANT_NULL_ROWS_PRESENT")
    for name in MACHINE_TABLES + RESIDUAL_TABLES:
        with op.batch_alter_table(name) as batch:
            batch.alter_column("tenant_id", existing_type=sa.String(255), nullable=False)


def downgrade():
    for name in reversed(RESIDUAL_TABLES):
        with op.batch_alter_table(name) as batch:
            batch.alter_column("tenant_id", existing_type=sa.String(255), nullable=True)
    for name in reversed(MACHINE_TABLES):
        op.drop_index(f"ix_{name}_tenant_id", table_name=name)
        with op.batch_alter_table(name) as batch:
            batch.drop_column("tenant_id")
