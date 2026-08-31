# PH-3E — Machine tenant binding and propagation v1

Verdict: **PASS for PH-3E's defined persistence-authority scope**. Full SQLite,
PostgreSQL, evaluation, agent and CLI regressions passed as recorded below.
This is explicitly **not** a claim that TopoAI is fully tenant-safe.

## Scope and custody authority

Repository: `C:\Topo-ai`. Branch: `security/ph-3e-machine-tenant-binding-v1`.
Accepted main/starting HEAD: `6b7265103f5a88c81d1a2f4dd9cc47d57f1b892f`.
The starting worktree was clean. No branch/history operation, staging, commit,
push, merge, rebase, tag, or PR is part of this work. PH-3F has not begun.

The approved custody amendment makes committed Git blob content authoritative
for immutable tracked migration text. In particular, 0006's Windows CRLF
working-copy bytes are not a new baseline. No normalization/edit of 0006 was
performed. Protected binary databases are always hashed as actual bytes.

The originally recorded 0001-0005 hashes below are raw Windows working-copy
bytes; they remain unchanged. The committed/LF authority is listed separately
and must not be confused with those byte representations. This is not a
rebaseline or a line-ending edit.

| Protected artifact | Recorded SHA-256 (before = after) |
|---|---|
| 0001_current_schema_baseline.py | B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6 |
| 0002_auth_sessions.py | 4EB2930BFF89944DA5E9EA24F33B80F170D0F82E40F0AB508A07B2DC6B624460 |
| 0003_auth_api_credentials.py | EAE6BA5CF16A4E68161A710EDFA29172E20C9DBD6F8739ACA981C4A8D4DFAC73 |
| 0004_tenant_foundation.py | CBCB14FF6C8D70C1A4F4039E5436D039C599EBC842BE8DB333D6CA4ED66A9A05 |
| 0005_domain_tenant_ownership.py | B60A69B26FB9A1D01DAE0107439BEC5A1C02F95FCABC0E0044F4E7F30F229E4C |
| 0006_domain_tenant_enforcement.py (HEAD blob/LF) | D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728 |
| backend/data/topo.db, developer DB V2 | 0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E |
| evaluation/results/lineage/post-sc4/topo-product-32695735269.db | 9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F |

0006's committed Git object is `fbcc470ae242299bf4c60f08fe3eacd576a399e9`.
The inspected CRLF working-copy SHA was
`9243EF0AFB8E82B6097B803C19A86AF1512BF216D7CE7CEE3AE716086AF6CFE9`;
it is explicitly not the canonical custody authority. Git's filtered object
hash matched HEAD, and its diff was empty. Both protected DB hashes matched
before implementation, after focused tests, around PostgreSQL and backend
runs, and after evaluation. Final custody commands are recorded below.

Committed Git blob SHA-256 values, unchanged at the same starting/final HEAD:

| Migration | Canonical Git blob SHA-256 (before = after) |
|---|---|
| 0001 | B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD |
| 0002 | DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92 |
| 0003 | 907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F |
| 0004 | D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3 |
| 0005 | 14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333 |
| 0006 | D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728 |

## Existing architecture inspected

Read the six accepted PH-3A/3B/3C/3D, PH-2D and PH-2F architecture/acceptance
documents, the PH-3E request and custody amendment, then traced:

- `db/models.py`, `db/domain_ownership.py`, migrations 0005/0006, Alembic env,
  database initialization and schema-authority checks.
- `repositories/agent_repository.py`, `change_source_repository.py`,
  `cloud_repository.py`, `runtime_observability_repository.py`, `tenant_scope.py`,
  tenant and artifact-evidence repositories; existing scoped domain writers.
- Agent, change-source and provider callback APIs; PH-2 agent token dependency,
  tenant context/routing, provider verification and ingestion/replay.
- Agent snapshot ingestion, continuous lifecycle/checkpoints, runtime and cloud
  enrichment, causal persistence/briefing, GitHub artifact discovery, webhook
  dispatch and delivery persistence.
- Authentication, enrollment-race, provider, tenant, schema, PostgreSQL,
  lifecycle, source-file and provenance preservation tests.
- Disposable evaluation-copy preparation, its tests and frozen seed protection;
  frontend central tenant headers and CLI global/profile tenant selection.

No current supported installation evidence proved that a single explicit
legacy-machine assertion necessarily spans independently owned legacy machines.
Read-only immutable SQLite inspection found the protected developer DB had
13 unbound enrollment tokens, 8 agents and 2 sources; the frozen seed had one
source and no agents/tokens. Both are pre-tenancy, without a tenant table or
Alembic revision. Neither was migrated, stamped, backfilled or used as the test
database. These counts are not an inference of ownership.

## Authority and transaction design

```text
Human PH-2 authentication + active membership/fixed service binding
  -> TenantContext -> scoped enrollment-token/source administration
Enrollment token digest
  -> persisted token tenant + active tenant check
  -> conditional max-use UPDATE AND agent INSERT in one transaction
Agent bearer digest
  -> persisted agent tenant + active tenant check
  -> runtime/cloud/snapshot/change/signal -> incident -> RCA -> briefing/webhook
Provider receiver ID
  -> configured source -> verify raw request -> active persisted source tenant
  -> parse -> delivery -> change event/evidence/link -> replay within same tenant
```

Human roles and membership checks remain PH-2/PH-3B. An admin role does not bypass
membership. Creation schemas forbid an explicit body `tenant_id`. Named services
continue to use their fixed binding; a conflicting human selector is denied.

