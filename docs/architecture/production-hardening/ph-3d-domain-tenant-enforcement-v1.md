# PH-3D — Domain tenant enforcement v1

Verdict: **PASS for PH-3D scope; ready for architect review.** No architecture,
security, or custody blocker remains in this scope. PH-3E/PH-3F remain open.

## Scope and review boundary

Application-level domain read/write isolation, explicit repository predicates,
request/background tenant propagation, minimal consumer compatibility, and
safe physical ownership closure. This is not PH-3E or PH-3F and is not a claim
that TopoAI is fully multi-tenant safe.

- Accepted parent: `c74d286a16defce69343d1670698355c2dc9fa4a`
  (`c74d286 feat(persistence): add domain tenant ownership metadata (#75)`).
- Branch: `security/ph-3d-domain-tenant-enforcement-v1`.
- Initial worktree was clean. No stage, commit, push, merge, rebase, tag,
  branch switch, history rewrite, or PR operation was performed.
- Applied the architect's MACHINE_AUTHORITY_DEFERRED amendment. Historical
  116 human domain routes means **104 enforced + 12 explicitly deferred**,
  not 116 falsely tenant-protected routes. Ambiguous classifications: **0**.
- PH-3A, PH-3B, PH-3C, PH-2F acceptance documents and their actual repository,
  service, authentication, persistence, consumer, and test implementations were
  inspected. Earlier architecture documents remain historical, not rewritten.

## Security contract

```text
PH-2 authentication
  -> PH-3B TenantContext (human membership / fixed service binding)
  -> existing action authorization
  -> explicit tenant_id passed to service and repository
  -> SQL tenant predicate before selection / aggregation / pagination
  -> explicit write ownership and same-tenant parent validation
```

`AuthPrincipal` is unchanged. There is no global ORM filter, session tenant,
contextvar authority, default tenant, first-tenant selection, or post-query
customer filtering. Tenant-owned repository arguments are required keyword-only
`tenant_id`, never `None` defaults. `tenant_scope.tenant_predicate` composes
explicit SQL; `tenant_get` selects by both tenant and primary key rather than
trusting SQLAlchemy's identity map.

Human requests require `X-Topo-Tenant-ID`. Missing/invalid shape gives
`400 TENANT_CONTEXT_REQUIRED`. Unknown, disabled, or unauthorized tenant gives
`403 TENANT_ACCESS_DENIED`. An administrator still needs membership. Revoking
membership or disabling a tenant removes domain access without invalidating
the user's authentication identity. Domain objects belonging elsewhere behave
as absent: `404`, including update/delete/child-parent operations.

Service API credentials use the existing fixed server-side PH-3B binding.
No header is needed; a conflicting header is denied. An unbound legacy service
still authenticates to `whoami` but cannot access a tenant domain route.

The request session now comes from `request.app.state.session_factory`, also
used by the existing authentication service. This prevents authentication and
domain dependencies from accidentally using different databases in an injected
application. No authentication policy or credential format changed.

### Writes and references

New records are owned from validated context, not request JSON. Existing strict
request schemas continue rejecting extraneous ownership fields (tested for
ownership mapping creation). Transient internal ORM records receive explicit
ownership; persistent records cannot be reassigned, and detached records are
rejected. Global primary-key/unique conflicts still fail rather than becoming
an unscoped upsert. Collision availability remains a PH-3F limitation.

`tenant_commit`/`tenant_flush` explicitly validate the unit of work before
persisting it. They are called by scoped writers, not installed as hidden ORM
hooks. Same-tenant parent validation covers:

- identity resolution -> snapshot;
- signal payload -> topology snapshot;
- change -> before/after snapshots; change event -> originating change;
- entity link -> event/snapshot;
- incident -> primary/latest signal, pinned topology, analysis, recommendation,
  recovery verification;
- analysis -> signal/topology; causal analysis -> incident and payload topology;
- explanation -> incident/topology/analysis;
- copilot session/message -> incident/session;
- investigation plan/step -> incident/plan;
- report/action -> incident/report; outcome -> incident/causal analysis;
- recommendation -> analysis/signal/change; recovery -> recommendation,
  analysis/signal and before/after snapshots;
- approval/event and dormant execution/event -> incident/approval/execution;
- webhook delivery -> endpoint; dead letter -> delivery;
- runtime dependency/process -> sensor.

`tenant_get` disables autoflush during lookup so adding a child followed by a
parent lookup cannot flush the child before validation, even with an injected
`autoflush=True` session. Pending change-link reuse also checks tenant ownership.
Source-native entity IDs, provider IDs, evidence IDs, and action IDs are not
mistaken for foreign keys to unrelated tables. Deeper polymorphic JSON/world-model
reference acceptance belongs to PH-3F; no canonical identity was rewritten.

## Repository inventory and operation closure

