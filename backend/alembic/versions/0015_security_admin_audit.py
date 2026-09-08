"""Add the minimum durable security/admin audit ledger.

Revision ID: 0015_security_audit
Revises: 0014_min_authority

The ledger begins empty.  No historical audit events are synthesized and no
tenant, principal, or resource foreign keys are introduced because security
evidence must survive lifecycle deletion of those records.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_security_audit"
down_revision = "0014_min_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("audit_event_id", sa.String(42), nullable=False),
        sa.Column("occurred_at", sa.String(50), nullable=False),
        sa.Column("actor_principal_id", sa.String(46), nullable=True),
        sa.Column("actor_kind", sa.String(24), nullable=False),
        sa.Column("actor_reference", sa.String(255), nullable=True),
        sa.Column("authentication_type", sa.String(64), nullable=False),
        sa.Column("authority_kind", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("permissions_json", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("audit_event_id"),
        sa.CheckConstraint(
            "actor_kind IN ('human', 'service', 'agent', 'provider', 'local_operator')",
            name="ck_security_audit_actor_kind",
        ),
        sa.CheckConstraint(
            "authority_kind IN ('authentication_self_service', 'human_tenant', "
            "'service_tenant', 'installation', 'agent_fixed_purpose', "
            "'provider_fixed_purpose', 'local_operator')",
            name="ck_security_audit_authority_kind",
        ),
        sa.CheckConstraint(
            "result IN ('allowed', 'denied')",
            name="ck_security_audit_result",
        ),
        sa.CheckConstraint(
            "length(audit_event_id) = 42 "
            "AND substr(audit_event_id, 1, 6) = 'audit:'",
            name="ck_security_audit_event_id",
        ),
    )
    op.create_index(
        "ix_security_audit_tenant_occurred",
        "security_audit_events",
        ["tenant_id", "occurred_at"],
    )
    op.create_index(
        "ix_security_audit_actor_occurred",
        "security_audit_events",
        ["actor_principal_id", "occurred_at"],
    )
    op.create_index(
        "ix_security_audit_action_occurred",
        "security_audit_events",
        ["action", "occurred_at"],
    )
    op.create_index(
        "ix_security_audit_request_id",
        "security_audit_events",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_table("security_audit_events")
