# PH-3F — Tenant identity namespace and world-model integrity v1

## Scope and acceptance boundary

Repository: `C:\Topo-ai`. Branch: `security/ph-3f-tenant-identity-world-model-v1`.
Accepted parent: `910839e04652164436512adbb052a52d7689229e` (PH-3E).

This block separates tenant-local semantic identity from storage identity. It does
not change canonical IDs, source-native IDs, public IDs, fingerprint algorithms,
causal scoring, candidate admission, relevance, lookback, support/contradiction,
blast-radius traversal, or incident-time topology rules. No new tenant authority,
tenant inference, default tenant, machine marker, execution capability, or evidence
source is introduced. PH-3G acceptance is not performed here.

Validation status: PASS within PH-3F scope; ready for architect review. Both
mandatory database engines and complete regression suites finished successfully,
with the explicitly documented platform/engine skips below. This is not PH-3
closure or a claim that PH-3G adversarial acceptance has been performed.

## Storage decision and complete table inventory

There are 43 ORM tables: 38 tenant-owned, 3 tenant-control, and 2 security-global.
All 38 owned `tenant_id` columns remain NOT NULL, without defaults. All 43 primary
keys and all unique rules were audited. There are no physical foreign keys.

For a tenant-local semantic ID, the database/ORM key is `(tenant_id, existing_id)`.
The existing ID string is unchanged. The order is explicit in ORM metadata and
migration 0008; SQLAlchemy can retain A/X and B/X as separate instances in one
Session. There are 25 composite-key tables, 3 retained global authority-locator
tables, and 10 retained global random-storage tables: exactly 38, ambiguous 0.
No surrogate IDs, tables, or canonical ID prefixes were added.

### Twenty-five tenant-local primary keys

| Table | Existing local ID; new PK is `(tenant_id, this column)` |
| --- | --- |
| topology_snapshots | snapshot_id |
| identity_resolutions | snapshot_id |
| signals | signal_id |
| changes | change_id |
| incident_analyses | analysis_id |
| remediation_recommendations | recommendation_id |
| recovery_verifications | verification_id |
| incidents | incident_id |
| incident_outcomes | outcome_id |
| ownership_mappings | ownership_id |
| webhook_deliveries | delivery_id |
| incident_explanations | explanation_id |
| incident_investigation_plans | plan_id |
| incident_investigation_steps | step_id |
| post_incident_reports | report_id |
| post_incident_report_actions | action_item_id |
| runtime_sensors | sensor_id |
| runtime_dependencies | runtime_dependency_id |
| runtime_processes | runtime_process_id |
| cloud_accounts | cloud_account_id |
| cloud_resources | cloud_resource_id |
| build_artifact_evidence | evidence_id |
| change_events | event_id |
| change_entity_links | link_id |
| causal_analyses | analysis_id |

These are persisted source-local, deterministic, snapshot-local, or derived
identities. Even when time participates in a builder, it does not establish a
customer boundary. Storage accepts identical values across tenants and rejects
duplicate values within one tenant. The real service corpus additionally uses
actual existing lineage/event/lifecycle builders, not only synthetic DB rows.

### Thirteen intentionally global owned primary keys

| Table | Global PK | Classification and reason |
| --- | --- | --- |
| agent_enrollment_tokens | enrollment_token_id | GLOBAL_AUTH_LOCATOR_SAFE; opaque enrollment authority record; token_hash remains globally unique |
| topo_agents | agent_id | GLOBAL_AUTH_LOCATOR_SAFE; random agent authority locator; token_hash remains globally unique |
| change_sources | source_id | GLOBAL_AUTH_LOCATOR_SAFE; random source receiver/authentication locator, resolved before tenant authority |
| identity_overrides | override_id | GLOBAL_RANDOM_STORAGE_SAFE; random row locator; target tuple is tenant-local |
| webhook_endpoints | webhook_id | GLOBAL_RANDOM_STORAGE_SAFE; random endpoint record, not an event fingerprint |
| incident_copilot_sessions | session_id | GLOBAL_RANDOM_STORAGE_SAFE; server-generated random conversation locator |
| incident_copilot_messages | message_id | GLOBAL_RANDOM_STORAGE_SAFE; server-generated random message locator |
| change_source_deliveries | delivery_id | GLOBAL_RANDOM_STORAGE_SAFE; delivery row locator; delivery_key is tenant-local |
| change_source_dead_letters | dead_letter_id | GLOBAL_RANDOM_STORAGE_SAFE; random failed-delivery record locator |
| action_approvals | approval_id | GLOBAL_RANDOM_STORAGE_SAFE; random dormant control record; pending_key is tenant-local |
| action_approval_events | event_id | GLOBAL_RANDOM_STORAGE_SAFE; random audit event; sequence tuple is tenant-local |
| execution_intents | execution_id | GLOBAL_RANDOM_STORAGE_SAFE; random dormant transaction locator; approval/idempotency constraints are tenant-local |
| execution_intent_events | event_id | GLOBAL_RANDOM_STORAGE_SAFE; random audit event; sequence tuple is tenant-local |

Random means the inspected builder uses server entropy, not merely a hash of a
customer name. For example, `_source_id` incorporates `uuid4`; it is not changed
into a tenant-dependent authentication locator. These records still require
tenant predicates for ordinary domain access. An accidental random-key collision
fails closed; no writer adopts or overwrites another tenant's record.

The five other PKs remain unchanged: `tenants.tenant_id`,
`tenant_memberships.membership_id`, `service_api_tenant_bindings.binding_id`,
`auth_sessions.session_id`, and `auth_api_credentials.credential_id`.

