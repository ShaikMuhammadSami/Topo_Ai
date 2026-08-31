# PH-4A — Secret / Credential / Provider Boundary Contract v1

## 1. Decision, scope, and evidence boundary

Verdict: **PASS — documentation/inventory checkpoint, ready for architect review.**

Accepted main / starting HEAD: `68ca976e55ef3c83cf0fcde8b915334d5d587be0`.
Commit subject: `test(security): close adversarial tenant isolation acceptance (#79)`.
Branch: `security/ph-4a-secret-custody-contract-v1`. Repository: `C:\Topo-ai`.
Inventory date: 2026-08-31. The starting working tree was clean.

This is a source-code and configuration-schema inventory, not a census of live
credential values. No real environment values, credential files, protected DB
contents, provider accounts, or historical secret bytes were inspected. No
provider request, deployment, credential rotation, migration, or product change
was performed. Protected DB files were hashed as opaque binary files only.

The current supported custody roles, their persistence, and incidental disclosure
carriers are inventoried below. Each has an explicit classification. Existing
digest-only credentials remain non-recoverable at the issuing server. Recoverable
integration credentials and current plaintext/config/log/API risks are identified.
The future SecretStore, root-key, rotation, and implementation contracts are
defined, but **PH-4 is NOT closed and production secret custody is NOT complete**.

PH-3 is frozen: TenantContext, membership, fixed service bindings, agent/source
binding, 38 tenant-owned tables, 25 tenant-local composite identities, canonical
IDs, world-model ownership, RCA evidence isolation, and LLM tenant filtering are
unchanged. Global authentication authority is not artificially tenant-scoped.

No active real credential was found by the tracked-tree scan or inspected source.
That does not assert that ignored configuration, backups, or historical Git are
secret-free. The previously revoked historical GitHub credential remains a known
historical issue; no history rewrite, redisclosure, or rebaseline is authorized.

## 2. Inventory method and exact counting rules

The taxonomy counts **logical custody roles**, not deployments, actual configured
secrets, bytes, appearances of the word `token`, or every copy of the same value.
Aliases and copies are enumerated within their role. Issuer-side verification and
client-side outbound possession are separate roles/trust domains: e.g. A7 is the
backend's digest-only agent verifier; C8 is the agent's recoverable client copy.
This is not permission for the backend to recover A7.

| Classification | Count | Interpretation |
| --- | ---: | --- |
| A — ONE_WAY_AUTH_SECRET | 8 | Issuer/verifier authority, including dormant internal claim proof |
| B — REVERSIBLE_INBOUND_VERIFICATION_SECRET | 6 | Five providers; GitLab has two supported credential modes |
| C — REVERSIBLE_OUTBOUND_CREDENTIAL | 20 | Product, client, SDK-local, and evaluation/CI roles explicitly separated |
| D — SIGNING_SECRET | 1 | Outbound customer webhook signing |
| E — ROOT_ENCRYPTION_KEY | 0 | No current application SecretStore/root key; proposed, not counted as implemented |
| F — PUBLIC_IDENTIFIER_OR_HINT | 11 | Identifier/hint families below; non-secret does not mean public API access |
| G — SECRET_REFERENCE | 10 | Existing locator families; not all are tenant-qualified secret-store references |
| H — UNKNOWN / AMBIGUOUS | 0 | No unresolved custody role |
| **Total inventoried roles** | **56** | **35 credential-material roles + 21 identifier/reference roles** |

Persistence has a different denominator: **11 direct ORM custody/configuration
fields**, counted once per column even when multiple roles share it. These are
7 DIGEST_ONLY_SAFE, 3 PLAINTEXT_PERSISTED, 0 ENCRYPTED_PERSISTED, and 1
REFERENCE_ONLY; AMBIGUOUS = 0. The URL entry is conditional on credential-bearing
URL configuration. This does not assert every instance contains a secret.

Additionally, all **61 `_json` columns** were inventoried as typed metadata or
potential incidental-copy carriers (§5), together with free-text/error/URL fields.
Those are not silently treated as encrypted or safe. They are not added to the
11-field direct-custody denominator: arbitrary evidence can contain injected
credentials without being a legitimate credential store. A copied credential
retains its A/B/C/D classification; its carrier is not a new secret class.

Source discovery covered tracked backend, frontend, CLI, agent, evaluation,
scripts, examples, CI, deployment files, and relevant prior hardening contracts.
Configuration inspection used names/schema/code only. The scanner reports only
path, line, and category; no matching credential values. SDK credential-chain
behavior was checked in the installed agent SDK source, not by running the SDKs.

## 3. Current custody matrix

`T` = authoritative tenant-owned domain row; `I` = installation/security-global;
`L` = operator/client/agent-local; `EVAL` = isolated evaluation or CI, not a product
integration. `R` = recoverable at the named holder; `NR` = not recoverable from the
server verifier. Current tests are indexed in §11; findings in §10.

### 3.1 One-way authentication — do not convert to encryption

| ID / value | Producer → consumer / trust / scope | Ingress, memory, persistence, recoverability / exposure | Current rotation, overlap, revocation, expiration | Tests / risk |
| --- | --- | --- | --- | --- |
| A1 bootstrap/static API bearer | Operator → human/service API middleware; installation/bootstrap, I | Raw Authorization header exists only in request/client custody; `TOPO_API_TOKEN_HASHES_JSON` contains SHA-256 digests mapped to principals. Configuration caches registry, not raw bearer. NR from registry; no API returns raw bootstrap value. | Replace registry/reload app; multiple independent entries permit deliberate overlap; removal invalidates authority after reload. No per-entry expiry schema. | AUTH, SESSION; preserve. Client/URL/log risks F04/F05/F09. |
| A2 opaque browser session | Auth session service → browser/session middleware; human browser, I authority | `topo_session` cookie; `auth_sessions.session_secret_digest`. Raw in `IssuedAuthSession` and Set-Cookie, then browser cookie jar; NR from DB. Cookie is the intentional issuance transport, not a JSON secret field. | New independent login session; logout/source revocation/idle or absolute expiry. Default absolute 480 min, idle 60 min, bounded configuration. | SESSION, BROWSER; repr risk F09. |
| A3 CSRF proof | Auth session service → same-origin browser unsafe requests; human browser, I | `topo_csrf` cookie and `X-Topo-CSRF`; `auth_sessions.csrf_digest`. NR from DB; deliberately JS-readable cookie, not independently sufficient authentication. | Tied to issued session and its expiry/revocation; replaced with new session. | SESSION, BROWSER; must preserve semantics. |
| A4 named human API credential | Human admin issuance → API middleware / human session exchange; I | One-time `ApiCredentialCreated.api_credential`; `auth_api_credentials.credential_secret_digest`; SHA-256, random `token_urlsafe(48)` material. Last-eight-character hint only in later views. NR from DB. | Issue new independent credential, verify, revoke old. Concurrent independent credentials allowed. Default 30-day expiry, maximum 90 days. | API, POSTGRES; one-time model/validation/debug risk F04/F09. |
| A5 named service API credential | Human admin issuance → service API middleware; I authentication plus fixed server-side tenant binding | Same digest column as A4, not an extra custody column. Raw once; no browser-session authority. Tenant binding is not supplied afresh by a service caller. | Same issuance/expiry/revocation as A4; preserve PH-3 fixed binding. | API, TENANT; preserve. |
| A6 enrollment secret | Tenant-scoped enrollment issuer → enroll endpoint; agent enrollment, T | One-time response `enrollment_token`; body `AgentEnrollRequest.enrollment_token`; `agent_enrollment_tokens.token_hash` SHA-256 + hint. NR from DB. No ordinary GET recovery. | Default 30 min / 1 use; max 10080 min / 100 uses. Atomic consumption; revoked/expired/disabled-tenant tokens rejected. No recover-old rotation. | AGENT, POSTGRES; argv/validation/stdout risk F04/F09. |
| A7 steady-state agent proof | Enrollment transaction → agent authentication; steady-state agent, T | One-time `AgentEnrollResponse.agent_token`; `topo_agents.token_hash` SHA-256 + hint. Raw request bearer; NR from DB. | Revocation and disabled-tenant denial exist. No token-expiry field or seamless same-agent multi-token rotation. Re-enrollment issues a new agent identity; do not claim otherwise. | AGENT, TENANT; local raw copy is C8, not backend plaintext. |
| A8 internal execution claim proof | Execution transaction service → internal claim validator; internal worker, T, dormant V1 | `execution_intents.claim_token_hash` SHA-256; raw transient internal result `claim_token` has `repr=False`. No customer briefing or claim HTTP capability. NR from DB. | Existing bounded claim/lease/intent lifecycle and claim-hash clearing; no new execution work. | EXECUTION; preserved and inventoried, not activated. |

`auth_sessions.source_credential_digest` is a persisted verifier linkage to A1/A4,
not a new independently issued raw credential. Seven direct digest columns are
listed exactly in §4. Hashes here are high-entropy token verifiers, not a password
hashing recommendation. Never encrypt/recover raw A1–A8 on the issuing backend.

### 3.2 Inbound providers — same reference storage, distinct authenticators

All six rows use tenant-owned `change_sources` records but the raw key currently
lives in a **process-global environment namespace**. `secret_ref` is a name, not
ciphertext or a raw secret. `resolve_secret()` calls `os.getenv(secret_ref)`.
The reference grammar is `^[A-Z][A-Z0-9_]{2,254}$`; it is not a purpose/owner
allowlist. Raw material is recoverable in the environment and per-request verifier
locals. No SecretStore, key version, expiry, or bounded previous-key overlap exists.
Rotation is operator environment replacement or a reference PATCH, with one
selected secret at a time; disabling a source stops future verification. All rows
share PROVIDER/TENANT tests and F02/F03/F07/F08/F11 risks.

| ID | Producer → verifier / exact inbound credential | Verification and ordering | Persistent/API copies |
| --- | --- | --- | --- |
| B1 GitHub HMAC secret | GitHub/customer shared key → GitHub verifier; provider webhook, T use / I key location | HMAC-SHA256 body, `X-Hub-Signature-256`, constant-time comparison before JSON parsing/persistence | Key not in DB; signature normally excluded by header allowlist. |
| B2 GitLab signing token | GitLab signing token → signing verifier | `whsec_` / base64-decoded key; signs webhook ID, timestamp, body; `Webhook-Signature`; default 300-second age check. Positive `config.signature_max_age` has no current upper cap. | Key not in DB; signature excluded; webhook ID/timestamp retained as non-secret evidence metadata. |
| B3 GitLab shared secret token | GitLab legacy `auth_mode=secret_token` → token verifier | Raw `X-Gitlab-Token`, constant-time equality before parse | Header excluded; key only resolved environment value. |
| B4 HCP Terraform HMAC secret | Terraform/customer shared key → Terraform verifier | HMAC-SHA512 body, `X-TFE-Notification-Signature`, before parse | **Signature header is currently included in `SAFE_HEADERS` and copied into `change_source_deliveries.headers_json`.** It is an authenticator, not the original HMAC key. |
| B5 Jenkins HMAC secret | Jenkins/customer shared key → Jenkins verifier | HMAC-SHA256 body, `X-Topo-Signature-256`, before parse | Key not in DB; signature excluded. No Jenkins outbound API token implementation implied. |
| B6 Azure DevOps Basic password | Customer service hook → Basic verifier | `Authorization: Basic …`; username from `config.username` (default `topo-webhook`), password from environment reference. Base64 is not encryption. Before parse. | Authorization excluded; username is F10 metadata. No Azure PAT/HMAC outbound implementation implied. |

