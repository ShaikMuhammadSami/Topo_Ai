# PH-2E — Named API Credentials + CLI / Evaluation Lifecycle v1

- Status: implementation candidate
- Branch: `security/ph-2e-named-api-credentials-lifecycle-v1`
- Accepted parent: `1713be4ac0c5d453726b4a0df16ffad9cdf40653`
- Migration head: `0003_auth_api_credentials`

## Scope

PH-2E adds a durable, digest-only lifecycle for named human and service API
credentials. It preserves the PH-2B static digest registry as an optional
bootstrap/break-glass authority, the PH-2C browser-session schema, and all
PH-2D agent/provider authentication domains. It adds no tenant, password,
OIDC, permission, provider-secret, or execution system.

## Credential contract

`auth_api_credentials` stores a stable credential ID, a SHA-256 secret digest,
a non-secret hint/name, caller type, stable principal metadata, creator,
bounded expiry, revocation actors/times, last use, and timestamps. Raw secrets
start with `topo_api_`, contain 48 URL-safe random bytes, and are returned only
by the create response. They are never stored by Topo. Credential IDs and
hints are not authenticators.

The supported caller types are:

- `human_api`, resolved as `human_api_token`; may create a browser session.
- `service_api`, resolved as `service_api_token`; may use ordinary
  identity-only API routes but cannot create a browser session or administer
  credentials.

Credential lifecycle routes are under `/api/v1/auth/api-credentials`. Create,
list, get, and revoke require an authenticated human `admin`. A static
bootstrap admin, named human admin, or valid admin browser session may manage
credentials. Creation accepts a lifetime of 1–90 days and defaults to 30.
Rotation is intentionally create-new, verify-new, then revoke-old; the secret
digest of an existing record is never replaced.

## Bearer and session authority

Bearer dispatch recognizes the server-generated `topo_api_` format, then
requires an exact durable digest match and active record. Revoked or expired
named matches fail with 401 and cannot fall through to static authority.
Other bearer values use the validated static registry. An invalid explicit
bearer never falls back to a browser cookie.

Successful named bearer authentication updates `last_used_at`. This is
observability metadata, not an authorization invariant. A database failure
during lookup/update fails closed with 503. Concurrent observations may race;
the latest committed observed timestamp wins. Once revocation commits,
subsequent authentication rejects; a request authenticated immediately before
that commit may complete normally.

The accepted `auth_sessions` schema already stores source authentication type
and source credential digest, so no session migration was required. Static
sessions revalidate against the current static registry. Named-human sessions
revalidate the exact durable source digest, principal snapshot, caller type,
expiry, and revocation on every request. Revoking a named source therefore
invalidates its derived sessions immediately. Service credentials are rejected
from session exchange with 403.

## Startup and recovery

Required mode parses auth configuration first but does not query credential
tables during configuration loading. Application lifespan performs persistence
initialization/schema-authority verification first. It then requires either:

1. a validated static authority mapping; or
2. at least one unexpired, unrevoked durable `human_api` credential with the
   `admin` role.

This ordering means a current PostgreSQL schema plus a durable named admin can
restart with an empty static registry. A missing/behind schema fails through
persistence authority before any named-credential query. If neither authority
exists, startup fails closed with `EMPTY_REQUIRED_AUTHORITY`.

Normal operation should use named credentials. An out-of-band, digest-only
static admin mapping remains supported for initial bootstrap and break-glass
recovery. After named-admin creation and recovery verification, operators may
remove/rotate the static mapping. Sessions derived from a removed static source
become invalid; named-source sessions remain valid.

## CLI and evaluation

The CLI keeps hidden/stdin login, OS-keyring storage, and JSON profiles without
raw secrets. `topo logout` removes only local keyring state. Server revocation
is explicit through `topo auth credentials revoke <credential-id>`. The new
administrative commands are create/list/revoke. Creation requires
`--output-token-stdout`, making the one-time raw-secret destination explicit;
the CLI does not auto-login or auto-store it. HTTP 401 retains authentication
exit code 4, while 403 uses distinct authorization exit code 9.

The evaluation runner now starts its isolated backend with
`TOPO_AUTH_MODE=required`. It generates an ephemeral static bootstrap secret in
memory, gives the backend only its digest mapping, creates one short-lived named
human admin, and switches the evaluation HTTP client to that named credential.
Raw values and random credential IDs do not enter results, baselines,
diagnostics, or logs. Causal/topology/incident outputs are unchanged.

## Migration and rollback

`0003_auth_api_credentials` is a static additive migration with
`down_revision = 0002_auth_sessions`. It creates only the credential table and
its required constraints/indexes. Revisions 0001 and 0002 remain immutable.
Disposable downgrade to 0002 drops only the new table; production rollback
remains a schema-compatible previous application, backup/restore, or a forward
corrective migration rather than routine destructive downgrade.
