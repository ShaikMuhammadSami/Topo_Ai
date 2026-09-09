# PH-5E Adversarial Authorization and Security Audit Acceptance / PH-5 Closure v1

Date: 2026-09-09  
Repository: `C:\Topo-ai`  
Branch: `security/ph-5e-adversarial-authorization-audit-closure-v1`  
Accepted starting commit: `f1f0473a8a67f18163440f2fcf28c67ba65a9942` (`feat(security): add durable security admin audit (#88)`)

## Scope and decision

PH-5E attempted to falsify the combined PH-5A through PH-5D identity,
authorization, authority-separation, masking, and durable security-audit
contracts. It added adversarial acceptance tests and made one bounded audit
validation repair after a test proved a concrete defect. It did not add or
change a permission, role, route, table, migration, identity rule, tenant
rule, credential policy, machine-authority rule, or execution capability.

Verdict: `PASS_PH5_CLOSE`.

PH-5E is complete and PH-5 is closed. No PH-6 or CLOUD-V1-1A work was started.

## Frozen contract

The accepted V1 authority vocabulary remains exactly 18 permissions: 14
tenant permissions and four installation permissions. The three human tenant
roles remain Viewer, Responder, and Admin; the only installation role remains
Installation Operator. Service authority remains an explicit subset of the
nine service-assignable tenant permissions. Agent and provider authority
remain fixed-purpose machine authority outside the human/service permission
resolver. There are zero execution, approval, remediation, or wildcard
permissions.

The route plan remains exactly 143 live routes, with zero unknown, duplicate,
or new routes and no unclassified live route. The critical-operation plan
remains exactly 98 operations, with zero unprotected operations. Unknown
operations fail closed. The authenticator credential policy remains the exact
eight-operation matrix for create/list/get/revoke across human and service
credential targets.

The audit vocabulary remains 33 actions and 11 reasons. The durable event
schema remains exactly these 15 fields, in order:

1. `audit_event_id`
2. `occurred_at`
3. `actor_principal_id`
4. `actor_kind`
5. `actor_reference`
6. `authentication_type`
7. `authority_kind`
8. `tenant_id`
9. `action`
10. `permissions_json`
11. `resource_type`
12. `resource_id`
13. `result`
14. `reason_code`
15. `request_id`

The audit repository still exposes only append. Audit records are evidence,
never an input to permission resolution.

## Adversarial matrix

| Family | Attack | Accepted result |
|---|---|---|
| Identity | Same subject under different issuers | Distinct external identities and principals; no membership, credential, or permission crossover |
| Identity | Same exact issuer and subject concurrently | One semantic external identity and one principal under PostgreSQL READ COMMITTED |
| Identity | `User123` versus `user123`, plus issuer-case variance | Exact, case-sensitive identity; no case folding |
| Identity | Equal display names and email-shaped subjects | No merge or authority transfer |
| Identity | Human/service resolver type confusion | Fails closed |
| Identity | Disable an otherwise authorized principal | Session/API/service/installation authority disappears on the next authoritative request or transaction |
| Tenant roles | Same principal Viewer in tenant A and Admin in tenant B | Exact per-membership authority; no strongest-role cache or cross-tenant borrowing |
| Tenant roles | Viewer and Responder escalation | Denied outside the explicit bundle |
| Tenant roles | Tenant Admin to installation authority | Denied unless a separate installation assignment exists |
| Installation | Installation Operator to tenant authority | Denied without an independent tenant membership |
| Dual authority | Operator plus Viewer in tenant A | Installation and tenant scopes remain separate; tenant authority remains Viewer |
| Legacy inputs | Legacy principal roles such as admin/operator/superuser | Zero PH-5 authority effect |
| Subject inputs | Subject/external subject as authorization key | Zero PH-5 authorization lookups; `principal_id` remains authoritative |
| Service | `incident.read`-only service | Incident read allowed; evidence, topology, and integration authority denied |
| Service | Forbidden admin/installation permission assignment or DB tamper | Assignment rejected or resolver fails closed |
| Service | Unknown, duplicate, malformed, noncanonical, admin, or installation permission JSON | Whole resolution fails closed; no best-effort filtering |
| Service | Permission reduction | Removed permission is unavailable on the next transaction; retained permission remains available |
| Service | Two credentials for one service principal | Same principal, tenant, and permission set; revoking one does not revoke the other |
| Service | Foreign-tenant use | Fixed credential tenant cannot be overridden |
| Credentials | Human credential CRUD | Self-only create/list/get/revoke |
| Credentials | Other-human and Tenant Admin impersonation attempts | Denied; tenant administration is not human credential impersonation |
| Credentials | Service self-administration and Responder administration | Denied |
| Credentials | Same-tenant Admin service-credential administration | Allowed only through the target-aware human administration contract |
| Credentials | Foreign or absent service credential | Identical masked 404 and no existence-confirming audit |
| Credentials | Human/service credential type confusion | Fails closed |
| Machine | Agent token | Fixed agent purpose only; no human, service, installation, or execution authority |
| Machine | Provider webhook | Signature/proof verified before payload parsing or tenant use |
| Machine | Payload tenant override | Ignored; authoritative server binding remains controlling |
| Execution | Every dormant approval/execution HTTP surface | Ten routes return 401 anonymously and exact 403 for every authenticated V1 authority |
| Execution | Direct dormant approval/execution services | Eleven operations deny; no execution permission exists |
| Masking | Foreign versus nonexistent tenant object | Same 404 status/body and same zero-audit result where masking applies |
| Audit | Forged audit permissions/actions | No authority change |
| Audit | Duplicate denial attempts in one request | One semantic denial event, with required permissions only |
| Audit | Allowed mutation failure | No false allowed event survives rollback |
| Audit | Audit-write failure during denied authorization | Authorization remains denied |
| Audit | Hostile secret/control/oversize input | Rejected or redacted; no raw secret in DB, log, or response |