The receive route loads an exact source locator, verifies, and proves active
server-side tenant binding before durable delivery/normalization. Unknown source,
bad credential, malformed signature, and disabled tenant receive generic 401.
Unavailable configured key receives a distinct generic 503: no key bytes leak,
but the distinction can reveal configuration availability (F11). Doctor is an
authenticated tenant route and returns the environment name and availability bit;
that bit is not evidence of ownership of the named environment secret (F02).

### 3.3 Outbound and local credential roles

All C rows require raw possession at the sending side. Unless stated otherwise,
the credential is **not stored in a Topo backend credential table**, is not returned
by a product read API, and has no Topo-managed rotation/overlap/revocation/expiry;
those are controlled by the external issuer/operator. The listed current risk is
potential code-path exposure, not a finding that a live secret was present.

| ID / credential | Producer → consumer; trust / scope | Ingress / memory / persistence / recoverability | Current lifecycle, API/log boundary; tests / risk |
| --- | --- | --- | --- |
| C1 OpenAI API key | Operator → OpenAI SDK; LLM provider, I | `OPENAI_API_KEY` → `_openai_client()` local → SDK auth; recoverable environment/SDK object, no DB key | New client per generation; operator reload/environment lifetime; response/error text can be propagated, not deliberate key output. LLM, TENANT; F04/F07/F09. |
| C2 Groq API key | Operator → four legacy Groq SDK call sites; LLM provider, I | `GROQ_API_KEY`, local SDK instances; R environment/SDK, no DB key | `incident_explanation`, `incident_copilot`, `investigation_planner`, `post_incident_report`; catches embed `str(exc)`. LLM/TENANT; F04/F07/F09. |
| C3 GitHub outbound API token | Operator → GitHub connector and authenticated source-file/build-artifact enrichment; outbound SCM, I | `TOPO_GITHUB_TOKEN` → `GitHubSettings.token` → Authorization Bearer. R environment + connector object; no DB token | Settings dataclass repr includes token; configurable API URL and redirects; raw provider error body may propagate. LINEAGE/PROVIDER; F04/F05/F09. |
| C4 outbound custom authentication headers | Tenant customer → webhook HTTP client; outbound customer webhook, T | `WebhookEndpointCreate/Update.headers` → `webhook_endpoints.headers_json` → HTTPX header dict. R **plaintext DB** | May contain Authorization, API-key, Cookie or other custom secrets. Returned unchanged by create/list/PATCH views. Immediate replacement/disable; no version/overlap/expiry. F01/F08. |
| C5 credential-bearing URLs | Operator/customer/provider payload → transport or rendered URL; mixed T/I/L | URL userinfo, query, opaque signed path; direct `webhook_endpoints.url`, local CLI `Profile.api_url`, agent `backend_url`, server backend/GitHub URL config; R plaintext where configured | No declared Topo query-token authentication route found. Config URLs can nevertheless carry secrets and be echoed/logged; five configurable transport families detailed in §8. F05. |
| C6 database connection credential | Operator → SQLAlchemy/psycopg/Alembic; installation bootstrap, I | `TOPO_DATABASE_URL`, `RAW_DATABASE_URL`/`DATABASE_URL`, explicit Alembic `sqlalchemy.url`; R environment/process/config, no DB self-storage | Needs connection before encrypted DB store is usable; stays outside that store. schema-admin masks connection errors; startup/driver/SQL parameter paths not uniformly sanitized. DB; F04/F05/F09. |
| C7 CLI/API client bearer copy | Credential issuer/operator → human/service CLI client; L | Prompt/stdin or `Profile.token_env` (default `TOPO_API_TOKEN`) / OS keyring → cached HTTPX header. R keyring/environment; not ordinary profile JSON | Login supports hidden prompt/stdin; named create requires `--output-token-stdout`. Keyring deletion is local logout, not server revocation. API/CLI; F05/F09. |
| C8 agent client bearer copy | Backend enroll response/operator → agent/sensor client; L | `TOPO_AGENT_TOKEN` first, otherwise `credentials.json` selected by `TOPO_AGENT_CREDENTIALS_FILE`; R **plaintext file/environment**, `AgentApiClient.token` and HTTPX header | Persists across restart; POSIX final-file chmod 0600 occurs **after** temp write/replace; no explicit Windows ACL or pre-write temp restriction. No seamless rotation; server revoke/re-enroll. F06/F09. |
| C9 AWS secret access key | Operator/SDK credential chain or STS → agent boto3; outbound cloud, L | `AWS_SECRET_ACCESS_KEY`, SDK profiles, STS `SecretAccessKey`; R SDK/source material, no Topo DB | Base `boto3.Session`; optional AssumeRole builds session from returned credentials. Topo does not expose raw credentials. No invented backend AWS key store. CLOUD; F06/F09. |
| C10 AWS temporary proof tokens | SDK/web identity/STS → agent boto3; L | `AWS_SESSION_TOKEN` / legacy `AWS_SECURITY_TOKEN`; web-identity file content; STS `SessionToken`; R SDK/local input, no Topo DB | External bounded credentials; AssumeRole result is copied into explicit boto3 session rather than a Topo refresh service. Availability/refresh verification is later work, not a PH-4A execution. CLOUD; F09. |
| C11 Azure client secret / legacy SDK password | Operator environment → `DefaultAzureCredential`; outbound cloud, L | Installed SDK supports `AZURE_CLIENT_SECRET` or legacy `AZURE_PASSWORD` with appropriate identity fields; R SDK/environment, no Topo DB | External issuance/revocation; plugin excludes interactive browser credential, not all SDK source modes. CLOUD; F06/F09. |
| C12 Azure certificate private material | Operator certificate + optional password → SDK; L | `AZURE_CLIENT_CERTIFICATE_PATH` file content and `AZURE_CLIENT_CERTIFICATE_PASSWORD`; R SDK/file; no Topo DB | SDK-supported credential source, not a new Topo-managed certificate product. CLOUD; F06/F09. |
| C13 Azure workload-identity assertion | Platform token projection → `WorkloadIdentityCredential`; L | Token file selected by `TOPO_AZURE_FEDERATED_TOKEN_FILE` / SDK `AZURE_FEDERATED_TOKEN_FILE`; R short-lived file/SDK memory | Plugin explicit workload-identity mode; external expiry/refresh semantics, no raw token in config view. CLOUD; F06/F09. |
| C14 Azure SDK access token | Azure identity chain → agent cloud clients; L | `get_token()` / SDK client memory; R in-memory bearer, no Topo DB | SDK-managed access lifetime; not a separate tenant-auth mechanism. CLOUD; F09. |
| C15 GCP service-account private key | Operator ADC file → `google.auth.default`; outbound cloud, L | `GOOGLE_APPLICATION_CREDENTIALS` points to file; private material R file/SDK memory, not Topo DB | ADC source, not a backend GCP upload/API-key field. CLOUD; F06/F09. |
| C16 GCP ADC / impersonation token material | ADC provider → agent Google clients; L | ADC user refresh/access tokens, external-account subject proof, resulting access token; optional impersonated credential object; no Topo DB | Optional impersonation lifetime requested 3600 seconds, external/SDK refresh; no Topo rotation API. CLOUD; F09. |
| C17 Kubernetes bearer / exec-plugin token | Kubeconfig or projected service account → backend/agent Kubernetes clients; L/I | `load_kube_config` / `load_incluster_config`, SDK configuration; R credential source + SDK, no Topo backend custody column | SDK/operator lifecycle; no discovery of Kubernetes Secret objects granted by supplied agent RBAC. Do not infer all Pod properties are secret-free. CLOUD; F06/F09. |
| C18 Kubernetes client private key | Kubeconfig TLS client credentials → backend/agent Kubernetes client; L/I | Embedded/file key through SDK; R local credential source, not topology credential storage | Operator/certificate lifecycle, no Topo rotation manager. CLOUD; F06/F09. |
| C19 CI GitHub/GHCR credential | GitHub Actions → checkout/login action; EVAL/CI | `${{ secrets.GITHUB_TOKEN }}` input to action; R runner/action custody, not literal workflow value or build argument | Job/platform lifetime; workflow grants contents read/packages write for evaluation publishing. Receipt fields are identity evidence, not a token dump. SCAN/LINEAGE; F09/F10. |
| C20 evaluation API client copy | Isolated evaluator bootstrap/named issuer → evaluation `TopoClient`; EVAL | Random bootstrap + one-day named API token, memory Authorization; agent child environment carries C8. No credential in intended result schema | Runner switches to named credential, clears bootstrap member; subprocess environment inherits operator environment and diagnostic tails can expose errors. Evaluation is not executed here. EVAL; F04/F09. |

The backend has no implemented outbound GitLab token, HCP Terraform API token,
Jenkins API credential, Azure DevOps PAT integration, or generic tenant LLM-key
upload/store. Mentions in scanner patterns, fixtures, and plans do not implement
those products. Cloud credentials are agent SDK-local; backend cloud enrichment
consumes inventory. Docker uses its configured local/remote daemon connection;
no separate Topo Docker credential schema/store was found. Signed artifact URLs
and credentials in future provider configuration fall under C5/C4, not a silently
invented provider integration.

### 3.4 Signing, public identifiers, and existing references

