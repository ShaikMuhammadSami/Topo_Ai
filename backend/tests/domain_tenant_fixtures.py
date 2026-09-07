"""Opt-in single-boundary fixtures for pre-tenancy domain regressions.

No autouse fixture, production default, or authorization override. Tests that
exercise machine authority explicitly seed the same real tenant. Isolation tests
use two real tenants and real authentication instead of this convenience data.
"""

from functools import wraps
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
    principal_id="principal:dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    authenticated_subject="local-development",
    authentication_type="development",
    actor_kind=TenantActorKind.HUMAN,
    selection_source=TenantSelectionSource.HUMAN_HEADER,
)


def seed_domain_tenant(engine, *, subject="local-development"):
    from app.models.principal_identity import DEVELOPMENT_ISSUER, LEGACY_LOCAL_ISSUER
    from app.services.principal_identity import provision_external_human_principal

    with Session(engine) as session:
        principal = provision_external_human_principal(
            session,
            issuer=(
                DEVELOPMENT_ISSUER
                if subject == "local-development"
                else LEGACY_LOCAL_ISSUER
            ),
            subject=subject,
            display_name=subject,
            authentication_type=(
                "development" if subject == "local-development" else "api_token"
            ),
        )
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
                    TenantMembershipRecord.principal_id == principal.principal_id,
                )
            )
            is None
        ):
            session.add(
                TenantMembershipRecord(
                    membership_id="membership:domain-regression:" + subject,
                    tenant_id=TEST_TENANT,
                    principal_id=principal.principal_id,
                    role="tenant_admin",
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
            primary = next(column.name for column in Base.metadata.tables[table_name].primary_key if column.name != "tenant_id")
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


def owned_world_fixture(function):
    """Explicit ownership on mocked service results in single-tenant unit tests.

    Real boundary tests use repositories and two tenants. This only replaces
    the ownership attestation that an intentionally mocked producer would make.
    """
    from app.services.tenant_world_model import bind_world_value

    @wraps(function)
    def fixture(*args, **kwargs):
        return bind_world_value(function(*args, **kwargs), tenant_id=TEST_TENANT)
    return fixture
