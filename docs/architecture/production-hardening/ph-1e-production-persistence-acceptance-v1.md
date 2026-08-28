# PH-1E — Production Persistence Acceptance & PH-1 Closure v1

- Status: **ACCEPTANCE CANDIDATE**
- Decision: **PH-1 ACCEPTED / CLOSED**
- Repository: `C:\Topo-ai`
- Branch reviewed: `architecture/ph-1e-production-persistence-acceptance-v1`
- Accepted repository commit: `1b44a92b4ff726d9dd8b81811063d1bc8d408793`
- Accepted repository summary: `1b44a92 test(persistence): validate migration operations and rollback (#64)`
- Scope: architecture acceptance and PH-1 closure only; no product, migration,
  model, database, evaluator, agent, frontend, CLI, or workflow changes

## 1. Executive decision

**PH-1 is accepted and closed.** TopoAI's accepted V1 persistence schema,
representative persistence services, and production migration lifecycle have
been validated against PostgreSQL 16.15 in a controlled disposable
environment. PostgreSQL managed through Alembic is the production persistence
baseline for continued V1 hardening.

This is an internal architecture acceptance statement, not a claim of full
production or customer readiness. It does not claim support for every
PostgreSQL version, locale, managed service, or deployment topology. It does
not prove high availability, zero-downtime upgrades, universal concurrency
correctness, automated backups, tenant isolation, secure secret storage, or a
complete customer-data boundary.

No accepted-state fact contradicts PH-1 closure. Remaining risks have explicit
owners in PH-2 through PH-10 and do not require keeping the persistence-
foundation program open.

## 2. Accepted repository state and evidence custody

The reviewed PH-1 history is:

| Block | Accepted merge commit | Accepted result |
|---|---|---|
| PH-1A | `6f849af` — `docs(architecture): define production persistence migration contract (#61)` | persistence inventory and migration contract accepted |
| PH-1B | `b937b46` — `feat(persistence): establish alembic schema authority (#62)` | Alembic authority and immutable 0001 accepted |
| PH-1C | `c5fd921` — `test(persistence): validate postgres runtime compatibility (#63)` | real PostgreSQL 16 compatibility accepted |
| PH-1D | `1b44a92` — `test(persistence): validate migration operations and rollback (#64)` | production migration operations accepted |

Current custody facts:

| Artifact | Accepted SHA-256 |
|---|---|
| `backend/alembic/versions/0001_current_schema_baseline.py` | `B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6` |
| `backend/app/db/models.py` | `5F4872BDA115DA70826327590366A74356D4CA40F74CA7D0CC03FAEA89BA7A4E` |
| `backend/data/topo.db` | `C3A2AB62DC6B8B8C68DEDFD26B858EBB3BB7199323217BE96B7764AEF7821BAF` |
| frozen LINEAGE seed | `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F` |

PH-1E is documentation-only. It does not rerun PostgreSQL, Docker, backend,
evaluation, or agent suites; it consolidates their merged evidence.

## 3. PH-1 objective

PH-1 was required to establish a production persistence foundation that could
support subsequent authentication, tenancy, secrets, RBAC, retention,
operational backup, and concurrency hardening without weakening TopoAI's
historical truth contracts.

The accepted objective was:

```text
one reviewed SQLAlchemy schema
  -> one immutable Alembic history
  -> real PostgreSQL execution
  -> fail-closed revision authority
  -> explicit strict schema verification
  -> preserved SQLite evaluation compatibility
```

PH-1 deliberately did not redesign the domain schema, introduce tenancy,
normalize serialized evidence, add relational cascades, or build a general
database operations platform.

## 4. PH-1A accepted evidence

PH-1A established the complete persistence inventory:

