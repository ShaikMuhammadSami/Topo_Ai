"""PH-3D writer inventory, not a tenant selection or authorization mechanism.

Every listed writer now receives an explicit boundary. Machine-dependent
writers retain NULL only at the authenticated, unbound PH-3E entry points.
"""

# Human/service or background work rooted in an already tenant-owned object.
REQUIRED_OWNERSHIP_WRITERS = {
    "identity_resolutions": "identities.materialize_snapshot_identities -> save_identity_resolution",
    "identity_overrides": "identities.create_identity_override -> upsert_identity_override",
    "incident_analyses": "incidents.analyze_signal_incident / incident_orchestrator.orchestrate_signal",
    "remediation_recommendations": "recommendations.generate_analysis_recommendations / incident_orchestrator.orchestrate_signal",
    "recovery_verifications": "recovery API -> recovery_repository",
    "ownership_mappings": "ownership.create_mapping -> ownership_resolver",
    "webhook_endpoints": "webhooks management -> webhook_repository",
    "incident_explanations": "incident_explanation.generate_incident_explanation",
    "incident_copilot_sessions": "incident_copilot -> copilot_repository",
    "incident_copilot_messages": "incident_copilot -> copilot_repository",
    "incident_investigation_plans": "investigation_planner -> investigation_plan_repository",
    "incident_investigation_steps": "investigation_planner -> investigation_plan_repository",
    "post_incident_reports": "post_incident_report -> post_incident_report_repository",
    "post_incident_report_actions": "post_incident_report -> post_incident_report_repository",
    "incident_outcomes": "incident_outcome.record_incident_outcome",
    "action_approvals": "action_approval -> action_approval_repository",
    "action_approval_events": "action_approval -> action_approval_repository",
    "execution_intents": "execution_transaction -> execution_intent_repository (dormant)",
    "execution_intent_events": "execution_transaction -> execution_intent_repository (dormant)",
}

MACHINE_DEPENDENT_WRITERS = {
    "topology_snapshots": "agent_snapshot_ingest.persist_agent_snapshot -> checkpoint",
    "changes": "agent_snapshot_ingest -> checkpoint -> snapshot diff",
    "signals": "agent signals / snapshot failure detection -> continuous_lifecycle",
    "incidents": "agent signals / snapshot failure detection -> continuous_lifecycle",
    "causal_analyses": "machine-origin continuous_lifecycle -> analyze_causal_rca",
    "build_artifact_evidence": "change_source_ingest -> GitHub Actions provider lineage",
    "change_events": "agent change-events / provider change_source_ingest",
    "change_entity_links": "agent/provider event ingestion and checkpoint correlation",
    "change_source_deliveries": "authenticated provider change_source_ingest",
    "change_source_dead_letters": "authenticated provider change_source_ingest",
    "cloud_accounts": "agent_snapshot_ingest -> cloud inventory",
    "cloud_resources": "agent_snapshot_ingest -> cloud inventory",
    "runtime_sensors": "authenticated agent runtime heartbeat / event batch",
    "runtime_dependencies": "authenticated agent runtime event batch",
    "runtime_processes": "authenticated agent runtime event batch",
    "webhook_deliveries": "machine-origin continuous_lifecycle -> publish_event_safely",
}

REQUIRED_OWNERSHIP_TABLES = frozenset(REQUIRED_OWNERSHIP_WRITERS)
