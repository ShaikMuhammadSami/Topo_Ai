"""Real PostgreSQL 16 READ COMMITTED proof for PH-5C decisions."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.security.authorization_enforcement import (
    AuthorizationFailure,
    authorize_installation,
    authorize_tenant,
)
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)
from app.services.authority_assignments import (
    disable_installation_operator,
    grant_installation_operator,
    update_service_permissions,
)
from test_minimum_authority_migrations import (
    HUMAN_A,
    SERVICE_A,
    TENANT_A,
    TENANT_B,
    _migrate,
    _seed_0013,
)
from test_postgres_runtime_compatibility import _temporary_database


pytestmark = pytest.mark.skipif(
    not os.getenv("TOPO_TEST_POSTGRES_URL"),
    reason="set TOPO_TEST_POSTGRES_URL for real PostgreSQL 16 PH-5C proof",
)


def _human() -> tuple[AuthPrincipal, TenantContext]:
    principal = AuthPrincipal(
        principal_id=HUMAN_A,
        principal_type="human",
        subject=HUMAN_A,
        display_name="PostgreSQL human",
        roles=("admin", "operator", "superuser"),
        authentication_type="human_api_token",
    )
    context = TenantContext(
        tenant_id=TENANT_A,
        principal_id=HUMAN_A,
        authenticated_subject=HUMAN_A,
        authentication_type="human_api_token",
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id="membership:authority-1",
    )
    return principal, context


def _service() -> tuple[AuthPrincipal, TenantContext]:
    principal = AuthPrincipal(
        principal_id=SERVICE_A,
        principal_type="service",
        subject=SERVICE_A,
        display_name="PostgreSQL service",
        roles=("admin",),
        authentication_type="service_api_token",
    )
    context = TenantContext(
        tenant_id=TENANT_A,
        principal_id=SERVICE_A,
        authenticated_subject=SERVICE_A,
        authentication_type="service_api_token",
        actor_kind=TenantActorKind.SERVICE,
        selection_source=TenantSelectionSource.SERVICE_BINDING,
        credential_id="credential:authority-1",
    )
    return principal, context


def test_postgresql_next_request_sees_role_membership_and_operator_changes() -> None:
    with _temporary_database("ph5c_human_current") as engine:
        _migrate(engine, "0013_principal_enforce")
        _seed_0013(engine)
        _migrate(engine)
        principal, context = _human()
        with Session(engine) as reader:
            authorize_tenant(
                reader,
                principal=principal,
                tenant_context=context,
                required_permissions=frozenset(
                    {Permission.TENANT_SETTINGS_MANAGE}
                ),
            )
        with engine.begin() as writer:
            writer.execute(
                text(
                    "UPDATE tenant_memberships SET role='tenant_viewer' "
                    "WHERE membership_id='membership:authority-1'"
                )
            )
        with Session(engine) as next_request:
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_tenant(
                    next_request,
                    principal=principal,
                    tenant_context=context,
                    required_permissions=frozenset(
                        {Permission.TENANT_SETTINGS_MANAGE}
                    ),
                )
            grant_installation_operator(
                next_request, principal_id=principal.principal_id or ""
            )
            next_request.commit()
        with Session(engine) as operator_request:
            authorize_installation(
                operator_request,
                principal=principal,
                required_permissions=frozenset(
                    {Permission.INSTALLATION_STATUS_READ}
                ),
            )
            disable_installation_operator(
                operator_request, principal_id=principal.principal_id or ""
            )
        with Session(engine) as next_request:
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_installation(
                    next_request,
                    principal=principal,
                    required_permissions=frozenset(
                        {Permission.INSTALLATION_STATUS_READ}
                    ),
                )
        with engine.begin() as writer:
            writer.execute(
                text(
                    "UPDATE tenant_memberships SET status='disabled' "
                    "WHERE membership_id='membership:authority-1'"
                )
            )
        with Session(engine) as next_request:
            with pytest.raises(
                AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"
            ):
                authorize_tenant(
                    next_request,
                    principal=principal,
                    tenant_context=context,
                    required_permissions=frozenset(),
                )


def test_postgresql_service_reduction_and_fixed_tenant_are_immediate() -> None:
    with _temporary_database("ph5c_service_current") as engine:
        _migrate(engine, "0013_principal_enforce")
        _seed_0013(engine)
        _migrate(engine)
        principal, context = _service()
        with Session(engine) as request:
            authorize_tenant(
                request,
                principal=principal,
                tenant_context=context,
                required_permissions=frozenset({Permission.INTEGRATION_MANAGE}),
            )
            update_service_permissions(
                request,
                principal_id=SERVICE_A,
                permissions=["incident.read"],
                expected_row_version=1,
            )
        with Session(engine) as next_request:
            with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
                authorize_tenant(
                    next_request,
                    principal=principal,
                    tenant_context=context,
                    required_permissions=frozenset(
                        {Permission.INTEGRATION_MANAGE}
                    ),
                )
            authorize_tenant(
                next_request,
                principal=principal,
                tenant_context=context,
                required_permissions=frozenset({Permission.INCIDENT_READ}),
            )
            with pytest.raises(
                AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"
            ):
                authorize_tenant(
                    next_request,
                    principal=principal,
                    tenant_context=replace(context, tenant_id=TENANT_B),
                    required_permissions=frozenset(),
                )