| ID / class | Current surface and flow | Scope / custody / lifecycle / exposure |
| --- | --- | --- |
| D1 SIGNING_SECRET | Tenant customer → `WebhookEndpointCreate/Update.signing_secret` → `webhook_endpoints.signing_secret` → HMAC-SHA256 body / `X-Topo-Signature` | T, plaintext Text column, R. View returns only `has_signing_secret`; raw Pydantic/ORM/request memory remains. PATCH replaces/clears; no versioned overlap or expiry. F01/F08/F09. Timestamp header is not itself part of the current body-only MAC. |
| F1 PUBLIC_IDENTIFIER_OR_HINT | `tenant_id` | Non-secret selection/binding ID; server proves membership/ownership. Never a cryptographic key or default tenant. |
| F2 PUBLIC_IDENTIFIER_OR_HINT | `agent_id` | Locator, not the bearer; may be in Kubernetes Secret resource as operational packaging, but ID remains non-secret. |
| F3 PUBLIC_IDENTIFIER_OR_HINT | `source_id` | Callback locator, not authentication; do not log with high-cardinality metrics. |
| F4 PUBLIC_IDENTIFIER_OR_HINT | `credential_id` | Named credential management locator, not raw credential. |
| F5 PUBLIC_IDENTIFIER_OR_HINT | `session_id` | Server record ID, not `topo_session` raw cookie. |
| F6 PUBLIC_IDENTIFIER_OR_HINT | `enrollment_token_id` | Enrollment record ID, not enrollment secret. |
| F7 PUBLIC_IDENTIFIER_OR_HINT | `webhook_id` and delivery IDs | Domain/evidence locators, not signing proof. |
| F8 PUBLIC_IDENTIFIER_OR_HINT | `credential_hint` / `token_hint` | Named API hint is last 8 characters; generated enrollment/agent hints are first 8 + ellipsis + last 4. Not reconstructable full secret; never authority. The helper returns short inputs unchanged, but generated tokens exceed that short-input branch. |
| F9 PUBLIC_IDENTIFIER_OR_HINT | AWS access-key ID | Identifier half, not secret access key; scanner flags it as a credential-context indicator. Still avoid unnecessary disclosure. |
| F10 PUBLIC_IDENTIFIER_OR_HINT | Provider type, repository/account/project/tenant/client identity, Azure Basic username, AWS role ARN/external ID/session name, digest/commit/image/evidence identifiers | Public/non-secret authentication-adjacent metadata, not shared verification keys. External ID is passed as STS request context, not used by Topo as a possession credential. Ordinary authorization/data confidentiality still applies. |
| F11 PUBLIC_IDENTIFIER_OR_HINT | Non-credential endpoint URLs, model names, policy/config booleans, credential availability/expiry/status, future key ID | Safe only when no userinfo/query/path secret is embedded. C5 takes authority over any credential-bearing component. Future key ID is metadata, not an implemented root key. |
| G1 SECRET_REFERENCE | `change_sources.secret_ref` environment variable name | T locator selecting I environment; persisted/returned reference-only. No owner/purpose-qualified lookup today (F02). |
| G2 SECRET_REFERENCE | CLI `Profile.token_env` | L configurable environment-name reference; saved in profile, not token value. |
| G3 SECRET_REFERENCE | CLI keyring service `topo-ai-cli` + profile name | L OS-keyring locator; backend selection/security depends on installed keyring backend. No guarantee every backend is encrypted; do not add plaintext fallback. |
| G4 SECRET_REFERENCE | Agent `TOPO_AGENT_CREDENTIALS_FILE` / resolved credentials path | L file locator; file contents C8. Config/home path overrides also influence location. |
| G5 SECRET_REFERENCE | Kubeconfig path/context / service-account mounted credential locations | L/I SDK locators; context is not token material. |
| G6 SECRET_REFERENCE | Azure federated token / certificate file paths | L SDK locators (C12/C13 content); not returned raw assertions. |
| G7 SECRET_REFERENCE | AWS profile/shared-credential/web-identity file locators | L SDK references, including `TOPO_AWS_PROFILE`, `AWS_PROFILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_WEB_IDENTITY_TOKEN_FILE`; no tenant authority inferred from profile name. |
| G8 SECRET_REFERENCE | GCP ADC / external-account credential file locator | L `GOOGLE_APPLICATION_CREDENTIALS`; no permission to import file contents into topology. |
| G9 SECRET_REFERENCE | Deployment `secretKeyRef` (`topo-agent-credentials`, `agent-token`) and CI `secrets.GITHUB_TOKEN` expression | Kubernetes/CI reference-only configuration. Kubernetes Secret data encryption at rest is a deployment concern, not guaranteed by this reference. |
| G10 SECRET_REFERENCE | systemd `EnvironmentFile` / operator config location | L `/etc/topo-agent/topo-agent.env`, CLI/agent config/home overrides; reference-only in supplied deployment template, content not inspected. |

F/G roles have no raw secret to revoke or expire themselves; replacement of a
locator does not revoke its target. Their API/config serialization is permissible
only under existing authorization and without granting reference-based secret
read authority. Current reference expiry/ownership is supplied by the owner or
underlying credential, not a new generic locator policy.

## 4. Exact direct persistence ledger

| Exact ORM field | Current category | Raw recovery / current read API behavior | Disposition |
| --- | --- | --- | --- |
| `auth_sessions.session_secret_digest` | DIGEST_ONLY_SAFE | NR; not returned | Preserve |
| `auth_sessions.csrf_digest` | DIGEST_ONLY_SAFE | NR; not returned | Preserve |
| `auth_sessions.source_credential_digest` | DIGEST_ONLY_SAFE | NR source linkage; not returned | Preserve |
| `auth_api_credentials.credential_secret_digest` | DIGEST_ONLY_SAFE | NR; create returns independently held raw value once, list/get do not | Preserve |
| `agent_enrollment_tokens.token_hash` | DIGEST_ONLY_SAFE | NR; issuance once | Preserve |
| `topo_agents.token_hash` | DIGEST_ONLY_SAFE | NR; enrollment response once | Preserve |
| `execution_intents.claim_token_hash` | DIGEST_ONLY_SAFE | NR; no customer claim endpoint | Preserve dormant implementation |
| `webhook_endpoints.signing_secret` | PLAINTEXT_PERSISTED | R; read view only exposes boolean, DB/repr still raw | PH-4B/C encrypted reference |
| `webhook_endpoints.headers_json` | PLAINTEXT_PERSISTED | R when secret header supplied; create/list/PATCH return actual header values | PH-4C split safe headers from encrypted secret-header bundle |
| `webhook_endpoints.url` | PLAINTEXT_PERSISTED if credential-bearing; otherwise NON_SECRET | R credential-bearing userinfo/query/path when configured; echoed in views | PH-4C/D reject/migrate credential-bearing URL; not automatic destructive URL rewriting |
| `change_sources.secret_ref` | REFERENCE_ONLY | Environment name only; raw resolved value not in DB | PH-4C controlled conversion to owner/purpose-bound opaque reference |

Totals: 11 direct custody fields; digest 7, plaintext-capable 3, encrypted 0,
reference 1, ambiguous 0. There is no encryption envelope/ciphertext/root-key
column in the current model. These counts exclude local files/keyring/environment
and the incidental-copy columns next; they do not imply an inspection of actual
DB secret presence or absence.

## 5. JSON, evidence, free text, and copy propagation

Normal provider data is **not** classified secret merely because it is provider
data. These are customer evidence/data boundaries (PH-6) unless credential
material is present. Fields listed below are normally NON_SECRET with respect to
authentication custody; secret-bearing values become **PLAINTEXT_PERSISTED
incidental copies**, not an approved use of the field. No ambiguity is hidden by
that distinction.

| All 61 JSON columns, grouped by exact table | Content / current boundary |
| --- | --- |
| `topology_snapshots.scope_json`, `payload_json` | Scope, graph/entity properties and evidence; not a credential store; arbitrary properties may carry injected secrets. |
| `identity_resolutions.payload_json` | Identity results/evidence, not credential authority. |
| `signals.payload_json`; `changes.payload_json`; `incident_analyses.payload_json` | Submitted/derived signal/change/analysis content; copy carriers. |
| `remediation_recommendations.payload_json`; `recovery_verifications.payload_json` | Derived/manual evidence and guidance; preserve deterministic semantics. |
| `incident_outcomes.source_json`, `payload_json` | Outcome/source evidence and responder content; tenant-owned, not secret input. |
| `webhook_endpoints.event_types_json`, `headers_json` | Event type enum list NON_SECRET; headers are explicit direct-custody entry C4. |
| `webhook_deliveries.payload_json` | Outbound event payload; no default copy of secret headers, but arbitrary event content can carry incidental secrets. |
| `incident_explanations.payload_json`, `evidence_json`, `warnings_json` | Derived narrative/evidence and error warnings; provider exception and evidence-copy sinks. |
| `incident_copilot_messages.evidence_ids_json`, `evidence_json`, `suggested_questions_json` | IDs metadata; evidence/questions can contain copied or user-injected secret strings. |
| `incident_investigation_plans.evidence_gaps_json`, `warnings_json`, `evidence_json`, `payload_json` | Derived/user/LLM content and errors; not protected by key storage. |
| `incident_investigation_steps.evidence_ids_json`; `post_incident_report_actions.evidence_ids_json` | Evidence IDs, normally non-secret. |
| `post_incident_reports.payload_json`, `evidence_json`, `warnings_json` | Report/export copies of evidence and errors. |
| `topo_agents.namespace_scope_json`, `capabilities_json`, `labels_json`, `metadata_json` | First two typed metadata; labels/metadata unrestricted copy carriers. Raw agent token is not deliberately inserted. |
| `runtime_sensors.capabilities_json`, `metadata_json`; `runtime_dependencies.metadata_json`; `runtime_processes.metadata_json` | Runtime metadata; process arguments/errors can carry credentials. Sensor buffers/agent spool can retain the same data locally. |
| `cloud_accounts.metadata_json`; `cloud_resources.subnet_ids_json`, `tags_json`, `properties_json` | IDs are not secrets; tags/properties are customer data and possible incidental copies, not cloud-credential upload. |
| `build_artifact_evidence.temporal_json` | Typed temporal metadata. Build-record parser uses selected fields; existing test rejects secret-bearing provider-field serialization. |
| `change_events.metadata_json`, `raw_payload_json` | `ingest_change_event()` JSON-serializes metadata/raw payload without a general secret scrub. Source-file mutations can contain source content. No blanket safe-content claim. |
| `change_sources.config_json`, `filters_json` | Untyped dictionaries accepted/persisted/returned unchanged; **unsupported embedded credentials would be plaintext and echoed** (F03). No top-level raw verifier field currently exists. |
| `change_source_deliveries.headers_json`, `payload_json`, `event_ids_json` | Header allowlist includes Terraform signature; payload uses limited `_redact`; event IDs non-secret. |
| `change_source_dead_letters.payload_json` | Copy of already-redacted delivery JSON, not a fresh credential load; inherits sanitizer misses. |
| `causal_analyses.payload_json` | Deterministic causal evidence/ranking; no secret-store custody. Preserve accepted causal contracts. |
| `action_approvals.target_entity_ids_json`, `readiness_snapshot_json`, `requested_by_roles_json`, `decided_by_roles_json`; `action_approval_events.actor_roles_json` | IDs/roles and derived readiness context, not credential store; dormant safety infrastructure preserved. |
| `execution_intents.target_entity_ids_json`, `execution_snapshot_json`, `created_by_roles_json`; `execution_intent_events.actor_roles_json` | Derived context/roles; claim raw secret excluded from public model. |
| `auth_sessions.roles_json`; `auth_api_credentials.roles_json` | Validated authority metadata, not raw credential material. |

