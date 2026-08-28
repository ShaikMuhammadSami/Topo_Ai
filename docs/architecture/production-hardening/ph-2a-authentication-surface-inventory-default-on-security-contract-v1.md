# PH-2A — Authentication Surface Inventory & Default-On Security Contract v1

- Status: **ARCHITECTURE / SECURITY INVENTORY CANDIDATE**
- Repository: `C:\Topo-ai`
- Branch reviewed: `architecture/ph-2a-authentication-surface-inventory-v1`
- Accepted repository commit: `075d724ca0bc896c1ca10048dabe305c84eda724`
- Accepted repository summary: `075d724 docs(architecture): close production persistence hardening (#65)`
- Scope: architecture and forensic inventory only; no product, frontend, agent,
  CLI, evaluator, workflow, migration, model, or database change

## 1. Executive finding

TopoAI has three working but distinct inbound authentication domains: a global
human/API bearer-token middleware, a durable Topo Agent token dependency, and
provider-specific webhook verification. Those domains are separable enough to
support a safe default-on transition. There is no PH-2A architecture blocker.

The current deployment posture is nevertheless unsafe for a production-shaped
service. `TOPO_AUTH_ENABLED` defaults to false, unrecognized values also become
false, and every ordinary `/api/*` route then receives a powerful synthetic
`local-development` principal with `admin` and `operator` roles. The 118 human-
domain API routes therefore do not require a real credential by default,
including 45 non-GET routes and all dormant approval/execution mutations. The
browser has no login, session, bearer header, logout, expiry, 401, or 403
boundary and consequently works only with authentication disabled.

The current API token registry is a useful high-entropy bootstrap/development
and compatibility mechanism. It is not a sufficient permanent human identity
system because it has no credential ID, creation API, expiration, revocation,
last-use tracking, lifecycle audit, or browser-safe transport. The CLI is more
mature: it already sends bearer tokens, obtains them from an environment
variable or OS keyring, offers login/logout/whoami, and avoids writing a raw
token to its JSON profile.

The recommended V1 direction is:

```text
default/production: authentication required and fail closed

browser:
  high-entropy operator credential used only for login exchange
    -> opaque, server-side, revocable session
    -> Secure + HttpOnly + SameSite cookie
    -> CSRF validation for unsafe methods

CLI/API:
  named, expiring, revocable high-entropy bearer API credential

Topo Agent:
  existing enrollment credential -> existing dedicated agent credential

provider webhook:
  existing provider-specific signature/shared-secret verification
```

Authentication proves caller identity only. It does not prove tenant access;
PH-3 still owns tenant identity and isolation. Provider/outbound secret custody
remains PH-4. PH-5 owns broader role-policy design.

One additional critical PH-4 finding was confirmed without reproducing the
secret: tracked `backend/.env.example` currently contains an uncommented, non-
placeholder GitHub token-shaped value, and ignored `backend/.env` also contains
one. Treat that provider credential as compromised, rotate/revoke it promptly,
and remove the value from tracked source/history in a separately reviewed
secret-remediation change. PH-2A does not modify either file.

## 2. Accepted state and governing constraints

PH-1E is merged in current `HEAD`. It accepts PostgreSQL 16 plus immutable,
additive Alembic history as the production persistence baseline. Revision
`0001_current_schema` is immutable. Any authentication schema must be an
additive `0002+` revision, must preserve SQLite test/evaluation roles, and must
not introduce tenant columns before PH-3.

The V1 transition document keeps the product read-only, preserves dormant
14F/14G/14H foundations, and prohibits treating authentication as tenancy or
using production hardening to reopen causal-reasoning work. This contract
therefore changes no execution behavior and grants no infrastructure authority.

Inventory evidence came from current source, the live FastAPI route tree, the
accepted post-15D API inventory, frontend/CLI/agent static inspection, focused
auth tests, configuration searches, and the governing PH-1E/transition docs.
The live route set exactly matches the accepted API inventory after accounting
for that inventory's `/health` row.

## 3. Current authentication architecture

### 3.1 Human/API request trace

```text
HTTP request to /api/*
  -> ApiTokenAuthMiddleware path classifier
  -> TOPO_AUTH_ENABLED (default false)
     -> false: development_principal()
     -> true: Authorization: Bearer <raw token>
  -> SHA-256 candidate digest
  -> TOPO_API_TOKEN_HASHES_JSON registry
  -> hmac.compare_digest(candidate digest, configured digest)
  -> AuthPrincipal(subject, display_name, roles, authentication_type)
  -> request.state.principal
  -> route
  -> optional route authorization helper
  -> service/repository
  -> selected approval/execution audit records
```

The middleware is global, not a router dependency. It guards `/api/*` except
the exact agent-enrollment route, the `/api/v1/agent/` prefix, and the
`/api/v1/change-source-webhooks/` prefix. It also bypasses all `OPTIONS`, exact
`/`, `/health`, `/openapi.json`, prefixes `/docs` and `/redoc`, and every path
outside `/api/`. Only `/health`, docs/schema routes, and API routes actually
exist; `/` is allowlisted but returns 404.

No service-layer authentication is applied to ordinary business services.
Approval/execution routes extract the principal explicitly; agent routes use a
dedicated dependency; provider delivery verifies inside its ingest service.

### 3.2 Implementation files and symbols

| Area | Current source and symbols |
|---|---|
| Global auth | `backend/app/security/api_tokens.py`: `ApiTokenAuthMiddleware`, `authentication_enabled`, `resolve_principal`, `token_digest`, `development_principal`, `AuthPrincipal` |
| Wiring/CORS/public health | `backend/app/main.py` |
| Human identity probe | `backend/app/api/system.py`: `whoami` |
| Role checks | `backend/app/security/approval_authorization.py`: `authenticated_principal`, `approval_control_principal`; `backend/app/api/agents.py`: `_require_admin` |
| Agent auth | `backend/app/security/agent_tokens.py`: `require_agent`; `backend/app/repositories/agent_repository.py`: enrollment, hashing, authentication, revocation |
| Provider webhook auth | `backend/app/api/change_source_webhooks.py`, `backend/app/services/webhook_security.py`, `backend/app/services/change_source_ingest.py` |
| Audit identity | action-approval and execution services/repositories plus `backend/app/db/models.py` |
| Browser client | `frontend/lib/topo-api.ts`; direct report-export URL in `frontend/components/app/incident-post-incident-report.tsx` |
| CLI | `cli/src/topo_cli/client.py`, `config.py`, `main.py`, `runtime.py`, `errors.py` |
| Agent client/storage | `agent/src/topo_agent/client.py`, `config.py`, `main.py`, Kubernetes deployment manifests |
| Evaluation bypass | `evaluation/runner.py` |

### 3.3 Configuration, hashing, and failure behavior

| Fact | Current behavior |
|---|---|
| Auth switch | `TOPO_AUTH_ENABLED`; absent defaults to `false`; only `1/true/yes/on` enable auth; typos fail open to disabled |
| Human registry | `TOPO_API_TOKEN_HASHES_JSON`; JSON object keyed by lowercase SHA-256 digest |
| Human raw-token storage | not stored by backend; deployment environment supplies hashes and metadata |
| Comparison | `hmac.compare_digest` over candidate/configured hexadecimal digests: **constant-time YES** |
| Registry metadata | `subject`, `display_name`, `roles`; unknown metadata ignored |
| Role parsing | only a JSON list is accepted; entries become strings; values are not normalized or allowlisted |
| Missing bearer | 401 with `WWW-Authenticate: Bearer` when auth is enabled |
| Unknown bearer | 401; response does not disclose registry membership beyond validity |
| Empty registry | backend starts; every human bearer is invalid, causing lockout |
| Malformed registry JSON | no startup validation; raises at request time and can become 500 |
| Revocation/expiry | absent for human API tokens |
| Auth logging | no dedicated auth logging; raw Authorization values are not logged by current auth code |
| Credential redaction | change-source ingest allowlists stored headers and recursively redacts known secret-shaped payload keys |

