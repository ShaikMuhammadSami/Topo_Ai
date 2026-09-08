"""Closed PH-5D classification of the frozen 98-operation PH-5C plan."""

from __future__ import annotations

from enum import StrEnum


class SecurityAuditInventoryClass(StrEnum):
    AUDIT_ALLOWED_PRIVILEGED_MUTATION = "AUDIT_ALLOWED_PRIVILEGED_MUTATION"
    AUDIT_ALLOWED_SECURITY_READ = "AUDIT_ALLOWED_SECURITY_READ"
    AUDIT_AUTHORIZATION_DENIAL = "AUDIT_AUTHORIZATION_DENIAL"
    OUT_OF_SCOPE_MINIMUM_AUDIT = "OUT_OF_SCOPE_MINIMUM_AUDIT"
    NONATOMIC_OPERATOR_ACTION = "NONATOMIC_OPERATOR_ACTION"


AUDIT_ALLOWED_PRIVILEGED_MUTATION_OPERATIONS = frozenset({
    "app.services.secret_consumers.create_change_source_secure",
    "app.services.secret_consumers.update_change_source_secure",
    "app.services.secret_consumers.create_webhook_endpoint_secure",
    "app.services.secret_consumers.update_webhook_endpoint_secure",
    "app.repositories.identity_repository.upsert_identity_override",
    "app.repositories.identity_repository.deactivate_identity_override",
    "app.services.ownership_resolver.create_ownership_mapping",
    "app.services.tenant_service.add_or_reactivate_tenant_membership",
    "app.services.tenant_service.disable_tenant_membership",
    "app.services.authority_assignments.update_service_permissions",
    "app.repositories.agent_repository.create_enrollment_token",
    "app.repositories.agent_repository.enroll_agent",
    "app.repositories.agent_repository.revoke_agent",
    "app.services.tenant_service.create_tenant_with_creator_membership",
    "app.api.tenants.recover_membership",
    "app.installation_secret_admin._mutate",
    "app.services.authority_assignments.grant_installation_operator",
    "app.services.authority_assignments.disable_installation_operator",
    "authenticator.human.create",
    "authenticator.service.create",
    "authenticator.human.revoke",
    "authenticator.service.revoke",
})

AUDIT_ALLOWED_SECURITY_READ_OPERATIONS = frozenset({
    "app.installation_secret_admin._safe_status",
    "app.services.authority_assignments.get_installation_operator_status",
    "authenticator.service.list",
    "authenticator.service.get",
})

AUDIT_AUTHORIZATION_DENIAL_OPERATIONS = frozenset({
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
})

NONATOMIC_OPERATOR_ACTIONS = frozenset({
    "app.services.secret_legacy_conversion.convert_legacy_secrets",
})

OUT_OF_SCOPE_MINIMUM_AUDIT_OPERATIONS = frozenset({
    "app.services.causal_rca.analyze_causal_rca",
    "app.services.incident_analysis.analyze_incident",
    "app.services.incident_orchestrator.orchestrate_signal",
    "app.services.incident_lifecycle.upsert_incident_from_orchestration",
    "app.services.continuous_lifecycle.ingest_failure_signal_batch",
    "app.services.continuous_lifecycle.process_failure_signal",
    "app.services.continuous_lifecycle.reconcile_pending_incidents_for_checkpoint",
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
    "app.services.topology_checkpoint.persist_topology_checkpoint",
    "app.services.change_source_ingest.replay_dead_letter",
    "app.services.change_event_bridge.promote_normalized_changes",
    "app.services.github_actions_artifact_lineage.enrich_snapshot_with_github_actions_provider_evidence",
    "app.repositories.identity_repository.save_identity_resolution",
    "app.repositories.change_event_repository.ingest_change_event",
    "app.repositories.change_event_repository.correlate_change_event",
    "app.services.webhook_delivery.deliver_event_to_endpoint",
    "app.services.lifecycle_status.build_lifecycle_status",
    "app.services.ownership_resolver.resolve_ownership_by_ids",
    "app.services.business_impact.calculate_incident_ownership_impact",
    "app.services.post_incident_report.render_post_incident_report_markdown",
    "app.repositories.tenant_repository.list_tenant_memberships",
    "app.services.authority_assignments.create_service_permission_assignment",
    "app.services.auth_session_service.create_auth_session",
    "app.services.auth_session_service.resolve_auth_session",
    "app.services.auth_session_service.revoke_auth_session",
    "app.services.auth_api_credential_service.authenticate_auth_api_credential",
    "app.services.agent_snapshot_ingest.persist_agent_snapshot",
    "app.repositories.agent_repository.record_heartbeat",
    "app.repositories.runtime_observability_repository.record_sensor_heartbeat",
    "app.repositories.runtime_observability_repository.ingest_runtime_event_batch",
    "app.services.change_source_ingest.ingest_change_source_webhook",
    "authenticator.human.list",
    "authenticator.human.get",
})

AUTHORIZATION_DENIAL_FAMILIES = frozenset({
    "missing_permission",
    "wrong_authority_kind",
    "membership_missing",
    "service_permission_missing",
    "credential_target_denied",
    "execution_disabled",
    "unknown_operation",
})


AUDIT_OPERATION_INVENTORY = {
    **{
        operation: SecurityAuditInventoryClass.AUDIT_ALLOWED_PRIVILEGED_MUTATION
        for operation in AUDIT_ALLOWED_PRIVILEGED_MUTATION_OPERATIONS
    },
    **{
        operation: SecurityAuditInventoryClass.AUDIT_ALLOWED_SECURITY_READ
        for operation in AUDIT_ALLOWED_SECURITY_READ_OPERATIONS
    },
    **{
        operation: SecurityAuditInventoryClass.AUDIT_AUTHORIZATION_DENIAL
        for operation in AUDIT_AUTHORIZATION_DENIAL_OPERATIONS
    },
    **{
        operation: SecurityAuditInventoryClass.OUT_OF_SCOPE_MINIMUM_AUDIT
        for operation in OUT_OF_SCOPE_MINIMUM_AUDIT_OPERATIONS
    },
    **{
        operation: SecurityAuditInventoryClass.NONATOMIC_OPERATOR_ACTION
        for operation in NONATOMIC_OPERATOR_ACTIONS
    },
}
