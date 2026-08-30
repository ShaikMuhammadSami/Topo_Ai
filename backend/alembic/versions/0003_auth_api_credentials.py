"""named API credentials

Revision ID: 0003_auth_api_credentials
Revises: 0002_auth_sessions
Create Date: 2026-08-29

This additive revision is intentionally static and model-independent.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_auth_api_credentials"
down_revision: str | Sequence[str] | None = "0002_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_api_credentials",
        sa.Column("credential_id", sa.String(length=255), nullable=False),
        sa.Column(
            "credential_secret_digest",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("credential_hint", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("caller_type", sa.String(length=30), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=50), nullable=False),
        sa.Column("created_by_subject", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.String(length=50), nullable=False),
        sa.Column("revoked_at", sa.String(length=50), nullable=True),
        sa.Column("revoked_by_subject", sa.String(length=500), nullable=True),
        sa.Column("last_used_at", sa.String(length=50), nullable=True),
        sa.Column("updated_at", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("credential_id"),
        sa.UniqueConstraint(
            "credential_secret_digest",
            name="uq_auth_api_credentials_secret_digest",
        ),
    )
    op.create_index(
        "ix_auth_api_credentials_caller_type",
        "auth_api_credentials",
        ["caller_type"],
        unique=False,
    )
    op.create_index(
        "ix_auth_api_credentials_subject",
        "auth_api_credentials",
        ["subject"],
        unique=False,
    )
    op.create_index(
        "ix_auth_api_credentials_expires_at",
        "auth_api_credentials",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_api_credentials_revoked_at",
        "auth_api_credentials",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_api_credentials_last_used_at",
        "auth_api_credentials",
        ["last_used_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("auth_api_credentials")