### Global unique rules removed and tenant rules retained

Ten obsolete global UniqueConstraints are removed. Each exact column tuple below
already has a parallel constraint prefixed with `tenant_id` from migration 0005;
that tenant rule remains, with `uq_tenant_...` name.

| Table | Removed global constraint | Unchanged semantic tuple |
| --- | --- | --- |
| identity_overrides | uq_identity_override_target | cluster_name, namespace, entity_kind, entity_name |
| webhook_deliveries | uq_webhook_delivery_event | webhook_id, event_id |
| incident_investigation_steps | uq_investigation_plan_sequence | plan_id, sequence |
| post_incident_reports | uq_post_incident_report_version | incident_id, version |
| post_incident_report_actions | uq_post_incident_report_action_sequence | report_id, sequence |
| runtime_sensors | uq_runtime_sensor_agent_node_source | agent_id, node_name, source |
| build_artifact_evidence | uq_build_artifact_provider_fact | provider, repository_id, workflow_run_id, run_attempt, image_digest, provider_evidence_id |
| change_entity_links | uq_change_event_entity_link | event_id, entity_id, link_type |
| action_approval_events | uq_action_approval_event_sequence | approval_id, sequence |
| execution_intent_events | uq_execution_intent_event_sequence | execution_id, sequence |

Seven global unique indexes are removed; the corresponding
`ix_tenant_<table>_<column>` indexes retain uniqueness over `(tenant_id, column)`.

| Table | Column | Removed index |
| --- | --- | --- |
| incident_outcomes | incident_id | ix_incident_outcomes_incident_id |
| ownership_mappings | fingerprint | ix_ownership_mappings_fingerprint |
| change_events | event_fingerprint | ix_change_events_event_fingerprint |
| change_source_deliveries | delivery_key | ix_change_source_deliveries_delivery_key |
| action_approvals | pending_key | ix_action_approvals_pending_key |
| execution_intents | approval_id | ix_execution_intents_approval_id |
| execution_intents | idempotency_key | ix_execution_intents_idempotency_key |

All 24 pre-change UniqueConstraints and 16 unique indexes were inspected. After
0008 there are 14 UniqueConstraints and 9 unique indexes. The four other retained
constraints are `uq_auth_sessions_secret_digest(session_secret_digest)`,
`uq_auth_api_credentials_secret_digest(credential_secret_digest)`,
`uq_service_api_tenant_bindings_credential_id(credential_id)`, and
`uq_tenant_memberships_tenant_subject(tenant_id, subject)`. The two other retained
unique indexes are `ix_agent_enrollment_tokens_token_hash(token_hash)` and
`ix_topo_agents_token_hash(token_hash)`. They must not be tenant-partitioned before
authentication derives authority. No digest computation is changed.

Metadata totals: 771 columns unchanged; PK columns 43 -> 68; indexes 351 -> 344
(nonunique 335 unchanged, unique 16 -> 9); UniqueConstraints 24 -> 14; physical
FKs 0 -> 0. Logical reference enforcement, rather than a new broad FK program,
continues through the existing explicit writer guards.

## Twenty-eight-family closure

In the table, `owned graph` means a graph constructed from an owned snapshot row,
not a process-global graph keyed by public ID. `T/local` means the unchanged local
ID in the tenant storage namespace. Remaining acceptance risk for every family is
independent PH-3G adversarial coverage, not an unresolved storage redesign.