There is no `HTTPBearer`/`APIKeyHeader` dependency for human routes, no user
database, password database, browser session table, JWT issuer, OAuth/OIDC
implementation, CSRF control, or generic service-token registry.

## 4. Principal contract

`AuthPrincipal` is a frozen dataclass with four fields:

| Field | Current origin | Classification | Notes |
|---|---|---|---|
| `subject` | trusted deployment registry metadata; default `unknown` | SECURITY AUTHORITATIVE after successful mapping | approval helper rejects blank/`unknown`; no general validation |
| `display_name` | registry metadata or subject | DISPLAY ONLY | never use for authorization or durable uniqueness |
| `roles` | registry metadata list | SECURITY AUTHORITATIVE under current policy | exact, case-sensitive string checks; client cannot submit roles directly |
| `authentication_type` | server-derived literal | DERIVED | `api_token` or `development` for HTTP human flow |
| token/credential ID | absent | ABSENT | prevents per-credential lifecycle/audit |
| tenant identity | absent | ABSENT | PH-3 owns it |
| arbitrary metadata | absent | ABSENT | do not add unbounded security metadata |

Internal services also construct the same dataclass with
`authentication_type="system"`. Future execution-worker tests use
`internal_service`, but there is no worker HTTP endpoint. Agent authentication
does not create `AuthPrincipal`: `require_agent` returns `TopoAgentRecord` and
sets only `request.state.agent_id`. Provider delivery creates no request
principal; its loaded `ChangeSourceRecord` plus successful provider verifier is
the trusted delivery context.

Roles are trusted only because they are on the server-side credential mapping.
They are not normalized, schema-validated at startup, or bound to a tenant.
PH-2 must retain server derivation; clients, cookies, webhooks, and request
bodies must never assert authoritative roles.

### 4.1 Durable actor use

- Approval records store requester/decider/revoker subjects, display names, and
  roles; append-only approval events also store `authentication_type`.
- Execution intents store creator subject/display/roles/authentication type;
  execution events persist actor subject/display/roles/authentication type;
  reserved internal claims store worker subject/display/authentication type.
- Agent enrollment tokens store `created_by` subject.
- Most ordinary incident/topology/change mutations do not persist the human
  principal today.

Default-off mode means current approval/execution audit rows can legitimately
contain the synthetic development identity. Production must never populate
those audit fields from an anonymous or synthetic fallback.

## 5. Complete route authentication matrix

The live application exposes **132 route objects / 136 method-path pairs**:
127 API routes, four FastAPI docs/schema routes with GET+HEAD, and one health
route. Of the API routes, 118 are human-domain, eight agent-domain, and one
provider-callback-domain.

Definitions used below:

- `Global conditional` means bearer auth only when `TOPO_AUTH_ENABLED=true`;
  the current default instead supplies `development` admin/operator.
- `Sensitive=Yes` means the request or response can carry customer,
  infrastructure, provider, incident, credential, identity, or operational
  data. The sample topology is synthetic and marked No.
- `Mutates=Yes` includes persistence or an external side effect. POST-based
  validation/discovery/predeployment computation is marked No.
- `USER_AUTHENTICATED` says identity only. Existing role checks remain listed;
  PH-5 still owns comprehensive authorization.