The historical **25 modules / 131 public session-backed methods** still reconcile.
Eleven methods in `agent_repository` and six machine-root methods in mixed
repositories are outside PH-3D tenant binding. Therefore **114 public methods**
plus **12 session-backed internal helpers** = **126 scoped methods in 24 modules**.
The explicit session-backed audit including machine methods is **143 methods**.
Pure serializers and non-session record builders are additional helpers, not
inflated into these counts.

All rows below are under `backend/app/repositories/`. Public method names are
preserved from PH-3A's exact inventory; this table records current conversion,
internal helpers, and exceptions. `test_domain_tenant_inventory.repository_inventory`
enumerates the current names directly from source.

| Module | Public scoped | Internal scoped | Deferred public |
|---|---:|---:|---:|
| action_approval_repository | 7 | 0 | 0 |
| agent_repository | 0 | 0 | 11 |
| build_artifact_evidence_repository | 3 | 0 | 0 |
| causal_analysis_repository | 3 | 0 | 0 |
| change_event_repository | 5 | 2 | 0 |
| change_repository | 4 | 0 | 0 |
| change_source_repository | 2 | 0 | 5 |
| cloud_repository | 4 | 0 | 1 |
| copilot_repository | 6 | 2 | 0 |
| execution_intent_repository | 12 | 1 | 0 |
| identity_repository | 5 | 0 | 0 |
| incident_explanation_repository | 4 | 0 | 0 |
| incident_outcome_repository | 4 | 0 | 0 |
| incident_record_repository | 7 | 0 | 0 |
| incident_repository | 3 | 0 | 0 |
| investigation_plan_repository | 4 | 2 | 0 |
| ownership_repository | 5 | 0 | 0 |
| post_incident_report_repository | 6 | 2 | 0 |
| recommendation_repository | 4 | 0 | 0 |
| recovery_repository | 3 | 0 | 0 |
| runtime_observability_repository | 4 | 3 | 0 |
| signal_repository | 5 | 0 | 0 |
| snapshot_repository | 4 | 0 | 0 |
| topology_snapshot_repository | 1 | 0 | 0 |
| webhook_repository | 9 | 0 | 0 |
| **Total** | **114** | **12** | **17** |

Internal session helpers: change events `_upsert_link`, `_links`; copilot
`_message_count`, `_session_to_summary`; execution `_atomic_transition`;
investigation `_load_step_records`, `_plan_to_summary`; reports
`_load_action_records`, `_report_to_summary`; runtime `_touch_sensor`,
`_upsert_dependency`, `_upsert_process`.

Operation classification is explicit, retaining existing filters and order:

- READ_ONE: load/get-by-ID methods and record-to-view loaders use scoped lookup.
- READ_MANY: list methods and child collections constrain the tenant in SQL.
- CREATE/BULK: save/create/ingest/persist methods own every inserted row and
  validate references. Existing save/upsert methods also perform UPDATE.
- UPDATE/DELETE: status transitions, overrides, report/action changes and
  webhook changes first use scoped lookup; atomic execution UPDATE includes the
  tenant in its authoritative SQL predicate. Soft-deactivation remains existing
  delete semantics.
- COUNT: copilot `_message_count` and max/sequence aggregates in approvals,
  execution, investigation and reports are scoped before aggregation.
- SEARCH/CORRELATION: active ownership matching, change windows, image-digest
  evidence lookup, event fingerprints, delivery keys, signal fingerprints and
  active incident correlation constrain tenant before matching.
- LATEST: causal analysis, explanation, outcome/history, report, cloud topology,
  snapshots/checkpoints and lifecycle status select latest only within tenant.
- INTERNAL_HELPER: the twelve named session helpers require the same explicit
  argument; pure serializers do not independently fetch foreign records.

No PH-3D tenant-owned unscoped repository operation remains. The six mixed-module
exceptions are `cloud_repository.agent_cloud_status` and change-source
`create_change_source`, `load_change_source`, `get_change_source`,
`list_change_sources`, `update_change_source`. Agent repository methods remain
PH-3E machine authority, not hidden tenant bypasses.

### Direct ORM, raw SQL, cache and background inventory

The historical 20 functions across 11 services were re-audited. Nineteen accept
explicit tenant authority; the verified provider-ingestion entry point is
machine-deferred. No ambiguous function remains.

| Service | Audited functions | Classification |
|---|---|---|
| causal_rca | `_snapshot_for_incident`, `analyze_causal_rca` | TENANT_SCOPED_NOW |
| change_source_ingest | `_existing_delivery`, `replay_dead_letter` | TENANT_SCOPED_NOW for domain rows |
| change_source_ingest | `ingest_change_source_webhook` | MACHINE_DEFERRED |
| continuous_lifecycle | `reconcile_pending_incidents_for_checkpoint` | TENANT_SCOPED_NOW |
| incident_change_analysis | `_snapshot_for_incident`, `_candidate_for_record`, `analyze_incident_change_events` | TENANT_SCOPED_NOW |
| incident_explanation | `_load_optional_record` | TENANT_SCOPED_NOW |
| incident_lifecycle | `upsert_incident_from_orchestration` | TENANT_SCOPED_NOW |
| lifecycle_status | `_latest`, `build_lifecycle_status`, `build_incident_lifecycle_status` | TENANT_SCOPED_NOW |
| lineage_candidate_admission | `_source_event`, `evaluate_lineage_candidate_admission` | TENANT_SCOPED_NOW |
| runtime_snapshot_enrichment | `enrich_snapshot_with_runtime_dependencies` | TENANT_SCOPED_NOW |
| temporal_semantics | `safe_snapshot_record_at_or_before`, `incident_operational_time` | TENANT_SCOPED_NOW |
| topology_checkpoint | `latest_checkpoint_record` | TENANT_SCOPED_NOW |