| # | Semantic family | Storage / former collision point and resolution | Final classification |
| --- | --- | --- | --- |
| 1 | Kubernetes canonical identity | UID/scope-native canonical value unchanged; equal node IDs live in separately owned snapshots | FULLY_TENANT_SAFE |
| 2 | AWS canonical identity | Account/region/resource-native identity unchanged; owned graph plus T/cloud resource | FULLY_TENANT_SAFE |
| 3 | Azure canonical identity | Subscription/resource-native identity unchanged; owned graph plus T/cloud resource | FULLY_TENANT_SAFE |
| 4 | GCP canonical identity | Project/resource-native identity unchanged; owned graph plus T/cloud resource | FULLY_TENANT_SAFE |
| 5 | Git repository identity | Canonical repository value unchanged; owned graph and tenant-filtered event/artifact records | FULLY_TENANT_SAFE |
| 6 | Git commit identity | Repository plus commit SHA unchanged; no cross-tenant evidence reuse | FULLY_TENANT_SAFE |
| 7 | CI build/workflow identity | Provider/run identity unchanged; T/build evidence and owned graph | FULLY_TENANT_SAFE |
| 8 | Container-image identity | Digest/reference unchanged; owned graph and T/artifact association | FULLY_TENANT_SAFE |
| 9 | Kubernetes graph entity/relationship IDs | Endpoint IDs resolve only inside owned graph; no multi-tenant node map | FULLY_TENANT_SAFE |
| 10 | Agent cloud entity/parent IDs | Submitted native values retained; PH-3E agent authority determines owned snapshot/resource storage | FULLY_TENANT_SAFE |
| 11 | Agent runtime/snapshot IDs | Former global snapshot/runtime IDs now T/local; no payload-selected authority | FULLY_TENANT_SAFE |
| 12 | GitHub repo/commit/Actions/evidence IDs | Former global evidence ID/provider fact now tenant-qualified; native lineage unchanged | FULLY_TENANT_SAFE |
| 13 | Container-image graph IDs | Digest graph nodes remain snapshot-local; no graph merge across owners | FULLY_TENANT_SAFE |
| 14 | Network topology IDs | Host/service/dependency IDs resolve within owned snapshot; T/runtime evidence | FULLY_TENANT_SAFE |
| 15 | Identity resolution/override IDs | T/snapshot resolution PK; random override PK retained; target uniqueness tenant-scoped | FULLY_TENANT_SAFE |
| 16 | Kubernetes event/signal fingerprints | Same digest allowed across tenants; T/signal PK and scoped dedupe | DIGEST_COMPUTATION_SAFE_WITH_TENANT_SCOPED_STORAGE |
| 17 | Normalized change fingerprint/change IDs | Same diff digest allowed; T/change PK and scoped snapshot parents | DIGEST_COMPUTATION_SAFE_WITH_TENANT_SCOPED_STORAGE |
| 18 | Durable change event/link IDs | T/event and T/link PKs; event fingerprint and endpoint tuple uniqueness tenant-qualified | FULLY_TENANT_SAFE |
| 19 | Change-source and delivery IDs/keys | Source auth locator intentionally global; random delivery row plus tenant delivery_key prevents global business dedupe | FULLY_TENANT_SAFE |
| 20 | Cloud-resource storage IDs | T/account and T/resource PKs; equal native resource identifiers remain separate rows | FULLY_TENANT_SAFE |
| 21 | Runtime dependency/process/sensor keys | T/local PKs and T/agent-node-source tuple; status/latest SQL scoped | FULLY_TENANT_SAFE |
| 22 | Incident fingerprint/incident/orchestration IDs | T/incident and T/analysis; fingerprint unchanged, active-window correlation SQL scoped | FULLY_TENANT_SAFE |
| 23 | Causal analysis/hypothesis/evidence/stable IDs | T/analysis; hypothesis/evidence IDs stay local to owned payload; inputs filtered before qualification | FULLY_TENANT_SAFE |
| 24 | Recommendation/response/recovery/predeployment IDs | T/recommendation and T/verification/analysis; request-local derived plans require owned inputs | FULLY_TENANT_SAFE |
| 25 | Explanation/investigation/report/outcome/memory IDs/hashes | T/local derived storage, tenant report/version and outcome/incident keys; owned history profiles | FULLY_TENANT_SAFE |
| 26 | Ownership mapping fingerprints | T/ownership and T/fingerprint; same service label cannot update foreign mapping | DIGEST_COMPUTATION_SAFE_WITH_TENANT_SCOPED_STORAGE |
| 27 | Approval/execution/webhook event/delivery keys | Random authority/audit IDs retained; business idempotency/sequence keys tenant-local; no execution activated | FULLY_TENANT_SAFE |
| 28 | Secret/content digest computation | Digest algorithms unchanged; auth digests retain necessary global uniqueness, customer content/event digests use tenant-scoped stores | DIGEST_COMPUTATION_SAFE_WITH_TENANT_SCOPED_STORAGE |

All 28 have an explicit result; PH3F_IDENTITY_REQUIRED remaining 0; AMBIGUOUS 0.
Mixed families 19/27/28 do not imply their authentication locators were made
tenant-local: the exact per-table and per-constraint distinctions above govern.
Canonical builder signature changes 0; tenant-prefix changes 0. A read-only AST
comparison found all 18 hash/random/digest call expressions in modified product
files identical to accepted HEAD. Unmodified canonical builders remain identical
in Git. This supplements, rather than replaces, semantic regression tests.

## Query, writer, and reference audit

The repository inventory contains 171 Session-typed entry points: 153 require an
explicit tenant parameter. The 18 exceptions are exactly three machine authority
derivations, nine security-global credential/session operations, and six tenant
control-plane operations. Remaining ordinary unscoped domain entry points: 0.

The three intentional machine derivations remain:

1. `agent_repository.enroll_agent`: global enrollment token digest lookup, then
   authoritative enrollment-record tenant binding.
2. `agent_repository.authenticate_agent`: global agent token digest lookup, then
   authoritative agent-record tenant binding.
3. `change_source_repository.load_change_source_for_authentication`: globally
   unambiguous source ID lookup, authenticated receiver, then stored source tenant.

The nine security-global operations are six `auth_api_credential_repository`
entry points (`add_auth_api_credential`, `load_auth_api_credential`,
`load_auth_api_credential_by_digest`, `list_auth_api_credentials`,
`update_auth_api_credential_last_used`, `active_human_credentials`) and three
`auth_session_repository` entry points (`add_auth_session`,
`load_auth_session_by_secret_digest`, `load_auth_session`). The six tenant-control operations are
`add_tenant`, `add_tenant_membership`, `list_active_tenants_for_subject`,
`add_service_api_tenant_binding`, `load_service_api_tenant_binding`, and
`service_binding_tenant_ids`. These are classification descriptions, not new
endpoints or broadened grants.

`tenant_get` now selects the one non-tenant PK column with `local_primary_key`,
then executes `SELECT ... WHERE tenant_id = :tenant AND local_id = :id` under
`session.no_autoflush`. It never mistakes the first composite column for the
public ID. Existing GET/LIST/COUNT/LATEST filters remain explicit SQL predicates;
latest adds ordering within that filtered set. No domain `Session.merge`, global
upsert, or object-ID-only conflict target is introduced. Writers select by tenant
before update/insert, and `tenant_commit` validates ownership and parent links.

