# PH-6A — Outbound Network, Customer-Data Flow, and Egress Policy Contract v1

## 1. Scope, starting point, and verdict

PH-6A is a forensic inventory and future-policy contract. It adds no network
transport, runtime allowlist, DNS resolver, permission, route, migration, or
customer-data transformation. Production connection behavior is unchanged.
PH-6B owns central egress/SSRF enforcement. PH-6C owns typed external-LLM
envelopes. PH-6D owns combined adversarial closure.

The starting commit is
`50d990c5127ad852d5480057eb69d6b087d7688d` (`test(security): close
adversarial authorization acceptance (#89)`) on
`security/ph-6a-outbound-network-dataflow-policy-v1`.

Verdict: **PASS**. Two findings that would otherwise have stopped the inventory
have explicit architect decisions:

- tenant-configured outbound webhooks are V1 public-HTTPS-only and PH-6B owns
  enforcement; and
- raw customer payload is forbidden from external LLM content and PH-6C owns
  the typed-envelope repair.

Neither decision declares the current implementation safe. No later block has
been started.

## 2. Code-owned inventory and counting convention

`backend/app/security/egress_inventory.py` is a descriptive, unreferenced
registry. It cannot open a connection. Each entry represents one actual
network-dispatch expression or one distinct SDK operation passed through a
shared dispatch helper. Shared OpenAI dispatches are counted twice at the
physical boundary (text and structured) and separately as eight product
purposes/twelve provider paths. Higher-order Kubernetes collector operations
are counted by the SDK operation that the helper invokes.

There are **103 reviewed outbound callsites**:

| Runtime component | Count |
|---|---:|
| `SERVER_PRODUCTION_EGRESS` | 28 |
| `AGENT_CONTROLLED_EGRESS` | 64 |
| `CLI_USER_DIRECTED_EGRESS` | 1 |
| `BROWSER_CLIENT_EGRESS` | 2 |
| `EVALUATION_TEST_ONLY` | 8 |
| `DEAD_OR_UNREACHABLE` | 0 |
| `UNKNOWN` | 0 |

Production-runtime total excluding evaluation is **95**. The production source
contains no generic fetch route, egress-debug route, update
checker, package fetcher, registry/image fetcher, Redis client, queue/broker
client, WebSocket/gRPC client, curl invocation, or wget invocation.

Exact network libraries/clients are SQLAlchemy plus a DBAPI driver, HTTPX,
OpenAI SDK, Groq SDK, Kubernetes Python client/urllib3, boto3/botocore, Azure
Identity/management SDKs, Google Auth/Cloud SDKs, Docker SDK, browser `fetch`,
CLI HTTPX, and evaluation-only `urllib.request`, `gh`, `docker`, and `kubectl`.
The local socket uses in agent host/network plugins and evaluation readiness
checks are inspected non-egress/local-control operations.

## 3. Server production egress — exact inventory

Every entry records file, symbol, client, sync/async, method/protocol,
destination, scheme/host/port/path/query/body/header sources, credential source,
control flags, redirects, TLS, proxies, timeout, response bound, data classes,
response use, destination changes, and credential binding in the code registry.
All 28 are synchronous.

| Family and exact symbols | Count | Initial authority and request | Current redirect/DNS/TLS/proxy/limit behavior | Classification |
|---|---:|---|---|---|
| `database.py:create_engine` | 1 | `TOPO_DATABASE_URL`; SQLite or PostgreSQL; DB credentials and tenant/domain rows | Driver DNS/TLS; no HTTP proxy; no explicit socket timeout; query-specific response bounds | installation configured, medium |
| `GitHubConnector._get`, `_get_bounded_content` | 2 | installation `TOPO_GITHUB_API_URL`; code/provider repository paths; installation GitHub bearer | redirects disabled; HTTPX OS DNS, TLS verify for HTTPS, `trust_env=True`, default 20 s; JSON unbounded, content stream bounded | installation configured, medium |
| `GitHubConnector.download_actions_artifact` | 1 | GitHub API then provider `Location`; no customer body | manual maximum four hops; Authorization removed on origin change; HTTP currently permitted; final body/declared length capped at 32 MiB | remote-response-derived, high |
| `deliver_event_to_endpoint` | 1 | tenant-admin persisted URL; lifecycle JSON; protected headers/signature from tenant SecretStore | redirects disabled; current HTTP/HTTPS and arbitrary host/port/private resolution allowed; OS DNS, `trust_env=True`, 1–30 s; response body discarded | tenant-admin configured, **critical current finding** |
| OpenAI `generate_openai_text`, `generate_openai_structured` | 2 | SDK default OpenAI endpoint; installation SecretStore key; structured/user/raw content described in §11 | SDK `follow_redirects=True`, HTTPX max 20, OS DNS, TLS verify, environment proxy inherited, 60 s, two SDK retries, token-bounded response | remote-response-derived, high |
| Groq `_groq_answer`, `_groq_explanation`, `_groq_plan`, `_groq_report` | 4 | SDK default Groq endpoint; installation SecretStore key; JSON evidence catalog | SDK `follow_redirects=True`, HTTPX max 20, OS DNS, TLS verify, environment proxy inherited, 60/90 s, two SDK retries; no `max_tokens` supplied | remote-response-derived, high |
| backend Kubernetes SDK operations below | 17 | in-cluster config or kubeconfig/context; only trusted control-plane scope | urllib3 redirect default enabled; auth/cookie headers removed cross-origin by Retry; SDK/OS DNS, cluster CA/verification, no per-call timeout, unbounded list objects | remote-response-derived, high |