`create_enrollment_token` requires a tenant ID obtained from TenantContext.
`enroll_agent` reads only an exact digest match, observes its stored tenant,
rejects unavailable/disabled tenants before consuming a use, then performs the
existing conditional expiration/revocation/max-use UPDATE with the same tenant
predicate. The agent INSERT inherits that exact tenant in the same commit.
Insert failure rolls back token consumption. Raw credentials are still returned
once; digest/hint storage and PH-2 public rejection messages are unchanged.

`authenticate_agent` resolves the exact agent-secret digest, checks revocation
and the active persisted tenant, and returns the bound record. Disabled tenants
produce bounded 401 responses, including before runtime writes. No tenant is
derived from cluster, namespace, name, metadata, creator or a request selector.

Provider callbacks use a separate, explicitly named authentication loader.
Source enablement and the existing verifier run before JSON parsing or storage;
the active tenant check then runs before parsing. A valid provider signature
with a disabled tenant has no delivery/evidence effect. GitHub, both GitLab
mechanisms, HCP Terraform, Jenkins HMAC and Azure DevOps Basic verification
remain unchanged. Agent and provider tenant headers are ignored as
non-authoritative; metadata/payload tenant claims never replace stored binding.

### The only unscoped machine-authentication derivation lookups

| Method | Exact selector | Use and boundary |
|---|---|---|
| agent_repository.enroll_agent | enrollment token SHA-256 digest equality | Derive enrollment authority; not a human lookup/list API |
| agent_repository.authenticate_agent | agent token SHA-256 digest equality | Agent dependency only; not administration |
| change_source_repository.load_change_source_for_authentication | exact source ID equality | Provider callback only; must verify before parse/persistence |

The internal active-tenant helper validates already-derived ownership; it is
not authentication or tenant selection. There is no optional-tenant shared
loader, session-global tenant, implicit default, ORM global filter, or public
machine-authority lookup. Agent detail/health/plugins/cloud-status/revoke and
source get/update/doctor use scoped SQL lookup; lists filter in SQL.

Agent heartbeat/snapshot success validate record ownership. Runtime/cloud
writers reject mismatched passed agent records. Durable parent checks now cover
snapshot scope agent IDs, change-event agent IDs, delivery/dead-letter source
IDs, runtime agent/sensor IDs and cloud-resource agent IDs. Replay proves its
dead letter, delivery and source in the same tenant before state changes.
This is machine-boundary reference validation, not PH-3F deep JSON/world-model
closure.

## Persistence and controlled legacy adoption

Exactly one new migration: `backend/alembic/versions/0007_machine_tenant_binding.py`.
Revision `0007_machine_tenant_binding`; down revision
`0006_domain_tenant_enforcement`; one Alembic head. No new table, physical foreign
key, default tenant, global unique-constraint removal, storage-ID change, 0008,
or change to any earlier migration.

The three machine-authority tables receive `tenant_id VARCHAR(255) NOT NULL`,
without ORM/server defaults, and these non-unique indexes:

- `ix_agent_enrollment_tokens_tenant_id`
- `ix_topo_agents_tenant_id`
- `ix_change_sources_tenant_id`

All 16 residual domain columns close to NOT NULL. Existing 19 already-closed
domain columns remain NOT NULL: 35 domain + 3 machine = **38 customer-owned
tables**. Total table count remains **43**; columns **771**; indexes **351**
(16 unique, 335 non-unique). Auth sessions, API credentials, tenants,
memberships and service bindings have no structural changes. AuthPrincipal is
unchanged.

### Operator assertion and failure gates

The migration requires `-x legacy_machine_tenant_id=<canonical active tenant>`
if any existing machine-authority row or NULL row among the 16 residual tables
exists. An empty installation needs no argument and creates no tenant/member.
The argument asserts that all previously unowned machine-era data belongs to
the chosen tenant; migration code does not guess or choose the first tenant.

Before DDL: validate canonical UUIDv4 shape, existing tenant and active status;
check frozen, model-independent durable references in both directions. A NULL
child pointing to a differently owned parent, or an owned child pointing to a
NULL/machine parent that would adopt another tenant, rejects the assertion.
This includes direct machine references, existing durable domain references and
delivery event-ID arrays. Missing/invalid historical references do not prove
ownership and are never used to infer it. Checks stream rows in bounded batches.

Bounded errors are `LEGACY_MACHINE_TENANT_REQUIRED`, `_INVALID`, `_NOT_FOUND`,
`_DISABLED`, `_CONFLICT` and `MACHINE_TENANT_NULL_ROWS_PRESENT`. Missing or invalid
authority produces neither schema change nor a stamp. Backfill updates only
NULL ownership in the exact 3+16 tables; all non-NULL owners, IDs and other
stored fields remain unchanged. All 19 columns are audited for NULL before
closure. PostgreSQL rollback after an injected post-backfill closure failure
restores DDL, data and stamp; SQLite tests establish pre-DDL rejection gates.

Downgrade restores 16 residual columns' nullability and removes only the three
machine tenant columns/indexes. It deletes no domain/control/security records;
re-upgrade uses an explicit assertion if legacy machine rows remain. Production
PostgreSQL startup rejects revision 0006 as behind. Intentional local SQLite
metadata-creation compatibility is unchanged; its explicit schema-authority
verification also rejects behind state. Protected DBs were never upgraded.

## Exact residual writers and propagation

