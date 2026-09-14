"""Adversarial runtime proof for the PH-5C authorization boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    AuthApiCredentialRecord,
    AuthPrincipalRecord,
    ServiceApiTenantBindingRecord,
    TenantMembershipRecord,
    TenantRecord,
)
from app.models.principal_identity import new_principal_id
from app.repositories import tenant_repository
from app.security.authorization_enforcement import (
    AuthorizationContext,
    AuthorizationFailure,
    AuthorityKind,
    authorize_authentication_self_service,
    authorize_installation,
    authorize_service_operation,
    authorize_tenant,
    require_route_authorization,
)
from app.security.authorization_plan import CRITICAL_OPERATION_PLAN
from app.security.authorization_policy import Permission
from app.security.principals import AuthPrincipal
from app.security.tenant_context import (
    TenantActorKind,
    TenantContext,
    TenantSelectionSource,
)
from app.services.authority_assignments import (
    AuthorityAssignmentError,
    create_service_permission_assignment,
    disable_installation_operator,
    grant_installation_operator,
)
from app.services.principal_identity import PrincipalNotProvisionedError
from test_authentication_acceptance import _registered_routes


NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
APP = Path(__file__).resolve().parents[1] / "app"

# These operation IDs contain an executable call to the central operation
# guard.  The remaining frozen entries are route-bound or are reached only
# below one of these exact guarded automatic-workflow roots.  This inventory is
# deliberately explicit so a new PH-5B operation cannot silently become
# "delegated" by set-complement alone.
DIRECTLY_GUARDED_OPERATIONS = frozenset(
    {
        "app.services.topology_checkpoint.persist_topology_checkpoint",
        "app.services.continuous_lifecycle.ingest_failure_signal_batch",
        "app.services.continuous_lifecycle.reconcile_pending_incidents_for_checkpoint",
        "app.services.agent_snapshot_ingest.persist_agent_snapshot",
        "app.repositories.agent_repository.enroll_agent",
        "app.repositories.agent_repository.record_heartbeat",
        "app.repositories.runtime_observability_repository.record_sensor_heartbeat",
        "app.repositories.runtime_observability_repository.ingest_runtime_event_batch",
        "app.services.change_source_ingest.ingest_change_source_webhook",
        "app.services.action_approval.create_action_approval",
        "app.services.action_approval.get_action_approval",
        "app.services.action_approval.list_action_approvals",
        "app.services.action_approval.decide_action_approval",
        "app.services.action_approval.revoke_action_approval",
        "app.services.execution_transaction.create_execution_intent",
        "app.services.execution_transaction.get_execution_intent",
        "app.services.execution_transaction.list_execution_intents",
        "app.services.execution_transaction.cancel_execution_intent",
        "app.services.execution_transaction.claim_execution_intent",
        "app.services.execution_transaction.release_execution_claim",
        "authenticator.human.create",
        "authenticator.service.create",
        "authenticator.human.list",
        "authenticator.service.list",
        "authenticator.human.get",
        "authenticator.service.get",
        "authenticator.human.revoke",
        "authenticator.service.revoke",
    }
)

DELEGATED_TO_GUARD_OPERATIONS = frozenset(
    {
        "app.services.causal_rca.analyze_causal_rca",
        "app.services.incident_analysis.analyze_incident",
        "app.services.incident_orchestrator.orchestrate_signal",
        "app.services.incident_lifecycle.upsert_incident_from_orchestration",
        "app.services.continuous_lifecycle.process_failure_signal",
        "app.services.incident_copilot.create_incident_copilot_session",
        "app.services.incident_copilot.answer_copilot_question",
        "app.services.incident_explanation.generate_incident_explanation",
        "app.services.incident_outcome.record_incident_outcome",
        "app.services.investigation_planner.generate_investigation_plan",
        "app.services.post_incident_report.generate_post_incident_report",
        "app.services.predeployment_impact.analyze_predeployment_impact",
        "app.services.recommendation_engine.generate_recommendations",
        "app.services.recovery_verification.verify_recovery",
        "app.repositories.incident_record_repository.update_incident_status",
        "app.repositories.investigation_plan_repository.update_investigation_step",
        "app.repositories.post_incident_report_repository.update_post_incident_report",
        "app.repositories.post_incident_report_repository.update_report_action_item",
        "app.repositories.recommendation_repository.update_recommendation_status",
        "app.services.incident_briefing.build_incident_briefing",
        "app.services.incident_context.build_incident_operational_context",
        "app.services.incident_outcome.get_incident_outcome",
        "app.services.incident_similarity.build_historical_incident_intelligence",
        "app.services.response_intelligence.build_incident_response_intelligence",
        "app.services.response_plan.build_incident_response_plan",
        "app.services.lifecycle_status.build_incident_lifecycle_status",
        "app.services.incident_change_analysis.analyze_incident_change_events",
        "app.services.execution_readiness.build_incident_execution_readiness",
        "app.repositories.causal_analysis_repository.latest_causal_analysis",
        "app.repositories.causal_analysis_repository.load_causal_analysis",
        "app.services.blast_radius.calculate_blast_radius",
        "app.services.network_dependency_analysis.analyze_network_dependencies",
        "app.services.identity_resolver.resolve_kubernetes_identities",
        "app.services.change_source_ingest.replay_dead_letter",
        "app.services.change_event_bridge.promote_normalized_changes",
        "app.services.github_actions_artifact_lineage.enrich_snapshot_with_github_actions_provider_evidence",
        "app.repositories.identity_repository.save_identity_resolution",
        "app.repositories.change_event_repository.ingest_change_event",
        "app.repositories.change_event_repository.correlate_change_event",
        "app.services.webhook_delivery.deliver_event_to_endpoint",
        "app.services.lifecycle_status.build_lifecycle_status",
        "app.services.secret_consumers.create_change_source_secure",
        "app.services.secret_consumers.update_change_source_secure",
        "app.services.secret_consumers.create_webhook_endpoint_secure",
        "app.services.secret_consumers.update_webhook_endpoint_secure",
        "app.repositories.identity_repository.upsert_identity_override",
        "app.repositories.identity_repository.deactivate_identity_override",
        "app.services.ownership_resolver.create_ownership_mapping",
        "app.services.ownership_resolver.resolve_ownership_by_ids",
        "app.services.business_impact.calculate_incident_ownership_impact",
        "app.services.post_incident_report.render_post_incident_report_markdown",
        "app.services.tenant_service.add_or_reactivate_tenant_membership",
        "app.services.tenant_service.disable_tenant_membership",
        "app.repositories.tenant_repository.list_tenant_memberships",
        "app.services.authority_assignments.create_service_permission_assignment",
        "app.services.authority_assignments.update_service_permissions",
        "app.repositories.agent_repository.create_enrollment_token",
        "app.repositories.agent_repository.revoke_agent",
        "app.services.tenant_service.create_tenant_with_creator_membership",
        "app.api.tenants.recover_membership",
        "app.installation_secret_admin._safe_status",
        "app.installation_secret_admin._mutate",
        "app.services.secret_legacy_conversion.convert_legacy_secrets",
        "app.services.authority_assignments.get_installation_operator_status",
        "app.services.authority_assignments.grant_installation_operator",
        "app.services.authority_assignments.disable_installation_operator",
        "app.services.auth_session_service.create_auth_session",
        "app.services.auth_session_service.resolve_auth_session",
        "app.services.auth_session_service.revoke_auth_session",
        "app.services.auth_api_credential_service.authenticate_auth_api_credential",
    }
)


@pytest.fixture()
def authority_factory():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _human(
    session: Session,
    *,
    tenant_id: str,
    role: str = "tenant_viewer",
    legacy_roles: tuple[str, ...] = (),
) -> tuple[AuthPrincipalRecord, AuthPrincipal, TenantContext]:
    principal_record = AuthPrincipalRecord(
        principal_id=new_principal_id(),
        principal_type="human",
        display_name="Authorization human",
        status="active",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    tenant = session.get(TenantRecord, tenant_id)
    if tenant is None:
        tenant = TenantRecord(
            tenant_id=tenant_id,
            display_name=tenant_id,
            status="active",
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
            created_by_subject="fixture",
        )
        session.add(tenant)
    membership = TenantMembershipRecord(
        membership_id=f"membership:{uuid4()}",
        tenant_id=tenant_id,
        principal_id=principal_record.principal_id,
        role=role,
        status="active",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by_subject="fixture",
    )
    session.add_all([principal_record, membership])
    session.commit()
    principal = AuthPrincipal(
        principal_id=principal_record.principal_id,
        principal_type="human",
        subject=f"fixture:{principal_record.principal_id}",
        display_name=principal_record.display_name,
        roles=legacy_roles,
        authentication_type="human_api_token",
    )
    context = TenantContext(
        tenant_id=tenant_id,
        principal_id=principal_record.principal_id,
        authenticated_subject=principal.subject,
        authentication_type=principal.authentication_type,
        actor_kind=TenantActorKind.HUMAN,
        selection_source=TenantSelectionSource.HUMAN_HEADER,
        membership_id=membership.membership_id,
    )
    return principal_record, principal, context


def _service(
    session: Session,
    *,
    tenant_id: str,
    permissions: list[str] | None,
) -> tuple[AuthPrincipalRecord, AuthPrincipal, TenantContext]:
    principal_record = AuthPrincipalRecord(
        principal_id=new_principal_id(),
        principal_type="service",
        display_name="Authorization service",
        status="active",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
    )
    session.add(principal_record)
    if session.get(TenantRecord, tenant_id) is None:
        session.add(
            TenantRecord(
                tenant_id=tenant_id,
                display_name=tenant_id,
                status="active",
                created_at=NOW.isoformat(),
                updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            )
        )
    session.commit()
    if permissions is not None:
        create_service_permission_assignment(
            session,
            principal_id=principal_record.principal_id,
            permissions=permissions,
            now=NOW,
        )
    credential_id = f"api-credential:{uuid4()}"
    session.add(
        AuthApiCredentialRecord(
            credential_id=credential_id,
            credential_secret_digest=uuid4().hex * 2,
            credential_hint=uuid4().hex[-8:],
            name="fixture",
            caller_type="service_api",
            principal_id=principal_record.principal_id,
            subject="fixture-service",
            display_name="Authorization service",
            roles_json="[]",
            created_at=NOW.isoformat(),
            created_by_subject="fixture",
            expires_at=(NOW + timedelta(days=1)).isoformat(),
            revoked_at=None,
            revoked_by_subject=None,
            last_used_at=None,
            updated_at=NOW.isoformat(),
        )
    )
    session.add(
        ServiceApiTenantBindingRecord(
            binding_id=f"binding:{uuid4()}",
            credential_id=credential_id,
            tenant_id=tenant_id,
            created_at=NOW.isoformat(),
            created_by_subject="fixture",
        )
    )
    session.commit()
    principal = AuthPrincipal(
        principal_id=principal_record.principal_id,
        principal_type="service",
        subject="fixture-service",
        display_name=principal_record.display_name,
        roles=("admin", "operator"),
        authentication_type="service_api_token",
    )
    context = TenantContext(
        tenant_id=tenant_id,
        principal_id=principal_record.principal_id,
        authenticated_subject=principal.subject,
        authentication_type=principal.authentication_type,
        actor_kind=TenantActorKind.SERVICE,
        selection_source=TenantSelectionSource.SERVICE_BINDING,
        credential_id=credential_id,
    )
    return principal_record, principal, context


def test_every_live_route_is_bound_to_the_single_global_runtime_guard(
    required_auth_app,
) -> None:
    routes = _registered_routes(required_auth_app)
    assert len(routes) == 144
    assert [item.dependency for item in required_auth_app.router.dependencies] == [
        require_route_authorization
    ]


def test_operation_enforcement_inventory_is_complete_and_explicit() -> None:
    assert len(DIRECTLY_GUARDED_OPERATIONS) == 28
    assert len(DELEGATED_TO_GUARD_OPERATIONS) == 70
    assert not (DIRECTLY_GUARDED_OPERATIONS & DELEGATED_TO_GUARD_OPERATIONS)
    assert (
        DIRECTLY_GUARDED_OPERATIONS | DELEGATED_TO_GUARD_OPERATIONS
    ) == set(CRITICAL_OPERATION_PLAN)
    product_source = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in APP.rglob("*.py")
        if path.name != "authorization_plan.py"
    )
    for operation_id in DIRECTLY_GUARDED_OPERATIONS:
        if operation_id.startswith("authenticator."):
            continue
        assert operation_id in product_source
    assert "authorize_service_operation(" in product_source


def test_human_permissions_are_current_tenant_membership_only(
    authority_factory,
) -> None:
    with authority_factory() as session:
        record, principal, tenant_context = _human(
            session,
            tenant_id="tenant:viewer",
            legacy_roles=("admin", "operator", "superuser"),
        )
        allowed = authorize_tenant(
            session,
            principal=principal,
            tenant_context=tenant_context,
            required_permissions=frozenset({Permission.INCIDENT_READ}),
        )
        assert allowed.authority_kind is AuthorityKind.HUMAN_TENANT
        assert Permission.INCIDENT_READ in allowed.effective_permissions
        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=tenant_context,
                required_permissions=frozenset({Permission.INCIDENT_RESPOND}),
            )
        record.status = "disabled"
        session.commit()
        with pytest.raises(PrincipalNotProvisionedError):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=tenant_context,
                required_permissions=frozenset(),
            )


def test_forged_or_missing_human_tenant_scope_is_rejected(authority_factory) -> None:
    with authority_factory() as session:
        _, principal, context = _human(session, tenant_id="tenant:a")
        session.add(
            TenantRecord(
                tenant_id="tenant:b",
                display_name="Tenant B",
                status="active",
                created_at=NOW.isoformat(),
                updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            )
        )
        session.commit()
        with pytest.raises(AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=replace(context, tenant_id="tenant:b"),
                required_permissions=frozenset(),
            )
        membership = session.get(TenantMembershipRecord, context.membership_id)
        assert membership is not None
        membership.status = "disabled"
        session.commit()
        with pytest.raises(AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=context,
                required_permissions=frozenset(),
            )


def test_service_permissions_require_one_durable_binding_and_assignment(
    authority_factory,
) -> None:
    with authority_factory() as session:
        _, principal, context = _service(
            session,
            tenant_id="tenant:service",
            permissions=["incident.read"],
        )
        allowed = authorize_tenant(
            session,
            principal=principal,
            tenant_context=context,
            required_permissions=frozenset({Permission.INCIDENT_READ}),
        )
        assert allowed.authority_kind is AuthorityKind.SERVICE_TENANT
        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=context,
                required_permissions=frozenset({Permission.EVIDENCE_READ}),
            )
        _, unassigned, unassigned_context = _service(
            session,
            tenant_id="tenant:unassigned",
            permissions=None,
        )
        with pytest.raises(
            AuthorityAssignmentError, match="SERVICE_PERMISSIONS_UNAVAILABLE"
        ):
            authorize_tenant(
                session,
                principal=unassigned,
                tenant_context=unassigned_context,
                required_permissions=frozenset(),
            )


def test_forged_service_tenant_scope_is_rejected(authority_factory) -> None:
    with authority_factory() as session:
        _, principal, context = _service(
            session,
            tenant_id="tenant:service-a",
            permissions=["incident.read"],
        )
        session.add(
            TenantRecord(
                tenant_id="tenant:service-b",
                display_name="Service B",
                status="active",
                created_at=NOW.isoformat(),
                updated_at=NOW.isoformat(),
                created_by_subject="fixture",
            )
        )
        session.commit()
        with pytest.raises(AuthorizationFailure, match="AUTHORITY_SCOPE_MISMATCH"):
            authorize_tenant(
                session,
                principal=principal,
                tenant_context=replace(context, tenant_id="tenant:service-b"),
                required_permissions=frozenset(),
            )


def test_installation_authority_is_current_human_assignment_only(
    authority_factory,
) -> None:
    with authority_factory() as session:
        record, principal, _ = _human(session, tenant_id="tenant:operator")
        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_installation(
                session,
                principal=principal,
                required_permissions=frozenset({Permission.INSTALLATION_STATUS_READ}),
            )
        grant_installation_operator(session, principal_id=record.principal_id)
        context = authorize_installation(
            session,
            principal=principal,
            required_permissions=frozenset({Permission.INSTALLATION_STATUS_READ}),
        )
        assert context.authority_kind is AuthorityKind.INSTALLATION
        assert context.tenant_id is None
        disable_installation_operator(session, principal_id=record.principal_id)
        with pytest.raises(AuthorizationFailure, match="PERMISSION_DENIED"):
            authorize_installation(
                session,
                principal=principal,
                required_permissions=frozenset({Permission.INSTALLATION_STATUS_READ}),
            )


def test_context_construction_unknown_operation_wrong_kind_and_dormant_deny() -> None:
    with pytest.raises(TypeError):
        AuthorizationContext(  # type: ignore[call-arg]
            actor_principal_id="principal:forged",
            actor_principal_type="human",
            authority_kind=AuthorityKind.HUMAN_TENANT,
            tenant_id="tenant:forged",
            effective_permissions=frozenset({Permission.TENANT_SETTINGS_MANAGE}),
            authentication_provenance="payload",
        )
    with pytest.raises(
        AuthorizationFailure, match="UNKNOWN_AUTHORIZATION_OPERATION"
    ):
        authorize_service_operation("caller.supplied.operation")
    with pytest.raises(AuthorizationFailure, match="AUTHORIZATION_CONTEXT_REQUIRED"):
        authorize_service_operation(
            "app.services.topology_checkpoint.persist_topology_checkpoint"
        )
    self_context = authorize_authentication_self_service(
        AuthPrincipal(
            principal_id=new_principal_id(),
            principal_type="human",
            subject="fixture:self",
            display_name="Self",
            roles=("admin",),
            authentication_type="human_api_token",
        )
    )
    with pytest.raises(AuthorizationFailure, match="AUTHORITY_KIND_MISMATCH"):
        authorize_service_operation(
            "app.services.topology_checkpoint.persist_topology_checkpoint",
            authorization_context=self_context,
        )
    with pytest.raises(AuthorizationFailure, match="V1_EXECUTION_DISABLED"):
        authorize_service_operation(
            "app.services.action_approval.create_action_approval",
            authorization_context=self_context,
        )
