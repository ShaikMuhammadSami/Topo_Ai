# PH-6D adversarial network and customer-data acceptance / PH-6 closure v1

## Decision

Verdict: `PASS_PH6_CLOSE`.

PH-6D falsified the combined PH-6A inventory, PH-6B network boundary, and
PH-6C typed customer-data boundary using controlled resolvers, an instrumented
HTTPCore backend, mocked providers, isolated tenant fixtures, static
completeness checks, and the full product regression matrix. Two concrete,
bounded defects were found and repaired. No route, permission, audit action,
schema, persistence, tenant-authority, credential-authority, execution, or
causal/evidence semantic was added or changed.

Starting main commit: `361fc68` (`feat(security): enforce typed customer data
egress (#92)`). Acceptance branch:
`security/ph-6d-adversarial-network-data-boundary-closure-v1`.

## Frozen contracts

The accepted contracts remain:

- 143 routes, 98 critical PH-5 operations, zero unknown or duplicate routes,
  and zero unprotected critical operations.
- 18 permissions: 14 tenant, four installation, zero execution.
- security audit: 33 actions, 11 reasons, 15 durable fields.
- six server egress purposes: `GITHUB_API_JSON_READ`,
  `GITHUB_SOURCE_CONTENT_READ`, `GITHUB_ARTIFACT_DOWNLOAD`,
  `TENANT_WEBHOOK_DELIVERY`, `OPENAI_PROVIDER`, and `GROQ_PROVIDER`.
- eight customer-data classes, five reviewed external data-sink policies,
  eight LLM purposes, and eight typed LLM envelope types.
- one Alembic head, `0015_security_audit`; 50 ORM tables and 844 columns.
- no generic fetch purpose, bypass flag, arbitrary LLM context API, LLM tool
  execution, authenticated analytics mount, new route, new permission, new
  audit action, new migration, or new persistent policy state.

PH-6D did not change the private GitHub Enterprise exception, public-only
tenant-webhook policy, actual-address transport design, provider destination
policy, customer-data vocabulary, SecretStore, tenancy, or PH-5 authority.

## Bounded defects and repairs

### First divergence: multicast destination classification

Attack: a DNS hostname resolved to `224.0.0.1` or `ff02::1`.

Root cause: the address classifier used `ipaddress.is_global` before an
explicit multicast check. Python reports globally scoped multicast in a way
that made those answers eligible as public external destinations.

Repair: `_address_kind` now rejects loopback, link-local, multicast,
unspecified, and reserved addresses before considering `is_global`. RFC1918
and IPv6 ULA classification remains unchanged. The 30-minute/runtime,
provider, redirect, DNS-resolution, and actual-socket semantics were not
changed.

Proof: the complete 115-case PH-6D network family passed after the isolated
repair, including IPv4 and IPv6 multicast answers. The full SQLite,
PostgreSQL, evaluation, and LINEAGE suites subsequently passed.

### Second divergence: unbacked LLM evidence identifier

Attack: an `LLMEvidenceEnvelope` used an `allowed_evidence_ids` value absent
from its tenant-validated `evidence_catalog`.

Root cause: normal service builders derived both collections from the same
scoped evidence, but the envelope model did not independently enforce that
relationship. An internal forged/unbacked identifier could therefore enter a
provider request.

Repair: the shared evidence-envelope validator now rejects every allowed ID
that is not present in the envelope catalog with the bounded
`llm_evidence_reference_invalid` error. Empty evidence remains supported and
model output validation remains owned by the existing services.

Proof: the PH-6D customer-data attack fails before provider construction, the
complete PH-6C plus PH-6D customer-data regression passed, and every product
and evaluation suite passed after the repair.

No architecture-level defect was found.

## Network attack matrix

