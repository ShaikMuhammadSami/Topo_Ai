# PH-6C — Typed LLM / Customer-Data Egress Boundary v1

## 1. Decision and scope

PH-6C starts from commit `978a71251445f0992119dc057217de4b45866e0f`
on `security/ph-6c-typed-llm-customer-data-egress-v1`. The accepted PH-6B
destination, DNS, address-binding, TLS, redirect, proxy, credential-binding,
timeout, retry, response-bound, and bounded-error controls remain the network
authority. PH-6C adds the independent content decision: exactly what
tenant/customer data may cross an already authorized external connection.

This block introduces no route, permission, role, audit action/reason/field,
table, column, migration, cache, provider tool, execution authority, or new
external destination. Internal raw evidence and deterministic causal semantics
remain intact. The boundary is an outbound transformation, not a deletion or
reinterpretation of internal truth.

## 2. Frozen customer-data classes

The runtime policy reuses the eight accepted PH-6A classes exactly:

1. `PUBLIC_SYSTEM_DATA`
2. `TOPO_CONTROL_METADATA`
3. `TENANT_OPERATIONAL_METADATA`
4. `CUSTOMER_STRUCTURED_OPERATIONAL_DATA`
5. `CUSTOMER_USER_AUTHORED_CONTENT`
6. `RAW_CUSTOMER_PAYLOAD`
7. `AUTHENTICATION_SECRET`
8. `SECRET_MATERIAL`

No vague sensitive/safe/private replacement class was introduced.

## 3. External sink matrix

`app.security.customer_data_policy.EXTERNAL_DATA_SINK_POLICIES` is the
code-owned current sink registry:

| Sink | Allowed content | Transport-only material | Authenticated product behavior |
|---|---|---|---|
| `GITHUB` | public system, Topo control, tenant operational metadata | authentication secret | enabled through PH-6B exact GitHub origin |
| `TENANT_WEBHOOK` | Topo control, tenant operational metadata, structured operational data, explicitly supported user text | authentication secret and secret material | enabled through PH-6B tenant webhook policy |
| `OPENAI` | Topo control, tenant operational metadata, structured operational data, user text only for purpose-owned envelopes | authentication secret | enabled only through the PH-6B OpenAI adapter |
| `GROQ` | same logical content policy as OpenAI | authentication secret | enabled only through the PH-6B Groq adapter |
| `VERCEL_ANALYTICS` | public system data only | none | disabled for the authenticated product |

`RAW_CUSTOMER_PAYLOAD`, `AUTHENTICATION_SECRET`, and `SECRET_MATERIAL` are not
LLM request content. Webhook signing/protected-header secrets remain in their
existing destination-bound transport plane and never enter the JSON body.
Unknown sinks and disallowed class combinations fail closed. The registry does
not grant actor authorization, tenant selection, credential authority, or
network destination authority; PH-5, PH-3, PH-4, and PH-6B retain those jobs.

## 4. LLM purpose registry and provider-safe type

`app.security.llm_data_boundary.LLMEgressPurpose` freezes exactly eight
code-owned purposes:

- `INCIDENT_EXPLANATION`
- `INCIDENT_COPILOT`
- `INVESTIGATION_PLANNER`
- `POST_INCIDENT_REPORT`
- `EXECUTION_READINESS_SUMMARY`
- `UNIFIED_BRIEFING_SUMMARY`
- `SIMILARITY_SUMMARY`
- `RESPONSE_INTELLIGENCE_SUMMARY`

Each service selects its purpose by constructing a distinct envelope class.
No request parameter can select a purpose, data class, allowlist, scrub policy,
or bound. `SafeLLMRequest` is immutable and can only be constructed with the
module-private factory token after tenant validation, typed serialization, and
the total UTF-8 byte check. OpenAI and Groq dispatch accept only this type plus
code-owned instructions. They do not accept arbitrary dictionaries, internal
models, raw evidence, `model_dump()` output, `payload_json`, or `raw_payload`.

The serialized customer context contains the code-owned purpose and the typed
envelope. The tenant ID is held for validation but is excluded from provider
content. No provider-safe context cache or generic transcript persistence was
added.

## 5. Exact typed envelope fields

All models are frozen Pydantic models with `extra="forbid"`.

### Incident explanation

