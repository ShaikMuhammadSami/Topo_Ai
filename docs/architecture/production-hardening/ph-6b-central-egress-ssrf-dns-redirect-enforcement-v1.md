# PH-6B — Central Egress / SSRF / DNS / Redirect Enforcement v1

## 1. Decision and scope

PH-6B starts from main commit `c9ed87c9006acd04cf90e2da61f65ece784d8bd2`
on `security/ph-6b-central-egress-ssrf-dns-redirect-v1`. It converts the
accepted PH-6A server HTTP contract into executable policy for GitHub,
tenant-webhook, OpenAI, and Groq traffic. It does not alter browser, CLI,
agent, Kubernetes-control-plane, database, or cloud-SDK transports.

The PH-6A inventory remains the forensic pre-enforcement record: 103 reviewed
network callsites, 95 production callsites, 28 server-production callsites,
64 agent-controlled callsites, one CLI user-directed callsite, two browser
callsites, eight evaluation-only callsites, and zero unknown callsites. The 28
server callsites are still present as product operations, but all HTTP dispatch
is now mediated by one central transport or one of two SDK adapters backed by
that transport. Uncontrolled server HTTP dispatch count is zero.

PH-6B adds no route, permission, audit action, table, column, migration,
execution capability, private-tenant-egress option, or enterprise proxy
feature. PH-6C still owns typed LLM envelopes and raw customer-data exclusion.

## 2. Executable purpose registry

`app.security.egress_policy.EgressPurpose` is the only runtime policy key:

| Purpose | Method | Destination | Redirect | Timeout | Response ceiling |
|---|---:|---|---|---:|---:|
| `GITHUB_API_JSON_READ` | GET | exact installation GitHub origin | reject every 3xx | 20 s | 2 MiB |
| `GITHUB_SOURCE_CONTENT_READ` | GET | exact installation GitHub origin | reject every 3xx | 20 s | 160 KiB, further tightened by the caller's existing cap |
| `GITHUB_ARTIFACT_DOWNLOAD` | GET | exact GitHub origin or validated public redirect origin | manual, maximum four dispatched hops | 20 s | 32 MiB |
| `TENANT_WEBHOOK_DELIVERY` | POST | public HTTPS DNS origin only | terminal 3xx | at most 30 s | body is never consumed |
| `OPENAI_PROVIDER` | POST | exact `api.openai.com` origin | reject every 3xx | 60 s | 8 MiB |
| `GROQ_PROVIDER` | POST | exact `api.groq.com` origin | reject every 3xx | 60 s | 8 MiB |

Unknown purposes fail closed with `destination_not_allowed`. Application APIs
do not accept purpose, allowed host, port, address class, redirect behavior,
proxy behavior, TLS behavior, resolver, or bypass flags from callers. There is
no generic fetch/request API. The only public transport wrappers are narrow
GitHub reads, one prepared webhook POST, and fixed OpenAI/Groq HTTP clients.

The GitHub JSON ceiling is intentionally 2 MiB: current repository, commit,
workflow, and artifact-list fixtures are far smaller, while the ceiling is
large enough for normal provider pagination without permitting unbounded JSON.
Source reads retain the existing smaller per-use ceiling and cannot exceed the
160 KiB transport ceiling.

## 3. URL and address authority

URLs are structurally parsed. Scheme is HTTPS, effective port is 443, and the
host must be a DNS hostname. Userinfo, fragments, malformed authorities,
control characters, IP literals, integer/ambiguous IP spellings, and
non-default ports are rejected. Hostnames are lower-cased, trailing dots are
removed, and standard IDNA conversion is applied. Paths and queries remain
separate from origin authority. Tenant webhook paths/query names with
credential-shaped material are rejected; provider-issued artifact queries are
preserved as opaque capabilities and never rendered in public errors or logs.