| Method | Path | Source | Purpose | Current auth / required? | Current principal | Current role | Sensitive | Mutates | V1 target classification |
|---|---|---|---|---|---|---|---:|---:|---|
| GET, HEAD | `/openapi.json` | FastAPI | OpenAPI schema | Public / no | None | None | Yes | No | DISABLED / SHOULD_NOT_BE_PUBLIC |
| GET, HEAD | `/docs` | FastAPI | Swagger UI | Public / no | None | None | Yes | No | DISABLED / SHOULD_NOT_BE_PUBLIC |
| GET, HEAD | `/docs/oauth2-redirect` | FastAPI | Swagger OAuth redirect helper | Public / no | None | None | Yes | No | DISABLED / SHOULD_NOT_BE_PUBLIC |
| GET, HEAD | `/redoc` | FastAPI | ReDoc UI | Public / no | None | None | Yes | No | DISABLED / SHOULD_NOT_BE_PUBLIC |
| GET | `/api/v1/topology/sample` | `topology.py` | get sample topology | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | No | No | USER_AUTHENTICATED |
| POST | `/api/v1/topology/validate` | `topology.py` | validate snapshot | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/kubernetes/connection` | `kubernetes.py` | check Kubernetes connection | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/kubernetes/discover` | `kubernetes.py` | discover Kubernetes topology | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/snapshots/capture` | `snapshots.py` | capture snapshot | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/snapshots` | `snapshots.py` | list snapshots | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/snapshots/diff` | `snapshots.py` | diff snapshots | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/snapshots/{snapshot_id}` | `snapshots.py` | get snapshot | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/identities/resolve` | `identities.py` | resolve snapshot identities | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/identities/materialize` | `identities.py` | materialize identities | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/identities/stored` | `identities.py` | get stored resolution | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/identities/overrides` | `identities.py` | create identity override | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/identities/overrides` | `identities.py` | list identity overrides | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| DELETE | `/api/v1/identities/overrides/{override_id}` | `identities.py` | deactivate identity override | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/github/connection` | `github.py` | check GitHub connection | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/github/enrich` | `github.py` | enrich snapshot with GitHub | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/github/actions/enrich` | `github.py` | enrich with Actions | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/signals/ingest` | `signals.py` | ingest normalized signals | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/signals/kubernetes/events/ingest` | `signals.py` | ingest Kubernetes events | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/signals` | `signals.py` | list signals | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/signals/{signal_id}` | `signals.py` | get signal | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/changes/from-diff` | `changes.py` | ingest snapshot changes | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/changes` | `changes.py` | list changes | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/changes/{change_id}` | `changes.py` | get change | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/analyze` | `incidents.py` | analyze signal incident | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents` | `incidents.py` | list incident analyses | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{analysis_id}` | `incidents.py` | get incident analysis | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/recommendations/generate` | `recommendations.py` | generate recommendations | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/recommendations` | `recommendations.py` | list recommendations | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/recommendations/{recommendation_id}` | `recommendations.py` | get recommendation | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| PATCH | `/api/v1/recommendations/{recommendation_id}/status` | `recommendations.py` | change recommendation status | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/recovery/verify` | `recovery.py` | verify recovery | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/recovery` | `recovery.py` | list recovery verifications | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/recovery/{verification_id}` | `recovery.py` | get recovery verification | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/orchestration/signals/{signal_id}/run` | `orchestration.py` | run signal orchestration | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incident-records` | `incident_records.py` | list incident records | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incident-records/{incident_id}/signals` | `incident_records.py` | get incident signals | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incident-records/{incident_id}` | `incident_records.py` | get incident record | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| PATCH | `/api/v1/incident-records/{incident_id}/status` | `incident_records.py` | update incident status | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/blast-radius` | `blast_radius.py` | get blast radius | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/predeployment/analyze` | `predeployment.py` | analyze planned change | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/ownership/mappings` | `ownership.py` | create ownership mapping | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/ownership/mappings` | `ownership.py` | list ownership mappings | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/ownership/resolve` | `ownership.py` | resolve ownership | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/ownership-impact` | `ownership.py` | get incident ownership impact | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/integrations/webhooks` | `webhooks.py` | create outbound webhook | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/integrations/webhooks` | `webhooks.py` | list outbound webhooks | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| PATCH | `/api/v1/integrations/webhooks/{webhook_id}` | `webhooks.py` | update outbound webhook | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/integrations/webhooks/{webhook_id}/test` | `webhooks.py` | test outbound webhook | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/integrations/deliveries` | `webhooks.py` | list webhook deliveries | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/snapshots/{snapshot_id}/network-dependencies` | `network_dependencies.py` | get network dependencies | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/explanations` | `incident_explanations.py` | create explanation | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/explanations/latest` | `incident_explanations.py` | get latest explanation | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/explanations` | `incident_explanations.py` | list explanations | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/copilot/sessions` | `incident_copilot.py` | create Copilot session | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/copilot/sessions` | `incident_copilot.py` | list Copilot sessions | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/copilot/sessions/{session_id}` | `incident_copilot.py` | get Copilot session | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/copilot/sessions/{session_id}/messages` | `incident_copilot.py` | post Copilot message | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/investigation-plans` | `investigation_plans.py` | create investigation plan | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/investigation-plans` | `investigation_plans.py` | list investigation plans | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/investigation-plans/{plan_id}` | `investigation_plans.py` | get investigation plan | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| PATCH | `/api/v1/incidents/{incident_id}/investigation-plans/{plan_id}/steps/{step_id}` | `investigation_plans.py` | update investigation step | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/reports` | `post_incident_reports.py` | create incident report | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/reports` | `post_incident_reports.py` | list incident reports | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/reports/{report_id}` | `post_incident_reports.py` | get incident report | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| PATCH | `/api/v1/incidents/{incident_id}/reports/{report_id}` | `post_incident_reports.py` | update incident report | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| PATCH | `/api/v1/incidents/{incident_id}/reports/{report_id}/actions/{action_item_id}` | `post_incident_reports.py` | update report action | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/reports/{report_id}/export` | `post_incident_reports.py` | export incident report | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/system/whoami` | `system.py` | return current identity | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/agents/{agent_id}/cloud-status` | `agents.py` | get agent cloud status | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/agents/enrollment-tokens` | `agents.py` | create enrollment token | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin` | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/agents/enroll` | `agents.py` | enroll agent | Enrollment token / yes | prospective agent; record on success | Enrollment credential | Yes | Yes | AGENT_AUTHENTICATED |
| GET | `/api/v1/agents` | `agents.py` | list agents | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/agents/{agent_id}` | `agents.py` | get agent | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/agents/{agent_id}/health` | `agents.py` | get agent health | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/agents/{agent_id}/revoke` | `agents.py` | revoke agent | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin` | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/agents/{agent_id}/plugins` | `agents.py` | get agent plugins | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/agents/{agent_id}/sensors` | `agents.py` | get runtime sensors | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/agents/{agent_id}/runtime-dependencies` | `agents.py` | get runtime dependencies | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/agent/config` | `agents.py` | get runtime config | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | No | AGENT_AUTHENTICATED |
| POST | `/api/v1/agent/heartbeat` | `agents.py` | submit agent heartbeat | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | Yes | AGENT_AUTHENTICATED |
| POST | `/api/v1/agent/snapshots` | `agents.py` | submit topology snapshot | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | Yes | AGENT_AUTHENTICATED |
| POST | `/api/v1/agent/runtime/heartbeat` | `agents.py` | submit sensor heartbeat | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | Yes | AGENT_AUTHENTICATED |
| POST | `/api/v1/agent/runtime/batches` | `agents.py` | submit runtime batch | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | Yes | AGENT_AUTHENTICATED |
| POST | `/api/v1/agent/change-events` | `agents.py` | submit change events | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | Yes | AGENT_AUTHENTICATED |
| POST | `/api/v1/agent/signals` | `agents.py` | submit failure signals | Agent Bearer dependency / yes | `TopoAgentRecord` + `state.agent_id` | agent identity | Yes | Yes | AGENT_AUTHENTICATED |
| GET | `/api/v1/clouds/accounts` | `clouds.py` | list cloud accounts | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/clouds/resources` | `clouds.py` | list cloud resources | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/clouds/topology` | `clouds.py` | get cloud topology | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/change-events` | `change_events.py` | create change event | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/change-events` | `change_events.py` | list change events | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/change-events/{event_id}` | `change_events.py` | get change event | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/change-events/{event_id}/correlate` | `change_events.py` | correlate change event | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/change-events` | `change_events.py` | get incident changes | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/suspected-change-events` | `change_events.py` | rank suspected changes | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/change-sources` | `change_sources.py` | create change source | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/change-sources` | `change_sources.py` | list change sources | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/change-sources/deliveries` | `change_sources.py` | list source deliveries | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/change-sources/dead-letters` | `change_sources.py` | list dead letters | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/change-sources/dead-letters/{dead_letter_id}/replay` | `change_sources.py` | replay dead letter | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/change-sources/{source_id}` | `change_sources.py` | get change source | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| PATCH | `/api/v1/change-sources/{source_id}` | `change_sources.py` | update change source | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/change-sources/{source_id}/doctor` | `change_sources.py` | diagnose change source | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/change-source-webhooks/{source_id}` | `change_source_webhooks.py` | receive provider callback | Provider verifier / yes | trusted `ChangeSourceRecord`; no `AuthPrincipal` | provider source | Yes | Yes | PROVIDER_CALLBACK_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/causal-rca` | `causal_rca.py` | create causal analysis | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/causal-rca/latest` | `causal_rca.py` | get latest causal analysis | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/causal-analyses/{analysis_id}` | `causal_rca.py` | get causal analysis | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/operational-context` | `incident_context.py` | get operational context | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/response-plan` | `response_plan.py` | get response plan | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/outcome` | `incident_outcome.py` | get incident outcome | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/outcome` | `incident_outcome.py` | record incident outcome | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/historical-intelligence` | `incident_memory.py` | get historical intelligence | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/response-intelligence` | `response_intelligence.py` | get response intelligence | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/lifecycle-status` | `incident_briefing.py` | get lifecycle status | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/briefing` | `incident_briefing.py` | get incident briefing | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/execution-readiness` | `execution_readiness.py` | get execution readiness | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/approvals` | `action_approvals.py` | create approval request | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin\|operator` | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/approvals` | `action_approvals.py` | list approval history | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | authenticated only | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/approvals/{approval_id}` | `action_approvals.py` | get approval request | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | authenticated only | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/approvals/{approval_id}/approve` | `action_approvals.py` | approve request | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin\|operator` | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/approvals/{approval_id}/reject` | `action_approvals.py` | reject request | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin\|operator` | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/approvals/{approval_id}/revoke` | `action_approvals.py` | revoke request | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin\|operator` | Yes | Yes | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/execution-intents` | `execution_intents.py` | create execution intent | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin\|operator` | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/execution-intents` | `execution_intents.py` | list execution intents | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | authenticated only | Yes | No | USER_AUTHENTICATED |
| GET | `/api/v1/incidents/{incident_id}/execution-intents/{execution_id}` | `execution_intents.py` | get execution intent | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | authenticated only | Yes | No | USER_AUTHENTICATED |
| POST | `/api/v1/incidents/{incident_id}/execution-intents/{execution_id}/cancel` | `execution_intents.py` | cancel execution intent | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | `admin\|operator` | Yes | Yes | USER_AUTHENTICATED |
| GET | `/api/v1/automation/status` | `automation.py` | get lifecycle automation status | Global conditional / no by default | `AuthPrincipal(api_token\|development)` | None | Yes | No | USER_AUTHENTICATED |
| GET | `/health` | `main.py` | process liveness/version | Public / no | None | None | No | No | PUBLIC_LIVENESS |

No route is `UNKNOWN`. There is no current readiness, metrics, root, or
standalone version route. CORS-generated `OPTIONS` preflight is a narrow
non-business `PUBLIC_CORS_PREFLIGHT` transport exception, not an anonymous
authority to invoke the underlying method.

## 6. Public endpoint inventory and target policy

### 6.1 Current state

| Surface | Current state | Current exposure |
|---|---|---|
| `/health` | implemented; returns only status, service, version | public GET; not in schema |
| liveness | `/health` serves this purpose | does not inspect database or provider state |
| readiness | absent | no way to distinguish alive from ready after startup |
| metrics | absent | no metrics endpoint |
| OpenAPI | `/openapi.json` | public |
| Swagger | `/docs`, `/docs/oauth2-redirect` | public |
| ReDoc | `/redoc` | public |
| root/version | absent | `/` is allowlisted by middleware but returns 404; version appears in health |

The existing health payload is appropriately minimal and does not expose
database revision, cluster name, customer data, provider configuration, token
configuration, or stack traces. It is liveness, not readiness. Database
startup currently fails before traffic when persistence preflight fails, but
there is no bounded runtime readiness contract.

### 6.2 Exact V1 public policy

1. `GET /health` remains `PUBLIC_LIVENESS` with its current minimal payload.
2. Add one minimal `GET /ready` as `PUBLIC_READINESS_MINIMAL`: return only
   `{"status":"ready"}` with 200 or `{"status":"not_ready"}` with 503. Never
   expose database URL/schema revision, providers, clusters, tenants, or error
   internals.
3. Browser `OPTIONS` preflight may remain unauthenticated only as a transport
   exception evaluated by an explicit origin policy.
4. In production, set FastAPI `docs_url`, `redoc_url`, and `openapi_url` to
   `None`. Docs/schema are `DISABLED / SHOULD_NOT_BE_PUBLIC`, not security by
   obscurity. Development may expose them under the explicit development mode.
5. Metrics are absent. A future metrics route must be
   `INTERNAL_SERVICE_AUTHENTICATED` or network-private and separately reviewed;
   it is not part of the public route set.
6. Do not add a public root/version endpoint. The allowlisted-but-absent `/`
   entry should not survive the target route classifier.

The exact target public business-route set is therefore `/health` and `/ready`
only; CORS preflight is not a business route.

## 7. Browser/frontend authentication audit

The frontend uses a central `apiRequest` helper in `frontend/lib/topo-api.ts`.
Its base is `NEXT_PUBLIC_TOPO_API_URL`, defaulting to
`http://127.0.0.1:8000`. It sends `Accept: application/json`, optional content
headers, and `cache: no-store`. It sends no `Authorization` header and does not
set `credentials`. The browser default would send cookies only for same-origin
requests; the current normal development topology (`:3000` to `:8000`) is
cross-origin, so it has no cookie credential path. The incident-report export
is a direct backend anchor URL and likewise cannot attach a bearer header.

