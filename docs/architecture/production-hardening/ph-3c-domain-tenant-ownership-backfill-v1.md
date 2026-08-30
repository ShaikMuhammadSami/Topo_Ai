# PH-3C — Domain Tenant Ownership + Controlled Legacy Backfill v1

- Status: **IMPLEMENTED — READY FOR ARCHITECT REVIEW**
- Verdict: **PASS**
- Repository: `C:\Topo-ai`
- Branch: `persistence/ph-3c-domain-tenant-ownership-v1`
- Accepted input commit: `16425088809de82dc07a9e3d9d99a4caba8a683c`
- Scope: additive domain tenant-ownership schema preparation only

## Scope and security boundary

PH-3C gives the accepted customer-domain persistence set explicit, nullable
tenant ownership metadata. It also provides an operator-controlled legacy
backfill, a tenant filtering index on every included table, and additive
tenant-scoped uniqueness preparation. It does not change Truth Contract
identity, repositories, APIs, background behavior, authentication,
`TenantContext`, agents, providers, the frontend, or the CLI.

This is a transitional schema. Existing rows are fully assigned during a
successful controlled upgrade, but new writes can still create `NULL`
`tenant_id` values until tenant context is enforced in later work. A nullable
tenant column and a parallel unique rule do not enforce isolation. **TopoAI is
not tenant-safe after PH-3C.**

## Accepted table partition

The 43-table ORM is partitioned without ambiguity:

| Classification | Count | Tables |
|---|---:|---|
| `PH3C_DOMAIN` | 35 | Listed below |
| `PH3E_MACHINE_AUTHORITY` | 3 | `agent_enrollment_tokens`, `topo_agents`, `change_sources` |
| `SECURITY_GLOBAL` | 2 | `auth_sessions`, `auth_api_credentials` |
| `TENANT_CONTROL` | 3 | `tenants`, `tenant_memberships`, `service_api_tenant_bindings` |
| Ambiguous | 0 | None |

The exact `PH3C_DOMAIN` set is:

1. `action_approval_events`
2. `action_approvals`
3. `build_artifact_evidence`
4. `causal_analyses`
5. `change_entity_links`
6. `change_events`
7. `change_source_dead_letters`
8. `change_source_deliveries`
9. `changes`
10. `cloud_accounts`
11. `cloud_resources`
12. `execution_intent_events`
13. `execution_intents`
14. `identity_overrides`
15. `identity_resolutions`
16. `incident_analyses`
17. `incident_copilot_messages`
18. `incident_copilot_sessions`
19. `incident_explanations`
20. `incident_investigation_plans`
21. `incident_investigation_steps`
22. `incident_outcomes`
23. `incidents`
24. `ownership_mappings`
25. `post_incident_report_actions`
26. `post_incident_reports`
27. `recovery_verifications`
28. `remediation_recommendations`
29. `runtime_dependencies`
30. `runtime_processes`
31. `runtime_sensors`
32. `signals`
33. `topology_snapshots`
34. `webhook_deliveries`
35. `webhook_endpoints`

Each receives `tenant_id VARCHAR(255) NULL`, with no application default,
server default, foreign key, relationship loader, or primary-key change. The
three machine-authority tables are intentionally reserved rather than forced
into the domain count:

- `agent_enrollment_tokens`: tenant authority must be selected when an
  administrator issues the token, then inherited atomically at enrollment.
- `topo_agents`: tenant must derive from validated enrollment and remain fixed
  for authenticated steady-state machine traffic.
- `change_sources`: tenant must derive from server-side provider source
  configuration/authentication, never a provider payload field.

Their downstream customer evidence is prepared now. Agent-derived snapshots,
cloud inventory, runtime observations, signals, and changes have ownership
columns. Source-derived deliveries, dead letters, events, links, and build
artifact evidence also have ownership columns. PH-3E must establish and
propagate the missing machine authority without trusting caller-selected
tenant identity.

## Migration and controlled backfill

The chain has exactly one head:

```text
0001_current_schema
  -> 0002_auth_sessions
  -> 0003_auth_api_credentials
  -> 0004_tenant_foundation
  -> 0005_domain_tenant_ownership
```

`0005_domain_tenant_ownership` is an additive, model-independent migration
whose down revision is `0004_tenant_foundation`. It creates no table, tenant,
membership, default, foreign key, or synthetic ownership value.