The 17 backend Kubernetes operations are:

1. version `get_code`;
2. namespace `read_namespace`;
3. namespace `list_namespace`;
4. namespaced/all deployments;
5. namespaced/all ReplicaSets;
6. namespaced/all Pods;
7. namespaced/all Services;
8. namespaced/all events; and
9. namespaced Services, Pods, Ingresses, and EndpointSlices in network
   enrichment.

Expanded, those are 1 + 2 + 2 + 2 + 2 + 2 + 2 + 4 = 17 callsites.

Server destination ownership is exact:

| Ownership | Count |
|---|---:|
| `CODE_FIXED` | 0 |
| `INSTALLATION_CONFIGURED` | 3 |
| `TENANT_ADMIN_CONFIGURED` | 1 |
| `PERSISTED_TRUSTED_RESOURCE` | 0 |
| `REMOTE_RESPONSE_DERIVED` | 24 |
| `REQUEST_OR_PAYLOAD_DERIVED` | 0 |
| `NONE` | 0 |
| `UNKNOWN` | 0 |

The initial LLM provider authorities are code-fixed, but the installed SDKs
follow remote `Location` responses; the effective destination classification
is therefore response-derived. The Kubernetes endpoint is installation
trusted, but urllib3 can also follow a control-plane response. This deliberately
does not hide the effective next-hop source.

Server risk is **0 low, 3 medium, 24 high, 1 critical**. The first/only critical
entry is `server.webhook.delivery-post`. Its PH-6A blocker is resolved only by
the frozen public-HTTPS policy in §8; the unsafe current implementation remains
open for PH-6B.

## 4. Agent, CLI, browser, and evaluation inventory

The agent has 64 controlled egress callsites:

| Agent family | Count | Exact operations / boundary |
|---|---:|---|
| Topo API | 1 | generic `AgentApiClient._request` to one operator-selected server; code-owned enrollment, heartbeat, snapshot, runtime, change, and signal paths |
| Native change watchers | 6 | AWS CloudTrail `lookup_events`; Azure `get_token` and fixed management API GET; GCP Logging `list_entries`; Kubernetes namespaced/all events |
| Kubernetes discovery | 15 | doctor namespaces; collect namespaces/nodes; all/namespaced deployments, ReplicaSets, Pods, Services, Ingresses, EndpointSlices |
| Docker discovery | 4 | doctor/collect `info`, networks list, containers list |
| AWS inventory | 20 | STS assume-role/caller identity; EC2 regions/VPCs/subnets/routes/security groups/instances; EKS clusters/nodegroups; ELBv2 load balancers/tags/target groups/health; RDS instances/tags; Lambda functions/tags |
| Azure inventory | 4 | credential token, subscription get/list, Resource Graph resources |
| GCP inventory | 14 | project search/get, folder/org get, network/subnetwork/firewall/route/instance/MIG/address/forwarding-rule lists, GKE clusters, Asset search |

Agent cloud destinations are SDK/provider controlled plus operator scope. AWS,
Azure, and GCP default credential chains can intentionally reach their own
workload/instance metadata credential endpoints. That is not tenant-generic
server SSRF. It must remain isolated to the agent SDK purposes. Agent Kubernetes,
Docker, and Topo server endpoints may legitimately be private because the agent
is deployed inside the customer infrastructure and its operator controls those
trusted destinations.

The CLI has one shared HTTPX request boundary to the local user's selected Topo
server. Redirects are disabled, timeout/retries are bounded, TLS verification
is default with an explicit user-selected insecure development option, and
JSON/download responses are fully buffered. This is user-directed egress, not
server SSRF.

The browser has one `apiFetch` boundary. It requires an `/api/` path and calls
same origin with `credentials: "same-origin"`; tenant and CSRF headers are
controlled by the UI/session contract. No frontend server-side fetch exists.

The production root layout also mounts one `@vercel/analytics/next` boundary.
It injects the same-origin `/_vercel/insights` script and the vendor runtime
emits automatic pageviews. Topo supplies no custom event properties or provider
credential, but route/path metadata can contain tenant-owned incident IDs. This
is browser egress and a real customer-data sink, not server SSRF. Development
and test builds do not mount it.

`next/font/google` is also imported by the root layout. Its font retrieval is a
Next.js build-time dependency rather than application-runtime customer-data
egress; production builds can therefore require network access unless the fonts
are vendored in a later block. No application source configures mutual TLS.