Additional exact copy sinks: `change_sources.last_error`,
`change_source_deliveries.error`, `change_source_dead_letters.reason`,
`webhook_deliveries.response_body`, `webhook_deliveries.error_message`,
`topo_agents.last_error`, `runtime_sensors.last_error`,
`execution_intents.last_error_message`, `incident_copilot_messages.content`,
investigation command/finding/responder-note fields, report summaries/actions,
`ownership_mappings.repository_url`, and signal/incident/identity reason/summary
fields. These are not overlooked secret columns: their schema is general text,
not encryption. Sanitize at appropriate ingress/egress and avoid putting
credentials into evidence; do not retroactively rewrite frozen causal evidence
or protected databases under this documentation task.

Exact inbound copy path:

```text
source locator -> source enabled -> secret verification -> active source tenant
 -> parse JSON -> delivery headers allowlist + payload key-name redaction
 -> commit authenticated receipt -> normalize original parsed payload
 -> durable normalized change evidence
 -> failure: persist exception string + copy delivery payload to dead letter
 -> authorized replay: normalize stored redacted payload, preserve receipt time
```

Replay does not reload or reauthenticate with a stored raw webhook key; it is an
authorized replay of an already authenticated receipt. Delivery/dead-letter view
models omit stored payload/headers, but expose `error` / `reason`. Thus a stored
signature is a DB/log risk, not a claim that the delivery list API returns it.
Normalizers select provider fields; not every raw webhook byte is automatically
copied into `change_events.raw_payload_json`. The direct change-event submission
path nevertheless permits raw payload storage, and source-file content is evidence.

## 6. API response and browser/client boundary

| Surface | Actual behavior | Required follow-up |
| --- | --- | --- |
| `/api/v1/auth/session` POST/GET/DELETE | POST exchanges human credential, sets Secure cookies; GET returns principal/expiry only; DELETE revokes and clears. No raw session JSON. | Preserve PH-2. No SecretStore session conversion. |
| `/api/v1/auth/api-credentials` | Human admin create returns raw once after transaction; list/get/revoke metadata exclude digest/raw secret. | Keep one-time boundary; prevent debug/validation/error copying. |
| `/api/v1/agents/enrollment-tokens`, `/agents/enroll` | Enrollment secret once; enroll accepts body secret and returns steady-state secret once after atomic consume/create. | Protect body/model validation and stdout/file handling, not encrypted backend verifiers. |
| `/api/v1/change-sources` create/list/get/PATCH | Exposes `secret_ref`, untyped `config`, `filters`, `last_error`; never calls resolve-secret to fill view. | Reference-only is not sufficient: restrict key ownership, make new secret inputs write-only, scrub config/error leaks. |
| `/change-sources/{source_id}/doctor` | Returns reference name and availability bit, not raw key | Future tenant/purpose/owner-qualified configured status; no arbitrary environment probe. |
| `/change-sources/deliveries`, `/dead-letters`, replay | No raw stored payload/header field in read models; error/reason may leak exception content | Safe error codes and sanitized evidence copies; preserve replay authority/timestamps. |
| `/api/v1/integrations/webhooks` create/list/PATCH | Raw headers + URL returned; `has_signing_secret` only | Write-only secret headers and signing material, safe URL handling. There is no separate current webhook detail GET to invent. |
| `/integrations/deliveries`, webhook test result | Remote response body (up to 4000 characters) and exception string returned | Remote response/exception may echo credentials; sanitize/bound by policy, not blind trust. |
| Incident explanation/copilot/plan/report/briefing exports | Structured tenant evidence; warnings can include provider errors and content-derived strings | Keep deterministic facts and tenant filtering; shared secret redaction is independent of RCA. |

Browser session: `topo_session` is HttpOnly, Secure (unconditionally, including
current development handling), SameSite=Lax, host-only, path `/`. CSRF cookie is
Secure/SameSite=Lax and intentionally not HttpOnly. Browser API requests are
same-origin `/api/`, `credentials: same-origin`, `cache: no-store`; unsafe requests
send `X-Topo-CSRF`. Login credential is React state/request-local, input type
password with autocomplete off, cleared in `finally`. Source audit found **0
credential localStorage/sessionStorage writes**. Tenant selection is non-secret
module state; tenant switch guards late JSON/blob delivery. 401 expires auth and
clears selection; tenant 403 invalidates workspace choice, not authentication;
other 403 is permission denial. Downloads use the authenticated tenant-aware
fetch/blob path, not token-bearing download URLs.

Webhook UI holds signing secret in React state and clears it after successful
creation, not on every error. Errors display API detail; this and model-validation
echo remain F04/F09. No visual redesign is proposed.

CLI profile serializes only URL, non-secret tenant preference, environment-name
reference, TLS/timeouts/retry/capture settings. **0 dedicated raw-token fields in
ordinary profile serialization**. Keyring/environment holds raw token; an insecure
keyring backend is not ruled out by importing `keyring`. `Profile.api_url` can
still carry an embedded credential (C5); the zero-token-field result does not
erase that risk. Login uses hidden prompt or `--token-stdin`. Named credential
creation requires explicit `--output-token-stdout`; agent `create-token` renders
the full one-time response without the same opt-in flag. CLI errors include
remote detail or configured URL/transport exception. Service tenant selection
never overrides its fixed server-side binding.

Agent `--token` remains an argv/history/process-list exposure route; stdin/hidden
prompt are supported alternatives. Enrollment success prints agent ID/plugin
metadata, not raw credential. Credentials are persisted separately from ordinary
agent config. Restart loads environment before file. Final POSIX chmod is not an
atomic restrictive-create guarantee; Windows inherited ACLs are not validated.
The supplied Kubernetes manifest uses `secretKeyRef`, read-only root filesystem,
non-root user, and restricted capabilities, but is a development example with
HTTP backend and TLS verification disabled. It is not production transport proof.
systemd references a local environment file; Windows installer adds a task but
does not establish credential-file ACL custody. Sensor uses the same agent client
credential family; no second backend token system exists.

## 7. Environment/config names, startup, outbound SDKs, and memory

No values in this table were obtained from the running environment.

| Exact names / config fields | Current classification / holder |
| --- | --- |
| `TOPO_API_TOKEN_HASHES_JSON` | A1 digest registry, not raw API token; loaded by auth configuration. |
| `TOPO_API_TOKEN` or CLI-selected `Profile.token_env` | C7 raw client bearer, not a backend raw bootstrap registry. |
| `TOPO_AGENT_TOKEN`; `TOPO_AGENT_CREDENTIALS_FILE`; `TOPO_AGENT_HOME`; `TOPO_AGENT_CONFIG_FILE` | C8 raw environment token; G4/G10 paths. |
| `OPENAI_API_KEY`; `GROQ_API_KEY`; `TOPO_GITHUB_TOKEN` | C1/C2/C3 process-global outbound credentials. |
| `change_sources.secret_ref` | Dynamic operator environment variable name for B1–B6; **no single fixed provider-key environment name exists in the product**. Do not invent six hard-coded names or read referenced values. |
| `TOPO_DATABASE_URL`; Alembic `sqlalchemy.url` | C6 if password-bearing; SQLite URL without credentials is non-secret. |
| `AWS_SECRET_ACCESS_KEY`; `AWS_SESSION_TOKEN`; `AWS_SECURITY_TOKEN` | C9/C10 SDK-local raw secrets. |
| `AWS_ACCESS_KEY_ID`; `AWS_PROFILE`; `AWS_SHARED_CREDENTIALS_FILE`; `AWS_CONFIG_FILE`; `AWS_WEB_IDENTITY_TOKEN_FILE`; `AWS_ROLE_ARN` | F9/G7 metadata/references; web-identity file contents C10. |
| `TOPO_AWS_PROFILE`; `TOPO_AWS_ROLE_ARN`; `TOPO_AWS_EXTERNAL_ID`; `TOPO_AWS_ROLE_SESSION_NAME` | Agent SDK selection/context; not a backend AWS key store. |
| `AZURE_CLIENT_SECRET`; `AZURE_PASSWORD`; `AZURE_CLIENT_CERTIFICATE_PASSWORD` | C11/C12 installed-SDK inputs; not direct Topo backend fields. |
| `AZURE_CLIENT_CERTIFICATE_PATH`; `AZURE_FEDERATED_TOKEN_FILE`; `TOPO_AZURE_FEDERATED_TOKEN_FILE` | G6 file references; contents C12/C13. |
| `AZURE_CLIENT_ID`; `AZURE_TENANT_ID`; `AZURE_USERNAME`; `TOPO_AZURE_CLIENT_ID`; `TOPO_AZURE_TENANT_ID`; `TOPO_AZURE_AUTH_MODE` | Identity/mode metadata F10/F11. |
| `GOOGLE_APPLICATION_CREDENTIALS` | G8 SDK ADC locator, not key bytes; source content C15/C16. |
| `TOPO_GCP_IMPERSONATE_SERVICE_ACCOUNT`; `TOPO_GCP_QUOTA_PROJECT` | Target identity/quota context, not credential bytes. |
| `KUBECONFIG`; `TOPO_KUBE_CONTEXT` | G5/F10 Kubernetes client selection; private data stays at SDK source. |
| CI `secrets.GITHUB_TOKEN` | G9 reference; evaluated action input C19, not a literal in tracked YAML. |
| `TOPO_API_URL`; `TOPO_BACKEND_URL`; `TOPO_GITHUB_API_URL` | F11 URL configuration only if no C5 credential-bearing component. |
| `TOPO_CONFIG_FILE`; `TOPO_PROFILE` | CLI config/profile references, not raw token. |
| `TOPO_AUTH_MODE`; legacy `TOPO_AUTH_ENABLED`; `TOPO_BROWSER_ALLOWED_ORIGINS_JSON`; `TOPO_SESSION_ABSOLUTE_TTL_MINUTES`; `TOPO_SESSION_IDLE_TTL_MINUTES`; `TOPO_AI_LLM_PROVIDER`; `TOPO_OPENAI_MODEL` | Non-secret controls; preserve fail-closed authentication and origin/TTL semantics. |

No current application session/JWT signing key or secret-encryption master-key
environment setting was found. Sessions are opaque server-side records, not
self-contained signed tokens. Do not invent a session-key rotation requirement.
No raw provider key is a `NEXT_PUBLIC_*` setting. The tracked backend example
contains variable names/placeholders; real `.env` files were not read.

Database handling: engine receives a credential-bearing URL at process setup;
there is no intentional startup URL print. `/health` and `/ready` return minimal
status only. `schema_admin` catches SQLAlchemy connection failures and prints a
generic message; its existing test checks credential safety. Raw engine/driver
construction, Alembic command failures, and general exception traces do not have
one application-wide redaction boundary. `create_engine()` does not configure
`hide_parameters`; SQL exception/debug output can expose plaintext bound secret
columns even if a URL renderer masks a password. Do not equate SQLAlchemy's URL
repr masking with complete query/exception/log protection. No schema-admin command
or migration was run against the protected databases.