The public policy validates the complete A/AAAA result set. Every address must
be globally routable. Loopback, RFC1918, ULA, link-local, unspecified,
multicast, reserved/non-global, metadata, IPv4-mapped IPv6, and mixed
public/private answer sets are rejected. The resolver is bounded to 16 unique
answers and has no authorization cache. The OS resolver supplies final
addresses after CNAME processing, so a CNAME ending at a forbidden address is
denied by the same whole-set rule. Resolution failures produce a bounded code
without exposing resolver details or returned addresses.

The sole private-address exception is the exact installation-configured GitHub
Enterprise origin. It may resolve wholly to RFC1918 or ULA addresses, but may
not resolve to loopback, link-local/metadata, unspecified, multicast, or other
special ranges. That authority is not reusable by tenant webhooks or
cross-origin artifact locations.

## 4. Actual-address connection binding

Installed versions are HTTPX 0.28.1 and HTTPCore 1.0.9. PH-6B uses HTTPCore's
public `NetworkBackend` extension point:

```text
canonical URL
  -> controlled A/AAAA resolution
  -> validate every candidate
  -> AddressBoundNetworkBackend.connect_tcp(validated IP, 443)
  -> HTTPConnection.start_tls(server_hostname=canonical DNS host)
  -> request Host: canonical DNS host
```

`AddressBoundHTTPTransport` leaves the HTTPCore request origin as the canonical
DNS authority but supplies an `AddressBoundNetworkBackend` whose socket target
is one of the exact validated IP values. Consequently HTTPCore passes the
canonical hostname to `start_tls`, the default SSL context enforces
`CERT_REQUIRED` and hostname checking, and the HTTP Host header remains the
canonical hostname. The normal socket path never resolves the hostname again.
An instrumented backend test proves all four values independently: resolver
input, socket target, TLS `server_hostname`, and wire Host header.

Keep-alive capacity is zero. Each new request/SDK retry obtains a fresh policy
decision and controlled resolution. A webhook attempt passes its already
validated `ResolvedDestination` into the network backend, so destination
approval and the actual socket use the same address set. There is no
independent second DNS resolution.

TLS uses Python's default verified context. Environment proxy inheritance is
off for every central client (`trust_env=False`); no proxy transport is
constructed. HTTP/1.1 is used, connection counts and resolver answer counts
are bounded, and no mutable default credentials or cookie jar are shared among
tenants or purposes.

## 5. Header, timeout, response, and error policy

The transport requires exactly one Host value equal to the canonical hostname
and strips HTTPX's connection header. Caller-controlled Host, Cookie,
Proxy-Authorization, Forwarded, `X-Forwarded-*`, hop-by-hop, transfer-encoding,
and upgrade headers are rejected. Accept-Encoding is fixed to `identity`, so
the byte ceiling applies to bytes actually consumed without a decompression
bomb ambiguity. Provider/webhook Authorization material is attached only by
the owning internal consumer after destination policy approval.

Connect, read, write, and pool timeouts are explicit. Webhook configuration may
only tighten the 30-second maximum. OpenAI/Groq retain two SDK retries and do
not gain a second application retry layer. GitHub has no new retry layer.
Webhook retry count/backoff remains its existing bounded product behavior, but
each attempt re-resolves and revalidates.

Declared Content-Length over a profile ceiling is rejected before body
consumption. Stream accounting aborts once the actual body crosses the same
ceiling. Non-identity content encoding is rejected. Webhook responses are sent
in streaming mode, only status/headers are observed, and the response body is
closed without consumption or persistence.

The bounded internal error codes are:

- `destination_invalid`
- `destination_not_allowed`
- `dns_resolution_failed`
- `redirect_not_allowed`
- `tls_failure`
- `timeout`
- `response_too_large`
- `upstream_unavailable`

Public errors never include a full URL/query, resolved address, socket text,
credential/header, request body, LLM prompt, or provider response body. PH-4
redaction remains an independent defense. No PH-5 security-audit action was
added for network telemetry.