The existing `_PARENTS` inventory has 30 table entries and 59 field/reference
paths, including scalar IDs, JSON snapshot pins, and polymorphic analysis IDs.
Pending-parent lookup uses the non-tenant local key plus owner, as does persisted
parent lookup. Existing ownership is never reassigned. Detached/foreign records
are rejected. These guards remain explicit calls, not a hidden Session filter.
The existing structural ORM audit finds 75 direct owned-model SELECT/UPDATE/
DELETE expressions: 72 scoped before execution, 3 exact machine-authentication
derivations, 0 ambiguous. This count excludes generic `tenant_get`, whose own
explicit predicate is shown above. Direct domain `session.get` calls remaining
in production: 0; the remaining calls address security-global or tenant-control
records. No structural audit exclusion was broadened.
The absence of physical FKs is an existing persistence property; this block does
not claim arbitrary direct SQL is subject to application guards or add RLS.

PH-3E route taxonomy is unchanged: 116 human tenant-required (the historical
104 + 12), 9 machine-bound, 7 tenant-control, 9 security-global, 2 public = 143.
Deferred 0, ambiguous 0. No API route, header, principal, membership check, service
binding, machine authority, frontend tenant selector, or CLI selection changes.

## World-model boundary and historical correctness

The model is one tenant per incident world, not tenant-prefixed source-native
nodes in a shared graph:

```text
PH-3B/3E authoritative tenant
  -> tenant-qualified repositories / validated logical parents
  -> same-tenant snapshot row + original snapshot/entity/edge IDs
  -> request-local owned graph, candidate records, evidence and history
  -> existing deterministic RCA / impact / response / outcome services
  -> optional LLM evidence package (already tenant-filtered)
```

`snapshot_from_owned_record(record, tenant_id=...)` checks the ORM row type,
owner, and embedded snapshot ID before constructing a graph. Snapshot loaders,
checkpoint selection, and lineage admission use it. The existing 13C snapshot
constructor explicitly checks the already scoped row owner before deserializing.
It retains the incident pin and existing no-later-than-boundary behavior. There
is no new latest-snapshot fallback. Entity and edge maps remain invocation-local
within the owned snapshot, so equal A/B canonical IDs never join worlds.

Reusable Pydantic service results receive a private `_Ownership(tenant_id)`
attestation through `tenant_world_model.py`. It is a frozen internal object,
not a model field, JSON authority, global current-tenant variable, or client
tenant selector. `tenant_world` explicitly decorates selected repository/service
boundaries. It validates reused inputs before service work, then attests outputs.
Recursive binding rejects a foreign marked child before rebinding anything;
reuse validation rejects an unattested child inserted after construction as well.
Serialized results deliberately lose this attestation and must re-enter through
an authoritative repository/producer rather than be trusted as prefetched data.

Input checks cover reused incident/analysis/context/plan/current-profile/history
values in operational context, response plan, memory, similarity and response
intelligence. Topology enrichment and ownership resolution also reject a foreign
marked graph/entity. Runtime enrichment checks the ORM agent owner. Authenticated
ingestion may bind new, unowned source input under server authority; no caller
JSON can manufacture the internal attestation. Tests attempt a forged private
key, metadata lookalike, serialized round trip, foreign prefetched values, and a
foreign node appended to an A graph.

Tenant filtering occurs before candidate selection, immutable-lineage resolution,
evidence qualification, history aggregation and LLM assembly. A complete B world
does not supply A's missing source or artifact record even when all public IDs
match. Missing foreign-only evidence stays missing; it is not contradiction.
Real A candidate audit, hypotheses, ledger, nodes and edges are identical before
and after B's complete corpus is inserted. TC-1 through TC-5 remain authoritative.

## Caches, background work, exports and LLM audit

Process-global caches holding tenant-owned customer truth found: 0; such cache
implementations changed: 0. Static policy dictionaries and configuration caches
remain global intentionally. Graph indexes, fingerprint maps and similarity
collections are invocation-local. Durable explanation reuse already queries by
tenant and now has tenant-qualified storage identity. No vector/shared-memory
incident knowledge store was added. Reused request-local derived results are
the additional boundary fixed in this block.

Background ingestion, continuous-lifecycle reconciliation, analysis and delivery
consumers carry authoritative `tenant_id` alongside each local object ID. They
use the same scoped repositories. Object-ID-only tenant-owned work remaining in
the audited production call chain: 0. There is no new worker/queue subsystem.
Report/download rendering produces response bytes in memory rather than storing
customer reports under shared local-ID filenames. No tenant export path required
rewriting; no public report ID was changed.

Eight centralized LLM call sites were audited: briefing, incident similarity,
response intelligence, dormant execution readiness (`generate_openai_text`), and
explanation, Copilot, investigation planner and post-incident report
(`generate_openai_structured`). Four existing legacy Groq invocation branches in
the latter four services consume the same scoped context builders. The provider
client and prompts are unchanged. A captured real briefing test sees A evidence,
no B evidence, and one mocked outbound call; outbound foreign evidence count in
that test is 0. Tests do not make live provider calls. This is not a claim that
all adversarial LLM paths have received independent PH-3G acceptance.

## Migration 0008

File: `backend/alembic/versions/0008_tenant_scoped_identity_namespace.py`.
Revision: `0008_tenant_scoped_identity_namespace`.
Down revision: `0007_machine_tenant_binding`. Head count: 1.

The migration freezes its own lists; it does not import mutable ORM metadata.
Before any DDL it rejects NULL ownership on affected tables and prospective
within-tenant duplicate keys. Checks use bounded result queries and SQL grouping;
nullable business tuples preserve ordinary SQL unique-NULL semantics. No UPDATE,
backfill, owner assignment, default tenant, fingerprint rewrite, or source ID
rewrite is part of the upgrade. SQLite batch recreation copies original values.