| Fact | Accepted value |
|---|---:|
| ORM tables | 38 |
| columns | 687 |
| single-column string primary keys | 38 |
| integer/autoincrement primary keys | 0 |
| declared foreign keys | 0 |
| check constraints | 0 |
| named multi-column unique constraints | 10 |
| unique column indexes | 9 |
| total ORM index objects | 296 |
| JSON-shaped columns stored as `TEXT` | 59 |
| timestamp-shaped columns stored as `VARCHAR(50)` | 134 |
| SQLAlchemy `DateTime` columns | 0 |
| native SQL enums | 0 |
| server defaults | 0 |

The schema is intentionally denormalized. Graphs, analyses, evidence ledgers,
signals, changes, reports, and configuration fragments remain Pydantic/Python-
validated serialized payloads. Most cross-record references remain
application-enforced strings or JSON arrays.

The initial PostgreSQL transition required no domain semantic rewrite, new
foreign key, JSONB conversion, native enum conversion, TIMESTAMPTZ conversion,
or arbitrary SQLite-to-PostgreSQL data mover.

PH-1A also proved that `Base.metadata.create_all()` was not schema evolution:
the unmanaged developer SQLite database had benign but real drift, while the
frozen LINEAGE SQLite seed exactly matched the accepted 38-table metadata.

## 5. PH-1B accepted evidence

PH-1B made Alembic the production schema authority and created one canonical
revision:

```text
revision = 0001_current_schema
down_revision = None
head count = 1
```

Revision 0001 is a static, model-independent representation of the accepted
38-table schema. It imports no application model and may not be edited,
renamed, regenerated, squashed, or made dialect-dependent.

For non-SQLite deployments, application startup:

- does not call `create_all()`;
- does not execute Alembic upgrades;
- does not stamp revision state;
- does not repair drift; and
- fails closed unless the current revision equals the application's single
  expected head.

Intentional local/test/evaluation SQLite databases may still use explicit
`create_all()` creation. Frozen evaluation databases remain outside Alembic
authority and must never be stamped or upgraded.

Exact existing-schema adoption is explicit and fail-closed. It requires no
existing revision state and exact structural parity across tables, columns,
types, lengths, nullability, primary keys, unique constraints/indexes,
ordinary indexes, foreign keys, and server defaults. Adoption stamps only the
verified revision; it does not repair domain DDL.

## 6. PH-1C accepted evidence

PH-1C measured the accepted implementation against:

- PostgreSQL `16.15` using `postgres:16`;
- UTF8;
- `en_US.utf8` in the accepted measured environment;
- UTC;
- `READ COMMITTED`;
- psycopg 3;
- SQLAlchemy 2.0; and
- Alembic 1.x.

The accepted real-PostgreSQL results include:

- 0001 upgrade and exact schema parity;
- basic ORM write/read for all 38 tables;
- topology snapshot, signal, incident lifecycle and topology-pin persistence;
- change intelligence and provider build-artifact evidence;
- causal analysis with TC-4 evidence ledger and TC-5 confidence semantics;
- cloud, runtime, ownership, outcome, approval, execution, and webhook data;
- exact `TEXT` JSON round trips;
- TC-3 string timestamp behavior and at-or-before snapshot selection;
- realistic deterministic/provider identifiers and `VARCHAR` boundaries;
- Boolean and string-discriminator behavior;
- current unique-index and composite-constraint semantics;
- exact PostgreSQL adoption and drift rejection; and
- disposable downgrade/re-upgrade parity.

Two measured query-portability defects were repaired without schema or model
changes:

1. Nullable incident-outcome ordering now explicitly uses `NULLS LAST`.
2. Lifecycle latest ordering no longer lets missing snapshot timestamps
   outrank real timestamps.

The measured results establish one controlled PostgreSQL 16 baseline. They do
not establish compatibility with every PostgreSQL release, collation, managed
service, replication topology, or workload profile.

## 7. PH-1D accepted evidence

PH-1D validated the production migration lifecycle against real disposable
PostgreSQL 16:

```text
empty database
  -> one migration owner runs alembic upgrade head
  -> strict schema_admin verify
  -> application startup
```

Fresh installation, repeated startup, exact-schema adoption, current-revision
drift detection, missing/unknown/multiple revision handling, credential-safe
connection errors, test-only migration failure, operator interruption,
backup/restore, concurrent application startup, bounded concurrent migration,
and disposable downgrade all passed.