Eight evaluation-only entries cover `urllib.request` to Topo plus `gh`, Docker,
and kubectl dispatches in H3/LINEAGE/runtime observers. They use synthetic
fixtures/operator credentials and are excluded from production policy. Product
source has zero subprocess network callsites.

## 5. Schemes, private networks, ports, and URL shape

Current possible schemes by trusted boundary are:

- server database: `sqlite`, `postgresql`;
- server GitHub/webhook/Kubernetes: `http`, `https`;
- server LLM: `https` initially;
- agent Topo/Kubernetes: `http`, `https`;
- agent Docker: `npipe`, `unix`, `http`, `https`;
- cloud SDKs: provider HTTPS plus SDK-specific credential mechanisms;
- CLI/browser: `http`, `https`; and
- evaluation tools: tool-specific HTTP(S)/SSH/control-plane protocols.

There are **21 server callsites currently capable of plaintext HTTP**: three
GitHub, one webhook, and 17 trusted Kubernetes calls. Only four are external
application integrations; HTTP is permitted by current validators but is not a
proven production requirement. Kubernetes HTTP is a trusted control-plane
configuration capability, not a generic remote-application exception.

No production source hard-codes `verify=False`, `ssl=False`, `CERT_NONE`, or a
permissive SSL context: insecure-TLS implementation count is **0**. Agent and
CLI have explicit operator/user development overrides, not silent defaults.

HTTP userinfo is rejected by current GitHub, webhook, agent, and CLI URL
validators. HTTP secret-bearing URL count is **0**. The installation database
DSN may contain a DB password and is the one non-HTTP credential-bearing
connection string; PH-4 redaction remains authoritative. Webhook fragments and
credential-shaped URL parts are already rejected, but current host, address,
scheme, and port validation is insufficient.

Tenant-configured private/ULA endpoint requirement count is **0**. Exact V1
tenant integrations requiring private egress: **none**. Trusted/private
infrastructure classes are database, backend Kubernetes, agent Topo,
agent Kubernetes, agent Docker, and optional installation-configured GitHub
Enterprise (**six classes**). There is no generic private endpoint requirement.

Current loopback/link-local/arbitrary-port capability exists in installation or
local-user configuration for database, GitHub API, Kubernetes, agent Topo,
Docker, CLI, and development browser origins. The tenant-controlled webhook can
also currently select them and can currently reach metadata; this is the
critical PH-6B finding. Agent AWS/Azure/GCP credential chains can intentionally
reach provider metadata under SDK policy. No other request/payload-controlled
metadata path was found.

PH-6B canonicalization must reject integer/decimal and ambiguous hex/octal IPv4,
all IP literals for webhooks, bracketed IPv6, IPv4-mapped forbidden IPv4,
userinfo, fragments, non-443 effective ports, loopback, unspecified,
link-local, RFC1918, ULA, multicast, and reserved/special ranges. It must
normalize scheme, IDNA/punycode DNS hostname, case, trailing dot, and effective
port before matching. Matching is exact canonical authority, never prefix or
substring. Cloud metadata and local file/unix URLs are always forbidden for
tenant-driven HTTP.

## 6. DNS, redirects, proxies, and credential routing

Today HTTPX, urllib3, SDK transports, DB drivers, and the OS resolve their own
destinations. There is no application-owned DNS resolution or socket binding.
Webhook hostname validation followed by library re-resolution is **not DNS
rebinding safe**.

The PH-6B webhook transport must:

1. accept only canonical `(https, IDNA DNS hostname, 443)`;
2. perform controlled A/AAAA/CNAME resolution for every attempt;
3. reject the whole answer set if any address is forbidden, including mixed
   public/private answers;
4. connect the socket only to one validated current address while preserving
   the canonical Host header, TLS SNI, and certificate verification; and
5. avoid long-lived authorization caches.

If actual-address-constrained connection cannot be implemented safely, PH-6B
must stop with `PH-6B DNS_REBINDING_DESIGN_BLOCKER`. This is a mandatory PH-6B
implementation gate, not a remaining PH-6A policy decision.

Redirect-enabled server callsites are **24**: one GitHub artifact call, six LLM
dispatches, and 17 Kubernetes reads. GitHub uses four manually checked hops and
strips Authorization on any origin change. HTTPX (OpenAI/Groq) defaults to at
most 20 and removes Authorization/cookies cross-origin, but a method-preserving
redirect can still forward customer content. urllib3 removes auth/cookie
headers cross-origin. No callsite was found that deliberately forwards a
credential to a different origin; credential cross-destination issue count is
**0**. PH-6B should disable redirects by default and validate every allowed
provider-specific hop/address. Webhooks must never follow a redirect.

HTTPX callsites inherit environment proxy settings unless explicitly disabled:
GitHub (3), webhook (1), OpenAI/Groq (6), Azure Activity (1), agent Topo (1),
and CLI (1): **13 reviewed HTTPX boundaries**. Browser/SDK proxy behavior is
environment/tool controlled. No enterprise proxy requirement is proven.
Webhook PH-6B must set `trust_env=False`; any future proxy support requires an
Installation Operator-controlled design. Tenant Admin cannot configure a proxy.
Proxy credentials are never accepted from tenant request data.

