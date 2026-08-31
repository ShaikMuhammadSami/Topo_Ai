"""Storage namespaces; never input to source-native identity/hash builders.

Only deterministic/source-local primary keys need a composite namespace.
Opaque authentication locators and server-generated random row IDs stay global.
Migration 0008 has its own frozen copy; it does not import application metadata.
"""

TENANT_LOCAL_PRIMARY_KEYS = {
    "topology_snapshots": "snapshot_id",
    "identity_resolutions": "snapshot_id",
    "signals": "signal_id",
    "changes": "change_id",
    "incident_analyses": "analysis_id",
    "remediation_recommendations": "recommendation_id",
    "recovery_verifications": "verification_id",
    "incidents": "incident_id",
    "incident_outcomes": "outcome_id",
    "ownership_mappings": "ownership_id",
    "webhook_deliveries": "delivery_id",
    "incident_explanations": "explanation_id",
    "incident_investigation_plans": "plan_id",
    "incident_investigation_steps": "step_id",
    "post_incident_reports": "report_id",
    "post_incident_report_actions": "action_item_id",
    "runtime_sensors": "sensor_id",
    "runtime_dependencies": "runtime_dependency_id",
    "runtime_processes": "runtime_process_id",
    "cloud_accounts": "cloud_account_id",
    "cloud_resources": "cloud_resource_id",
    "build_artifact_evidence": "evidence_id",
    "change_events": "event_id",
    "change_entity_links": "link_id",
    "causal_analyses": "analysis_id",
}

# These three keys locate authority; tenant binding is resolved only afterward.
GLOBAL_AUTH_LOCATORS = {
    "agent_enrollment_tokens": "enrollment_token_id",
    "topo_agents": "agent_id",
    "change_sources": "source_id",
}

GLOBAL_RANDOM_STORAGE_KEYS = {
    "identity_overrides": "override_id",
    "webhook_endpoints": "webhook_id",
    "incident_copilot_sessions": "session_id",
    "incident_copilot_messages": "message_id",
    "change_source_deliveries": "delivery_id",
    "change_source_dead_letters": "dead_letter_id",
    "action_approvals": "approval_id",
    "action_approval_events": "event_id",
    "execution_intents": "execution_id",
    "execution_intent_events": "event_id",
}
