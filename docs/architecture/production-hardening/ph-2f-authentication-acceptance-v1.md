# PH-2F — Authentication Acceptance v1

- Date: 2026-08-30
- Branch: `security/ph-2f-authentication-acceptance-closure-v1`
- Accepted parent: `786756c59bae91d00d646828136db0a3ff927967`
- Accepted parent summary: `feat(security): add named API credential lifecycle (#71)`
- Scope: authentication acceptance and PH-2 closure only
- Verdict: **PH-2 ACCEPTED / CLOSED**

## Scope

PH-2F validates the authentication architecture delivered by PH-2A through
PH-2E. It adds one deterministic acceptance test module and this closure
record. It does not add an identity type, login mechanism, authentication
protocol, migration, database column, tenant concept, permission model, or
secret-custody system. No production implementation defect was found during
acceptance, so production code did not need repair.

Authentication now establishes who a caller is and selects one inbound trust
domain. It does not establish tenant membership, comprehensive authorization,
or complete secret custody.

## Accepted authentication architecture

```text
public liveness/readiness
  -> no business authority

human browser
  -> transient static or named-human bearer exchange
  -> opaque server-persisted session + CSRF
  -> USER_AUTHENTICATED routes

human CLI/API
  -> static bootstrap/break-glass or named human_api bearer
  -> USER_AUTHENTICATED routes

service API
  -> named service_api bearer
  -> identity-only USER_AUTHENTICATED routes
  -> no browser session or credential administration

Topo Agent enrollment
  -> body-bound one-time enrollment credential
  -> atomic consume + agent creation

Topo Agent steady state
  -> dedicated agent bearer
  -> AGENT_AUTHENTICATED routes

provider callback
  -> provider-specific verification over the raw request
  -> PROVIDER_CALLBACK_AUTHENTICATED route
```

Route classification selects the authority before credential verification.
Sharing the HTTP Bearer transport does not allow a credential to cross trust
domains.

## Trust-domain acceptance matrix

The closure test uses the real middleware, digest-only credential/session
persistence, agent enrollment path, agent dependency, and GitHub callback
verification against disposable SQLite.

| Caller | Public | Human identity | Human admin | Agent enrollment | Agent steady state | Provider callback |
|---|---:|---:|---:|---:|---:|---:|
| Anonymous | Yes | 401 | 401 | no valid authority | 401 | 401 |
| Static bootstrap human admin | Yes | Yes | Yes | creates enrollment authority as admin | 401 | 401 |
| Named `human_api` admin | Yes | Yes | Yes | creates enrollment authority as admin | 401 | 401 |
| Named `human_api` non-admin | Yes | Yes | 403 | forbidden to create authority | 401 | 401 |
| Named `service_api` | Yes | Yes | 403 | forbidden to create authority | 401 | 401 |
| Bootstrap-derived browser session | Yes | Yes | Yes when source has admin | not an enrollment credential | 401 | 401 |
| Named-human-derived browser session | Yes | Yes | Yes when source has admin | not an enrollment credential | 401 | 401 |
| Agent enrollment credential | Yes | 401 | 401 | Yes, body-bound and bounded by max uses | 401 as bearer | 401 |
| Steady-state agent credential | Yes | 401 | 401 | No | Yes | 401 |
| Provider-authenticated caller | Yes | 401 | 401 | No | 401 | Yes |

The provider signature/header material cannot authenticate human or agent
routes. Human bearer, browser session, service credential, enrollment token,
and agent bearer cannot substitute for provider authentication.

## Route-domain model

Required-mode production registration has:

- 136 route objects and 136 registered method/path pairs;
- 134 API method/path pairs;
- 2 public routes: `GET /health` and `GET /ready`;
- 125 `USER_AUTHENTICATED` API pairs;
- 8 `AGENT_AUTHENTICATED` API pairs;
- 1 `PROVIDER_CALLBACK_AUTHENTICATED` API pair; and
- 0 unknown API pairs.

