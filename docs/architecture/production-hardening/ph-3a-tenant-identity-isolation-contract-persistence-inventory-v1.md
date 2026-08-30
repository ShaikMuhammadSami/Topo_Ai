# PH-3A — Tenant Identity + Isolation Contract / Persistence Inventory v1

- Status: **ARCHITECTURE ACCEPTED — IMPLEMENTATION NOT STARTED**
- Verdict: **PASS**
- Repository: `C:\Topo-ai`
- Branch inspected: `architecture/ph-3a-tenant-identity-isolation-contract-v1`
- Accepted input commit: `fd7b74d67a17867f84e706f4f3752d0738553b54`
- Accepted input summary: `fd7b74d test(security): close authentication hardening (#72)`
- Scope: architecture and static inventory only
- Product, model, schema, migration, frontend, CLI, agent, provider, and evaluator changes: **none**

## 1. Executive decision

PH-3A passes as an architecture contract. TopoAI has production-shaped,
default-on authentication after PH-2, but its domain persistence is not
tenant-isolated. PH-3 must add an explicit durable tenant boundary between
authentication and later PH-5 authorization.

The V1 decision is:

```text
authenticated identity
  -> explicit, server-validated tenant access
  -> immutable request-scoped TenantContext
  -> tenant predicate on every domain read and write
  -> same-tenant parent/reference validation
  -> PH-5 permission check inside that tenant
```

Tenant identity is a server-generated, immutable, non-secret identifier. A
customer name, email domain, GitHub organization, cloud alias, cluster, or
namespace is never the tenant security key. The recommended format is an
opaque identifier with a semantic prefix, for example `tenant:<uuid>`; the
random component is not derived from display metadata.

All 38 current domain tables are tenant-owned. Thirteen are direct ownership
roots in their domain and 25 derive ownership from a logical parent. Because
the schema has no foreign keys and almost every child is independently
addressable, **all 38 should receive a direct, non-null `tenant_id`** after a
controlled backfill. The two PH-2 authentication tables remain
security-global. There are no current installation-global or shared-reference
tables, and no table remains ambiguous.

This document does not implement tenancy and does not claim TopoAI is
multi-tenant safe today.

## 2. Current-state tenancy gap

At Alembic head `0003_auth_api_credentials`, SQLAlchemy metadata contains 40
tables, 715 columns, 40 single-string primary keys, no declared foreign keys,
12 named unique constraints, nine unique indexes, and 301 total index objects.
The 38 pre-auth domain tables remain deliberately denormalized and use
application-enforced string/JSON references.

Current requests authenticate a caller but do not establish a tenant. Domain
repositories accept IDs, fingerprints, cluster/name scopes, timestamps, and
filters without a mandatory tenant predicate. Consequently, identical
customer-local names and deterministic fingerprints can collide, list/search
queries can cross customer boundaries, direct ID lookups are IDOR-prone, and
historical/LLM/report pipelines can assemble evidence from unrelated
customers. This is an expected PH-3 hardening gap, not a defect in PH-2.

PH-1 remains accepted: PostgreSQL plus immutable additive Alembic migrations
is the production persistence authority. PH-2 remains accepted: it answers
who authenticated and through which trust domain. Neither acceptance implied
tenant isolation.

## 3. Tenant terminology

| Term | Frozen meaning |
|---|---|
| Tenant | Durable customer security boundary, not a company-name alias. |
| Tenant ID | Stable, immutable, server-generated, non-secret opaque identifier. |
| Tenant membership | Permission for a human identity to enter a tenant boundary; not PH-5 RBAC. |
| Tenant binding | Fixed server-side association used by service credentials, agents, enrollment credentials, and provider sources. |
| Active tenant | Tenant selected for one human request and validated against active membership. |
| `TenantContext` | Immutable server-created request/work-item context carried through all persistence calls. |
| Tenant-owned direct | Record is a domain ownership root and directly belongs to one tenant. |
| Tenant-owned derived | Record belongs through a logical parent; direct `tenant_id` is still recommended for defense in depth. |
| Installation-global | Installation metadata that is not customer data. No current ORM table qualifies. |
| Security-global | Authentication identity/credential infrastructure whose ownership is not equivalent to one tenant. |
| Shared reference | Immutable reference data genuinely shared by all tenants. No current ORM table qualifies. |

Future minimal tenant states are `active` and `disabled`. Disabled tenants deny
normal data-plane operations while retaining data for later PH-7 retention
policy. A display name and optional slug are navigation metadata only. If a
slug is later added, installation-wide uniqueness is acceptable for routing,
but authorization must continue to use `tenant_id`. A slug is not required
for V1.

## 4. Tenant identity contract

The future tenant root concept is:

```text
tenant_id       immutable opaque security identity
display_name    mutable presentation metadata
status          active | disabled
created_at
updated_at
```

Creation is server-side. Renaming a tenant never changes `tenant_id`. Tenant
IDs may appear in URLs, headers, logs, and audit records and therefore are not
secrets, but knowledge of an ID grants no authority. There is no implicit
tenant derived from subject text, email, host name, provider payload, cluster,
repository, or customer display name.

Recommended request context:

```text
TenantContext(
    tenant_id,
    subject,
    authentication_type,
    actor_kind,          # human | service | agent | provider | internal
    selection_source,    # header | credential_binding | agent_binding |
                         # provider_source | persisted_work_item
    membership_id=None,  # human requests
    credential_id=None,  # service requests when available
)
```

The context is immutable and server-created after trust-boundary validation.
Models and request bodies may not override it.

## 5. Authentication vs tenancy vs RBAC

```text
AUTHENTICATION                       PH-2
Who is the caller and is the credential valid?
        |
TENANCY                              PH-3
Which tenant boundary may this caller enter?
        |
RBAC                                 PH-5
What may the caller do inside that tenant?
```

`AuthPrincipal(subject, display_name, roles, authentication_type)` remains an
authentication object and does not gain an implied tenant. PH-3 does not
require changing it. Existing `roles` do not substitute for membership, and
an installation `admin` is not an implicit cross-tenant data-plane superuser.

## 6. Table ownership classification matrix

The schema declares no foreign keys. “Parent” below means an application-level
string or JSON reference. `DTR` means **DIRECT TENANT REQUIRED** and `DDR`
means **DERIVED BUT DIRECT RECOMMENDED**. Every `DTR` and `DDR` row receives a
direct tenant column in the later migration. `SG` means **SECURITY GLOBAL**.
“Req” means request/API bound; “ingest” includes synchronous agent/provider
processing; “life” includes lifecycle reconciliation; “exec” is preserved
future approval/execution infrastructure.