## 6. Tenant webhook lifecycle

Create and update validate URL structure, canonical authority, current DNS,
and complete address classification before persistence. Update ordering is:

```text
structural origin comparison
  -> require integration.manage
  -> if origin/protected credential changes, also require credential.rotate
  -> controlled DNS/address validation
  -> persist
```

Thus an under-authorized origin change is denied before DNS, while an
authorized unsafe destination receives a distinct egress-policy denial. A
same-origin path/query or metadata-only update requires only
`integration.manage`; origin, signing-secret, or protected-header changes
require `integration.manage + credential.rotate`. PH-5D allowed/denied audit
records retain the exact permission conjunction.

At dispatch, the stored URL is never treated as permanently trusted. Each
normal/test/retry attempt validates and resolves before loading the signing
secret or protected headers. Those credentials are therefore bound to the
accepted `(https, canonical hostname, 443)` authority and the same prepared
address set used for TCP connection. Any 3xx is terminal and never causes a
second request, credential replay, or body replay. Receiver bodies remain
unread. Duplicate-delivery/idempotency semantics are unchanged.

## 7. GitHub policy

Installation GitHub configuration is canonical HTTPS, DNS hostname, port 443,
no userinfo/fragment/query, with TLS verification. Normal JSON and source
reads are exact-origin only and reject every 3xx. GitHub Enterprise may use a
wholly private address set only for that exact configured origin.

Artifact download manually dispatches at most four hops. Every dispatched hop
is independently canonicalized, resolved, classified, and address-bound.
Same-origin hops may retain the GitHub bearer according to the existing
provider protocol. A cross-origin hop strips it before dispatch and must be
public HTTPS DNS port 443. HTTP downgrade, loopback, metadata, private
cross-origin, userinfo, fragment, and non-443 targets are denied before a
second connection. Provider-signed queries remain usable but are absent from
logs, audit, and bounded public errors. Declared and streamed artifact bodies
remain capped at 32 MiB.

## 8. OpenAI and Groq transport adapters

The existing OpenAI provider creates its SDK with the fixed OpenAI central
client. All four former direct Groq constructors now use one factory that
creates the Groq SDK with the fixed Groq central client. The SDKs cannot select
an arbitrary base URL through product configuration. Provider keys are
request/provider scoped; exact-host policy rejects a request attempting to use
the other provider or an arbitrary host. Provider 3xx is rejected inside the
transport before the SDK can replay prompt or Authorization data. Both clients
ignore environment proxy variables and use verified TLS, fresh connection DNS,
60-second timeout components, two SDK retries, and an 8 MiB transport response
ceiling.

PH-6B deliberately does not alter prompt builders, evidence selection,
`NormalizedSignal.raw_payload`, `SignalRecord.payload_json`, or causal/evidence
semantics. The mocked marker `ph6c-opaque-raw-payload-marker` remains reachable
at the existing LLM assembly boundary. This is the accepted open PH-6C content
finding, not a PH-6B network failure.

## 9. Explicitly separate trusted boundaries

- Backend Kubernetes remains `TRUSTED_INFRA_CONTROL_PLANE`; its installation
  kubeconfig/in-cluster private endpoint and native SDK semantics are not
  routed through public egress policy. No tenant request can replace that
  endpoint.
- PostgreSQL remains the installation-owned trusted datastore and is not HTTP
  egress.
- AWS, Azure, and GCP SDKs retain native signing, credential, paging, and
  metadata-chain behavior under the PH-6A reviewed provider boundary.
- Agent Topo/cloud/Kubernetes/Docker egress remains agent-controlled and is not
  migrated into the server policy.
- CLI user-directed and browser same-origin/vendor traffic retain their
  separate threat models. Frontend source is unchanged.

## 10. Completeness and frozen authority

