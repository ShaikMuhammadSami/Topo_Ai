"""Make principal identity authoritative for membership and credentials.

Revision ID: 0013_principal_enforce
Revises: 0012_principal_identity
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_principal_enforce"
down_revision = "0012_principal_identity"
branch_labels = None
depends_on = None

LEGACY_LOCAL_ISSUER = "urn:topo:auth:legacy-local-v1"


def _exists(connection, query: str, parameters: dict | None = None) -> bool:
    return connection.execute(sa.text(query), parameters or {}).first() is not None


def _preflight(connection) -> None:
    for table in ("tenant_memberships", "auth_sessions", "auth_api_credentials"):
        if _exists(connection, f"SELECT 1 FROM {table} WHERE principal_id IS NULL LIMIT 1"):
            raise RuntimeError("PRINCIPAL_IDENTITY_BACKFILL_INCOMPLETE")
    checks = (
        "SELECT 1 FROM tenant_memberships m LEFT JOIN auth_principals p "
        "ON p.principal_id=m.principal_id WHERE p.principal_id IS NULL "
        "OR p.principal_type <> 'human' LIMIT 1",
        "SELECT 1 FROM auth_sessions s LEFT JOIN auth_principals p "
        "ON p.principal_id=s.principal_id WHERE p.principal_id IS NULL "
        "OR p.principal_type <> 'human' LIMIT 1",
        "SELECT 1 FROM auth_api_credentials c LEFT JOIN auth_principals p "
        "ON p.principal_id=c.principal_id WHERE p.principal_id IS NULL OR "
        "(c.caller_type='human_api' AND p.principal_type <> 'human') OR "
        "(c.caller_type='service_api' AND p.principal_type <> 'service') OR "
        "c.caller_type NOT IN ('human_api','service_api') LIMIT 1",
        "SELECT 1 FROM external_identities e LEFT JOIN auth_principals p "
        "ON p.principal_id=e.principal_id WHERE p.principal_id IS NULL "
        "OR p.principal_type <> 'human' LIMIT 1",
        "SELECT 1 FROM auth_principals p WHERE p.principal_type='human' AND NOT EXISTS "
        "(SELECT 1 FROM external_identities e WHERE e.principal_id=p.principal_id) LIMIT 1",
        "SELECT 1 FROM tenant_memberships GROUP BY tenant_id, principal_id "
        "HAVING COUNT(*) > 1 LIMIT 1",
        "SELECT 1 FROM external_identities GROUP BY issuer, subject "
        "HAVING COUNT(DISTINCT principal_id) > 1 LIMIT 1",
    )
    if any(_exists(connection, query) for query in checks):
        raise RuntimeError("PRINCIPAL_IDENTITY_INTEGRITY_FAILURE")


def upgrade() -> None:
    _preflight(op.get_bind())
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.drop_constraint("uq_tenant_memberships_tenant_subject", type_="unique")
        batch.drop_index("ix_tenant_memberships_subject")
        batch.drop_index("ix_tenant_memberships_active_resolution")
        batch.alter_column(
            "principal_id",
            existing_type=sa.String(46),
            existing_nullable=True,
            nullable=False,
        )
        batch.drop_column("subject")
        batch.create_unique_constraint(
            "uq_tenant_memberships_tenant_principal",
            ["tenant_id", "principal_id"],
        )
        batch.create_index(
            "ix_tenant_memberships_active_resolution",
            ["tenant_id", "principal_id", "status"],
        )
    for table in ("auth_sessions", "auth_api_credentials"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "principal_id",
                existing_type=sa.String(46),
                existing_nullable=True,
                nullable=False,
            )


def _downgrade_preflight(connection) -> None:
    if _exists(
        connection,
        "SELECT 1 FROM tenant_memberships m WHERE NOT EXISTS "
        "(SELECT 1 FROM external_identities e WHERE e.principal_id=m.principal_id "
        "AND e.issuer=:issuer) LIMIT 1",
        {"issuer": LEGACY_LOCAL_ISSUER},
    ) or _exists(
        connection,
        "SELECT 1 FROM tenant_memberships m JOIN external_identities e "
        "ON e.principal_id=m.principal_id AND e.issuer=:issuer "
        "GROUP BY m.tenant_id, e.subject HAVING COUNT(*) > 1 LIMIT 1",
        {"issuer": LEGACY_LOCAL_ISSUER},
    ):
        raise RuntimeError("PRINCIPAL_IDENTITY_PREVENTS_DOWNGRADE")


def downgrade() -> None:
    connection = op.get_bind()
    _downgrade_preflight(connection)
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.drop_constraint(
            "uq_tenant_memberships_tenant_principal",
            type_="unique",
        )
        batch.drop_index("ix_tenant_memberships_active_resolution")
        batch.add_column(sa.Column("subject", sa.String(500), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE tenant_memberships SET subject=(SELECT e.subject FROM "
            "external_identities e WHERE e.principal_id=tenant_memberships.principal_id "
            "AND e.issuer=:issuer)"
        ),
        {"issuer": LEGACY_LOCAL_ISSUER},
    )
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.alter_column(
            "subject",
            existing_type=sa.String(500),
            existing_nullable=True,
            nullable=False,
        )
        batch.create_unique_constraint(
            "uq_tenant_memberships_tenant_subject",
            ["tenant_id", "subject"],
        )
        batch.create_index("ix_tenant_memberships_subject", ["subject"])
        batch.create_index(
            "ix_tenant_memberships_active_resolution",
            ["tenant_id", "subject", "status"],
        )
    for table in ("auth_api_credentials", "auth_sessions"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "principal_id",
                existing_type=sa.String(46),
                existing_nullable=False,
                nullable=True,
            )
