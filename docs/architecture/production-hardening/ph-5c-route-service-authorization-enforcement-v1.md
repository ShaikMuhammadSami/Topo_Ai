# PH-5C — Route + Service Authorization Enforcement v1

Status: accepted for architect review  
Starting commit: `3380b52f2f05a7cb9d0a849595fc19ff10f2818e`  
Branch: `security/ph-5c-route-service-authorization-enforcement-v1`

## Scope and starting gap

PH-5B froze the permission vocabulary, authority bundles, 143-route registry,
98-operation registry, authenticator credential policy, and V1 execution deny.
Before PH-5C those plans were not one executable boundary: route handlers still
contained several legacy `admin` checks, critical direct/background operations
did not consistently require a typed authority, and the four global credential
routes did not enforce their target-sensitive human-self/service-tenant policy.

PH-5C makes the frozen plans executable without adding a permission, role,
route, table, column, migration, durable audit record, or execution capability.
PH-3 tenant predicates remain an independent storage-level isolation defense;
PH-4 secret custody remains unchanged.

## Central authorization model

`app.security.authorization_enforcement` owns the executable boundary:

```text
authenticate
    -> resolve durable principal or machine identity
    -> resolve selected/fixed tenant or installation assignment
    -> derive server-only AuthorizationContext
    -> authorize frozen route/operation
    -> execute tenant-scoped service/repository work
```

`AuthorizationContext` is frozen and cannot be normally constructed by a
caller. Its exact fields are:

- `actor_principal_id`
- `actor_principal_type`
- `authority_kind`
- `tenant_id`
- `effective_permissions`
- `authentication_provenance`
- `fixed_purpose`
- `request_id`

Construction requires a module-private identity token. The type is not a
Pydantic request model, has no deserializer, and is never accepted from an HTTP
body, header, provider payload, or internal caller string. It carries no raw
credential, cookie, provider proof, or `SecretMaterial`.

The six authority kinds are authentication self-service, human tenant,
service tenant, installation, agent fixed-purpose, and provider fixed-purpose.
No generic internal/system administrator or bypass flag exists.

The application installs `require_route_authorization` once as a global
FastAPI dependency. It resolves every registered production route by exact
method and path-template lookup. Unknown routes fail closed; tests compare the
live application to the frozen plan. `authorize_service_operation` similarly
looks up an exact frozen operation ID, requires the typed context, and rejects
unknown operations.

## Human, service, and installation enforcement

Human tenant authority is derived on every request from the durable active
human principal, selected `TenantContext`, active membership, and membership
role. The membership row is reloaded and its ID must match the resolved
context. PH-5B role bundles then produce the effective permissions. Subject
fallback count is zero and `AuthPrincipal.roles` contributes no PH-5 tenant or
installation authority.

Service authority is derived from a durable active service principal, the
exact PH-3 fixed tenant binding for the authenticated credential, and the
service principal's explicit PH-5B permission assignment. Service principals
do not need or consume human memberships. The complete durable tenant set must
equal the context tenant, so a forged selector, missing assignment, additional
binding, disabled principal, or reduced permission fails authorization on the
next request/transaction.

Installation authority is human-only and comes only from an active durable
installation-operator assignment. Tenant Admin does not imply Installation
Operator, and Installation Operator does not imply membership or tenant
permissions. The existing local grant/disable/status utility remains the
trusted deployment boundary for assignment recovery.

## Machine fixed-purpose enforcement

Agent authority is built only from a verified, unrevoked durable agent or a
verified usable enrollment-token row, its server-owned tenant, an active
machine tenant, and one exact allow-listed purpose. Agent enrollment,
heartbeat/configuration, topology snapshots, runtime telemetry, changes, and
failure signals retain their accepted authentication and tenant derivation.

Provider authority is built only after provider proof identifies an enabled
durable `ChangeSourceRecord`. The source's server-owned tenant and exact
webhook-ingestion purpose are then bound into the context. Provider payloads
cannot supply authority. Provider verification-before-JSON-parse behavior is
preserved.

Fixed-purpose authorities never become tenant roles, permission bundles, or
installation operators. Automatic workflows propagate a context derived from
their proven agent/provider root; the implementation introduces no caller-name
trust such as `system`, `internal`, or `background`.