| Residual table | Authoritative writer after PH-3E |
|---|---|
| topology_snapshots | Authenticated agent -> persist_agent_snapshot -> checkpoint |
| changes | Same tenant -> checkpoint snapshot diff |
| signals | Bound agent signals or snapshot failure detection -> lifecycle |
| incidents | Same tenant -> lifecycle correlation/creation |
| causal_analyses | Same tenant -> existing automatic analyze_causal_rca/persistence |
| build_artifact_evidence | Authenticated GitHub discovery -> provider artifact enrichment; see correction below |
| change_events | Bound agent batch, bound provider ingestion, or owned snapshot diff |
| change_entity_links | Existing event/checkpoint correlation with propagated tenant |
| change_source_deliveries | Verified provider source tenant |
| change_source_dead_letters | Same source/delivery tenant, including replay |
| cloud_accounts | Agent snapshot -> persist_cloud_inventory with agent tenant |
| cloud_resources | Same writer plus owned agent reference |
| runtime_sensors | Authenticated agent heartbeat/batch |
| runtime_dependencies | Same agent batch and owned sensor |
| runtime_processes | Same agent batch and owned sensor |
| webhook_deliveries | Machine-triggered lifecycle publishes only owned endpoints |

Inventory correction: PH-3D labeled artifact persistence as a webhook-origin
writer. Actual code has only `api/github.py ->
enrich_snapshot_with_github_actions_provider_evidence -> save_build_artifact_evidence`,
already carrying the authenticated request tenant. Webhook normalization does
not create BuildArtifactEvidenceRecord. This block closes the residual column
and tests the real provider-artifact writer; it does not invent a callback path.

The old marker had **25 textual references** at HEAD: **20 call-site uses**,
3 imports, definition and comparison. It now has zero production references,
as do DeferredMachineAuthority and the marker's string value. `DomainTenant`
is a validated string; no live tenant-NULL predicate or machine write remains.
Migration preflight/backfill and test NULL audits are not live domain queries.

## Route and repository reconciliation

The historical 104 + 12 = 116 human tenant-required routes are now all enforced.
No routes were added or removed: **143 method/path pairs**, **0 unknown**.

| Current classification | Count |
|---|---:|
| PH3D_TENANT_REQUIRED (name retained) | 116 |
| MACHINE_BOUND | 9 |
| TENANT_CONTROL | 7 |
| SECURITY_GLOBAL | 9 |
| PUBLIC | 2 |
| MACHINE_AUTHORITY_DEFERRED / MACHINE_DEFERRED | 0 |

The twelve former human deferrals, now tenant-required:

| Method/path | Authority |
|---|---|
| POST /api/v1/agents/enrollment-tokens | agent_enrollment_tokens |
| GET /api/v1/agents | topo_agents |
| GET /api/v1/agents/{agent_id} | topo_agents |
| GET /api/v1/agents/{agent_id}/health | topo_agents |
| POST /api/v1/agents/{agent_id}/revoke | topo_agents |
| GET /api/v1/agents/{agent_id}/plugins | topo_agents |
| GET /api/v1/agents/{agent_id}/cloud-status | topo_agents |
| POST /api/v1/change-sources | change_sources |
| GET /api/v1/change-sources | change_sources |
| GET /api/v1/change-sources/{source_id} | change_sources |
| PATCH /api/v1/change-sources/{source_id} | change_sources |
| GET /api/v1/change-sources/{source_id}/doctor | change_sources |

Cross-tenant direct GET/PATCH/revoke returns 404; foreign list selectors return
no foreign evidence. Missing human selector is 400, unauthorized membership is
403, invalid machine/provider credentials or disabled bound tenant is 401.
PH-2 still classifies 8 agent-authenticated routes and 1 provider callback.

AST inventory: **144 session-taking repository functions in 25 modules**,
**141 explicit scoped functions**, **3 named authentication derivations**.
Of these 132 are public and 12 internal; 129 public are scoped. Zero generic
unscoped machine methods, optional tenant administration functions or ambiguous
operations remain. The inventory excludes security/tenant-control repositories,
not machine administration. SQL-expression tests inspect actual predicates,
including tenant-scoped enrollment UPDATE, and permit only the three exact
authentication SELECT predicates. Owned `Session.get` is banned.

The historical direct-ORM inventory remains 20 functions/11 services: 19 with
explicit tenant arguments and 1 provider entry deriving its tenant after
verification; **20 tenant-scoped, 0 deferred, 0 ambiguous**. Existing raw SQL
in migrations/schema/audit tooling remains installation-scoped, not a new
customer query or default-authority escape.

## Tests and non-NULL observation

New migration coverage: fresh schema, 38 physical NOT NULL columns/no defaults,
strict parity, downgrade/re-upgrade, production behind-head rejection, required/
invalid/unknown/disabled legacy authority, explicit target with two tenants,
preservation of all existing values, both-direction conflicts, machine-parent
conflicts, residual-only adoption, and injected PostgreSQL rollback after backfill.

New binding coverage: real PH-2 credentials/membership, token-to-agent inheritance,
overlapping names/cluster/source metadata with distinct representable IDs, forged
tenant headers/payloads, agent and source GET/list/health/plugins/cloud-status/
revoke/PATCH isolation, disabled tenant no-consumption/no-write, fixed service
binding, provider verify-before-parse/idempotency, durable parent rejection, and
agent runtime + cloud + checkpoint + failure + incident + persisted RCA +
briefing + outgoing webhook ownership. Only network I/O is substituted for
outbound webhook delivery; orchestration/persistence are real. Provider artifact
ownership tests use the existing provider-authentic artifact fixture.