Credential binding is:

| Credential | Bound destination |
|---|---|
| database credential | installation DB authority |
| GitHub bearer | configured GitHub API origin; manually stripped on artifact origin change |
| webhook protected headers/signing secret | target: persisted endpoint canonical HTTPS host:443 authority; not yet enforced at actual-address layer |
| OpenAI/Groq keys | SDK provider authority; HTTPX strips cross-origin Authorization |
| Kubernetes service account/kubeconfig | cluster authority from the same trusted configuration |
| AWS/Azure/GCP identity | provider SDK audience/authority |
| enrolled agent token | one agent-configured Topo server |
| CLI credential | one local-user profile server |
| browser session | same origin only |

No mutable cross-tenant default credential header or shared cross-tenant cookie
jar exists. Shared client counts are agent Topo (one), CLI Topo (one), Azure
Activity per poll context, and webhook per attempt; credentials are constructed
for their single authority. Generic inbound-sensitive-header forwarding count
is **0**. Arbitrary Host override count is **0**.

## 7. Timeouts, retries, response bounds, and errors

Exactly **82 production callsites lack an application-owned network timeout**:
41 cloud SDK operations, 34 Kubernetes SDK operations (17 backend and 17
agent/watcher), four Docker operations, the database driver connection, browser
`fetch` without an `AbortController`, and the browser analytics vendor runtime.
Provider/library defaults may still terminate some of these requests; they are
not a Topo-owned bound. Those findings are recorded, not repaired here. HTTPX
GitHub defaults to 20 seconds; webhook is clamped 1–30; Azure Activity is 30;
agent Topo is 60; CLI defaults to 30; OpenAI/Groq use 60/90 seconds.

Exactly **90 production callsites can consume data without a Topo-owned byte or
item bound**: database query rows, GitHub JSON, Kubernetes lists, provider SDK
pages, Docker collections, Azure Activity JSON, agent/CLI/browser JSON, the
analytics vendor resource, and Groq token output. GitHub source content is
streamed and capped; artifact bytes are checked/capped at 32 MiB; OpenAI
response tokens are caller bounded. The webhook response body is deliberately
not consumed and is not included in either count. Bounds apply after HTTP
decompression where HTTPX exposes decoded content; PH-6B must define
wire/decoded byte limits by purpose.

Exactly **83 production callsites are retry-enabled or retry-capable under the
current configured/library policy**: six OpenAI/Groq calls, one webhook, one
agent Topo boundary, one CLI boundary, 34 Kubernetes SDK calls, 21 AWS SDK
calls, four Azure inventory SDK calls, and 15 Google SDK calls. Azure Activity's
direct HTTP request is not counted. Kubernetes/urllib3 can retry/redirect under
SDK policy. GitHub
connector does not retry API calls; artifact hops are redirects, not retries.
The webhook POST can currently be retransmitted without an idempotency key;
receivers must tolerate duplicate delivery. PH-6B must distinguish idempotent
reads from mutations and count every retry as a fresh destination/DNS decision.

Network errors are converted to product-specific unavailable/failure states.
Safe exception/redaction utilities avoid credential rendering. HTTPX request
logging may expose method/URL but PH-4 URL redaction remains required for
application errors. Response bodies are not generically returned to callers;
provider error payloads are either discarded/safely summarized or handled by
SDK exception policies. PH-6B errors must not disclose resolved private IPs,
credentials, protected headers, or raw provider bodies.

## 8. Frozen V1 tenant-webhook policy

Tenant Admin intentionally chooses an arbitrary **public HTTPS** integration
sink, not a private-network capability. V1 permits only:

- scheme `https`;
- a canonical IDNA DNS hostname (no IP literal); and
- effective port 443 with certificate and hostname verification.

It rejects HTTP, userinfo, fragments, credential-bearing path/query forms,
non-443 ports, localhost/private/link-local/ULA/reserved/special/metadata
addresses, private DNS, cluster-local names, and mixed DNS answers. Redirects
are false and every 3xx is terminal. Protected headers/signing secrets are
bound to the exact canonical authority. Origin changes require existing
`integration.manage` **and** `credential.rotate`, followed by full validation.
Path-only same-origin changes do not create a new credential authority.

Create/update validation is insufficient: normal delivery and `/test` must
perform the same delivery-time central policy and current controlled DNS/socket
binding. Environment proxy inheritance is disabled. Private/self-hosted
webhooks are outside V1; a future need requires a narrow Installation
Operator-controlled architecture, not Tenant Admin private egress.

No PH-5 permission, audit schema, route, or persistent network-policy state is
added by this decision.

## 9. Customer-data classification and external sinks

The minimum closed classes are:

| Class | Meaning |
|---|---|
| `PUBLIC_SYSTEM_DATA` | public/static product/provider data |
| `TOPO_CONTROL_METADATA` | non-secret Topo IDs, operation types, bounded timestamps |
| `TENANT_OPERATIONAL_METADATA` | tenant resource/service names, topology and incident IDs |
| `CUSTOMER_STRUCTURED_OPERATIONAL_DATA` | normalized failure/change/evidence facts |
| `CUSTOMER_USER_AUTHORED_CONTENT` | explicit authenticated notes/prompts |
| `RAW_CUSTOMER_PAYLOAD` | unfiltered provider bodies, telemetry/logs/config/environment/opaque serialization |
| `AUTHENTICATION_SECRET` | API/bearer/provider authentication material |
| `SECRET_MATERIAL` | protected headers, passwords, private keys, SecretStore/root material |

This does not claim a general PII detector. Free-form fields named message,
description, summary, reason, or detail are not automatically safe.

There are **15 production external sink families**:

| Sink | Data classes sent/stored across boundary | Credential plane |
|---|---|---|
| installation database | tenant metadata, structured data, raw payload, encrypted/secret records | DB secret in installation authority |
| GitHub API/artifact | control/tenant query metadata | GitHub bearer |
| backend Kubernetes | control/tenant query metadata | cluster auth |
| tenant webhook | control, tenant, structured, possibly raw event fields | protected headers/signature |
| OpenAI | control, tenant, structured, user text, **current raw exposure** | OpenAI API key header |
| Groq | control, tenant, structured, user text, **current raw exposure** | Groq API key header |
| agent Topo | control, tenant, structured, raw discovery/telemetry | agent bearer |
| agent AWS | control/tenant scope | AWS credential/signature |
| agent Azure | control/tenant scope | Azure bearer |
| agent GCP | control/tenant scope | Google credential |
| agent Kubernetes | control/tenant scope | cluster auth |
| agent Docker | control/tenant scope | daemon/TLS auth if configured |
| CLI Topo | control, tenant, structured, user text | API credential |
| browser Topo | control, tenant, structured, user text | same-origin session cookie |
| browser Vercel Web Analytics | public/browser/control/tenant route metadata; no custom event properties | no Topo provider credential |

`RAW_CUSTOMER_PAYLOAD` reaches five sink families: internal database, tenant
webhook, OpenAI, Groq, and the customer's agent-to-Topo channel. This count
does not mean all five have the same trust policy. The two external LLM sinks
are the forbidden current exposure. Authentication material reaches provider
headers as required for 13 credentialed sink families, but it is not an LLM
content field. `SECRET_MATERIAL` reaches the installation database and approved
webhook credential header plane, never LLM content.

No other telemetry/analytics vendor, update service, external media/image
fetcher, or unlisted third party receives customer data. Provider
retention/residency is
not controlled or promised by this source tree; deployment documentation must
state provider contract/region limitations rather than imply zero retention.

## 10. Exact raw-signal-to-LLM finding

The verified current path is:

```text
Kubernetes event collector sanitize_for_serialization
  -> NormalizedSignal.raw_payload
  -> signal_repository SignalRecord.payload_json
  -> incident_explanation._record_data / evidence data
  -> local recursive key scrub and/or llm_client.sanitize_structured
  -> OpenAI or Groq request
```

An opaque JSON string is a scalar to the current key-based scrubbers, so nested
content is not inspected. The frozen synthetic marker
`ph6c-opaque-raw-payload-marker` survives the Copilot, planner, report, and
shared OpenAI scrubbers. The PH-6A test intentionally proves that current
exposure; it is not a desired-behavior assertion.

Architect decision:

- current implementation exposure: **YES**;
- target contract: `RAW_CUSTOMER_PAYLOAD` is never automatically allowed in an
  external LLM content envelope;
- raw internal evidence storage remains unchanged; and
- implementation closure owner: **PH-6C**.

PH-6C must turn this marker into a negative mocked-provider regression: it may
remain in internal storage but must be absent from every external request.

## 11. Complete LLM inventory

There are eight product purposes and twelve provider paths. OpenAI is available
to all eight through the central client; four evidence-rich families also call
Groq directly, giving four central-client bypasses.

| Purpose | Inputs and provenance | Raw / free-form / user text | Bounds and sanitizer | Persistence / consumer |
|---|---|---|---|---|
| incident explanation | incident, signals, changes, topology, RCA, blast, investigation `GroundingEvidence` | raw yes; free form yes; user no | evidence default 50; OpenAI shared scrub; Groq model dump; opaque strings survive | validated explanation/evidence JSON persisted |
| incident Copilot | authenticated question, last 10 messages, incident evidence | raw yes; free form yes; user yes | history 10; local scrub plus shared scrub; no PH-6C byte envelope | question/history and validated answer/evidence IDs persisted |
| investigation planner | incident/RCA/topology/change/blast evidence | raw yes; free form yes; user no | selected evidence; local/shared scrub; opaque strings survive | validated plan/steps/evidence IDs persisted |
| post-incident report | incident/RCA/outcome/plan/findings/actions/evidence/responder notes | raw yes; free form yes; user yes | selected evidence; local/shared scrub; opaque strings survive | validated report/evidence JSON persisted |
| execution-readiness summary | deterministic readiness/action context | raw no; free form yes; user no | bounded structured service context/shared scrub | optional narrative returned, not authority |
| unified briefing summary | derived compact briefing sections | raw no; free form yes; user no | bounded presentation lists/shared scrub | optional `ai_summary` returned |
| similarity summary | deterministic current/similar incident facts | raw no; free form yes; user no | bounded candidate list/shared scrub | optional explanation returned |
| response-intelligence summary | deterministic action/history facts | raw no; free form yes; user no | bounded actions/history/shared scrub | optional narrative returned |