Outbound boundary: OpenAI uses the existing client helper and `store=False`, not
a new provider. Groq uses four existing SDK constructors. Keys are sent as SDK
authentication, not intentionally inserted in evidence prompts. Existing tenant
evidence gates remain before either provider. Generic secret sanitization is
separate from those gates. GitHub uses `GitHubSettings` and Authorization headers;
source-file enrichment shares the installation token, not a tenant PAT vault.
Agent cloud/Kubernetes SDKs acquire credentials locally. No real calls were made.

Current raw-memory lifetime: issuer local until one-time response; verifier local
for a request; cookies until browser/server expiry; CLI/agent HTTPX headers for
client lifetime; GitHub settings for connector lifetime; cloud SDK credentials
for SDK lifetime; outbound webhook ORM object/header dict during delivery; LLM
key in environment/local SDK instance. Environment and client objects are not
short-lived zeroized buffers. Future encrypted material must be retrieved as late
as possible and not attached to domain/ORM views or process-global plaintext
caches. Limit references and close clients; Python immutable strings/SDK copies
do **not** permit a truthful guaranteed zeroization claim.

## 8. Logging, errors, URL carriers, and redaction contract

### Actual source findings

There is no application-wide logging filter or secret-aware exception formatter.
Most authentication rejection paths are generic and current PH-2 tests assert
raw credentials are absent, but this is not a blanket guarantee for other APIs.

* `change_source_ingest._redact` matches a small set of exact lowercase key names.
  It misses Cookie/Set-Cookie, hyphen/camel aliases, `signing_secret`, arbitrary
  credential strings, and nested values under innocuous keys. `_safe_headers`
  retains Terraform signatures. Exceptions are interpolated into delivery/source/
  dead-letter records and replay error responses.
* Outbound webhook delivery persists remote response text and `type(exc): exc`;
  `publish_event_safely` returns exception text as a warning. A remote echo is
  untrusted even when the destination belongs to the tenant.
* OpenAI helper exception strings and structured-validation errors may include
  provider body/input. Its sanitizer checks sensitive key fragments and Bearer
  text, but at depth 6 returns `str(value)[:500]` **before recursively redacting**.
  It does not generally sanitize Basic auth, signed URLs, or secret-looking free
  text. Legacy Groq paths have separate sanitizer coverage and exception wrapping;
  explanation generation does not call the shared OpenAI sanitizer before Groq.
* `GitHubSettings` and `IssuedAuthSession` default dataclass repr include raw
  fields. Secret-bearing Pydantic request/one-time response models use ordinary
  `str`, without a general secret-aware repr/validation policy. The internal
  execution claim result already uses `repr=False`; do not weaken it.
* CLI/agent clients render remote errors and transport exceptions. Agent/sensor
  verbose mode enables root DEBUG; SDK/httpx/urllib3 logging is not constrained by
  a shared credential filter. SDK debug behavior must be adversarially tested,
  not assumed safe because normal log lines omit auth headers.
* Evaluation runner inherits environment into subprocesses and exposes diagnostic
  log tails; intended result schemas omit auth material. Provider truth sanitizer
  handles secret-key patterns and signed query keys, but is evaluation-only and
  is not the product's universal sanitizer.

Six offline synthetic probes (no DB/network/environment reads) returned True:
webhook URL/header values serialize; webhook repr includes the supplied secret;
depth-limited LLM sanitizer retains a nested secret marker; Basic free text retains
marker; webhook PATCH accepts an unvalidated URL string; Pydantic validation error
includes rejected secret input. Markers were synthetic and output was boolean-only.
These are diagnostic observations, not six newly added test files or full API
integration claims.

URL audit: **0 declared raw-auth-secret query/path API parameters found**. IDs in
auth/source paths are locators. **5 configurable transport URL families** can
nevertheless carry credential material: webhook endpoint URL, CLI API URL, agent
backend URL, Next server backend URL, GitHub API URL. Userinfo/query/opaque signed
path data can reach config persistence, errors, or remote requests. Webhook create
validates scheme/host only; PATCH has no equivalent URL validator. Next rewrite
validates scheme only. CLI/agent/GitHub use redirect-following HTTP clients; SDK
cross-origin Authorization stripping is not a general guarantee for custom headers,
URL secrets, or enrollment request-body redirects. Outbound customer webhooks
explicitly use `follow_redirects=False` today. Provider/source/repository URLs in
evidence are additional arbitrary data carriers, not an authentication API.

### Required PH-4D contract (not implemented here)

One bounded secret-safe formatting contract must cover case-insensitive normalized
key names, nested structures, headers, URLs, free text, and exception chains.
Always suppress Authorization, Proxy-Authorization, Cookie, Set-Cookie,
X-Topo-CSRF, provider signature/token headers, API keys, token/password/passwd/
secret/client-secret/private-key values, signing material, DB password/query
credentials, and ciphertext. Handle underscore/hyphen/camel variants. Depth/item/
size limits must replace an unvisited subtree with a safe marker, not `str()` it.
Do not attach raw request/response objects or Pydantic error `input` to responses.

Use explicit safe error codes plus bounded sanitized metadata; a regex is defense
in depth, not proof all arbitrary strings are harmless. Truncate **after** safe
formatting. Restrict configured auth to headers/secret references; reject URL
userinfo, known secret query parameters and signed credential paths where those
are inappropriate. Separate public endpoint from credential before persistence.
Do not strip a query blindly and claim the endpoint remains functional. Redirect
rules must protect auth headers **and bodies**, retain safe legitimate provider
artifact redirects without logging signed locations, and never permit a tenant
to choose the destination of an installation credential without policy. Network
allowlisting/SSRF/egress topology is PH-6, with PH-4D owning credential disclosure.

Future provider authentication rejection is externally generic across unknown
source, disabled tenant, bad/malformed proof, unavailable binding/version, and
unknown secret reference. Readiness/operator diagnostics can separately expose
authorized bounded reason codes without becoming an unauthenticated existence
oracle. No raw secret or failed key version is returned. Preserve verify-before-
parse and authenticated replay semantics.

## 9. Recommended SecretStore and production custody design

This entire section is prospective. No schema, key, or encryption code is added.

### 9.1 Choice and minimal interface

| Option | Decision / tradeoff |
| --- | --- |
| Plaintext DB | Reject: database reads/backups expose recoverable credentials. |
| Application-managed authenticated DB encryption | Viable V1 baseline: self-hosted, no mandatory cloud control plane, transactional configuration; root-key operations become operator responsibility. |
| External cloud manager only | Not the initial requirement: useful future AWS-first integration, but would couple availability, deployment, and tests to a provider before CLOUD-V1. |
| **Pluggable SecretStore, encrypted DB baseline** | **Recommend.** Narrow purpose/owner boundary now, same-database atomicity and SQLite/PostgreSQL testability; future external backend can add IAM-managed availability/rotation without changing domain custody. |

The store is not a general tenant-accessible vault or a way to decrypt auth
digests. Only configured reversible integration purposes may be stored. Internal
operations: `put`, `get_for_use`, `rotate`, `revoke`, `describe`, plus controlled
rewrap. Inputs include server-authoritative scope, exact owner type/ID, purpose,
opaque reference, and operation/version identity. Plaintext is accepted only at a
write/use boundary; `describe` never returns it. No HTTP decrypt/export endpoint.

Scope must be either `(tenant, authoritative tenant_id)` or `(installation,
explicit installation_id)`, never a guessed/default tenant. Before fetching or
decrypting, check the caller/service capability, owning domain record, active
tenant, exact purpose, and complete scope-qualified reference. Tenant A must not
obtain Tenant B ciphertext even if IDs collide. Internal installation operations
cannot be invoked by a tenant choosing a scope flag. Purpose binds different
providers/modes as well as inbound verification versus outbound signing/header
use. A source ID alone is not secret authority.

### 9.2 Proposed schema and envelope

PH-4B owns two narrowly justified tables: `secret_records` (stable ownership,
purpose, reference, lifecycle/current-version metadata) and `secret_versions`
(immutable encrypted version material). A stable reference with separately
versioned ciphertext is needed for bounded provider overlap and rewrap; it is not
a duplicate evidence/history store. Names are the proposed implementation contract,
not claims about current ORM.

`secret_records`: explicit scope kind/ID, authoritative tenant ID when tenant
scope (NULL only for explicit installation scope), opaque `secret_id`, owner
type/ID, allowlisted purpose, active version, optional previous version and hard
previous-accept-until, revoked state/timestamp, created/updated timestamp and actor,
operation/idempotency metadata. Validate scope combinations; installation scope
does not imply a synthetic tenant. Scope-qualified uniqueness and parent lookup
must follow existing explicit repository conventions on both database engines.

`secret_versions`: scope-qualified parent reference, version, key ID, algorithm,
envelope version, random nonce, ciphertext including authentication tag, creation
metadata, and lifecycle/rewrap metadata. No plaintext or root-key column. No ORM
default that invents a scope or root key. External manager backend locator would
remain internal behind this interface; domain rows would not expose it.

Use vetted **AES-256-GCM**, 32-byte uniformly random keys, fresh random 96-bit
nonce per encryption, full 128-bit authentication tag, versioned key IDs.
Envelope validation must reject malformed encodings, unsupported algorithms/
versions, wrong nonce/tag lengths, and oversized material before use. Use a
maintained cryptographic library, not homegrown primitives. Never ECB, unauthenticated
CBC, deterministic nonces, hard-coded app key, or password-derived fixed salt.

Canonical AAD binds at minimum scope kind, tenant or installation ID, secret
record ID, secret purpose, and envelope/schema version. Also bind owner type/ID
and secret version; include algorithm/key-ID metadata in authenticated context.
Use explicit typed canonical encoding, not delimiter-concatenation ambiguity.
Tampering with tenant, owner, purpose, ID, version, nonce, tag, or ciphertext must
fail closed. AAD authenticates ownership metadata; it does not replace the
pre-decryption tenant predicate or authorization check.

### 9.3 Root keys, startup, rotation, and memory

Proposed operator settings: `TOPO_SECRET_STORE_BACKEND=encrypted_db`,
`TOPO_SECRET_KEYRING_FILE` (read-only restrictive-permission operator-mounted
file), `TOPO_SECRET_ACTIVE_KEY_ID`, and explicit `TOPO_INSTALLATION_ID`.
These are **new proposed names**, not existing configuration or live values.
Keyring contains active and explicitly retained prior key IDs/material outside
the app DB, ordinary config export, source control, and database backup. Mounted
secret delivery/external key manager can evolve later. File ownership/permissions
and empty/malformed/duplicate key IDs must be validated without echoing values.

