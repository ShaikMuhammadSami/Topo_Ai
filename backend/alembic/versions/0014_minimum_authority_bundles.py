"""Add explicit human, service, and installation authority assignments.

Revision ID: 0014_min_authority
Revises: 0013_principal_enforce

Existing membership/service authority is mapped once for compatibility. No
installation authority can be inferred. Downgrade discards authorization
metadata and is intended only for explicitly disposable rollback exercises.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json

from alembic import op
import sqlalchemy as sa


revision = "0014_min_authority"
down_revision = "0013_principal_enforce"
branch_labels = None
depends_on = None

# Immutable migration-local vocabulary; never import current policy/models.
SERVICE_COMPATIBILITY_PERMISSIONS = (
    "evidence.read",
    "incident.read",
    "incident.respond",
    "integration.manage",
    "integration.read",
    "ownership.manage",
    "ownership.read",
    "report.read",
    "topology.read",
)


def upgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.add_column(sa.Column("role", sa.String(30), nullable=True))
    # Existing rows already possessed broad application authority before roles.
    connection.execute(sa.text("UPDATE tenant_memberships SET role='tenant_admin'"))
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.alter_column(
            "role", existing_type=sa.String(30), existing_nullable=True,
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_tenant_memberships_role",
            "role IN ('tenant_viewer', 'tenant_responder', 'tenant_admin')",
        )

    service_permissions = op.create_table(
        "service_principal_permissions",
        sa.Column("principal_id", sa.String(46), nullable=False),
        sa.Column("permissions_json", sa.Text(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("principal_id"),
        sa.ForeignKeyConstraint(["principal_id"], ["auth_principals.principal_id"]),
        sa.CheckConstraint("row_version > 0", name="ck_service_permissions_row_version"),
    )
    op.create_table(
        "installation_operator_assignments",
        sa.Column("principal_id", sa.String(46), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("principal_id"),
        sa.ForeignKeyConstraint(["principal_id"], ["auth_principals.principal_id"]),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_installation_operator_status"
        ),
    )
    serialized = json.dumps(SERVICE_COMPATIBILITY_PERMISSIONS, separators=(",", ":"))
    now = datetime.now(UTC).isoformat()
    principals = connection.execute(
        sa.text("SELECT principal_id FROM auth_principals WHERE principal_type='service'")
    ).scalars()
    for principal_id in principals:
        connection.execute(service_permissions.insert().values(
            principal_id=principal_id, permissions_json=serialized, row_version=1,
            created_at=now, updated_at=now,
        ))
    # Populated installations require explicit local operator assignment.


def downgrade() -> None:
    op.drop_table("installation_operator_assignments")
    op.drop_table("service_principal_permissions")
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.drop_constraint("ck_tenant_memberships_role", type_="check")
        batch.drop_column("role")