Tenant filtering occurs before request assembly: every service receives the
authorized tenant ID and uses tenant-scoped incident/evidence/history
repositories. No cross-tenant cache or global context builder was found.

Providers are OpenAI and Groq. Base URLs are SDK defaults; the product exposes
no tenant or installation arbitrary model base URL. API keys are late-loaded
from installation SecretStore. Provider/model selection is installation
environment configuration. OpenAI/Groq SDK normal HTTP logs are not configured
by product code. Product prompt logging count is **0** and response logging
count is **0**. Provider requests are not persisted as request transcripts.
Generated validated output is persisted only where the owning product feature
already persists explanations, Copilot messages, plans, or reports; optional
summary outputs are returned/embedded by their services.

Authorization secrets, session cookies, API credentials, provider/webhook
tokens, protected headers, database passwords, private keys, and SecretStore
plaintext are absolute LLM-content exclusions. The OpenAI/Groq API key is a
transport authentication header, not prompt content. No code path makes LLM
output authoritative for authentication, authorization, tenant selection,
credential use, execution/remediation, deterministic RCA, evidence truth,
blast radius, ownership, or outcome. Tool/function automatic execution count
is **0**.

Prompt injection remains untrusted data, not authority. Structured response
models and evidence-ID validation constrain output, but sanitizing instructions
does not make remote text factual. Deterministic Topo evidence remains the
source of truth.

When a provider/key is absent or a request fails, deterministic responses still
work: explanation/planner/report use their existing deterministic fallbacks or
controlled provider-unavailable states; briefing/similarity/response/readiness
return structured results with unavailable/warning status. Core incident,
topology, change, RCA, blast, ownership, and response facts do not require LLM.

## 12. Proposed PH-6C typed envelopes

PH-6C must implement four purpose-specific allowlists, not one rich incident
dictionary and not `model_dump()`/`dict()`/`json.dumps()` of arbitrary models:

- `LLMIncidentExplanationEnvelope`: bounded incident ID/title/status/severity/
  time, safe entity refs, normalized signal codes/change facts, causal claims,
  topology relationship facts, blast totals, ownership labels, evidence claim
  refs, warnings.
- `LLMCopilotEnvelope`: incident ID, explicit bounded user question, bounded
  conversation roles/content, compact incident facts, causal claims, topology
  facts, evidence claim refs.
- `LLMInvestigationPlannerEnvelope`: incident facts, root entity ref, causal
  claims, normalized changes, topology facts, blast totals, existing validation
  checks, evidence claim refs.
- `LLMPostIncidentReportEnvelope`: incident/timeline facts, causal verdict,
  resolution facts, outcome metrics, bounded responder notes, evidence refs.

Unknown fields are not serialized. `raw_payload`, `payload_json`, full events,
provider/webhook bodies, logs/telemetry blobs, environment/config, headers,
opaque serialized objects, and complete ORM/model dumps are forbidden.

Proposed conservative bounds, derived from current fixture cardinalities and
the existing 10-message/50-evidence conventions, are: identifiers/names 256
characters, title 512, normalized text 1,024, explicit question/responder note
4,096 each, conversation 10 messages, 50 entity refs, 100 relationship facts,
50 change facts, 100 evidence refs, 50 warnings, and 65,536 total serialized
UTF-8 bytes per request. PH-6C must measure the final typed fixtures and may
tighten these; widening requires review.

Boundary order is mandatory:

```text
authorized tenant-scoped deterministic state
  -> purpose-specific typed allowlist
  -> field/count/byte bounds
  -> secondary central secret-pattern scrub
  -> provider transport
```

The scrubber is defense in depth, never permission to send raw payload. Copilot
user text is allowed only for the authenticated operation that explicitly
submits it, with tenant scope/history bounds/scrub and no authority semantics.

## 13. SDK/provider findings

AWS uses boto3 sessions, optional profile/role assumption/external ID, code-owned
service clients/regions, standard botocore signing/retries, and provider
pagination. It exposes no endpoint URL override in the plugin. The default
credential chain may deliberately use web identity, ECS credentials, or EC2
IMDS. Such metadata access is agent-only provider authentication and must never
become a general server egress purpose.