`LLMIncidentExplanationEnvelope` contains exactly:

- validation-only `tenant_id` (excluded from serialization)
- `incident_id`
- `prompt_version`
- `allowed_evidence_ids`
- `evidence_catalog`

Each evidence item contains only `evidence_id`, `evidence_type`, a bounded safe
statement, optional bounded `observed_at`, and up to 25 typed scalar facts.

### Incident Copilot

`LLMCopilotEnvelope` contains the explanation base plus:

- the explicit current `question`
- up to ten typed `conversation_history` messages

Message roles are limited to code-owned `user`/`assistant`; each message is
bounded and scrubbed. Session/incident tenant filtering occurs before envelope
construction.

### Investigation planner

`LLMInvestigationPlannerEnvelope` contains the same safe evidence base as the
explanation envelope. It receives deterministic incident/RCA/topology/action
facts only through the typed evidence references; no raw telemetry or provider
body is admitted.

### Post-incident report

`LLMPostIncidentReportEnvelope` contains the safe evidence base plus up to 50
explicitly extracted `responder_notes`. Each note is a bounded, scrubbed
user-authored string. The surrounding findings object is never serialized.

### Execution-readiness summary

`LLMExecutionReadinessSummaryEnvelope` contains:

- validation-only `tenant_id`
- `incident_id`, `policy_version`, `overall_execution_posture`
- `deterministic_summary`
- typed `actions`
- bounded `warnings`

An action may contain only its ID/title plus category, family, risk, status,
current evidence strength, historical support, rank, mutation/approval booleans,
and bounded missing-precondition/blocker/caution strings.

### Unified briefing summary

`LLMUnifiedBriefingSummaryEnvelope` contains:

- validation-only `tenant_id`
- incident ID/title/status/severity and deterministic summary
- one typed root-cause fact
- bounded typed recent changes and dependency-path facts
- optional typed blast-radius and ownership/business-impact facts
- bounded typed remediation actions and historical incidents
- optional typed outcome
- bounded warnings

### Similarity summary

`LLMSimilaritySummaryEnvelope` contains:

- validation-only `tenant_id`
- incident ID, historical support level, deterministic summary
- bounded typed current-analysis scalar facts
- bounded typed historical matches and resolution patterns
- bounded warnings

### Response-intelligence summary

`LLMResponseIntelligenceSummaryEnvelope` contains:

- validation-only `tenant_id`
- incident ID and response priority
- one typed root-cause fact
- overall historical support and deterministic summary
- bounded typed actions and warnings

## 6. Forbidden fields and opaque-data closure

No envelope admits `raw_payload`, `payload_json`, headers, cookies,
environment/config dumps, generic secret dictionaries, arbitrary unknown
fields, full ORM rows, or opaque internal serialization. Unknown fields are
rejected at construction. `SecretMaterial` is not a supported field type and
is rejected before dispatch.

Evidence transformation uses an explicit per-`EvidenceType` scalar-key
allowlist. A signal's remote summary is replaced with a code-owned normalized
statement, while safe signal category/severity/reason and identity/timestamp
facts remain available. Unknown values and nested objects are not stringified.

The exact marker `ph6c-opaque-raw-payload-marker` remains provably present in a
stored `NormalizedSignal.raw_payload` inside the acceptance test. The complete
real tenant-scoped service pipeline is then exercised for all eight OpenAI
purposes and all four Groq-backed purposes. Its provider-request occurrence is
zero for both providers. The marker is not deleted from internal evidence.

## 7. Text provenance, bounds, and scrub behavior

The central `scrub_outbound_text` function reuses the accepted PH-4
`safe_text` redactor and adds bounded private-key/PEM removal plus explicit
`[TRUNCATED]` clipping. It is used by every admitted title, normalized text,
Copilot/history message, responder note, webhook summary, webhook status note,
and webhook recommendation. Identifier fields are rejected rather than
truncated when invalid or credential-shaped.

Free-form provenance is deliberately narrow:

- Copilot question: the authenticated user's explicit model invocation.
- Copilot history: the last ten same-tenant messages in the permitted session.
- Responder notes: only the named `responder_notes` field from same-tenant
  investigation findings, at most 50 notes.
- Summary-envelope prose: deterministic Topo-owned fields already selected by
  the owning service.