Static search found:

- no login or logout UI;
- no whoami/session bootstrap flow;
- no localStorage/sessionStorage token use;
- no JavaScript cookie handling;
- no auth-aware Next middleware or route guard;
- no direct auth/OIDC dependency;
- no authenticating/authenticated/expired/forbidden state machine; and
- generic `Error` handling for all non-2xx responses, with no stable 401/403
  distinction.

The browser therefore **cannot authenticate today**. It must not be repaired by
shipping a privileged bearer token in source, a `NEXT_PUBLIC_*` variable, a
JavaScript bundle, or localStorage.

### 7.1 Browser options evaluated

| Option | Security | Complexity / usability | Decision |
|---|---|---|---|
| A. Browser-held bearer API token | exposes a long-lived credential to JavaScript/XSS; localStorage persists theft; logout is local only | superficially simple, poor revocation and expiry | Reject as V1 primary browser auth |
| B. Server-side opaque session with HttpOnly cookie | raw session unavailable to JavaScript; server expiry/revocation; requires CSRF and session persistence | moderate; strong private-beta UX; compatible with PH-3/PH-5 | **Selected** |
| C. External OIDC plus Topo session | strongest enterprise identity/lifecycle when configured correctly | new provider/config/callback/logout complexity; no current implementation | Optional later PH-2 extension, not initial V1 gate |
| D. Reverse-proxy authenticated identity | can be sound only if Topo trusts a specific proxy and strips spoofed headers | deployment-coupled, fragile without PH-6 network boundary | Not primary; later reviewed deployment option |
| E. Same-origin web facade/BFF | improves cookie routing and keeps backend credentials server-side; is not itself identity authority | small deployment/frontend transport change | Use as the transport companion to B, not a separate auth mechanism |

### 7.2 Recommended browser contract

Deploy the web UI and API behind one Topo origin (or a reviewed same-site
layout) and use relative `/api` access. A human submits a high-entropy operator
credential once to a TLS-protected session-exchange endpoint. The raw
credential exists only in the transient login form/request, never persistent
browser storage. The backend issues an opaque session whose digest and
principal snapshot are server-side and sets:

```text
HttpOnly = true
Secure = true in every production-shaped deployment
SameSite = Lax
Path = /
bounded absolute expiry + bounded idle expiry
```

Unsafe methods require a CSRF token bound to the session and supplied in a
custom header. Login has strict Origin validation; logout revokes the server
session and expires the cookie. Frontend state must explicitly represent
unauthenticated, authenticating, authenticated, expired, forbidden, logout,
and backend-unavailable. No incident/topology/customer data renders before
authentication completes.

## 8. Human CLI/API audit

The CLI already supplies a coherent bearer path:

```text
profile token_env (default TOPO_API_TOKEN)
  -> environment value if present
  -> otherwise OS keyring service topo-ai-cli / profile name
  -> Authorization: Bearer <token>
  -> /api/v1/system/whoami for login verification
```

The JSON profile stores only API URL, token environment-variable name, TLS,
timeouts, retry policy, and capture path. It does not store the token. `topo
login` uses a hidden prompt or `--token-stdin`, verifies `whoami`, then stores
the token in the OS keyring. `topo logout` deletes only the local keyring entry;
it does not revoke the server credential. TLS verification is on by default
but `--insecure` is available. The CLI does not offer a human `--token` option,
which avoids one direct shell-history path; operators can still expose secrets
through careless environment-setting commands or process environments.

Current 401 and 403 responses both become `AuthenticationFailure` with exit
code 4. V1 must retain exit 4 for 401 and add a distinct forbidden error/exit
for 403 so callers can distinguish invalid identity from insufficient rights.

Current static hash registry classification:

| Use | Classification |
|---|---|
| initial/recovery bootstrap | VALID BOOTSTRAP AUTH when provisioned and rotated explicitly |
| local development and focused tests | VALID DEVELOPMENT AUTH |
| bounded service automation | TEMPORARY COMPATIBILITY ONLY until named lifecycle exists |
| permanent human login | NOT PRODUCTION-SUITABLE |
| initial PH-2B compatibility | VALID TRANSITIONAL AUTH |

V1 CLI/API automation should use named high-entropy bearer credentials with a
server credential ID, stable principal, type (`human_api` or `service_api`),
bounded expiry, revocation, last-used time, and audit. The CLI may keep its
existing environment/keyring transport. Raw tokens are returned exactly once.
Human and service credentials must not authenticate agent or provider routes.

