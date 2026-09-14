"""PH-5B planning contract for PH-5C authorization enforcement.

Nothing in this module authorizes a request or runs a service. The exact route
templates are deliberately static: adding a live route requires an explicit
reviewed entry. Permission tuples mean ALL OF, never a choice of permissions.

Repository targets in the operation inventory identify existing operations
whose caller/service boundary PH-5C must protect; they do not put permission
logic into PH-3 persistence. Automatic ingestion inherits only its enumerated
fixed-purpose caller authority. A bare tenant_id is never authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.security.authorization_policy import Permission


class AuthorizationIntent(StrEnum):
    PUBLIC = "PUBLIC"
    AUTHENTICATION_SELF_SERVICE = "AUTHENTICATION_SELF_SERVICE"
    TENANT_PERMISSION = "TENANT_PERMISSION"
    INSTALLATION_PERMISSION = "INSTALLATION_PERMISSION"
    AGENT_FIXED_PURPOSE = "AGENT_FIXED_PURPOSE"
    PROVIDER_FIXED_PURPOSE = "PROVIDER_FIXED_PURPOSE"
    V1_DORMANT_EXECUTION_DENY = "V1_DORMANT_EXECUTION_DENY"
    AUTHENTICATOR_CREDENTIAL_POLICY = "AUTHENTICATOR_CREDENTIAL_POLICY"


@dataclass(frozen=True)
class PlannedAuthority:
    intent: AuthorizationIntent
    permissions: frozenset[Permission] = frozenset()
    rationale: str = ""


@dataclass(frozen=True)
class RouteAuthorizationPlan:
    method: str
    path: str
    authority: PlannedAuthority
    credential_operation: str | None = None


@dataclass(frozen=True)
class OperationAuthorizationPlan:
    operation_id: str
    target: str
    authority: PlannedAuthority
    # Explicit already-authorized parent entrypoints, not generic machine bypass.
    delegated_callers: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthenticatorCredentialBranchPolicy:
    operation: str
    target_type: str
    caller_principal_type: str
    permissions: frozenset[Permission]
    ownership_rule: str
    valid_tenant_context_required: bool
    accepted_service_binding_required: bool
    raw_credential_returned_once: bool
    foreign_object_status: int = 404
    installation_assignment_grants_authority: bool = False
    tenant_membership_implies_human_credential_ownership: bool = False


def _authority(intent: AuthorizationIntent, codes: str = "", rationale: str = ""):
    return PlannedAuthority(intent, frozenset(Permission(code) for code in codes.split()), rationale)


def _routes(intent: AuthorizationIntent, codes: str, lines: str, rationale: str):
    authority = _authority(intent, codes, rationale)
    return tuple(
        RouteAuthorizationPlan(method, path, authority)
        for method, path in (line.split(" ", 1) for line in lines.strip().splitlines())
    )


I = AuthorizationIntent

# API methods are classified by the behavior inspected in app/api, not by HTTP
# verb alone: e.g. validation/discovery POSTs only read, while approval GETs write.
_ROUTE_ENTRIES = (
    *_routes(I.PUBLIC, "", """
GET /startup
GET /health
GET /ready
""", "Minimal startup/liveness/readiness; no tenant or security metadata."),
    *_routes(I.AUTHENTICATION_SELF_SERVICE, "", """
POST /api/v1/auth/session
GET /api/v1/auth/session
DELETE /api/v1/auth/session
GET /api/v1/system/whoami
GET /api/v1/tenants
GET /api/v1/tenant-context
GET /api/v1/topology/sample
""", "Preserve PH-2 authentication. Sessions/identity are caller-owned; tenants are only the caller's active memberships; tenant-context still validates PH-3 selection. Sample topology is fixed synthetic data with no persisted tenant data."),
    *_routes(I.INSTALLATION_PERMISSION, "installation.bootstrap", """