Static tests scan production sources so `httpx.Client(` may occur only in the
central transport, direct `OpenAI(` and `Groq(` only in the SDK adapter module,
and known bypass-flag spellings nowhere in application source. The historical
28 server-production operations therefore map to six code-owned purposes or
two approved SDK adapters, with zero uncontrolled direct HTTP callsites,
generic fetch APIs, generic bypass flags, environment-proxy central clients,
unbounded central responses, or central no-timeout calls.

Frozen acceptance counts remain:

- routes 143, new 0;
- critical operations 98;
- permissions 18 (14 tenant, four installation, zero execution);
- audit actions/reasons/fields 33/11/15;
- Alembic heads one, head `0015_security_audit`;
- ORM 50 tables and 844 columns; and
- new migration none.

## 11. Tests

The focused PH-6B module proves hostile webhook URL/address matrices, IDNA and
trailing-dot canonicalization, complete/mixed DNS denial, actual-IP socket
binding, Host/SNI/certificate identity, no second DNS, private GitHub exact
origin, proxy isolation, exact provider hosts, SDK adapter injection, declared
and streamed response ceilings, bounded error text, authorization-before-DNS,
delivery-before-decryption ordering, retry re-resolution, terminal webhook
redirects, artifact every-hop policy, cross-origin bearer stripping, unsafe
artifact redirects, hop limit, static direct-client completeness, and frozen
route/operation/permission/audit/schema counts.

All provider, LLM, DNS, and network correctness tests use controlled fake
resolvers/backends. No acceptance test depends on live DNS, GitHub, OpenAI,
Groq, cloud, Kubernetes, or a tenant receiver.

Final receipts:

| Gate | Result |
|---|---|
| PH-2 focused | 86 passed, one warning |
| PH-3 focused | 229 passed, 86 skipped, two warnings |
| PH-4 focused | 136 passed, 89 skipped, one warning |
| PH-5 focused | 177 passed, 30 skipped, one warning |
| PH-6A focused | 13 passed |
| PH-6B focused | 45 passed, one warning |
| Full backend SQLite | 1697 passed, 272 skipped, two warnings |
| Full backend PostgreSQL 16 | 1961 passed, eight skipped, two warnings |
| Full offline evaluation | 917 passed, three skipped |
| Significant deterministic LINEAGE | 319 passed |
| Mocked LLM/customer-data group | 261 passed, two warnings |
| Mocked GitHub/source/artifact group | 175 passed, one warning |
| CLI compile / full tests | compile passed / 85 passed |
| Agent compile / full tests | compile passed / 24 passed, one skipped |
| Frontend configured tests | 93 passed |
| Backend/evaluation compile | passed |
| Secret scanner | 12 tests and 14 subtests passed; tracked and four-new-file scans passed with zero findings |
| `git diff --check` | passed |

The PostgreSQL acceptance environment is `postgres:16-alpine`, published only
on loopback, with its data directory on tmpfs, no persistent volume, and
automatic removal. Provider and evaluation calls remain offline/mocked.

## 12. Custody

Canonical Git-blob SHA-256 values for immutable migrations are:

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

Migration diff remains empty. Protected actual-byte baselines are
`0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`
for `backend/data/topo.db` and
`9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`
for the frozen post-SC4 LINEAGE database. Final before/after rechecks match
these accepted values. Migration Git-blob hashes also match their accepted
before values, and migration/protected-artifact diffs are empty.

## 13. PH-6C handoff

PH-6C receives verified network destination, DNS/address, TLS, redirect,
credential-binding, proxy, timeout, retry, response-bound, and safe-error
enforcement. Its exact next responsibility is typed purpose-specific LLM
customer-data envelopes, absolute secret exclusion, raw-payload exclusion,
field/count/byte bounds, the user-authored Copilot boundary, and the existing
browser analytics route-metadata decision. PH-6B does not begin that work.

PH-6B ACCEPTED / READY FOR ARCHITECT REVIEW