## 9. Topo Agent authentication flow

### 9.1 Enrollment

1. A human `admin` calls `POST /api/v1/agents/enrollment-tokens`.
2. Backend generates `topo_enroll_` plus 32 URL-safe random bytes, stores only
   SHA-256 and a hint, and returns the raw credential once.
3. Record carries label, `max_uses`, `use_count`, expiry, last-use, revocation,
   creator subject, and timestamps.
4. Agent sends the enrollment token in the JSON body to the globally bypassed
   exact `/api/v1/agents/enroll` path.
5. Repository looks up the digest, checks revoked/expiry/use count, creates a
   bound agent record, increments use count, and returns a new `topo_agent_`
   token once.

The enrollment endpoint reports invalid/revoked/expired/used distinctions.
Because the token is high entropy, this is not username enumeration, but V1 may
normalize outward messages while retaining internal diagnostics.

### 9.2 Steady state

All seven `/api/v1/agent/*` routes bypass human middleware and use
`require_agent`. It extracts a Bearer token, hashes it with SHA-256, performs a
database equality lookup, rejects missing/unknown/revoked tokens with 401, sets
`request.state.agent_id`, and returns the durable `TopoAgentRecord`. The agent
record binds ID, cluster, environment, namespace scope, capabilities, and
metadata. Snapshot/signal ingestion additionally validates cluster and
namespace against that binding.

Agent digest lookup is not an application-level constant-time comparison; it
is a database equality query over a high-entropy digest. Agent credentials
have revocation but no expiry or rotation flow.

The raw agent token is loaded from `TOPO_AGENT_TOKEN` or plaintext
`credentials.json`. On non-Windows the client attempts mode `0600`; no
equivalent Windows ACL hardening is implemented. Kubernetes manifests read it
from a Kubernetes Secret. Server storage contains hash and hint only. File/
Kubernetes secret custody is a PH-4 concern.

### 9.3 Concurrency prerequisite

PH-1 measured a lost update for concurrent enrollment-token consumption. PH-2
**does depend** on `max_uses` as a security invariant. Therefore this is a
**PH-2 SECURITY PREREQUISITE** before claiming one-use enrollment safety:

```text
atomically consume one enrollment use
WHERE not revoked
  AND not expired
  AND use_count < max_uses
and create the agent in the same transaction
```

The implementation must use a conditional update/row lock appropriate to
SQLite/PostgreSQL tests and require exactly one affected row. It must preserve
the existing credential model and belongs in the narrow agent-boundary PH-2
block, not wait for general PH-10 counter work.

### 9.4 Human/agent collision rule

Human and agent credentials both use the HTTP Bearer scheme, so correctness
depends on route classification. Current explicit path bypass prevents double
authentication. V1 must centralize and test this delegation: an agent token is
accepted only by agent routes; a human token is not accepted there; valid
agent traffic never also needs a human token. Token prefixes are useful format
guards, not authorization by themselves.

## 10. Inbound webhook/provider authentication

There is one callback path, parameterized by a human-created change source:

`POST /api/v1/change-source-webhooks/{source_id}`. Human global auth bypasses
it, but it is not unauthenticated. The service loads the source, resolves the
configured `secret_ref` from an environment variable, verifies raw bytes
before parsing or storing, then deduplicates by source plus provider delivery
identity/payload hash.

| Provider | Current authentication | Replay/idempotency behavior |
|---|---|---|
| GitHub | `X-Hub-Signature-256`, HMAC-SHA256, constant-time compare | delivery ID/payload-hash dedupe; no timestamp window |
| GitLab signing mode | webhook ID + timestamp + `Webhook-Signature`, HMAC-SHA256, constant-time compare | default 300-second window plus delivery dedupe |
| GitLab secret-token mode | `X-Gitlab-Token`, constant-time shared-secret compare | delivery/event ID or payload dedupe; no timestamp window |
| HCP Terraform | `X-TFE-Notification-Signature`, HMAC-SHA512, constant-time compare | run/config ID or payload dedupe; no timestamp window |
| Jenkins | `X-Topo-Signature-256`, HMAC-SHA256, constant-time compare | deterministic delivery/payload dedupe; no timestamp window |
| Azure DevOps | HTTP Basic username plus environment-resolved secret, constant-time field compares | provider ID/payload dedupe; no timestamp window |

No supported inbound provider route is unsigned/unverified. Provider-specific
verification failures become generic 401. Unknown source IDs currently return
404 before signature verification, and valid deliveries have no provider
`AuthPrincipal`; they use a trusted source/delivery context. PH-2D should
regression-test failure non-disclosure, body verification order, replay bounds,
dedupe, and global-auth separation. Broader secret storage remains PH-4.

## 11. Outbound webhook and provider credential boundaries

Outbound webhook configuration/list/update/test/delivery routes are human-
domain routes and must be `USER_AUTHENTICATED`. Delivery execution is internal
service behavior. Remote signing secrets and arbitrary headers are credentials
used **by Topo to a remote destination**, not identities authenticating callers
to Topo. They remain a PH-4 secret-boundary concern. Current output models use
`has_signing_secret`, but storage includes plaintext signing secret and headers.

Other outbound credentials are likewise outside human authentication:

- backend GitHub calls use `TOPO_GITHUB_TOKEN`;
- backend Kubernetes discovery uses kubeconfig or in-cluster identity;
- agent AWS uses SDK profile/default chain and optional role/external ID;
- agent Azure uses CLI, managed identity, workload identity, or default chain;
- agent GCP uses application default credentials and optional impersonation;
- provider webhook `secret_ref` identifies an environment variable; and
- OpenAI uses `OPENAI_API_KEY` for optional narrative services.

None may become a Topo login token. PH-4 owns storage, rotation, least
privilege, redaction, and provider-access policy. The tracked GitHub token-
shaped value described in the executive finding is a critical PH-4 incident
and must be rotated before any design-partner use.

## 12. Approval/execution identity assumptions

The dormant 14G/14H HTTP routes are still reachable under the standard human
domain. List/get operations require an `AuthPrincipal` explicitly. Create,
approve, reject, revoke, create-intent, and cancel require a stable non-
`unknown` subject plus exact `admin` or `operator` role. High-risk approval
logic and worker-vs-human restrictions remain service-layer controls.

Current disabled auth satisfies every human control-plane gate as
`local-development` with `admin,operator`; those mutations are therefore
possible without a real production credential. The target must never persist
that synthetic identity in production. Existing actor fields and
`authentication_type` must survive session/API-token hardening unchanged in
meaning. A browser session should yield `authentication_type="session"`; a
named CLI token should yield `human_api_token` or `service_api_token`.

Execution worker identity is server-derived and rejects `development`,
`api_token`, and `human_api_token`. There is no public claim endpoint and PH-2
must not add one or activate execution.

## 13. Existing authorization inventory

| Rule | Location | Current policy | Classification |
|---|---|---|---|
| Any authenticated principal | global middleware and `authenticated_principal` | identity required only when global auth enabled | KEEP FOR PH-2; default-on fixes enforcement |
| Agent enrollment-token creation | `api/agents.py::_require_admin` | exact `admin` | KEEP FOR PH-2; PH-5 owns consolidation |
| Agent revocation | `api/agents.py::_require_admin` | exact `admin` | KEEP FOR PH-2; PH-5 owns consolidation |
| Approval state mutation | `approval_control_principal` | exact `admin` or `operator`, stable subject | KEEP FOR PH-2; DORMANT EXECUTION ONLY |
| Execution-intent create/cancel | `approval_control_principal` | exact `admin` or `operator`, stable subject | KEEP FOR PH-2; DORMANT EXECUTION ONLY |
| Approval/execution reads | route calls `authenticated_principal` | any authenticated principal | KEEP FOR PH-2; PH-5 OWNS REDESIGN |
| Other read/mutation routes | none beyond global identity | no roles | SECURITY GAP; PH-5 owner |
| Worker claim services | internal `_worker_principal` | server-derived, non-human authentication type | DORMANT EXECUTION ONLY |