Production must explicitly configure key material; no generated-on-start key or
plaintext fallback. Missing active key/invalid configuration prevents encrypted
store readiness. When encrypted records exist, startup must verify all required
key IDs are available and fail closed when any is absent; do not start with silent
partial decryption. An explicit development/test mode may supply disposable keys
in an isolated database, never silently create a durable production key. No
change to authentication or TenantContext fallback is permitted. Database URL,
root key and bootstrap auth authority remain installation/bootstrap custody
outside the database store to avoid circular startup dependency.

New writes use only the active key. Old ciphertext is readable only with its
explicit retained key ID. Controlled bounded rewrap decrypts and re-encrypts with
a fresh nonce/active key, preserves underlying provider secret/reference/version
meaning, and is transactional/idempotent with compare-and-swap state. Interruptions
must be restartable; report counts/key IDs, never plaintext/ciphertext. Retire old
keys only after inventory proves no live ciphertext needs them and PH-8 recovery
requirements are addressed. Root-key rotation **does not** rotate a provider
credential; compromise of a root key may require separately authorized provider
credential rotation because old ciphertext may already have been exposed.

No process-global plaintext cache. Retrieve at verification/delivery call boundary,
use only for that purpose, drop references promptly, avoid repr/serialization,
close transports. At most the bounded active/previous verifier set is loaded.
Memory compromise remains outside encryption-at-rest protection; no guaranteed
Python zeroization or protection from a fully compromised application is claimed.

### 9.4 Provider rotation versus one-way rotation

For B1–B6, support active + **at most one** previous version to coordinate sender
rollover. Default immediate replacement (zero overlap); an explicit rotation may
request a bounded overlap no longer than 24 hours, selected as this V1 contract,
not alleged current behavior. Compute immutable `previous_accept_until` using
server time, capped by the previous version's own expiry. Repeated rotation or
retry must not extend a retired version indefinitely; a second rotation drops
the older previous version. Emergency revoke stops all versions immediately.
Tenant disable/source disable denies all versions. Replay does not extend key
acceptance. GitLab timestamp-age policy remains separate and must be server-bounded.
Response/error cannot reveal which version verified or failed.

Outbound D1 signs using the active version only; receiver rollout must be
coordinated outside Topo. Never emit dual secret values. C4 header bundles use one
active version; do not retry blindly using old outbound credentials after an auth
failure. Other external credentials follow their issuer lifecycle. No generic
automatic credential rotation job or cloud IAM provisioning is introduced.

A1–A8 remain digest-only on the issuing side: issue independent new credential,
verify it, revoke old credential. A7 currently lacks seamless same-agent rotation;
document re-enrollment/new identity honestly. Do not decrypt old hashes, add raw
recoverable token columns, or repurpose SecretStore for session/API verifier state.

### 9.5 Domain integration, migration, atomicity, deletion

Current source already has a reference column, but its meaning is an environment
name. PH-4C may reuse `change_sources.secret_ref` for **opaque store references**
after an explicit conversion; the runtime must not guess that an unresolved
reference means `os.getenv`. No tenant chooses an arbitrary environment/keyring/
external-manager locator. Legacy env import requires operator-authorized exact
source ID + authoritative tenant + purpose + approved environment-name manifest,
never an inferred/default owner or caller-selected binding. Unmapped legacy
sources remain disabled/unavailable, not silently rebound.

Required field transition plan:

* `change_sources.secret_ref`: explicit legacy-reference conversion; replace
  `resolve_secret()`/doctor arbitrary environment lookup with scoped store use.
  `config_json` / `filters_json`: typed non-secret validation; unsupported embedded
  credentials require operator decision, not automatic secret-name heuristics.
* `webhook_endpoints.signing_secret`: controlled encrypt-and-reference migration
  to proposed `signing_secret_ref`; clear legacy plaintext only after verified
  transaction. New API input is write-only, never a read echo.
* `webhook_endpoints.headers_json`: retain allowed non-secret headers; move actual
  secret-header bundle to proposed `headers_secret_ref`. Views may return safe
  header names/availability, not authentication values. Do not accidentally treat
  every application header as a secret or silently discard required headers.
* `webhook_endpoints.url`: explicit inventory/quarantine of credential-bearing
  URLs; operator supplies safe destination and supported separate credential.
  Never strip a signed URL and claim unchanged delivery semantics.

No migration in PH-4A; existing 0001–0008 are immutable. Future migration files
must be new and must not read arbitrary live env or infer tenant ownership during
DDL. Separate schema introduction from controlled data conversion. Require a
backup/recovery plan and purpose-authorized operator operation, not a global
plaintext export. Do not run it against either protected DB. Failed conversion
leaves a clear unavailable/not-converted state, not a dual-store ambiguity.

Encrypted DB backend: new domain reference, encrypted version, active metadata,
and legacy-column clearing share **one database transaction**. Helpers must not
commit independently. On encryption/store/domain failure roll back; duplicate
idempotency keys cannot bind to different owner/purpose/material. Conditional
updates prevent concurrent rotation from overwriting a newer version.

Future external backend: no claim that provider API participates in DB ACID.
Reserve an operation with scope/owner/idempotency key, write an immutable external
version idempotently, activate domain reference only after success, then bounded
reconcile/retry or compensate orphaned versions. Pending operations do not enable
verification/delivery; fail closed during ambiguity. Avoid indefinite orphans.

Revocation immediately prohibits verification/use after the defined transition;
physical ciphertext cleanup/retention is PH-7. Old backups, WAL, logs, and copied
plaintext are not erased by updating one column. PH-8 must provide separately
controlled key recovery/escrow: ciphertext-only backup may be unrecoverable;
keys co-located with DB backup defeat custody separation. Do not build retention
or backup systems in PH-4.

## 10. Threat model, findings, and ownership

Severity: P0 = active/immediate exposure and stop; P1 = production blocker;
P2 = before design-partner usage; P3 = later hardening. Architectural PASS here
accepts the inventory, not these unresolved product risks.

| Finding | Severity | Evidence / remaining risk | Repair owner |
| --- | --- | --- | --- |
| F01 recoverable webhook plaintext and read echo | P1 | Signing column plaintext; custom headers plaintext and returned; DB/config export compromise | PH-4B/C |
| F02 global environment-reference authority | P1 | Tenant source can select an arbitrary grammar-valid environment name; doctor probes presence, verifier uses global value without owner/purpose binding. Raw key extraction is **not** claimed proven. | PH-4B/C |
| F03 untyped source config/filters | P1 | Unsupported embedded credentials persist and echo through normal views | PH-4C |
| F04 unsafe errors / validation / remote echo | P1 | Raw exception/Pydantic input/remote body can reach API, durable error fields, logs and exports; DB parameter output not universally protected | PH-4D |
| F05 URL/redirect/outbound credential destination | P1 | Credential-bearing config URLs and redirect bodies/headers are not uniformly constrained; error echo | PH-4C/D; PH-6 network handoff |
| F06 agent-local custody / production transport gap | P1 | Plaintext credential file with post-write POSIX chmod/no explicit Windows ACL; development HTTP/TLS-disabled template | PH-4D; deployment/network controls PH-6 |
| F07 incomplete redaction of payloads/authenticators/LLM input | P1 | Terraform signature persisted, exact-name sanitizer misses, depth-to-string fallback, separate Groq paths, source/free-text copies | PH-4D; PH-6 data handoff |
| F08 rotation/version/audit gaps | P2 | Single environment key / immediate webhook replacement; no bounded previous-key custody or general secret audit event; agent rotation gap | PH-4B/C, PH-10 metadata handoff |
| F09 repr/debug/stdout/process-memory/operator exposure | P2 | Raw-bearing repr/models, argv enrollment option, one-time enrollment stdout, verbose SDK logs, inherited evaluation environment; no zeroization guarantee | PH-4D |
| F10 tracked scanner blind spots | P2 | Missing current formats/names/URL/header patterns; ignored files/history/binary not scanned | PH-4D/E |
| F11 provider configuration oracle / policy bounds | P2 | Unknown/bad proof 401 vs unavailable-key 503; GitLab max-age has no upper cap; doctor namespace probing belongs also to F02 | PH-4C/D |
| F12 external backend/recovery operational evolution | P3 | No external manager adapter or rehearsed separated root-key recovery yet; not a reason to claim encrypted DB is implemented | Future PH-4E/PH-8 follow-up |

Exact finding counts: **P0 0; P1 7; P2 4; P3 1; total 12**.

| Threat | Current mitigation | Residual exposure / finding | Owner |
| --- | --- | --- | --- |
| T01 database read compromise | A verifier hashes; PH-3 row isolation for application queries | D1/C4/C5 raw config; hashes do not protect reversible material (F01) | PH-4B/C |
| T02 application log compromise | Generic auth rejections, no routine auth header print | Exceptions/remote echo/durable warnings (F04/F09) | PH-4D |
| T03 API response leak | One-time credential views separated from read views | Header/config echo, validation input, provider errors (F01/F03/F04) | PH-4C/D |
| T04 browser storage leak | HttpOnly session, no local/sessionStorage credential writes | JS/XSS can use active session/CSRF and temporary form state; no universal error filtering (F04/F09) | PH-4D; PH-6 browser/data |
| T05 CLI profile leak | Token uses environment/keyring, not profile token field | URL-embedded credential, insecure keyring backend/exception/stdout (F05/F09) | PH-4D |
| T06 agent filesystem leak | Separate file; final POSIX 0600; backend digest only | Temp write/Windows ACL/environment/SDK credential sources (F06) | PH-4D |
| T07 provider config export leak | `secret_ref` not raw env key | Config/filters and headers accept plaintext; arbitrary environment locator (F02/F03) | PH-4C |
| T08 backup compromise/loss | Digest-only verifier custody | Plaintext legacy fields; future key separation/recovery required (F01/F12) | PH-4B/C, PH-8 |
| T09 debug trace/repr leak | Claim token `repr=False`; generic some auth errors | Session/GitHub/settings/model/SDK traces (F09) | PH-4D |
| T10 cross-tenant secret-reference IDOR | PH-3 tenant-scoped domain rows/source binding | Environment references are global, not qualified secret authority (F02); future AAD alone insufficient | PH-4B/C |
| T11 wrong-secret/purpose rotation | Current exact source row updates | No typed purpose/version CAS; future swapped reference risks (F08) | PH-4B/C |
| T12 stale previous secret accepted indefinitely | Current one selected key, no built-in previous version | Operator old keys can remain; future overlap must be hard bounded (F08/F11) | PH-4C |
| T13 missing root key | No current encrypted store, so not a current decrypt failure | Future fail-closed availability/recovery requirement, no fallback (F12) | PH-4B/E, PH-8 |
| T14 root key compromise | No current app root key | Future DB+key compromise defeats at-rest boundary; rewrap not retroactive revocation (F12) | PH-4B/E, operator/PH-8 |
| T15 accidental operator disclosure | Hidden prompts/stdin, named output opt-in, scanner | Enrollment argv/stdout, screenshots/env/config/logs, debug (F09/F10) | PH-4D |
| T16 malicious provider payload credential injection | Verify-before-parse; key-based payload scrub; build evidence selects fields | Unknown-key strings/deep structures/source content/error injection (F03/F07) | PH-4C/D; PH-6 |
| T17 outbound destination/redirect theft | Customer webhook redirects disabled; browser same-origin | Other URL configuration/body redirects/SDK behavior not uniformly constrained (F05) | PH-4D/PH-6 |
| T18 signature replay / copied authenticator | Delivery idempotency; GitLab timestamp check | Terraform signature durable copy; not every provider has timestamp-bound proof (F07/F11) | PH-4C/D |
| T19 partial secret/domain transaction | Current domain operations transactional; no separate store yet | Future orphan/unbound/dual-store state under failure/concurrency (F08) | PH-4B/C/E |
| T20 ciphertext metadata substitution | Not applicable to current plaintext | Future wrong-tenant/purpose/version/AAD/key-ID swaps must reject before use (F12) | PH-4B/E |