| Table / primary key | Domain; current logical owner / parent references | Class | Direct tenant decision and rationale | Unique/index migration | Access paths; exposure/background; risk if unchanged |
|---|---|---|---|---|---|
| `action_approval_events` / `event_id` | Approval audit; `approval_id`, `incident_id` | DDR | Direct required: append-only events are loaded independently and must remain auditable after parent deletion/export. | Scope `(approval_id, sequence)` and all actor/incident/time indexes. | `action_approval_repository`; incident approval APIs; exec. Cross-tenant audit disclosure. |
| `action_approvals` / `approval_id` | Incident action approval; `incident_id`, action/change/entity refs | DDR | Direct required: independently addressable control-plane record. | Scope `pending_key`; tenant-leading incident/status/action/time indexes. | `action_approval_repository`; approval APIs; exec. Cross-tenant decision/control risk. |
| `agent_enrollment_tokens` / `enrollment_token_id` | Tenant-bound machine enrollment authority | DTR | Direct required: token is issued for exactly one tenant and agent inherits it atomically. | Keep `token_hash` globally unique for credential safety; add tenant status/expiry indexes. | `agent_repository`; admin create + machine enroll. Wrong-tenant agent creation. |
| `auth_api_credentials` / `credential_id` | Caller identity credential | SG | No tenant column: humans can have multiple memberships; service binding belongs in a separate binding record. | Keep digest uniqueness and security indexes global. | Auth repository/service and credential APIs. Equating credential with tenant breaks human multi-tenancy. |
| `auth_sessions` / `session_id` | Browser authentication session | SG | No tenant column: active tenant is per request, not permanently session-bound. | Keep session-secret uniqueness global. | Auth session repository/service and session APIs. Session-bound tenant can become stale or confused. |
| `build_artifact_evidence` / `evidence_id` | Provider-authentic build/image evidence; repository/run/commit/image refs | DTR | Direct required: durable evidence can be queried by image independent of source/delivery. | Scope provider-fact unique constraint and all repository/run/image/time indexes. | `build_artifact_evidence_repository`; provider/change/RCA ingest. Cross-tenant lineage leakage. |
| `causal_analyses` / `analysis_id` | 13C RCA; `incident_id`, root event and serialized evidence | DDR | Direct required: latest/by-ID queries and briefing load it directly. | Tenant-leading incident/generated/root-event indexes and `(tenant_id, analysis_id)` lookup. | `causal_analysis_repository`; RCA/briefing APIs; life. Cross-tenant causal evidence. |
| `change_entity_links` / `link_id` | Change-to-topology link; event/entity/snapshot refs | DDR | Direct required: link scans occur independently and nested entity IDs are snapshot-local. | Scope `(event_id, entity_id, link_type)` and event/entity/snapshot indexes. | `change_event_repository`, direct incident-change service query; change/RCA APIs. Cross-tenant graph join. |
| `change_events` / `event_id` | Durable normalized native/agent/human change | DTR | Direct required: multiple ingress paths and direct by-ID/window queries. | Scope unique `event_fingerprint`; tenant-leading source/time/scope/repo/status indexes. | `change_event_repository`; human, agent, provider routes; ingest. Cross-tenant dedupe and attribution. |
| `change_source_dead_letters` / `dead_letter_id` | Failed source delivery; `source_id`, `delivery_id` | DDR | Direct required: replay loads rows independently by ID. | Tenant-leading source/delivery/status/time indexes. | `change_source_repository`, direct `change_source_ingest`; source APIs/provider processing. Cross-tenant replay. |
| `change_source_deliveries` / `delivery_id` | Provider delivery; `source_id`, event IDs | DDR | Direct required: replay/idempotency queries are independent. | Scope unique `delivery_key`; tenant-leading source/provider-delivery/status/time indexes. | `change_source_repository`, direct ingest service; provider + source APIs. Cross-tenant replay suppression or disclosure. |
| `change_sources` / `source_id` | Provider configuration/secret reference | DTR | Direct required: server-side source is the provider callback tenant authority. | Tenant-leading name/type/status indexes; deterministic source ID must be tenant-namespaced. | `change_source_repository`; source APIs/provider callback. Provider payload could enter wrong tenant. |
| `changes` / `change_id` | Snapshot-diff change; from/to snapshots, entity/relationship refs | DTR | Direct required: direct list/load/window queries and both snapshots must share tenant. | Tenant-leading time/type/scope/entity/snapshot indexes; fingerprint/ID namespace. | `change_repository`; changes/predeployment/RCA APIs. Cross-tenant snapshot comparison. |
| `cloud_accounts` / `cloud_account_id` | Discovered cloud account/subscription/project | DTR | Direct required: account is a tenant root even when provider ID is globally stable. | Tenant-leading provider/account/display/last-seen indexes and tenant-scoped business uniqueness. | `cloud_repository`; agent/cloud APIs; ingest. Same aliases and delegated accounts can cross tenants. |
| `cloud_resources` / `cloud_resource_id` | Resource under account; account/provider/agent refs | DDR | Direct required: resources are queried without joining account. | Tenant-leading provider/account/region/type/native-id/agent/time indexes; namespace deterministic PK. | `cloud_repository`; agent/cloud APIs; ingest. Cross-tenant resource collapse. |
| `execution_intent_events` / `event_id` | Execution transaction audit; execution/incident/approval refs | DDR | Direct required despite V1 read-only positioning. | Scope `(execution_id, sequence)` and tenant-lead all lookup/audit indexes. | `execution_intent_repository`; execution APIs/future worker. Cross-tenant transaction audit. |
| `execution_intents` / `execution_id` | Preserved future execution transaction | DDR | Direct required: claim/idempotency operations address row independently. | Scope unique `approval_id` and `idempotency_key`; tenant-leading status/claim/action indexes. | `execution_intent_repository`; execution APIs/future worker. Cross-tenant claims are critical. |
| `identity_overrides` / `override_id` | Operator identity rule for scoped entity target | DTR | Direct required: cluster/namespace/name are customer-local. | Scope target unique constraint and active/scope indexes. | `identity_repository`; identity APIs. Tenant A rule could rewrite Tenant B identity. |
| `identity_resolutions` / `snapshot_id` | Materialized TC-1 resolution for one snapshot | DDR | Direct required: PK currently aliases parent ID and load is direct. | Tenant-leading generated/count indexes; require same-tenant snapshot. | `identity_repository`; identity APIs. Cross-tenant snapshot resolution. |
| `incident_analyses` / `analysis_id` | Legacy incident analysis; signal + snapshot refs | DDR | Direct required: separately listed/loaded and historical snapshot is authoritative. | Tenant-leading signal/snapshot/time/scope indexes. | `incident_repository`; legacy analysis APIs. Cross-tenant evidence candidates. |
| `incident_copilot_messages` / `message_id` | Copilot message; session + incident refs | DDR | Direct required: message/session/incident triad must be same tenant. | Tenant-leading session/incident/time indexes. | `copilot_repository`; Copilot APIs. LLM context/data disclosure. |
| `incident_copilot_sessions` / `session_id` | Copilot conversation; `incident_id` | DDR | Direct required: directly addressable session. | Tenant-leading incident/status/time indexes. | `copilot_repository`; Copilot APIs. Cross-tenant conversation access. |
| `incident_explanations` / `explanation_id` | Grounded explanation; incident/snapshot/analysis refs | DDR | Direct required: cached latest/by-ID queries are independent. | Tenant-leading incident/snapshot/analysis/generated/grounding indexes. | `incident_explanation_repository`; explanation APIs. Cross-tenant prompt grounding. |
| `incident_investigation_plans` / `plan_id` | Investigation plan; `incident_id` | DDR | Direct required: directly loaded and generated from evidence. | Tenant-leading incident/status/time/grounding indexes. | `investigation_plan_repository`; plan APIs. Cross-tenant plan/evidence. |
| `incident_investigation_steps` / `step_id` | Plan step; plan + incident refs | DDR | Direct required: direct PATCH by step ID. | Scope `(plan_id, sequence)` and tenant-leading plan/incident/status indexes. | `investigation_plan_repository`; plan APIs. Cross-tenant child mutation. |
| `incident_outcomes` / `outcome_id` | 14C outcome; incident/RCA/response refs | DDR | Direct required: latest/history scans query independently. | Scope unique `incident_id`; tenant-leading status/time/verdict indexes. | `incident_outcome_repository`; outcome/history APIs. Cross-tenant historical learning. |
| `incidents` / `incident_id` | Correlated operational problem; signal/snapshot/entity/analysis refs | DTR | Direct required: central tenant root for incident intelligence. | Tenant-leading fingerprint/status/time/scope indexes; correlation key and ID need tenant namespace. | `incident_record_repository`; most incident APIs; life. Cross-tenant correlation is critical. |
| `ownership_mappings` / `ownership_id` | Ownership/routing/business context rule | DTR | Direct required: ownership is customer-private and cluster/service names are local. | Scope unique `fingerprint`; tenant-leading entity/service/scope/team/active indexes. | `ownership_repository`; ownership APIs. Wrong-team routing and contact disclosure. |
| `post_incident_report_actions` / `action_item_id` | Report action; report + incident refs | DDR | Direct required: independently PATCHed. | Scope `(report_id, sequence)` and tenant-leading report/incident/team/status indexes. | `post_incident_report_repository`; report APIs/export. Cross-tenant action mutation. |
| `post_incident_reports` / `report_id` | Incident report; `incident_id`, serialized evidence | DDR | Direct required: direct export/load and LLM grounding. | Scope `(incident_id, version)` and tenant-leading incident/status/time indexes. | `post_incident_report_repository`; report APIs/export. Customer-data export disclosure. |
| `recovery_verifications` / `verification_id` | Recovery check; recommendation/analysis/signal/snapshots/entity refs | DDR | Direct required: direct API lookup and multiple parents must share tenant. | Tenant-leading all parent/status/time/scope/entity indexes. | `recovery_repository`; recovery APIs. Cross-tenant recovery conclusion. |
| `remediation_recommendations` / `recommendation_id` | Guidance; analysis/hypothesis/signal/change/entity refs | DDR | Direct required: direct status mutation and V1 guidance. | Tenant-leading analysis/signal/change/status/time/entity indexes. | `recommendation_repository`; recommendation APIs. Cross-tenant guidance/status mutation. |
| `runtime_dependencies` / `runtime_dependency_id` | eBPF/runtime edge; agent/sensor/workload refs | DDR | Direct required: queried by agent/time without joining sensor. | Tenant-leading agent/sensor/scope/pod/workload/destination/time indexes; namespace deterministic ID. | `runtime_observability_repository`; agent runtime + admin APIs; ingest. Runtime cross-customer disclosure. |
| `runtime_processes` / `runtime_process_id` | Runtime process observation; agent/sensor/container/pod refs | DDR | Direct required: independently upserted; no current public list repository but persisted evidence feeds topology. | Tenant-leading agent/sensor/scope/pod/container/exec/time indexes; namespace deterministic ID. | `runtime_observability_repository`; agent ingest/topology enrichment. Cross-tenant process evidence. |
| `runtime_sensors` / `sensor_id` | Sensor under agent | DDR | Direct required: authenticated runtime path upserts/loads sensor directly. | Scope `(agent_id, node_name, source)` and tenant-leading status/time indexes. | `runtime_observability_repository`; agent runtime + admin APIs; ingest. Cross-tenant sensor association. |
| `signals` / `signal_id` | Failure observation | DTR | Direct required: human/agent ingress and direct list/fingerprint/window queries. | Tenant-leading fingerprint/type/scope/entity/time indexes; signal ID/fingerprint namespace. | `signal_repository`; signal/orchestration/incident APIs; life. Cross-tenant incident creation. |
| `topo_agents` / `agent_id` | Enrolled machine identity | DTR | Direct required: durable fixed tenant binding; request payload cannot select tenant. | Keep token hash globally unique; tenant-leading name/cluster/status/time indexes. | `agent_repository`; admin + machine APIs; ingest. Agent telemetry tenant escape. |
| `topology_snapshots` / `snapshot_id` | Immutable graph checkpoint | DTR | Direct required: snapshot is the historical authority for all nested entity IDs. | Tenant-leading collected/scope indexes; dedupe lookup must include tenant. | `snapshot_repository` and legacy loader; snapshot/topology/RCA APIs; checkpoint/life. Historical cross-tenant graph use. |
| `webhook_deliveries` / `delivery_id` | Outbound delivery; endpoint + event/resource refs | DDR | Direct required: retries/list queries address delivery independently. | Scope `(webhook_id, event_id)` and tenant-leading endpoint/status/resource indexes. | `webhook_repository`; outbound webhook APIs/delivery path. Cross-tenant payload delivery. |
| `webhook_endpoints` / `webhook_id` | Customer outbound destination/configuration | DTR | Direct required: endpoint, headers, and signing material belong to one tenant. | Tenant-leading active/name index; IDs tenant-namespaced where deterministic. | `webhook_repository`; webhook APIs/delivery path. Sending customer data to another tenant endpoint. |