Current role names with access-control meaning are `admin` and `operator`.
`viewer` appears in tests as a denied principal but is not a global read-policy
role. String checks are case-sensitive. Checks are only partly centralized.
Development defaults to `admin,operator`. Registry roles are server-mapped,
not request-supplied, but malformed/unknown roles are not rejected at startup.

PH-2 must preserve current gates and deliver a real principal. It must not
claim that the absence of route-specific roles is acceptable authorization;
PH-5 owns minimum RBAC across the product.

## 14. Authentication versus tenancy

Authentication answers who called. Authorization answers what that identity
may do. Tenancy answers which customer's records the operation may touch.
Current principal and all current domain tables have no tenant identity.

Therefore:

- authenticated principal does **not** imply tenant access;
- PH-2 adds no `tenant_id` to domain records;
- PH-2 credential/session records must be structurally ready for a future
  membership binding but must not invent one;
- PH-3 owns tenant identity, membership, query scoping, uniqueness, background
  work, and historical-record isolation; and
- PH-5 owns role policy within the tenant boundary.

## 15. Current default and target mode contract

### 15.1 Current state table

| Input/state | Current result |
|---|---|
| auth config absent | auth disabled; development admin/operator |
| `TOPO_AUTH_ENABLED=false` | auth disabled; development admin/operator |
| malformed/unknown boolean | auth disabled; development admin/operator |
| enabled + registry absent/empty | every human token invalid; no startup failure |
| enabled + missing/malformed bearer | 401 |
| enabled + unknown bearer | 401 |
| revoked/expired human token | unsupported |
| malformed registry JSON | request-time runtime failure, not startup validation |
| malformed roles | empty roles rather than config rejection |
| middleware internal exception | normal unhandled server error; no controlled auth category |

### 15.2 Frozen V1 modes

Replace the boolean's fail-open semantics with one narrow explicit contract:

| Mode | Selection | Behavior |
|---|---|---|
| `required` | default when mode absent | all non-public routes delegate to exactly one required human, agent, provider, or internal auth domain; missing authority/config fails closed |
| `development-disabled` | explicit local choice only | synthetic development principal allowed; startup emits an unmistakable warning; reject this mode with non-SQLite production persistence |

Do not create a generic environment/profile framework. During compatibility,
legacy `TOPO_AUTH_ENABLED=true` may map to `required`; `false`, malformed, or
ambiguous legacy values must not silently disable auth. Disabling requires the
explicit new mode.

In `required`, malformed registry/principal/role configuration is a startup
error. If no valid bootstrap, named credential authority, or configured OIDC
authority exists, startup/readiness fails closed rather than becoming admin or
silently serving a locked, unexplained system. Public liveness may remain
minimal; readiness must be false.

No network-address heuristic decides security mode. The development exception
is explicit and additionally bounded to the retained SQLite development role.

## 16. Development, test, and evaluation policy

Current tests commonly call the full app anonymously and inherit default-off
development identity. A small set explicitly toggles `TOPO_AUTH_ENABLED`; unit
tests also construct `AuthPrincipal` or `SimpleNamespace(request.state)`
directly. `evaluation/runner.py` explicitly starts an isolated backend with
`TOPO_AUTH_ENABLED=false` and waits on `whoami`.

Target policy:

- **Development:** only explicit `development-disabled` plus SQLite may use the
  synthetic principal. Never default. Display/log a warning and expose the
  development auth type through `whoami`.
- **Unit/API tests:** use an app factory or test-only dependency/middleware
  injection fixture that is import-scoped to tests, not activated by a product
  environment variable. Security regressions must run the real `required`
  path.
- **Evaluation:** do not bypass. The harness deterministically generates an
  ephemeral high-entropy token, passes only its digest/mapped evaluation
  principal to the isolated backend, and uses the raw token only in the
  harness client. It still runs `required` and needs no external IdP.
- **Production/default:** `required`; synthetic principal impossible.

This preserves deterministic evaluation without a runtime production bypass.
Tests that currently depend implicitly on default-off must change during PH-2,
and dedicated regressions must prove absent/malformed config cannot activate a
development principal.

## 17. CORS, cookies, and CSRF

Current CORS allows these exact origins:

```text
http://localhost:3000
http://127.0.0.1:3000
http://localhost:5173
http://127.0.0.1:5173
https://topo-ai-hxhm.vercel.app
```

It sets `allow_credentials=True`, with all methods and headers. There is no
wildcard origin, so the prohibited wildcard-origin plus credential combination
is not present. The fixed Vercel origin and broad method/header allowances are
still hard-coded rather than deployment configuration. Current bearer CLI/API
auth is not subject to browser CSRF, but the selected cookie design is.

PH-2C must:

- prefer same-origin production UI/API and relative API paths;
- make allowed development origins explicit configuration;
- remove unused production cross-origin entries;
- send credentials only through the same-origin session design;
- require Origin validation and a session-bound CSRF header for POST/PATCH/
  PUT/DELETE;
- exempt provider/agent routes from browser CSRF because they do not use human
  cookies, while retaining their own authentication; and
- ensure login/logout/session endpoints have purpose-specific CSRF/Origin
  rules.

## 18. First-admin/bootstrap contract

Options considered were an environment-provisioned digest, a durable one-time
token, a local CLI bootstrap, and OIDC administrator mapping. OIDC is not yet
present; a durable one-time-token workflow would require the session/credential
schema before the first secure start; auth-disabled bootstrap is prohibited.

The selected V1 bootstrap is an **environment-provisioned high-entropy
bootstrap token digest with server-side principal metadata**:

1. Operator generates the raw token offline; only its SHA-256 digest and a
   stable admin subject/display/role mapping enter deployment secret config.
2. No raw token is committed, browser-bundled, logged, or persisted by Topo.
3. Over TLS, the operator uses it through `topo login --token-stdin` or the
   transient browser session exchange.
4. The first authenticated admin creates named, expiring operational
   credential(s) and verifies recovery.
5. The bootstrap mapping is then removed and deployment config rotated. A new
   out-of-band digest can recover a locked installation.
6. Every resulting session/credential/audit actor uses the mapped stable
   subject; never `unknown` and never the development principal.

Bootstrap is not a global auth bypass and does not imply tenant ownership. A
backend-enforced one-use bootstrap may be added only with an atomic consume
contract; the initial V1 operational contract uses explicit removal/rotation.

## 19. Token and session lifecycle

Current human API credentials have none of creation, expiration, server
revocation, last-use, naming, scopes, lifecycle audit, or recovery beyond
editing deployment configuration. Roles and display fields live in config.

Before design-partner use, minimum named API credential lifecycle is:

- high-entropy raw secret returned once;
- digest-only persistence;
- stable credential ID and non-secret hint/name;
- explicit `human_api` or `service_api` caller type;
- stable subject/display and server-derived roles;
- created-by/created-at, bounded expiry, revoked-by/revoked-at;
- last-used time updated safely and never used as the sole authorization
  invariant;
- list/revoke/rotate recovery that never returns the digest or raw token; and
- audit without secret material.