Threat count **20**; unowned/unclassified **0**. None is authority to broaden PH-4A
into production repair. No active-exposure, architecture, or custody blocker was
found. First blocker: none.

## 11. Existing tests, scanner coverage, and PH-4A diagnostics

These references describe inspected existing coverage, not suites rerun in PH-4A:

| Test key | Existing evidence |
| --- | --- |
| AUTH | `test_authentication_default_on.py`, `test_authentication_acceptance.py`: default-on/domain/generic error contracts. |
| SESSION | `test_auth_sessions.py`: digest custody, cookies/CSRF, expiry/revocation/source authority. |
| API | `test_auth_api_credentials.py`: one-time issuance, digest-only DB, list/get secrecy, roles, service/session boundary, revocation/expiry/collision. |
| AGENT | `test_agent_enrollment_postgres.py`, `test_machine_tenant_binding.py`, `test_provider_authentication_hardening.py`: atomic use, distinct credentials, binding, rejected proof. Agent test directory has no dedicated credential-file ACL/atomic-write test. |
| PROVIDER | `test_webhook_security.py`; `test_provider_authentication_hardening.py` verify-before-JSON/persistence, exact replay, all modes, credential-domain rejection and caplog checks. These do not prove encrypted custody. |
| POSTGRES / DB | `test_postgres_runtime_compatibility.py`, `test_database_migration_operations.py::test_connection_error_is_credential_safe`; no protected DB migration rerun here. |
| TENANT | `test_tenant_adversarial_acceptance.py`, `test_tenant_adversarial_routes.py`, `test_tenant_adversarial_llm.py`: owned source/agent records and provider/LLM isolation. |
| LLM | `test_incident_briefing.py`, explanation/copilot/planner/report and tenant LLM tests: deterministic fallback/grounding; not comprehensive secret redaction acceptance. |
| EXECUTION | `test_execution_transaction.py`: no command/claim secret in models/responses and secret-shaped cancellation reason scrub. Remains dormant. |
| CLI | `C:\Topo-ai\cli\tests\test_config.py`, `test_client_auth.py`, `test_auth_credentials.py`: no profile token field, auth transport, one-time credential destination. |
| BROWSER | `C:\Topo-ai\frontend\test\auth-session.test.mjs` and tenant transport tests: cookie/same-origin/401-vs-403/storage/download boundaries. |
| CLOUD | `C:\Topo-ai\agent\tests\test_aws_cache.py`, `test_azure_cache.py`, `test_gcp_cache.py` are plugin/cache coverage, not credential-custody certification. |
| LINEAGE / EVAL | `test_github_actions_build_lineage.py::test_secret_bearing_provider_fields_are_not_serialized`, evaluation fixture secret checks and `test_required_authentication.py`. No experiment rerun. |
| SCAN | `C:\Topo-ai\scripts\security\tests\test_check_tracked_secrets.py`: eight scanner tests below. |

Backend test basenames above are under `C:\Topo-ai\backend\tests` unless another
absolute root is supplied. Existing coverage is preserved, with **0 test changes**.

SEC-1 scanner recognizes GitHub token prefixes, AWS access-key IDs, private-key
block delimiters, literal Bearer strings of minimum length, and a fixed list of
sensitive assignment names. It ignores explicit placeholders/runtime references;
unquoted source expressions are treated as code references, not literal secrets.
These suppressions are pattern-based, not arbitrary per-path blanket allowlists.
Binary/NUL-containing content is skipped; Git-tracked working files are scanned,
with unchanged unreadable files falling back to index content. Unreadable changed
files fail the scan. Ignored/untracked files, full history, actual environment,
provider account state, and binary backups are **not** validated.

Eight tests: synthetic GitHub detection without value output; synthetic AWS ID;
literal assignment; unquoted runtime source reference; quoted source literal;
placeholders/references; binary skip; ignored backend env outside tracked scan.
CI runs them and the tracked scanner on PR/main push. No new scanner helper or
pattern change was needed for this inventory.

Coverage gaps F10: fixed assignment names omit `GROQ_API_KEY` and dynamic inbound
key names; no comprehensive `topo_api_`/`topo_session_`/`topo_csrf_`/enrollment/agent
format detection, DB URL password/query detection, Basic/cookie/signature/header
JSON detection, or arbitrary credential-string detection. Multiline/encoded data,
unquoted literal-like expressions, templating/placeholder-like text and
non-UTF8/binary data can evade heuristics. Some SDK secret names are covered, not
all certificate/password/path content. A passing SEC-1 result is not proof of no
live credentials. Do not broaden historical scanning or print match values here.

PH-4A executed verification:

* `backend\.venv\Scripts\python.exe -m pytest scripts/security/tests -q -p no:cacheprovider`
  — **8 passed in 0.08s** at preflight.
* `backend\.venv\Scripts\python.exe scripts/security/check_tracked_secrets.py`
  — exit 0, tracked-tree hygiene passed.
* Six synthetic in-memory validation/redaction probes (§8) — exit 0, all six
  observations True; no live configuration/provider/DB access.
* Final scanner tests, tracked scan, explicit new-document scan, custody checks,
  and Git checks are recorded in §14. No full product suites were necessary or
  claimed for this docs-only change.

## 12. Exact implementation handoffs

### PH-4B — encrypted store and root-key foundation

Implement only the §9 narrow internal store, proposed two-table schema, explicit
scope/purpose/owner authority, opaque references, AES-256-GCM envelope/AAD,
operator-mounted keyring configuration, strict startup/readiness, active/prior-key
decryption, and bounded transactional rewrap. No one-way raw-token storage, no
provider algorithm or tenant-authority redesign. New migration only; immutable
0001–0008 untouched. No bulk automatic legacy-secret import in schema DDL.

SQLite and PostgreSQL tests must cover parity, tenant/reference collisions,
installation-vs-tenant rejection, wrong owner/purpose/AAD, bit/nonce/tag/key-ID
tampering, fresh nonces for repeated plaintext, malformed/missing keys, no-key
startup with encrypted records, rollback on partial put, concurrent/CAS rotation,
idempotency, interrupted rewrap and zero raw/ciphertext in logs/views/repr/errors.
Test against disposable databases and explicit synthetic keys; never the protected
developer/frozen LINEAGE DBs. Physical key recovery remains PH-8 handoff.

### PH-4C — provider/source and outbound webhook custody integration

Use B1–B6 exact provider credentials, preserve algorithms/auth-domain checks and
verification before parsing. Replace env lookup/doctor with scoped SecretStore
binding. New raw secret request fields are write-only; GET/list/PATCH responses
return status/metadata, not raw key or secret header value. Existing source
config/filter dictionaries must have typed non-secret schema handling; unsupported
secret material cannot be echoed. Integrate D1 and C4 via signing/header refs;
keep safe URL/header config separate. Treat missing field as no change and explicit
clear/revoke as an intentional operation; never turn a masked view value into a
new secret. Use current+previous bounded inbound rotation and single-active outbound
policy, generic error behavior and server-bounded timestamp checks. Implement the
controlled owner-proven legacy conversion/transaction policy in §9.5.

Adversarial tests: every provider/mode, two tenants, same reference names/IDs,
wrong owner/purpose/version, rotated previous-key expiry/second rotation/retry,
disabled tenant/source/revocation, invalid signature before parse, old authenticated
dead-letter replay without credential copying, failures between domain/store
writes, legacy env map rejection without authority, and view/PATCH/config export
secrecy. No external provider enrollment or key rotation without separate approval.

### PH-4D — outbound credentials, redaction, client/operator handling

Exact repair families: `change_source_ingest` header/key sanitizer and error fields;
`webhook_delivery` remote-body/exception/warning handling; `llm_client` depth cutoff,
provider errors and validation; the four legacy Groq callers; `github_connector`
settings repr, destination/redirect behavior and error details; Pydantic secret
input errors and one-time models; SQL/driver/Alembic logging and parameter safety;
CLI/agent remote error formatting and URL configuration; browser webhook form/error
handling; agent/sensor temp-file permissions/Windows ACL custody, argv/stdout and
debug behavior; evaluation diagnostic propagation without evaluator semantics
change; scanner current-format gaps. Preserve same-origin cookie/CSRF and fixed
service binding, not a browser token-storage regression.

Use the shared §8 formatting policy and late-use memory boundary. Tests must
exercise headers (including Proxy-Authorization/Cookie/Set-Cookie/provider proofs),
case variants, deep nesting, arbitrary exceptions/response echo/validation input,
Basic and signed URLs, redirect request bodies, SDK DEBUG/repr, local profile/token
file failure paths, stdout opt-in, and deterministic fallback without actual LLM
calls. Signed provider payload/customer data remains distinct from credentials;
PH-6 owns general data minimization/egress. No causal rules/evidence IDs/ranking
or accepted frozen receipt rewriting to satisfy redaction tests.

### PH-4E — adversarial acceptance and closure evidence

Run a fresh two-tenant custody acceptance with disposable SQLite/PostgreSQL,
synthetic provider proofs/HTTP transports and fake SDKs, including wrong-reference
collisions/purpose swaps, one-way non-recovery, all write/read/export paths,
rotation/rewrap crash points, root-key absence/retirement, nonce/AAD tampering,
inbound replay after rotation, body/query/header/log/debug exfiltration attempts,
keyring/file permissions, scanner fixture coverage, and provider-unavailable
fallback. Demonstrate DB-read attacker sees ciphertext, not raw reversible
credentials; demonstrate application/keys compromise is outside that guarantee.

Reconcile routes/tables/roles/remaining risks and custody hashes without changing
PH-1/2/3 authority or frozen causal/evaluation semantics. Confirm PH-5/6/7/8/9/10
handoffs and record remaining accepted gaps; only a later authorized acceptance
may close PH-4. Do not activate execution, rotation jobs, a cloud vault product,
or new integrations as part of this checkpoint.

