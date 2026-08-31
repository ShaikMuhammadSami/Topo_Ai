# PH-3G — Adversarial two-tenant acceptance and closure v1

## Scope and baseline

Repository: `C:\Topo-ai`. Required/current branch:
`security/ph-3g-adversarial-tenant-acceptance-v1`.
Accepted starting HEAD: `635306b7a9cdf4f183b4d6f4531f9acbfa8b80fa`
(`feat(persistence): namespace tenant-local identities (#78)`). Starting worktree
was clean. This is acceptance of PH-3A–F, not a feature or identity redesign.

**Final verdict: PASS_PH3_CLOSE.** Verification completed on 2026-08-31.
The completed run results, custody checks and closure decision are recorded below.
No migration 0009, Git write, live Kubernetes/provider experiment, infrastructure
execution, protected-database migration/stamp, or PH-4 work is authorized here.

Read in full: accepted PH-3A persistence inventory, PH-3B membership/context,
PH-3C ownership/backfill, PH-3D predicates, PH-3E machine authority, PH-3F identity
namespace/world-model contracts; PH-2D/2F authentication; Truth Substrate and
TC-1 through TC-5. Historical counts in earlier documents are not substituted
for the actual current route/schema inventory.

## Independent corpus and authority

The new corpus is in four `backend/tests/test_tenant_adversarial_*.py` modules.
It reuses disposable database and PH-2 credential fixture infrastructure, not
TenantContext overrides. The hostile fixture explicitly creates two tenants and
real memberships/credentials through supported authenticated APIs. No universal
autouse tenant fixture or inferred/default tenant is installed.

| Actor | Authority exercised |
| --- | --- |
| Human A / Human B | Bootstrap human administrators, each a member of only its own tenant |
| Human AB | Named human credential with explicit memberships in both tenants |
| AdminNoB | Named admin, A membership only; admin role cannot select B |
| Service A / Service B | Named service credentials with fixed server-persisted bindings |
| Agent A / Agent B | Real enrollment-token creation and enrollment; persisted owner inherited atomically |
| Provider A / Provider B | Separate configured GitHub sources and different fixture HMAC secrets |

Primary machine inputs deliberately overlap: cluster `prod`, namespace `default`,
workload `checkout`, Pod/ReplicaSet/Deployment UIDs, sensor ID, node, runtime
destination and process, cloud account/VPC, submission labels, and failure time.
The source corpus overlaps repository identity, SHA, run, image digest, durable
event identity, snapshot/incident IDs and report versions. Ownership uses the
same `payments` team and `checkout` service/fingerprint but distinct contacts
and capabilities. Different marker strings are content, not tenant authority.

Real canonical builders also produce identical Kubernetes, AWS, Azure, GCP,
repository, commit, workflow-run and image IDs inside separately owned snapshots.
No canonical ID is tenant-prefixed or rewritten. Agent/source authentication
locators intentionally remain distinct globally random values; the corpus does
not manufacture impossible duplicate authentication locators as successful data.

The machine test executes config -> runtime heartbeat/batch -> healthy inventory
-> failed inventory -> checkpoint/change/signal -> incident -> persisted 13C ->
briefing for BOTH owners. Only outbound webhook network transport is replaced.
It asserts real automatic incident IDs and canonical Pod IDs collide across
owners, distinct ORM identities coexist, repeated signals correlate locally,
and later checkpoints do not move the original pin. No manual analysis call is
used on that machine path. The separate lineage corpus intentionally invokes
existing analysis services to compare deterministic evidence before/after B.

## Acceptance-first divergences and bounded repairs

Product was unchanged when the corrected initial corpus ran: **30 passed,
3 failed**. The three failing outcome checks also reproduced on PostgreSQL.
The stronger source-context case then reproduced with a real primary action
whose matching runbook reference was substituted. All final defect assertions
were preserved unchanged across their corresponding product repairs.

| Defect | First semantic divergence | Bounded repair | Permanent reproducer |
| --- | --- | --- | --- |
| D1: outcome ownership | `load_incident_outcome` returned unattested reusable data; profile reuse and save could accept a B outcome with A's coincident incident ID | Apply existing world attestation on owned load/new producer save, reject foreign loaded values, require attestation on profile outcome input; historical decoder binds only after ORM owner check | `test_foreign_outcome_prefetch_rejected_before_historical_profile`; `test_foreign_loaded_outcome_cannot_overwrite_owned_outcome` |
| D2: historical source context | Plain `outcome_source_data` could supply another owner's runbook to an owned historical outcome | Compare source context with the same-tenant durable outcome and outcome ID before historical assembly; no inference from matching public IDs | `test_unowned_outcome_source_cannot_inject_foreign_history` |
| D3: frontend delayed body | Header-time selection check preceded awaited JSON/blob consumption; an intervening switch could release old-tenant data or trigger a download | Recheck the captured selection after body consumption, before returning JSON or creating/clicking the download link | Two `PH-3G` tests in `frontend/test/auth-session.test.mjs`, both failed before repair |

These are three bounded implementation defects, not new authority/schema models.
D1 has two failing manifestations and D3 has two. They are in-memory reuse/client
release failures, not evidence that unauthenticated remote access was possible.
No scoring, root-level classification, candidate admission, temporal rule,
ledger stance, source trust, graph traversal or public identifier changed.

