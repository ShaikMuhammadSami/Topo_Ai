"""Close proven human/service domain ownership; preserve PH-3E residuals.

Revision ID: 0006_domain_tenant_enforcement
Revises: 0005_domain_tenant_ownership

Model-independent frozen writer closure. No assignment, backfill, x-argument,
default, identity rewrite, new table, or machine authority binding.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_domain_tenant_enforcement"
down_revision = "0005_domain_tenant_ownership"
branch_labels = None
depends_on = None

REQUIRED_OWNERSHIP_TABLES = (
    "action_approval_events",
    "action_approvals",
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
    "ownership_mappings",
    "post_incident_report_actions",
    "post_incident_reports",
    "recovery_verifications",
    "remediation_recommendations",
    "webhook_endpoints",
)


def upgrade():
    connection = op.get_bind()
    failures = []
    # Complete preflight before any ALTER (including on SQLite).
    for name in REQUIRED_OWNERSHIP_TABLES:
        table = sa.table(name, sa.column("tenant_id"))
        count = connection.scalar(
            sa.select(sa.func.count())
            .select_from(table)
            .where(table.c.tenant_id.is_(None))
        )
        if count:
            failures.append(f"{name}={count}")
    if failures:
        raise RuntimeError("TENANT_OWNERSHIP_NULL_ROWS_PRESENT: " + ", ".join(failures))
    for name in REQUIRED_OWNERSHIP_TABLES:
        with op.batch_alter_table(name) as batch:
            batch.alter_column(
                "tenant_id", existing_type=sa.String(255), nullable=False
            )


def downgrade():
    for name in reversed(REQUIRED_OWNERSHIP_TABLES):
        with op.batch_alter_table(name) as batch:
            batch.alter_column("tenant_id", existing_type=sa.String(255), nullable=True)