Before any PH-3C DDL, it checks all 35 domain tables for pre-tenancy rows. A
populated database requires the Alembic x-argument
`legacy_tenant_id=<tenant_id>`. The value must match the accepted
`tenant:<uuid4>` structure, identify an existing tenant, and identify a tenant
whose status is exactly `active`. Deterministic failures are:

| Condition | Result |
|---|---|
| Populated domain data and missing argument | `LEGACY_TENANT_REQUIRED` |
| Malformed tenant ID | `LEGACY_TENANT_INVALID` |
| Unknown tenant | `LEGACY_TENANT_NOT_FOUND` |
| Disabled tenant | `LEGACY_TENANT_DISABLED` |
| Post-write null validation failure | `LEGACY_TENANT_BACKFILL_INCOMPLETE` |

The authority preflight happens before DDL/backfill. On PostgreSQL the upgrade
is transactional; rejected or incomplete migrations are not stamped. With a
valid explicit target, every pre-existing row in every included table is set
to that one tenant and each table is checked for remaining null ownership.
Rows are never partitioned by company, email, repository, cloud account,
cluster, user, or tenant ordering.

An empty `0004` database upgrades without the x-argument and without creating
control-plane or domain data. Because PH-3C columns intentionally remain
nullable, a future transitional write can still be null. Startup does not
pretend otherwise. Downgrade removes only the 0005 columns and parallel rules;
re-upgrade applies the same controlled policy.

### Operator upgrade procedure

```text
application at 0004
  -> authenticated administrator creates/selects an active tenant
  -> ensure the intended human membership exists
  -> stop application writes
  -> back up and verify the database
  -> alembic -x legacy_tenant_id=<chosen-tenant-id> upgrade head
  -> verify all pre-tenancy domain rows have that tenant_id
  -> start the PH-3C application
```

There is no online mixed-version guarantee. Production orchestration remains a
PH-9 responsibility.

## Schema and constraint preparation

| Measure | Before | After |
|---|---:|---:|
| ORM tables | 43 | 43 |
| ORM columns | 733 | 768 |
| ORM indexes | 306 | 348 |
| Unique indexes | 9 | 16 |
| Named unique constraints | 14 | 24 |

There are 35 new single-column `ix_<table>_tenant_id` indexes and seven new
tenant-leading composite unique indexes: 42 new index objects in total. Ten
parallel tenant-scoped unique constraints were also added. No old global rule
was removed because current writers and deterministic IDs remain pre-tenant.

The ten audited named domain constraints and their additive counterparts are:

| Preserved global rule | Added tenant-scoped rule |
|---|---|
| `uq_action_approval_event_sequence` | `uq_tenant_action_approval_event_sequence` |
| `uq_build_artifact_provider_fact` | `uq_tenant_build_artifact_provider_fact` |
| `uq_change_event_entity_link` | `uq_tenant_change_event_entity_link` |
| `uq_execution_intent_event_sequence` | `uq_tenant_execution_intent_event_sequence` |
| `uq_identity_override_target` | `uq_tenant_identity_override_target` |
| `uq_investigation_plan_sequence` | `uq_tenant_investigation_plan_sequence` |
| `uq_post_incident_report_action_sequence` | `uq_tenant_post_incident_report_action_sequence` |
| `uq_post_incident_report_version` | `uq_tenant_post_incident_report_version` |
| `uq_runtime_sensor_agent_node_source` | `uq_tenant_runtime_sensor_agent_node_source` |
| `uq_webhook_delivery_event` | `uq_tenant_webhook_delivery_event` |

The seven audited domain unique indexes and their additive counterparts are:

| Preserved global rule | Added tenant-scoped rule |
|---|---|
| `ix_action_approvals_pending_key` | `ix_tenant_action_approvals_pending_key` |
| `ix_change_events_event_fingerprint` | `ix_tenant_change_events_event_fingerprint` |
| `ix_change_source_deliveries_delivery_key` | `ix_tenant_change_source_deliveries_delivery_key` |
| `ix_execution_intents_approval_id` | `ix_tenant_execution_intents_approval_id` |
| `ix_execution_intents_idempotency_key` | `ix_tenant_execution_intents_idempotency_key` |
| `ix_incident_outcomes_incident_id` | `ix_tenant_incident_outcomes_incident_id` |
| `ix_ownership_mappings_fingerprint` | `ix_tenant_ownership_mappings_fingerprint` |