D2 adds one scoped outcome lookup per historical feature-profile assembly when
source data is supplied. The existing bounded historical scan remains bounded;
there is no new global cache or unrestricted scan. A future optimization must
carry authoritative source provenance rather than omit validation.

Fixture corrections are distinguished from product defects: the new corpus
initially used a wrong `whoami` path, omitted required runtime counters, gave
replacement Pods names that did not represent the accepted workload grouping,
attempted duplicate snapshot INSERTs within one tenant when adding history,
requested explicit providers while expecting AUTO fallback, and used the wrong
canonical resolution field. Those mistakes were corrected using actual models;
no product semantics or assertions were weakened to accommodate them. One old
isolated memory test with `session=object()` now supplies the new owned outcome
lookup and actual outcome ID; its historical-pin and runbook assertions remain.

## Route, query and error accounting

Actual registered required-auth routes were re-enumerated. The corpus inspects
real FastAPI dependency graphs; classification alone is not the behavioral proof.

| Domain | Method/path pairs |
| --- | ---: |
| PH3D_TENANT_REQUIRED | 116 |
| MACHINE_BOUND | 9 |
| TENANT_CONTROL | 7 |
| SECURITY_GLOBAL | 9 |
| PUBLIC | 2 |
| UNKNOWN / deferred | 0 / 0 |
| Total | 143 |

The historical 104 + 12 = 116 reconciliation remains exact. The twelve former
machine administration deferrals are enrollment-token creation; agent list,
detail, health, revoke, plugins and cloud status; source create, list, detail,
patch and doctor. PH-3E already bound all of them; PH-3G adds none or removes none.
Eight agent/enrollment paths and one verified provider callback remain machine
bound, not human-header-selected.

The bidirectional IDOR corpus compares the SAME requested ID before and after a
foreign-only row is inserted: exact 404 status and body remain equal for incident
detail/signals/status, briefing, latest causal analysis, operational context,
ownership impact, response plan, outcome and Copilot creation. Separate actual
report/export/child mutations, identity override DELETE, agent GET/revoke and
provider-source PATCH checks preserve the foreign row. Human and fixed-service
unauthorized tenant selection is 403; missing human selection is 400; invalid
machine authority is 401. Membership revocation retains valid authentication
and unaffected B membership. Disabling a tenant retains data but denies effects.

Repository inventory: **171 Session-typed entry points, 153 explicit tenant
arguments, 18 classified exceptions, zero ordinary unscoped entries**. The
exceptions are exactly:

- Machine derivation: `enroll_agent`, `authenticate_agent`, and
  `load_change_source_for_authentication` (digest/digest/source-locator equality).
- Security global: six named-credential and three session repository functions.
- Tenant control: add tenant/membership, list active subject tenants, add/load
  service binding, and list binding tenant IDs (six functions).

The exact exception names, actual route list and all 12 outbound LLM callsites
are emitted by `test_tenant_adversarial_inventory.py`; additions fail the set
reconciliation rather than being silently accepted. Existing structural tests
still audit each named owned SQL expression. The sole legacy `.query()` path is
`load_topology_snapshot`, with its explicit tenant filter before ID lookup.
The only raw driver SQL in product is schema bookkeeping in strict
`adopt_current_schema`; there is no ambiguous raw tenant-domain SQL path.

Measured direct ORM accounting: 75 named modern SELECT/UPDATE/DELETE expressions
= 72 tenant-scoped + 3 exact authentication derivations. The separately audited
legacy topology query adds one scoped expression: 76 total, 73 scoped, 3
classified auth derivations, 0 deferred/ambiguous. Generic `tenant_get` is
separately validated and is not misleadingly counted as one named-model SELECT.

Representative actual implementations (not post-filtering):

| Operation | Existing implementation and proof |
| --- | --- |
| GET | `tenant_get`: `WHERE model.tenant_id = owner AND local_primary_key = id` under `no_autoflush`; same Session A/X, B/X, A/Y, B/Y remains four objects |
| LIST / pagination | `list_snapshots`: tenant WHERE, collected_at DESC, LIMIT/OFFSET; interleaved newer B records do not consume A's offset/limit |
| Filter/search | incident status/severity/namespace, ownership service/scope and source-delivery selectors are added to tenant-qualified SQL, never merged result sets |
| COUNT / aggregation | report actions loaded by tenant + report, then counted; tenant report/version and override upsert/list counts remain independent |
| LATEST | `latest_causal_analysis`: tenant + incident filters before generated-time ordering/limit; stronger B world cannot supply A's latest RCA |
| Mutation | scoped load + `tenant_commit` checks every new/dirty/deleted object; attempted mixed A/B commit rolls back without altering B |
| Parent | `_PARENTS` validates tenant + local ID for scalar, JSON and polymorphic references; foreign-only parent is absent; report URL parent and child are additionally checked |

The absence of physical FKs is not hidden: application writer validation is the
accepted boundary, not arbitrary SQL protection. Full namespace tests exercise
all 25 tenant-local PKs and all 17 formerly-global business uniqueness rules on
both engines, including same-tenant rejection, A updates/deletes, and safe
downgrade refusal. New tests add actual-builder/native inputs and end-to-end
effects rather than claiming a 404 alone proves storage coexistence.