Existing concurrency tests prove max_uses=1 has one winner from two contenders,
max_uses=2 has two winners from three, forced agent INSERT failure restores
use_count, and revocation is durable on SQLite/PostgreSQL. Existing PH-2 provider
tests retain all supported verification mechanisms and credential-domain tests.

The following is an actual PostgreSQL machine-pipeline observation. Every table
was audited, including empty tables; zero rows is not claimed as writer coverage.
Separate source/artifact/replay and migration tests cover those paths.

| Table | Total rows | NULL owners |
|---|---:|---:|
| action_approval_events | 0 | 0 |
| action_approvals | 0 | 0 |
| agent_enrollment_tokens | 1 | 0 |
| build_artifact_evidence | 0 | 0 |
| causal_analyses | 1 | 0 |
| change_entity_links | 14 | 0 |
| change_events | 13 | 0 |
| change_source_dead_letters | 0 | 0 |
| change_source_deliveries | 0 | 0 |
| change_sources | 0 | 0 |
| changes | 13 | 0 |
| cloud_accounts | 1 | 0 |
| cloud_resources | 1 | 0 |
| execution_intent_events | 0 | 0 |
| execution_intents | 0 | 0 |
| identity_overrides | 0 | 0 |
| identity_resolutions | 0 | 0 |
| incident_analyses | 0 | 0 |
| incident_copilot_messages | 0 | 0 |
| incident_copilot_sessions | 0 | 0 |
| incident_explanations | 0 | 0 |
| incident_investigation_plans | 0 | 0 |
| incident_investigation_steps | 0 | 0 |
| incident_outcomes | 0 | 0 |
| incidents | 1 | 0 |
| ownership_mappings | 0 | 0 |
| post_incident_report_actions | 0 | 0 |
| post_incident_reports | 0 | 0 |
| recovery_verifications | 0 | 0 |
| remediation_recommendations | 0 | 0 |
| runtime_dependencies | 1 | 0 |
| runtime_processes | 1 | 0 |
| runtime_sensors | 1 | 0 |
| signals | 1 | 0 |
| topo_agents | 1 | 0 |
| topology_snapshots | 2 | 0 |
| webhook_deliveries | 1 | 0 |
| webhook_endpoints | 2 | 0 |

## Causal, evaluation, authentication and client preservation

No canonical IDs, ranking/scoring, candidate windows, abstention, TC evidence
semantics, historical snapshot pinning or provenance algorithms changed. The
accepted causal/evaluation preservation-test exclusions were not broadened;
`test_github_actions_build_lineage.py` is unchanged. Only disposable evaluation
schema preparation advanced to 0007 with an explicit single-fixture assertion,
and its expected schema/owned-table count changed. No frozen result, evaluator
grade, ground truth, evidence normalization or experiment was altered/rerun.

Tests using the removed quarantine now explicitly seed real fixture tenancy.
Historical 0006 tests still exercise its frozen 19-column closure independently
of 0007; they were not replaced with new-head assertions. Four old PH-2 tests
initially returned 400 on newly tenant-required administration routes; they now
provide real memberships/headers while preserving 201/403/CSRF assertions.
No broad default-tenant autouse fixture or TenantContext bypass was added.

The first PostgreSQL full run also exposed two stale PH-1C fixture expectations:
the expected non-unique index count was still 332 rather than 335, and a generated
runtime-agent fixture did not explicitly carry TEST_TENANT. The count now includes
the three specified indexes, and only that fixture explicitly supplies its owner.
The subsequent focused run passed both cases; ownership enforcement was not relaxed.

Frontend and CLI product sources did not change. Frontend central requests
already supply the selected workspace tenant, drop call-site overrides, preserve
cookie/CSRF handling, reject stale workspace responses, distinguish 401 from
tenant-denied 403, and use scoped downloads. CLI `--tenant` overrides its profile
selection; service credentials still use server binding. Agent clients need no
tenant header or protocol update. No visual redesign or execution work occurred.

## Verification results

Final results (all commands exit 0):

| Check | Result |
|---|---|
| Backend compile | exit 0 |
| Full backend, SQLite/default | 1,202 passed, 101 skipped, 1 warning; 320.71s |
| Full backend, PostgreSQL 16 enabled | 1,302 passed, 1 skipped, 1 warning; 557.89s |
| PostgreSQL backup/restore | passed within full suite; 4.482s testcase time |
| Full evaluation | 917 passed, 3 skipped; 98.38s |
| Evaluation compile | exit 0 |
| Agent compile / full tests | exit 0 / 15 passed; 3.52s |
| CLI compile / full tests | exit 0 / 70 passed; 4.19s |
| Provider/source-file focused | 34 passed, 1 warning; 12.77s |
| SEC-1 scanner tests | 8 passed; final repeat 0.11s |
| Tracked and new-file secret scans | passed |
| git diff --check | exit 0 |
| Frontend | not run; no changes |

Additional focused observations:

- Focused agent/provider/lifecycle/source/tenant regressions: 127 passed.
- SQLite schema/0006 regression/repository inventory: 62 passed, 20 PostgreSQL skips.
- Initial PH-3E PostgreSQL migration/binding/enrollment bundle: 31 passed.
- Expanded PostgreSQL machine-to-briefing + webhook path: 1 passed.
- Expanded migration/artifact bundle: 22 passed, 1 SQLite-only transactional-DDL skip.
- Repaired PH-2 authentication-focused suite: 54 passed.
- Corrected PostgreSQL schema/runtime cases plus provider regressions: 36 passed (9.37s).
- Final SQLite full backend: 1,202 passed, 101 skipped, 1 warning (320.71s).
- Final standalone provider/source-file suite: 34 passed, 1 warning (12.77s).
- Evaluation: 917 passed, 3 Windows symlink skips (98.38s).
- Agent: compile exit 0; 15 passed (3.52s).
- CLI: compile exit 0; 70 passed (4.19s).
- SEC-1: 8 passed; tracked and new-file scans passed.
- Frontend checks not run: no frontend change was required.