Classification totals:

| Category | Count |
|---|---:|
| `TENANT_ROOT` (current) | 0 |
| `TENANT_OWNED_DIRECT` | 13 |
| `TENANT_OWNED_DERIVED` | 25 |
| `INSTALLATION_GLOBAL` | 0 |
| `SECURITY_GLOBAL` | 2 |
| `SHARED_REFERENCE` | 0 |
| `AMBIGUOUS` | 0 |
| **Total** | **40** |

Future `tenants` is `TENANT_ROOT`. Future `tenant_memberships` and fixed
machine/service binding records are security-bound association tables and must
carry an explicit tenant reference; they are not part of this current-table
count.

## 7. Repository/query inventory

There are 25 repository modules over tenant-owned tables. Static AST inspection
found 131 public, session-backed functions requiring a `TenantContext` or
explicit `tenant_id` and tenant predicate. Pure serialization helpers are not
counted. Existing signatures below are exact; the future requirement is to add
tenant context without weakening existing filters.

| Repository | Count | Current session-backed functions requiring tenant scope |
|---|---:|---|
| `action_approval_repository.py` | 7 | `load_action_approval_record`, `list_action_approval_records`, `list_active_action_approval_records`, `find_pending_action_approval_record`, `create_action_approval_record`, `transition_action_approval_record`, `list_action_approval_events` |
| `agent_repository.py` | 11 | `create_enrollment_token`, `enroll_agent`, `authenticate_agent`, `list_agents`, `load_agent`, `load_agent_record`, `record_heartbeat`, `record_snapshot_success`, `revoke_agent`, `agent_health`, `agent_plugins` |
| `build_artifact_evidence_repository.py` | 3 | `save_build_artifact_evidence`, `list_build_artifact_evidence`, `list_build_artifact_evidence_for_image_digest` |
| `causal_analysis_repository.py` | 3 | `save_causal_analysis`, `load_causal_analysis`, `latest_causal_analysis` |
| `change_event_repository.py` | 5 | `change_event_view`, `load_change_event`, `correlate_change_event`, `ingest_change_event`, `list_change_events` |
| `change_repository.py` | 4 | `save_changes`, `list_changes`, `load_change`, `find_changes_in_window` |
| `change_source_repository.py` | 7 | `create_change_source`, `load_change_source`, `get_change_source`, `list_change_sources`, `update_change_source`, `list_deliveries`, `list_dead_letters` |
| `cloud_repository.py` | 5 | `persist_cloud_inventory`, `list_cloud_accounts`, `list_cloud_resources`, `latest_cloud_topology`, `agent_cloud_status` |
| `copilot_repository.py` | 6 | `create_copilot_session_record`, `load_copilot_session_record`, `list_copilot_messages`, `load_copilot_session_detail`, `list_incident_copilot_sessions`, `save_copilot_message` |
| `execution_intent_repository.py` | 12 | `load_execution_intent_record`, `load_execution_intent_by_key`, `load_execution_intent_by_approval`, `list_execution_intent_records`, `create_execution_intent_record`, `atomic_claim_execution_intent_record`, `atomic_release_execution_claim_record`, `atomic_expire_execution_claim_record`, `atomic_cancel_execution_intent_record`, `atomic_invalidate_execution_intent_record`, `atomic_expire_execution_intent_record`, `list_execution_intent_events` |
| `identity_repository.py` | 5 | `save_identity_resolution`, `load_identity_resolution`, `upsert_identity_override`, `list_identity_overrides`, `deactivate_identity_override` |
| `incident_explanation_repository.py` | 4 | `load_incident_explanation`, `load_latest_incident_explanation`, `list_incident_explanations`, `save_incident_explanation` |
| `incident_outcome_repository.py` | 4 | `load_incident_outcome_record`, `list_incident_outcome_records`, `load_incident_outcome`, `save_incident_outcome` |
| `incident_record_repository.py` | 7 | `get_incident_by_fingerprint`, `find_correlatable_incident`, `list_incidents_by_fingerprint`, `load_incident_record`, `list_incident_records`, `save_incident_record`, `update_incident_status` |
| `incident_repository.py` | 3 | `save_incident_analysis`, `load_incident_analysis`, `list_incident_analyses` |
| `investigation_plan_repository.py` | 4 | `load_investigation_plan`, `list_incident_investigation_plans`, `create_investigation_plan`, `update_investigation_step` |
| `ownership_repository.py` | 5 | `load_ownership_mapping`, `get_ownership_by_fingerprint`, `find_active_ownership_mappings`, `list_ownership_mappings`, `save_ownership_mapping` |
| `post_incident_report_repository.py` | 6 | `load_post_incident_report`, `load_latest_post_incident_report`, `list_post_incident_reports`, `create_post_incident_report`, `update_post_incident_report`, `update_report_action_item` |
| `recommendation_repository.py` | 4 | `save_recommendation`, `load_recommendation`, `list_recommendations`, `update_recommendation_status` |
| `recovery_repository.py` | 3 | `save_recovery_verification`, `load_recovery_verification`, `list_recovery_verifications` |
| `runtime_observability_repository.py` | 4 | `record_sensor_heartbeat`, `ingest_runtime_event_batch`, `list_runtime_sensors`, `list_runtime_dependencies` |
| `signal_repository.py` | 5 | `save_signals`, `list_signals`, `list_signals_by_incident_fingerprint`, `load_signal`, `find_signals_after` |
| `snapshot_repository.py` | 4 | `save_snapshot`, `list_snapshots`, `get_snapshot_record`, `load_snapshot` |
| `topology_snapshot_repository.py` | 1 | `load_topology_snapshot` |
| `webhook_repository.py` | 9 | `create_webhook_endpoint`, `load_webhook_endpoint_record`, `load_webhook_endpoint`, `list_webhook_endpoint_records`, `list_webhook_endpoints`, `update_webhook_endpoint`, `find_delivery_record`, `save_delivery_result`, `list_webhook_deliveries` |