## Actor, result, and masking truth

Human, service, agent, provider, and local-operator events preserve their real
actor and authentication boundaries. `authority_kind` follows the operation
scope rather than a principal's strongest unrelated assignment. Required
permissions, action, result, reason, resource type, and bounded resource ID
are derived by code-owned registries and the operation that actually ran.

The HTTP distinction remains:

- unauthenticated requests return 401;
- authenticated same-scope requests without required permission return 403;
- foreign tenant objects use the existing masked 404 contract where required.

Foreign and nonexistent masked probes are response-equivalent and audit-
equivalent. A masked foreign probe does not create an existence-confirming
audit row.

## Audit transaction and durability proof

SQLite and PostgreSQL prove that ordinary DB-backed privileged mutations and
their allowed audit event commit or roll back together. Business-operation
failure leaves no false success event. Denial audit is best-effort durable and
cannot turn denial into permission if its writer fails. One request produces
one semantic denial event. Concurrent audit appends retain distinct event IDs
and complete rows.

Audit history does not influence identity, membership, service permission,
installation assignment, credential authentication, or authorization. Direct
insertion or mutation of a hostile audit row cannot grant authority.

## Bounded defect found and repaired

First semantic divergence: `_bounded()` in
`backend/app/services/security_audit.py` rejected control characters and
oversized values but accepted an HTTP(S) `resource_id` containing URL userinfo
credentials. That violated the PH-5D/PH-5E rule that raw credential-bearing
URLs cannot enter the audit ledger.

The bounded repair parses only audit `resource_id` values and rejects HTTP(S)
URLs with a username or password using the existing
`AUDIT_RESOURCE_ID_INVALID` validation failure. It does not rewrite, store,
log, or return the URL. The regression builds a synthetic credential-bearing
URL from fragments and proves that no event is appended. No other audit field
semantics changed.

## Concurrency and current-authority proof

Real PostgreSQL 16 (`postgres:16-alpine`) ran loopback-only with a tmpfs data
directory and no persistent volume. READ COMMITTED tests prove next-
transaction visibility for:

- human Admin-to-Viewer demotion;
- service permission reduction;
- installation-operator disablement;
- human credential revocation;
- tenant-membership removal/disablement; and
- concurrent same-issuer/same-subject identity provisioning.

Concurrent provisioning produced one semantic external identity and one
principal. Concurrent audit writers produced both unique events. PH-5D's six
PostgreSQL audit tests, including backup/restore, also passed in the full
PostgreSQL run. The disposable container was removed after verification.

## Secret-exclusion proof

Adversarial values covered token shapes, provider secrets, database-password
URLs, protected headers, SecretStore-shaped material, control characters, and
oversized values. Observed raw secret markers:

- audit database: 0;
- audit logs: 0;
- authorization responses: 0;
- raw credential URL markers: 0.

The SEC-1 scanner itself is unchanged. Its 12 tests pass, the tracked-tree
scan passes, and the explicit PH-5E new-file scan reports zero findings.

## Schema and immutable custody

No migration was created. Alembic has one head,
`0015_security_audit`. The ORM remains 50 tables and 844 columns. `git diff`
for `backend/alembic/versions` is empty.

Canonical Git-blob SHA-256 values before and after PH-5E are identical:

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

