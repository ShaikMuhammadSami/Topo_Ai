# PH-3B — Tenant Foundation + Membership + Request TenantContext v1

- Status: **IMPLEMENTED — READY FOR ARCHITECT REVIEW**
- Verdict: **PASS**
- Repository: `C:\Topo-ai`
- Branch: `security/ph-3b-tenant-foundation-membership-context-v1`
- Accepted input commit: `0160c4c5bc48ab2741f58c2e556e0994de975502`
- Scope: tenant control-plane foundation only

## Scope and security boundary

PH-3B adds a durable tenant root, human tenant memberships, immutable request
`TenantContext`, fixed single-tenant service-credential binding, bounded
tenant/membership control APIs, and direct-static-bootstrap membership
recovery. It does not tenant-scope existing customer domain persistence.

Authentication, tenancy, and future authorization remain separate:

```text
AuthPrincipal
  -> explicit tenant selection or server-side binding
  -> active tenant and membership/binding validation
  -> immutable TenantContext
  -> PH-3C/3D/3E domain isolation (deferred)
  -> PH-5 permissions (deferred)
```

`AuthPrincipal` remains exactly `subject`, `display_name`, `roles`, and
`authentication_type`. Neither `auth_sessions` nor `auth_api_credentials`
gained a tenant column. Application startup still requires PH-2 authentication
authority but does not require an existing tenant.

## Migration and schema

The additive migration chain now has one head:

```text
0001_current_schema
  -> 0002_auth_sessions
  -> 0003_auth_api_credentials
  -> 0004_tenant_foundation
```

`0004_tenant_foundation` creates only three control-plane tables. It imports no
application models and performs no ALTER or backfill against the existing 40
tables. SQLAlchemy metadata and the migrated schema contain 43 tables and 733
columns with strict parity on SQLite and PostgreSQL 16.

### `tenants`

- Columns: `tenant_id`, `display_name`, `status`, `created_at`, `updated_at`,
  `created_by_subject`.
- Primary key: `tenant_id`.
- IDs: server-generated `tenant:<uuid4>` opaque identities.
- Status: string `active` or `disabled`; no native enum.
- Display names are non-unique metadata.
- Index: `ix_tenants_status`.
- Foreign keys: none, preserving the accepted logical-reference schema style.

### `tenant_memberships`

- Columns: `membership_id`, `tenant_id`, `subject`, `status`, `created_at`,
  `updated_at`, `created_by_subject`.
- Primary key: `membership_id`.
- Unique constraint: `(tenant_id, subject)`.
- Status: string `active` or `disabled`.
- Indexes: subject, tenant ID, and `(tenant_id, subject, status)` active
  resolution.
- Foreign keys: none; application services validate tenant identity and state.

One stable subject may be active in multiple tenants. Adding an existing active
membership is idempotent. Adding a disabled membership reactivates the same
stable membership record. Disable is soft and tenant-scoped; a cross-tenant
membership ID behaves as absent.

### `service_api_tenant_bindings`

- Columns: `binding_id`, `credential_id`, `tenant_id`, `created_at`,
  `created_by_subject`.
- Primary key: `binding_id`.
- Unique constraint: `credential_id`.
- Index: tenant ID.
- Foreign keys: none; credential, active tenant, and creator membership are
  validated by the transactional service.

The binding is immutable in V1. Moving automation requires creating and
verifying a new credential and revoking the old credential.

## TenantContext contract

`TenantContext` is a frozen dataclass with:

- `tenant_id`
- `authenticated_subject`
- `authentication_type`
- `actor_kind` (`human` or `service`)
- `selection_source` (`human_header` or `service_binding`)
- optional `membership_id`
- optional `credential_id`

Human requests select a tenant with `X-Topo-Tenant-ID`. The header is bounded,
shape-validated, and used only as a selector. An active tenant and active
membership for the authenticated subject are resolved together in SQL. Even an
authentication `admin` cannot enter a tenant without membership, and no
single-membership default is inferred.

Named `service_api` requests receive their durable `credential_id` through
request-scoped middleware metadata, not through `AuthPrincipal`. The server
loads the fixed binding. No header is required; a matching header is accepted;
a different header is denied. The caller can never override the binding.

Frozen outward errors are:

- Missing, empty, or malformed required human selector: HTTP 400,
  `TENANT_CONTEXT_REQUIRED`.
- Unknown tenant, disabled tenant, missing/disabled membership, unbound service,
  disabled bound tenant, or service/header mismatch: HTTP 403,
  `TENANT_ACCESS_DENIED`.
- A membership ID absent from an already authorized tenant: bounded HTTP 404.

Unknown and known-but-unauthorized human tenant IDs have identical status and
body. Errors never echo tenant header contents or membership metadata.

## Control-plane APIs

All routes remain `USER_AUTHENTICATED` under the PH-2 middleware. The route
inventory remains complete with zero unknown API routes.

- `POST /api/v1/tenants`: human `admin`; atomically creates the tenant and the
  creator's active membership.
- `GET /api/v1/tenants`: human only; SQL returns only active tenant/active
  membership rows for the authenticated subject.
- `GET /api/v1/tenant-context`: validates human selection or resolves a service
  binding.
- `GET /api/v1/tenant-memberships`: current human tenant context plus `admin`;
  tenant-scoped list only.