The security-global `auth_session_repository.py` and
`auth_api_credential_repository.py` are excluded from the 25/131 tenant-owned
counts. They remain identity lookup repositories. A later service-credential
binding lookup must join/resolve a separate fixed tenant binding after
authentication.

Every direct load changes conceptually from `load_x(id)` to
`load_x(tenant_id, id)` (or `load_x(context, id)`). Every list, latest, count,
search, fingerprint, time-window, correlation, replay, upsert, transition, and
delete query begins with the tenant predicate. Filtering only after rows are
loaded is forbidden.

### Direct ORM paths outside repositories

Static inspection found 20 tenant-sensitive functions in 11 service files
using `session.get/scalar/scalars/add` directly:

| File | Functions |
|---|---|
| `services/causal_rca.py` | `_snapshot_for_incident`, `analyze_causal_rca` |
| `services/change_source_ingest.py` | `_existing_delivery`, `ingest_change_source_webhook`, `replay_dead_letter` |
| `services/continuous_lifecycle.py` | `reconcile_pending_incidents_for_checkpoint` |
| `services/incident_change_analysis.py` | `_snapshot_for_incident`, `_candidate_for_record`, `analyze_incident_change_events` |
| `services/incident_explanation.py` | `_load_optional_record` |
| `services/incident_lifecycle.py` | `upsert_incident_from_orchestration` |
| `services/lifecycle_status.py` | `_latest`, `build_lifecycle_status`, `build_incident_lifecycle_status` |
| `services/lineage_candidate_admission.py` | `_source_event`, `evaluate_lineage_candidate_admission` |
| `services/runtime_snapshot_enrichment.py` | `enrich_snapshot_with_runtime_dependencies` |
| `services/temporal_semantics.py` | `safe_snapshot_record_at_or_before`, `incident_operational_time` |
| `services/topology_checkpoint.py` | `latest_checkpoint_record` |

There is no tenant-sensitive literal/raw SQL in `backend/app`. The three domain
`session.execute()` sites in `agent_repository.py` and
`execution_intent_repository.py` use SQLAlchemy expressions and still require
tenant predicates. `main.py` owns the injected `SessionLocal` factory; it is
not a domain query. Future architecture tests must fail on a domain select,
update, delete, or direct `Session.get()` without a tenant condition.

No cross-request customer cache exists in current backend product code. The
blast-radius aggregate map is invocation-local. Cached incident explanation is
database-backed and therefore must use tenant-scoped repository lookup. Future
cache keys must begin with tenant ID, for example
`(tenant_id, incident_id, ...)`.

Current product report export is response rendering rather than a durable
customer filesystem store. No backend product code writes tenant reports or
exports to shared paths. If later durable files are introduced, paths and
object-store keys must be tenant-prefixed and authorization must precede file
resolution. Evaluation artifacts and frozen evaluation databases are outside
the product tenant store.

## 8. API route tenancy inventory

The accepted production application has 136 method/path pairs: 125 human, eight
agent, one provider callback, and two public. PH-3A classifies every pair; no
route is ambiguous.

### Human routes — tenant required (116)

The following authenticated method/path pairs require a validated
`TenantContext`. The list is exhaustive at the accepted commit.