Provider source configuration access remains a machine-authority dependency.
Dead-letter replay first proves ownership of its durable dead-letter and
delivery roots, then reuses their server-recorded source reference. It does not
accept a caller-selected source as tenant authority. Shared source configuration
and its health counters are not claimed tenant-isolated before PH-3E.

Direct SQLAlchemy domain SELECT/UPDATE chains are structurally audited for a
tenant predicate, not merely a signature. Domain `Session.get` calls are banned
by tests. No tenant-sensitive literal/raw SQL was introduced in product queries.
Migration/preflight/schema management and disposable evaluation audit SQL are
explicit installation/operator boundaries, not customer data APIs. Agent token
conditional SQL remains PH-2/PH-3E. Authentication and tenant-control ORM access
retain their existing separate authority.

Background work receives `tenant_id + object_id`, including checkpoint -> signal
-> correlation -> incident -> automatic causal analysis, pending reconciliation,
webhook publication and derived briefing/history/outcome/report work. It does
not load a global object first and infer tenancy. Unowned machine entry points
pass the explicit quarantine sentinel, never a guessed customer tenant.

Backend blast-radius caches are invocation-local. Explanation cache is durable
and now looked up within tenant. No cross-request customer cache was added.
Reports remain response exports, not shared filesystem artifacts. Explanation
record serialization excludes ORM `tenant_id` from evidence/narrative inputs.

## Route acceptance and exact PH-3E deferral

Actual application: **143 method/path pairs**.

| Classification | Count |
|---|---:|
| PH3D_TENANT_REQUIRED | 104 |
| MACHINE_AUTHORITY_DEFERRED | 12 |
| MACHINE_DEFERRED (8 agent, 1 provider callback) | 9 |
| TENANT_CONTROL | 7 |
| SECURITY_GLOBAL | 9 |
| PUBLIC | 2 |
| AMBIGUOUS / UNKNOWN | 0 |

`tenant_routing.py` classifies routes and tests inspect the actual FastAPI
dependency graph. New human product routes default to tenant-required, not
silent deferral. Public health/readiness, authentication/session/credential
endpoints, tenant bootstrap/control, `whoami`, and static topology sample do not
gain inappropriate domain tenancy requirements.

**All 12 deferred human-facing routes, and no others:**

| Method | Path | Authoritative PH-3E table |
|---|---|---|
| POST | `/api/v1/agents/enrollment-tokens` | agent_enrollment_tokens |
| GET | `/api/v1/agents` | topo_agents |
| GET | `/api/v1/agents/{agent_id}` | topo_agents |
| GET | `/api/v1/agents/{agent_id}/health` | topo_agents |
| POST | `/api/v1/agents/{agent_id}/revoke` | topo_agents |
| GET | `/api/v1/agents/{agent_id}/plugins` | topo_agents |
| GET | `/api/v1/agents/{agent_id}/cloud-status` | topo_agents |
| POST | `/api/v1/change-sources` | change_sources |
| GET | `/api/v1/change-sources` | change_sources |
| GET | `/api/v1/change-sources/{source_id}` | change_sources |
| PATCH | `/api/v1/change-sources/{source_id}` | change_sources |
| GET | `/api/v1/change-sources/{source_id}/doctor` | change_sources |

Every route remains PH-2 authenticated; anonymous requests are tested as 401.
None gains cosmetic TenantContext enforcement or a tenant-isolation claim.
PH-3E must persist server-authoritative ownership on enrollment credentials,
propagate that to enrolled/steady-state agents, and bind provider source
configuration before scoping these queries. Supplied headers/payloads cannot
assign machine ownership.

Ordinary incidents, topology, runtime/cloud inventory, changes/evidence, source
deliveries/dead letters, ownership, analyses, history, reports, outcomes and
dormant approval/execution domain routes remain enforced. They were not deferred
merely because their data might originate from a machine.

## Writer inventory and NULL ownership closure

**43 ORM tables remain.** Of 35 PH3C_DOMAIN tables:

- HUMAN_SERVICE_COMPLETE: **19**.
- BACKGROUND_COMPLETE as a separate all-writers table classification: **0**.
  The existing root-owned derived services for these nineteen are invoked in
  human/service workflows, not a separate independent job authority. Converted
  lifecycle/background paths also write the mixed-origin tables below.
