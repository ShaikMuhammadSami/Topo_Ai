"""Namespace source-local storage identities without rewriting their values.

Revision ID: 0008_tenant_scoped_identity_namespace
Revises: 0007_machine_tenant_binding

Frozen and model-independent. Every rejection preflight precedes DDL.
Random authentication locators remain globally unambiguous.
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_tenant_scoped_identity_namespace"
down_revision = "0007_machine_tenant_binding"
branch_labels = None
depends_on = None

LOCAL_KEYS = {
    "topology_snapshots": "snapshot_id",
    "identity_resolutions": "snapshot_id",
    "signals": "signal_id",
    "changes": "change_id",
    "incident_analyses": "analysis_id",
    "remediation_recommendations": "recommendation_id",
    "recovery_verifications": "verification_id",
    "incidents": "incident_id",
    "incident_outcomes": "outcome_id",
    "ownership_mappings": "ownership_id",
    "webhook_deliveries": "delivery_id",
    "incident_explanations": "explanation_id",
    "incident_investigation_plans": "plan_id",
    "incident_investigation_steps": "step_id",
    "post_incident_reports": "report_id",
    "post_incident_report_actions": "action_item_id",
    "runtime_sensors": "sensor_id",
    "runtime_dependencies": "runtime_dependency_id",
    "runtime_processes": "runtime_process_id",
    "cloud_accounts": "cloud_account_id",
    "cloud_resources": "cloud_resource_id",
    "build_artifact_evidence": "evidence_id",
    "change_events": "event_id",
    "change_entity_links": "link_id",
    "causal_analyses": "analysis_id",
}

# Parallel tenant-qualified rules already exist from 0005. Only the old global
# rules are removed. No authority/authentication digest rule is in these lists.
GLOBAL_UNIQUES = {
    "identity_overrides": ("uq_identity_override_target", (
        "cluster_name", "namespace", "entity_kind", "entity_name")),
    "webhook_deliveries": ("uq_webhook_delivery_event", ("webhook_id", "event_id")),
    "incident_investigation_steps": ("uq_investigation_plan_sequence", ("plan_id", "sequence")),
    "post_incident_reports": ("uq_post_incident_report_version", ("incident_id", "version")),
    "post_incident_report_actions": ("uq_post_incident_report_action_sequence", ("report_id", "sequence")),
    "runtime_sensors": ("uq_runtime_sensor_agent_node_source", ("agent_id", "node_name", "source")),
    "build_artifact_evidence": ("uq_build_artifact_provider_fact", (
        "provider", "repository_id", "workflow_run_id", "run_attempt", "image_digest", "provider_evidence_id")),
    "change_entity_links": ("uq_change_event_entity_link", ("event_id", "entity_id", "link_type")),
    "action_approval_events": ("uq_action_approval_event_sequence", ("approval_id", "sequence")),
    "execution_intent_events": ("uq_execution_intent_event_sequence", ("execution_id", "sequence")),
}
GLOBAL_INDEXES = {
    "incident_outcomes": ("incident_id",),
    "ownership_mappings": ("fingerprint",),
    "change_events": ("event_fingerprint",),
    "change_source_deliveries": ("delivery_key",),
    "action_approvals": ("pending_key",),
    "execution_intents": ("approval_id", "idempotency_key"),
}


def _duplicate(connection, table, columns):
    """Match ordinary SQL uniqueness: nullable tuples do not conflict."""
    names = ", ".join(f'"{name}"' for name in columns)
    non_null = " AND ".join(f'"{name}" IS NOT NULL' for name in columns)
    return connection.execute(sa.text(
        f'SELECT 1 FROM "{table}" WHERE {non_null} '
        f'GROUP BY {names} HAVING COUNT(*) > 1 LIMIT 1'
    )).first() is not None


def _rules():
    for table, key in LOCAL_KEYS.items():
        yield table, (key,)
    for table, (_, columns) in GLOBAL_UNIQUES.items():
        yield table, columns
    for table, columns in GLOBAL_INDEXES.items():
        for column in columns:
            yield table, (column,)


def upgrade():
    connection = op.get_bind()
    affected = set(LOCAL_KEYS) | set(GLOBAL_UNIQUES) | set(GLOBAL_INDEXES)
    for table in sorted(affected):
        if connection.execute(sa.text(
            f'SELECT 1 FROM "{table}" WHERE tenant_id IS NULL LIMIT 1'
        )).first() is not None:
            raise RuntimeError("TENANT_IDENTITY_NULL_OWNERSHIP")
    for table, columns in _rules():
        if _duplicate(connection, table, ("tenant_id", *columns)):
            raise RuntimeError("TENANT_IDENTITY_DUPLICATE_WITHIN_TENANT")

    # The explicitly specified revision is longer than Alembic's default
    # VARCHAR(32). This is migration bookkeeping, not a customer ID change.
    # Keep the wider bookkeeping column on downgrade: Alembic still has to
    # replace this long revision with its parent after downgrade() returns.
    if connection.dialect.name == "postgresql":
        op.alter_column("alembic_version", "version_num", existing_type=sa.String(32), type_=sa.String(64))

    for table in sorted(affected):
        for column in GLOBAL_INDEXES.get(table, ()):
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        if table not in LOCAL_KEYS and table not in GLOBAL_UNIQUES:
            continue
        old_pk = sa.inspect(connection).get_pk_constraint(table)["name"]
        # SQLite's original PK is unnamed. Assign its reflection a name so
        # Alembic can target it; no historical migration is modified.
        with op.batch_alter_table(table, naming_convention={"pk": "pk_%(table_name)s"}) as batch:
            if table in GLOBAL_UNIQUES:
                batch.drop_constraint(GLOBAL_UNIQUES[table][0], type_="unique")
            if table in LOCAL_KEYS:
                batch.drop_constraint(old_pk or f"pk_{table}", type_="primary")
                batch.create_primary_key(f"pk_{table}", ["tenant_id", LOCAL_KEYS[table]])


def downgrade():
    connection = op.get_bind()
    # Check every old rule before *any* DDL. Reject collisions even when the
    # conflicting rows have different tenants. Never pick a survivor or rename.
    for table, columns in _rules():
        if _duplicate(connection, table, columns):
            raise RuntimeError("TENANT_IDENTITY_COLLISION_PREVENTS_DOWNGRADE")

    affected = set(LOCAL_KEYS) | set(GLOBAL_UNIQUES) | set(GLOBAL_INDEXES)
    for table in sorted(affected, reverse=True):
        if table in LOCAL_KEYS or table in GLOBAL_UNIQUES:
            with op.batch_alter_table(table) as batch:
                if table in LOCAL_KEYS:
                    batch.drop_constraint(f"pk_{table}", type_="primary")
                    old_name = f"{table}_pkey" if connection.dialect.name == "postgresql" else f"pk_{table}"
                    batch.create_primary_key(old_name, [LOCAL_KEYS[table]])
                if table in GLOBAL_UNIQUES:
                    name, columns = GLOBAL_UNIQUES[table]
                    batch.create_unique_constraint(name, list(columns))
        for column in GLOBAL_INDEXES.get(table, ()):
            op.create_index(f"ix_{table}_{column}", table, [column], unique=True)