- Signal evidence statement: code-owned, not the remote event message.

Frozen bounds are:

| Field/collection | Bound |
|---|---:|
| identifier/name | 256 characters |
| title | 512 characters |
| normalized text | 1,024 characters |
| Copilot question | 4,096 characters |
| responder note | 4,096 characters |
| conversation message | 4,096 characters |
| conversation messages | 10 |
| entity references | 50 |
| relationship facts | 100 |
| change facts | 50 |
| evidence references/claims | 100 |
| warnings | 50 |
| total serialized customer context | 65,536 UTF-8 bytes |

Collections are deterministically selected/capped. The total bound is checked
after typed construction, scrub, and serialization. Oversized contexts fail or
degrade before provider dispatch; no prefix of a raw object is sent.

Topo does not claim perfect semantic detection of every secret format a user
could intentionally paste. The defensible claim is that Topo-owned secret
sources and raw infrastructure payloads are structurally excluded, while known
credential patterns are scrubbed from the small set of admitted free-text
fields.

## 8. Tenant and authority boundary

Every builder receives the validated `DomainTenant` from its owning service.
Repository/service filtering happens first. Any admitted object that carries a
tenant identifier must match that authoritative scope; mismatch raises a
bounded `llm_tenant_mismatch` before dispatch. Tenant ID is not serialized.

LLM instructions, questions, and responses have no authorization, tenant
selection, credential, execution/remediation, ownership, or deterministic
RCA/evidence authority. The provider APIs configure no tools, functions,
function calls, or automatic execution. Existing structured response models
and evidence-ID validation remain authoritative. Model output remains untrusted
generated explanation/summarization content.

Provider request/response/envelope content is not logged or added to a generic
request table. Existing feature-owned generated result persistence remains
unchanged. Provider exceptions are converted to bounded type/status errors
without request or response bodies.

## 9. Provider parity and disabled mode

OpenAI and Groq receive the same `SafeLLMRequest.customer_context_json` for the
same logical request. Provider selection changes only the approved PH-6B
transport and provider response schema mechanics; it cannot admit additional
customer-data fields. All calls still use fixed provider hosts, verified TLS,
redirect denial, `trust_env=False`, bounded timeouts/responses, and the PH-6B
SDK adapters.

With no configured provider, or on bounded provider failure, the existing
deterministic result and controlled unavailable/fallback behavior remain.
Incident detection, topology, change correlation, evidence, RCA, blast radius,
ownership, and incident state have no live-LLM dependency.

## 10. Tenant webhook body contract

The outbound body is created only from `WebhookEvent`, a typed extra-forbid
contract. Its exact outer fields are:

- `event_id`
- `event_type`
- `occurred_at`
- constant `source="topo-ai"`
- `resource_type`
- `resource_id`
- scrubbed `summary`
- optional `severity`
- typed `payload`

Event-to-payload type matching is validated. Exact payload fields are:

| Event | Fields |
|---|---|
| incident created | incident ID, status, severity, cluster, optional namespace/snapshot/automatic/object kind/object name/analysis ID |
| incident status changed | incident ID, status, optional scrubbed status note, updated timestamp |
| recommendation generated | recommendation/analysis/signal IDs, action type, status, confidence, risk, optional target entity name |
| recovery result | verification/recommendation/analysis IDs, status, confidence, passed/failed/unknown counts |
| change risk detected | analysis/snapshot/root entity IDs, root name, change type, risk score/level, deployment decision, affected count, scrubbed recommendation |
| test | webhook ID and constant `test=true` |

Identifiers are bounded and reject credential-shaped values; descriptive text
is scrubbed. `raw_payload`, a `payload_json` field, signal/provider bodies,
headers, and secret objects cannot be added. The serialized body ceiling is
131,072 UTF-8 bytes. The existing delivery-record column named `payload_json`
continues to store the already validated outbound body for delivery semantics;
no `payload_json` key or internal raw payload is transmitted.

Signing secrets and protected headers are loaded only after PH-6B destination
approval and remain transport headers. They are not available to the typed body
model. The customer-data sink registry is checked before body serialization.

## 11. Browser analytics decision

Before PH-6C, `frontend/app/layout.tsx` globally imported and mounted
`@vercel/analytics/react`, so authenticated dynamic product routes could emit
route metadata containing tenant-owned resource identifiers. No separate,
already-safe public marketing layout exists.