POST /api/v1/tenants
""", "Explicit bounded installation bootstrap/tenant creation; no implicit tenant business authority."),
    *_routes(I.INSTALLATION_PERMISSION, "installation.recovery", """
POST /api/v1/tenant-memberships/recover
""", "Preserve direct bootstrap recovery proof in addition to planned installation recovery authority."),
    *_routes(I.AGENT_FIXED_PURPOSE, "", """
POST /api/v1/agents/enroll
GET /api/v1/agent/config
POST /api/v1/agent/heartbeat
POST /api/v1/agent/snapshots
POST /api/v1/agent/runtime/heartbeat
POST /api/v1/agent/runtime/batches
POST /api/v1/agent/change-events
POST /api/v1/agent/signals
""", "Enrolled agent/enrollment credential and persisted tenant/scope binding; no human/service Permission set."),
    *_routes(I.PROVIDER_FIXED_PURPOSE, "", """
POST /api/v1/change-source-webhooks/{source_id}
""", "Verified provider callback, persisted source tenant binding, and frozen six-mechanism PH-2 authentication."),
    *_routes(I.V1_DORMANT_EXECUTION_DENY, "", """
POST /api/v1/incidents/{incident_id}/approvals
GET /api/v1/incidents/{incident_id}/approvals
GET /api/v1/incidents/{incident_id}/approvals/{approval_id}
POST /api/v1/incidents/{incident_id}/approvals/{approval_id}/approve
POST /api/v1/incidents/{incident_id}/approvals/{approval_id}/reject
POST /api/v1/incidents/{incident_id}/approvals/{approval_id}/revoke
POST /api/v1/incidents/{incident_id}/execution-intents
GET /api/v1/incidents/{incident_id}/execution-intents
GET /api/v1/incidents/{incident_id}/execution-intents/{execution_id}
POST /api/v1/incidents/{incident_id}/execution-intents/{execution_id}/cancel
""", "Dormant control plane. GET/list also refresh and persist active approval/intent states; they are not read-only historical evidence."),
    *_routes(I.TENANT_PERMISSION, "incident.read", """
GET /api/v1/incident-records
GET /api/v1/incident-records/{incident_id}
GET /api/v1/incidents
GET /api/v1/incidents/{analysis_id}
GET /api/v1/incidents/{incident_id}/lifecycle-status
GET /api/v1/incidents/{incident_id}/briefing
GET /api/v1/incidents/{incident_id}/operational-context
GET /api/v1/incidents/{incident_id}/copilot/sessions
GET /api/v1/incidents/{incident_id}/copilot/sessions/{session_id}
GET /api/v1/incidents/{incident_id}/explanations/latest
GET /api/v1/incidents/{incident_id}/explanations
GET /api/v1/incidents/{incident_id}/historical-intelligence
GET /api/v1/incidents/{incident_id}/outcome
GET /api/v1/incidents/{incident_id}/investigation-plans
GET /api/v1/incidents/{incident_id}/investigation-plans/{plan_id}
GET /api/v1/incidents/{incident_id}/response-intelligence
GET /api/v1/incidents/{incident_id}/response-plan
GET /api/v1/recommendations
GET /api/v1/recommendations/{recommendation_id}
GET /api/v1/recovery
GET /api/v1/recovery/{verification_id}
""", "Read incident intelligence and responder history within the selected tenant."),
    *_routes(I.TENANT_PERMISSION, "incident.respond", """