All 17 original rules remain globally restrictive. The tenant variants prepare
non-null owned rows but, under SQL null semantics, do not constrain two
transitional null rows as final isolation would require.

## Identity and deterministic-key audit

TC-1 canonical meanings, record primary keys, logical references, content
fingerprints, historical IDs, and evidence payloads are byte-for-byte
preserved. Tenant is an outer ownership/security namespace; PH-3C does not
prefix entity, incident, snapshot, or evidence identifiers.

The accepted 28 builder families were re-audited against the implemented
storage shape:

| # | Builder family | Primary storage after PH-3C | Ownership prepared? | Remaining decision |
|---:|---|---|---|---|
| 1 | Canonical Kubernetes identity | Snapshot graph JSON | Yes, snapshot | Tenant-scoped graph/repository lookup |
| 2 | Canonical AWS identity | Snapshot/cloud rows | Yes | Tenant-scoped lookup/storage namespace |
| 3 | Canonical Azure identity | Snapshot/cloud rows | Yes | Tenant-scoped lookup/storage namespace |
| 4 | Canonical GCP identity | Snapshot/cloud rows | Yes | Tenant-scoped lookup/storage namespace |
| 5 | Git repository identity | Snapshot/change/build evidence | Yes | Tenant-aware persisted builders/lookups |
| 6 | Git commit identity | Snapshot/change/build evidence | Yes | Tenant-aware persisted builders/lookups |
| 7 | CI build/Actions run identity | Snapshot/build evidence | Yes | Tenant-aware persisted builders/lookups |
| 8 | Container image identity | Snapshot/build evidence | Yes | Tenant-scoped evidence lookup |
| 9 | Kubernetes collector entity/edge IDs | Snapshot graph JSON | Yes, snapshot | Tenant-scoped graph storage/lookup |
| 10 | Agent cloud entity/parent IDs | Cloud/snapshot rows | Yes downstream | Derive agent tenant, then namespace writes |
| 11 | Agent snapshot/runtime IDs | Snapshot/runtime rows | Yes downstream | Derive agent tenant, then namespace writes |
| 12 | GitHub repo/commit/Actions graph IDs | Snapshot/build evidence | Yes | Tenant-aware persisted builders/lookups |
| 13 | Image graph IDs | Snapshot/build evidence | Yes | Tenant-scoped graph/evidence lookup |
| 14 | Network topology IDs | Snapshot/runtime rows | Yes | Tenant-scoped graph/runtime lookup |
| 15 | Identity resolution/override IDs | Identity tables | Yes | Tenant-aware builder and query predicate |
| 16 | Event fingerprints/signal IDs | `signals` | Yes | Tenant-aware correlation and ID builder |
| 17 | Change normalizer fingerprint/ID | `changes` | Yes | Tenant-aware dedupe and ID builder |
| 18 | Change-event/link IDs | Event/link tables | Yes | Tenant-aware dedupe and ID builder |
| 19 | Source/delivery IDs and keys | Source authority plus domain delivery rows | Partial | PH-3E source binding; tenant-aware keys |
| 20 | Cloud resource IDs | `cloud_resources` | Yes | Tenant-aware builder and lookup |
| 21 | Runtime dependency/process/sensor IDs | Runtime tables | Yes | Tenant-aware builders/upserts |
| 22 | Incident fingerprint/ID/orchestration ID | `incidents` | Yes | Tenant-first correlation and ID builders |
| 23 | Incident/causal analysis/hypothesis/evidence IDs | Analysis rows/payloads | Yes at owning row | Tenant-scoped evidence resolution/builders |
| 24 | Recommendation/response/recovery/predeployment IDs | Guidance/recovery rows or derived payloads | Yes where persisted | Tenant-aware builders/lookups |
| 25 | Explanation/plan/report/outcome/memory IDs | Incident intelligence rows/derived features | Yes where persisted | Tenant-aware builders/cache/query keys |
| 26 | Ownership fingerprint | `ownership_mappings` | Yes | Tenant-aware fingerprint lookup/builder |
| 27 | Approval/execution/webhook keys | Approval/execution/webhook rows | Yes | Tenant-aware idempotency/builders |
| 28 | Secret and immutable content digests | Security/machine authority and domain records | Digest is globally safe | Keep digest algorithm; scope owned-row dedupe |