Minimum browser session lifecycle is opaque random secret, digest-only record,
stable session ID, principal snapshot/source credential reference, issued/
absolute-expiry/idle-expiry/last-seen/revoked timestamps, CSRF binding, logout,
and administrative revocation. A role or credential revocation must invalidate
affected sessions within a bounded period; session expiry must produce 401.

No general scopes are designed in PH-2; PH-5 roles remain the authority. Token
rotation creates a new credential and revokes the old one rather than mutating
secret material in place.

## 20. Password and OIDC decision

Topo has no user/password database, password hashing, reset, MFA, or recovery
system. **Topo-managed password authentication is not required and must not be
introduced for V1.** It would create a larger identity-security product than
the private-beta requirement.

**OIDC is optional, not required for the initial V1 private beta.** It is the
preferred later enterprise human identity authority and should still terminate
in the same Topo server-side session/principal contract. Do not claim SSO until
issuer/audience/nonce/state/PKCE, key rotation, group mapping, logout, and
failure tests exist. OIDC identities still require PH-3 tenant membership and
PH-5 role mapping.

## 21. Error semantics, logging, and observability

Freeze:

- 401 `UNAUTHENTICATED`: missing, malformed, invalid, expired, or revoked human
  credential/session;
- 403 `FORBIDDEN`: valid principal lacks authorization;
- stable generic outward detail that does not disclose whether a subject,
  session, credential ID, or token exists;
- provider/agent failures remain bounded and credential-free; and
- malformed server auth configuration fails startup/readiness, not a random
  protected request.

Current human middleware correctly uses 401 and `WWW-Authenticate: Bearer` for
missing/invalid bearer. Approval helpers correctly use 403 for stable-subject
or role failures. CLI currently conflates both and must change.

The current auth code does not log Authorization, raw tokens, cookies, token
hashes, or signing secrets, and webhook ingest stores only allowlisted headers
plus redacted payloads. Preserve that. V1 auth telemetry may log mechanism,
coarse success/failure category, route class, correlation ID, and successful
subject/credential ID. It must never log credential headers, cookies, CSRF
secrets, raw/digested tokens, provider signing material, or full credential-
bearing configuration. Authentication error objects must also be rendered
through credential-safe messages.

## 22. Caller taxonomy

| Caller | Credential | Principal/context | Route class | Human RBAC? | PH-3 tenancy later? |
|---|---|---|---|---:|---:|
| HUMAN_BROWSER | opaque server session cookie + CSRF on unsafe methods | `AuthPrincipal(authentication_type=session)` | USER_AUTHENTICATED | Yes | Yes |
| HUMAN_CLI_OR_API | named high-entropy bearer API credential | human or service API principal; caller type explicit | USER_AUTHENTICATED | Yes for human; service policy later | Yes |
| TOPO_AGENT | enrollment token once; dedicated agent bearer thereafter | durable `TopoAgentRecord` / agent principal | AGENT_AUTHENTICATED | No | Agent enrollment/account binding in PH-3 |
| INBOUND_PROVIDER_WEBHOOK | provider signature, secret token, or Basic credential | trusted source/delivery context | PROVIDER_CALLBACK_AUTHENTICATED | No | Change source ownership in PH-3 |
| INTERNAL_BACKGROUND_WORKER | in-process server-derived system identity; future explicit service credential only if crossing a network | system/internal-service principal | INTERNAL_SERVICE_AUTHENTICATED | No human RBAC | Tenant job context in PH-3 |
| OUTBOUND_PROVIDER_CLIENT | provider SDK/OAuth/workload credentials used by Topo | no Topo caller principal | not an inbound route class | No | provider account ownership in PH-3 |

One credential cannot cross caller classes merely because it is a Bearer
string. Route classification selects the authentication authority first;
credential verification occurs second.

## 23. Trust-boundary architecture

```text
Browser
  -> transient bootstrap/operator credential exchange
  -> opaque HttpOnly Topo session + CSRF
  -> Human Principal
  -> USER_AUTHENTICATED API

CLI / API automation
  -> named human_api/service_api bearer credential
  -> Human/Service Principal
  -> USER_AUTHENTICATED API

Topo Agent
  -> enrollment credential -> dedicated agent bearer
  -> Agent Record / Agent Principal
  -> AGENT_AUTHENTICATED ingest API

GitHub / GitLab / Jenkins / Azure DevOps / HCP Terraform
  -> provider-specific signature/shared-secret verification
  -> trusted ChangeSource delivery context
  -> PROVIDER_CALLBACK_AUTHENTICATED change ingest

Internal background operation
  -> server-derived system identity (or future explicit service credential)
  -> internal service operation

Topo -> cloud/source/provider
  -> outbound provider credential
  -> external provider API
  [not an identity into Topo]
```

## 24. Persistence and migration implication

**Persistent auth tables required: YES. Future additive migration required:
YES. Revision family: `0002+`; never modify `0001_current_schema`.**

The minimum purpose-only schema is:

1. `auth_api_credentials`: credential ID, digest, non-secret hint/name, caller
   type, subject/display, roles snapshot, created-by/time, expiry, revocation,
   last-used, and timestamps.
2. `auth_sessions`: session ID, session-secret digest, principal snapshot,
   source credential reference, CSRF binding digest, issued/absolute-expiry/
   idle-expiry/last-seen/revoked timestamps.

No password table, tenant column, OIDC binding, group model, permission graph,
or provider secret belongs in this migration. Exact DDL, constraints,
PostgreSQL/SQLite behavior, concurrent revocation/last-use semantics, and
Alembic downgrade policy require their implementation block's review.

## 25. Security risk matrix

| Risk | Current behavior | Severity | PH-2 impact | Owner block | Before design partner? |
|---|---|---|---|---|---:|
| auth disabled by default | 118 human API routes get synthetic identity | Critical | make default `required` | PH-2B | Yes |
| development admin fallback | admin/operator can mutate dormant and product state | Critical | explicit SQLite-only development exception | PH-2B | Yes |
| malformed auth flag fails open | unknown value disables auth | Critical | validated enum and startup fail closed | PH-2B | Yes |
| browser has no credential path | secure backend makes UI unusable | Critical | opaque session, login/logout/expiry UX | PH-2C | Yes |
| tracked provider token-shaped value | credential exposed in tracked example/history | Critical | no direct PH-2 change; rotate and remediate immediately | PH-4 | Yes |
| static API-token lifecycle | no ID/expiry/revoke/audit/last-use | High | named credential lifecycle | PH-2E | Yes |
| empty/malformed registry | lockout or request-time 500 | High | startup validation/recovery | PH-2B | Yes |
| agent enrollment lost update | concurrent max-use can be exceeded | High | atomic security prerequisite | PH-2D | Yes |
| agent/human auth collision | both use Bearer; safety depends on path bypass | High | central route-domain dispatch + negative tests | PH-2B/2D | Yes |
| webhook/global-auth collision | default-on could demand human plus signature | High | provider route delegation + negative tests | PH-2B/2D | Yes |
| public docs/OpenAPI | API structure public | Medium | disable production docs/schema | PH-2B | Yes |
| no readiness | liveness cannot express safe traffic readiness | Medium | minimal public readiness | PH-2B | Yes |
| CORS/cookie mismatch | hard-coded origins, credential flag, broad methods/headers | High under sessions | same-origin + explicit CORS/CSRF | PH-2C | Yes |
| provider replay windows uneven | most providers rely on dedupe without time window | Medium/High | preserve auth; review bounded replay per provider | PH-2D/PH-4 | Yes for enabled provider |
| agent raw-token file custody | plaintext JSON; Windows ACL not hardened | High | identity remains; secret custody repair | PH-4 | Yes |
| plaintext outbound webhook secrets/headers | durable DB plaintext | Critical | do not conflate with login; encrypt/externalize | PH-4 | Yes |
| tenant isolation absent | identity cannot bound customer data | Critical | explicitly no tenant implication | PH-3 | Yes |
| incomplete role policy | most mutations require identity only | High | preserve current gates; comprehensive policy later | PH-5 | Yes |
| test/evaluation bypass leakage | default-off is normal runtime config | High | injected tests + ephemeral required-auth evaluation token | PH-2B/2E | Yes |
| bootstrap lockout | enabled empty registry has no recovery | High | reviewed digest bootstrap/recovery contract | PH-2B/2C | Yes |
| CLI 401/403 ambiguity | both map to authentication failure | Medium | separate forbidden result | PH-2E | Yes |
| credential logging | auth code currently safe; no explicit policy guard | High if regressed | redaction/logging regression tests | PH-2B/2D | Yes |
| provider source existence leak | unknown source 404 before verification | Medium | normalize provider failure boundary | PH-2D | Before public callback use |
| roles case/unvalidated | exact strings from config; malformed roles silently empty | Medium | startup validation; policy redesign later | PH-2B/PH-5 | Yes |