Protected binary custody also remained exact:

| Artifact | Before and after SHA-256 |
|---|---|
| `backend/data/topo.db` | `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E` |
| `evaluation/results/lineage/post-sc4/topo-product-32695735269.db` | `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F` |

## Verification results

All mandatory gates passed after the bounded repair:

| Gate | Exact result |
|---|---|
| PH-2 focused | 82 passed; 1 warning |
| PH-3 focused | 156 passed; 54 skipped; 2 warnings |
| PH-4 focused | 130 passed; 75 skipped; 1 warning |
| PH-5A focused | 13 passed; 5 PostgreSQL-conditional skips; 1 warning |
| PH-5B focused | 91 passed; 20 PostgreSQL-conditional skips; 1 warning |
| PH-5C focused | 29 passed; 2 PostgreSQL-conditional skips; 1 warning |
| PH-5D focused | 21 passed; 6 PostgreSQL-conditional skips; 1 warning |
| New PH-5E SQLite acceptance | 36 passed; 2 PostgreSQL-conditional skips; 1 warning |
| New PH-5E PostgreSQL acceptance | 2 passed in the full PostgreSQL run |
| Full backend SQLite | 1,639 passed; 272 skipped; 2 warnings in 761.65 s |
| Full backend PostgreSQL | 1,903 passed; 8 skipped; 2 warnings in 2,025.27 s |
| Evaluation compile | Passed |
| Full evaluation | 917 passed; 3 skipped in 67.68 s |
| Significant source/build/image/runtime lineage | 347 passed in 16.98 s |
| Mocked LLM, briefing, history, and report paths | 170 passed; 1 warning in 23.95 s |
| CLI compile and full suite | Compile passed; 85 passed in 5.77 s |
| Agent compile and full suite | Compile passed; 24 passed; 1 skipped in 11.29 s |
| Configured frontend tests | 93 passed; 0 failed |
| Backend compile | Passed |
| Secret-scanner tests | 12 passed |
| Tracked-tree secret scan | Passed; zero findings |
| PH-5E new-file secret scan before this document | 11 files; zero findings |

The two backend warnings are an existing Starlette TestClient/httpx
deprecation and an intentional SQLAlchemy identity-key conflict exercised by
an adversarial rollback test. No live LLM call was made. Frontend source did
not change, so PH-5E required the configured frontend tests but not a new
typecheck, lint, or production-build gate.

## Files and product boundary

Product code modified:

- `backend/app/services/security_audit.py`

Acceptance tests created:

- `backend/tests/test_ph5e_identity_adversarial.py`
- `backend/tests/test_ph5e_tenant_role_adversarial.py`
- `backend/tests/test_ph5e_service_authority_adversarial.py`
- `backend/tests/test_ph5e_installation_authority_adversarial.py`
- `backend/tests/test_ph5e_credential_policy_adversarial.py`
- `backend/tests/test_ph5e_machine_authority_adversarial.py`
- `backend/tests/test_ph5e_execution_deny_adversarial.py`
- `backend/tests/test_ph5e_contract_static_adversarial.py`
- `backend/tests/test_ph5e_audit_adversarial.py`
- `backend/tests/test_ph5e_masking_adversarial.py`
- `backend/tests/test_ph5e_postgres_adversarial.py`

This closure document is the only documentation addition. Evaluator,
workflow, frontend, CLI, agent, migration, permission, role, tenant, identity,
secret-custody, causal/evidence, and dormant execution product code have zero
diff.

## Accepted PH-5 claims

PH-5 may claim issuer-aware durable principal identity; an explicit minimum
V1 permission vocabulary; explicit human tenant roles; explicit bounded
service permissions; independent installation-operator authority; complete
route/service authorization enforcement; fixed-purpose agent/provider
authority; target-aware credential administration; dormant execution denial;
durable minimum security/admin audit; 401/403/404 authorization semantics;
application-level append-only audit; transactional audit for ordinary DB-
backed privileged mutations; and adversarially tested authority separation.

## Explicit limitations and PH-6 handoff

PH-5 does not claim enterprise SSO/OIDC, SCIM, custom roles, ABAC,
PostgreSQL RLS, HSM/KMS/BYOK, SOC 2 compliance, cryptographic audit
immutability, SIEM integration, audit export, retention/deletion closure,
network/SSRF closure, backup/recovery closure, deployment/rollback closure,
capacity/SLO closure, or autonomous-remediation safety.

The recommended next block is PH-6 — Network / SSRF / Egress /
Customer-Data / LLM Boundary. That work has not begun.

PH-5E ACCEPTED / PH-5 CLOSED