- MACHINE_DEPENDENT: **16**.
- AMBIGUOUS: **0**.

**19 physically NOT NULL + 16 residual nullable = 35.** All converted
human/service and tenant-root background writers assign ownership even when
their target column remains nullable for an unbound machine writer.

### Exact NOT NULL set (HUMAN_SERVICE_COMPLETE)

| Table | Authoritative writer/root |
|---|---|
| identity_resolutions | identities resolve request + owned snapshot |
| identity_overrides | identities override request |
| incident_analyses | incident analysis/orchestration request + owned signal/snapshot |
| remediation_recommendations | recommendation/orchestration + owned analysis |
| recovery_verifications | recovery request + owned recommendation/analysis/snapshots |
| ownership_mappings | ownership mapping request |
| webhook_endpoints | webhook management request |
| incident_explanations | explanation service + owned incident |
| incident_copilot_sessions | copilot service + owned incident |
| incident_copilot_messages | copilot service + owned session/incident |
| incident_investigation_plans | investigation service + owned incident |
| incident_investigation_steps | investigation service + owned plan/incident |
| post_incident_reports | report service + owned incident |
| post_incident_report_actions | report service + owned report/incident |
| incident_outcomes | outcome service + owned incident/causal analysis |
| action_approvals | approval service + owned incident (existing dormant foundation) |
| action_approval_events | approval service + owned approval/incident |
| execution_intents | transaction foundation + owned approval/incident; no executor added |
| execution_intent_events | transaction foundation + owned intent/approval/incident |

### Exact nullable MACHINE_DEPENDENT set and writers

| Table | Machine-origin NULL writer chain remaining for PH-3E |
|---|---|
| topology_snapshots | agents.submit_snapshot -> agent_snapshot_ingest.persist_agent_snapshot -> persist_topology_checkpoint/save_snapshot |
| changes | agent snapshot -> checkpoint diff -> save_changes |
| signals | agents.submit_failure_signals or snapshot failure detection -> ingest_failure_signal_batch/save_signals |
| incidents | machine failure -> continuous_lifecycle -> upsert_incident_from_orchestration |
| causal_analyses | machine incident -> continuous_lifecycle._complete_automatic_analysis -> analyze_causal_rca/save_causal_analysis |
| build_artifact_evidence | provider webhook/agent event -> GitHub Actions lineage -> save_build_artifact_evidence |
| change_events | agent submit_change_events or ingest_change_source_webhook -> ingest_change_event |
| change_entity_links | agent/provider event or checkpoint correlation -> correlate_change_event/_upsert_link |
| change_source_deliveries | verified ingest_change_source_webhook |
| change_source_dead_letters | verified ingest_change_source_webhook error handling |
| cloud_accounts | agent_snapshot_ingest -> persist_cloud_inventory |
| cloud_resources | agent_snapshot_ingest -> persist_cloud_inventory |
| runtime_sensors | agent runtime_sensor_heartbeat/runtime_event_batch -> record_sensor_heartbeat/_touch_sensor |
| runtime_dependencies | agent runtime_event_batch -> ingest_runtime_event_batch/_upsert_dependency |
| runtime_processes | agent runtime_event_batch -> ingest_runtime_event_batch/_upsert_process |
| webhook_deliveries | machine lifecycle -> publish_event_safely -> save_delivery_result |

These exact ingress boundaries use `UNOWNED_MACHINE`, an internal enum sentinel,
not a tenant ID or public field. It selects `tenant_id IS NULL` only for deferred
machine work. Human/service contexts are validated strings and select
`tenant_id = T`, so unowned rows are invisible. No client can choose the sentinel.

Outbound endpoint lookup also scopes tenant before external delivery; unowned
machine work cannot enumerate tenant-owned endpoints. Until PH-3E binding,
machine-origin customer notification routing and visibility are intentionally
limited rather than assigned an invented tenant. Ordinary domain API ownership
is still enforced independently.

## Migration 0006

- File: `backend/alembic/versions/0006_domain_tenant_enforcement.py`.
- Revision: `0006_domain_tenant_enforcement`.
- Down revision: `0005_domain_tenant_ownership`.
- Exactly one head, at 0006; no 0007 and no new table.
- Complete preflight of all nineteen candidate columns before any ALTER.
- Any NULL fails deterministically with
  `TENANT_OWNERSHIP_NULL_ROWS_PRESENT: table=count,...`; no customer row content.
- No guessed assignment, legacy/transitional tenant, x-argument backfill,
  trigger, default, server default, canonical ID rewrite or uniqueness removal.
- Failure remains stamped at 0005; tests verify all candidate columns remain
  nullable after failed preflight, for each table on SQLite and PostgreSQL.
- SQLite batch ALTER and PostgreSQL DDL match current ORM metadata exactly.
- Disposable downgrade restores nullability without reassigning data; re-upgrade
  is tested. Production rollback remains the existing backup/forward-fix policy.