The development-only catalog has 140 route objects and 144 method/path pairs.
Its additional four documentation routes represent eight GET/HEAD pairs:
OpenAPI, Swagger, the Swagger redirect helper, and ReDoc. They are not
registered in required mode. CORS `OPTIONS` is a bounded transport behavior,
classified `PUBLIC_CORS_PREFLIGHT`; it grants no business authority.

## Default-on and development boundary

`TOPO_AUTH_MODE` absent resolves to `required`. Explicit `required` does the
same. Invalid values fail configuration. Legacy `TOPO_AUTH_ENABLED=false`
cannot disable authentication, and inconsistent legacy/new settings fail
closed. Malformed static registries fail during configuration loading without
reflecting their raw value.

The synthetic `local-development` admin/operator principal exists only under
explicit `development-disabled` with SQLite persistence. PostgreSQL or another
non-SQLite backend rejects that mode. Required-mode bearer, session,
credential-management, approval, and execution-intent paths cannot create the
synthetic principal. Acceptance persistence contains no synthetic credential
creator, revoker, or session subject.

## Startup authority model

Required-mode startup first executes persistence initialization and schema
authority verification. Only after that succeeds does it evaluate whether one
of these human administrative authorities exists:

1. a valid configured static mapping; or
2. an active, unexpired durable `human_api` credential carrying `admin`.

A current PostgreSQL schema plus a durable named administrator starts with an
empty static registry, and that named credential authenticates after restart.
A current schema with neither authority fails with
`EMPTY_REQUIRED_AUTHORITY`. A missing, behind, unstamped, ahead, unavailable,
or otherwise invalid database fails through persistence/schema authority
before absence of a durable administrator can be misreported. There is no
authentication-disabled recovery fallback.

## Bootstrap lifecycle

`TOPO_API_TOKEN_HASHES_JSON` remains an optional initial bootstrap,
break-glass/recovery, and backwards-compatibility authority. It is not the
recommended normal credential store and is not required permanently.

A configured bootstrap administrator can authenticate, create a named human
administrator, and create a browser session. After the named administrator is
verified, operators may remove the bootstrap mapping. Removal invalidates
bootstrap-derived sessions on their next request but does not invalidate
sessions derived from the durable named administrator. Required-mode restart
then succeeds using durable authority.

## Named credential lifecycle

Named secrets use the server-generated `topo_api_` format and high-entropy
random material. The raw value is returned exactly once by creation. Topo
persists only its SHA-256 digest plus non-secret identifier/hint and server-side
principal metadata. List/get/revoke responses expose neither raw value nor
digest.

`human_api` resolves to `human_api_token`; `service_api` resolves to
`service_api_token`. Expired or revoked records fail with 401. Successful use
updates `last_used_at`; persistence failure fails closed. Human administrators
can create/list/get/revoke. Human non-admin and service identities receive 403
for management. Rotation remains create-new, verify-new, revoke-old.

Service credentials may use ordinary APIs that currently require authenticated
identity only. They cannot create browser sessions, manage credentials,
authenticate agent routes, or authenticate provider callbacks. PH-5 owns any
future service permission decomposition.

## Browser session and CSRF model

Browser sessions are opaque random secrets stored digest-only on the server.
The cookie is `Secure`, `HttpOnly`, `SameSite=Lax`, path `/`, with bounded
absolute and idle expiry. The readable CSRF cookie is also random and its
server record is digest-only. Logout revokes the server session and clears both
cookies. Session persistence and revocation survive application restart.

Only static-human and named-human bearer authorities can exchange for a
session. Service credentials are rejected with 403. Source authority is
revalidated on every session request. Revoking a named human credential makes
its existing sessions return 401 immediately on subsequent use. Removing a
static mapping similarly invalidates sessions derived from it.

For cookie-authenticated requests, POST, PUT, PATCH, and DELETE require a valid
`X-Topo-CSRF` value. GET, HEAD, and OPTIONS do not. Bearer-authenticated human
requests, agent requests, and provider callbacks do not use human CSRF.
Missing/invalid CSRF is 403. An explicit Authorization header always selects
bearer authentication; an invalid bearer plus a valid cookie is 401 rather
than an ambient-cookie fallback.