- `POST /api/v1/tenant-memberships`: current human tenant context plus `admin`;
  tenant comes only from context.
- `POST /api/v1/tenant-memberships/{membership_id}/disable`: soft-disable in
  the current tenant.
- `POST /api/v1/tenant-memberships/recover`: direct configured static bearer
  plus `admin` only; restores or creates one supplied subject membership.

Named human credentials, browser sessions, and service credentials cannot use
break-glass recovery. A browser session derived from the static bootstrap does
not become direct bootstrap authority. Recovery mutates only membership
metadata and grants the bootstrap caller no implicit tenant or data-plane
access.

The explicit CORS allow-header list adds only `X-Topo-Tenant-ID`; origin,
credential, cookie, and CSRF policies are unchanged.

## Service credential creation

`POST /api/v1/auth/api-credentials` remains the PH-2 authentication control
plane with one additive contract:

- `human_api` creation continues without `tenant_id` and creates no binding.
- `service_api` creation requires `tenant_id`.
- The human creator must retain existing `admin` authority and have active
  membership in the active target tenant.
- Service callers remain forbidden from credential administration.

The credential row is flushed and the binding row is added in the same
SQLAlchemy session and transaction. The raw service secret is returned only
after the combined commit succeeds. A binding failure rolls back both rows and
returns no successful secret response. Credential list/get/revoke metadata may
show the non-secret bound tenant ID for service credentials; human credential
tenant metadata is null and no digest is exposed. Revocation remains PH-2
authority and immediately prevents further authentication; the immutable
binding may remain as historical control-plane metadata.

Pre-PH-3B unbound service credentials remain authentication-valid under PH-2
semantics but receive `TENANT_ACCESS_DENIED` from tenant-context resolution.
They are not auto-backfilled. Operators should create and verify a new
tenant-bound service credential, then revoke the old unbound credential.

## Atomicity and recovery guarantees

- Tenant plus creator membership is one commit. A forced membership insertion
  failure left neither row; a normal retry succeeded.
- Service credential plus fixed tenant binding is one commit. Forced binding
  failures on SQLite and PostgreSQL left neither credential nor binding and no
  usable raw secret escaped; normal retry succeeded.
- Membership create/reactivate and disable each have one clear transaction.
- Direct static bootstrap can create the initial tenant and creator membership,
  then a named human with the same stable subject resolves that membership.
  A different subject receives no membership implicitly.
- Direct static bootstrap can restore one disabled membership after lockout,
  while named human, browser session, and service identities receive 403.

## PostgreSQL and SQLite evidence

PostgreSQL used a disposable `postgres:16` container on loopback with no named
volume and cleanup after the gate. The measured transaction isolation was
`READ COMMITTED`.

- Focused tenant foundation (SQLite): 8 passed.
- Schema/migration module (SQLite): 25 passed.
- PH-2 authentication/session/agent/provider regression bundle: 84 passed.
- PostgreSQL 16 runtime, migration, and PH-3B control-plane acceptance:
  39 passed.
- Full backend: 1,091 passed, 60 skipped.
- Full evaluation: 914 passed, 3 skipped.
- Agent: 15 passed.
- CLI: 67 passed.
- Backend, evaluation, agent, and CLI compile checks: passed.
- SEC-1 scanner unit tests: 8 passed.
- SEC-1 tracked-tree scan: passed.
- Frontend: not run because no frontend product file changed.
- `git diff --check`: passed.

PostgreSQL acceptance covered fresh migration, `0003 -> 0004`, strict schema
parity, behind-schema startup denial, `0004 -> 0003` downgrade, re-upgrade,
tenant and membership lifecycle, human context, fixed service binding, both
atomic rollback invariants, and direct bootstrap recovery.

## Custody evidence

Protected hashes remained byte-identical before and after all mutable gates:

- `0001`: `B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6`
- `0002`: `4EB2930BFF89944DA5E9EA24F33B80F170D0F82E40F0AB508A07B2DC6B624460`
- `0003`: `EAE6BA5CF16A4E68161A710EDFA29172E20C9DBD6F8739ACA981C4A8D4DFAC73`
- Developer DB V2:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`
- Frozen LINEAGE DB:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`

No existing migration, protected database, domain repository, agent, provider,
frontend, CLI, or evaluation runtime file changed.

## Explicit deferrals and security conclusion

PH-3B does not add tenant IDs to the 38 domain tables and does not enforce
tenant predicates in incidents, topology, signals, changes, RCA, ownership,
reports, runtime, agents, providers, cloud, approvals, or execution. It does
not add a frontend/CLI tenant selector, OIDC/user records, permissions, billing,
or a global ORM tenant filter.

Therefore TopoAI has a durable tenant root and an authenticated tenant-context
control plane, but **TopoAI is not tenant-safe after PH-3B**. PH-3C, PH-3D,
PH-3E, PH-3F, and PH-3G remain required. Current `admin` is an interim minimum
control-plane role; PH-5 must distinguish installation administration, tenant
administration, and data-plane permissions.

The recommended next block after architect review, commit, PR, merge, and a
clean main branch is **PH-3C — Domain Tenant Ownership Columns + Controlled
Legacy Backfill + Tenant-Scoped Identity / Constraint Migration**.

**PH-3B ACCEPTED / READY FOR ARCHITECT REVIEW**
