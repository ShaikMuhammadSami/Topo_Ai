"""domain tenant ownership and controlled legacy backfill

Revision ID: 0005_domain_tenant_ownership
Revises: 0004_tenant_foundation
Create Date: 2026-08-30

This additive revision is intentionally model-independent.  It prepares
customer-domain persistence for tenant enforcement without changing current
repository or API behavior.  Existing rows require an explicitly selected,
active tenant supplied as ``-x legacy_tenant_id=<tenant_id>``.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa


revision: str = "0005_domain_tenant_ownership"
down_revision: str | Sequence[str] | None = "0004_tenant_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PH3C_DOMAIN_TABLES: tuple[str, ...] = (
    "action_approval_events",
    "action_approvals",
    "build_artifact_evidence",
    "causal_analyses",
    "change_entity_links",
    "change_events",
    "change_source_dead_letters",
    "change_source_deliveries",
    "changes",
    "cloud_accounts",
    "cloud_resources",
    "execution_intent_events",
    "execution_intents",
    "identity_overrides",
    "identity_resolutions",
    "incident_analyses",
    "incident_copilot_messages",
    "incident_copilot_sessions",
    "incident_explanations",
    "incident_investigation_plans",
    "incident_investigation_steps",
    "incident_outcomes",
    "incidents",
    "ownership_mappings",
    "post_incident_report_actions",
    "post_incident_reports",
    "recovery_verifications",
    "remediation_recommendations",
    "runtime_dependencies",
    "runtime_processes",
    "runtime_sensors",
    "signals",
    "topology_snapshots",
    "webhook_deliveries",
    "webhook_endpoints",
)


TENANT_SCOPED_UNIQUE_CONSTRAINTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "action_approval_events": (
        (
            "uq_tenant_action_approval_event_sequence",
            ("tenant_id", "approval_id", "sequence"),
        ),
    ),
    "build_artifact_evidence": (
        (
            "uq_tenant_build_artifact_provider_fact",
            (
                "tenant_id",
                "provider",
                "repository_id",
                "workflow_run_id",
                "run_attempt",
                "image_digest",
                "provider_evidence_id",
            ),
        ),
    ),
    "change_entity_links": (
        (
            "uq_tenant_change_event_entity_link",
            ("tenant_id", "event_id", "entity_id", "link_type"),
        ),
    ),
    "execution_intent_events": (
        (
            "uq_tenant_execution_intent_event_sequence",
            ("tenant_id", "execution_id", "sequence"),
        ),
    ),
    "identity_overrides": (
        (
            "uq_tenant_identity_override_target",
            (
                "tenant_id",
                "cluster_name",
                "namespace",
                "entity_kind",
                "entity_name",
            ),
        ),
    ),
    "incident_investigation_steps": (
        (
            "uq_tenant_investigation_plan_sequence",
            ("tenant_id", "plan_id", "sequence"),
        ),
    ),
    "post_incident_report_actions": (
        (
            "uq_tenant_post_incident_report_action_sequence",
            ("tenant_id", "report_id", "sequence"),
        ),
    ),
    "post_incident_reports": (
        (
            "uq_tenant_post_incident_report_version",
            ("tenant_id", "incident_id", "version"),
        ),
    ),
    "runtime_sensors": (
        (
            "uq_tenant_runtime_sensor_agent_node_source",
            ("tenant_id", "agent_id", "node_name", "source"),
        ),
    ),
    "webhook_deliveries": (
        (
            "uq_tenant_webhook_delivery_event",
            ("tenant_id", "webhook_id", "event_id"),
        ),
    ),
}


TENANT_SCOPED_UNIQUE_INDEXES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "action_approvals": (
        (
            "ix_tenant_action_approvals_pending_key",
            ("tenant_id", "pending_key"),
        ),
    ),
    "change_events": (
        (
            "ix_tenant_change_events_event_fingerprint",
            ("tenant_id", "event_fingerprint"),
        ),
    ),
    "change_source_deliveries": (
        (
            "ix_tenant_change_source_deliveries_delivery_key",
            ("tenant_id", "delivery_key"),
        ),
    ),
    "execution_intents": (
        (
            "ix_tenant_execution_intents_approval_id",
            ("tenant_id", "approval_id"),
        ),
        (
            "ix_tenant_execution_intents_idempotency_key",
            ("tenant_id", "idempotency_key"),
        ),
    ),
    "incident_outcomes": (
        (
            "ix_tenant_incident_outcomes_incident_id",
            ("tenant_id", "incident_id"),
        ),
    ),
    "ownership_mappings": (
        (
            "ix_tenant_ownership_mappings_fingerprint",
            ("tenant_id", "fingerprint"),
        ),
    ),
}


_TENANT_ID_PATTERN = re.compile(
    r"^tenant:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _has_pre_tenancy_rows(bind: sa.Connection) -> bool:
    for table_name in PH3C_DOMAIN_TABLES:
        row = bind.execute(
            sa.text(f'SELECT 1 FROM "{table_name}" LIMIT 1')
        ).first()
        if row is not None:
            return True
    return False


def _legacy_tenant_id(bind: sa.Connection) -> str | None:
    arguments = context.get_x_argument(as_dictionary=True)
    tenant_id = arguments.get("legacy_tenant_id")
    has_rows = _has_pre_tenancy_rows(bind)

    if tenant_id is None:
        if has_rows:
            raise RuntimeError("LEGACY_TENANT_REQUIRED")
        return None

    if not _TENANT_ID_PATTERN.fullmatch(tenant_id):
        raise RuntimeError("LEGACY_TENANT_INVALID")

    status = bind.execute(
        sa.text(
            "SELECT status FROM tenants WHERE tenant_id = :tenant_id"
        ),
        {"tenant_id": tenant_id},
    ).scalar_one_or_none()
    if status is None:
        raise RuntimeError("LEGACY_TENANT_NOT_FOUND")
    if status != "active":
        raise RuntimeError("LEGACY_TENANT_DISABLED")
    return tenant_id


def _add_tenant_shape(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(
            sa.Column("tenant_id", sa.String(length=255), nullable=True)
        )
        for constraint_name, columns in TENANT_SCOPED_UNIQUE_CONSTRAINTS.get(
            table_name, ()
        ):
            batch_op.create_unique_constraint(constraint_name, columns)

    op.create_index(
        f"ix_{table_name}_tenant_id",
        table_name,
        ["tenant_id"],
        unique=False,
    )
    for index_name, columns in TENANT_SCOPED_UNIQUE_INDEXES.get(
        table_name, ()
    ):
        op.create_index(
            index_name,
            table_name,
            list(columns),
            unique=True,
        )


def _drop_tenant_shape(table_name: str) -> None:
    for index_name, _ in reversed(
        TENANT_SCOPED_UNIQUE_INDEXES.get(table_name, ())
    ):
        op.drop_index(index_name, table_name=table_name)
    op.drop_index(
        f"ix_{table_name}_tenant_id",
        table_name=table_name,
    )

    with op.batch_alter_table(table_name) as batch_op:
        for constraint_name, _ in reversed(
            TENANT_SCOPED_UNIQUE_CONSTRAINTS.get(table_name, ())
        ):
            batch_op.drop_constraint(constraint_name, type_="unique")
        batch_op.drop_column("tenant_id")


def upgrade() -> None:
    bind = op.get_bind()
    tenant_id = _legacy_tenant_id(bind)

    for table_name in PH3C_DOMAIN_TABLES:
        _add_tenant_shape(table_name)

    if tenant_id is None:
        return

    for table_name in PH3C_DOMAIN_TABLES:
        bind.execute(
            sa.text(
                f'UPDATE "{table_name}" SET tenant_id = :tenant_id '
                "WHERE tenant_id IS NULL"
            ),
            {"tenant_id": tenant_id},
        )
        remaining = bind.execute(
            sa.text(
                f'SELECT COUNT(*) FROM "{table_name}" '
                "WHERE tenant_id IS NULL"
            )
        ).scalar_one()
        if remaining:
            raise RuntimeError("LEGACY_TENANT_BACKFILL_INCOMPLETE")


def downgrade() -> None:
    for table_name in reversed(PH3C_DOMAIN_TABLES):
        _drop_tenant_shape(table_name)