```text
GET    /api/v1/agents
POST   /api/v1/agents/enrollment-tokens
GET    /api/v1/agents/{agent_id}
GET    /api/v1/agents/{agent_id}/cloud-status
GET    /api/v1/agents/{agent_id}/health
GET    /api/v1/agents/{agent_id}/plugins
POST   /api/v1/agents/{agent_id}/revoke
GET    /api/v1/agents/{agent_id}/runtime-dependencies
GET    /api/v1/agents/{agent_id}/sensors
GET    /api/v1/automation/status
GET    /api/v1/causal-analyses/{analysis_id}
GET    /api/v1/change-events
POST   /api/v1/change-events
GET    /api/v1/change-events/{event_id}
POST   /api/v1/change-events/{event_id}/correlate
GET    /api/v1/change-sources
POST   /api/v1/change-sources
GET    /api/v1/change-sources/dead-letters
POST   /api/v1/change-sources/dead-letters/{dead_letter_id}/replay
GET    /api/v1/change-sources/deliveries
GET    /api/v1/change-sources/{source_id}
PATCH  /api/v1/change-sources/{source_id}
GET    /api/v1/change-sources/{source_id}/doctor
GET    /api/v1/changes
POST   /api/v1/changes/from-diff
GET    /api/v1/changes/{change_id}
GET    /api/v1/clouds/accounts
GET    /api/v1/clouds/resources
GET    /api/v1/clouds/topology
POST   /api/v1/github/actions/enrich
GET    /api/v1/github/connection
POST   /api/v1/github/enrich
POST   /api/v1/identities/materialize
GET    /api/v1/identities/overrides
POST   /api/v1/identities/overrides
DELETE /api/v1/identities/overrides/{override_id}
GET    /api/v1/identities/resolve
GET    /api/v1/identities/stored
GET    /api/v1/incident-records
GET    /api/v1/incident-records/{incident_id}
GET    /api/v1/incident-records/{incident_id}/signals
PATCH  /api/v1/incident-records/{incident_id}/status
GET    /api/v1/incidents
POST   /api/v1/incidents/analyze
GET    /api/v1/incidents/{analysis_id}
GET    /api/v1/incidents/{incident_id}/approvals
POST   /api/v1/incidents/{incident_id}/approvals
GET    /api/v1/incidents/{incident_id}/approvals/{approval_id}
POST   /api/v1/incidents/{incident_id}/approvals/{approval_id}/approve
POST   /api/v1/incidents/{incident_id}/approvals/{approval_id}/reject
POST   /api/v1/incidents/{incident_id}/approvals/{approval_id}/revoke
GET    /api/v1/incidents/{incident_id}/blast-radius
GET    /api/v1/incidents/{incident_id}/briefing
POST   /api/v1/incidents/{incident_id}/causal-rca
GET    /api/v1/incidents/{incident_id}/causal-rca/latest
GET    /api/v1/incidents/{incident_id}/change-events
GET    /api/v1/incidents/{incident_id}/copilot/sessions
POST   /api/v1/incidents/{incident_id}/copilot/sessions
GET    /api/v1/incidents/{incident_id}/copilot/sessions/{session_id}
POST   /api/v1/incidents/{incident_id}/copilot/sessions/{session_id}/messages
GET    /api/v1/incidents/{incident_id}/execution-intents
POST   /api/v1/incidents/{incident_id}/execution-intents
GET    /api/v1/incidents/{incident_id}/execution-intents/{execution_id}
POST   /api/v1/incidents/{incident_id}/execution-intents/{execution_id}/cancel
GET    /api/v1/incidents/{incident_id}/execution-readiness
GET    /api/v1/incidents/{incident_id}/explanations
POST   /api/v1/incidents/{incident_id}/explanations
GET    /api/v1/incidents/{incident_id}/explanations/latest
GET    /api/v1/incidents/{incident_id}/historical-intelligence
GET    /api/v1/incidents/{incident_id}/investigation-plans
POST   /api/v1/incidents/{incident_id}/investigation-plans
GET    /api/v1/incidents/{incident_id}/investigation-plans/{plan_id}
PATCH  /api/v1/incidents/{incident_id}/investigation-plans/{plan_id}/steps/{step_id}
GET    /api/v1/incidents/{incident_id}/lifecycle-status
GET    /api/v1/incidents/{incident_id}/operational-context
GET    /api/v1/incidents/{incident_id}/outcome
POST   /api/v1/incidents/{incident_id}/outcome
GET    /api/v1/incidents/{incident_id}/ownership-impact
GET    /api/v1/incidents/{incident_id}/reports
POST   /api/v1/incidents/{incident_id}/reports
GET    /api/v1/incidents/{incident_id}/reports/{report_id}
PATCH  /api/v1/incidents/{incident_id}/reports/{report_id}
PATCH  /api/v1/incidents/{incident_id}/reports/{report_id}/actions/{action_item_id}
GET    /api/v1/incidents/{incident_id}/reports/{report_id}/export
GET    /api/v1/incidents/{incident_id}/response-intelligence
GET    /api/v1/incidents/{incident_id}/response-plan
GET    /api/v1/incidents/{incident_id}/suspected-change-events
GET    /api/v1/integrations/deliveries
GET    /api/v1/integrations/webhooks
POST   /api/v1/integrations/webhooks
PATCH  /api/v1/integrations/webhooks/{webhook_id}
POST   /api/v1/integrations/webhooks/{webhook_id}/test
GET    /api/v1/kubernetes/connection
POST   /api/v1/kubernetes/discover
POST   /api/v1/orchestration/signals/{signal_id}/run
GET    /api/v1/ownership/mappings
POST   /api/v1/ownership/mappings
GET    /api/v1/ownership/resolve
POST   /api/v1/predeployment/analyze
GET    /api/v1/recommendations
POST   /api/v1/recommendations/generate
GET    /api/v1/recommendations/{recommendation_id}
PATCH  /api/v1/recommendations/{recommendation_id}/status
GET    /api/v1/recovery
POST   /api/v1/recovery/verify
GET    /api/v1/recovery/{verification_id}
GET    /api/v1/signals
POST   /api/v1/signals/ingest
POST   /api/v1/signals/kubernetes/events/ingest
GET    /api/v1/signals/{signal_id}
GET    /api/v1/snapshots
POST   /api/v1/snapshots/capture
GET    /api/v1/snapshots/diff
GET    /api/v1/snapshots/{snapshot_id}
GET    /api/v1/snapshots/{snapshot_id}/network-dependencies
POST   /api/v1/topology/validate
```

The `incidents/{analysis_id}` and `incidents/{incident_id}` path shapes overlap
semantically in different routers; both remain tenant-required and future
lookup order must not permit a foreign record to affect routing or error text.

### Human routes — security/installation global (9)

| Route | Classification | Contract |
|---|---|---|
| `GET /api/v1/topology/sample` | `INSTALLATION_GLOBAL` | Static synthetic sample only; it contains no customer persistence. Authentication remains required. |
| `POST /api/v1/auth/session` | `SECURITY_GLOBAL` | Exchanges eligible human bearer authority for identity session; no active tenant is embedded. |
| `GET /api/v1/auth/session` | `SECURITY_GLOBAL` | Returns authentication session identity only. |
| `DELETE /api/v1/auth/session` | `SECURITY_GLOBAL` | Revokes authentication session identity only. |
| `POST /api/v1/auth/api-credentials` | `SECURITY_GLOBAL` | Current identity credential lifecycle. Later fixed service credential creation should move to or atomically invoke a tenant-scoped binding operation. |
| `GET /api/v1/auth/api-credentials` | `SECURITY_GLOBAL` | Lists credentials under PH-2 security policy, not customer domain rows. |
| `GET /api/v1/auth/api-credentials/{credential_id}` | `SECURITY_GLOBAL` | Security-object lookup. |
| `POST /api/v1/auth/api-credentials/{credential_id}/revoke` | `SECURITY_GLOBAL` | Security-object revocation. |
| `GET /api/v1/system/whoami` | `SECURITY_GLOBAL` | Reports authentication identity; future tenant membership discovery should use a separate bounded endpoint. |

### Machine and public routes

| Routes | Count | Tenant source |
|---|---:|---|
| `POST /api/v1/agents/enroll` | 1 | Server loads the enrollment credential, obtains its fixed tenant, and atomically creates the agent with that tenant. Body tenant claims are forbidden. |
| `GET /api/v1/agent/config`; `POST /api/v1/agent/heartbeat`; `POST /api/v1/agent/snapshots`; `POST /api/v1/agent/runtime/heartbeat`; `POST /api/v1/agent/runtime/batches`; `POST /api/v1/agent/change-events`; `POST /api/v1/agent/signals` | 7 | Server authenticates the agent and derives tenant from `topo_agents`. Payload tenant claims are ignored/rejected. |
| `POST /api/v1/change-source-webhooks/{source_id}` | 1 | Server authenticates the source and derives tenant from `change_sources` before parsing/persisting domain data. |
| `GET /health`; `GET /ready` | 2 | Public minimal liveness/readiness; no tenant or customer data. |

CORS `OPTIONS` is a public transport preflight, not a business route and not a
tenant authority. Production-disabled documentation routes remain outside the
136-pair production inventory.

## 9. Agent tenant propagation contract

Agent enrollment must preserve PH-2D atomic max-use semantics while adding the
tenant invariant:

```text
authenticate enrollment secret
  -> lock/conditionally consume enrollment credential for tenant T
  -> create agent with tenant_id = T
  -> commit consumption and agent together
  -> return one-time steady-state credential
```

The future enrollment-credential row and `topo_agents` row both carry direct
tenant IDs. A body field cannot select or override T. A failed agent insert
rolls back token consumption exactly as PH-2D requires.

Steady state authenticates the opaque agent secret globally, loads the agent,
then constructs `TenantContext` from the persisted agent binding. Config,
heartbeat, snapshot, runtime, change-event, signal, cloud, and lifecycle paths
inherit that context. Agent, cluster, environment, and namespace scope are
validated inside T; cluster `prod` is not an installation-global identity.

## 10. Provider tenant propagation contract

Provider callbacks do not use a human tenant selector:

```text
route source_id
  -> load candidate source without exposing existence
  -> authenticate raw request using that source's PH-2D mechanism
  -> derive tenant_id from the authenticated source
  -> create provider TenantContext
  -> parse, deduplicate, normalize, link, and persist only in that tenant
```

Unknown, disabled, misconfigured, and invalidly authenticated sources retain
bounded PH-2 response semantics. Provider payload fields, repository
organization names, account aliases, delivery IDs, or custom headers never
select tenant.

Propagation is `change_sources -> change_source_deliveries/dead_letters ->
change_events -> change_entity_links/build_artifact_evidence -> incident/RCA`.
Every link is same-tenant. Delivery replay re-derives context from the persisted
dead letter/source, not from replay request payload.

## 11. Background-job tenant propagation contract

The current backend has no general scheduler or unbounded product work queue.
Pending-incident reconciliation is invoked synchronously from agent snapshot
ingest, webhook processing is request-bound, and execution worker transaction
functions are preserved foundations rather than the V1 product path.