PATCH /api/v1/incident-records/{incident_id}/status
POST /api/v1/incidents/analyze
POST /api/v1/incidents/{incident_id}/causal-rca
POST /api/v1/incidents/{incident_id}/copilot/sessions
POST /api/v1/incidents/{incident_id}/copilot/sessions/{session_id}/messages
POST /api/v1/incidents/{incident_id}/explanations
POST /api/v1/incidents/{incident_id}/outcome
POST /api/v1/incidents/{incident_id}/investigation-plans
PATCH /api/v1/incidents/{incident_id}/investigation-plans/{plan_id}/steps/{step_id}
POST /api/v1/incidents/{incident_id}/reports
PATCH /api/v1/incidents/{incident_id}/reports/{report_id}
PATCH /api/v1/incidents/{incident_id}/reports/{report_id}/actions/{action_item_id}
POST /api/v1/orchestration/signals/{signal_id}/run
POST /api/v1/predeployment/analyze
POST /api/v1/recommendations/generate
PATCH /api/v1/recommendations/{recommendation_id}/status
POST /api/v1/recovery/verify
POST /api/v1/signals/ingest
""", "Persist bounded investigation/response state, evidence observations or generated reports. Applied status records a manually performed action; no infrastructure action is invoked. Predeployment analysis may publish a configured risk notification."),
    *_routes(I.TENANT_PERMISSION, "evidence.read", """
GET /api/v1/incident-records/{incident_id}/signals
GET /api/v1/incidents/{incident_id}/causal-rca/latest
GET /api/v1/causal-analyses/{analysis_id}
GET /api/v1/change-events
GET /api/v1/change-events/{event_id}
GET /api/v1/incidents/{incident_id}/change-events
GET /api/v1/incidents/{incident_id}/suspected-change-events
GET /api/v1/changes
GET /api/v1/changes/{change_id}
GET /api/v1/signals
GET /api/v1/signals/{signal_id}
GET /api/v1/agents/{agent_id}/runtime-dependencies
GET /api/v1/incidents/{incident_id}/execution-readiness
""", "Read actual causal/runtime/change evidence. Readiness only derives safety/validation context and never creates an approval or execution intent."),
    *_routes(I.TENANT_PERMISSION, "topology.read", """
POST /api/v1/topology/validate
POST /api/v1/kubernetes/discover
GET /api/v1/snapshots
GET /api/v1/snapshots/diff
GET /api/v1/snapshots/{snapshot_id}
GET /api/v1/snapshots/{snapshot_id}/network-dependencies
GET /api/v1/identities/resolve
GET /api/v1/identities/stored
GET /api/v1/identities/overrides
GET /api/v1/clouds/resources
GET /api/v1/clouds/topology
GET /api/v1/incidents/{incident_id}/blast-radius
""", "Read or validate topology. Kubernetes discover collects and returns resources without persisting; capture/enrichment have separate mutation authority."),
    *_routes(I.TENANT_PERMISSION, "integration.read", """
GET /api/v1/agents
GET /api/v1/agents/{agent_id}
GET /api/v1/agents/{agent_id}/health
GET /api/v1/agents/{agent_id}/plugins
GET /api/v1/agents/{agent_id}/cloud-status
GET /api/v1/agents/{agent_id}/sensors
GET /api/v1/automation/status
GET /api/v1/github/connection
GET /api/v1/kubernetes/connection
GET /api/v1/clouds/accounts
GET /api/v1/change-sources/deliveries
GET /api/v1/change-sources/dead-letters
GET /api/v1/integrations/deliveries
""", "Read connector/agent inventory, collection health and delivery diagnostics; does not grant credential mutation."),
    *_routes(I.TENANT_PERMISSION, "integration.read credential.metadata.read", """
GET /api/v1/change-sources
GET /api/v1/change-sources/{source_id}
GET /api/v1/change-sources/{source_id}/doctor
GET /api/v1/integrations/webhooks
""", "Combined integration view exposes credential configured/status/rotation metadata or protected-header names. Both read authorities are required; no raw secret read."),
    *_routes(I.TENANT_PERMISSION, "integration.manage", """