The accepted strict authority states and automation exit codes are:

| Exit | State |
|---:|---|
| 0 | `CURRENT` |
| 10 | `REVISION_MISSING` |
| 11 | `REVISION_BEHIND` |
| 12 | `REVISION_AHEAD_OR_UNKNOWN` |
| 13 | `MULTIPLE_HEADS` |
| 14 | `SCHEMA_DRIFT` |
| 15 | `CONNECTION_ERROR` |
| 16 | `AUTHORITY_ERROR` |

Strict verification detected both an unexpected table and a missing accepted
index while `alembic_version` still claimed `0001_current_schema`.

Accepted regression evidence at closure:

| Suite | Accepted result |
|---|---|
| PH-1B migration | 17 passed |
| PH-1C PostgreSQL compatibility | 35 passed |
| PH-1D operations | 16 passed |
| full backend with PostgreSQL suites enabled | 1,044 passed; one existing deprecation warning |
| evaluation | 912 passed; 3 Windows symlink-privilege skips |
| agent | 15 passed |
| compile checks | backend, evaluation, PH-1D tests, and agent passed |

## 8. Accepted production persistence architecture

```text
Reviewed SQLAlchemy model intent
  -> immutable additive Alembic history
  -> singleton deployment migration owner
  -> PostgreSQL production database
  -> strict revision + structural preflight
  -> revision-only application startup guard
  -> synchronous SQLAlchemy sessions/repositories
  -> persisted TopoAI historical and current state
```

The roles are separate:

- SQLAlchemy models declare current application intent.
- Alembic revisions are immutable production history.
- Deployment orchestration owns migration execution.
- `schema_admin verify` owns strict operational parity verification.
- Application workers only verify that the database is at the expected head.
- Repositories and services continue owning existing transaction and domain
  semantics.

No application worker is a migration owner. No database revision alone is
treated as proof of structural truth.

## 9. PostgreSQL compatibility statement

Accepted internal statement:

> TopoAI's accepted V1 persistence schema, representative persistence
> services, and production migration lifecycle have been validated against
> PostgreSQL 16.15 in a controlled disposable environment. PostgreSQL managed
> through Alembic is the production persistence baseline for continued V1
> hardening.

This statement is intentionally bounded. It does not imply support for all
PostgreSQL versions, extensions, collations/locales, managed providers,
replication modes, failover configurations, or traffic levels.

## 10. SQLite remaining role

SQLite remains supported for:

- local development;
- focused/unit tests;
- deterministic evaluations;
- frozen evaluation seeds;
- isolated fixtures; and
- single-process demonstrations.

SQLite is not the accepted customer production persistence target.
Production-like customer/design-partner environments must use PostgreSQL plus
Alembic unless a later architecture decision approves another production
dialect.

`backend/data/topo.db` remains an unmanaged local developer database with
known drift. It is not a production database, must not be blindly stamped,
and is not automatically migrated to PostgreSQL. If its preservation is ever
required, it needs a backup and separately reviewed schema/data assessment and
export/import procedure.

Frozen evaluation SQLite databases remain byte-identical, receive no
`alembic_version`, and are never migrated or stamped.

## 11. Schema authority contract

Alembic is the sole production schema authority. Success requires:

```text
one reviewed application migration head
AND current database revision == expected application revision
AND exact structural schema parity
```

`alembic current` and application startup prove revision state only. Strict
operational truth is produced by:

```powershell
python -m app.db.schema_admin verify
```

The verifier is read-only, emits deterministic categories, supports
automation through stable exit codes, and does not render credential-bearing
connection errors.

## 12. Deployment preflight contract

Every production deployment must follow this order:

1. Confirm database reachability.
2. Confirm the application repository has exactly one reviewed Alembic head.
3. Inspect the current database revision.
4. Satisfy the backup/snapshot policy for the deployment class.
5. Assign exactly one migration owner.
6. Run `python -m alembic -c alembic.ini upgrade head`.
7. Run `python -m app.db.schema_admin verify`.
8. Require expected revision equality and exact schema parity.
9. Only then roll or start application instances.

Production deployment must not omit strict preflight. A revision-only worker
startup is safe only inside this deployment contract.

## 13. Application startup contract

Non-SQLite startup verifies the database's current revision against the
application's single expected head. Missing, behind, ahead/unknown, or
ambiguous revision state fails closed before the application serves traffic.

Startup does not create, upgrade, stamp, downgrade, or repair PostgreSQL
schema. It intentionally does not perform the complete 687-column structural
comparison on every worker start; that cost and responsibility belong to the
mandatory deployment preflight.

Intentional SQLite startup may continue to create disposable/local metadata
schemas for the explicitly retained SQLite roles.

## 14. Exact-schema adoption contract

Adoption is reserved for a pre-existing schema that has no Alembic revision
and exactly matches accepted metadata:

```text
schema_admin verify
  -> REVISION_MISSING + schema_parity=exact
  -> explicit schema_admin adopt-current
  -> schema_admin verify
  -> CURRENT + schema_parity=exact
```

Adoption modifies only Alembic revision state. It may not add, remove, rename,
or repair a Topo domain object. Existing revision state, drift, ambiguity, or
an unknown schema causes rejection. Adoption is never automatic.

## 15. Schema-drift contract

Revision equality is necessary but not sufficient:

```text
alembic_version == 0001_current_schema
does not imply
live schema == accepted schema
```

Strict verification compares tables, columns, types/lengths, nullability,
primary keys, unique constraints/indexes, ordinary indexes, foreign keys, and
server defaults. Drift returns `SCHEMA_DRIFT` and a deterministic readable
category list.

A drifted database must not be stamped, silently repaired, or considered
healthy for rollout. The operator must investigate and use a reviewed forward
migration, a controlled rebuild, or restoration from known-good state.

## 16. Migration failure and recovery contract

PH-1D measured PostgreSQL transactional DDL using temporary synthetic
migrations outside accepted history:

| Scenario | Measured result |
|---|---|
| failure before DDL | no Topo domain change; revision unchanged |
| failure after transactional DDL | synthetic DDL rolled back; revision unchanged |
| operator interruption after transactional DDL | synthetic DDL rolled back; revision unchanged |

In every invalid/unmigrated state, application startup refused service.

Safe recovery is either:

```text
fix the reviewed migration issue
  -> rerun the forward migration
  -> strict verify
  -> start compatible application
```

or:

```text
restore known-good backup/snapshot
  -> strict verify
  -> run a schema-compatible application
```

This measured behavior is specific to PostgreSQL transactional DDL and does
not claim equivalent rollback semantics for every database dialect.

## 17. Production rollback contract

Revision 0001's downgrade is destructive and exists only to prove migration
correctness on disposable databases. It must never be the routine production
rollback for customer data.

Production rollback options are:

1. Deploy an application version compatible with the already-upgraded schema.
2. Restore a known-good database backup/snapshot.
3. Apply a reviewed corrective forward migration.

Future migrations should prefer backward-compatible expand/contract behavior
where practical. PH-1 does not prove blue/green schema compatibility or zero-
downtime migration behavior.

## 18. Backup and restore evidence

PH-1D used PostgreSQL-native custom-format `pg_dump` and `pg_restore` against a
disposable PostgreSQL 16 database. The measured exercise preserved:

- topology snapshot identity and exact serialized payload;
- signal identity;
- incident identity and exact topology pin;
- causal-analysis identity and exact serialized causal payload;
- change-event identity;
- ownership identity;
- TC-3 ISO timestamp strings;
- Alembic revision state; and
- exact schema parity after restore.

This is a narrow migration-related preservation proof. PH-8 still owns backup
scheduling, encryption, isolated storage, retention, restore drills, RPO/RTO,
cross-region/availability design, deletion consistency, and customer recovery
operations.

