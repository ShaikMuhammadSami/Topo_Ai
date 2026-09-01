"""Add conversion-only provider/webhook SecretStore references.

Revision ID: 0010_secret_refs
Revises: 0009_secret_store

No credential is read, encrypted, inferred, or removed here. Normal application
startup remains schema-behind until the explicit conversion and 0011 upgrade.
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_secret_refs"
down_revision = "0009_secret_store"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "webhook_endpoints",
        sa.Column("signing_secret_ref", sa.String(64), nullable=True),
    )
    op.add_column(
        "webhook_endpoints",
        sa.Column("protected_headers_secret_ref", sa.String(64), nullable=True),
    )
    op.add_column(
        "webhook_endpoints",
        sa.Column(
            "protected_header_names_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade():
    connection = op.get_bind()
    source_refs = connection.execute(
        sa.text(
            "SELECT secret_ref FROM change_sources "
            "WHERE secret_ref LIKE 'secret:%' LIMIT 1"
        )
    ).first()
    webhook_refs = connection.execute(
        sa.text(
            "SELECT 1 FROM webhook_endpoints "
            "WHERE signing_secret_ref IS NOT NULL "
            "OR protected_headers_secret_ref IS NOT NULL LIMIT 1"
        )
    ).first()
    if source_refs is not None or webhook_refs is not None:
        raise RuntimeError("SECRET_CONSUMER_REFERENCES_PREVENT_DOWNGRADE")

    with op.batch_alter_table("webhook_endpoints") as batch:
        batch.drop_column("protected_header_names_json")
        batch.drop_column("protected_headers_secret_ref")
        batch.drop_column("signing_secret_ref")