## Storage and migration authority

Current schema: **43 tables; 38 tenant-owned, all NOT NULL/no tenant default**;
25 composite tenant-local PKs + 3 global auth locators + 10 global random owned
PKs; zero ambiguous partition entries; no physical FKs. The five remaining
tables are tenant control/security. Existing column/constraint inventory remains
771 columns, 68 PK columns, 344 indexes (335 nonunique/9 unique), and 14 unique
constraints. No migration, ORM schema, uniqueness rule, auth digest or locator
was changed in PH-3G. One head: `0008_tenant_scoped_identity_namespace`.

Migration acceptance runs existing immutable 0001–0008 against disposable engines:
fresh chain; populated 0007 -> 0008 comparing every owned-table field; clean
0008 -> 0007 -> 0008; behind-0007 startup rejection; actual cross-tenant duplicate
storage; hostile downgrade failure **before DDL** with exactly
`TENANT_IDENTITY_COLLISION_PREVENTS_DOWNGRADE`; unchanged rows and revision after
refusal; PostgreSQL injected transactional-DDL rollback. Enrollment max-use
concurrency and failed agent INSERT rollback are included. This is not a general
race-freedom or PH-10 concurrency claim.

Primary database acceptance uses only task-created `topo-ph3g-acceptance-20260831`,
image `postgres:16`, ID
`62eb8c34f32cf4c62b82c4f11f0c12c39b56d30e62a0896cd78a6d4bd68f600e`,
port `127.0.0.1:55437`, database `ph3g_acceptance`. Docker inspection proves
tmpfs `/var/lib/postgresql/data`, `Mounts=[]`, no persistent volume. Test-only
trust authentication is loopback-confined, not a deployment recommendation.
Helpers create/drop uniquely named disposable databases; SQLite uses temporary
files/in-memory engines. After all tests completed, the exact container ID above
was reverified against its name, image, empty mounts and tmpfs configuration,
stopped and removed. `docker ps -aq --no-trunc --filter id=<exact-ID>` returned
no container. Its disposable tmpfs data was discarded; no persistent volume or
user database was removed.

## World-model, history and 28-family acceptance matrix

One incident world is derived from an owned row and the unchanged canonical
entities/relationships inside that snapshot. Reuse requires the existing private
nonserialized attestation recursively on child models. Foreign entity/edge
insertion, JSON roundtrip without authority, metadata lookalikes, foreign RCA,
outcome, response plan, profile and historical-intelligence inputs fail before
downstream assembly. Private Python authority is not constructible by request
JSON. Equal public IDs alone never grant ownership.

RCA comparison preserves exact candidate audit, hypothesis order, scores,
confidence semantics, supporting/contradicting/missing evidence, graph nodes/
edges, analysis ID and snapshot ID before/after a complete B world. Missing A
source/provider evidence remains absent rather than becoming support or
contradiction from B. No semantic field is normalized away. Automatic incident
pins remain fixed after later A/B observations; foreign/future checkpoint
rejection remains covered by lifecycle and PH-3F world-model regressions.

An exact matching foreign historical case exists before the current tenant has
any history: matches remain empty. Adding its own case produces only that case,
in both directions. Foreign response/history prefetch fails. The same owned
lookup applies to recommendation/recovery/predeployment assembly; their pure
reasoning functions are not independent authentication entry points. Their
upstream repositories/parent checks and complete regression suites remain the
boundary, not a new tenant-aware rewrite of those algorithms.

The matrix distinguishes direct adversarial scenarios from shared-invariant
proof. Shared proof is not a claim that a nonexistent source/API was exercised.