Downgrade preflights every old PK/unique rule before any DDL. Cross-tenant local
collisions produce exactly `TENANT_IDENTITY_COLLISION_PREVENTS_DOWNGRADE`. No row
is selected as a survivor, renamed, merged or deleted. A clean corpus downgrades
and re-upgrades. Populated tests compare every column in all 38 owned tables
before/after. PostgreSQL injected DDL failure rolls back keys and revision.

Two compatibility details are explicit:

- The required revision string exceeds Alembic's default VARCHAR(32). After
  preflight, PostgreSQL bookkeeping `alembic_version.version_num` becomes
  VARCHAR(64). Strict exact-schema adoption also prepares that width only after
  its existing validation gate. Domain schema/authentication semantics are not
  altered. Downgrade keeps this bookkeeping width because Alembic replaces the
  long current revision after the downgrade callback returns.
- Original SQLite PK constraints were unnamed. Batch migration needs targetable
  names; clean downgrade restores the original single-column keys with explicit
  `pk_<table>` names. Logical/column/uniqueness parity is preserved. PostgreSQL
  restores original `<table>_pkey` names. No historical migration is normalized.

Real PostgreSQL 16 acceptance uses only the task-created loopback container
`topo-ph3f-acceptance-20260831`, cached `postgres:16`, a tmpfs data directory and no
persistent volume. Test helpers create/drop disposable databases. No configured
developer or frozen database is used by migration tests. SQLite tests use temporary
files. Schema-behind 0007 startup rejection remains enforced.

## Preservation and test coverage

New suites are `test_tenant_identity_namespace.py` and
`test_tenant_world_model.py`. Coverage includes:

- Exact 25/3/10 partition, fresh migration/schema parity, populated value equality,
  downgrade/re-upgrade, behind-schema rejection and NULL-before-DDL refusal.
- All 25 composite-PK families on SQLite and PostgreSQL: A/X+B/X coexistence,
  distinct same-Session identity, A update/delete leaves B intact, and safe
  collision downgrade refusal before ALTER/CREATE/DROP/DELETE/UPDATE.
- All 10 removed unique tuples and 7 removed unique-index keys: cross-tenant
  coexistence, same-tenant rejection, downgrade refusal; all intentional auth
  locator/digest ambiguities still fail globally.
- PostgreSQL transactional DDL failure rollback.
- Real same-ID lineage -> 13C durable analysis -> authenticated latest/briefing
  200 for both tenants; ownership differences and captured tenant-only AI input.
- B's matching IDs cannot repair A's missing source/provider evidence; B insertion
  cannot change A's candidate audit, causal structures or evidence semantics.
- Foreign snapshot/child/prefetch/JSON-attestation rejection; foreign checkpoint
  cannot reconcile A; repeated automatic failures dedupe within tenant and never
  move pins; same-ID outcomes and history remain separate.

Existing test adaptations select `(tenant, local_id)` for direct ORM get calls,
assert the new tenant unique rules, and attest mocked producer results explicitly.
Frozen 0007 test metadata keeps historical 0005/0006/0007 assertions meaningful;
tests targeting an old revision are not silently retargeted to a moving head.
The provenance test still asserts a real runtime dependency reference and keeps
its deterministic clock; its agent fixture is now an actual owned ORM agent.

Evaluation changes are limited to disposable DB preparation through 0008 and
five tenant-qualified fixture ORM lookups. No evaluator scoring, grading,
experiment result, evidence qualification or frozen artifact changes. The causal
AST preservation guard is unchanged; no new exclusion, predicate stripping or
allowlist broadening was added. In 13C the only edits are two explicit owner
checks at topology construction, covered by its pre-existing narrow guard rule.

Exact final test results and completion accounting are recorded below.

## Custody

For immutable tracked text, authority is the committed Git blob, as accepted by
the PH-3E custody amendment. Each canonical SHA below is identical before/after.
Working-tree CRLF expansion is separately reported, not a rebaseline. Git diffs
for 0001–0007 are empty; no line-ending normalization was made.

| Migration | Canonical committed SHA-256, before = after |
| --- | --- |
| 0001 | B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD |
| 0002 | DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92 |
| 0003 | 907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F |
| 0004 | D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3 |
| 0005 | 14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333 |
| 0006 | D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728 |
| 0007 | 8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84 |

Working-file byte SHA-256 (also unchanged):

The supplied 0001–0005 byte values correspond to these Windows working files.
The committed/LF values are separately recorded above under the accepted Git-blob
authority rule. Neither representation has been replaced or rebaselined.

```text
0001 B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6
0002 4EB2930BFF89944DA5E9EA24F33B80F170D0F82E40F0AB508A07B2DC6B624460
0003 EAE6BA5CF16A4E68161A710EDFA29172E20C9DBD6F8739ACA981C4A8D4DFAC73
0004 CBCB14FF6C8D70C1A4F4039E5436D039C599EBC842BE8DB333D6CA4ED66A9A05
0005 B60A69B26FB9A1D01DAE0107439BEC5A1C02F95FCABC0E0044F4E7F30F229E4C
0006 9243EF0AFB8E82B6097B803C19A86AF1512BF216D7CE7CEE3AE716086AF6CFE9
0007 C9F32B065E785F231782470BA8AB7C539ED08B5217426A47AAA7E09B2580E9F5
```

Protected binary SHA-256 uses actual bytes, without normalization:

| Artifact | Before = after |
| --- | --- |
| backend/data/topo.db | 0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E |
| evaluation/results/lineage/post-sc4/topo-product-32695735269.db | 9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F |