- Production schema authority rejects 0005 for this application. No automatic
  production upgrade is introduced. Local/disposable SQLite initialization
  retains its existing metadata-create behavior; existing databases still need
  the deliberate migration workflow.

Protected developer/frozen databases were not migrated. Operators must establish
real ownership of any new NULL rows in the nineteen closed tables before 0006;
the migration will not choose ownership for them.

## Consumer compatibility

Frontend authenticates first, then calls the real tenant-list API. Zero tenants
gets bounded onboarding/no-access guidance; one may be selected client-side;
multiple require an explicit choice. Selection is non-secret memory only. The
central same-origin client injects the selected tenant header and ignores
call-site overrides. The backend revalidates every request.

Switching remounts the full tenant-owned subtree, including sidebar/page state;
late successful responses for another selection are discarded. Tenant-denied
responses have their own bounded state, not blanket logout. Late denials from
the old tenant cannot clear a newer selection. Existing CSRF/cookie/401 semantics
and prohibition on browser secret storage remain unchanged.

Report export now uses the same authenticated, tenant-header transport before
creating a local blob download. Direct API anchors could not carry the required
header. No credential or tenant authorization is added to a query string.

CLI adds `--tenant` with an optional explicit non-secret profile preference.
Resolution copies that preference; the flag overrides it. It never selects the
first server tenant. Missing tenant receives bounded guidance. Authentication
credentials remain in the existing keyring/environment mechanism; 401/403 exits
and server fixed service binding remain authoritative.

Evaluation's disposable backend uses required auth -> named human credential ->
real tenant creation with atomic creator membership -> transport tenant header.
A real local-backend test exercises that sequence without starting an agent,
Kubernetes, or provider. Random tenant IDs stay in transport/persistence, not
scenario semantic IDs or frozen evidence. Legacy evaluation DBs are copied
before controlled preparation through existing 0005 ownership backfill and 0006;
the frozen seed stays byte-identical. Live machine-origin evaluations cannot
assume customer visibility before PH-3E; the harness does not fake agent binding.

## Identity and PH-3F handoff

No TC-1 identifiers, causal scores, candidate windows, support/projection rules,
confidence semantics, historical topology rules, or primary-key builders changed.
The 28 PH-3A builder families remain: **1 safe digest-computation family, 27
PH3F_IDENTITY_REQUIRED, 0 ambiguous**. The twenty-seven have tenant-scoped domain
queries now but are not declared collision/world-model closed. For persisted
keys this is QUERY_ISOLATED_BUT_STORAGE_COLLISION_REMAINS; source-native graph
IDs remain scoped by their proven snapshot rather than rewritten.

Exact PH-3F families (numbers preserve PH-3A):

1. Kubernetes canonical identity.
2. AWS canonical identity.
3. Azure canonical identity.
4. GCP canonical identity.
5. Git repository canonical identity.
6. Git commit canonical identity.
7. CI build / GitHub workflow-run identity.
8. Container-image canonical identity.
9. Kubernetes collector cluster/entity/relationship IDs.
10. Agent cloud/Azure/GCP entity/parent IDs.
11. Agent snapshot/runtime entity/relationship IDs.
12. GitHub repository/commit/Actions graph and evidence IDs.
13. Container-image graph IDs.
14. Network topology IDs.
15. Identity resolution/override IDs.
16. Kubernetes event fingerprint/signal IDs.
17. Normalized change fingerprint/change IDs.
18. Durable change-event fingerprint/event/link IDs (PH-3C tenant-aware link
    uniqueness is retained; the family is not fully closed).
19. Change-source ID, delivery ID/key.
20. Cloud-resource storage IDs.
21. Runtime dependency/process IDs and sensor business keys.
22. Incident fingerprint/incident/orchestration IDs.
23. Incident/causal analysis, hypothesis/evidence/stable IDs.
24. Recommendation/response/recovery/predeployment IDs.
25. Explanation/investigation/report/outcome/memory IDs and hashes.
26. Ownership mapping fingerprints.
27. Approval pending/evidence, execution idempotency, webhook event/delivery keys.

Family 28 (secret/content digests) remains safe for digest computation only;
tenant-owned deduplication still needs the scoped repository. Families 9–12,
16 and 19–21 also have PH-3E machine-entry dependencies. Native-provider identity
does not confer tenant authority. PH-3F must reconcile storage collisions,
polymorphic causal/JSON references, cache/materialized lookup namespaces, and
adversarial full-world-model isolation. Existing global constraints are intact.

## Verification record

Final results and custody are recorded below. Tests use
explicit per-module tenant fixtures, not a universal autouse tenant or resolver
bypass. Two-tenant API tests exercise real authentication, membership and service
binding against both SQLite and PostgreSQL.

New permanent backend coverage:

- `test_domain_tenant_enforcement.py`: route dependency accounting; all twelve
  deferred administration routes still authenticate; all 35 domain row types
  enforce scoped ID lookup; incident IDOR/list/update; admin membership;
  fixed/unbound service authority; human ownership assignment/body spoof rejection;
  foreign child-parent rejection; snapshot/change/impact/outcome/report/delete
  IDOR; latest/pagination/NULL quarantine; real automatic checkpoint/signal/
  incident/causal persistence and tenant-local correlation; revoked/disabled
  access; JSON snapshot references and autoflush child validation.
- `test_domain_tenant_closure.py`: 35-table writer/ORM/no-default inventory;
  SQLite/PostgreSQL fresh/current upgrade, schema-behind, downgrade/re-upgrade,
  parity; per-table NULL preflight, no guessing/backfill or failed stamp.
- `test_domain_tenant_inventory.py`: required repository authority, no direct
  owned Session.get, no public/default quarantine authority, explicit SQL
  predicates on domain SELECT/UPDATE/DELETE expressions.
- `domain_tenant_fixtures.py`: opt-in real tenant/member fixture and disposable
  35-table total/NULL audit; no product audit API.

Regression fixtures establish their actual parents and tenant context; original
behavior assertions remain. Schema-head assertions now expect 0006. The causal
file hash guard retains the immutable accepted blob and compares the complete
AST after removing only authorized tenant plumbing; scoring/evidence behavior
is not whitelisted away. Other protected product hash guards are unchanged.

The complete PostgreSQL-enabled run also exposed an existing test-order leak:
`test_agent_enrollment_postgres` invoked Alembic's CLI logging configuration
inside pytest, disabling the app logger and suppressing the subsequent PH-2B
development-mode warning assertion. Its fixture now loads the same INI migration
options without installing CLI logging handlers. The real database migrations,
enrollment assertions, and authentication warning assertion remain unchanged;
the previously failing six-test sequence passes. No product logging or auth
policy was changed to make this test pass.

Frontend adds central header selection, stale success/denial, remount/gate, and
tenant-scoped report download tests. CLI adds header/profile/flag precedence and
bounded missing-context guidance. Evaluation adds transport tenancy and a real
local runtime bootstrap test; no infrastructure experiment was rerun.

| Gate | Final result |
|---|---|
| Backend compile | PASS: `python -m compileall app` |
| Full backend pytest (default/SQLite) | 1,183 passed, 89 PostgreSQL-gated skipped; 312.11s |
| Real PostgreSQL 16 closure + isolation + runtime regression | 144 passed; 296.30s |
| Full backend pytest with PostgreSQL enabled | 1,271 passed, 1 container-gated backup/restore skipped; 485.78s. That exact skipped test passed separately below. |
| PostgreSQL backup/restore (container-enabled) | 1 passed; 4.93s |
| Full evaluation | 917 passed, 3 existing Windows symlink-privilege skips; 101.97s |
| Agent compile / tests | PASS / 15 passed; 4.39s |
| CLI compile / tests | PASS / 70 passed; 3.60s |
| Frontend typecheck / tests / lint / build | PASS / 83 passed / 0 errors, 11 pre-existing warnings / PASS |
| Secret-scanner tests / tracked-tree scan / new deliverable scan | 8 passed / PASS / PASS |
| git diff --check | PASS, no whitespace errors |

PostgreSQL uses only the task-created loopback-bound, tmpfs-backed disposable
`postgres:16` container `topo-ph3d-20260830`, with no named persistent volume.
No development or frozen database is used as a test target. Test output is not
retained as a customer-data artifact; temporary refactor drivers and JUnit
scratch reports are removed after result consolidation.

Cleanup completed: the exact verified `topo-ph3d-20260830` container was stopped
and auto-removed, including its disposable databases; no named volume existed.
Three temporary refactor drivers and six scratch JUnit reports were removed.
No protected database or other container was removed.

The three evaluation skips are the existing symlink containment tests:
`test_symlink_inside_result_root_fails_safely`,
`test_symlink_cannot_escape_result_root`, and
`test_symlink_result_root_is_rejected`. Windows returned error 1314 (symlink
creation privilege unavailable). No assertion or skip condition was weakened.
The backend warning is the existing Starlette/httpx deprecation notice.
Frontend lint has zero errors and eleven existing warnings in untouched files;
the production build, including its existing font fetch, completed successfully.

## Custody

All seven SHA-256 hashes below were remeasured after implementation and match
their before values exactly. Existing migrations changed: **none**. Developer
DB unchanged: **yes**. Frozen LINEAGE DB unchanged: **yes**.

| Artifact | SHA-256 before = after |
|---|---|
| 0001_current_schema_baseline.py | B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6 |
| 0002_auth_sessions.py | 4EB2930BFF89944DA5E9EA24F33B80F170D0F82E40F0AB508A07B2DC6B624460 |
| 0003_auth_api_credentials.py | EAE6BA5CF16A4E68161A710EDFA29172E20C9DBD6F8739ACA981C4A8D4DFAC73 |
| 0004_tenant_foundation.py | CBCB14FF6C8D70C1A4F4039E5436D039C599EBC842BE8DB333D6CA4ED66A9A05 |
| 0005_domain_tenant_ownership.py | B60A69B26FB9A1D01DAE0107439BEC5A1C02F95FCABC0E0044F4E7F30F229E4C |
| backend/data/topo.db | 0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E |
| evaluation/results/lineage/post-sc4/topo-product-32695735269.db | 9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F |