| # | Family | Independent evidence / retained shared proof |
| --- | --- | --- |
| 1 | Kubernetes canonical | Actual TC-1 UID builder, equal owned nodes; actual two-agent Pod path |
| 2 | AWS canonical | Actual account/region/native builder equal nodes; real submitted cloud inventory persistence |
| 3 | Azure canonical | Actual full-resource-ID builder equal owned nodes; shared owned snapshot/resource namespace and existing connector regressions, no live Azure claim |
| 4 | GCP canonical | Actual full-resource-ID builder equal owned nodes; shared owned snapshot/resource namespace and existing connector regressions, no live GCP claim |
| 5 | Git repository | Actual provider repository builder; same repository source event/artifact inputs |
| 6 | Git commit | Actual repository-scoped SHA builder; same SHA real lineage admission |
| 7 | CI/workflow | Actual Actions run builder and durable provider lineage fixture; no invented CI graph source |
| 8 | Container image | Actual digest builder; equal immutable artifact identity in RCA worlds |
| 9 | Kubernetes graph IDs | Real agent inventory -> declared/derived graph -> fixed pin; foreign child rejection |
| 10 | Cloud graph/parents | Real AWS submitted inventory with equal native IDs; Azure/GCP parent linkage supported by shared owned-graph invariant and connector regressions |
| 11 | Agent runtime/snapshot | Both authenticated pipelines; equal sensor/runtime metadata, distinct bound authority, tenant-qualified persistence |
| 12 | GitHub graph/evidence | Same durable source/artifact/provider facts, exact before/after RCA ledger; missing producer cannot borrow B |
| 13 | Image graph | Same digest and requested reference; no foreign lineage completion |
| 14 | Network topology | Real runtime dependency inputs; graph child rejection; shared owned graph plus unchanged network regressions |
| 15 | Resolution/override | Actual identical override target upsert remains separate; A DELETE leaves B active; resolution storage composite-PK proof |
| 16 | Kubernetes signal/fingerprint | Real observed failure, repeated signal dedupe, automatic same incident ID in two owners |
| 17 | Normalized change | Real automatic checkpoint diff creates owned ChangeRecords in each machine world |
| 18 | Durable event/link | Real source normalization, equal event identity, local links/ledger; namespace PK/business-key tests |
| 19 | Source/delivery | Separate authenticated sources, same delivery key/body, same-owner replay; invalid auth no delivery/domain effects |
| 20 | Cloud storage | Real both-agent account/VPC writer and namespace collision tests |
| 21 | Runtime storage | Real heartbeat/dependency/process writers with identical metadata; composite key and business-key collision tests |
| 22 | Incident/orchestration | Real equal failure-builder incident ID, local correlation, fixed pins; same Session four-record update/delete/rollback |
| 23 | Analysis/hypothesis/evidence | Real 13C before/after hostile world comparison; exact stance/score/support preservation |
| 24 | Response/recommendation/recovery/predeployment | Direct response-plan/history reuse attacks; remaining IDs supported by shared 25-PK/parent/query invariants plus full domain regressions |
| 25 | Explanation/investigation/report/outcome/memory | Real report versions/child/export checks; fixed outcome/source reuse; real local/foreign history; outbound contexts |
| 26 | Ownership fingerprint | Same entity/service/team fingerprint, different contacts/capabilities, actual resolved context remains local |
| 27 | Approval/execution/webhook keys | Real tenant endpoint dispatch; dormant approval/execution storage rules supported by all-17 business-key and full dormant regression corpus; no executor/claim loop invoked |
| 28 | Secret/content digest | Independent provider signatures, actual credential-domain rejection; auth digest uniqueness tests remain global, business digests tenant-qualified |

These are 28 independently accepted mappings after the completed gates below,
not a restatement of the previous PH-3F document's labels. Shared portions
are families 3/4/10/14/15/24/27/28 as expressly bounded in the table; raw digest
computation, dormant control storage and unavailable provider transports are not
misrepresented as live end-to-end provider experiments.

The accepted PH-3F classification for each row is `FULLY_TENANT_SAFE`, except
families 16, 17, 26 and 28, whose exact classification is
`DIGEST_COMPUTATION_SAFE_WITH_TENANT_SCOPED_STORAGE`. PH-3G independently retains
that distinction. Rows 3/4/10/14/15/24/27/28 have a
`SUPPORTED_BY_SHARED_INVARIANT` component, explicitly named in their evidence
cell; the other twenty rows have direct adversarial scenarios. This does not
turn an unexercised transport into a passing integration. The shared proof is
the accepted owned-snapshot attestation, tenant-qualified storage/query/parent
boundary and tested uniqueness partition, not similarity of provider labels.

## Background, caches and outbound context

Audited production orchestration: continuous failure/topology binding,
checkpoint persistence and reconciliation, incident orchestration, agent snapshot
ingestion, provider ingest/replay, automatic causal persistence and webhook
delivery. Work carries explicit owner with local IDs or derives it from the
verified machine root; no object-ID-only tenant work queue is introduced.
No process-global cache of tenant-owned customer truth was found. Per-request
graph maps are snapshot-local; explanation cache is a scoped durable query.
Global configuration/policy dictionaries are not customer caches. Exports are
response bytes, not a shared on-disk filename namespace.

The six-module Session-entrypoint audit measured 18 functions: 16 require an
explicit tenant and two derive it from their machine root. The exact functions
are continuous lifecycle `bind_signal_to_incident_topology`,
`_publish_incident_created`, `_attach_causal_analysis`, `_complete_automatic_analysis`,
`process_failure_signal`, `reconcile_pending_incidents_for_checkpoint`,
`ingest_failure_signal_batch`; `incident_orchestrator.orchestrate_signal`;
`agent_snapshot_ingest.persist_agent_snapshot` (authenticated agent owner);
checkpoint `latest_checkpoint_record`, `latest_checkpoint_at_or_before`,
`persist_topology_checkpoint`; source ingest `_existing_delivery`,
`ingest_change_source_webhook` (verified source owner), `replay_dead_letter`;
webhook `deliver_event_to_endpoint`, `publish_event`, `publish_event_safely`.
Object-ID-only tenant-owned work in this audited chain: zero.

The optional-owner argument scan found no repository or security function with
a defaulted tenant argument. The only two service matches are
`auth_api_credential_service.credential_view` and `credential_created_view`:
their optional value serializes an already-authorized credential's binding;
neither selects a tenant or queries tenant-owned domain data. All three removed
unowned-machine marker spellings have zero production references. The nullable
human selector is validated by membership, while service and machine authority
still derive from their persisted bindings, never from that optional selector.