POST /api/v1/snapshots/capture
POST /api/v1/github/enrich
POST /api/v1/github/actions/enrich
POST /api/v1/identities/materialize
POST /api/v1/changes/from-diff
POST /api/v1/change-events
POST /api/v1/change-events/{event_id}/correlate
POST /api/v1/change-sources/dead-letters/{dead_letter_id}/replay
POST /api/v1/signals/kubernetes/events/ingest
POST /api/v1/integrations/webhooks/{webhook_id}/test
""", "Explicit ingestion/reconciliation/enrichment or integration delivery changes durable tenant evidence or invokes configured outbound delivery; no infrastructure mutation."),
    *_routes(I.TENANT_PERMISSION, "integration.manage credential.rotate", """
POST /api/v1/change-sources
PATCH /api/v1/change-sources/{source_id}
POST /api/v1/integrations/webhooks
""", "These combined endpoints can configure integration and create/rotate/revoke reversible credentials. Require BOTH authorities for the entire endpoint, including metadata-only payloads; no implicit service credential-administration exception."),
    *_routes(I.TENANT_PERMISSION, "integration.manage", """
PATCH /api/v1/integrations/webhooks/{webhook_id}
""", "Webhook metadata and same-origin path changes require integration authority; origin or protected-credential changes dynamically require credential.rotate as well."),
    *_routes(I.TENANT_PERMISSION, "credential.rotate", """
POST /api/v1/agents/enrollment-tokens
POST /api/v1/agents/{agent_id}/revoke
""", "Bounded tenant-owned agent credential issuance/revocation; not general principal authenticator administration."),
    *_routes(I.TENANT_PERMISSION, "tenant.settings.manage", """
POST /api/v1/identities/overrides
DELETE /api/v1/identities/overrides/{override_id}
""", "Change tenant canonical-identity override configuration; not ownership or source integration configuration."),
    *_routes(I.TENANT_PERMISSION, "ownership.read", """
GET /api/v1/ownership/mappings
GET /api/v1/ownership/resolve
GET /api/v1/incidents/{incident_id}/ownership-impact
""", "Read existing ownership mapping/resolution and derived business impact."),
    *_routes(I.TENANT_PERMISSION, "ownership.manage", """
POST /api/v1/ownership/mappings
""", "Persist explicit tenant ownership/business-capability configuration."),
    *_routes(I.TENANT_PERMISSION, "report.read", """
GET /api/v1/incidents/{incident_id}/reports
GET /api/v1/incidents/{incident_id}/reports/{report_id}
GET /api/v1/incidents/{incident_id}/reports/{report_id}/export
""", "Read/export persisted incident report; generation and edits require incident.respond."),
    *_routes(I.TENANT_PERMISSION, "member.read", """
GET /api/v1/tenant-memberships
""", "List memberships in selected tenant."),
    *_routes(I.TENANT_PERMISSION, "member.manage", """