## 19. Singleton migration-owner policy

Application workers are never migration owners. PH-1D measured:

```text
two workers + unmigrated database
  -> both refuse; neither creates schema

one migration owner completes upgrade
  -> two workers start
  -> both pass; neither mutates schema or revision
```

A bounded experiment with two independent simultaneous Alembic upgrade
processes produced one success and one conflict; final strict verification was
current and exact. The result reinforces rather than relaxes the policy:

> Exactly one migration owner is permitted per deployment.

PH-1 does not add distributed migration locking. HA migration coordination is
later operational work.

## 20. Immutable migration-history policy

`0001_current_schema` is immutable accepted history. Never edit an accepted
migration to make a later environment pass.

Future product schema changes must use additive reviewed revisions:

```text
schema requirement
  -> new 0002 / 0003 / ... revision
  -> SQLite migration tests where relevant
  -> real PostgreSQL validation
  -> operational rollback analysis
  -> architect review and merge
```

No migration is created without an actual product schema requirement.

PH-1 intentionally did not add `tenant_id` to the 38 current tables. PH-3 is
expected to be the first major schema evolution and must revisit tenant-owned
roots, tenant-derived children, enrollment-token tenancy, shared/owned build
artifact evidence, tenant-aware uniqueness, historical incident access,
provider/account identity, and safe backfill. PH-3 must add reviewed
migration(s); it must not modify 0001.

## 21. Known concurrency defect

PH-1C measured one real PostgreSQL lost update:

```text
two concurrent enrollment-token use-count increments
  -> observed final value 1 instead of 2
```

Classification: **KNOWN CONCURRENCY DEFECT**.

Owner: **PH-10 — Operational Observability + Concurrency + Capacity**.

The same unversioned read-modify-write pattern appears in signal occurrence,
change-source, runtime observation, sensor, and other counters. This does not
prove every such counter is defective; each requires an appropriate audit.

The finding does not block PH-1 closure because schema authority, persisted
representation, migration safety, and representative service compatibility
are established, and the concurrency defect has a later explicit owner. It
does block claims of general multi-writer counter correctness. Security work
must not rely on an unversioned counter being atomic. If PH-2 or PH-4 needs
atomic counter behavior for a security invariant before PH-10, that program
must implement a narrow earlier repair.

## 22. Current security and persistence limitations

PH-1 does not make the database a safe multi-customer production boundary:

- authentication is disabled by default;
- disabled authentication supplies a development admin/operator principal;
- the browser API client sends no bearer/session credential;
- tenant isolation and tenant identity columns are absent;
- `webhook_endpoints.signing_secret` remains plaintext;
- arbitrary webhook headers may contain sensitive material;
- customer/provider credential boundaries are incomplete;
- retention and deletion behavior is not implemented;
- automated operational backup and restore are absent;
- HA/failover and broad capacity behavior are unproven;
- connection-pool/liveness production tuning is incomplete; and
- network and customer-data boundaries are incomplete.

PH-2 must not merely flip one boolean. PH-2A must first define bootstrap,
login/token behavior, browser access, agent/service identity, public health
routes, token lifecycle, failure/recovery behavior, role propagation, and test
bypasses.

## 23. Deferred-risk register

| Known risk | Owner block | V1 gate? | Current mitigation |
|---|---|---|---|
| lost-update counters | PH-10 | YES before design partner | do not claim multi-writer counter correctness; avoid security reliance on unversioned counters |
| plaintext webhook signing secret and sensitive headers | PH-4 | YES | do not treat the database as a safe secret store; restrict real credentials |
| tenant isolation absent | PH-3 | YES | no customer multi-tenancy or customer records |
| authentication default-off | PH-2 | YES | development/evaluation use only |
| minimum authorization/RBAC incomplete | PH-5 | YES | do not claim customer access control |
| network/customer-data boundary incomplete | PH-6 | YES | no production customer-data claim |
| retention/deletion absent | PH-7 | YES | no customer retention or deletion claim |
| backup automation and recovery policy absent | PH-8 | YES for agreed production deployment | manual measured `pg_dump`/`pg_restore` proof only |
| install/upgrade/rollback packaging incomplete | PH-9 | YES | persistence-level runbook only |
| HA, pool tuning, failover, observability, capacity | PH-10 | deployment-dependent gate | bounded initial architecture; no HA/capacity claim |
| broad app/schema compatibility and zero-downtime upgrades | PH-9/PH-10 | deployment-dependent gate | singleton migration and compatible-app/restore/forward-fix policy |