Result: 28 families audited, one digest/content algorithm family proven safe
without identity rewriting, 27 families still requiring tenant-aware query or
storage namespacing, and zero ambiguous families. Adding `tenant_id` beside a
globally deterministic single-column primary key does not prevent insert
collision. Primary-key/canonical collision closure is therefore explicitly
deferred.

## Persistence and behavior preservation

The migration and ORM are the only production changes. There are no new
tables, foreign keys, defaults, composite primary keys, route dependencies,
repository signature changes, or business-service changes. `AuthPrincipal`,
`TenantContext`, `auth_sessions`, `auth_api_credentials`, and the three
PH-3B tenant-control tables retain their accepted semantics. Incident
correlation, topology selection, RCA, ownership, reports, approval/execution,
causal scoring, and TC-1/TC-4 evidence meaning are unchanged.

The frozen LINEAGE evaluator uses only disposable copies. Its compatibility
helper refuses the protected source database, recognizes the exact historical
38-table fixture shape, applies the real 0001–0005 chain to the copy, and uses
one explicit deterministic evaluation tenant for the controlled backfill.
This changes neither evaluator algorithms nor result contracts and never adds
a tenant value to accepted evaluation JSON.

## Verification evidence

### SQLite and schema

- Focused migration/schema suite: **37 passed in 77.42s**.
- Fresh `0004 -> 0005`: passed without tenant creation or x-argument.
- Populated upgrade: passed only with an explicit active tenant.
- Missing, malformed, unknown, and disabled authority: deterministic failure
  before PH-3C DDL.
- Two tenants plus explicit tenant B: all 35 tables assigned only to tenant B.
- All-table backfill: zero migrated nulls.
- ORM/migration parity: exact columns, indexes, constraints, and nullability.
- `0005 -> 0004 -> 0005`: passed.
- A new post-upgrade row with null ownership remains possible by design.

Representative logical references survived unchanged:
`snapshot:legacy`, `signal:legacy`, `incident:legacy`,
`causal-analysis:legacy`, `change-event:legacy`, `change-link:legacy`,
`entity:legacy`, `ownership:legacy`, and `report:legacy`. Only their owning
rows gained the explicitly selected tenant.

### PostgreSQL 16

The full PostgreSQL runtime/migration module ran against a disposable
`postgres:16` container with no volume: **48 passed, 1 warning in 256.79s**.
It proved fresh and populated upgrades, missing/unknown/disabled authority
failure, two-tenant explicit-target behavior, all-35-table backfill, exact ORM
parity, transactional failure behavior, behind-schema startup denial,
downgrade, and re-upgrade. The disposable container was stopped and removed.

### Full regressions

- Backend compile: passed.
- Backend: **1103 passed, 69 skipped, 1 warning in 111.76s**
  (1172 collected).
- Evaluation compile: passed.
- Evaluation: **916 passed, 3 skipped in 33.11s** (919 collected).
- Agent compile/tests: **15 passed in 2.66s**.
- CLI compile/tests: **67 passed in 1.51s**.
- SEC-1 scanner unit tests: **8 passed**.
- Tracked-tree secret scan: passed.
- Frontend: not run because no frontend source or response contract changed.
- `ruff`/`black`: executables were not installed; Python compilation and the
  full relevant suites supplied source validation.

## Custody

Protected expected SHA-256 values are:

- `0001_current_schema_baseline.py`:
  `B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6`
- `0002_auth_sessions.py`:
  `4EB2930BFF89944DA5E9EA24F33B80F170D0F82E40F0AB508A07B2DC6B624460`
- `0003_auth_api_credentials.py`:
  `EAE6BA5CF16A4E68161A710EDFA29172E20C9DBD6F8739ACA981C4A8D4DFAC73`
- `0004_tenant_foundation.py`:
  `CBCB14FF6C8D70C1A4F4039E5436D039C599EBC842BE8DB333D6CA4ED66A9A05`
- Developer database:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`
- Frozen LINEAGE database:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`

All were measured before mutable gates and must match again at handoff. No
protected database was stamped, migrated, backfilled, or used as a live test
store. No migration before 0005 was edited.

## PH-3D enforcement handoff

The accepted PH-3A inventory remains the precise enforcement source: 25
repository modules expose 131 tenant-sensitive session-backed functions, 11
services contain 20 direct ORM paths, and 116 human product routes require
tenant context. PH-3C changes none of those signatures or predicates.