### Metadata/audit/metrics handoffs

Current credential/source records retain timestamps/status/actor metadata; action
approval/execution event tables are domain-specific, not a general secret audit
bus. Do not put credential events into change/RCA evidence or pretend a reusable
security audit sink already exists. Future PH-4 operations may record bounded
events: configured, rotated, revoked, credential created, rewrap completed/failed;
metadata only (operation ID, scope/ref/purpose/owner, actor, key ID, time, result).
PH-10 owns the durable audit/observability transport. No raw secret, ciphertext,
auth header, URL secret, or exception body. Authorized internal logs may contain
tenant/ref IDs; metrics may not use those high-cardinality IDs or secret values as
labels. Suitable bounded metrics: decrypt failure, rotation failure, store latency,
provider auth failure by purpose/provider/backend/result. PH-7 owns physical
retention/deletion; PH-8 separate key escrow/recovery; PH-5 minimum RBAC; PH-6
network/customer-data boundary; PH-9 deployment rollback.

Non-goals: encryption of every entity/change/payload, HSM/FIPS certification,
PostgreSQL RLS, mandatory external KMS, BYOK/per-tenant KMS, cloud IAM provisioning,
general RBAC, network segmentation, SIEM, production deployment changes, provider
queries/rotations, migrations in this block, or new autonomous execution.

## 13. Inspected source anchors

Primary inspected code and exact search/trace families (not a claim that every
unrelated file was read end-to-end):

* Auth: `C:\Topo-ai\backend\app\security\auth_config.py`, `api_tokens.py`,
  `agent_tokens.py`, `session_auth.py`; services `auth_session_service.py`,
  `auth_api_credential_service.py`; `C:\Topo-ai\backend\app\api\auth.py`;
  `C:\Topo-ai\backend\app\models\auth.py`, `agents.py`; agent repository and
  the existing auth repositories; `execution_transaction.py` claim boundary.
* Persistence: `C:\Topo-ai\backend\app\db\models.py`, `database.py`,
  `schema_management.py`, `schema_admin.py`; `C:\Topo-ai\backend\alembic\env.py`;
  migration metadata/hashes only, no DB schema mutation.
* Providers: `C:\Topo-ai\backend\app\models\change_sources.py`, `webhooks.py`;
  `C:\Topo-ai\backend\app\repositories\change_source_repository.py`,
  `change_event_repository.py`, `webhook_repository.py`; services
  `change_source_ingest.py`, `webhook_security.py`, `webhook_delivery.py`,
  `external_change_normalizers.py`, `github_source_file_enrichment.py`,
  `github_actions_artifact_lineage.py`, `github_actions_build_record.py`;
  `C:\Topo-ai\backend\app\connectors\github_connector.py`;
  `C:\Topo-ai\backend\app\api\change_sources.py`, `change_source_webhooks.py`,
  `webhooks.py`, `system.py`; `C:\Topo-ai\backend\app\main.py`.
* LLM: `C:\Topo-ai\backend\app\services\llm_client.py`,
  `incident_explanation.py`, `incident_copilot.py`, `investigation_planner.py`,
  `post_incident_report.py`; call-site/error searches in briefing/intelligence.
* Clients: `C:\Topo-ai\frontend\lib\topo-api.ts`,
  `C:\Topo-ai\frontend\components\auth\auth-boundary.tsx`, tenant boundary,
  `C:\Topo-ai\frontend\components\app\webhook-integrations-view.tsx`,
  `C:\Topo-ai\frontend\next.config.mjs`;
  `C:\Topo-ai\cli\src\topo_cli\config.py`, `client.py`, `main.py`,
  `C:\Topo-ai\cli\src\topo_cli\commands\auth.py`, `agents.py`.
* Agent: `C:\Topo-ai\agent\src\topo_agent\config.py`, `client.py`, `main.py`,
  `sensor_main.py`, `collector.py`; plugins `aws.py`, `azure.py`, `gcp.py`,
  Kubernetes credential entry points; backend Kubernetes collector/network
  enricher; installed botocore/azure-identity/google-auth credential-chain source.
* Operations/evaluation: `C:\Topo-ai\agent\deploy\kubernetes.yaml`,
  `topo-agent.service`, `install-windows.ps1`; `C:\Topo-ai\backend\.env.example`
  **names only**; `C:\Topo-ai\.github\workflows\secret-hygiene.yml`,
  `topo-lineage-provider-fixture.yml`; `C:\Topo-ai\evaluation\topo_client.py`,
  `runner.py`, `lineage_provider_truth.py`; scanner and test files in §11.

Search inventories included password/passwd/secret/token/api-key/authorization/
bearer/cookie/session/digest/hash/signature/HMAC/Basic/credential/private-key/
client-secret/keyring, all supported provider names, environment access sites,
ORM JSON/text fields, SDK constructors, logging/repr/error/URL paths and tests.

## 14. Custody and final acceptance reconciliation

Immutable text authority is committed **Git blob content**, not CRLF-expanded
Windows working-copy bytes. 0006 was not normalized or edited. Before and after
canonical SHA-256 values are identical:

| Migration | Before = after SHA-256 |
| --- | --- |
| 0001 | `B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD` |
| 0002 | `DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92` |
| 0003 | `907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F` |
| 0004 | `D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3` |
| 0005 | `14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333` |
| 0006 | `D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728` |
| 0007 | `8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84` |
| 0008 | `9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7` |

Protected binary authority is actual bytes, with **no normalization**:

| File | Before = after SHA-256 |
| --- | --- |
| `C:\Topo-ai\backend\data\topo.db` | `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E` |
| `C:\Topo-ai\evaluation\results\lineage\post-sc4\topo-product-32695735269.db` | `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F` |

Alembic script head count: **1**. Exact head:
**`0008_tenant_scoped_identity_namespace`**. No 0009. Protected artifacts,
existing migrations, product, evaluator, workflows, and tests unchanged.

Final verification outcomes below are based on the recorded local tool results.

| Requested completion item(s) | Result / evidence |
| --- | --- |
| 1–4 | Docs-only PH-4A; accepted HEAD/branch §1; verdict PASS (inventory only). |
| 5–8 | Product changed NO; migration created NO; one head, `0008_tenant_scoped_identity_namespace`. |
| 9–17 | Eight exact canonical before/after hashes above; existing migrations changed NO. |
| 18–21 | Exact actual-byte DB hashes above; both unchanged YES. |
| 22–30 | 56 roles: A8/B6/C20/D1/E0/F11/G10/H0. E absent currently; G current reference implementations listed, not an implemented generic SecretStore. |
| 31–36 | 11 direct ORM custody fields: digest7/plaintext-capable3/encrypted0/reference1/ambiguous0. Full 61-column incidental JSON inventory separately in §5. |
| 37–40 | Exact plaintext/digest/reversible fields §§3–5; environment/config names §7. |
| 41–46 | Server auth digests preserved; browser cookie boundary preserved; CLI keyring/env not token field; agent raw local custody gap §§3/6. |
| 47–51 | Exact GitHub/GitLab/Terraform/Jenkins/Azure verifier modes and reference custody §3.2. |
| 52–55 | Source reference not raw key; untyped config/PATCH echo and error risks; dead-letter payload copy, no payload read API or reloaded raw key §§5/6. |
| 56–59 | Webhook plaintext gap; global environment/SDK LLM/SCM credentials; cloud agent-local; unimplemented outbound providers explicitly distinguished §§3/7. |
| 60–64 | DB URL/parameter, Authorization, Cookie/Set-Cookie, provider signature, raw issuance/error audits §§6–8; no values disclosed. |
| 65–68 | 0 declared auth-secret query/path inputs; 5 unsafe configurable URL families; 0 browser storage credential writes; 0 dedicated raw CLI-profile token fields (URL caveat); explicit repr/debug risks §8. |
| 69–71 | SEC-1 preflight 8 passed in 0.08s; final 8 passed in 0.10s; tracked and explicit new-document scans exit0; scanner gaps enumerated §11. |
| 72–76 | P0=0/P1=7/P2=4/P3=1; active real secret found NO within inspected boundary. |
| 77–87 | Pluggable encrypted-DB baseline; schema/ref/envelope/AES-GCM/AAD/root/startup/rewrap/provider overlap/one-way rotation §9. |
| 88–90 | Legacy plaintext conversion required for supported configured reversible fields, not auth hashes; exact targets and DB-atomic/external-compensation design §9.5. |
| 91–94 | Exact PH-4B/C/D/E handoffs §12. |
| 95–96 | Threats20; unowned/unclassified0. |
| 97–98 | Created only this document; modified existing files NONE; helper files NONE. |
| 99 | `?? docs/architecture/production-hardening/ph-4a-secret-credential-provider-boundary-contract-v1.md` |
| 100 | `git diff --name-only`: empty (new document is untracked, not staged). |
| 101 | `git diff --check`: exit0, no findings; explicit untracked-document whitespace check also required below. |
| 102–105 | Active-exposure blocker NO; architecture blocker NO; custody blocker NO; first blocker NONE. |
| 106–108 | PH-4 closed NO; recommended next block PH-4B after architect review; STOP, no staging/commit/push or implementation. |

### Final executed checks

| Check | Result |
| --- | --- |
| SEC-1 pytest, final | **8 passed in 0.10s**, exit 0 |
| Tracked-tree scanner | **PASS**, exit 0; values never printed |
| Explicit untracked-document scanner | **PASS**, exit 0 |
| Document whitespace | No trailing whitespace; final newline present |
| All eight canonical migration hashes | Match accepted before/after values |
| Migration content diff from HEAD | Empty; 0006 not normalized or edited |
| Script heads | One: `0008_tenant_scoped_identity_namespace`; no 0009 |
| Developer DB and frozen LINEAGE actual-byte hashes | Both match accepted before/after values |
| Product/evaluator/workflow/test tracked diffs | Empty |
| `git diff --name-only`, `git diff --stat` | Empty: the only addition is untracked |
| `git diff --cached --name-only` | Empty; nothing staged |
| `git diff --check` | Exit 0, no findings |
| `git status --short` | Only the new document shown in item 99 |

Git status emits existing permission warnings for four `.pytest_cache`
directories (root, backend, agent, CLI); none was changed or deleted. A read-only
audit helper initially compared the full Alembic head to the shorthand `0008`
and asserted after all eight blob hashes had matched. The corrected comparison
to the actual full revision passed; this was not a migration/custody mutation or
a product test failure. No full backend/frontend/agent/evaluation suite, provider
experiment, or database migration was run for this docs-only checkpoint.

Only this document was created; existing files modified: none. No helper, product,
evaluator, workflow, test, or migration file was created or modified. No staging,
commit, push, branch switch, or history operation occurred. PH-4B is a handoff for
review, not work begun here.

PH-4A ACCEPTED / READY FOR ARCHITECT REVIEW
