"""PH-4B isolated encrypted secret custody; no legacy conversion or key material."""

from alembic import op
import sqlalchemy as sa

revision = "0009_secret_store"
down_revision = "0008_tenant_scoped_identity_namespace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "secret_records",
        sa.Column("secret_ref", sa.String(64), primary_key=True),
        sa.Column("scope_kind", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("owner_type", sa.String(40), nullable=False),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("previous_accept_until", sa.String(50), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.String(50), nullable=False),
        sa.Column("created_by_subject", sa.String(500), nullable=False),
        sa.Column("updated_by_subject", sa.String(500), nullable=False),
        sa.Column("revoked_at", sa.String(50), nullable=True),
        sa.UniqueConstraint("scope_kind", "scope_id", "owner_type", "owner_id", "purpose", name="uq_secret_records_binding"),
        sa.CheckConstraint("(scope_kind = 'tenant' AND tenant_id IS NOT NULL AND scope_id = tenant_id) OR (scope_kind = 'installation' AND tenant_id IS NULL)", name="ck_secret_records_scope"),
        sa.CheckConstraint("status IN ('active', 'revoked') AND active_version >= 1 AND row_version >= 1", name="ck_secret_records_state"),
        sa.CheckConstraint("(previous_version IS NULL AND previous_accept_until IS NULL) OR (previous_version IS NOT NULL AND previous_accept_until IS NOT NULL AND previous_version >= 1 AND previous_version < active_version)", name="ck_secret_records_previous"),
    )
    op.create_table(
        "secret_versions",
        sa.Column("secret_ref", sa.String(64), sa.ForeignKey("secret_records.secret_ref", name="fk_secret_versions_record"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.String(20), nullable=False),
        sa.Column("envelope_version", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(12), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("operation_kind", sa.String(20), nullable=False),
        sa.Column("overlap_seconds", sa.Integer(), nullable=False),
        sa.Column("envelope_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(50), nullable=False),
        sa.Column("created_by_subject", sa.String(500), nullable=False),
        sa.Column("rewrapped_at", sa.String(50), nullable=True),
        sa.Column("rewrapped_by_subject", sa.String(500), nullable=True),
        sa.UniqueConstraint("secret_ref", "operation_id", name="uq_secret_versions_operation"),
        sa.CheckConstraint("version >= 1 AND envelope_revision >= 1 AND overlap_seconds >= 0 AND overlap_seconds <= 86400", name="ck_secret_versions_state"),
    )


def downgrade():
    # Explicitly destructive only for this store; operators must back up first.
    op.drop_table("secret_versions")
    op.drop_table("secret_records")
