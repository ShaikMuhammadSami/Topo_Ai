"""Historical metadata expectations, including pre-PH-3F global identities.

No historical migration imports current product models. Tests that explicitly
stop at 0007 or earlier must compare against the historical key shape, not HEAD.
"""

from sqlalchemy import (
    CheckConstraint, Column, ForeignKeyConstraint, Index, MetaData,
    PrimaryKeyConstraint, String, Text, UniqueConstraint,
)

from app.db.database import Base
from app.db.schema_management import script_directory


SECRET_STORE_TABLES = {"secret_records", "secret_versions"}
PRINCIPAL_TABLES = {"auth_principals", "external_identities"}


def frozen_0008_metadata():
    """PH-3's exact 43-table contract, before the additive secret store."""
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        if table.name not in SECRET_STORE_TABLES | PRINCIPAL_TABLES:
            copied = table.to_metadata(metadata)
            if copied.name in {
                "auth_sessions",
                "auth_api_credentials",
                "tenant_memberships",
            }:
                for index in list(copied.indexes):
                    if "principal_id" in {column.name for column in index.columns}:
                        copied.indexes.remove(index)
                for constraint in list(copied.constraints):
                    if isinstance(constraint, ForeignKeyConstraint) and {
                        element.parent.name for element in constraint.elements
                    } == {"principal_id"}:
                        copied.constraints.remove(constraint)
                    if (
                        copied.name == "tenant_memberships"
                        and isinstance(constraint, UniqueConstraint)
                        and constraint.name == "uq_tenant_memberships_tenant_principal"
                    ):
                        copied.constraints.remove(constraint)
                for foreign_key in list(copied.c.principal_id.foreign_keys):
                    copied.c.principal_id.foreign_keys.remove(foreign_key)
                    copied.foreign_keys.remove(foreign_key)
                copied._columns.remove(copied.c.principal_id)
            if copied.name == "tenant_memberships":
                copied.append_column(Column("subject", String(500), nullable=False))
                copied.append_constraint(
                    UniqueConstraint(
                        "tenant_id",
                        "subject",
                        name="uq_tenant_memberships_tenant_subject",
                    )
                )
                Index("ix_tenant_memberships_subject", copied.c.subject)
                Index(
                    "ix_tenant_memberships_active_resolution",
                    copied.c.tenant_id,
                    copied.c.subject,
                    copied.c.status,
                )
            if copied.name == "change_sources":
                copied.c.secret_ref.type = String(255)
                for constraint in list(copied.constraints):
                    if isinstance(constraint, CheckConstraint) and constraint.name in {
                        "ck_change_sources_secret_ref",
                        "ck_change_sources_enabled_secret",
                    }:
                        copied.constraints.remove(constraint)
            if copied.name == "webhook_endpoints":
                for name in (
                    "signing_secret_ref", "protected_headers_secret_ref",
                    "protected_header_names_json",
                ):
                    copied._columns.remove(copied.c[name])
                for constraint in list(copied.constraints):
                    if isinstance(constraint, CheckConstraint) and constraint.name in {
                        "ck_webhook_signing_secret_ref",
                        "ck_webhook_headers_secret_ref",
                    }:
                        copied.constraints.remove(constraint)
                copied.append_column(Column("headers_json", Text(), nullable=False))
                copied.append_column(Column("signing_secret", Text(), nullable=True))
    return metadata


def frozen_0007_metadata():
    metadata = MetaData()
    namespace = script_directory().get_revision("0008_tenant_scoped_identity_namespace").module
    for table in frozen_0008_metadata().tables.values():
        copied = table.to_metadata(metadata)
        key = namespace.LOCAL_KEYS.get(table.name)
        if key:
            copied.constraints.remove(copied.primary_key)
            copied.c.tenant_id.primary_key = False
            copied.append_constraint(PrimaryKeyConstraint(key))
        if table.name in namespace.GLOBAL_UNIQUES:
            name, columns = namespace.GLOBAL_UNIQUES[table.name]
            copied.append_constraint(UniqueConstraint(*columns, name=name))
        for column in namespace.GLOBAL_INDEXES.get(table.name, ()):
            Index(f"ix_{table.name}_{column}", copied.c[column], unique=True)
    return metadata