POST /api/v1/tenant-memberships
POST /api/v1/tenant-memberships/{membership_id}/disable
""", "Create/reactivate/disable explicit human membership in selected tenant."),
)

_AUTHENTICATOR_ROUTES = (
    ("POST", "/api/v1/auth/api-credentials", "create"),
    ("GET", "/api/v1/auth/api-credentials", "list"),
    ("GET", "/api/v1/auth/api-credentials/{credential_id}", "get"),
    ("POST", "/api/v1/auth/api-credentials/{credential_id}/revoke", "revoke"),
)

_ROUTE_ENTRIES += tuple(
    RouteAuthorizationPlan(
        method, path,
        _authority(
            I.AUTHENTICATOR_CREDENTIAL_POLICY,
            rationale="Architect amendment: human self-only or human same-tenant service administration. Legacy PH-2 broad admin gate is compatibility only until PH-5C replaces it.",
        ),
        credential_operation=operation,
    )
    for method, path, operation in _AUTHENTICATOR_ROUTES
)


def _index(entries, key):
    result = {}
    for entry in entries:
        item_key = key(entry)
        if item_key in result:
            raise ValueError(f"Duplicate authorization-plan entry: {item_key}")
        result[item_key] = entry
    return MappingProxyType(result)


ROUTE_AUTHORIZATION_PLAN = _index(_ROUTE_ENTRIES, lambda entry: (entry.method, entry.path))

AUTHENTICATOR_CREDENTIAL_POLICY = tuple(
    AuthenticatorCredentialBranchPolicy(
        operation=operation,
        target_type=target_type,
        caller_principal_type="human",
        permissions=(
            frozenset()
            if target_type == "human"
            else frozenset({Permission("credential.metadata.read" if operation in {"get", "list"} else "credential.rotate")})
        ),
        ownership_rule=(
            "target.principal_id == caller.principal_id"
            if target_type == "human"
            else "service_api_tenant_binding.tenant_id == tenant_context.tenant_id"
        ),
        valid_tenant_context_required=target_type == "service",
        accepted_service_binding_required=target_type == "service",
        raw_credential_returned_once=operation == "create",
    )
    for operation in ("create", "list", "get", "revoke")
    for target_type in ("human", "service")
)

ERROR_CONTRACT = MappingProxyType({
    "unauthenticated": 401,
    "valid_tenant_insufficient_permission": 403,
    "foreign_or_absent_object": 404,
})


def route_authorization_plan(method: str, path_template: str) -> RouteAuthorizationPlan:
    """Exact registered-template lookup; unknown entries fail closed."""
    return ROUTE_AUTHORIZATION_PLAN[(method, path_template)]

# Each operation row freezes a direct-entry requirement. Where an existing
# machine/automatic path calls it, PH-5C must propagate that already-authorized
# caller's bounded scope instead of inventing human permissions for machines.
# These names do not authenticate a caller: enforcement must prove its origin.
def _operation(target, intent, codes="", rationale="", delegated_callers=(), *, operation_id=None):
    return OperationAuthorizationPlan(
        operation_id or target, target, _authority(intent, codes, rationale), delegated_callers,
    )


_OPERATION_ENTRIES = (
    _operation("app.services.causal_rca.analyze_causal_rca", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission.", ("app.services.continuous_lifecycle._complete_automatic_analysis",)),
    _operation("app.services.incident_analysis.analyze_incident", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_orchestrator.orchestrate_signal", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_lifecycle.upsert_incident_from_orchestration", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission.", ("app.services.incident_orchestrator.orchestrate_signal",)),
    _operation("app.services.continuous_lifecycle.ingest_failure_signal_batch", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission.", ("app.api.agents.submit_failure_signals","app.services.agent_snapshot_ingest.persist_agent_snapshot",)),
    _operation("app.services.continuous_lifecycle.process_failure_signal", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission.", ("app.services.continuous_lifecycle.ingest_failure_signal_batch",)),
    _operation("app.services.continuous_lifecycle.reconcile_pending_incidents_for_checkpoint", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission.", ("app.services.agent_snapshot_ingest.persist_agent_snapshot",)),
    _operation("app.services.incident_copilot.create_incident_copilot_session", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_copilot.answer_copilot_question", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_explanation.generate_incident_explanation", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_outcome.record_incident_outcome", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.investigation_planner.generate_investigation_plan", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.post_incident_report.generate_post_incident_report", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.predeployment_impact.analyze_predeployment_impact", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.recommendation_engine.generate_recommendations", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.recovery_verification.verify_recovery", I.TENANT_PERMISSION, "incident.respond", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.repositories.incident_record_repository.update_incident_status", I.TENANT_PERMISSION, "incident.respond", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.investigation_plan_repository.update_investigation_step", I.TENANT_PERMISSION, "incident.respond", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.post_incident_report_repository.update_post_incident_report", I.TENANT_PERMISSION, "incident.respond", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.post_incident_report_repository.update_report_action_item", I.TENANT_PERMISSION, "incident.respond", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.recommendation_repository.update_recommendation_status", I.TENANT_PERMISSION, "incident.respond", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.services.incident_briefing.build_incident_briefing", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_context.build_incident_operational_context", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_outcome.get_incident_outcome", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_similarity.build_historical_incident_intelligence", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.response_intelligence.build_incident_response_intelligence", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.response_plan.build_incident_response_plan", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.lifecycle_status.build_incident_lifecycle_status", I.TENANT_PERMISSION, "incident.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.incident_change_analysis.analyze_incident_change_events", I.TENANT_PERMISSION, "evidence.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.execution_readiness.build_incident_execution_readiness", I.TENANT_PERMISSION, "evidence.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.repositories.causal_analysis_repository.latest_causal_analysis", I.TENANT_PERMISSION, "evidence.read", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.causal_analysis_repository.load_causal_analysis", I.TENANT_PERMISSION, "evidence.read", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.services.blast_radius.calculate_blast_radius", I.TENANT_PERMISSION, "topology.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.network_dependency_analysis.analyze_network_dependencies", I.TENANT_PERMISSION, "topology.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.identity_resolver.resolve_kubernetes_identities", I.TENANT_PERMISSION, "topology.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.topology_checkpoint.persist_topology_checkpoint", I.TENANT_PERMISSION, "integration.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission.", ("app.services.agent_snapshot_ingest.persist_agent_snapshot","app.api.signals.ingest_kubernetes_events",)),
    _operation("app.services.change_source_ingest.replay_dead_letter", I.TENANT_PERMISSION, "integration.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.change_event_bridge.promote_normalized_changes", I.TENANT_PERMISSION, "integration.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.github_actions_artifact_lineage.enrich_snapshot_with_github_actions_provider_evidence", I.TENANT_PERMISSION, "integration.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.repositories.identity_repository.save_identity_resolution", I.TENANT_PERMISSION, "integration.manage", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.change_event_repository.ingest_change_event", I.TENANT_PERMISSION, "integration.manage", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent.", ("app.api.agents.submit_change_events","app.services.change_source_ingest.ingest_change_source_webhook","app.services.change_event_bridge.promote_normalized_changes",)),
    _operation("app.repositories.change_event_repository.correlate_change_event", I.TENANT_PERMISSION, "integration.manage", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.services.webhook_delivery.deliver_event_to_endpoint", I.TENANT_PERMISSION, "integration.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.lifecycle_status.build_lifecycle_status", I.TENANT_PERMISSION, "integration.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.secret_consumers.create_change_source_secure", I.TENANT_PERMISSION, "integration.manage credential.rotate", "Bounded credential lifecycle; combined integration/secret calls require all listed permissions. No raw-secret read authority."),
    _operation("app.services.secret_consumers.update_change_source_secure", I.TENANT_PERMISSION, "integration.manage credential.rotate", "Bounded credential lifecycle; combined integration/secret calls require all listed permissions. No raw-secret read authority."),
    _operation("app.services.secret_consumers.create_webhook_endpoint_secure", I.TENANT_PERMISSION, "integration.manage credential.rotate", "Bounded credential lifecycle; combined integration/secret calls require all listed permissions. No raw-secret read authority."),
    _operation("app.services.secret_consumers.update_webhook_endpoint_secure", I.TENANT_PERMISSION, "integration.manage", "Webhook metadata is integration-managed; origin and protected-credential changes dynamically require credential.rotate. No raw-secret read authority."),
    _operation("app.repositories.identity_repository.upsert_identity_override", I.TENANT_PERMISSION, "tenant.settings.manage", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.repositories.identity_repository.deactivate_identity_override", I.TENANT_PERMISSION, "tenant.settings.manage", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation("app.services.ownership_resolver.create_ownership_mapping", I.TENANT_PERMISSION, "ownership.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.ownership_resolver.resolve_ownership_by_ids", I.TENANT_PERMISSION, "ownership.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.business_impact.calculate_incident_ownership_impact", I.TENANT_PERMISSION, "ownership.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.post_incident_report.render_post_incident_report_markdown", I.TENANT_PERMISSION, "report.read", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.tenant_service.add_or_reactivate_tenant_membership", I.TENANT_PERMISSION, "member.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.services.tenant_service.disable_tenant_membership", I.TENANT_PERMISSION, "member.manage", "Tenant-scoped operation; direct invocation requires the listed semantic permission."),
    _operation("app.repositories.tenant_repository.list_tenant_memberships", I.TENANT_PERMISSION, "member.read", "Existing low-level operation: PH-5C enforces its calling service boundary; PH-3 repository tenant predicates remain independent."),
    _operation(
        "app.services.authority_assignments.create_service_permission_assignment",
        I.TENANT_PERMISSION,
        "credential.rotate",
        "Human authority for the target service's accepted same-tenant binding; new principal, assignment, credential and binding are one transaction. A service cannot assign its own authority.",
    ),
    _operation(
        "app.services.authority_assignments.update_service_permissions",
        I.TENANT_PERMISSION,
        "credential.rotate",
        "Human authority for an already-bound same-tenant service principal; full replacement is CAS protected. A service cannot update its own authority.",
    ),
    _operation("app.repositories.agent_repository.create_enrollment_token", I.TENANT_PERMISSION, "credential.rotate", "Bounded credential lifecycle; combined integration/secret calls require all listed permissions. No raw-secret read authority."),
    _operation("app.repositories.agent_repository.revoke_agent", I.TENANT_PERMISSION, "credential.rotate", "Bounded credential lifecycle; combined integration/secret calls require all listed permissions. No raw-secret read authority."),
    _operation("app.services.tenant_service.create_tenant_with_creator_membership", I.INSTALLATION_PERMISSION, "installation.bootstrap", "Explicit installation operation; local utilities additionally require deployment/operator access, never tenant membership."),
    _operation("app.api.tenants.recover_membership", I.INSTALLATION_PERMISSION, "installation.recovery", "Explicit installation operation; local utilities additionally require deployment/operator access, never tenant membership."),
    _operation("app.installation_secret_admin._safe_status", I.INSTALLATION_PERMISSION, "installation.status.read", "Explicit installation operation; local utilities additionally require deployment/operator access, never tenant membership."),
    _operation("app.installation_secret_admin._mutate", I.INSTALLATION_PERMISSION, "installation.secret.manage", "Explicit installation operation; local utilities additionally require deployment/operator access, never tenant membership."),
    _operation("app.services.secret_legacy_conversion.convert_legacy_secrets", I.INSTALLATION_PERMISSION, "installation.secret.manage", "Explicit installation operation; local utilities additionally require deployment/operator access, never tenant membership."),
    _operation(
        "app.services.authority_assignments.get_installation_operator_status",
        I.INSTALLATION_PERMISSION,
        "installation.status.read",
        "Local deployment administration only; an installation assignment is not inferred from tenant authority.",
    ),
    _operation(
        "app.services.authority_assignments.grant_installation_operator",
        I.INSTALLATION_PERMISSION,
        "installation.recovery",
        "Explicit local deployment recovery boundary. The initial assignment cannot require a pre-existing operator and is never inferred from a tenant role.",
    ),
    _operation(
        "app.services.authority_assignments.disable_installation_operator",
        I.INSTALLATION_PERMISSION,
        "installation.recovery",
        "Explicit local deployment recovery boundary; revocation remains possible after principal disablement and never derives from tenant authority.",
    ),
    _operation("app.services.auth_session_service.create_auth_session", I.AUTHENTICATION_SELF_SERVICE, "", "PH-2 authentication/session validation for the caller's durable principal only."),
    _operation("app.services.auth_session_service.resolve_auth_session", I.AUTHENTICATION_SELF_SERVICE, "", "PH-2 authentication/session validation for the caller's durable principal only."),
    _operation("app.services.auth_session_service.revoke_auth_session", I.AUTHENTICATION_SELF_SERVICE, "", "PH-2 authentication/session validation for the caller's durable principal only."),
    _operation("app.services.auth_api_credential_service.authenticate_auth_api_credential", I.AUTHENTICATION_SELF_SERVICE, "", "PH-2 authentication/session validation for the caller's durable principal only."),
    _operation("app.services.agent_snapshot_ingest.persist_agent_snapshot", I.AGENT_FIXED_PURPOSE, "", "Persisted agent/enrollment binding and fixed ingestion purpose only."),
    _operation("app.repositories.agent_repository.enroll_agent", I.AGENT_FIXED_PURPOSE, "", "Persisted agent/enrollment binding and fixed ingestion purpose only."),
    _operation("app.repositories.agent_repository.record_heartbeat", I.AGENT_FIXED_PURPOSE, "", "Persisted agent/enrollment binding and fixed ingestion purpose only."),
    _operation("app.repositories.runtime_observability_repository.record_sensor_heartbeat", I.AGENT_FIXED_PURPOSE, "", "Persisted agent/enrollment binding and fixed ingestion purpose only."),
    _operation("app.repositories.runtime_observability_repository.ingest_runtime_event_batch", I.AGENT_FIXED_PURPOSE, "", "Persisted agent/enrollment binding and fixed ingestion purpose only."),
    _operation("app.services.change_source_ingest.ingest_change_source_webhook", I.PROVIDER_FIXED_PURPOSE, "", "Verified source callback and accepted provider tenant binding only."),
    _operation("app.services.action_approval.create_action_approval", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.action_approval.get_action_approval", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.action_approval.list_action_approvals", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.action_approval.decide_action_approval", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.action_approval.revoke_action_approval", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.execution_transaction.create_execution_intent", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.execution_transaction.get_execution_intent", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.execution_transaction.list_execution_intents", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.execution_transaction.cancel_execution_intent", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.execution_transaction.claim_execution_intent", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
    _operation("app.services.execution_transaction.release_execution_claim", I.V1_DORMANT_EXECUTION_DENY, "", "Dormant approval/execution state mutation including refresh-on-read; planned V1 deny."),
)

# The four global authenticator endpoints branch on durable target ownership.
# These eight operation-context rows reuse the frozen narrow amendment. They do
# not extend AUTHENTICATOR_CREDENTIAL_POLICY to any additional route.
_CREDENTIAL_TARGETS = {
    "create": "app.services.auth_api_credential_service.create_auth_api_credential",
    "list": "app.repositories.auth_api_credential_repository.list_auth_api_credentials",
    "get": "app.repositories.auth_api_credential_repository.load_auth_api_credential",
    "revoke": "app.services.auth_api_credential_service.revoke_auth_api_credential",
}
_OPERATION_ENTRIES += tuple(
    _operation(
        _CREDENTIAL_TARGETS[policy.operation],
        I.AUTHENTICATION_SELF_SERVICE if policy.target_type == "human" else I.TENANT_PERMISSION,
        " ".join(sorted(permission.value for permission in policy.permissions)),
        (
            "HUMAN caller only; " + policy.ownership_rule
            + "; foreign or absent credential is 404; installation assignment is never authority. "
            + ("Only self-owned human credential; membership implies no ownership."
               if policy.target_type == "human"
               else "Validated selected TenantContext and accepted same-tenant service binding required; creation must establish that binding atomically before raw credential delivery.")
        ),
        operation_id="authenticator." + policy.target_type + "." + policy.operation,
    )
    for policy in AUTHENTICATOR_CREDENTIAL_POLICY
)

CRITICAL_OPERATION_PLAN = _index(_OPERATION_ENTRIES, lambda entry: entry.operation_id)


def operation_authorization_plan(operation_id: str) -> OperationAuthorizationPlan:
    """Exact operation/context lookup; no unknown-operation authority."""
    return CRITICAL_OPERATION_PLAN[operation_id]