## File manifest and Git state

143 tracked files modified and 10 new files. All changes are unstaged. The
literal status list below also supplies the exact modified-path inventory
(`git diff --name-only` is the set of `M` paths). New `??` files do not appear
in ordinary `git diff --stat` until staged; no staging was performed.

```text
 M backend/app/api/action_approvals.py
 M backend/app/api/agents.py
 M backend/app/api/automation.py
 M backend/app/api/blast_radius.py
 M backend/app/api/causal_rca.py
 M backend/app/api/change_events.py
 M backend/app/api/change_sources.py
 M backend/app/api/changes.py
 M backend/app/api/clouds.py
 M backend/app/api/execution_intents.py
 M backend/app/api/execution_readiness.py
 M backend/app/api/github.py
 M backend/app/api/identities.py
 M backend/app/api/incident_briefing.py
 M backend/app/api/incident_context.py
 M backend/app/api/incident_copilot.py
 M backend/app/api/incident_explanations.py
 M backend/app/api/incident_memory.py
 M backend/app/api/incident_outcome.py
 M backend/app/api/incident_records.py
 M backend/app/api/incidents.py
 M backend/app/api/investigation_plans.py
 M backend/app/api/kubernetes.py
 M backend/app/api/network_dependencies.py
 M backend/app/api/orchestration.py
 M backend/app/api/ownership.py
 M backend/app/api/post_incident_reports.py
 M backend/app/api/predeployment.py
 M backend/app/api/recommendations.py
 M backend/app/api/recovery.py
 M backend/app/api/response_intelligence.py
 M backend/app/api/response_plan.py
 M backend/app/api/signals.py
 M backend/app/api/snapshots.py
 M backend/app/api/topology.py
 M backend/app/api/webhooks.py
 M backend/app/db/database.py
 M backend/app/db/models.py
 M backend/app/main.py
 M backend/app/repositories/action_approval_repository.py
 M backend/app/repositories/build_artifact_evidence_repository.py
 M backend/app/repositories/causal_analysis_repository.py
 M backend/app/repositories/change_event_repository.py
 M backend/app/repositories/change_repository.py
 M backend/app/repositories/change_source_repository.py
 M backend/app/repositories/cloud_repository.py
 M backend/app/repositories/copilot_repository.py
 M backend/app/repositories/execution_intent_repository.py
 M backend/app/repositories/identity_repository.py
 M backend/app/repositories/incident_explanation_repository.py
 M backend/app/repositories/incident_outcome_repository.py
 M backend/app/repositories/incident_record_repository.py
 M backend/app/repositories/incident_repository.py
 M backend/app/repositories/investigation_plan_repository.py
 M backend/app/repositories/ownership_repository.py
 M backend/app/repositories/post_incident_report_repository.py
 M backend/app/repositories/recommendation_repository.py
 M backend/app/repositories/recovery_repository.py
 M backend/app/repositories/runtime_observability_repository.py
 M backend/app/repositories/signal_repository.py
 M backend/app/repositories/snapshot_repository.py
 M backend/app/repositories/topology_snapshot_repository.py
 M backend/app/repositories/webhook_repository.py
 M backend/app/security/tenant_context.py
 M backend/app/services/action_approval.py
 M backend/app/services/agent_snapshot_ingest.py
 M backend/app/services/blast_radius.py
 M backend/app/services/business_impact.py
 M backend/app/services/causal_rca.py
 M backend/app/services/change_event_bridge.py
 M backend/app/services/change_source_ingest.py
 M backend/app/services/continuous_lifecycle.py
 M backend/app/services/execution_readiness.py
 M backend/app/services/execution_transaction.py
 M backend/app/services/github_actions_artifact_lineage.py
 M backend/app/services/incident_briefing.py
 M backend/app/services/incident_change_analysis.py
 M backend/app/services/incident_context.py
 M backend/app/services/incident_copilot.py
 M backend/app/services/incident_explanation.py
 M backend/app/services/incident_lifecycle.py
 M backend/app/services/incident_memory.py
 M backend/app/services/incident_orchestrator.py
 M backend/app/services/incident_outcome.py
 M backend/app/services/incident_similarity.py
 M backend/app/services/investigation_planner.py
 M backend/app/services/lifecycle_status.py
 M backend/app/services/lineage_candidate_admission.py
 M backend/app/services/network_dependency_analysis.py
 M backend/app/services/ownership_resolver.py
 M backend/app/services/post_incident_report.py
 M backend/app/services/predeployment_impact.py
 M backend/app/services/response_intelligence.py
 M backend/app/services/response_plan.py
 M backend/app/services/runtime_snapshot_enrichment.py
 M backend/app/services/temporal_semantics.py
 M backend/app/services/topology_checkpoint.py
 M backend/app/services/webhook_delivery.py
 M backend/tests/test_action_approval.py
 M backend/tests/test_agent_enrollment_postgres.py
 M backend/tests/test_blast_impact_policy.py
 M backend/tests/test_canonical_identity.py
 M backend/tests/test_causal_candidate_policy.py
 M backend/tests/test_causal_evaluation_budget.py
 M backend/tests/test_causal_evidence_ledger.py
 M backend/tests/test_causal_hypothesis_projection.py
 M backend/tests/test_causal_relevance_policy.py
 M backend/tests/test_change_event_link_idempotency.py
 M backend/tests/test_continuous_lifecycle.py
 M backend/tests/test_domain_tenant_migration.py
 M backend/tests/test_execution_readiness.py
 M backend/tests/test_execution_transaction.py
 M backend/tests/test_github_actions_build_lineage.py
 M backend/tests/test_identity_transition_diff.py
 M backend/tests/test_incident_briefing.py
 M backend/tests/test_incident_context.py
 M backend/tests/test_incident_memory.py
 M backend/tests/test_incident_outcome.py
 M backend/tests/test_lineage_candidate_admission.py
 M backend/tests/test_lineage_causal_relevance.py
 M backend/tests/test_postgres_runtime_compatibility.py
 M backend/tests/test_relationship_provenance.py
 M backend/tests/test_response_intelligence.py
 M backend/tests/test_response_plan.py
 M backend/tests/test_sc3_container_image_identity.py
 M backend/tests/test_schema_migrations.py
 M backend/tests/test_source_file_mutations.py
 M backend/tests/test_temporal_semantics.py
 M cli/src/topo_cli/client.py
 M cli/src/topo_cli/config.py
 M cli/src/topo_cli/main.py
 M cli/tests/test_client_auth.py
 M cli/tests/test_config.py
 M evaluation/lineage_broken_run_image.py
 M evaluation/lineage_distractor_robustness.py
 M evaluation/runner.py
 M evaluation/tests/test_lineage_distractor_robustness.py
 M evaluation/tests/test_required_authentication.py
 M evaluation/topo_client.py
 M frontend/components/app/incident-post-incident-report.tsx
 M frontend/components/auth/auth-boundary.tsx
 M frontend/lib/topo-api.ts
 M frontend/test/auth-session.test.mjs
?? backend/alembic/versions/0006_domain_tenant_enforcement.py
?? backend/app/db/domain_ownership.py
?? backend/app/repositories/tenant_scope.py
?? backend/app/security/tenant_routing.py
?? backend/tests/domain_tenant_fixtures.py
?? backend/tests/test_domain_tenant_closure.py
?? backend/tests/test_domain_tenant_enforcement.py
?? backend/tests/test_domain_tenant_inventory.py
?? docs/architecture/production-hardening/ph-3d-domain-tenant-enforcement-v1.md
?? frontend/components/auth/tenant-boundary.tsx
```