Every future work item must contain either `(tenant_id, object_id)` or reference
a persisted row that itself has a direct tenant ID. Workers load with both
values, build an internal `TenantContext(selection_source="persisted_work_item")`,
and reject missing/mismatched tenant data. Workers must never scan “all
tenants” and then filter in memory, infer tenant from an object ID, or inherit
ambient request/global state. Retry, dedupe, lease, claim, cancellation, and
dead-letter keys all include tenant scope.

Periodic reconciliation runs as a bounded per-tenant loop over active tenants,
with one tenant context at a time. Failure in one tenant cannot suppress or
merge work in another. Cross-tenant operational analytics/support tooling is
not part of V1.

## 12. Human membership model

The future conceptual association is:

```text
tenant_memberships(
    membership_id,
    tenant_id,
    subject,
    status,        # active | disabled
    created_at,
    updated_at,
)
```

Membership answers only “may this stable authenticated identity enter this
tenant?” Role/permission semantics remain PH-5. V1 may use the PH-2
`AuthPrincipal.subject` as the membership key because static bootstrap,
named-human API credentials, and browser-session reconstruction preserve that
stable subject. Subject must remain non-empty, non-`unknown`, and have
installation-wide identity semantics.

Subject alone is not a permanent OIDC model. Before federated identity is
introduced, membership should migrate to a stable internal principal identity
whose external key is issuer plus subject. This is a documented future
compatibility requirement, not a PH-3A blocker and not authority to create a
user table now.

## 13. Service credential tenant model

V1 `service_api` credentials are bound to exactly one tenant. Arbitrary tenant
switching is forbidden. The preferred representation is a separate durable
`service_credential_tenant_bindings` association keyed by `credential_id` and
`tenant_id`, not a tenant column on the security-global credential row. This
keeps credential identity, membership/binding, and request context separate.

Creation must be atomic with the fixed binding and must require a human who is
both authorized for that tenant and permitted by later PH-5 policy. A global
credential endpoint must not mint unbound service credentials; a later
tenant-scoped service-credential operation is preferable. Authentication
loads the credential and fixed binding server-side and creates the tenant
context without accepting `X-Topo-Tenant-ID` from service automation.

## 14. Browser/CLI tenant-selection recommendation

Human V1 requests use `X-Topo-Tenant-ID` on tenant-required APIs. Middleware or
a single dependency validates active tenant status and active membership, then
creates `TenantContext`. The header is an untrusted selector, not authority.
It must be added to the bounded CORS allow-header policy during implementation.

Explicit context is required even for a human with one active membership. The
server must not select the first database row or silently switch after
membership changes. Browser UX may automatically choose the sole membership,
but the central API client still sends it explicitly and the server validates
it on every request. Tenant switching clears/refetches all tenant-owned client
state; individual pages do not implement tenant selection.

CLI profiles may store a non-secret preferred tenant ID and expose an explicit
`--tenant` override. Raw credentials remain in the keyring. The CLI sends the
selector, but the server revalidates membership every time. A stored tenant ID
is never authorization. Fixed-tenant service credentials do not accept the
override.

Static bootstrap is installation-level break-glass authentication. It may
create the first tenant and initial membership or perform bounded recovery. It
does not implicitly read all tenants. After bootstrap, customer data-plane
access requires ordinary membership; comprehensive installation support is a
separate future audited/RBAC design.

## 15. Canonical identity collision audit

TC-1 remains authoritative inside one immutable topology snapshot. Kubernetes
UID/scoped tuple, provider-native cloud IDs, repository-scoped commits,
provider/pipeline-scoped builds, and digest/reference image identities retain
their accepted source meaning. Historical snapshots and entity IDs are not
rewritten.

Tenant is an **outer mandatory security namespace**, not a casual prefix added
to every source-native identity string:

```text
(tenant_id, snapshot_id, Entity.id)
(tenant_id, canonical source identity)
(tenant_id, relationship endpoint/type identity)
```

Two tenants may therefore contain the exact same TC-1 `Entity.id` in different
snapshot payloads without being the same customer object. Resolution,
snapshot diff, aliases, blast radius, change linking, and RCA operate only on
snapshots already proven to belong to the active tenant. Any materialized
lookup/cache uses the tuple, never bare `Entity.id`.

For persisted single-column deterministic primary keys, outer predicates alone
cannot prevent an insert collision because current PKs are installation-global.
Later implementation must either tenant-namespace the generated opaque PK
digest or adopt a reviewed composite-key strategy. The preferred V1 approach
is to preserve single-column API IDs and include tenant ID in deterministic
persisted-record ID builders, while leaving source-native TC-1 strings inside
snapshot payloads unchanged. Random opaque IDs still require tenant predicates
but need no collision-builder change.

## 16. Deterministic primary-key collision audit

The static audit groups concrete helper/call-site implementations into 28
collision-sensitive builder families. Twenty-seven need tenant context in
their storage/deduplication namespace. The final security/content-digest family
is safe without changing the digest algorithm; tenant ownership of records is
still enforced separately. “Tenant scope required” may mean scoping the query
or storage key, not altering a Truth Contract string.

| # | Actual builder family / representative symbols | Current inputs and collision result | Decision |
|---:|---|---|---|
| 1 | `canonical_kubernetes_identity` | UID or cluster/kind/namespace/name; same customer-local K8s identity can exist in two tenants. | `TENANT_SCOPE_REQUIRED`; preserve TC-1 string. |
| 2 | `canonical_aws_identity` | Account/region/type/resource ID or ARN; delegated/shared observations may belong to multiple tenants. | `TENANT_SCOPE_REQUIRED`; preserve native meaning. |
| 3 | `canonical_azure_identity` | Normalized full Azure resource ID. | `TENANT_SCOPE_REQUIRED`; preserve native meaning. |
| 4 | `canonical_gcp_identity` | Normalized full GCP resource identity. | `TENANT_SCOPE_REQUIRED`; preserve native meaning. |
| 5 | `canonical_git_repository_identity` | Host + provider repository ID/name fallback. | `TENANT_SCOPE_REQUIRED`; same integration may be connected by multiple tenants. |
| 6 | `canonical_git_commit_identity` | Repository canonical ID + SHA. | `TENANT_SCOPE_REQUIRED`; preserve repository-scoped TC-1 identity. |
| 7 | `canonical_ci_build_identity`, `canonical_github_workflow_run_identity` | Provider/pipeline/run identifiers. | `TENANT_SCOPE_REQUIRED`. |
| 8 | `canonical_container_image_identity` | Immutable digest or normalized mutable reference. | `TENANT_SCOPE_REQUIRED`; identical artifact does not authorize cross-tenant evidence. |
| 9 | Kubernetes collector `_cluster_id`, `_entity_id`, `_relationship_id` | Cluster and scoped object values; local names collide. | `TENANT_SCOPE_REQUIRED`. |
| 10 | Agent cloud/Azure/GCP `_entity_id`, `_azure_entity_id`, `_parent_id` | Provider/native IDs and account/project scope. | `TENANT_SCOPE_REQUIRED`. |
| 11 | Agent snapshot/runtime `_entity_id`, `_relationship_id` | Cluster/object/runtime endpoint values. | `TENANT_SCOPE_REQUIRED`. |
| 12 | GitHub repository/commit/Actions graph `_repository_entity_id`, `_commit_entity_id`, `_workflow_run_entity_id`, relationship/evidence IDs | Provider IDs, SHA, run, graph endpoints. | `TENANT_SCOPE_REQUIRED`. |
| 13 | Container image graph `_image_entity_id`, `_relationship_id` | Reference/digest and graph endpoints. | `TENANT_SCOPE_REQUIRED`. |
| 14 | Network topology `_entity_id`, `_relationship_id` | Host/container/network/address/port inputs. | `TENANT_SCOPE_REQUIRED`. |
| 15 | Identity resolver/override `_identity_id` | Snapshot/entity/override target inputs. | `TENANT_SCOPE_REQUIRED`. |
| 16 | Kubernetes event `_fingerprint`, `_signal_id` | Cluster/namespace/object/reason/action/time inputs. | `TENANT_SCOPE_REQUIRED`; otherwise incident source collisions. |
| 17 | Change normalizer `_fingerprint`, `_change_id` | Snapshot/entity/relationship/change values. | `TENANT_SCOPE_REQUIRED`. |
| 18 | Change-event repository `_event_fingerprint`, `_event_id`, `_link_id` | Source/external/scope/change/entity values. | `TENANT_SCOPE_REQUIRED`. |
| 19 | Change-source `_source_id`, source-delivery ID and `delivery_key` | Source type/name, source ID, provider delivery/payload. | `TENANT_SCOPE_REQUIRED`. |
| 20 | Cloud repository `_cloud_resource_id` | Provider/account/region/type/resource ID. | `TENANT_SCOPE_REQUIRED`. |
| 21 | Runtime repository `_dependency_id`, `_process_id`, sensor business key | Agent/sensor/pod/container/process/endpoint values. | `TENANT_SCOPE_REQUIRED`. |
| 22 | `incident_fingerprint`, lifecycle `_incident_id`, orchestrator `_orchestration_id` | Failure entity/scope/category/window and signal/snapshot values. | `TENANT_SCOPE_REQUIRED`; correlation query must start with tenant. |
| 23 | Incident-analysis and causal `_analysis_id`, `_hypothesis_id`, `_evidence_id`, causal `_stable_id` | Signal/snapshot/incident/event/evidence inputs. | `TENANT_SCOPE_REQUIRED`. |
| 24 | Recommendation, response-plan, recovery-verification, predeployment IDs | Analysis/action/change/entity/snapshot inputs. | `TENANT_SCOPE_REQUIRED`. |
| 25 | Explanation, investigation plan/step, report/action, outcome, memory feature IDs/hashes | Incident/evidence/version/action inputs. | `TENANT_SCOPE_REQUIRED`. |
| 26 | Ownership mapping fingerprint | Service/entity/scope/team mapping inputs. | `TENANT_SCOPE_REQUIRED`. |
| 27 | Approval evidence/`pending_key`, execution idempotency, webhook event/delivery keys | Incident/action/evidence/endpoint/resource inputs. | `TENANT_SCOPE_REQUIRED`. |
| 28 | API/session/agent secret digests and immutable content/payload digests | High-entropy secrets or byte content. | `SAFE_GLOBAL_ID` for digest computation; secret uniqueness/auth lookup may remain global. Dedupe of tenant rows still includes tenant. |