| Boundary | Adversarial proof | Result |
|---|---|---|
| Loopback | `127.0.0.1`, `127.1`, `127.255.255.255`, `::1`, IPv4-mapped loopback | denied before dispatch |
| RFC1918 | `10/8`, lower/upper `172.16/12`, `192.168/16`, direct and DNS-derived | denied |
| ULA/link-local | `fc00::1`, `fd00::1`, `fe80::1`, `169.254.1.1` | denied |
| Metadata | direct/DNS-derived `169.254.169.254` and mapped IPv6 | zero socket dispatch |
| Special | IPv4/IPv6 unspecified, multicast, reserved/documentation and broadcast-like values | denied |
| Public IP literal | globally routable literal | denied because webhook authority requires DNS hostname |
| Ambiguous IP | decimal integer, hexadecimal, octal-like and shortened IPv4 forms | denied |
| URL structure | userinfo, fragments, control characters, credential path/query, six non-HTTPS schemes and six non-443 ports | denied |
| Canonical authority | mixed case, trailing dot and equivalent IDNA/punycode forms | one canonical origin |
| Mixed DNS/CNAME result | public plus RFC1918, ULA, link-local or metadata; final forbidden result | entire set denied |
| DNS rebinding | public policy resolution followed by hypothetical private library resolution | no independent second hostname resolution |
| Retry rebinding | first public answer, second private answer | first may dispatch; retry denied before connect |
| Connection reuse | keepalive/pool reuse disabled for central clients | fresh destination decision per new connection |
| Transport triple | instrumented valid webhook | socket is validated IP; Host and SNI are canonical DNS hostname |
| TLS | default SSL context inspected | `CERT_REQUIRED`, hostname checking enabled, no `verify=False` path |
| Environment proxy | hostile `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, including credential-bearing proxy URL | ignored; proxy dispatch count zero |

The mandatory triple proof observed socket target `93.184.216.34:443`, HTTP
Host `hooks.example`, and TLS `server_hostname=hooks.example`. Certificate
verification used `ssl.CERT_REQUIRED` with `check_hostname=True`. The resolver
was called once; the controlled socket backend received the validated address,
not the hostname.

## Redirect, credential and response attacks

All 30 webhook combinations of 301/302/303/307/308 with same-origin,
cross-origin public, HTTP downgrade, private, metadata, and non-443 locations
made exactly one request. Second-request, protected-header replay, signing
secret replay, and POST-body replay counts were zero.

Blocked webhook destinations are rejected before SecretStore material is
loaded or protected headers/signatures are prepared. A destination approved at
configuration time is re-resolved at delivery/retry time. An actor with only
`integration.manage` may change a path/query on the same canonical origin but
cannot change origin without `credential.rotate`; an authorized unsafe origin
still fails at PH-6 policy, distinct from PH-5 authorization denial.

GitHub Enterprise RFC1918/ULA access remains limited to the exact configured
GitHub origin and GitHub API/source purposes. It never transfers to a different
private artifact host. Cross-origin public artifact hops receive no GitHub
Authorization header. Forged artifact locations covering loopback, metadata,
RFC1918, ULA, link-local, HTTP, non-443 and userinfo are denied before a second
connection. Four dispatched artifact hops are the maximum; no fifth request is
made. Signed query material is not logged, audited, or returned in public
errors.

OpenAI is fixed to `api.openai.com:443`; Groq is fixed to
`api.groq.com:443`. Cross-provider host/credential swaps fail before network
dispatch. Both provider transports ignore environment proxies and follow zero
redirects. The 301/302/303/307/308 provider matrix produced no second request
and no body/credential replay.

GitHub JSON rejects declared and streamed bodies above 2 MiB, source reads
reject above 160 KiB, and artifacts reject above 32 MiB. Non-identity content
encoding fails closed before automatic decompression. Central provider
responses retain the accepted 8 MiB bound. Network failures expose only
bounded semantic error codes, never URL, resolved address, signed query,
credential, provider response, or customer prompt.

## Purpose and transport completeness

The six-purpose enum and profile map are exact. Unknown strings fail closed.
One purpose cannot be supplied through request/customer input or exchanged
with another purpose's broader policy. A typed LLM request is not a webhook
body, a webhook event is not an LLM request, and a GitHub artifact destination
cannot use an LLM/provider purpose.

Production server HTTP construction remains centralized in
`services/egress_http.py`. OpenAI and Groq SDK construction remains centralized
in `services/llm_client.py`, with only the central purpose-specific HTTPX
clients supplied. Static scans found zero generic bypass flags and zero
uncontrolled direct server HTTP callsites.

Installed dependencies are HTTPX `0.28.1` and HTTPCore `1.0.9`. The
instrumented `httpcore.NetworkBackend` proof confirms the accepted seam:
controlled socket address with the canonical hostname retained by HTTPCore for
Host, SNI, and certificate verification. Requirements permit compatible
HTTPX `<1.0` and HTTPCore `<2.0`; a dependency update still requires rerunning
this seam proof before acceptance.

Backend Kubernetes SDK endpoints and database DSNs remain installation-trusted
boundaries and are not tenant HTTP destinations. Cloud SDK metadata credential
chains remain agent/provider SDK behavior; there is no central metadata egress
purpose. CLI user-selected Topo egress, agent control/cloud/Kubernetes/Docker
egress, and browser same-origin Topo API traffic remain separate from the
server external-destination policy.

## Typed customer-data attack matrix

| Attack | Result |
|---|---|
| Raw `raw_payload` / `payload_json` marker | remains internally present; absent from OpenAI and Groq content |
| Nested/double-encoded opaque JSON and unknown evidence keys | excluded by the code-owned evidence allowlist |
| Unknown envelope fields | extra-forbid rejection for raw payload, headers, secret, environment, provider body and arbitrary extras |
| Secret object/type injection | impossible/rejected; secret objects are not stringified |
| Copilot question/history and responder-note secrets | known bearer/basic/provider token, DB URL, credential URL and PEM forms scrubbed |
| Provider key as content | absent; provider credential exists only in exact-destination transport authentication |
| Tenant identifier | used for validation only and excluded from serialized customer context |
| Foreign tenant evidence/object | tenant mismatch before provider dispatch; provider request count zero |
| Foreign/unbacked evidence reference | envelope validation failure before dispatch |
| Model-invented evidence reference | existing service validation rejects unknown evidence; no global existence lookup |
| Identifier/text field bounds | 256/512/1024/4096-character policies enforced deterministically |
| Collection bounds | messages 10, entities 50, relationships 100, changes 50, evidence 100, warnings 50 |
| Total envelope | maximum 65,536 serialized UTF-8 bytes; multibyte overflow rejects before dispatch |
| Provider parity | OpenAI and Groq receive identical safe customer-context JSON and data-class policy |
| System-prompt bypass | customer data supplied only as `SafeLLMRequest.customer_context_json`; count zero elsewhere |
| Cache attack | no unscoped global customer-context cache exists |

All eight LLM purposes use the shared builder and a purpose-specific typed
envelope. Generic arbitrary customer-context API count and direct boundary
bypass count are zero.

## LLM authority and failure behavior

User-authored hostile instructions may be narrative content after bounded
scrubbing; they receive no tenant, authorization, credential, deterministic
RCA/evidence, or execution authority. Raw Kubernetes/provider prompt injection
has no LLM egress path. Production LLM clients expose no tools, functions,
tool choice, function call, agent loop, or automatic MCP execution. Automatic
tool execution count is zero.

Model output remains a validated optional explanation/result owned by the
calling service. It cannot mutate memberships, select another tenant, retrieve
or rotate credentials, execute remediation, or replace durable deterministic
causal truth. Foreign evidence references are rejected. With the LLM disabled,
incident detection, topology, changes, evidence, causal ranking, blast radius,
ownership and incident state continue deterministically. Timeout, TLS, DNS,
oversize, unavailable-provider, empty and invalid structured-response cases
degrade through bounded failure paths without authority gain or content leak.

## Webhook data boundary

All eight existing webhook event types were constructed with the matching
typed payload: incident created, incident status changed, recommendation
generated, recovery verified, recovery failed, recovery inconclusive, change
risk detected, and webhook test. Wrong pairings and extra fields are rejected.
`raw_payload` and `payload_json` cannot enter the typed body. Known secret
markers in admitted text are scrubbed; protected headers and signing material
remain transport-only. The maximum body is 131,072 serialized UTF-8 bytes, and
multibyte overflow fails before dispatch.

Endpoint ownership is checked against the server-authoritative tenant before
body/credential/network work. A Tenant B endpoint presented in Tenant A
context fails with zero dispatches. A safe typed body plus unsafe destination
is stopped by PH-6B; an approved destination plus forbidden raw-data attempt is
stopped by PH-6C. PH-5 authorization still precedes privileged webhook
configuration changes.

## Browser analytics and external sink completeness

Authenticated product sources contain zero Vercel Analytics imports/mounts,
zero alternate analytics vendors, and zero analytics calls containing tenant,
incident, report, session, analysis, or snapshot identifiers. Browser egress
remains the single same-origin Topo API helper. No hashing workaround was
introduced.

The exact reviewed external policy registry is `GITHUB`, `TENANT_WEBHOOK`,
`OPENAI`, `GROQ`, and disabled-for-authenticated-product
`VERCEL_ANALYTICS`. Unknown sink count is zero. No additional production
customer-data sink was discovered.

## Error, log and audit hygiene

Injected bearer, webhook secret, provider token, database URL, signed URL,
private-key, prompt, raw payload, private target, metadata target and provider
echo markers were absent from public errors and log output. Webhook delivery
persists no remote response body. Provider errors retain only a code-owned
operation and exception type. Security audit remains limited to its frozen
security/admin vocabulary and carries no LLM prompt, webhook body, signed URL,
resolved IP, or provider response.

## Verification receipts

Every external interaction was mocked or used a controlled local transport.
No live OpenAI, Groq, GitHub, cloud, Kubernetes, metadata, or tenant webhook
endpoint was contacted.

| Gate | Exact result |
|---|---|
| PH-2 focused authentication | 84 passed; 1 known warning |
| PH-3 tenant/adversarial | 227 passed, 86 skipped; 2 known warnings |
| PH-4 secret custody | 136 passed, 89 skipped; 1 known warning |
| PH-5 selected authority/closure | 65 passed, 4 skipped; 1 known warning |
| PH-6A focused | 13 passed |
| PH-6B focused | 45 passed; 1 known warning |
| PH-6C focused | 16 passed |
| PH-6D focused | 144 passed; 1 known warning |
| Full backend SQLite | 1,857 passed, 272 skipped; 2 known warnings; 731.64s |
| Full backend PostgreSQL 16 | 2,121 passed, 8 skipped; 2 known warnings; 1,993.55s |
| PostgreSQL logical backup/restore | passed inside full PostgreSQL run |
| Evaluation compile/full offline | compile passed; 917 passed, 3 skipped; 128.96s |
| Significant deterministic LINEAGE/causal | 1,249 passed; 139.58s |
| Broad mocked LLM/customer-data | 192 passed; 1 known warning |
| Mocked GitHub/source/artifact | 480 passed; 1 known warning |
| Mocked webhook | 223 passed; 1 known warning |
| CLI compile/full | compile passed; 85 passed |
| Agent compile/full | compile passed; 24 passed, 1 skipped |
| Frontend tests | 96 passed |
| Frontend typecheck | passed |
| Frontend lint | passed with 0 errors and 11 pre-existing warnings |
| Frontend production build | passed; all 14 routes generated |
| Backend compile | passed |
| Scanner tests | 12 passed |
| Tracked-tree scan | passed, zero findings |
| New-file scan | 6 files scanned, zero findings |

The PostgreSQL environment was `postgres:16-alpine`, published only on
`127.0.0.1:55436`, with `/var/lib/postgresql/data` on tmpfs, no persistent
volume, and automatic removal. The exact container was removed after the run.
The first frontend build attempt could not fetch configured Google Fonts while
network was sandboxed; the identical build passed once allowed network access.
This was not a source compilation failure.

## Migration and protected-artifact custody

There is no migration diff. Canonical committed Git-blob SHA-256 values are:

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

Protected actual-byte hashes before and after all tests are unchanged:

- `backend/data/topo.db`:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
- frozen post-SC4 LINEAGE database:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

## Accepted claim boundary and residual limitations

PH-6 closes the reviewed application egress inventory, code-owned central
server HTTP purposes, public-HTTPS-only tenant webhook SSRF policy,
actual-address DNS enforcement, rebinding resistance under the accepted
HTTPX/HTTPCore seam, redirect denial/reviewed artifact hops,
credential-to-destination binding, proxy isolation, bounded responses, typed
sink policy, eight typed LLM envelopes, raw/structural-secret exclusion,
bounded scrubbed admitted user text, tenant fail-closed behavior, typed bounded
webhooks, disabled authenticated analytics, LLM non-authority, and adversarial
network/customer-data acceptance.

Residual limitations are explicit. PH-6 does not claim OS/firewall
default-deny, Kubernetes NetworkPolicy, cloud firewall closure, service mesh,
enterprise proxy support, private tenant webhooks, perfect prompt-injection or
semantic secret/PII detection, provider zero retention/no-training, data
residency, compliance certification, general DLP, retention/deletion,
backup/recovery, deployment/rollback, capacity/SLO, or autonomous-remediation
safety. A deliberately pasted secret in an unknown format can evade a
pattern-based scrubber; structural exclusion, allowlists, bounds and exact
destination binding reduce but do not eliminate that residual risk.

## Handoff

PH-6D stops here. It does not provision or modify cloud infrastructure. The
recommended next engineering milestone is **CLOUD-V1-1A — First Real AWS/EKS
Internal Golden**, to measure the real GitHub → Actions/build → immutable image
→ EKS deployment → runtime failure → incident → historical topology pin →
evidence-backed RCA path.

PH-6D ACCEPTED / PH-6 CLOSED