## Route and operation binding

The live route and frozen plan inventories remain one-to-one:

| Route intent | Count | Runtime behavior |
|---|---:|---|
| PUBLIC | 2 | The only unauthenticated product routes |
| AUTHENTICATION_SELF_SERVICE | 7 | Exact authenticated caller lifecycle |
| TENANT_PERMISSION | 109 | Active human membership or fixed service binding plus permission |
| INSTALLATION_PERMISSION | 2 | Active human installation assignment plus permission |
| AGENT_FIXED_PURPOSE | 8 | Existing agent auth then exact machine operation |
| PROVIDER_FIXED_PURPOSE | 1 | Provider proof then exact source operation |
| V1_DORMANT_EXECUTION_DENY | 10 | Authenticated callers receive bounded 403 |
| AUTHENTICATOR_CREDENTIAL_POLICY | 4 | Human-self or same-tenant service target policy |
| **Total** | **143** | 0 unknown, 0 duplicate, 0 new |

The critical operation registry remains exactly 98 entries: 65 tenant, eight
installation, eight authentication self-service, five agent fixed-purpose,
one provider fixed-purpose, and 11 V1 dormant execution-deny operations.
Twenty-eight operation roots call the central operation guard directly.
Seventy entries are explicitly enumerated as descendants of the global route
guard or a guarded automatic-workflow root. Their union equals the frozen
registry; intersection and unprotected counts are zero. The test uses two
explicit sets rather than treating every set-complement entry as trusted.

## Credential target-aware enforcement

The four existing authenticator endpoints remain global routes, but their
target is now explicit and authoritative:

- human credential create/get/list/revoke is self-only for the authenticated
  human principal;
- service credential create/revoke requires `credential.rotate` in the
  selected tenant;
- service credential list/get requires `credential.metadata.read` in the
  selected tenant;
- service credentials are listed separately using the bounded
  `target_type=service` query contract; omitted `target_type` means the
  caller's own human credentials;
- foreign and nonexistent service credential IDs are both masked as the same
  404 before permission detail is returned;
- service callers, responders, unrelated humans, Tenant Admins from another
  tenant, and Installation Operators cannot administer a human's credential;
  and
- new service principal, explicit permission assignment, credential, and
  fixed tenant binding remain one transaction before one-time raw-secret
  delivery.

The CLI mirrors the target distinction with `--target-type human|service` and
requires a selected tenant for service credential listing. JSON and displayed
metadata remain secret-safe.

## Permission behavior

Viewer reads succeed only for mapped incident, topology, evidence, report,
integration, and ownership reads. Same-tenant responder/admin mutations are
403 when the required permission is absent. Responder adds
`incident.respond` but does not gain integration, ownership, membership,
credential, tenant-settings, or installation administration. Tenant Admin
receives the frozen 14 tenant permissions in its own tenant but no
installation or execution authority.

Service principals receive only their explicit assignable subset. A service
with `integration.manage` can perform the corresponding non-secret integration
operation without an artificial `credential.rotate` conjunction. Operations
that create or replace secret material retain the frozen combined
`integration.manage` plus `credential.rotate` requirement. Service principals
cannot receive `member.*`, `credential.*`, `tenant.settings.manage`, or
`installation.*` assignments.

The same human can be Viewer in Tenant A and Admin in Tenant B; authority is
resolved from the selected tenant's current membership on each request. No
cross-tenant role cache exists. PostgreSQL READ COMMITTED tests prove that the
next transaction observes membership demotion/disable, service permission
reduction, and installation-operator disablement.

## 401, 403, and 404 ordering

- Missing, invalid, expired, or revoked authentication remains 401.
- An authenticated caller lacking a same-tenant permission receives a bounded
  403 with a stable code and, where useful, only the required permission.
- A foreign tenant object ID is checked with tenant-scoped persistence before
  permission detail and returns the same 404 shape as an absent object.
- Existing PH-3 tenant-selector 400/403 semantics are preserved.
- Dormant execution routes authenticate first: unauthenticated is 401 and
  every authenticated V1 authority receives 403 `V1_EXECUTION_DISABLED`.