The SQLite full-run skips comprise 100 PostgreSQL cases without an opt-in URL
and one deliberately PostgreSQL-only post-DDL rollback proof. That test's
SQLite parameter is skipped; its PostgreSQL parameter runs. The warning is the
existing Starlette/httpx TestClient deprecation. Pytest's cache provider was
disabled because existing cache directories are permission-restricted; no test
was deselected to avoid a failure.

Both final backend reports contain 1,303 collected cases, 0 failures and 0
errors. With PostgreSQL enabled, the only skip is
`test_postgres_failure_after_backfill_rolls_back_ddl_data_and_stamp[sqlite]`.
All 100 opt-in PostgreSQL cases, including backup/restore, actually ran.
The evaluation's three skips are the existing Windows symlink limitations.

Final JUnit receipts are temporary local verification output (not tracked):
`%TEMP%/topo-ph3e-backend-sqlite-complete.xml`,
`%TEMP%/topo-ph3e-backend-postgres-complete.xml`, and
`%TEMP%/topo-ph3e-evaluation.xml`. They are not frozen experiment artifacts.

Commands used (from `C:\Topo-ai\backend`, against disposable databases only):

```powershell
& .\.venv\Scripts\python.exe -m compileall -q app
& .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q --tb=short
# Separate process for the PostgreSQL acceptance run:
$env:TOPO_TEST_POSTGRES_URL='postgresql+psycopg://postgres@127.0.0.1:55439/topo_ph3e_test'
$env:TOPO_TEST_POSTGRES_CONTAINER='topo-ph3e-acceptance-20260831'
& .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q --tb=short
```

The connection above identifies only the task-created, loopback test container;
it is not a production migration instruction. No deployment database was
selected through application configuration or upgraded implicitly.

New named tests (parameterized cases also run on PostgreSQL):

- `test_fresh_38_owned_tables_no_defaults_and_downgrade_parity`
- `test_rejected_authority_has_no_ddl_backfill_or_stamp`
- `test_explicit_adoption_two_tenants_preserves_every_owned_row_and_id`
- `test_conflicts_in_both_reference_directions_fail_before_ddl`
- `test_machine_parent_conflict_rejects_incorrect_assertion`
- `test_residual_only_data_requires_explicit_adoption`
- `test_postgres_failure_after_backfill_rolls_back_ddl_data_and_stamp`
- `test_agent_binding_inheritance_header_ignored_and_cross_tenant_admin`
- `test_disabled_tenant_blocks_enrollment_without_consumption_and_existing_agent`
- `test_source_management_provider_binding_idempotency_and_disabled_tenant`
- `test_human_machine_creation_rejects_payload_tenant`
- `test_service_fixed_binding_applies_to_machine_admin`
- `test_real_agent_snapshot_failure_rca_briefing_carries_tenant`
- `test_machine_parent_references_cannot_cross_tenants`
- `test_provider_artifact_discovery_persists_and_scopes_authoritative_tenant`

PostgreSQL uses task-created `topo-ph3e-acceptance-20260831`, image `postgres:16`,
loopback `127.0.0.1:55439`, tmpfs `/var/lib/postgresql/data`, no mounted/named
persistent volume. Local test-only trust authentication is confined to this
disposable acceptance instance; it is not a production configuration. After all
tests, its exact ID
`2ee59d3695aeb8424e1e985898ef898e274e02bbc626f386414de570ee46acab`
was inspected, stopped and removed. A subsequent exact-ID container listing
was empty. Only this task-created container and its tmpfs test data were removed;
that temporary data is not retained. No persistent volume or user database was
deleted. Both protected binary hashes still matched afterward.

## Deployment compatibility

Migrate an operator-selected deployment database to 0007 before running the
new application. Existing machine-era data requires the explicit, valid
`legacy_machine_tenant_id` assertion; this block did not execute it on either
protected database. Installations whose legacy machines demonstrably belong
to multiple independent tenants need an explicitly reviewed mapping, not a
guessed assignment.

The twelve administration routes now require the same tenant selection or fixed
service binding as ordinary domain routes. Existing frontend/CLI transports
already provide it; ad hoc callers must also do so. Existing agent/provider
credentials continue to work after their persisted rows are explicitly bound;
no new agent-supplied tenant field is accepted. Disabled tenants cannot enroll,
authenticate an agent, or ingest a verified provider callback.

Global primary keys/uniqueness and existing deep references are unchanged.
Therefore this block does not promise simultaneous storage of colliding native
IDs in different tenants. These remain explicit PH-3F risks.

## PH-3F handoff: unchanged 28-family classification

Families 1–27 remain **PH3F_IDENTITY_REQUIRED**: query-isolated where durable,
but storage-collision/deep-world-model closure is not claimed. Machine-entry
dependencies are now bound, not a reason to rewrite native identities.

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
18. Durable change-event fingerprint/event/link IDs.
19. Change-source ID and delivery ID/key.
20. Cloud-resource storage IDs.
21. Runtime dependency/process IDs and sensor business keys.
22. Incident fingerprint/incident/orchestration IDs.
23. Incident/causal analysis, hypothesis/evidence/stable IDs.
24. Recommendation/response/recovery/predeployment IDs.
25. Explanation/investigation/report/outcome/memory IDs and hashes.
26. Ownership mapping fingerprints.
27. Approval pending/evidence, execution idempotency, webhook event/delivery keys.
28. Secret/content digests: safe digest computation only; persisted dedupe still
    requires tenant-scoped lookup.