All **8 centralized LLM callers + 4 legacy Groq branches** are enumerated from
actual AST calls. **24 new captured SDK-boundary scenarios** exercise both
tenants across briefing, explanation, Copilot, investigation planner, report,
history, response intelligence, read-only dormant readiness, and four Groq
variants. Full real context construction, filtering, evidence selection and
sanitization runs before only the outbound SDK transport is replaced. Transport
failure exercises controlled fallback. Each capture requires its own marker and
zero foreign markers, in both directions. No live LLM call, fabricated AI
evidence, or execution authority is involved.

## Frontend and CLI

Browser auth gate precedes tenant-list fetch and domain mount. Multiple tenants
require selection; a sole accessible tenant may be selected in the UI but is
still checked server-side. Non-secret selection is memory-only. Central requests
discard call-site tenant header overrides, preserve cookie/CSRF transport and
use `cache: no-store`. Switch remounts tenant-owned state. The new body-completion
check closes the late JSON/blob release race. Tenant 403 clears only that
tenant selection, not authentication; generic 403 remains forbidden; 401 expires
authentication. Downloads use the same guarded fetch/blob path. No browser raw
credential/localStorage/sessionStorage persistence was added.

CLI global `--tenant` overrides profile `tenant_id`; it does not select the first
tenant. `TopoClient` sends the explicit header. Fixed service binding remains
server authority; a conflicting selector is 403. No selector is required for
bound service access. Keyring/environment credential custody is unchanged;
401 and 403 remain separate CLI exception/exit categories. Full CLI tests run
even though CLI product files are unchanged.

## Custody (before = after; final recheck passed)

Committed Git blob bytes are canonical for immutable migration text. No LF/CRLF
normalization or rebaseline was performed. All 0001–0008 diffs are empty.

| Migration | Canonical SHA-256, identical before and after |
| --- | --- |
| 0001 | B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD |
| 0002 | DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92 |
| 0003 | 907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F |
| 0004 | D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3 |
| 0005 | 14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333 |
| 0006 | D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728 |
| 0007 | 8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84 |
| 0008 | 9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7 |

Protected binary artifacts use actual file bytes, no normalization:

- Developer DB V2 `backend/data/topo.db`:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
- Frozen LINEAGE `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

Each binary value above is both the before and final after value. Both files
remain unchanged. The final canonical-blob check also asserted all eight exact
migration hashes, empty migration diffs, and absence of migration 0009.

## Final verification results

| Check | Observed result |
| --- | --- |
| New PostgreSQL corpus, initial repaired expansion | 39 passed, 2 warnings, 156.20s; subsequent added cases included in final full suite |
| New SQLite expansion + memory | 69 passed, 2 warnings, 37.45s; before final two added cases |
| Final new SQLite adversarial corpus | 49 passed, 2 warnings, 43.24s |
| Frontend tests after body repair | 85 passed, 0 failed, 0 skipped |
| Frontend typecheck | Exit 0 |
| Frontend lint | Exit 0; 11 existing warnings, 0 errors |
| Frontend production build | Exit 0; compilation, TypeScript and 14 static pages completed |
| Full CLI / compile | 70 passed, 5.41s / exit 0 |
| Full agent / compile | 15 passed, 5.40s / exit 0 |
| Full evaluation / compile | 917 passed, 3 skipped, 114.67s / exit 0 |
| SEC-1 tests / tracked scan | 8 passed, 0.12s / exit 0, no findings |
| Full backend SQLite / compile | 1313 passed, 148 skipped, 2 warnings, 756.83s / exit 0 |
| Full backend PostgreSQL-enabled | 1459 passed, 2 skipped, 2 warnings, 1889.25s; exit 0 |
| Focused agent/provider + source-file mutations | 45 passed, 1 warning, 45.93s |
| New-file secret scan | 5 files, 0 findings, exit 0 |
| Final custody / diff check / cleanup | Unchanged / exit 0 / exact task container removed |

Final SQLite receipt module counts (included above, not extra test totals): new
acceptance 16, new route attacks 7, new static inventory 2, new outbound LLM
captures 24 = 49. The unchanged Truth Contract modules passed: canonical identity
12; relationship provenance 24; temporal semantics 29; causal evidence ledger
50; confidence semantics 46. The unchanged GitHub Actions/build-lineage module,
including its preservation guards, passed 87. Namespace migration/collision
module: 53 passed and 54 PostgreSQL-related skips in the SQLite-only run.
The PostgreSQL-enabled receipt includes all 49 new adversarial cases passing,
106 namespace cases passing with one SQLite-only skip, 41 PostgreSQL runtime
compatibility cases passing, and 16 database migration operations cases passing.

The initial restricted-network frontend build failed solely fetching existing
Google Fonts (Geist, Geist Mono, Roboto Slab). Authorized retry fetched those
build dependencies and completed; no font workaround or source change was made.
The evaluation skips are the existing Windows symlink privilege limitations.
The SQLite-only run skips 146 PostgreSQL-gated cases and two assertions that
specifically require PostgreSQL transactional DDL. The PostgreSQL-enabled full
run is the required primary-engine proof, not a waiver of those 146 cases.
Its only two skips are explicitly `[sqlite]` variants of PostgreSQL transactional
DDL tests in `test_machine_tenant_migration` and `test_tenant_identity_namespace`;
the corresponding PostgreSQL variants passed. No PostgreSQL case was skipped in
the PostgreSQL-enabled run.
The backend warning is existing Starlette/httpx deprecation; the new duplicate
same-Session attack also intentionally produces SQLAlchemy's identity-conflict
warning before the expected IntegrityError. No test is excluded for warnings.

The first full SQLite run collected the new canonical-field typo before it was
corrected: 1 failed, 1312 passed, 148 skipped (711.06s). Its failure was the test's
nonexistent `snapshot_entity_id` attribute, not a different product failure.
The first full PostgreSQL-enabled run had exactly the same already-corrected
collected assertion: 1 failed, 1458 passed, 2 skipped (1464.01s).
The final full runs use the actual `CanonicalIdentityResolution.resolved_entity_id`
assertion, with no product or existing regression edits for that correction.

Final backend JUnit receipts are task-local `%TEMP%/topo-ph3g-backend-sqlite-final.xml`
and `topo-ph3g-backend-postgres-final.xml`. Evaluation/provider/acceptance-first receipts
also use `topo-ph3g-*` temporary names. They are not frozen experiment artifacts.

## Files and final accounting

Final verified task scope: three product files, six test/fixture files, one document;
no migrations, evaluator/workflow/agent/CLI product or OTHER changes.

- Product: outcome repository, incident-memory profile boundary, frontend central client.
- Existing tests: historical memory fixture; frontend auth/tenant race tests.
- Created tests: four `test_tenant_adversarial_*.py` files.
- Created document: this closure record.

Final exact Git state, full-suite results, the 163-item reconciliation and the
decision follow. No schema, identity, authentication architecture or causal
semantic redesign was needed to close the three bounded defects.

## Completion-request reconciliation

Number ranges below correspond exactly to the architect's 163 requested report
items. All final gates have completed.
Behavioral evidence refers to the actual corpus and unchanged regression tests
described above, not merely a route label or signature audit.

| Item(s) | Evidence / answer |
| --- | --- |
| 1 | PH-3A–F adversarial acceptance; three bounded boundary repairs, no feature/schema redesign |
| 2 | Accepted starting main commit `635306b7a9cdf4f183b4d6f4531f9acbfa8b80fa` |
| 3 | `security/ph-3g-adversarial-tenant-acceptance-v1` |
| 4 | PASS_PH3_CLOSE |
| 5–8 | Product changed YES: 3 product files; 6 test/fixture files; 1 document |
| 9–11 | Migration created NO; one Alembic head, `0008_tenant_scoped_identity_namespace` |
| 12–19 | The eight canonical before/after migration SHA-256 values are in the custody table |
| 20 | Existing migration changes NONE; canonical committed representation is authority |
| 21–27 | 43 tables; 38 owned; 38 owned NOT NULL; 25 composite tenant-local PKs; 3 global auth locators; 10 global random owned PKs; 0 ambiguous table/key classifications |
| 28–34 | 143 routes = PUBLIC 2 + SECURITY_GLOBAL 9 + TENANT_CONTROL 7 + TENANT_REQUIRED 116 + MACHINE_BOUND 9; UNKNOWN 0 |
| 35–39 | Real A/B human isolation, AB switching, AdminNoB denied, AB A-membership revocation without logout/B denial, disabled tenant denied without deleting data |
| 40–42 | Service A/B fixed binding works without header; conflicting header is 403; foreign incident/object access under its own binding is absent, not a tenant switch |
| 43–47 | Both real agents inherit enrollment owner; equal cluster/namespace/workload metadata; forged tenant metadata/header ignored as authority; revoked/disabled credentials denied; both actual machine pipelines produce only owned records |
| 48–52 | Both real source records bind server-side; same repository/body/delivery metadata; HMAC verified before invalid JSON parsing; invalid signature creates no delivery/event; same-owner replay deduplicates without consuming the other source's delivery |
| 53–55 | Bidirectional GET and mutation matrices, exact absent/foreign 404 body equality; owned parent succeeds, foreign parent/child fails; existing scalar/JSON/polymorphic parent guard corpus retained |
| 56–60 | Scoped lists and searches; local report/version/override counts; actual captured pagination SQL has WHERE before ORDER BY/LIMIT/OFFSET; latest analysis/topology selected inside owner, never globally then filtered |
| 61–62 | PASS on SQLite and PostgreSQL: all 25 local PK collision families and all 17 formerly-global business uniqueness rules; new native-builder/world/machine cases supplement those persistence tests |
| 63–65 | Same Session A/X, B/X, A/Y, B/Y are four objects; A update/delete and mixed-owner rollback preserve B; same-tenant duplicate fails; global auth locator/digest collisions remain rejected |
| 66–69 | Equal incident IDs coexist; actual repeated failures correlate per owner; current/old/future checkpoint tests preserve time semantics and original pins |
| 70–72 | Foreign child entity/edge, forged metadata and serialized lost authority rejected; prefetched graph/RCA/outcome/plan/history/profile attacks rejected before reuse |
| 73–75 | Equal change/event/signal/artifact identities coexist; missing A source/provider lineage remains missing even with a complete supported B chain |
| 76–79 | Candidate audit, full hypothesis/ledger/node/edge collections and confidence semantics compare exactly before/after B; no semantic fields excluded; foreign logical IDs resolve only through owned parents/repositories |
| 80–85 | Owned contacts/capabilities and impact remain local; foreign-only history yields zero matches; response/history prefetch rejected; actual report/outcome export/child/write tests; real own-only webhook dispatch; dormant approval/execution storage/idempotency preserved by collision and domain regression tests without execution |
| 86–87 | 18 exact background Session entry points listed above: 16 explicit owner, 2 verified-machine derivations; object-ID-only tenant work remaining 0 in that audited chain |
| 88–89 | Customer-truth global caches found 0; per-call owned maps and scoped durable explanation reuse remain local; exports are response bytes |
| 90–92 | 12 outbound callsites (8 OpenAI + 4 Groq); 24 real context-construction/captured-transport cases, both owners; foreign marker occurrences 0 |
| 93–94 | Same absent/foreign request status/body; service/human cannot substitute for agent credentials, agent cannot substitute for human; foreign provider signature fails before parsing |
| 95–97 | Required/nondefault owner args, direct owned Session.get, modern SQL predicates, legacy query, unowned marker, machine derivation, global cache, background, raw SQL and export paths audited; unresolved security-relevant bypasses 0; ambiguous raw tenant SQL 0 |
| 98–101 | 28 families independently reviewed and accepted; unresolved 0; ambiguous 0; shared-invariant components explicitly classified |
| 102–106 | TC-1 PASS; TC-2 PASS; TC-3 PASS; TC-4 PASS; TC-5 PASS: new exact-world assertions plus unchanged complete domain/evaluation regressions; exact module counts above |
| 107–108 | Four-level causal semantics changed NO; preservation guard broadened NO |
| 109–112 | PASS: SQLite fresh chain, hostile corpus, clean downgrade/re-upgrade and pre-DDL hostile downgrade refusal |
| 113–119 | PASS: PostgreSQL fresh chain, hostile corpus, real duplicate storage, clean downgrade, pre-DDL hostile downgrade refusal and re-upgrade; behind-0007 startup correctly rejected |
| 120–133 | All completed; exact full-suite/compile/frontend/scanner/diff results and environmental skips are in the verification table |
| 134–139 | Developer DB and frozen LINEAGE before/after actual-byte SHA-256 values in custody section; both final rechecks unchanged |
| 140–144 | Three first divergences / three bounded fixes (D1–D3); five permanent failed-before-fix assertions, unchanged after the corresponding repair; fixture mistakes separately disclosed |
| 145–149 | 0009 required NO; canonical IDs changed NO; fingerprints changed NO; tenant authority changed NO; causal scoring changed NO |
| 150–153 | Created/modified files and exact Git output recorded below after final checks |
| 154–158 | Closure blocker NO; security blocker NO; custody blocker NO; first remaining blocker NONE; all 21 PH-3 closure gates satisfied YES |
| 159–160 | YES, tenant-safe within the explicitly documented supported V1 application boundary; PH-3 closed YES; no DB-superuser/RLS claim |
| 161 | Arbitrary direct/superuser SQL and RLS are outside the application guarantee; future code must preserve explicit tenant APIs; PH-5 RBAC, PH-4 secrets and PH-6 network/customer-data boundary remain separate |
| 162 | If accepted, recommend only PH-4 — Secrets / Credentials / Provider Boundary; do not implement it |
| 163 | Stop after report; no stage, commit, push, Git-history change, 0009 or subsequent block |

### Preservation guard scope

`test_github_actions_build_lineage.py::test_protected_product_contract_implementation_is_unchanged`
was not modified. Its pre-existing RCA AST comparison removes only the accepted
tenant-scope import, keyword-only `tenant_id`, `require_record_owner` expression,
call-site tenant keyword, and `tenant_get` versus old Session.get mechanics.
It does not remove candidate/ranking/evidence/causal code. Other protected files
use exact Git-object comparison. No exclusion was added in PH-3G; causal product,
canonical builders, evaluation code, workflows and TC documents have empty diffs.

### Collision family receipt

The 25 actual composite-PK tables exercised on each enabled engine are:
`topology_snapshots`, `identity_resolutions`, `signals`, `changes`,
`incident_analyses`, `remediation_recommendations`, `recovery_verifications`,
`incidents`, `incident_outcomes`, `ownership_mappings`, `webhook_deliveries`,
`incident_explanations`, `incident_investigation_plans`,
`incident_investigation_steps`, `post_incident_reports`,
`post_incident_report_actions`, `runtime_sensors`, `runtime_dependencies`,
`runtime_processes`, `cloud_accounts`, `cloud_resources`,
`build_artifact_evidence`, `change_events`, `change_entity_links`,
`causal_analyses`. The tests perform real INSERT/SELECT/update/delete, assert ORM
identity separation, reject same-owner duplicates, and attempt downgrade with
colliding rows. They do not accept a 404 as proof that duplicate rows can exist.

### Exact change surface

Created:

```text
backend/tests/test_tenant_adversarial_acceptance.py
backend/tests/test_tenant_adversarial_inventory.py
backend/tests/test_tenant_adversarial_llm.py
backend/tests/test_tenant_adversarial_routes.py
docs/architecture/production-hardening/ph-3g-adversarial-two-tenant-acceptance-closure-v1.md
```

Modified:

```text
backend/app/repositories/incident_outcome_repository.py
backend/app/services/incident_memory.py
backend/tests/test_incident_memory.py
frontend/lib/topo-api.ts
frontend/test/auth-session.test.mjs
```

No OTHER paths. Product delta: 35 added, 6 removed lines across three files.
Tracked diff: 94 insertions, 6 deletions across five files. Untracked additions
are listed separately, because `git diff --stat` does not include new files
until staging (which is forbidden and was not done).

### Commands / environment receipt

All test commands run with each component's existing environment. Backend,
agent, CLI and evaluation compilation used `python -m compileall` over `app`,
`src`, `src` and `evaluation` respectively. Pytest used `-p no:cacheprovider`
because pre-existing cache directories were inaccessible, not to deselect
tests. No cache directory was deleted. The final backend runs use:

```powershell
Set-Location C:\Topo-ai\backend
& .\.venv\Scripts\python.exe -m compileall -q app
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short --junitxml="$env:TEMP\topo-ph3g-backend-sqlite-final.xml"