Totals: 28 builder families audited; 27 require tenant scope; one is safe
without tenant modification; zero are ambiguous. Provider-native global IDs
are not treated as tenant authority even when their source uniqueness is
strong.

## 17. Unique constraint/index migration impact

Current domain schema has ten named unique constraints and nine unique indexes.
Seven of the nine unique indexes encode tenant-domain uniqueness. The two agent
credential token-hash indexes remain globally unique for credential safety.
The two security-global auth digest constraints also remain global.

Tenant scope is required for these ten named constraints:

1. `uq_action_approval_event_sequence`
2. `uq_build_artifact_provider_fact`
3. `uq_change_event_entity_link`
4. `uq_execution_intent_event_sequence`
5. `uq_identity_override_target`
6. `uq_investigation_plan_sequence`
7. `uq_post_incident_report_action_sequence`
8. `uq_post_incident_report_version`
9. `uq_runtime_sensor_agent_node_source`
10. `uq_webhook_delivery_event`

Tenant scope is required for these seven unique indexes:

1. `ix_action_approvals_pending_key`
2. `ix_change_events_event_fingerprint`
3. `ix_change_source_deliveries_delivery_key`
4. `ix_execution_intents_approval_id`
5. `ix_execution_intents_idempotency_key`
6. `ix_incident_outcomes_incident_id`
7. `ix_ownership_mappings_fingerprint`

The 38 domain tables contain 287 current ordinary indexes. All 287 are in the
tenant-index review set because domain queries may not scan another tenant.
Implementation should not blindly clone every index: retain selectivity and
query plans, but make tenant a leading component or add a tenant-leading
companion for actual list/latest/filter/join paths. Priority patterns are
`(tenant_id, id)`, `(tenant_id, status, time)`, `(tenant_id, fingerprint)`,
`(tenant_id, incident_id, time)`, `(tenant_id, source_id, time)`,
`(tenant_id, agent_id, time)`, `(tenant_id, cluster_name, namespace, time)`,
and `(tenant_id, snapshot_id/entity_id)`.

Later migrations must inspect duplicates per legacy tenant before replacing
constraints. Adding a column and removing global uniqueness in one unsafe step
is forbidden. PostgreSQL query-plan/index validation belongs to the PH-3
acceptance block and PH-10 concurrency/performance work.

## 18. Incident/topology/RCA isolation rules

1. Signal correlation and incident fingerprint lookup always include tenant.
   Tenant A `prod/default/checkout` never joins Tenant B with the same values.
2. A new or correlated incident, all signals, and its affected entity share
   tenant. Correlated signals cannot move the incident's original topology pin.
3. Snapshot selection queries only snapshots for the incident tenant. Historical
   at-or-before and incident-boundary semantics remain unchanged; there is no
   latest-snapshot fallback across or within tenants.
4. Every nested affected entity or relationship is resolved only inside the
   tenant-proven pinned snapshot. Bare entity IDs have no installation-global
   authority.
5. Snapshot diff requires both snapshots have the same tenant. A mismatch is a
   bounded client error/security audit event, never an empty diff.
6. Causal candidate windows, change links, root events, build evidence,
   hypotheses, counterevidence, and evidence ledger rows are tenant-local.
7. `latest_causal_analysis` means latest for `(tenant_id, incident_id)`.
8. Blast radius traverses only the pinned same-tenant graph. Cloud/runtime
   enrichment records must share tenant with the snapshot/agent.
9. Briefing and lifecycle orchestration reuse these scoped services; they do
   not perform a global lookup by incident or analysis ID.

These rules preserve TC-1 through TC-5 and historical correctness. PH-3 adds
security scope; it does not reinterpret evidence, confidence, provenance, or
time.

## 19. Ownership/memory/report isolation

- Ownership mappings and business-impact resolution are tenant-scoped. The
  team name `payments`, a repository URL, email, and on-call contact are not
  shared catalog entries.
- Historical incident memory and similarity scan only tenant incidents,
  analyses, outcomes, actions, and feature fingerprints. Cross-customer
  “learning” is forbidden even if names/fingerprints match.
- Response intelligence, remediation guidance, recovery checks, and outcome
  derivation use only same-tenant parents/evidence.
- LLM prompts are assembled only after tenant-scoped deterministic retrieval.
  The model cannot select tenant, expand search, or return an ID that bypasses
  same-tenant validation. Provider failure/fallback does not weaken isolation.
- Copilot sessions/messages, explanations, investigation plans, post-incident
  reports, action items, and exports are tenant-scoped end to end. Export
  authorization occurs before rendering.
- Outbound webhook endpoints and deliveries are tenant-owned; a payload is sent
  only to an endpoint from the resource tenant.
- 14G approvals and 14H execution intents remain preserved but tenant-scoped.
  Claims, idempotency, events, and actor audit never cross tenants. PH-3 does
  not make execution part of the V1 product.

## 20. IDOR threat model

Primary threats are guessed/observed object IDs, nested child IDs, foreign
parent IDs in create/update payloads, list/count side channels, provider source
enumeration, cache-key collisions, report exports, and background work carrying
only a globally shaped ID.

Frozen outward semantics:

| Condition | Response |
|---|---|
| Missing/invalid authentication | `401` under PH-2 semantics. |
| Missing required human tenant selector | `400` with a bounded generic contract error. |
| Selected tenant is absent, disabled, or caller has no active membership | Same generic `403` (“Tenant access is not permitted”); do not reveal existence or status. |
| Object does not exist under an authorized tenant, including an ID belonging to another tenant | `404` with the same resource-not-found shape. |
| Caller is a tenant member but lacks a later PH-5 action permission | `403`. |
| Parent/child/reference tenant mismatch on mutation | Bounded `404` for caller-supplied resource references, transaction rollback, and security audit; never attach it. |

Every object query is `WHERE tenant_id = :tenant_id AND id = :id`. Lists,
searches, counts, pagination totals, existence checks, uniqueness checks,
latest queries, exports, and correlations are tenant-predicated in SQL. No
post-query filtering and no cross-tenant “admin search” are allowed in V1.

On child creation/update, the server loads every parent and durable reference
under the same tenant in the same transaction. Serialized arrays/evidence IDs
are validated likewise when they carry authoritative references. The invariant
is: **no tenant-owned row or evidence payload may authoritatively reference a
row from another tenant**.

## 21. Two-tenant adversarial corpus

Future acceptance uses two real tenants with deliberately identical local
values:

| Field | Tenant A | Tenant B |
|---|---|---|
| cluster | `prod` | `prod` |
| namespace | `default` | `default` |
| workload/service | `checkout` | `checkout` |
| Kubernetes object name | `checkout-api` | `checkout-api` |
| ownership team | `payments` | `payments` |
| source display name | `production` | `production` |
| repository fallback/name | `checkout` | `checkout` |
| cloud account alias | `production` | `production` |
| signal/change/incident source-local fingerprint inputs | identical | identical |
| webhook event/resource local IDs | identical | identical |

Acceptance must prove independent inserts, tenant-scoped unique behavior,
lists/counts/latest/search, direct-ID 404 behavior, child-parent mismatch
rejection, incident correlation separation, pinned snapshot separation,
change/RCA/ownership/history/LLM/report isolation, provider replay separation,
agent telemetry separation, cache/work-item separation, and disabled-tenant
denial. It must attempt cross-tenant IDs through every nested incident/report/
approval route, not merely top-level list endpoints.

## 22. Existing-data migration/backfill recommendation

Current single-installation domain data has no provable customer owner. It must
not be silently assigned based on company text, email, cluster, source, or the
first tenant row. The later migration requires an operator-selected legacy
tenant:

1. Back up and verify the database under PH-1 operations.
2. Create one explicit legacy tenant with a server-generated ID and operator
   supplied display label.
3. Create explicit bootstrap membership for an operator-selected stable
   subject.
4. Add nullable tenant columns to the 38 domain tables.
5. Backfill direct roots to the explicit legacy tenant and derived rows through
   validated parent/reference order; because there are no FKs, run cross-table
   and serialized-reference audits.
6. Quarantine/orchestrator-stop on an orphan or conflicting inferred parent;
   do not guess ownership.
7. Add fixed agent enrollment/agent/provider/service bindings.
8. Validate non-null tenant, same-tenant references, deterministic-ID collision
   reports, and tenant-scoped uniqueness.
9. Deploy tenant-aware dual-read/write only under a reviewed rollout contract,
   replace uniqueness/indexes, then enforce non-null and request predicates.
10. Remove any legacy compatibility path only after adversarial and PostgreSQL
    acceptance.

The unmanaged developer SQLite database may later be migrated only through an
explicit developer legacy tenant after backup; PH-3A does not touch it. Fresh
development/test databases should create explicit tenants/memberships rather
than a magical global tenant.

## 23. Frozen evaluation/data custody treatment

`evaluation/results/lineage/post-sc4/topo-product-32695735269.db` is immutable
evidence custody. It is never upgraded, stamped, backfilled, or used as a live
tenant store. Future tenant-aware evaluations copy it into a disposable
workspace only when historical fixture compatibility is required, or prefer a
fresh tenant-aware database with explicit fixture tenants. Golden hashes remain
the authority for the original artifact.

Likewise, PH-3A does not initialize, migrate, or write `backend/data/topo.db`.
Migrations `0001`, `0002`, and `0003` remain immutable. PH-3 implementation
must use additive new revisions; no accepted baseline is edited or rebaselined.

## 24. Recommended PH-3 implementation decomposition

### PH-3B — Tenant Foundation + Membership + Request Tenant Context

Add tenant root, human memberships, service binding, immutable
`TenantContext`, header/membership validation, bootstrap-to-first-tenant flow,
error semantics, and security-global route separation. Do not yet claim all
domain persistence is isolated.

### PH-3C — Domain Tenant Columns + Backfill + Constraint/Index Migration

Add direct tenant ID to all 38 domain tables, explicit legacy backfill tooling,
same-tenant validation, deterministic persisted-ID namespacing, tenant-scoped
unique constraints, and priority indexes. Preserve frozen databases.

### PH-3D — Agent + Provider + Cloud Tenant Propagation

Bind enrollment credentials, agents, provider sources, cloud inventory,
runtime data, snapshots, signals, changes, deliveries, and replays to server-
derived tenant context while preserving PH-2D authentication/atomicity.

### PH-3E — Repository, Service, API, Lifecycle + Worker Isolation

Convert all 131 repository methods and the 20 direct-session functions; enforce
same-tenant incident/topology/RCA/ownership/memory/report/approval references;
add structural tests that reject unscoped domain queries.

### PH-3F — Browser + CLI Tenant Context

Add authorized tenant discovery/selection, central frontend client propagation,
state clearing on switch, CLI profile/`--tenant`, and bounded customer UX. Do
not redesign the incident cockpit.

### PH-3G — Adversarial PostgreSQL Acceptance + PH-3 Closure

Run the two-tenant corpus on real PostgreSQL, route/IDOR/security tests,
concurrency/idempotency checks, migration/backfill acceptance, frozen-custody
checks, frontend/CLI/agent/evaluation regressions, and publish the PH-3 closure
contract.

## 25. Stop conditions / architecture blockers

PH-3 implementation must stop for architecture review if:

- it needs to reinterpret `AuthPrincipal` as tenant ownership;
- stable V1 subject identity cannot be governed before OIDC;
- any agent/provider path accepts caller-selected tenant;
- a domain table cannot be backfilled without guessing ownership;
- deterministic ID namespacing would rewrite historical TC-1 truth;
- a worker cannot carry or derive an explicit tenant;
- a cross-tenant reference cannot be rejected atomically;
- frozen evaluation or accepted migration custody would change; or
- any route/table/query/ID builder becomes ambiguous.

None of these is unresolved at PH-3A. The outer tenant namespace, direct tenant
columns, fixed machine bindings, explicit legacy tenant, and preserved source-
native snapshot identity provide a defensible implementation path. Therefore
there is no architecture blocker.

## 26. Explicit deferred work

PH-3A does not implement tenant, membership, binding, API, repository, schema,
migration, frontend, CLI, agent, provider, cloud, evaluation, cache, file-store,
or worker changes. It does not define final owner/admin/editor/viewer roles,
service endpoint permissions, installation support impersonation, cross-tenant
search, cross-customer analytics, tenant billing/plans/trials, deletion and
retention, secret custody, backup/restore, deployment lifecycle, or broad
observability/concurrency.

Those remain respectively in later PH-3 implementation and PH-4 through
PH-11. PH-7 owns deletion/retention. PH-5 owns permissions inside a tenant.
Aggregated/anonymized product analytics requires a separate privacy/product
decision. No customer-readiness claim is made.

## 27. PH-3A final verdict

**PASS.** Every current ORM table and production route is classified; machine
tenant derivation, human membership/selection, fixed service binding, canonical
identity scope, deterministic collision handling, repository/query impact,
constraints/indexes, lifecycle/history/LLM/report isolation, IDOR semantics,
adversarial testing, legacy backfill, and frozen custody have a concrete V1
contract. Ambiguous tables, routes, repositories, and builder families: zero.

Current TopoAI remains **not tenant-safe** until the implementation and
adversarial acceptance blocks close. PH-2 remains valid. The exact next block
is **PH-3B — Tenant Foundation + Membership + Request Tenant Context**.