These are frozen ownership assignments, not new implementation tasks in
PH-1E.

## 24. Customer and design-partner gate

PH-1 acceptance alone does **not** authorize real customer/design-partner
infrastructure or customer data to connect.

The minimum remaining hardening program is:

1. PH-2 — authentication;
2. PH-3 — tenant identity and isolation;
3. PH-4 — secrets and provider credentials;
4. PH-5 — minimum RBAC;
5. PH-6 — network and customer-data boundary;
6. PH-7 — retention and deletion;
7. PH-8 — operational backup and restore;
8. PH-9 — install, upgrade, and rollback packaging; and
9. PH-10 — concurrency, observability, and capacity.

CLOUD-V1-1 real EKS validation remains required before V1 evidence claims are
finalized. It validates the existing bounded Kubernetes causal path and must
not reopen broad causal-evidence expansion.

## 25. PH-1 explicit non-claims

PH-1 does not claim:

- full production or customer readiness;
- compatibility with every PostgreSQL version, locale, provider, or topology;
- high availability or failover;
- zero-downtime or blue/green schema upgrades;
- general multi-writer concurrency safety;
- correctness of every read-modify-write aggregate;
- customer tenant isolation;
- authentication default-on or complete RBAC;
- secure durable storage for webhook/provider secrets;
- automated, encrypted, retained, or cross-region backups;
- customer RPO/RTO or restore-drill readiness;
- retention, deletion, residency, or legal-hold behavior;
- production connection-pool, liveness, or capacity tuning;
- arbitrary SQLite-to-PostgreSQL migration;
- JSONB, TIMESTAMPTZ, native enum, or relational-FK modernization;
- a full expand/contract migration framework; or
- permission to connect real design-partner infrastructure.

PH-1 establishes the persistence substrate upon which those controls can now
be added safely.

## 26. PH-1 acceptance verdict

**Verdict: PH-1 ACCEPTED / CLOSED.**

The evidence is sufficient because PH-1A established the exact persistence
contract, PH-1B created one immutable schema authority, PH-1C proved the
accepted schema and representative services on real PostgreSQL 16.15, and
PH-1D proved the required migration, verification, failure, restore, and
multi-instance operational lifecycle.

No accepted evidence requires a model change, edit to revision 0001, or new
migration for current correctness. Remaining security, tenancy, operations,
and concurrency limitations are explicit and owned by later programs.

## 27. PH-1 closure statement

PH-1 is closed. PostgreSQL managed through Alembic is now TopoAI's accepted
production persistence baseline for subsequent V1 hardening. SQLite remains a
development/test/evaluation substrate. The persistence foundation is not
equivalent to full production/customer readiness; authentication, tenancy,
secret handling, customer-data boundaries, retention, operational backup,
packaging, and concurrency hardening remain mandatory later gates.

## 28. Exact next block

The next program is:

```text
PH-2 — Authentication Default-On
```

The exact next block is:

```text
PH-2A — Authentication Surface Inventory + Default-On Security Contract
```

PH-2A must inventory current middleware, default-off and development-principal
behavior, token-hash configuration, route authentication, browser credentials,
agent/webhook/provider boundaries, role propagation, dormant approval/
execution assumptions, public health/readiness routes, test bypasses, and
bootstrap/admin recovery. It must define the default-on transition before any
authentication implementation.

PH-1E does not start PH-2A. Proposed next action:

```text
ARCHITECT REVIEW / MERGE PH-1E
```