## PH-3G handoff and limits

PH-3G receives the exact key/constraint and 28-family inventories above, two-engine
collision fixtures, existing human/service/machine authentication fixtures, real
two-tenant RCA/briefing fixtures, unchanged 143-route inventory and 0001–0008
migration chain. Remaining work is independent adversarial acceptance, including
broader route combinations, complex JSON reference reuse, operational concurrency,
and deployment-specific controls; no further foundational namespace redesign is
intended. Application scoping is not a claim of database RLS against arbitrary SQL.

TopoAI is **not declared fully tenant-safe**, PH-3 is **not closed**, and
design-partner readiness is **not claimed** by this block. The next recommended
block is PH-3G — Full Adversarial Two-Tenant Acceptance + Migration/Route/Identity/
RCA Isolation Proof + PH-3 Closure Decision. Do not start it in this task.

## Verification record

All commands were executed locally. Test databases are disposable. Pytest cache
was disabled because pre-existing `.pytest_cache` directories are permission-
restricted; no tests were excluded for that reason. The single backend warning
is the existing Starlette/httpx TestClient deprecation, not an isolation failure.

| Check | Exact final result |
| --- | --- |
| Backend `compileall app` | Exit 0 |
| Full backend, SQLite default | 1264 passed, 148 skipped, 1 warning, 680.17 seconds |
| Full backend, PostgreSQL 16 enabled | 1410 passed, 2 skipped, 1 warning, 1162.38 seconds |
| Evaluation `compileall evaluation` | Exit 0 |
| Full evaluation | 917 passed, 3 skipped, 119.92 seconds |
| Agent `compileall src` | Exit 0 |
| Full agent, explicit pytest summary | 15 passed, 5.44 seconds |
| Agent/provider auth hardening modules | 17 passed, 1 warning, 51.03 seconds |
| Auth-locator collision corpus, both engines | 14 passed, 93 deselected, 1 warning, 78.26 seconds |
| World-model/briefing/memory/response-intelligence focused run | 90 passed, 1 warning, 12.39 seconds |
| Real PostgreSQL backup/restore focused rerun | 1 passed, 7.21 seconds |
| SEC-1 scanner tests | 8 passed, 0.12 seconds |
| Tracked secret scan | Exit 0; 0 findings |
| New-file secret scan | 7 files; 0 findings |
| Frontend / CLI | Not run: neither tree changed |
| `git diff --check` | Exit 0; no output (rechecked at completion) |

The SQLite run collected 1412 cases: 1264 passed and 148 opt-in/engine-specific
cases skipped. These PostgreSQL paths are exercised in the PostgreSQL-enabled
run, not treated as proven by SQLite. The two intentional backend skips under
PostgreSQL are the SQLite parameterizations of PostgreSQL-only transactional DDL
proofs. Evaluation's three skips are existing symlink tests: this Windows token
lacks symlink-creation privilege (WinError 1314); those checks are not claimed as
passed and remain a platform-specific acceptance consideration.