The resource masker covers incident, analysis, signal, snapshot, change,
change-event, source, dead-letter, webhook, membership, agent, identity
override, recommendation, recovery verification, Copilot session,
investigation plan, report, and report-action-item identifiers. It returns no
foreign tenant metadata.

## V1 execution deny

All ten dormant HTTP routes and all 11 action-approval/execution-transaction
operation entries deny every V1 authority. The same denial exists at the
service layer before dormant business behavior, so direct/background calls
without a context or with Admin, Operator, service, agent, or provider context
cannot execute them. The permission vocabulary still contains zero execution
permissions.

Legacy approval handler role checks remain inside six unreachable dormant
route functions as preserved 14G/14H implementation detail; the global route
deny prevents entry and the service deny prevents direct invocation. They are
not PH-5 authority. The one startup check for an active durable human
credential carrying legacy bootstrap metadata is retained solely to prevent a
required-mode installation from starting with no usable authentication root;
it grants no route/service authorization. Eleven active legacy admin-gate call
sites were replaced across agent administration, credential policy, tenant
bootstrap/membership, and recovery. No unknown active legacy gate remains.

## Adversarial and regression proof

The new enforcement tests prove:

- exact 143-route global binding and exact 98-operation coverage;
- private context construction, no-context denial, wrong-kind denial, forged
  human/service scope denial, and unknown-operation denial;
- Viewer/Responder/Admin/Operator separation and legacy-role non-authority;
- active membership, principal, service assignment, fixed binding, and
  installation assignment revalidation;
- credential target confusion, human self-only ownership, same-tenant service
  administration, responder denial, service-caller denial, and foreign 404;
- agent/provider/human cross-authority attacks fail;
- ten HTTP and 11 direct-service execution denials; and
- real PostgreSQL next-transaction behavior for human demotion, membership
  disable, service permission reduction/fixed tenant, and operator disable.

The evaluation runner's disposable database now grants its authenticated
bootstrap principal an explicit Installation Operator assignment through the
existing trusted local utility, then mints a self credential for that same
principal. It no longer uses legacy `roles: ["admin"]` as authorization or
creates a credential for a different human. This is test-harness authority for
an isolated temporary database only.

Measured final results:

| Gate | Result |
|---|---|
| PH-5C plan + enforcement focus | 29 passed |
| PH-5B/PH-5C PostgreSQL authority focus | 22 passed |
| Backend default/SQLite | 1,582 passed, 264 skipped, 2 established warnings |
| Backend PostgreSQL 16 | 1,838 passed, 8 skipped, 2 established warnings |
| PostgreSQL logical backup/restore | passed inside full PostgreSQL run |
| Evaluation | 917 passed, 3 skipped |
| CLI | complete suite passed (85 tests) |
| Agent | complete suite passed (24 tests, 1 platform skip) |
| Frontend configured auth/session/product tests | 93 passed |
| Secret scanner | 12 tests passed; tracked tree and explicit new files clear |
| Backend, evaluation, CLI, agent compile | passed |

The two backend warnings are the existing Starlette TestClient deprecation and
the accepted SQLAlchemy identity-map warning produced by a deliberate
same-identifier cross-tenant adversarial case. No causal, evidence, lineage,
LLM, incident, topology, secret-custody, or machine-authentication semantics
were excluded from either full backend run. The full evaluation suite made no
live provider, Kubernetes, or LLM call.

## Schema and custody

PH-5C creates no migration. Alembic has one head,
`0014_min_authority`. ORM inventory remains 49 tables and 829 columns.
Migrations 0001 through 0014 have no Git diff and retain their accepted
committed-content SHA-256 authorities. The developer database and frozen
LINEAGE database retain their accepted actual-byte hashes. Test databases were
temporary SQLite files or PostgreSQL databases inside the loopback-only
`postgres:16-alpine` container with tmpfs storage and no persistent volume.

## PH-5D handoff

PH-5C intentionally adds no durable security/admin audit ledger. PH-5D can now
consume central, typed allow/deny decisions for privileged tenant mutations,
membership, integrations/providers/webhooks, ownership, credential metadata
lifecycle, tenant settings, and installation-sensitive activity without
reconstructing authority from route names or legacy roles.

PH-5C ACCEPTED / READY FOR ARCHITECT REVIEW