Classification: 1 safe digest-computation family, 27 PH3F_IDENTITY_REQUIRED,
0 ambiguous. Global PK/unique constraints remain; collisions fail closed rather
than adopting foreign records. Deeper polymorphic/JSON RCA references, caches,
materialized lookups, identity namespaces and adversarial full-world-model
acceptance remain PH-3F.

TopoAI is **not fully tenant-safe** after PH-3E. Structural ownership and
human/service/agent/provider authority at the persistence boundary do not imply
canonical collision closure or deep RCA/world-model same-tenant acceptance.
The recommended next block, requiring separate authorization, is PH-3F — Tenant-Scoped Identity
Namespace + Deterministic Collision Closure + World-Model / RCA Same-Tenant
Integrity. This document does not authorize or begin it.

## Final file inventory and Git state

36 changed paths: 30 modified tracked files and 6 new, unstaged files.

| Category | Modified | Created | Total |
|---|---:|---:|---:|
| Backend product | 13 | 1 | 14 |
| Alembic migration | 0 | 1 | 1 |
| Backend tests/fixtures | 15 | 3 | 18 |
| Evaluation copy preparation/test | 2 | 0 | 2 |
| Documentation | 0 | 1 | 1 |
| OTHER / frontend / CLI / agent / workflows | 0 | 0 | 0 |

`git status --short` (M = modified; ?? = created and untracked):

```text
 M backend/app/api/agents.py
 M backend/app/api/change_source_webhooks.py
 M backend/app/api/change_sources.py
 M backend/app/db/domain_ownership.py
 M backend/app/db/models.py
 M backend/app/repositories/agent_repository.py
 M backend/app/repositories/change_source_repository.py
 M backend/app/repositories/cloud_repository.py
 M backend/app/repositories/runtime_observability_repository.py
 M backend/app/repositories/tenant_scope.py
 M backend/app/security/tenant_routing.py
 M backend/app/services/agent_snapshot_ingest.py
 M backend/app/services/change_source_ingest.py
 M backend/tests/domain_tenant_fixtures.py
 M backend/tests/test_agent_authentication_hardening.py
 M backend/tests/test_agent_enrollment_postgres.py
 M backend/tests/test_auth_sessions.py
 M backend/tests/test_authentication_acceptance.py
 M backend/tests/test_authentication_default_on.py
 M backend/tests/test_continuous_lifecycle.py
 M backend/tests/test_domain_tenant_closure.py
 M backend/tests/test_domain_tenant_enforcement.py
 M backend/tests/test_domain_tenant_inventory.py
 M backend/tests/test_domain_tenant_migration.py
 M backend/tests/test_postgres_runtime_compatibility.py
 M backend/tests/test_provider_authentication_hardening.py
 M backend/tests/test_schema_migrations.py
 M backend/tests/test_source_file_mutations.py
 M evaluation/lineage_distractor_robustness.py
 M evaluation/tests/test_lineage_distractor_robustness.py
?? backend/alembic/versions/0007_machine_tenant_binding.py
?? backend/app/security/machine_tenant.py
?? backend/tests/test_machine_artifact_ownership.py
?? backend/tests/test_machine_tenant_binding.py
?? backend/tests/test_machine_tenant_migration.py
?? docs/architecture/production-hardening/ph-3e-agent-provider-tenant-binding-machine-propagation-v1.md
```

`git diff --name-only` is exactly the 30 M paths above; Git does not include
untracked additions in that command. `git diff --stat`: **30 files changed,
340 insertions(+), 198 deletions(-)**, excluding the six new files for the same
reason. No changes are staged. Existing cache-directory permission warnings and
Git CRLF notices are reported separately from command exit status; they did not
modify any file or cause a whitespace-check failure.

## Final verdict

**PASS.** No legacy-mapping, machine-authority, security, identity or custody
blocker was observed within PH-3E's defined scope. The accepted custody amendment
was honored: all six existing migration diffs are empty; 0006 HEAD blob and
filtered working-copy Git object are identical; actual binary database hashes
are unchanged. HEAD and branch are unchanged. The temporary PostgreSQL instance
has been removed.

Human/service/agent/provider ownership authority and non-NULL persistence are
complete for the specified 38 tables. Canonical collision closure and deep
RCA/world-model same-tenant acceptance are **not** complete.

STOP: no staging, commit, push, merge, rebase, tag, branch switch, PR, protected
database mutation, 0008, provider/Kubernetes experiment, execution work, or PH-3F
implementation was performed.

## Requested completion checklist (1-164)