Explicit SQLite regression module counts: tenant foundation 8 passed; domain
ownership migration 10 passed; domain enforcement 55 passed; machine binding
8 passed; new world-model suite 9 passed. New namespace suite under SQLite mode:
53 passed, 54 skipped (53 opt-in PostgreSQL parameterizations plus one
PostgreSQL-only DDL test's SQLite parameterization).

PostgreSQL-enabled exact module counts: new namespace corpus 106 passed / 1
intentional SQLite DDL skip; new world-model suite 9 passed; tenant foundation
8 passed; domain ownership migration 10 passed; domain closure 41 passed; domain
enforcement 55 passed; machine migration 21 passed / 1 intentional SQLite DDL
skip; machine binding 8 passed; database migration operations 16 passed, including
real pg_dump/pg_restore. Total full backend cases: 1412; failures/errors: 0.

The exact disposable container ID
`57d441d9223bf0af103e7b2e5562e58b869e9264d82fafc0cf3707c10ebbb0d8`
was rechecked before cleanup. It used a tmpfs data directory, no mounted persistent
volume, and only loopback port 55436. After the final PostgreSQL run it was removed;
the exact-name container listing is empty. Its disposable database contents are
discarded, not retained for recovery. No protected database or other container
was removed.

Pre-final failures are not hidden: the first complete SQLite implementation run
reported 31 failed, 1206 passed, 130 skipped. These exposed old scalar ORM fixture
lookups, old schema/key assertions and an unowned runtime-agent test double. After
those adaptations, a later SQLite run reported 2 failed, 1261 passed, 148 skipped:
the two new auth fixtures used `secret_digest` instead of the actual column names.
The corresponding PostgreSQL-enabled run reported 5 failed, 1404 passed, 2 skipped:
the same two cases on both engines and an old scalar ORM get in backup/restore.
Those exact tests were repaired, without dropping assertions, and passed focused
reruns before the final complete runs. A separate added negative test rejects an
unowned child inserted into an already owned graph. These pre-final counts are
not the acceptance result.

Representative commands (the PostgreSQL environment here is task-local and does
not configure the product):

```powershell
Set-Location C:\Topo-ai\backend
& .\.venv\Scripts\python.exe -m compileall app
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short

# Only while the disposable acceptance database exists:
$env:TOPO_TEST_POSTGRES_URL = 'postgresql+psycopg://postgres@127.0.0.1:55436/ph3f_acceptance'
$env:TOPO_TEST_POSTGRES_CONTAINER = 'topo-ph3f-acceptance-20260831'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short
Remove-Item Env:TOPO_TEST_POSTGRES_URL
Remove-Item Env:TOPO_TEST_POSTGRES_CONTAINER

Set-Location C:\Topo-ai
& .\backend\.venv\Scripts\python.exe -m compileall evaluation
& .\backend\.venv\Scripts\python.exe -m pytest evaluation/tests -q -p no:cacheprovider --tb=short
& .\backend\.venv\Scripts\python.exe -m pytest scripts/security/tests -q -p no:cacheprovider
& .\backend\.venv\Scripts\python.exe scripts/security/check_tracked_secrets.py

Set-Location C:\Topo-ai\agent
& .\.venv\Scripts\python.exe -m compileall src
& .\.venv\Scripts\python.exe -m pytest -o addopts="" -q -p no:cacheprovider

Set-Location C:\Topo-ai
git branch --show-current
git status --short
git diff --name-only
git diff --stat
git diff --check
```

## Files and source-control evidence

Changed-file categories: 44 existing files modified (20 backend product, 22
backend test, 2 evaluation); 7 files created (1 migration, 2 backend product,
3 backend test, 1 architecture report). Total 51. OTHER paths: none. Workflow,
agent, frontend and CLI diffs: empty. Product change is scoped storage/boundary
plumbing; evaluation change is fixture storage compatibility only.

The following exact `git status --short` paths are also the complete created and
modified file inventory. ` M` means modified, unstaged; `??` means newly created,
untracked. Removing the status prefix from the ` M` rows gives the exact
`git diff --name-only` list. No staged paths exist.

```text
 M backend/app/db/models.py
 M backend/app/db/schema_management.py
 M backend/app/repositories/causal_analysis_repository.py
 M backend/app/repositories/incident_record_repository.py
 M backend/app/repositories/snapshot_repository.py
 M backend/app/repositories/tenant_scope.py
 M backend/app/repositories/topology_snapshot_repository.py
 M backend/app/services/business_impact.py
 M backend/app/services/causal_rca.py
 M backend/app/services/github_actions_artifact_lineage.py
 M backend/app/services/incident_briefing.py
 M backend/app/services/incident_context.py
 M backend/app/services/incident_memory.py
 M backend/app/services/incident_similarity.py
 M backend/app/services/lineage_candidate_admission.py
 M backend/app/services/ownership_resolver.py
 M backend/app/services/response_intelligence.py
 M backend/app/services/response_plan.py
 M backend/app/services/runtime_snapshot_enrichment.py
 M backend/app/services/topology_checkpoint.py
 M backend/tests/domain_tenant_fixtures.py
 M backend/tests/test_causal_candidate_policy.py
 M backend/tests/test_causal_evaluation_budget.py
 M backend/tests/test_causal_hypothesis_projection.py
 M backend/tests/test_causal_relevance_policy.py
 M backend/tests/test_continuous_lifecycle.py
 M backend/tests/test_database_migration_operations.py
 M backend/tests/test_domain_tenant_closure.py
 M backend/tests/test_domain_tenant_enforcement.py
 M backend/tests/test_domain_tenant_migration.py
 M backend/tests/test_execution_transaction.py
 M backend/tests/test_github_actions_build_lineage.py
 M backend/tests/test_incident_briefing.py
 M backend/tests/test_incident_memory.py
 M backend/tests/test_lineage_candidate_admission.py
 M backend/tests/test_machine_tenant_migration.py
 M backend/tests/test_postgres_runtime_compatibility.py
 M backend/tests/test_relationship_provenance.py
 M backend/tests/test_response_intelligence.py
 M backend/tests/test_schema_migrations.py
 M backend/tests/test_source_file_mutations.py
 M backend/tests/test_temporal_semantics.py
 M evaluation/lineage_distractor_robustness.py
 M evaluation/tests/test_lineage_distractor_robustness.py
?? backend/alembic/versions/0008_tenant_scoped_identity_namespace.py
?? backend/app/db/tenant_identity.py
?? backend/app/services/tenant_world_model.py
?? backend/tests/frozen_schema_fixtures.py
?? backend/tests/test_tenant_identity_namespace.py
?? backend/tests/test_tenant_world_model.py
?? docs/architecture/production-hardening/ph-3f-tenant-identity-world-model-integrity-v1.md
```

Tracked `git diff --stat` total: 44 files changed, 310 insertions(+), 194
deletions(-). As usual, that statistic excludes untracked new files. Git status
may warn about the pre-existing inaccessible pytest-cache directories; those
directories were not deleted or modified to suppress the warning.

## Completion accounting: request items 1–170

Ranges explicitly map to the detailed inventories above; they do not omit items.
The verification table contains the completed final runs, not pre-fix results.

| Requested item(s) | Evidence / answer |
| --- | --- |
| 1 | PH-3F only: tenant storage identity and same-tenant world-model boundary |
| 2 | Accepted main `910839e04652164436512adbb052a52d7689229e` |
| 3 | `security/ph-3f-tenant-identity-world-model-v1` |
| 4 | PH-3F PASS / ready for architect review; no PH-3 closure claim |
| 5 | Exactly `backend/alembic/versions/0008_tenant_scoped_identity_namespace.py` |
| 6 | Revision `0008_tenant_scoped_identity_namespace` |
| 7 | Down revision `0007_machine_tenant_binding` |
| 8–9 | One Alembic head, exactly the revision in item 6 |
| 10–16 | 0001–0007 respectively: canonical before/after SHA-256 table in Custody; all equal |
| 17 | Existing migrations changed: NO; empty Git diff |
| 18–20 | 43 ORM tables; 38 owned; 0 nullable owned tenant_id columns |
| 21–26 | All 43 PKs audited; owned partition 25 semantic / 3 global auth / 10 global random; 5 non-domain control/security tables; ambiguous 0 |
| 27–28 | 25 composite PK changes; exact first inventory table |
| 29–30 | 0 surrogates; no list or generation required |
| 31–33 | Canonical ID, tenant ID and fingerprint value rewrites: NO / NO / NO |
| 34 | Physical FKs updated: 0; none existed; logical references remain explicitly validated |
| 35–36 | Audited 24 UniqueConstraints and 16 unique indexes |
| 37–38 | Removed 10 global unique constraints and 7 global unique indexes; exact rules in inventory |
| 39–40 | Global auth/random PKs and 4 other constraints / 2 other unique indexes retained; exact names and reasons above |
| 41 | Retained 10 tenant unique constraints and 7 tenant unique indexes; added 25 tenant composite PKs |
| 42–43 | All 25 local PK families plus 17 business uniqueness rules exercised on real PostgreSQL 16 and SQLite |
| 44 | Same Session holds distinct `(A,X)` and `(B,X)` instances |
| 45 | Tenant-local lookup/update/delete leaves foreign row intact; real repeated lifecycle dedupe stays within tenant |
| 46 | Equal auth locator/digest is still globally rejected; focused 14-test both-engine proof |
| 47 | 28 deterministic/native identity families reviewed |
| 48–75 | Respectively family 1–28 in the complete closure table; each has semantic identity, storage/collision resolution and final classification |
| 76–77 | PH3F_IDENTITY_REQUIRED remaining 0; ambiguous families 0 |
| 78–79 | Same incident ID coexists; equal automatic failure family creates separate owned incidents, repeated signals correlate locally |
| 80–81 | Same snapshot ID coexists; a foreign-only pin/reconciliation target is rejected, not adopted |
| 82–83 | Same entity IDs coexist in owned graphs; foreign child is rejected and no cross-tenant endpoint map exists |
| 84–88 | Event/link, artifact, runtime/cloud, ownership, webhook/idempotency PK and business-key collision corpus; exact families/rules above |
| 89–90 | Single owned graph with original node IDs; no mixed-tenant cache; persisted keys are tenant-qualified |
| 91–92 | Process-global customer-truth caches found 0; global-cache fixes 0; request-local prefetched context checks added |
| 93–94 | Background identity is tenant plus local ID; object-ID-only tenant-owned work remaining 0 in audited call chain |
| 95–96 | Ordinary unscoped domain helpers remaining 0; only the three named machine auth derivations plus security/control operations |
| 97–100 | Real source/provider corpus proves A input/candidate/ledger independence and foreign evidence exclusion before qualification |
| 101–102 | TC-4 semantics and causal scoring changed: NO / NO |
| 103–106 | Memory/history, ownership/impact and outcome/report repository boundaries are tenant-local; equal-ID real outcome/briefing tests and existing regressions |
| 107–108 | 8 centralized + 4 legacy invocation branches audited; captured A briefing contains 0 foreign evidence items |
| 109–111 | Canonical builder signature changes 0; changed-builder list empty; unnecessary tenant prefixes NO |
| 112–116 | SQLite fresh/0007 upgrade, exact parity, clean downgrade/re-upgrade and duplicate-corpus safe downgrade refusal are included in final namespace suite |
| 117–123 | PostgreSQL fresh/0007 upgrade, parity, actual duplicates, clean downgrade, collision refusal and re-upgrade are included in final namespace suite |
| 124 | Startup rejects schema-behind 0007; no auto-stamp or fail-open |
| 125–128 | PH-3B/3C/3D/3E regression modules included unchanged in scope; historical expected schema frozen appropriately |
| 129–130 | Exact full backend and evaluation results: verification table |
| 131–132 | Agent 15 passed; agent/provider authentication modules 17 passed |
| 133–134 | CLI/frontend not run, no changes |
| 135–138 | Compile exit 0; scanner tests 8 passed; tracked/new scans 0 findings; diff check exit 0 |
| 139–141 | Developer DB exact before/after SHA in Custody; unchanged YES |
| 142–144 | Frozen LINEAGE exact before/after SHA in Custody; unchanged YES |
| 145–148 | AuthPrincipal, TenantContext authority, auth_sessions schema, auth_api_credentials schema changed: NO for all four |
| 149–150 | Agent/provider tenant authority and canonical public API ID contract changed: NO / NO |
| 151–152 | Causal preservation guard changed: NO; exclusions neither narrowed nor broadened |
| 153–154 | Exact 7 created / 44 modified paths in Git status inventory |
| 155–156 | Exactly migration 0008 created; 0001–0007 modified NONE |
| 157–158 | Exact Git status paths above; diff name-only is its 44 modified paths |
| 159–164 | Storage, rewrite, world-model, security and custody blockers: none found in implemented scope; first blocker NONE; final regressions passed |
| 165 | Fully tenant-safe platform claim: NO; independent PH-3G remains |
| 166–167 | Persistence identity collision closure: YES; deep RCA/world-model same-tenant integrity: YES within implemented architecture; independent PH-3G remains |
| 168 | Remaining planned PH-3 work: PH-3G independent acceptance only |
| 169 | Recommend PH-3G adversarial two-tenant migration/route/identity/RCA proof and closure decision; do not begin |
| 170 | Stop after PH-3F report; no staging, commit, push, branch/history change, 0009 or next-block work |

PH-3F ACCEPTED / READY FOR ARCHITECT REVIEW