Azure uses Workload Identity or `DefaultAzureCredential`, Subscription and
Resource Graph SDKs, and a code-fixed Activity Log host. Resource Graph
`skip_token` is passed as an opaque SDK pagination field; it is not dereferenced
as a URL. Azure SDK retries transient/408/429/5xx failures within configured
attempt bounds. Managed Identity may intentionally use Azure metadata.

GCP uses ADC, optional service-account impersonation, code-owned Cloud clients,
Google Retry, and SDK pagers. Asset/project/resource pagination objects are not
direct arbitrary URLs. ADC can intentionally use GCE metadata. No custom
endpoint override was found.

GitHub `_get` pagination is code-owned query data. Artifact `Location` is the
one server-side remote-response-derived download family. Current origin checks
protect the bearer but do not validate public address/DNS or forbid HTTP
downgrade; PH-6B owns every-hop policy.

Kubernetes server and agent clients use in-cluster service-account or trusted
kubeconfig authority. Backend calls are read-only GET/list discovery. Private
cluster endpoints are required trusted infrastructure, not tenant-configured
webhook exceptions. Cluster CA/hostname behavior must remain intact; PH-6B must
not force public-only rules onto infrastructure SDKs.

The database is an installation-owned internal datastore connection. No Redis,
message broker, or internal microservice HTTP dependency exists. PH-6B must not
mistake DB/private control-plane traffic for attacker-selected application
egress.

## 14. Request/response and minimization observations

GitHub sends repository/provider identifiers and query parameters; Kubernetes
and cloud SDKs send account/cluster/resource scope; webhook sends lifecycle
event JSON; agent sends inventory/telemetry/failure/change batches; CLI/browser
send user-intended Topo API models; LLM sends the currently assembled evidence
contexts above. Query strings are not assumed non-sensitive and must remain
redacted in errors/logs.

No inbound `Authorization`, Cookie, proxy header, `Host`, or arbitrary header
map is generically forwarded. Webhook protected headers are decrypted from an
authorized tenant record, validated by PH-4 policy, and intentionally sent only
to that integration. GitHub and LLM SDK clients do not share tenant cookies.

Streaming is used only for bounded GitHub source content. Other calls are
synchronous and generally not cancellation-aware beyond timeouts/process
cancellation. PH-6B should centralize HTTP-only purposes without pretending it
controls SDK/database cancellation.

## 15. Proposed PH-6B central egress contract

PH-6B should add a non-caller-extensible purpose registry and a central HTTP
transport for exact server HTTP purposes. A caller selects a code-owned purpose
and supplies only that purpose's typed inputs; it cannot supply schemes,
arbitrary headers, proxy, redirect policy, network-class bypasses, or a
`skip_validation` boolean.

Proposed purposes:

- GitHub API JSON read;
- GitHub bounded source-content read;
- GitHub provider-artifact download with reviewed every-hop rules;
- tenant public webhook delivery/test;
- OpenAI text/structured provider call; and
- Groq structured provider call.

Cloud/Kubernetes/database SDKs retain dedicated adapters and explicit trusted
infrastructure classifications. They must not be squeezed through a generic
HTTP client.

The central HTTP policy owns canonicalization, allowed method/scheme/port,
current DNS validation and socket binding, TLS/SNI/Host, redirects, environment
proxy policy, per-purpose credentials/headers, connect/read/write/pool timeout,
retry/idempotency, encoded/decoded response limits, safe errors, and metrics.
No public route exposes this transport. There is no generic fetch method.

Webhook is fixed to public HTTPS DNS host:443, no redirect, no environment
proxy, and current-address connection. GitHub/LLM redirects default off; any
provider-required redirect is independently authorized per hop with credentials
and bodies constrained. Localhost development exceptions must be exact,
operator-controlled, disabled in production, and unusable from tenant input.

PH-6B makes no new permission or schema by default. Installation-wide proxy or
private-egress needs require separate architecture review.

## 16. PH-6D adversarial handoff

PH-6D must attack at least:

- webhook loopback/RFC1918/ULA/link-local/metadata/IP literals, integer and
  mapped forms, mixed public/private A/AAAA, CNAME to forbidden, DNS change,
  IDNA/case/trailing dot, userinfo, fragments, non-443 ports;
- redirect cross-origin, HTTPS-to-HTTP, different port, protected headers,
  method-preserving body replay, retry re-resolution, and environment proxies;
- GitHub artifact forged/multi-hop locations, response-size/decompression, and
  same/cross-origin bearer handling;
- purpose confusion, caller-supplied arbitrary header/host/path/scheme, bypass
  flags, and error/log disclosure;
- all four typed LLM envelopes with the exact opaque raw marker, secret-shaped
  fields, prompt injection, oversize/count overflow, unknown fields, cross-
  tenant context, arbitrary base URL, logging, response authority, and provider
  failure; and
- agent/provider metadata boundaries so central server policy neither grants a
  generic metadata capability nor breaks legitimate SDK identity.

## 17. Frozen route, authority, audit, and schema custody

PH-6A changes no HTTP route or authority:

- routes: **143**, new 0, unknown 0;
- PH-5 critical operations: **98**;
- permissions: **18** (14 tenant + 4 installation), execution 0;
- security-audit actions/reasons/fields: **33 / 11 / 15**, unchanged;
- Alembic heads: **1**, head `0015_security_audit`;
- ORM: **50 tables / 844 columns**; and
- migration created: **NO**.

No new network policy is caller-controlled. Authentication, tenant isolation,
SecretStore, permission checks, target-aware credential administration, audit,
provider verification, agent fixed-purpose authority, identity, and causal/
evidence semantics remain frozen.

## 18. Migration and protected-artifact custody

Canonical Git-blob SHA-256 values, before and after, are:

| Migration | Accepted SHA-256 |
|---|---|
| 0001 | `B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD` |
| 0002 | `DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92` |
| 0003 | `907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F` |
| 0004 | `D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3` |
| 0005 | `14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333` |
| 0006 | `D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728` |
| 0007 | `8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84` |
| 0008 | `9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7` |
| 0009 | `20B1109D75E78F511B346F1D85DA8FA7FB9F6CAA8B8A92347A2859BA2D35CA5C` |
| 0010 | `4303D0826DCE3E8FB0750A376CB68B8ABCBA7E1D62296BEE23A1782EAA3EDCF4` |
| 0011 | `15E89A6B4BDF00FC7334E7A7D0128251B378803A98771700066568683F234DF8` |
| 0012 | `C5028EDB83D75542494619EEE267940955B54AC1A6284873A4A8A7C5A46F440D` |
| 0013 | `7388CBFD71B0EC35F945545B813BDB08D177C263AB34348E36449BF44DA91B29` |
| 0014 | `864328578509AEA48B28F2FE6B705DA3D8F609424C553DB9B0070253B751BC9F` |
| 0015 | `C6C57FD42AC84BB46AACBA3F927F10FF77269937A4B5A44F0725A3E9BE95DA8D` |

Migration diff is empty. Protected actual-byte artifacts are expected to remain:

- `backend/data/topo.db`:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`;
- `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

## 19. Limitations and explicit blocker accounting

This block does not claim network-layer firewalling, service-mesh policy,
Kubernetes NetworkPolicy, cloud security-group policy, proxy isolation, DNS
pinning, data residency, provider zero-retention, perfect PII detection, or
external-LLM raw-data safety.

Blocker results after the two architect decisions:

| Stop condition | Result |
|---|---|
| SSRF architecture | resolved policy; current webhook repair assigned PH-6B |
| private egress | no blocker; tenant webhook private egress is outside V1 |
| DNS rebinding | no PH-6A blocker; mandatory actual-address PH-6B gate frozen |
| unsafe protocol / plaintext / TLS | no required external unsafe protocol, HTTP, or disabled TLS found |
| credential egress/isolation | no blocker; no cross-origin credential forwarding or cross-tenant client state found |
| secret URL/header forwarding | no HTTP secret URL or generic inbound header forwarding found |
| LLM authority/tool | no authority and no tool execution |
| LLM raw data | resolved policy; current implementation repair assigned PH-6C |
| LLM secret/tenant/destination | no content-secret, cross-tenant, or arbitrary-base-URL blocker found |
| LLM availability/logging | deterministic core works without provider; no product prompt/response logging |
| persistence/foundation/custody | none required or changed |

First unresolved blocker: **none**. PH-6 as a whole is **not complete**.

## 20. Verification receipts

All verification used mocked/offline provider and LLM boundaries; no live
provider, LLM, Kubernetes, or evaluation experiment was invoked.

| Gate | Exact result |
|---|---|
| PH-2 focused regression | 86 passed; 1 warning |
| PH-3 focused regression | 227 passed, 86 skipped; 2 warnings |
| PH-4 focused regression | 139 passed, 89 skipped; 1 warning |
| PH-5 focused/closure regression | 190 passed, 35 skipped; 1 warning |
| PH-6A inventory/sink/LLM contracts | 13 passed |
| Full backend SQLite | 1,652 passed, 272 skipped; 2 warnings |
| Full backend PostgreSQL 16 | 1,916 passed, 8 skipped; 2 warnings |
| Full offline evaluation | 917 passed, 3 skipped |
| Significant deterministic LINEAGE subset | 318 passed |
| Mocked LLM regression group | 276 passed; 1 warning |
| CLI | 85 passed |
| Agent | 24 passed, 1 skipped |
| Frontend configured tests | 93 passed |
| Backend / evaluation / CLI / agent compileall | passed (four commands) |
| Secret-scanner tests | 12 passed, 14 subtests passed |
| Tracked-tree secret scan | passed, zero findings |
| New PH-6A file secret scan | passed, zero findings |
| `git diff --check` | passed |

The PostgreSQL 16 run used a disposable loopback-only container with the data
directory on tmpfs and no persistent volume. It was stopped and auto-removed
after the run. Migration Git-blob hashes and protected database actual-byte
hashes match §18; migration diff and staged diff are empty.

PH-6A ACCEPTED / READY FOR ARCHITECT REVIEW