PH-6C removes the global mount entirely. Authenticated application analytics
egress is disabled, tenant/resource identifier analytics count is zero, and no
public-only analytics mount is retained. The package dependency remains to
avoid unrelated lockfile churn; the security property is absence of runtime
mount/import. Same-origin browser-to-Topo API communication is unchanged.

## 12. PH-6B and frozen custody preservation

PH-6C does not change the PH-6B destination registry, resolver/address checks,
actual-address socket binding, SNI/Host identity, redirect policy, proxy
isolation, credential routing, response ceilings, or bounded public errors.
There is no arbitrary provider base URL, redirect-enabled LLM path, environment
proxy client, or direct service-level HTTP/SDK content call.

Frozen platform counts remain:

- 143 live routes; zero new, unknown, or duplicate routes.
- 98 PH-5 critical operations; zero unprotected.
- 18 permissions: 14 tenant, four installation, zero execution.
- 33 audit actions, 11 reasons, 15 fields.
- one Alembic head: `0015_security_audit`.
- ORM: 50 tables and 844 columns.
- new migration: no.

Canonical committed Git-blob SHA-256 values remain:

| Migration | SHA-256 |
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

Protected actual-byte SHA-256 values remain
`0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`
for `backend/data/topo.db` and
`9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`
for the frozen post-SC4 LINEAGE database. Migration and protected-artifact
diffs are empty.

## 13. Test receipts

All provider/network behavior in acceptance is mocked or uses controlled local
backends. No live OpenAI, Groq, GitHub, cloud, Kubernetes, or tenant webhook
request was made.

| Gate | Result |
|---|---|
| PH-2 focused | 82 passed; one warning |
| PH-3 focused | 180 passed, 54 skipped; two warnings |
| PH-4 focused | 130 passed, 75 skipped; one warning |
| PH-5 focused | 106 passed; one warning |
| PH-6A focused | 13 passed |
| PH-6B focused | 45 passed; one warning |
| PH-6C focused and real-provider-path marker matrix | 40 passed; one warning across the provider-path group |
| Full backend SQLite | 1,713 passed, 272 skipped; two warnings |
| Full backend PostgreSQL 16 | 1,977 passed, eight skipped; two warnings |
| Full offline evaluation | 917 passed, three skipped |
| Significant deterministic LINEAGE/causal group | 472 passed |
| Broad mocked LLM/customer-data group | 149 passed; one warning |
| Mocked GitHub/source/artifact group | 176 passed |
| CLI compile/full tests | compile passed; 85 passed |
| Agent compile/full tests | compile passed; 24 passed, one skipped |
| Frontend tests | 94 passed |
| Frontend typecheck | passed |
| Frontend lint | passed with 11 pre-existing warnings, zero errors |
| Frontend production build | passed |
| Backend/evaluation compile | passed |
| Secret scanner tests | 12 passed plus 14 subtests |
| Tracked-tree / explicit new-file secret scans | passed / five files, zero findings |
| `git diff --check` | passed; line-ending notices only, zero whitespace errors |

The PostgreSQL environment used `postgres:16-alpine`, an ephemeral loopback-only
port, a tmpfs data directory, no persistent volume, and `--rm`; the exact
container was stopped and removed after each run.

## 14. Remaining limitations and PH-6D handoff

Residual risk remains for an authenticated user intentionally pasting a secret
in an unknown format into an explicitly external Copilot question or responder
note. The design reduces this risk with structural secret-source exclusion,
known-pattern scrub, strict purpose/field allowlists, character/count bounds,
and an overall byte ceiling; it does not claim impossible perfect semantic
secret discovery.

PH-6D receives the complete PH-6A sink inventory, PH-6B destination/network
enforcement, and PH-6C typed customer-data/LLM/webhook/browser boundary. PH-6D
must adversarially combine SSRF, DNS rebinding, redirects, credential routing,
purpose confusion, raw/secret LLM leakage, cross-tenant context, prompt
injection authority, analytics leakage, webhook raw-data leakage, bounds,
errors, and provider failures. PH-6D is not started here.

PH-6C ACCEPTED / READY FOR ARCHITECT REVIEW