## 26. Recommended V1 default-on contract

1. **Default behavior:** `required`; absent or malformed configuration never
   creates a development principal.
2. **Browser:** transient high-entropy credential exchange to an opaque,
   server-side, revocable Secure/HttpOnly/SameSite session with CSRF.
3. **CLI/API:** named, expiring, revocable bearer API credentials; existing OS
   keyring/environment transport retained.
4. **Agent:** existing dedicated enrollment and steady-state token domain;
   atomic max-use repair required.
5. **Provider callbacks:** existing provider-specific verifier selected by
   change-source type; never ordinary human login.
6. **Public:** `/health`, minimal `/ready`, and bounded CORS preflight only.
7. **Bootstrap:** environment-provisioned high-entropy digest mapped to stable
   admin identity, removed/rotated after named credentials exist.
8. **Roles:** server-side credential/session mapping only; preserve current
   admin/operator checks; PH-5 expands policy.
9. **Errors:** 401 for invalid identity; 403 for valid but unauthorized.
10. **Development/evaluation:** explicit SQLite-only development mode; tests
    inject identity; evaluation uses ephemeral real bearer auth.
11. **Migration:** additive `0002+` for API credentials and sessions.
12. **PH-3:** tenant identity/membership/scoping and tenant-aware background
    work.
13. **PH-4:** human/provider secret custody, exposed token remediation,
    webhook/provider credential storage, agent token file security.
14. **PH-5:** comprehensive roles/permissions and route policy.

An authenticated principal never implies tenant access.

## 27. Exact route-domain policy

Authentication selection must be explicit and fail closed:

```text
PUBLIC_LIVENESS:
  GET /health

PUBLIC_READINESS_MINIMAL:
  GET /ready

PUBLIC_CORS_PREFLIGHT:
  OPTIONS only after exact Origin/method/header policy

AGENT_AUTHENTICATED:
  POST /api/v1/agents/enroll (enrollment authority)
  /api/v1/agent/* (steady agent authority)

PROVIDER_CALLBACK_AUTHENTICATED:
  POST /api/v1/change-source-webhooks/{source_id}

USER_AUTHENTICATED:
  every other /api/v1 route, including auth/session lifecycle routes

DISABLED / SHOULD_NOT_BE_PUBLIC in production:
  /openapi.json, /docs*, /redoc

INTERNAL_SERVICE_AUTHENTICATED:
  no current HTTP route; reserve for reviewed future internal service APIs
```

Path ambiguity, an unclassified API route, or unavailable verifier is a deny,
not a fallthrough to human, agent, provider, development, or public access.
Route-class coverage must be a startup/test invariant so no new route is
`UNKNOWN`.

## 28. PH-2 implementation decomposition

### PH-2B — Authentication Core Default-On + Fail-Closed Configuration

- introduce the explicit `required` / `development-disabled` contract;
- default to required and validate auth/registry/principal configuration at
  startup;
- centralize route-domain classification with no unknown routes;
- preserve agent/provider delegation without double auth;
- keep current API digest registry as transitional/bootstrap authority;
- disable production docs/schema and add minimal readiness;
- add 401/403/log-redaction/config-failure regressions; and
- do not add sessions, OIDC, passwords, tenants, or broad RBAC.

### PH-2C — Human Browser Session + Bootstrap Boundary

- additive reviewed `0002+` session schema;
- transient bootstrap/operator credential exchange;
- opaque server-side session, logout/revocation/expiry, CSRF;
- same-origin browser transport and explicit CORS;
- frontend auth state/route boundary without redesigning the product.

### PH-2D — Agent + Provider Authentication Boundary Regression

- atomically consume enrollment-token max uses;
- prove agent/human/provider credential non-interchangeability;
- preserve cluster/namespace binding and revocation;
- provider verification, bounded replay/dedupe, error non-disclosure, and raw-
  credential logging regressions.

### PH-2E — Named API Credentials + CLI / Operational Recovery

- additive credential lifecycle schema (may share PH-2C's reviewed revision
  family without editing an accepted revision);
- create/list/revoke/rotate/expire named human/service API credentials;
- CLI 401 vs 403, server revocation-aware logout, doctor/recovery behavior;
- migrate evaluation runner to an ephemeral real credential;
- remove implicit default-off dependencies from tests.

### PH-2F — Authentication Acceptance + PH-2 Closure

- full backend/frontend/CLI/agent/evaluation regression;
- real production-mode negative/positive route matrix;
- bootstrap, session, credential, machine-domain, restart, recovery, and
  credential-redaction acceptance;
- no PH-3 tenant or PH-5 role completeness claim.

This decomposition avoids one giant IAM/RBAC change. If PH-2C and PH-2E both
need schema, each accepted revision remains immutable and later work adds the
next revision; implementation review may order the two tables into one narrow
initial auth revision only if both are implemented and tested together.

## 29. Security stop conditions

PH-2 implementation stops rather than shipping any design that:

- introduces plaintext passwords without a separately reviewed requirement;
- embeds a privileged token in browser source, public environment, JavaScript,
  or localStorage;
- uses auth-disabled mode for production bootstrap;
- accepts an agent/provider credential as human identity or requires a human
  token in addition to valid machine authentication;
- treats identity as tenant authorization;
- accepts missing/malformed config as admin;
- logs or persists raw long-lived human credentials;
- turns provider credentials into Topo login credentials;
- edits migration 0001 or preemptively adds tenant schema;
- exposes approval/execution audit identity from an anonymous fallback; or
- activates autonomous execution.

## 30. Architecture verdict and exact next block

**PH-2A ARCHITECTURE_BLOCKER: NO.** Current route boundaries can distinguish
human, agent, and provider authorities; `AuthPrincipal` can preserve stable
human audit identity; the browser can be added through a server-side session;
and bootstrap does not require globally disabling auth.

The enrollment max-use race is a required PH-2D security repair, and the
tracked provider credential is an urgent PH-4 incident, but neither prevents
the dependency-correct core transition.

The exact next block is:

```text
PH-2B — Authentication Core Default-On + Fail-Closed Configuration
```

Proposed next action:

```text
ARCHITECT REVIEW / MERGE PH-2A
```

PH-2A stops here. It does not implement PH-2B, enable auth, modify frontend/
agent/provider behavior, add sessions/JWT/password/OIDC, create migration 0002,
add tenancy, redesign RBAC, run Docker/PostgreSQL, or activate execution.
