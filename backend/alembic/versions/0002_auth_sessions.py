"""human browser auth sessions

Revision ID: 0002_auth_sessions
Revises: 0001_current_schema
Create Date: 2026-08-28

This additive revision is intentionally static and model-independent.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_auth_sessions"
down_revision: str | Sequence[str] | None = "0001_current_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column(
            "session_secret_digest",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("csrf_digest", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column(
            "source_authentication_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "source_credential_digest",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("issued_at", sa.String(length=50), nullable=False),
        sa.Column(
            "absolute_expires_at",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("idle_expires_at", sa.String(length=50), nullable=False),
        sa.Column("last_seen_at", sa.String(length=50), nullable=False),
        sa.Column("revoked_at", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint(
            "session_secret_digest",
            name="uq_auth_sessions_secret_digest",
        ),
    )


def downgrade() -> None:
    op.drop_table("auth_sessions")
