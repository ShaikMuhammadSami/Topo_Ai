from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AuthApiCredentialRecord,
    AuthPrincipalRecord,
    ExternalIdentityRecord,
    TenantMembershipRecord,
)
from app.db.schema_management import alembic_config, current_revisions, schema_differences
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.principal_identity import LEGACY_LOCAL_ISSUER
from app.services.auth_api_credential_service import create_auth_api_credential
from app.services.auth_api_credential_service import ServiceTenantAccessError
from app.services.principal_identity import (
    create_service_principal,
    provision_external_human_principal,
)
from app.services.tenant_service import (
    add_or_reactivate_tenant_membership,
    create_tenant_with_creator_membership,
)
from test_postgres_runtime_compatibility import _temporary_database, _upgrade
from test_principal_identity_migrations import _seed_0011


pytestmark = pytest.mark.skipif(
    not os.getenv("TOPO_TEST_POSTGRES_URL"),
    reason="set TOPO_TEST_POSTGRES_URL for PostgreSQL 16 principal proof",
)


def test_postgresql_populated_principal_migration_and_reupgrade() -> None:
    with _temporary_database("ph5a_identity_migration") as engine:
        _upgrade(engine, "0011_secret_enforce")
        with engine.begin() as connection:
            _seed_0011(connection)
        _upgrade(engine)
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0013_principal_enforce",)
            assert schema_differences(connection) == ()
            assert connection.scalar(
                text("SELECT COUNT(*) FROM auth_principals")
            ) == 2
            assert connection.scalar(
                text("SELECT COUNT(*) FROM external_identities")
            ) == 1
            assert connection.scalar(
                text("SELECT COUNT(*) FROM tenant_memberships WHERE principal_id IS NULL")
            ) == 0
        with engine.begin() as connection:
            command.downgrade(
                alembic_config(connection=connection),
                "0012_principal_identity",
            )
        assert "subject" in {
            column["name"]
            for column in inspect(engine).get_columns("tenant_memberships")
        }
        _upgrade(engine)


def test_postgresql_same_issuer_subject_concurrency_has_one_principal() -> None:
    with _temporary_database("ph5a_identity_concurrency") as engine:
        _upgrade(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        barrier = Barrier(2)

        def provision(_: int) -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                principal = provision_external_human_principal(
                    session,
                    issuer="urn:test:issuer:concurrent",
                    subject="opaque-subject",
                    display_name="Concurrent human",
                    authentication_type="api_token",
                )
                assert principal.principal_id is not None
                return principal.principal_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(provision, (1, 2)))
        assert len(set(results)) == 1
        with Session(engine) as session:
            assert session.scalar(
                select(func.count()).select_from(ExternalIdentityRecord)
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(AuthPrincipalRecord)
            ) == 1


def test_postgresql_membership_concurrency_is_idempotent() -> None:
    with _temporary_database("ph5a_membership_concurrency") as engine:
        _upgrade(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            admin = provision_external_human_principal(
                session,
                issuer=LEGACY_LOCAL_ISSUER,
                subject="test:admin",
                display_name="Admin",
                authentication_type="api_token",
            )
            target = provision_external_human_principal(
                session,
                issuer="urn:test:issuer:target",
                subject="target",
                display_name="Target",
                authentication_type="api_token",
            )
            tenant = create_tenant_with_creator_membership(
                session,
                display_name="Concurrent tenant",
                creator_subject=admin.subject,
                creator_principal_id=admin.principal_id,
            )
        barrier = Barrier(2)

        def add(_: int) -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                membership = add_or_reactivate_tenant_membership(
                    session,
                    tenant_id=tenant.tenant_id,
                    principal_id=target.principal_id,
                    subject=None,
                    created_by_subject=admin.subject,
                    created_by_principal_id=admin.principal_id,
                )
                return membership.membership_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(add, (1, 2)))
        assert len(set(results)) == 1
        with Session(engine) as session:
            assert session.scalar(
                select(func.count()).select_from(TenantMembershipRecord).where(
                    TenantMembershipRecord.tenant_id == tenant.tenant_id,
                    TenantMembershipRecord.principal_id == target.principal_id,
                )
            ) == 1


def test_postgresql_service_principal_survives_credential_rotation() -> None:
    with _temporary_database("ph5a_service_identity") as engine:
        _upgrade(engine)
        with Session(engine) as session:
            admin = provision_external_human_principal(
                session,
                issuer=LEGACY_LOCAL_ISSUER,
                subject="test:admin",
                display_name="Admin",
                authentication_type="api_token",
            )
            tenant = create_tenant_with_creator_membership(
                session,
                display_name="Service tenant",
                creator_subject=admin.subject,
                creator_principal_id=admin.principal_id,
            )
            first = create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name="first",
                    caller_type=ApiCredentialCallerType.SERVICE_API,
                    subject="service:postgres",
                    roles=[],
                    tenant_id=tenant.tenant_id,
                ),
                created_by_subject=admin.subject,
                created_by_principal_id=admin.principal_id,
            )
            second = create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name="second",
                    caller_type=ApiCredentialCallerType.SERVICE_API,
                    principal_id=first.principal_id,
                    roles=[],
                    tenant_id=tenant.tenant_id,
                ),
                created_by_subject=admin.subject,
                created_by_principal_id=admin.principal_id,
            )
            assert first.principal_id == second.principal_id
            assert session.scalar(
                select(func.count()).select_from(AuthApiCredentialRecord).where(
                    AuthApiCredentialRecord.principal_id == first.principal_id
                )
            ) == 2
            assert session.scalar(
                select(func.count()).select_from(TenantMembershipRecord).where(
                    TenantMembershipRecord.principal_id == first.principal_id
                )
            ) == 0


def test_postgresql_service_principal_tenant_binding_race_has_one_authority() -> None:
    with _temporary_database("ph5a_service_tenant_race") as engine:
        _upgrade(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            admin = provision_external_human_principal(
                session,
                issuer=LEGACY_LOCAL_ISSUER,
                subject="test:admin",
                display_name="Admin",
                authentication_type="api_token",
            )
            tenant_a = create_tenant_with_creator_membership(
                session,
                display_name="Service tenant A",
                creator_subject=admin.subject,
                creator_principal_id=admin.principal_id,
            )
            tenant_b = create_tenant_with_creator_membership(
                session,
                display_name="Service tenant B",
                creator_subject=admin.subject,
                creator_principal_id=admin.principal_id,
            )
            service = create_service_principal(session, display_name="Service")
            session.commit()

        barrier = Barrier(2)

        def create(tenant_id: str) -> str:
            with factory() as session:
                barrier.wait(timeout=10)
                try:
                    result = create_auth_api_credential(
                        session,
                        request=ApiCredentialCreate(
                            name=f"credential for {tenant_id}",
                            caller_type=ApiCredentialCallerType.SERVICE_API,
                            principal_id=service.principal_id,
                            roles=[],
                            tenant_id=tenant_id,
                        ),
                        created_by_subject=admin.subject,
                        created_by_principal_id=admin.principal_id,
                    )
                except ServiceTenantAccessError:
                    session.rollback()
                    return "rejected"
                return result.tenant_id or "missing"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (tenant_a.tenant_id, tenant_b.tenant_id)))
        assert results.count("rejected") == 1
        assert set(results) & {tenant_a.tenant_id, tenant_b.tenant_id}
        with Session(engine) as session:
            assert session.scalar(
                select(func.count()).select_from(AuthApiCredentialRecord).where(
                    AuthApiCredentialRecord.principal_id == service.principal_id
                )
            ) == 1