Every create/save/upsert path that can reach one of the 35 tables can still
write null ownership. PH-3D must thread server-resolved `TenantContext` through
all domain repository and direct-session access, begin every load/list/latest/
count/search/correlation/replay/upsert/update/delete with a tenant predicate,
validate same-tenant logical references, reconcile transitional null rows, and
then close nullability. Filtering after loading is forbidden.

The table-to-access checklist is:

| Domain group | Tables | Primary repository/service owners |
|---|---|---|
| Topology/identity | `topology_snapshots`, `identity_resolutions`, `identity_overrides` | snapshot/topology-snapshot/identity repositories; checkpoint, temporal and runtime-enrichment services |
| Signals/incidents/RCA | `signals`, `incidents`, `incident_analyses`, `causal_analyses` | signal, incident-record, incident and causal-analysis repositories; lifecycle, change-analysis and RCA services |
| Changes/providers | `changes`, `change_events`, `change_entity_links`, `change_source_deliveries`, `change_source_dead_letters`, `build_artifact_evidence` | change, change-event, change-source and build-evidence repositories; source ingest/lineage services |
| Runtime/cloud | `runtime_sensors`, `runtime_dependencies`, `runtime_processes`, `cloud_accounts`, `cloud_resources` | runtime-observability and cloud repositories |
| Incident intelligence | `incident_explanations`, `incident_copilot_sessions`, `incident_copilot_messages`, `incident_investigation_plans`, `incident_investigation_steps`, `remediation_recommendations`, `recovery_verifications`, `incident_outcomes` | explanation, copilot, plan, recommendation, recovery and outcome repositories/services |
| Ownership/reporting | `ownership_mappings`, `post_incident_reports`, `post_incident_report_actions` | ownership and post-incident-report repositories/services |
| Dormant execution/webhooks | `action_approvals`, `action_approval_events`, `execution_intents`, `execution_intent_events`, `webhook_endpoints`, `webhook_deliveries` | approval, execution-intent and webhook repositories/services |

All 17 pre-tenant global uniqueness rules listed above remain restrictive.
Incident fingerprint correlation, snapshot/entity access, change/evidence
fingerprints, ownership keys, historical-memory/cache keys, and every
single-column deterministic PK remain collision-sensitive until tenant-aware
builders and storage lookups are reviewed.

## PH-3E machine-authority handoff

PH-3E must add the exact three excluded ownership bindings and derive each
server-side:

1. `agent_enrollment_tokens`: from authenticated administrator tenant context
   at issuance.
2. `topo_agents`: atomically from the validated enrollment token; steady-state
   payloads cannot select or change it.
3. `change_sources`: from authenticated source creation/configuration; provider
   webhook payloads cannot select it.

It must then propagate and verify this authority on downstream PH-3C rows,
including cloud inventory, runtime observations, topology snapshots, signals,
changes, source deliveries/dead letters, change events/links, and build
evidence. Existing PH-2D authentication and token atomicity must remain intact.

## PH-3F identity-risk handoff

PH-3F must close, without rewriting source-native Truth Contract meaning:

- tenant-first incident fingerprint/correlation and incident ID creation;
- tenant-proven snapshot and nested entity lookup;
- tenant-scoped change, signal, evidence, ownership, and idempotency keys;
- tenant-scoped historical memory, report, explanation, and cache keys;
- tenant-aware deterministic persisted-record builders or an explicitly
  reviewed storage namespace strategy;
- safe removal of compatibility-global uniqueness only after all writers and
  queries are tenant-aware.

## Explicit deferrals and security conclusion

PH-3C does not close null ownership for new transitional writes, repository
tenant predicates, route enforcement, background propagation, agent/provider
binding, deterministic primary-key collisions, same-tenant RCA joins,
cross-tenant IDOR acceptance, or the two-tenant adversarial corpus. It makes no
claim that a bare entity, incident, snapshot, fingerprint, or historical ID is
globally safe across tenants.

The only allowed conclusion is that the accepted domain records now have
explicit tenant ownership metadata; pre-tenancy rows can migrate only to an
explicit active operator-selected tenant; customer identity is never inferred;
canonical evidence identity is preserved; and additive index/constraint
preparation exists. Full enforcement remains incomplete.

The next block after architect review is **PH-3D — Domain Tenant Enforcement:
Repository Predicates + API/Background TenantContext + NULL Ownership
Closure**. PH-3C stops here.

PH-3C ACCEPTED / READY FOR ARCHITECT REVIEW