# In a separate process; only the task-created disposable database is selected.
$env:TOPO_TEST_POSTGRES_URL = 'postgresql+psycopg://postgres@127.0.0.1:55437/ph3g_acceptance'
$env:TOPO_TEST_POSTGRES_CONTAINER = 'topo-ph3g-acceptance-20260831'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short --junitxml="$env:TEMP\topo-ph3g-backend-postgres-final.xml"
```

The PostgreSQL URL is test-only loopback trust, not a production credential.
After cleanup this command requires a fresh disposable container; it must not
be redirected at the developer or frozen LINEAGE database. No environment or
database URL was changed persistently in the repository.

### Final Git evidence

Branch: `security/ph-3g-adversarial-tenant-acceptance-v1`.
HEAD remains `635306b7a9cdf4f183b4d6f4531f9acbfa8b80fa`.

`git status --short`:

```text
 M backend/app/repositories/incident_outcome_repository.py
 M backend/app/services/incident_memory.py
 M backend/tests/test_incident_memory.py
 M frontend/lib/topo-api.ts
 M frontend/test/auth-session.test.mjs
?? backend/tests/test_tenant_adversarial_acceptance.py
?? backend/tests/test_tenant_adversarial_inventory.py
?? backend/tests/test_tenant_adversarial_llm.py
?? backend/tests/test_tenant_adversarial_routes.py
?? docs/architecture/production-hardening/ph-3g-adversarial-two-tenant-acceptance-closure-v1.md
```

`git diff --name-only`:

```text
backend/app/repositories/incident_outcome_repository.py
backend/app/services/incident_memory.py
backend/tests/test_incident_memory.py
frontend/lib/topo-api.ts
frontend/test/auth-session.test.mjs
```

`git diff --stat`: five tracked files changed, 94 insertions(+), 6 deletions(-).
The five untracked additions are separately enumerated above.
`git diff --check`: exit 0, no whitespace diagnostics. New files were also checked
individually with `git diff --no-index --check` against `NUL`: no whitespace
diagnostics (exit 1 denotes the expected new-file content difference).
`git diff --cached --name-only`: empty. No stage, commit, push, branch switch or
history mutation was performed. Existing inaccessible pytest-cache warnings and
Windows CRLF notices are not changes or whitespace failures.

## Final closure decision and limits

All 21 closure gates passed after D1–D3 were repaired and their unchanged
adversarial assertions and full regressions rerun. Authority covers all four
principal domains; ownership covers 38/38 tables; route and repository audits
have no unclassified/unscoped ordinary domain paths; background and machine
propagation are authoritative; tenant-local collision storage is representable;
and no final tested foreign read, write, correlation, pin, graph/evidence/history/
ownership/LLM contamination remains. All 28 identity families have explicit
accepted evidence or their explicitly named shared-invariant component.
Downgrade collision refusal, custody and regression gates passed. No unresolved
closure, security or custody blocker remains.

TopoAI V1 tenant isolation is accepted across supported application and machine
access paths, tenant-owned persistence, tenant-local storage identity,
background propagation, incident/world-model assembly, RCA evidence resolution,
history/memory and outbound AI context.

This does not claim PostgreSQL row-level security against arbitrary direct SQL,
least-privilege RBAC, complete secret custody, network isolation, or full
production readiness; those belong to later production-hardening phases.

Future application code must preserve the explicit tenant APIs and attestation
boundaries. The recommended next block is PH-4 — Secrets / Credentials / Provider
Boundary, inheriting this tenant architecture; it has NOT been started. PH-5,
PH-6, PH-10, CLOUD-V1-1 and execution work were not started. No live Kubernetes,
cloud/SCM provider or LLM experiment was performed. Stop for architect review;
all changes remain unstaged and uncommitted.

PH-3 CLOSED / ACCEPTED
