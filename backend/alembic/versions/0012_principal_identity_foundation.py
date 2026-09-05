"""Create issuer-aware principal identity and backfill legacy security rows.

Revision ID: 0012_principal_identity
Revises: 0011_secret_enforce
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0012_principal_identity"
down_revision = "0011_secret_enforce"
branch_labels = None
depends_on = None

LEGACY_LOCAL_ISSUER = "urn:topo:auth:legacy-local-v1"


def _principal_id() -> str:
    return f"principal:{uuid4()}"


def _identity_id() -> str:
    return f"identity:{uuid4()}"


def _valid_authority(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 500
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _legacy_human_rows(connection) -> dict[str, str]:
    humans: dict[str, str] = {}
    queries = (
        "SELECT subject, subject AS display_name FROM tenant_memberships",
        "SELECT subject, display_name FROM auth_sessions",
        "SELECT subject, display_name FROM auth_api_credentials "
        "WHERE caller_type = 'human_api'",
    )
    for query in queries:
        for row in connection.execute(sa.text(query)).mappings():
            subject = row["subject"]
            display_name = row["display_name"]
            if not _valid_authority(subject):
                raise RuntimeError("LEGACY_PRINCIPAL_IDENTITY_REVIEW_REQUIRED")
            if not _valid_authority(display_name):
                display_name = subject
            humans.setdefault(subject, display_name)
    return humans


def _backfill(connection) -> None:
    now = datetime.now(UTC).isoformat()
    for subject, display_name in sorted(_legacy_human_rows(connection).items()):
        principal_id = _principal_id()
        connection.execute(
            sa.text(
                "INSERT INTO auth_principals "
                "(principal_id, principal_type, display_name, status, created_at, updated_at) "
                "VALUES (:principal_id, 'human', :display_name, 'active', :now, :now)"
            ),
            {"principal_id": principal_id, "display_name": display_name, "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO external_identities "
                "(external_identity_id, principal_id, issuer, subject, status, "
                "created_at, updated_at) VALUES "
                "(:identity_id, :principal_id, :issuer, :subject, 'active', :now, :now)"
            ),
            {
                "identity_id": _identity_id(),
                "principal_id": principal_id,
                "issuer": LEGACY_LOCAL_ISSUER,
                "subject": subject,
                "now": now,
            },
        )
        for table in ("tenant_memberships", "auth_sessions"):
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET principal_id = :principal_id "
                    "WHERE subject = :subject"
                ),
                {"principal_id": principal_id, "subject": subject},
            )
        connection.execute(
            sa.text(
                "UPDATE auth_api_credentials SET principal_id = :principal_id "
                "WHERE caller_type = 'human_api' AND subject = :subject"
            ),
            {"principal_id": principal_id, "subject": subject},
        )

    services = connection.execute(
        sa.text(
            "SELECT credential_id, display_name FROM auth_api_credentials "
            "WHERE caller_type = 'service_api' ORDER BY credential_id"
        )
    ).mappings()
    for service in services:
        display_name = service["display_name"]
        if not _valid_authority(display_name):
            raise RuntimeError("LEGACY_PRINCIPAL_IDENTITY_REVIEW_REQUIRED")
        principal_id = _principal_id()
        connection.execute(
            sa.text(
                "INSERT INTO auth_principals "
                "(principal_id, principal_type, display_name, status, created_at, updated_at) "
                "VALUES (:principal_id, 'service', :display_name, 'active', :now, :now)"
            ),
            {"principal_id": principal_id, "display_name": display_name, "now": now},
        )
        connection.execute(
            sa.text(
                "UPDATE auth_api_credentials SET principal_id = :principal_id "
                "WHERE credential_id = :credential_id"
            ),
            {
                "principal_id": principal_id,
                "credential_id": service["credential_id"],
            },
        )


def upgrade() -> None:
    op.create_table(
        "auth_principals",
        sa.Column("principal_id", sa.String(46), nullable=False),
        sa.Column("principal_type", sa.String(30), nullable=False),
        sa.Column("display_name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("principal_id"),
        sa.CheckConstraint(
            "principal_type IN ('human', 'service')",
            name="ck_auth_principals_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_auth_principals_status",
        ),
        sa.CheckConstraint(
            "length(principal_id) = 46 AND substr(principal_id, 1, 10) = 'principal:'",
            name="ck_auth_principals_id",
        ),
    )
    op.create_index(
        "ix_auth_principals_status",
        "auth_principals",
        ["status"],
        unique=False,
    )
    op.create_table(
        "external_identities",
        sa.Column("external_identity_id", sa.String(45), nullable=False),
        sa.Column("principal_id", sa.String(46), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("external_identity_id"),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["auth_principals.principal_id"],
            name="fk_external_identities_principal_id",
        ),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_external_identities_issuer_subject",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_external_identities_status",
        ),
        sa.CheckConstraint(
            "length(external_identity_id) = 45 "
            "AND substr(external_identity_id, 1, 9) = 'identity:'",
            name="ck_external_identities_id",
        ),
    )
    op.create_index(
        "ix_external_identities_principal_id",
        "external_identities",
        ["principal_id"],
        unique=False,
    )

    for table in ("tenant_memberships", "auth_sessions", "auth_api_credentials"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("principal_id", sa.String(46), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_principal_id",
                "auth_principals",
                ["principal_id"],
                ["principal_id"],
            )
            batch.create_index(f"ix_{table}_principal_id", ["principal_id"])

    _backfill(op.get_bind())


def _downgrade_preflight(connection) -> None:
    if connection.execute(
        sa.text(
            "SELECT 1 FROM external_identities WHERE issuer <> :issuer LIMIT 1"
        ),
        {"issuer": LEGACY_LOCAL_ISSUER},
    ).first() is not None:
        raise RuntimeError("PRINCIPAL_IDENTITY_PREVENTS_DOWNGRADE")


def downgrade() -> None:
    _downgrade_preflight(op.get_bind())
    for table in ("auth_api_credentials", "auth_sessions", "tenant_memberships"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_principal_id")
            batch.drop_constraint(f"fk_{table}_principal_id", type_="foreignkey")
            batch.drop_column("principal_id")
    op.drop_index("ix_external_identities_principal_id", table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_index("ix_auth_principals_status", table_name="auth_principals")
    op.drop_table("auth_principals")
