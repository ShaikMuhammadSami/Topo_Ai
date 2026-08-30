"""tenant foundation

Revision ID: 0004_tenant_foundation
Revises: 0003_auth_api_credentials
Create Date: 2026-08-30

This additive revision is intentionally static and model-independent.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_tenant_foundation"
down_revision: str | Sequence[str] | None = "0003_auth_api_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.String(length=50), nullable=False),
        sa.Column("updated_at", sa.String(length=50), nullable=False),
        sa.Column(
            "created_by_subject",
            sa.String(length=500),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_index(
        "ix_tenants_status",
        "tenants",
        ["status"],
        unique=False,
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("membership_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.String(length=50), nullable=False),
        sa.Column("updated_at", sa.String(length=50), nullable=False),
        sa.Column(
            "created_by_subject",
            sa.String(length=500),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("membership_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "subject",
            name="uq_tenant_memberships_tenant_subject",
        ),
    )
    op.create_index(
        "ix_tenant_memberships_subject",
        "tenant_memberships",
        ["subject"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_memberships_tenant_id",
        "tenant_memberships",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_memberships_active_resolution",
        "tenant_memberships",
        ["tenant_id", "subject", "status"],
        unique=False,
    )

    op.create_table(
        "service_api_tenant_bindings",
        sa.Column("binding_id", sa.String(length=255), nullable=False),
        sa.Column("credential_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.String(length=50), nullable=False),
        sa.Column(
            "created_by_subject",
            sa.String(length=500),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("binding_id"),
        sa.UniqueConstraint(
            "credential_id",
            name="uq_service_api_tenant_bindings_credential_id",
        ),
    )
    op.create_index(
        "ix_service_api_tenant_bindings_tenant_id",
        "service_api_tenant_bindings",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("service_api_tenant_bindings")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