Revocation is request-boundary enforcement: once the revocation transaction
commits, subsequent authentication fails. A request authenticated before that
commit may complete; PH-2 makes no retroactive cancellation claim.

## Agent authentication

Enrollment credentials and steady-state agent credentials remain digest-only
in backend persistence and are never human/provider authority. Enrollment-token
consumption and agent creation share one transaction. On the measured
PostgreSQL 16 READ COMMITTED baseline, two concurrent attempts against
`max_uses=1` produce exactly one success. A failed agent insert rolls back the
conditional consumption, leaving `use_count` unchanged. Revoked, expired,
unknown, and exhausted enrollment credentials cannot enroll.

The raw steady-state agent token is returned only after commit. A revoked agent
returns 401 on the next request and after restart. Human bearer, human session,
service credential, provider material, and enrollment bearer cannot use agent
routes. An agent credential cannot use a human route. Existing cluster and
namespace binding remains unchanged.

This is a bounded security claim, not a claim that all repository operations
are race-free.

## Provider authentication and replay semantics

Supported mechanisms remain:

- GitHub: HMAC-SHA256 over the raw body;
- GitLab: signed webhook mode with bounded signed timestamp, or configured
  legacy shared-secret mode;
- HCP Terraform: HMAC-SHA512 over the raw body;
- Jenkins: Topo HMAC-SHA256 over the raw body; and
- Azure DevOps: configured HTTP Basic verification.

Authentication occurs before trusted JSON parsing, delivery acceptance,
change persistence, or incident/domain mutation. Unknown and disabled sources
and invalid caller material return the same generic 401. Missing or malformed
server verification configuration returns a bounded generic 503 without
revealing source or secret details.

Only protocols that cryptographically sign freshness receive a freshness-window
claim. Other supported providers authenticate first and then use durable
delivery identity/payload-hash idempotency. Exact authenticated replay reuses
one delivery record and produces no duplicate domain effect. PH-2 does not
claim universal cryptographic replay prevention.

## CLI behavior

`topo login` accepts a named bearer through hidden input or stdin, verifies it
with `whoami`, and stores the raw value in the OS keyring. Profile JSON contains
no raw credential. The CLI does not depend on a browser session or provide a
password login.

`topo auth credentials create/list/revoke` preserves the server lifecycle.
Creation requires explicit one-time stdout authorization. `topo logout`
removes only the local keyring value and states that the server credential is
unchanged; server revocation is a separate explicit command. HTTP 401 maps to
authentication exit code 4, while 403 maps to authorization exit code 9.

## Evaluation required-auth proof

Evaluation runs with `TOPO_AUTH_MODE=required`. It creates a runtime-only
bootstrap value, supplies only its digest mapping to the isolated backend,
creates a short-lived named administrator, then uses that named credential for
subsequent requests. Active evaluation source contains no
`development-disabled`, legacy false switch, or synthetic development
principal path. Raw values and random credential identifiers do not enter
result files, baselines, integrity manifests, logs, or artifact names.
Evaluation semantics remain unchanged.

## Frontend acceptance

The application authentication gate resolves the session before product
components mount or fetch. Login credentials remain transient component state
and are sent only in the Authorization header to session exchange. No auth
secret is stored in localStorage or sessionStorage. The central client uses
same-origin cookie transport and adds CSRF automatically for unsafe session
requests.

HTTP 401 moves the frontend to an unauthenticated/expired state. HTTP 403 keeps
the authenticated boundary and reports forbidden. Logout invokes server
session revocation. Report export uses the same-origin authenticated route and
has no query-string credential.

## Migration chain

The accepted immutable chain is:

```text
0001_current_schema
  -> 0002_auth_sessions
  -> 0003_auth_api_credentials
```

There is exactly one Alembic head: `0003_auth_api_credentials`.

Frozen SHA-256 values:

- `0001`: `B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6`
- `0002`: `4EB2930BFF89944DA5E9EA24F33B80F170D0F82E40F0AB508A07B2DC6B624460`
- `0003`: `EAE6BA5CF16A4E68161A710EDFA29172E20C9DBD6F8739ACA981C4A8D4DFAC73`

PH-2F creates no migration and changes none of these files or `models.py`.

## Credential and logging boundary

Security implementation review found no logging of bearer values, session or
CSRF cookie values, credential digests, provider secrets/signatures, or raw
Authorization headers. Error responses remain bounded. Credential management
responses do not expose digests. The SEC-1 scanner tests and tracked-tree scan
pass. Broader secret custody and observability remain PH-4 work.

## Acceptance evidence

- PH-2F focused acceptance: 3 passed.
- PH-2B default-on/fail-closed: 32 passed.
- PH-2C session/CORS: 21 passed.
- PH-2D agent/provider: 17 passed.
- PH-2E named credentials: 11 passed.
- Disposable PostgreSQL 16 acceptance: 59 passed at READ COMMITTED.
- Full backend: 1,080 passed, 59 skipped.
- Full evaluation: 914 passed, 3 skipped.
- Agent: 15 passed.
- CLI: 67 passed.
- Frontend: 78 passed.
- Frontend typecheck: passed.
- Frontend lint: passed with 11 existing warnings and zero errors.
- Frontend production build: passed.
- Backend/evaluation/agent/CLI compile checks: passed.
- SEC-1 scanner unit tests: 8 passed.
- SEC-1 tracked-tree scan: passed.
- `git diff --check`: passed.

PostgreSQL used a disposable `postgres:16` container, no persistent named
volume, and guaranteed cleanup. SQLite acceptance used disposable databases.
The protected developer and frozen LINEAGE database artifacts were not used as
mutable test databases.

## Custody evidence

- Developer DB Custody Baseline V2 before/after:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`
- Frozen LINEAGE DB before/after:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`
- Migrations 0001, 0002, and 0003 remained byte-identical.

## Defensible production authentication claims

PH-2 freezes only these claims:

1. Authentication is required by default.
2. Authentication configuration fails closed.
3. Browser sessions are opaque, revocable, server-persisted, and
   CSRF-protected.
4. Human/service API credentials are named, expiring, revocable, and stored
   digest-only.
5. Static credentials are optional bootstrap/break-glass authority.
6. Topo Agent credentials are isolated from human/provider authority.
7. Provider callbacks use provider-specific authentication before trusted
   payload processing.
8. Agent enrollment max-use is atomic on the measured PostgreSQL 16 READ
   COMMITTED and bounded SQLite baselines.
9. Evaluation executes the required-auth path.
10. Authentication does not imply tenancy, comprehensive RBAC, or complete
    secret custody.

## Known exclusions and deferred work

- **PH-3:** tenant identity, membership, tenant-scoped persistence, query
  scoping, and isolation.
- **PH-4:** provider/outbound secret encryption or externalization, agent
  `credentials.json` custody, Kubernetes Secret lifecycle, secret rotation,
  secret-manager integration, and broader secret observability.
- **PH-5:** comprehensive role/permission policy, least privilege, service
  permissions, and administrative permission decomposition.
- **PH-10:** general counters, sequence allocation, incident-correlation races,
  multi-worker behavior, capacity, and repository concurrency.

Current `admin`, `operator`, and test/viewer semantics remain the limited
existing authorization model. PH-2 does not claim customer readiness, tenant
safety, complete least privilege, complete provider secret custody, or general
concurrency safety.

## Final PH-2 state

- PH-2A: accepted
- PH-2B: accepted
- PH-2C: accepted
- PH-2D: accepted
- PH-2E: accepted
- PH-2F: accepted

**PH-2 AUTHENTICATION HARDENING = ACCEPTED / CLOSED.**

The next recommended block, after architect review, commit, PR, merge, and a
clean main branch, is **PH-3A — Tenant Identity + Isolation Contract /
Persistence Inventory**. PH-3 work is not started here.