1. Scope: PH-3E machine authority, propagation and residual ownership closure only.
2. Accepted main/start: `6b7265103f5a88c81d1a2f4dd9cc47d57f1b892f`.
3. Branch: `security/ph-3e-machine-tenant-binding-v1`.
4. Verdict: PASS for PH-3E's defined persistence-authority boundary; not full tenant-safety acceptance.
5. Migration: `backend/alembic/versions/0007_machine_tenant_binding.py`.
6. Revision: `0007_machine_tenant_binding`.
7. Down revision: `0006_domain_tenant_enforcement`.
8. Alembic head count: 1.
9. Alembic head: `0007_machine_tenant_binding`.
10. 0001 SHA before/after: equal; both raw working-copy and canonical blob values are in the custody tables.
11. 0002 SHA before/after: equal; both representations are in the custody tables.
12. 0003 SHA before/after: equal; both representations are in the custody tables.
13. 0004 SHA before/after: equal; both representations are in the custody tables.
14. 0005 SHA before/after: equal; both representations are in the custody tables.
15. 0006 SHA before/after: canonical `D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728`; Windows expansion is not the authority.
16. Existing migrations changed: NO; empty diff, unchanged HEAD and filtered worktree blob identity.
17. ORM table count: 43.
18. New tables: NONE.
19. `agent_enrollment_tokens.tenant_id` added: YES.
20. `topo_agents.tenant_id` added: YES.
21. `change_sources.tenant_id` added: YES.
22. Machine authority tenant columns nullable: NO.
23. Machine authority tenant defaults: NONE.
24. Indexes: `ix_agent_enrollment_tokens_tenant_id`, `ix_topo_agents_tenant_id`, `ix_change_sources_tenant_id`.
25. Residual tables entering PH-3E: 16, exactly listed in the writer table.
26. Residual tables closed NOT NULL: 16.
27. Residual nullable customer-owned tables: 0.
28. Physically NOT NULL customer-owned tables: 38.
29. Tenant-owned NULL/default-tenant defaults: 0.
30. `legacy_machine_tenant_id` required when any machine row or residual NULL owner exists.
31. Empty database argument required: NO.
32. Existing machine data without argument: `LEGACY_MACHINE_TENANT_REQUIRED`, before DDL.
33. Unknown target: `LEGACY_MACHINE_TENANT_NOT_FOUND`.
34. Disabled target: `LEGACY_MACHINE_TENANT_DISABLED`.
35. Multiple tenants plus explicit target: accepted only with active valid target and no contradictory recorded reference; tested on both engines.
36. Automatic tenant creation: NO.
37. Automatic membership creation: NO.
38. Existing non-NULL ownership overwritten: NO.
39. Legacy conflict validation: exact durable parent references in both directions; `LEGACY_MACHINE_TENANT_CONFLICT` before DDL.
40. Failed migration stamped: NO; preflight and injected PostgreSQL rollback tests prove it.
41. Token creation authority: human membership or fixed service TenantContext.
42. Body may select enrollment-token tenant: NO (422).
43. Enrolled agent authority: authenticated enrollment token's persisted tenant.
44. Agent INSERT and conditional token consumption atomic: YES.
45. Max-use concurrency: one winner for max=1/two contenders, two winners for max=2/three contenders; PostgreSQL passed.
46. Forced agent INSERT failure: token consumption rolls back; PostgreSQL passed.
47. Steady-state agent authority: authenticated persisted `topo_agents.tenant_id`.
48. Agent tenant header authoritative: NO; conflicting header and metadata do not rebind.
49. Agent derivation: exact-digest `enroll_agent` / `authenticate_agent`, as listed above.
50. Agent auth lookup exposed as human administration: NO.
51. Human agent administration enforced: 7 routes.
52. Cross-tenant agent GET: 404.
53. Cross-tenant revoke: 404.
54. Agent list SQL tenant-scoped: YES.
55. Source creation authority: human membership or fixed service TenantContext.
56. Body may select source tenant: NO (422).
57. Provider authority: verified configured source's persisted tenant.
58. Provider payload/header authoritative: NO.
59. Provider auth loader: `load_change_source_for_authentication`, exact receiver ID only.
60. Provider auth lookup exposed as human administration: NO.
61. Verify-before-parse: preserved; disabled-tenant check also precedes JSON parse.
62. Human source administration enforced: 5 routes.
63. Cross-tenant source GET: 404.
64. Cross-tenant source PATCH: 404.
65. Source list SQL tenant-scoped: YES.
66. UNOWNED_MACHINE before: 25 textual references, including 20 actual call-site uses.
67. UNOWNED_MACHINE production references after: 0.
68. DeferredMachineAuthority production references after: 0.
69. Live machine `tenant_id IS NULL` selection/write semantics: 0.
70. Agent-origin NULL writes: 0; explicit binding plus physical NOT NULL.
71. Provider-origin NULL writes: 0; verified source binding plus physical NOT NULL.
72. Machine-triggered background NULL writes: 0; propagated binding plus physical NOT NULL.
73. topology_snapshots: authenticated agent binding, real checkpoint test.
74. changes: checkpoint diff inherits that binding, real persisted rows.
75. signals: agent/snapshot failure inherits that binding, real persisted rows.
76. incidents: lifecycle correlation inherits that binding, real persisted incident.
77. causal_analyses: existing automatic 13C persists same tenant; briefing succeeds.
78. build_artifact_evidence: actual authenticated GitHub discovery writer is scoped and tested; no invented webhook writer.
79. change_events: bound agent/provider/snapshot ingestion, real rows and source regressions.
80. change_entity_links: same tenant through existing correlation, real persisted links.
81. change_source_deliveries: verified source tenant, duplicate isolation/durability tests.
82. change_source_dead_letters: source/delivery tenant, existing failure/replay PostgreSQL tests.
83. cloud_accounts: bound agent inventory, real persisted account.
84. cloud_resources: bound agent inventory and owned agent reference, real persisted resource.
85. runtime_sensors: bound agent heartbeat/batch, real persisted sensor.
86. runtime_dependencies: bound agent and owned sensor, real persisted dependency.
87. runtime_processes: bound agent and owned sensor, real persisted process.
88. webhook_deliveries: only owned endpoints selected; real dispatch/persistence with substituted network transport.
89. Human machine-authority deferrals before: 12.
90. Human machine-authority deferrals after: 0.
91. Human tenant-required routes: 116 = previous 104 + enforced 12.
92. Machine-bound routes: 9 (8 agent/enrollment paths, 1 provider callback).
93. Unknown routes: 0.
94. Exact authentication derivations: `enroll_agent`, `authenticate_agent`, `load_change_source_for_authentication`; no others in audited repositories.
95. Generic unscoped machine repository methods remaining: 0.
96. Optional-tenant human machine administration methods remaining: 0.
97. Provider duplicate/idempotency: preserved; repeated delivery returns existing receipt, another source's same external delivery key remains distinct.
98. Invalid provider auth: no delivery/domain effect; regression passed.
99. Agent/provider credential-domain substitution regressions: passed unchanged PH-2 expectations.
100. Two-tenant agent proof: same names/cluster, distinct bound agents; foreign administration denied.
101. Two-tenant provider proof: same source metadata, persisted binding controls ingestion; foreign administration denied.
102. Overlapping metadata proof: cluster/name/source labels are never used as tenant authority; global canonical-ID collision closure is not claimed.
103. Fresh SQLite to 0007: passed.
104. Populated SQLite with explicit assertion: passed, IDs/non-NULL owners preserved.
105. SQLite missing assertion: rejected before DDL/backfill/stamp.
106. SQLite strict parity: passed.
107. Fresh PostgreSQL to 0007: passed.
108. Populated PostgreSQL with explicit assertion: passed.
109. PostgreSQL missing assertion: rejected before DDL/backfill/stamp.
110. PostgreSQL unknown target: rejected before DDL.
111. PostgreSQL disabled target: rejected before DDL.
112. PostgreSQL explicit two-tenant target: passed; no first-tenant inference.
113. PostgreSQL all-38 NOT NULL: physically inspected, no defaults; audit table records observed counts.
114. PostgreSQL machine write isolation: real two-tenant HTTP/persistence tests passed.
115. PostgreSQL transactional failure: injected after backfill; DDL, assignment and revision stamp rolled back; retry passed.
116. 0007 to 0006 downgrade: passed on SQLite and PostgreSQL.
117. Re-upgrade: passed on both engines.
118. PH-2 regression: passed in full backend, including auth sessions/credentials, default-on, provider and enrollment cases.
119. PH-3B regression: tenant foundation/membership/service-context tests passed.
120. PH-3C regression: domain ownership/backfill/uniqueness tests passed.
121. PH-3D regression: frozen 0006 tests, repository inventory and real route/domain isolation tests passed.
122. Full backend: see exact final SQLite and PostgreSQL result table.
123. Full evaluation: 917 passed, 3 Windows symlink skips.
124. Agent: compile exit 0; 15 passed.
125. Provider focused: 34 passed (12.77s).
126. CLI: compile exit 0; 70 passed.
127. Frontend: not run; no source changes. Existing central tenant transport inspected.
128. Compilation: backend, evaluation, agent and CLI exit 0.
129. Secret scanner tests: 8 passed.
130. Tracked-tree scanner: passed; new-file scan also passed.
131. `git diff --check`: exit 0.
132. Developer DB before: `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
133. Developer DB after: same actual-byte SHA-256.
134. Developer DB unchanged: YES; never migrated, stamped or used for tests.
135. Frozen LINEAGE before: `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.
136. Frozen LINEAGE after: same actual-byte SHA-256.
137. Frozen LINEAGE unchanged: YES; no experiment/provider/Kubernetes operation.
138. 0001-0006 unchanged: YES; committed representation and empty diffs prove custody.
139. AuthPrincipal changed: NO.
140. auth_sessions schema changed: NO.
141. auth_api_credentials schema changed: NO.
142. Tenant control tables structurally changed: NO.
143. Canonical IDs rewritten: NO.
144. Causal scoring changed: NO.
145. Files created: the 6 ?? paths in the exact Git inventory.
146. Files modified: the 30 M paths in the exact Git inventory.
147. Migration files created: exactly 0007.
148. Other migration files modified: NONE.
149. `git status --short`: exact output recorded in the Git inventory.
150. `git diff --name-only`: exactly the 30 tracked M paths; untracked files are separately listed.
151. Legacy mapping blocker: NONE in the inspected supported state; explicit operator assertion still required on real legacy installations.
152. Machine authority blocker: NONE.
153. Security blocker: NONE observed within PH-3E acceptance.
154. Identity blocker: NONE for PH-3E; known collision/deep-integrity work remains PH-3F.
155. Custody blocker: NONE; approved canonical-text amendment applied.
156. First blocker: NONE.
157. Fully tenant-safe after PH-3E: NO.
158. Customer-owned rows structurally non-NULL: YES in schema 0007; protected legacy DBs intentionally remain untouched.
159. Human/service/agent/provider authority complete at the defined persistence boundary: YES.
160. Deterministic/canonical storage collision closure complete: NO.
161. Deep RCA/world-model same-tenant acceptance complete: NO.
162. PH-3F risks: the unchanged 28-family inventory above, global key collisions, deep references, caches/materialized lookup/world-model acceptance.
163. Recommended next block only: PH-3F — Tenant-Scoped Identity Namespace + Deterministic Collision Closure + World-Model / RCA Same-Tenant Integrity.
164. STOP after PH-3E. No staging, commit, push, history operation, 0008, or PH-3F implementation.