Tracked diff summary after formatting-only cleanup: `143 files changed,
4484 insertions(+), 4625 deletions(-)`. Temporary refactor drivers are removed;
they are not deliverables. No agent directory, provider connector, immutable
migration 0001–0005, or protected database file is in the modified-path list.

## Compatibility and handoff

- Missing tenant selection is now deliberately rejected for the 104 product
  routes. Frontend/CLI/evaluation were adapted centrally; third-party human API
  callers must send their selected tenant. Fixed-bound services need no selector.
- NULL machine rows are quarantined, not silently assigned to a customer. The
  twelve machine administration routes remain authenticated but unisolated.
- The 19-table preflight can block upgrade until an operator establishes correct
  ownership. No automatic NULL remediation exists.
- Global identity collisions may still reject legitimate duplicate creation
  across tenants; no foreign row is reused to conceal a collision.
- No agent protocol/product source, provider connector/authentication semantics,
  AuthPrincipal, security-global table schema, or tenant-control table structure
  changed. Backend machine-boundary call sites were narrowly adapted to carry
  explicit unowned authority into newly scoped repositories; this is not tenant
  binding and does not claim machine product isolation.
- No execution behavior was activated. No tenant secret/browser credential
  storage was introduced. No new database table was created.
- PH-3E must bind the three authority tables, propagate that verified ownership
  through every listed machine writer, resolve residual rows from evidence, then
  preflight/close the sixteen remaining nullable columns and enforce the twelve
  deferred administration routes. It has not begun.
- PH-3F receives the exact twenty-seven families and deeper reference/world-model
  acceptance. TopoAI is **not fully tenant-safe after PH-3D**.

No PH-3E/PH-3F implementation, migration 0007, machine tenant binding, execution
activation, staging, commit, push, or history operation was performed. The next
architect handoff is PH-3E, not work started in this change.

PH-3D ACCEPTED / READY FOR ARCHITECT REVIEW
