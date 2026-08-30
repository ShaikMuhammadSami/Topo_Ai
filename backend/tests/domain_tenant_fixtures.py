"""Opt-in single-boundary fixtures for pre-tenancy domain regressions.

No autouse fixture, production default, or authorization override. Tests that
exercise machine authority opt into UNOWNED_MACHINE separately. Isolation tests
use two real tenants and real authentication instead of this convenience data.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TenantMembershipRecord, TenantRecord
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)

TEST_TENANT = "tenant:dddddddd-dddd-4ddd-8ddd-dddddddddddd"
TEST_HEADERS = {"X-Topo-Tenant-ID": TEST_TENANT}
TEST_CONTEXT = TenantContext(
    tenant_id=TEST_TENANT,
    authenticated_subject="local-development",
    authentication_type="development",
    actor_kind=TenantActorKind.HUMAN,
    selection_source=TenantSelectionSource.HUMAN_HEADER,
)


def seed_domain_tenant(engine, *, subject="local-development"):
    with Session(engine) as session:
        if session.get(TenantRecord, TEST_TENANT) is None:
            session.add(
                TenantRecord(
                    tenant_id=TEST_TENANT,
                    display_name="Domain regression tenant",
                    status="active",
                    created_by_subject=subject,
                    created_at="2026-08-30T00:00:00+00:00",
                    updated_at="2026-08-30T00:00:00+00:00",
                )
            )
            session.flush()
        if (
            session.scalar(
                select(TenantMembershipRecord).where(
                    TenantMembershipRecord.tenant_id == TEST_TENANT,
                    TenantMembershipRecord.subject == subject,
                )
            )
            is None
        ):
            session.add(
                TenantMembershipRecord(
                    membership_id="membership:domain-regression:" + subject,
                    tenant_id=TEST_TENANT,
                    subject=subject,
                    status="active",
                    created_by_subject=subject,
                    created_at="2026-08-30T00:00:00+00:00",
                    updated_at="2026-08-30T00:00:00+00:00",
                )
            )
        session.commit()


def seed_domain_parents(engine, *references):
    """Explicit parents for isolated unit tests that mock derived parent views."""
    from app.db.database import Base
    from test_domain_tenant_migration import _seed_pre_tenancy_row

    with engine.begin() as connection:
        for table_name, identifier in references:
            primary = next(iter(Base.metadata.tables[table_name].primary_key)).name
            _seed_pre_tenancy_row(
                connection,
                table_name,
                **{primary: identifier, "tenant_id": TEST_TENANT},
            )


def null_ownership_inventory(session):
    """Disposable test audit only; no public/global product counting endpoint."""
    from sqlalchemy import func
    from app.db.database import Base
    from app.db.domain_ownership import (
        REQUIRED_OWNERSHIP_TABLES,
        MACHINE_DEPENDENT_WRITERS,
    )

    result = {}
    for name in sorted(REQUIRED_OWNERSHIP_TABLES | MACHINE_DEPENDENT_WRITERS.keys()):
        table = Base.metadata.tables[name]
        result[name] = {
            "total": session.scalar(select(func.count()).select_from(table)),
            "null": session.scalar(
                select(func.count())
                .select_from(table)
                .where(table.c.tenant_id.is_(None))
            ),
        }
    return result
